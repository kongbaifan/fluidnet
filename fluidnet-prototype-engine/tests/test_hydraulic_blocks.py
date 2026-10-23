"""D0–D2 依赖安全的水力分块求解验收测试。

覆盖：独立分量可拆、Python 多端口保守同块、未知依赖降级整网、换热器两回路热力依赖、
分块/常规求解的 3.1 差值门、原未知量布局、warm start 切片、块失败定位、难收敛块不影响
其他块重复迭代、动态一致性与模块生命周期、以及批量 Worker 子集不新建 Worker。
"""
import dataclasses
import importlib.util
import json

import numpy as np
import pytest

from fn_engine import partition
from fn_engine.batch import BatchRunners
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import (ChannelSpec, Connection, Endpoint, ModuleDefinition, ModuleInstance, PortSpec,
                              Project)
from fn_engine.partition import (BlockSolveError, HydraulicBlockFailure, build_blocks, clear_plan_cache,
                                 plan_signature, resolve_plan, solve_hydraulics_hook)
from fn_engine.solver import (CompilationError, HydraulicNotConverged, _close_runners, _python_runners,
                              _retryable, solve_dynamic, solve_hydraulics, solve_steady)
from test_thermal import hx_network, prototype

CATALOG = catalog_map()


@pytest.fixture(autouse=True)
def _fresh_plan_cache():
    clear_plan_cache()
    yield
    clear_plan_cache()


def link(connection_id, source, target):
    (si, sp), (ti, tp) = source.split(':'), target.split(':')
    return Connection(id=connection_id, source=Endpoint(instance_id=si, port_id=sp),
                      target=Endpoint(instance_id=ti, port_id=tp))


def project(instances, connections, extra_modules=(), **solver):
    kinds = sorted({kind for _, kind, _ in instances if kind in CATALOG})
    model = Project(id='blocks', name='blocks',
                    modules=[CATALOG[kind] for kind in kinds] + list(extra_modules),
                    instances=[ModuleInstance(id=name, module_id=kind, name=name, parameters=parameters)
                               for name, kind, parameters in instances],
                    connections=[link(f'e{index}', source, target)
                                 for index, (source, target) in enumerate(connections)])
    for key, value in solver.items():
        setattr(model.solver, key, value)
    return model


def two_lines():
    """两个完全独立的水网：一条管道 + 一个阀门。"""
    return project(
        [('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
         ('L1', 'pipe', {'length_m': 30., 'diameter_m': 0.04}),
         ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
         ('B3', 'source', {'pressure_pa': 220000., 'temperature_k': 293.15}),
         ('V1', 'valve', {'opening_ratio': 0.7, 'kv_m3_h': 16.}),
         ('B4', 'source', {'pressure_pa': 130000., 'temperature_k': 293.15})],
        [('B1:out0', 'L1:in0'), ('L1:out0', 'B2:out0'),
         ('B3:out0', 'V1:in0'), ('V1:out0', 'B4:out0')])


def pipe_line():
    """单条独立管道回路（用于对照「易收敛块」）。"""
    return project(
        [('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
         ('L1', 'pipe', {'length_m': 30., 'diameter_m': 0.04}),
         ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
        [('B1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')])


def pump_line():
    """单个「泵 + 阀」回路（用于对照难收敛块）。"""
    return project(
        [('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
         ('P1', 'pump', {'speed_ratio': 1.0}),
         ('V1', 'valve', {'opening_ratio': 0.5, 'kv_m3_h': 10.}),
         ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
        [('B1:out0', 'P1:in0'), ('P1:out0', 'V1:in0'), ('V1:out0', 'B2:out0')])


def combined():
    """独立管道块 + 独立泵阀块，共 2 块。"""
    return project(
        [('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
         ('L1', 'pipe', {'length_m': 30., 'diameter_m': 0.04}),
         ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
         ('B3', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
         ('P1', 'pump', {'speed_ratio': 1.0}),
         ('V1', 'valve', {'opening_ratio': 0.5, 'kv_m3_h': 10.}),
         ('B4', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
        [('B1:out0', 'L1:in0'), ('L1:out0', 'B2:out0'),
         ('B3:out0', 'P1:in0'), ('P1:out0', 'V1:in0'), ('V1:out0', 'B4:out0')])


TWO_SIDED = '''class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("commit_count", 0)

    def evaluate(self, ctx):
        ctx.net.valve(channel="a", kv=10.0, opening=1.0)
        ctx.net.valve(channel="b", kv=10.0, opening=1.0)

    def commit_step(self, ctx, dt_s):
        ctx.state["commit_count"] = int(ctx.state.get("commit_count", 0)) + 1
'''


def multiport_module():
    ports = [PortSpec(id=name, label=name, direction='in' if name.startswith('in') else 'out')
             for name in ('in0', 'out0', 'in1', 'out1')]
    return ModuleDefinition(
        id='twosided', name='twosided', runtime='python', entrypoint='module:Module', solver_model='python_x',
        source={'runtime': TWO_SIDED}, ports=ports,
        channels=[ChannelSpec(id='a', name='a', input_port='in0', output_port='out0',
                              relation='resistance', solver_model='python_x'),
                  ChannelSpec(id='b', name='b', input_port='in1', output_port='out1',
                              relation='resistance', solver_model='python_x')])


def multiport_project(with_line=True, **solver):
    """一个 Python 多通路实例（两个互不相连的回路）+ 一条独立内置管路。"""
    module = multiport_module()
    instances = [('BH', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                 ('BC', 'source', {'pressure_pa': 240000., 'temperature_k': 293.15}),
                 ('M1', 'twosided', {}),
                 ('SH', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
                 ('SC', 'source', {'pressure_pa': 110000., 'temperature_k': 293.15})]
    connections = [('BH:out0', 'M1:in0'), ('M1:out0', 'SH:out0'),
                   ('BC:out0', 'M1:in1'), ('M1:out1', 'SC:out0')]
    if with_line:
        instances += [('B5', 'source', {'pressure_pa': 200000., 'temperature_k': 293.15}),
                      ('V5', 'valve', {'opening_ratio': 0.6, 'kv_m3_h': 12.}),
                      ('B6', 'source', {'pressure_pa': 150000., 'temperature_k': 293.15})]
        connections += [('B5:out0', 'V5:in0'), ('V5:out0', 'B6:out0')]
    return project(instances, connections, extra_modules=[module], **solver)


def two_multiports(module_parallelism=1):
    """两个 Python 多通路实例 + 一条独立管路：默认走批量 Worker。"""
    module = multiport_module()
    instances = [('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                 ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
                 ('M1', 'twosided', {}),
                 ('B3', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                 ('B4', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
                 ('M2', 'twosided', {}),
                 ('B5', 'source', {'pressure_pa': 230000., 'temperature_k': 293.15}),
                 ('V1', 'valve', {'opening_ratio': 0.6, 'kv_m3_h': 12.}),
                 ('B6', 'source', {'pressure_pa': 130000., 'temperature_k': 293.15})]
    connections = [('B1:out0', 'M1:in0'), ('M1:out0', 'M1:in1'), ('M1:out1', 'B2:out0'),
                   ('B3:out0', 'M2:in0'), ('M2:out0', 'M2:in1'), ('M2:out1', 'B4:out0'),
                   ('B5:out0', 'V1:in0'), ('V1:out0', 'B6:out0')]
    return project(instances, connections, extra_modules=[module], module_parallelism=module_parallelism)


def two_tanks(**solver):
    """两个独立的水箱回路（动态状态用于验证拆分→合并不丢状态）。"""
    return project(
        [('B1', 'source', {'pressure_pa': 201325., 'temperature_k': 293.15}),
         ('V1', 'valve', {'opening_ratio': 0.65, 'kv_m3_h': 16.}),
         ('TK1', 'tank', {'level_m': 2., 'area_m2': 2.5}),
         ('V2', 'valve', {'opening_ratio': 0.4, 'kv_m3_h': 16.}),
         ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
         ('B3', 'source', {'pressure_pa': 205000., 'temperature_k': 293.15}),
         ('V3', 'valve', {'opening_ratio': 0.5, 'kv_m3_h': 20.}),
         ('TK2', 'tank', {'level_m': 1.5, 'area_m2': 3.0}),
         ('V4', 'valve', {'opening_ratio': 0.5, 'kv_m3_h': 20.}),
         ('B4', 'source', {'pressure_pa': 125000., 'temperature_k': 293.15})],
        [('B1:out0', 'V1:in0'), ('V1:out0', 'TK1:in0'), ('TK1:out0', 'V2:in0'), ('V2:out0', 'B2:out0'),
         ('B3:out0', 'V3:in0'), ('V3:out0', 'TK2:in0'), ('TK2:out0', 'V4:in0'), ('V4:out0', 'B4:out0')],
        **solver)


# --------------------------------------------------------------------------- 3.1 差值门工具


def tolerance(key, reference):
    magnitude = abs(float(reference))
    if key.endswith('mass_flow_kg_s') or key.endswith('net_inflow_kg_s'):
        return 1e-8 + 1e-6 * magnitude
    if key.endswith('pressure_pa'):
        return 1.0 + 1e-8 * magnitude
    if key.endswith('temperature_k'):
        return 1e-5 + 1e-8 * magnitude
    if key.endswith('_w') or key.endswith('_j_kg') or key.endswith('_kg'):
        return 1e-6 + 1e-9 * magnitude
    return 1e-9 + 1e-9 * magnitude


def assert_close_with_gate(reference, actual, key, where=''):
    if isinstance(reference, bool) or reference is None or isinstance(reference, str):
        assert actual == reference, f'{where} {key}: {actual!r} != {reference!r}'
        return 0.0
    if not isinstance(reference, (int, float)):
        return 0.0
    gap, limit = abs(actual - reference), tolerance(key, reference)
    assert gap <= limit, f'{where} {key}: |{actual} - {reference}| = {gap:.3e} > {limit:.3e}'
    return gap / limit if limit else 0.0


def assert_hydraulics_close(blocked, regular, name):
    for index, (actual, reference) in enumerate(zip(blocked.pressures, regular.pressures)):
        assert_close_with_gate(reference, actual, 'pressure_pa', f'{name} node {index}')
    for index, (actual, reference) in enumerate(zip(blocked.flows, regular.flows)):
        assert_close_with_gate(reference, actual, 'mass_flow_kg_s', f'{name} branch {index}')
    assert blocked.solution is not None and regular.solution is not None
    assert blocked.solution.shape == regular.solution.shape
    for index, (actual, reference) in enumerate(zip(blocked.solution, regular.solution)):
        assert_close_with_gate(reference, actual, 'solution', f'{name} solution {index}')
    assert blocked.pressure_residual <= 1.0
    assert blocked.mass_residual <= 1e-8


def assert_frames_close(blocked_frames, regular_frames, name):
    assert len(blocked_frames) == len(regular_frames)
    for step, (blocked, regular) in enumerate(zip(blocked_frames, regular_frames)):
        assert blocked.variables.keys() == regular.variables.keys(), f'{name} frame {step} 变量集合不同'
        for key, reference in regular.variables.items():
            assert_close_with_gate(reference, blocked.variables[key], key, f'{name} frame {step}')
        for key, reference in regular.metrics.items():
            if key in ('iterations', 'matrix_size', 'matrix_nnz'):
                continue  # 分块后这些结构计数按块累加/取最大值，语义不同但不算物理结果
            assert_close_with_gate(reference, blocked.metrics[key], key, f'{name} frame {step} metric')


def block_of(network, plan, instance_id):
    for block in plan.blocks:
        if any(network.branches[index].instance_id == instance_id for index in block.branches):
            return block
    raise AssertionError(f'没有包含 {instance_id} 的块')


# --------------------------------------------------------------------------- D0：块划分（纯函数）


def test_build_blocks_splits_two_independent_water_networks():
    network = compile_project(two_lines())
    plan = build_blocks(network)
    assert plan.degraded is False
    assert plan.block_count == 2
    assert [len(block.open_branches) for block in plan.blocks] == [1, 1]
    assert sorted(node for block in plan.blocks for node in block.nodes) == list(range(len(network.node_keys)))
    assert sorted(index for block in plan.blocks for index in block.branches) == list(range(len(network.branches)))
    assert sorted(set(plan.node_block)) == [0, 1]
    assert sorted(set(plan.branch_block)) == [0, 1]
    assert len(set(plan.node_block)) == plan.block_count
    for block_id, block in enumerate(plan.blocks):
        assert block.id == block_id
        assert all(plan.node_block[node] == block_id for node in block.nodes)
        assert all(plan.branch_block[index] == block_id for index in block.branches)
    fixed = set(network.fixed_pressures)
    expected_steady = sum(1 for node in range(len(network.node_keys)) if node not in fixed) + len(network.branches)
    assert sum(block.unknowns_steady for block in plan.blocks) == expected_steady
    assert sum(block.unknowns_dynamic for block in plan.blocks) == plan.total_unknowns_dynamic
    payload = json.loads(json.dumps(plan.to_json(), ensure_ascii=False))
    assert payload['block_count'] == 2 and payload['degraded'] is False
    assert len(payload['blocks']) == 2 and payload['blocks'][0]['reason']


def test_build_blocks_keeps_multiport_python_instance_together():
    network = compile_project(multiport_project(with_line=False))
    # 编译期是两个独立的静态回路；Python 实例的 4 个端口把两侧保守并成一块。
    assert len(set(network.node_component)) == 2
    plan = build_blocks(network)
    assert plan.degraded is False
    assert plan.block_count == 1
    assert len(plan.blocks[0].open_branches) == 2
    assert plan.blocks[0].instances == ('M1',)
    assert any('M1' in note and '保守同块' in note for note in plan.blocks[0].notes)
    assert any('M1' in note for note in plan.notes)


def test_build_blocks_degrades_when_dependency_unknown():
    network = compile_project(two_lines())
    unknown_model = dataclasses.replace(
        network, branches=[dataclasses.replace(branch, solver_model='legacy_magic') if index == 0 else branch
                           for index, branch in enumerate(network.branches)])
    plan = build_blocks(unknown_model)
    assert plan.degraded is True
    assert plan.block_count == 1
    assert 'BRANCH_MODEL_UNKNOWN' in plan.reason
    assert list(plan.node_block) == [0] * len(unknown_model.node_keys)
    assert json.loads(json.dumps(plan.to_json(), ensure_ascii=False))['degraded'] is True
    # 降级后 hook 不接管：返回 None，继续常规求解路径。
    assert solve_hydraulics_hook(unknown_model, {}, 0.) is None


def test_plan_cache_keyed_by_structure_and_closed_state():
    network = compile_project(two_lines())
    first = resolve_plan(network)
    assert resolve_plan(network) is first
    assert plan_signature(network) == plan_signature(network)
    closed = dataclasses.replace(
        network, branches=[dataclasses.replace(network.branches[0], closed=True), network.branches[1]])
    assert plan_signature(closed) != plan_signature(network)
    replanned = resolve_plan(closed)
    assert replanned is not first
    # 关闭支路不传递压力耦合：只有管道那一条被拆成两个孤立边界节点，阀门回路仍是一块。
    assert replanned.block_count == 3
    assert len(replanned.solvable_blocks) == 1
    assert solve_hydraulics_hook(closed, {}, 0.) is None


# --------------------------------------------------------------------------- D1：顺序分块求解


def test_blocked_solver_matches_regular_on_two_independent_networks():
    network = compile_project(two_lines())
    assert build_blocks(network).block_count == 2
    regular = solve_hydraulics(network)
    blocked = solve_hydraulics(network, hooks=frozenset({'blocks'}))
    assert_hydraulics_close(blocked, regular, 'two-lines')
    assert blocked.solution.shape == regular.solution.shape
    unknown = [node for node in range(len(network.node_keys)) if node not in network.fixed_pressures]
    assert np.allclose(blocked.solution[:len(unknown)] * partition.PRESSURE_SCALE,
                       blocked.pressures[unknown], rtol=0, atol=1e-9)
    assert np.allclose(blocked.solution[len(unknown):], blocked.flows, rtol=0, atol=0)
    assert '分块求解 2/2 块' in blocked.method_reason


def test_blocked_solution_rebuilds_original_unknown_layout():
    network = hx_network()
    plan = build_blocks(network)
    assert plan.block_count == 2
    regular = solve_hydraulics(network)
    blocked = solve_hydraulics(network, hooks=frozenset({'blocks'}))
    assert_hydraulics_close(blocked, regular, 'hx-layout')
    unknown = [node for node in range(len(network.node_keys)) if node not in network.fixed_pressures]
    flows_offset = len(unknown)
    assert blocked.solution.shape == (flows_offset + len(network.branches),)
    assert np.allclose(blocked.solution[:flows_offset] * partition.PRESSURE_SCALE, blocked.pressures[unknown],
                       rtol=0, atol=1e-9)
    assert np.allclose(blocked.solution[flows_offset:], blocked.flows, rtol=0, atol=0)


def test_blocked_heat_exchanger_two_loops_thermal_dependency():
    network = hx_network()
    plan = build_blocks(network)
    assert plan.block_count == 2
    assert len(plan.dependencies) == 1
    edge = plan.dependencies[0]
    assert edge.kind == 'thermal' and 'HX' in edge.detail
    assert {edge.source, edge.target} == {0, 1}
    assert all(any('水力独立、热力耦合' in note for note in block.notes) for block in plan.blocks)
    regular = solve_hydraulics(network)
    blocked = solve_hydraulics(network, hooks=frozenset({'blocks'}))
    assert_hydraulics_close(blocked, regular, 'hx')


def test_blocked_warm_start_slices_initial_per_block(monkeypatch):
    network = hx_network()
    plan = build_blocks(network)
    regular = solve_hydraulics(network)
    real = partition.solve_hydraulics
    captured = []

    def spy(subnetwork, runners=None, time_s=0., **options):
        captured.append(options.get('initial'))
        return real(subnetwork, runners=runners, time_s=time_s, **options)

    monkeypatch.setattr(partition, 'solve_hydraulics', spy)
    warm = solve_hydraulics_hook(network, {}, 0., initial=regular.solution)
    assert warm is not None
    assert_hydraulics_close(warm, regular, 'warm')
    unknown = [node for node in range(len(network.node_keys)) if node not in network.fixed_pressures]
    flows_offset = len(unknown)
    expected = []
    for block in plan.solvable_blocks:
        pressure = [regular.solution[unknown.index(node)] for node in block.nodes if node in unknown]
        flows = [regular.solution[flows_offset + index] for index in block.open_branches]
        expected.append(np.array(pressure + flows, dtype=float))
    assert len(captured) == len(expected)
    for actual, want in zip(captured, expected):
        assert actual is not None
        np.testing.assert_array_equal(actual, want)
    # 形状不匹配的 initial 必须被忽略（冷启动），不能把别的向量误当本块初值。
    captured.clear()
    cold = solve_hydraulics_hook(network, {}, 0., initial=np.zeros(3))
    assert cold is not None
    assert all(item is None for item in captured)
    assert_hydraulics_close(cold, regular, 'cold-fallback')


def test_blocked_solver_uses_passed_runners_without_new_workers(monkeypatch):
    network = compile_project(multiport_project())
    plan = build_blocks(network)
    assert plan.block_count == 2
    regular = solve_hydraulics(network)
    runners = _python_runners(network)
    try:
        before_state = dict(runners['M1'].state)
        before_requests = runners['M1'].request_count

        def forbidden(*args, **kwargs):
            raise AssertionError('分块求解不得新建 Worker：runners 必须由调用方传入')

        monkeypatch.setattr('fn_engine.solver._python_runners', forbidden)
        blocked = solve_hydraulics(network, runners=runners, hooks=frozenset({'blocks'}))
        assert len(blocked.relations) == 2
        assert dict(runners['M1'].state) == before_state
        assert runners['M1'].request_count > before_requests
    finally:
        _close_runners(runners)
    assert_hydraulics_close(blocked, regular, 'manual-runners')


def test_batch_runner_subset_keeps_workers_and_matches():
    network = compile_project(two_multiports(module_parallelism=2))
    plan = build_blocks(network)
    assert plan.block_count == 3
    runners = _python_runners(network)
    assert isinstance(runners, BatchRunners)
    worker_ids = [id(worker) for worker in runners.workers]
    try:
        blocked = solve_hydraulics(network, runners=runners, hooks=frozenset({'blocks'}))
        # 子集视图只转发请求，绝不新建/关闭 Worker。
        assert [id(worker) for worker in runners.workers] == worker_ids
        assert all(worker.process is None or worker.process.poll() is None for worker in runners.workers)
        assert len(blocked.relations) == 4
    finally:
        _close_runners(runners)
    assert_hydraulics_close(blocked, solve_hydraulics(network), 'batch-subset')


def test_block_failure_reports_block_and_instance(monkeypatch):
    network = compile_project(combined())
    plan = build_blocks(network)
    target = block_of(network, plan, 'V1')
    real = partition.solve_hydraulics

    def flaky(subnetwork, *args, **kwargs):
        if any(branch.instance_id == 'V1' for branch in subnetwork.branches):
            raise HydraulicNotConverged('合成的不收敛块')
        return real(subnetwork, *args, **kwargs)

    monkeypatch.setattr(partition, 'solve_hydraulics', flaky)
    with pytest.raises(HydraulicBlockFailure) as info:
        solve_hydraulics(network, hooks=frozenset({'blocks'}))
    message = str(info.value)
    assert '水力分块' in message and 'V1' in message
    assert f'{target.id}/' in message
    # 收敛失败仍保持「可缩小步长」语义。
    assert isinstance(info.value, HydraulicNotConverged)
    assert _retryable(info.value) is True


def test_non_convergence_failure_keeps_final_semantics():
    network = compile_project(
        project([('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                 ('L1', 'pipe', {'length_m': 10., 'diameter_m': 0.04}),
                 ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
                 ('B3', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
                 ('P1', 'pump', {'speed_ratio': 1.0}),
                 ('B4', 'source', {'pressure_pa': 600000., 'temperature_k': 293.15})],
                [('B1:out0', 'L1:in0'), ('L1:out0', 'B2:out0'),
                 ('B3:out0', 'P1:in0'), ('P1:out0', 'B4:out0')]))
    plan = build_blocks(network)
    target = block_of(network, plan, 'P1')
    with pytest.raises(BlockSolveError) as info:
        solve_hydraulics(network, hooks=frozenset({'blocks'}))
    message = str(info.value)
    assert 'P1' in message and f'{target.id}/' in message
    assert _retryable(info.value) is False
    assert not isinstance(info.value, CompilationError)


def test_easy_block_iteration_count_unchanged_by_other_block():
    standalone_easy = compile_project(pipe_line())
    standalone_easy.project.solver.hydraulic_diagnostics = True
    easy_calls = solve_hydraulics(standalone_easy).counters['residual_calls']

    standalone_hard = compile_project(pump_line())
    standalone_hard.project.solver.hydraulic_diagnostics = True
    hard_calls = solve_hydraulics(standalone_hard).counters['residual_calls']

    network = compile_project(combined())
    network.project.solver.hydraulic_diagnostics = True
    plan = build_blocks(network)
    blocked = solve_hydraulics(network, hooks=frozenset({'blocks'}))
    assert blocked.counters is not None
    records = {record['block']: record for record in blocked.counters['blocks']}
    easy_block = block_of(network, plan, 'L1')
    hard_block = block_of(network, plan, 'P1')
    # 每个块的调用计数等于它单独求解时的计数：另一个块的存在与难度不会让它重复迭代。
    assert records[easy_block.id]['residual_calls'] == easy_calls
    assert records[hard_block.id]['residual_calls'] == hard_calls
    assert blocked.counters['residual_calls'] == sum(record['residual_calls'] for record in records.values())
    # 冷启动下每块恰好一次 least_squares 尝试：难块没有触发其他块重新求解。
    assert blocked.counters['solver_attempts'] == len(records)


def test_block_timings_are_reported_when_diagnostics_on():
    network = compile_project(combined())
    network.project.solver.hydraulic_diagnostics = True
    blocked = solve_hydraulics(network, hooks=frozenset({'blocks'}))
    counters = blocked.counters
    assert counters is not None and counters['block_count'] == 2
    assert len(counters['blocks']) == 2
    assert counters['blocks_wall_s'] > 0.0
    for record in counters['blocks']:
        assert record['wall_s'] > 0.0
        assert record['nfev'] >= 0 and record['residual_calls'] >= record['nfev']
        assert record['pressure_residual'] >= 0.0 and record['mass_residual'] >= 0.0
    fixed = set(network.fixed_pressures)
    expected_unknown = sum(1 for node in range(len(network.node_keys)) if node not in fixed) + len(network.branches)
    assert counters['problem_size'] == expected_unknown


# --------------------------------------------------------------------------- D2：动态一致性与事务


def test_dynamic_heat_loop_blocked_matches_regular():
    regular_model = prototype('heat-loop')
    blocked_model = prototype('heat-loop')
    blocked_model.solver.hydraulic_blocks = True
    assert build_blocks(compile_project(blocked_model)).block_count == 2
    regular = solve_dynamic(compile_project(regular_model), .2, .1)
    blocked = solve_dynamic(compile_project(blocked_model), .2, .1)
    assert_frames_close(blocked, regular, 'heat-loop-dynamic')
    assert blocked[-1].metrics['pressure_residual_pa'] <= blocked_model.solver.pressure_tolerance_pa
    assert blocked[-1].metrics['mass_residual_kg_s'] <= blocked_model.solver.mass_tolerance_kg_s


def test_dynamic_two_tank_state_split_merge_matches_regular():
    regular_model = two_tanks()
    blocked_model = two_tanks(hydraulic_blocks=True)
    assert build_blocks(compile_project(blocked_model)).block_count == 2
    regular = solve_dynamic(compile_project(regular_model), .3, .1)
    blocked = solve_dynamic(compile_project(blocked_model), .3, .1)
    assert_frames_close(blocked, regular, 'two-tanks-dynamic')
    for frame_regular, frame_blocked in zip(regular, blocked):
        for tank in ('TK1', 'TK2'):
            mass = f'{tank}.state.mass_kg'
            assert_close_with_gate(frame_regular.variables[mass], frame_blocked.variables[mass], 'mass_kg', mass)
            assert frame_blocked.variables[mass] > 0.0


def test_dynamic_multiport_module_commits_once_per_frame():
    regular = solve_dynamic(compile_project(multiport_project()), .2, .1)
    blocked = solve_dynamic(compile_project(multiport_project(hydraulic_blocks=True)), .2, .1)
    assert_frames_close(blocked, regular, 'multiport-dynamic')
    expected_commits = len(blocked) - 1
    for frames in (regular, blocked):
        assert frames[-1].variables['M1.state.commit_count'] == expected_commits
    for channel in ('M1.a.mass_flow_kg_s', 'M1.b.mass_flow_kg_s'):
        assert_close_with_gate(regular[-1].variables[channel], blocked[-1].variables[channel],
                               'mass_flow_kg_s', channel)

def test_failed_block_does_not_commit_module_state(monkeypatch):
    network = compile_project(multiport_project())
    runners = _python_runners(network)
    real = partition.solve_hydraulics
    try:
        before = dict(runners['M1'].state)
        before_requests = runners['M1'].request_count

        def flaky(subnetwork, *args, **kwargs):
            result = real(subnetwork, *args, **kwargs)  # evaluate 真的跑过，但没有 commit
            if any(branch.instance_id == 'M1' for branch in subnetwork.branches):
                raise HydraulicNotConverged('合成的不收敛块')
            return result

        monkeypatch.setattr(partition, 'solve_hydraulics', flaky)
        with pytest.raises(HydraulicBlockFailure):
            solve_hydraulics(network, runners=runners, hooks=frozenset({'blocks'}))
        # evaluate 发生过（物理残差试算），但 commit_step 一次都没有：状态与提交计数不变。
        assert runners['M1'].request_count > before_requests
        assert dict(runners['M1'].state) == before
        assert dict(runners['M1'].state).get('commit_count', 0) == before.get('commit_count', 0)
    finally:
        _close_runners(runners)


def closed_valve_plus_two_lines():
    """两条开放独立回路 + 一条关闭阀门支路（关闭支路只贡献流量=0）。"""
    return project(
        [('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
         ('V1', 'valve', {'opening_ratio': 0.0, 'kv_m3_h': 16.}),
         ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
         ('B3', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
         ('L1', 'pipe', {'length_m': 30., 'diameter_m': 0.04}),
         ('B4', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
         ('B5', 'source', {'pressure_pa': 220000., 'temperature_k': 293.15}),
         ('L2', 'pipe', {'length_m': 20., 'diameter_m': 0.05}),
         ('B6', 'source', {'pressure_pa': 130000., 'temperature_k': 293.15})],
        [('B1:out0', 'V1:in0'), ('V1:out0', 'B2:out0'),
         ('B3:out0', 'L1:in0'), ('L1:out0', 'B4:out0'),
         ('B5:out0', 'L2:in0'), ('L2:out0', 'B6:out0')])


def many_lines(count):
    """count 条互不相连的「源-管-阀-源」回路，用于分块规模回归。"""
    instances, connections = [], []
    for index in range(count):
        instances += [(f'B{index}a', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                      (f'P{index}', 'pipe', {'length_m': 30. + index, 'diameter_m': 0.04}),
                      (f'V{index}', 'valve', {'opening_ratio': 0.5 + 0.01 * (index % 40),
                                              'kv_m3_h': 10. + index}),
                      (f'B{index}b', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})]
        connections += [(f'B{index}a:out0', f'P{index}:in0'), (f'P{index}:out0', f'V{index}:in0'),
                        (f'V{index}:out0', f'B{index}b:out0')]
    return project(instances, connections)


def two_chains():
    """两个独立串联链（分块在 C 压缩的外层，用于组合验收）。"""
    return project(
        [('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
         ('L1', 'pipe', {'length_m': 30., 'diameter_m': 0.04}),
         ('L2', 'pipe', {'length_m': 20., 'diameter_m': 0.04}),
         ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
         ('B3', 'source', {'pressure_pa': 230000., 'temperature_k': 293.15}),
         ('V1', 'valve', {'opening_ratio': 0.7, 'kv_m3_h': 16.}),
         ('V2', 'valve', {'opening_ratio': 0.6, 'kv_m3_h': 16.}),
         ('B4', 'source', {'pressure_pa': 130000., 'temperature_k': 293.15})],
        [('B1:out0', 'L1:in0'), ('L1:out0', 'L2:in0'), ('L2:out0', 'B2:out0'),
         ('B3:out0', 'V1:in0'), ('V1:out0', 'V2:in0'), ('V2:out0', 'B4:out0')])


def test_blocks_compose_with_series_compression():
    if importlib.util.find_spec('fn_engine.hydraulic_plan') is None:
        pytest.skip('C（串联压缩）模块尚未落地，D 在块内自动回退 frozenset()')
    network = compile_project(two_chains())
    network.project.solver.series_compression = True
    regular = solve_hydraulics(network, hooks=frozenset({'compression'}))
    both = solve_hydraulics(network, hooks=frozenset({'blocks', 'compression'}))
    assert build_blocks(network).block_count == 2
    assert_hydraulics_close(both, regular, 'blocks+compression')


def test_many_independent_components_split_and_match():
    network = compile_project(many_lines(12))
    plan = build_blocks(network)
    assert plan.block_count == 12 and len(plan.solvable_blocks) == 12
    regular = solve_hydraulics(network)
    blocked = solve_hydraulics(network, hooks=frozenset({'blocks'}))
    assert_hydraulics_close(blocked, regular, 'many-lines')


def test_closed_branch_flow_is_exactly_zero():
    network = compile_project(closed_valve_plus_two_lines())
    plan = build_blocks(network)
    closed_positions = [index for index, branch in enumerate(network.branches) if branch.closed]
    assert len(closed_positions) == 1
    assert plan.block_count == 4 and len(plan.solvable_blocks) == 2
    blocked = solve_hydraulics(network, hooks=frozenset({'blocks'}))
    regular = solve_hydraulics(network)
    for index in closed_positions:
        assert blocked.flows[index] == 0.0
        assert abs(regular.flows[index]) <= 1e-8
    assert_hydraulics_close(blocked, regular, 'closed-branch')


def test_solve_steady_two_blocks_matches_regular():
    regular_network = compile_project(combined())
    blocked_network = compile_project(combined())
    blocked_network.project.solver.hydraulic_blocks = True
    regular = solve_steady(regular_network)
    blocked = solve_steady(blocked_network)
    assert regular.status == blocked.status == 'converged'
    assert blocked.metrics['pressure_residual_pa'] <= blocked_network.project.solver.pressure_tolerance_pa
    assert blocked.metrics['mass_residual_kg_s'] <= blocked_network.project.solver.mass_tolerance_kg_s
    assert '分块求解' in blocked.solve_summary['method_reason']
    assert_frames_close([blocked], [regular], 'steady-two-blocks')


def test_steady_state_two_block_result_passes_residual_gates():
    network = compile_project(combined())
    blocked = solve_hydraulics(network, hooks=frozenset({'blocks'}))
    options = network.project.solver
    assert blocked.pressure_residual <= options.pressure_tolerance_pa
    assert blocked.mass_residual <= options.mass_tolerance_kg_s
    assert np.all(np.isfinite(blocked.pressures)) and np.all(blocked.pressures > 0)
    assert np.all(np.isfinite(blocked.solution))
