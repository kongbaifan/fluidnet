"""C0–C3 验收：受限串联支路压缩与原变量回算。

覆盖：识别（链/锚点/未压缩原因）、1000 串联维数、复合压降（同向/反向/不同口径/泵阀串联）、
关闭阀与参数变化的计划失效、warm start 的 ``solution`` 布局、动态帧一致、node 物性耦合、
环/稀疏请求/不适用回退，以及真实端到端耗时。

运行：
    python -m pytest tests/test_series_compression.py -q
    # 打印 C 证据需要的耗时/维数表格：
    $env:CHECK_VALVE_REPORT="1"; python -m pytest tests/test_series_compression.py -q -s -k report
"""
from __future__ import annotations

import dataclasses
import os
import statistics
import time
from pathlib import Path

import numpy as np
import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompiledBranch, CompiledNetwork, compile_project
from fn_engine.hydraulic_plan import plan_compression, solve_hydraulics_hook
from fn_engine.models import (
    Connection,
    Endpoint,
    FluidConfig,
    ModuleInstance,
    Project,
    SolverOptions,
)
from fn_engine.packages import load_module_package
from fn_engine.solver import (
    PRESSURE_SCALE,
    pipe_drop,
    solve_dynamic,
    solve_hydraulics,
    solve_network,
    solve_steady,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT = bool(os.environ.get('CHECK_VALVE_REPORT'))
PIPE_DEFAULTS = {parameter.id: parameter.default for parameter in catalog_map()['pipe'].parameters}


# --------------------------------------------------------------------------- 网络工厂
def _project(instances, connections, *, compression, **solver):
    catalog = catalog_map()
    used = sorted({instance.module_id for instance in instances} - {'source'})
    modules = [catalog['source']] + [catalog[module_id] for module_id in used]
    options = dict(thermal=False, hydraulic_diagnostics=True, series_compression=compression)
    options.update(solver)
    return Project(id='compress-probe', name='串联压缩验收', modules=modules, instances=instances,
                   connections=connections, solver=SolverOptions(**options))


def _source(instance_id, pressure_pa):
    return ModuleInstance(id=instance_id, module_id='source', name=instance_id,
                          parameters={'pressure_pa': pressure_pa, 'temperature_k': 293.15})


def _link(connection_id, source_instance, source_port, target_instance, target_port):
    return Connection(id=connection_id, source=Endpoint(instance_id=source_instance, port_id=source_port),
                      target=Endpoint(instance_id=target_instance, port_id=target_port))


def chain_project(count=5, *, compression=True, diameters=None, **solver):
    """source(300 kPa) → P0 → … → P(count−1) → source(200 kPa)。"""
    instances = [_source('B1', 300000.0), _source('B2', 200000.0)]
    connections = [_link('c0', 'B1', 'out0', 'P0', 'in0')]
    for index in range(count):
        parameters = {'diameter_m': diameters[index]} if diameters else None
        instances.append(ModuleInstance(id=f'P{index}', module_id='pipe', name=f'管{index}',
                                        parameters=dict(parameters or {})))
    for index in range(count - 1):
        connections.append(_link(f'c{index + 1}', f'P{index}', 'out0', f'P{index + 1}', 'in0'))
    connections.append(_link('c-last', f'P{count - 1}', 'out0', 'B2', 'out0'))
    return _project(instances, connections, compression=compression, **solver)


def reversed_chain_project(*, compression=True):
    """第三个 pipe 反向安装（in0 接下游、out0 接上游），用于验证遍历符号。"""
    instances = [_source('B1', 300000.0), _source('B2', 200000.0),
                 ModuleInstance(id='P0', module_id='pipe', name='p0'),
                 ModuleInstance(id='P1', module_id='pipe', name='p1'),
                 ModuleInstance(id='P2', module_id='pipe', name='p2')]
    connections = [
        _link('r0', 'B1', 'out0', 'P0', 'in0'),
        _link('r1', 'P0', 'out0', 'P1', 'in0'),
        _link('r2', 'P1', 'out0', 'P2', 'out0'),
        _link('r3', 'P2', 'in0', 'B2', 'out0'),
    ]
    return _project(instances, connections, compression=compression)


def pump_valve_project(*, compression=True):
    """source(200 kPa) → 泵 → 阀 → source(250 kPa)；泵提供水位差 + 阀损的扬程。"""
    instances = [_source('B1', 200000.0), _source('B2', 250000.0),
                 ModuleInstance(id='P1', module_id='pump', name='泵', parameters={'speed_ratio': 1.0}),
                 ModuleInstance(id='V1', module_id='valve', name='阀', parameters={'opening_ratio': 0.8})]
    connections = [
        _link('p0', 'B1', 'out0', 'P1', 'in0'),
        _link('p1', 'P1', 'out0', 'V1', 'in0'),
        _link('p2', 'V1', 'out0', 'B2', 'out0'),
    ]
    return _project(instances, connections, compression=compression)


def out_of_curve_pump_project(*, compression=True):
    """source(400 kPa) → 管 → 泵(0.5 转速) → 管 → source(100 kPa)：工作点超出泵曲线。"""
    instances = [_source('B1', 400000.0), _source('B2', 100000.0),
                 ModuleInstance(id='P0', module_id='pipe', name='p0'),
                 ModuleInstance(id='P1', module_id='pump', name='泵', parameters={'speed_ratio': 0.5}),
                 ModuleInstance(id='P2', module_id='pipe', name='p2')]
    connections = [_link('u0', 'B1', 'out0', 'P0', 'in0'),
                   _link('u1', 'P0', 'out0', 'P1', 'in0'),
                   _link('u2', 'P1', 'out0', 'P2', 'in0'),
                   _link('u3', 'P2', 'out0', 'B2', 'out0')]
    return _project(instances, connections, compression=compression)


def mesh_project(*, compression=True, **solver):
    """三条链在一个度数 3 的未知压锚点 J1 汇合（P0–P1 / P2–P3 / P4–P5）。"""
    instances = [_source('B1', 300000.0), _source('B2', 200000.0), _source('B3', 210000.0),
                 ModuleInstance(id='J1', module_id='junction', name='J1')]
    instances += [ModuleInstance(id=f'P{index}', module_id='pipe', name=f'p{index}') for index in range(6)]
    connections = [
        _link('m0', 'B1', 'out0', 'P0', 'in0'),
        _link('m1', 'P0', 'out0', 'P1', 'in0'),
        _link('m2', 'P1', 'out0', 'J1', 'in0'),
        _link('m3', 'J1', 'out0', 'P2', 'in0'),
        _link('m4', 'P2', 'out0', 'P3', 'in0'),
        _link('m5', 'P3', 'out0', 'B2', 'out0'),
        _link('m6', 'J1', 'out1', 'P4', 'in0'),
        _link('m7', 'P4', 'out0', 'P5', 'in0'),
        _link('m8', 'P5', 'out0', 'B3', 'out0'),
    ]
    return _project(instances, connections, compression=compression, **solver)


def closed_valve_project(*, compression=True):
    """B1 → P0 → P1 → 关闭阀 → P2 → P3 → B2：链在关闭阀处断开。"""
    instances = [_source('B1', 300000.0), _source('B2', 200000.0)]
    instances += [ModuleInstance(id=f'P{index}', module_id='pipe', name=f'p{index}') for index in range(4)]
    instances.append(ModuleInstance(id='V1', module_id='valve', name='关闭阀', parameters={'opening_ratio': 0.0}))
    connections = [
        _link('v0', 'B1', 'out0', 'P0', 'in0'),
        _link('v1', 'P0', 'out0', 'P1', 'in0'),
        _link('v2', 'P1', 'out0', 'V1', 'in0'),
        _link('v3', 'V1', 'out0', 'P2', 'in0'),
        _link('v4', 'P2', 'out0', 'P3', 'in0'),
        _link('v5', 'P3', 'out0', 'B2', 'out0'),
    ]
    return _project(instances, connections, compression=compression)


def ring_project(*, compression=True):
    """纯环：source → J1 → P0 → P1 → P2 → J1；J1 是唯一压力参考锚点。"""
    instances = [_source('B1', 250000.0), ModuleInstance(id='J1', module_id='junction', name='J1')]
    instances += [ModuleInstance(id=f'P{index}', module_id='pipe', name=f'p{index}') for index in range(3)]
    connections = [
        _link('g0', 'B1', 'out0', 'J1', 'in0'),
        _link('g1', 'J1', 'out0', 'P0', 'in0'),
        _link('g2', 'P0', 'out0', 'P1', 'in0'),
        _link('g3', 'P1', 'out0', 'P2', 'in0'),
        _link('g4', 'P2', 'out0', 'J1', 'out1'),
    ]
    return _project(instances, connections, compression=compression)


def tank_project(*, compression=True):
    """source(300 kPa) → P0 → P1 → 开式水箱；水箱在稳态是固定压力锚点。"""
    instances = [_source('B1', 300000.0), ModuleInstance(id='T1', module_id='tank', name='水箱'),
                 ModuleInstance(id='P0', module_id='pipe', name='p0'),
                 ModuleInstance(id='P1', module_id='pipe', name='p1')]
    connections = [_link('t0', 'B1', 'out0', 'P0', 'in0'),
                   _link('t1', 'P0', 'out0', 'P1', 'in0'),
                   _link('t2', 'P1', 'out0', 'T1', 'in0')]
    return _project(instances, connections, compression=compression)


def python_chain_project(*, compression=True):
    """管道 + Python 止回阀：C 第一版不压缩 Python 通路，应回退常规路径。"""
    valve = load_module_package(ROOT / 'modules' / 'check_valve_v2')
    catalog = catalog_map()
    instances = [_source('B1', 300000.0), _source('B2', 200000.0),
                 ModuleInstance(id='P0', module_id='pipe', name='p0'),
                 ModuleInstance(id='P1', module_id='pipe', name='p1'),
                 ModuleInstance(id='V1', module_id='check_valve', name='止回阀',
                                parameters={'p_crack_pa': 5000.0})]
    connections = [_link('q0', 'B1', 'out0', 'P0', 'in0'),
                   _link('q1', 'P0', 'out0', 'P1', 'in0'),
                   _link('q2', 'P1', 'out0', 'V1', 'in0'),
                   _link('q3', 'V1', 'out0', 'B2', 'out0')]
    options = SolverOptions(thermal=False, hydraulic_diagnostics=True, series_compression=compression)
    return Project(id='python-chain', name='python chain', modules=[catalog['source'], catalog['pipe'], valve],
                   instances=instances, connections=connections, solver=options)


def synthetic_chain(count=1000, *, compression=True):
    """绕过 Project 实例上限（1000）的纯 count 支路串联网络，用于维数/耗时实测。"""
    parameters = {f'P{index}': dict(PIPE_DEFAULTS) for index in range(count)}
    branches = [CompiledBranch(f'P{index}', 'ch0', 'pipe', 'in0', 'out0', index, index + 1)
                for index in range(count)]
    node_keys = [f'P{index}:in0' for index in range(count)] + [f'P{count - 1}:out0']
    project = Project(id='synthetic-chain', name='synthetic', fluid=FluidConfig(),
                      solver=SolverOptions(thermal=False, hydraulic_diagnostics=True,
                                           series_compression=compression))
    return CompiledNetwork(project=project, modules={}, instances={}, parameters=parameters,
                           port_nodes={}, node_keys=node_keys, branches=branches,
                           fixed_pressures={0: 300000.0, count: 200000.0}, diagnostics=[])


# --------------------------------------------------------------------------- 工具
def branch_index(network, instance_id):
    return next(index for index, branch in enumerate(network.branches)
                if branch.instance_id == instance_id)


def hydraulic(network):
    return solve_network(network, {})


def assert_hydraulic_close(off, on):
    """3.1 差值门：流量 1e-8 + 1e-6|q_ref|；压力 1 Pa + 1e-8|p_ref|。"""
    for node in range(len(off.pressures)):
        reference = float(off.pressures[node])
        assert abs(float(on.pressures[node]) - reference) <= 1.0 + 1e-8 * abs(reference), \
            f'节点 {node} 压力不一致：{reference} vs {on.pressures[node]}'
    for index in range(len(off.flows)):
        reference = float(off.flows[index])
        assert abs(float(on.flows[index]) - reference) <= 1e-8 + 1e-6 * abs(reference), \
            f'支路 {index} 流量不一致：{reference} vs {on.flows[index]}'


def assert_close(off, on):
    assert_hydraulic_close(off.hydraulic, on.hydraulic)


def compare(build):
    off = hydraulic(compile_project(build(compression=False)))
    on = hydraulic(compile_project(build(compression=True)))
    assert_close(off, on)
    assert on.hydraulic.pressure_residual <= 1.0 and on.hydraulic.mass_residual <= 1e-8
    return off, on


def median_seconds(call, repeats):
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = call()
        samples.append(time.perf_counter() - started)
    return statistics.median(samples), result


# --------------------------------------------------------------------------- C0：识别
def test_plan_identifies_series_chain_and_sizes():
    network = compile_project(chain_project(5, compression=True))
    plan = plan_compression(network)
    assert plan.chain_count == 1
    chain = plan.chains[0]
    assert [member.branch for member in chain.members] == list(range(5))
    assert all(member.sign == 1 for member in chain.members)
    assert plan.anchors == (0, 5)
    assert plan.unknown_anchors == ()
    assert plan.standalone == ()
    assert plan.excluded == ()
    assert plan.original_size == (6 - 2) + 5
    assert plan.reduced_size == 1
    assert plan.saved_unknowns == (plan.original_size - 1)
    exported = plan.as_dict()
    assert exported['chains'][0]['members'] == [(index, 1) for index in range(5)]
    assert exported['original_size'] == plan.original_size


def test_plan_keeps_degree_three_anchor_and_splits_chains():
    network = compile_project(mesh_project(compression=True))
    plan = plan_compression(network)
    assert plan.chain_count == 3
    assert {len(chain.members) for chain in plan.chains} == {2}
    assert len(plan.unknown_anchors) == 1
    joint = plan.unknown_anchors[0]
    assert network.node_keys[joint] == 'P1:out0'  # J1 与 P1:out0 合并成同一节点
    assert plan.reduced_size == 4
    assert plan.excluded == ()


def test_plan_excludes_closed_branch_and_unsupported_model():
    network = compile_project(closed_valve_project(compression=True))
    plan = plan_compression(network)
    valve = branch_index(network, 'V1')
    reasons = dict(plan.excluded)
    assert valve in reasons and '关闭' in reasons[valve]
    assert valve in plan.standalone
    assert plan.chain_count == 2
    synthetic = synthetic_chain(4, compression=True)
    synthetic.branches[2] = dataclasses.replace(synthetic.branches[2], solver_model='heat_exchanger')
    plan = plan_compression(synthetic)
    reasons = dict(plan.excluded)
    assert reasons.get(2, '').startswith('未支持模型')
    assert plan.chain_count == 1 and len(plan.chains[0].members) == 2


def test_ring_with_reference_becomes_single_loop_chain():
    network = compile_project(ring_project(compression=True))
    plan = plan_compression(network)
    assert plan.chain_count == 1 and plan.chains[0].loop
    assert plan.chains[0].start_node == plan.chains[0].end_node
    assert len(plan.chains[0].members) == 3
    assert plan.reduced_size == 1
    compare(ring_project)


# --------------------------------------------------------------------------- C1/C2：维数、曲线、布局
def test_thousand_series_reduces_to_one_unknown():
    network = synthetic_chain(1000, compression=True)
    plan = plan_compression(network)
    assert plan.chain_count == 1 and len(plan.chains[0].members) == 1000
    assert plan.original_size == 1999
    assert plan.reduced_size == 1
    result = solve_hydraulics(network, {})
    assert result.matrix_size == 1
    assert result.counters['original_problem_size'] == 1999
    assert result.counters['series_compression'] is True
    assert result.iterations >= 1 and result.pressure_residual <= 1.0
    q = float(result.flows[0])
    assert pipe_drop(PIPE_DEFAULTS, q, 998.2752462838249, 1.0015503944484675e-3) == pytest.approx(100.0, rel=2e-6)
    for index in (1, 500, 999):
        expected = 300000.0 - index * 100.0
        assert float(result.pressures[index]) == pytest.approx(expected, abs=1e-3)
    assert float(result.pressures[1000]) == pytest.approx(200000.0)


def test_forward_and_reverse_chain_match_uncompressed():
    compare(chain_project)
    _, on = compare(reversed_chain_project)
    assert on.hydraulic.counters['compression_chains'] == 1
    plan = plan_compression(compile_project(reversed_chain_project(compression=True)))
    signs = [member.sign for member in plan.chains[0].members]
    assert -1 in signs and signs.count(1) == 2


def test_varied_diameters_and_pump_valve_series_match():
    compare(lambda *, compression: chain_project(6, compression=compression,
                                                 diameters=[0.05, 0.04, 0.032, 0.04, 0.05, 0.032]))
    compare(pump_valve_project)
    network = compile_project(pump_valve_project(compression=True))
    plan = plan_compression(network)
    assert plan.chain_count == 1
    assert any(network.branches[member.branch].solver_model == 'pump_curve'
               for member in plan.chains[0].members)


def test_mesh_partial_compression_matches():
    off, on = compare(mesh_project)
    assert on.hydraulic.matrix_size == 4
    assert off.hydraulic.matrix_size > on.hydraulic.matrix_size


def test_closed_valve_and_open_change_are_consistent():
    compare(closed_valve_project)
    compare(tank_project)
    network = compile_project(chain_project(6, compression=True))
    result = hydraulic(network)
    assert result.hydraulic.counters['compression_chains'] == 1
    changed = branch_index(network, 'P3')
    network.branches[changed] = dataclasses.replace(network.branches[changed], closed=True)
    result = hydraulic(network)
    assert result.hydraulic.counters['compression_chains'] == 2
    assert changed in dict(plan_compression(network).excluded)


def test_solution_layout_is_original_network_and_warm_start_reuses_it():
    network = compile_project(chain_project(6, compression=True))
    first = hydraulic(network)
    off_network = compile_project(chain_project(6, compression=False))
    off = hydraulic(off_network)
    unknown = [node for node in range(len(network.node_keys)) if node not in network.fixed_pressures]
    solution = np.asarray(first.hydraulic.solution)
    assert solution.shape == (off.hydraulic.solution.shape[0],)
    assert np.allclose(solution[:len(unknown)] * PRESSURE_SCALE, first.hydraulic.pressures[unknown],
                       rtol=0, atol=1e-9)
    assert np.allclose(solution[len(unknown):], first.hydraulic.flows, rtol=0, atol=1e-15)
    warm_off = solve_hydraulics(off_network, {}, initial=solution)
    assert_hydraulic_close(off.hydraulic, warm_off)
    warm_on = solve_hydraulics(network, {}, initial=solution)
    assert warm_on.iterations <= first.hydraulic.iterations
    assert_hydraulic_close(off.hydraulic, warm_on)


def test_python_network_falls_back_to_normal_path():
    network = compile_project(python_chain_project(compression=True))
    assert solve_hydraulics_hook(network, {'V1': object()}, 0.0) is None
    assert solve_hydraulics_hook(network, {}, 0.0, storage_step=(0.1, {})) is None
    assert solve_hydraulics_hook(network, {}, 0.0, port_base={}) is None
    assert solve_hydraulics_hook(dataclasses.replace(synthetic_chain(4), mixed=True), {}, 0.0) is None
    assert solve_hydraulics_hook(compile_project(chain_project(1, compression=True)), {}, 0.0) is None


def test_no_compression_request_returns_none():
    network = synthetic_chain(10, compression=False)
    assert solve_hydraulics_hook(network, {}, 0.0) is None


# --------------------------------------------------------------------------- C2：字段与请求
def test_result_fields_and_method_reason_trace_compression():
    network = compile_project(mesh_project(compression=True))
    result = hydraulic(network).hydraulic
    assert result.requested_method == 'dense'
    assert result.effective_method == 'dense'
    assert '压缩' in result.method_reason and '条链' in result.method_reason
    assert result.jacobian_mode == 'analytic' and '复合压降' in result.jacobian_reason
    assert result.matrix_size == 4 and result.matrix_nnz > 0
    assert result.branch_density.shape == (len(network.branches),)
    assert result.branch_viscosity.shape == (len(network.branches),)
    assert result.relations == {} and result.storage_rates == {}
    assert result.module_variables == {} and result.module_diagnostics == []
    counters = result.counters
    for key in ('residual_calls', 'nfev', 'njev', 'problem_size', 'original_problem_size',
                'reduced_problem_size', 'compression_chains', 'compressed_branches', 'unknowns_saved'):
        assert key in counters, key
    assert counters['unknowns_saved'] == counters['original_problem_size'] - counters['reduced_problem_size']


def test_sparse_request_is_honored_on_reduced_system():
    on = hydraulic(compile_project(mesh_project(compression=True, hydraulic_method='sparse')))
    off = hydraulic(compile_project(mesh_project(compression=False, hydraulic_method='sparse')))
    assert on.hydraulic.requested_method == 'sparse'
    assert on.hydraulic.effective_method == 'sparse'
    assert_close(off, on)


def test_out_of_curve_pump_still_raises():
    """泵曲线外工况必须报原有错误，压缩不得静默外推。"""
    messages = []
    for compression in (False, True):
        network = compile_project(out_of_curve_pump_project(compression=compression))
        with pytest.raises(ValueError, match='超出泵曲线范围') as caught:
            hydraulic(network)
        messages.append(str(caught.value))
    assert messages[0] == messages[1]


# --------------------------------------------------------------------------- C3：动态与 node 耦合
def test_dynamic_frames_match_with_and_without_compression():
    duration_s, dt_s = 0.6, 0.1
    off = solve_dynamic(compile_project(chain_project(6, compression=False)), duration_s, dt_s)
    on = solve_dynamic(compile_project(chain_project(6, compression=True)), duration_s, dt_s)
    assert len(off) == len(on)
    keys = [key for key in on[0].variables if key.endswith(('mass_flow_kg_s', 'pressure_pa'))]
    for frame_off, frame_on in zip(off, on):
        assert frame_on.status == 'converged'
        for key in keys:
            left, right = frame_off.variables.get(key), frame_on.variables.get(key)
            if left is None or right is None:
                continue
            tolerance = (1.0 + 1e-8 * abs(left)) if key.endswith('pressure_pa') else (1e-8 + 1e-6 * abs(left))
            assert abs(right - left) <= tolerance, (key, left, right)


def test_node_property_coupling_matches_and_keeps_branch_properties():
    off = hydraulic(compile_project(chain_project(5, compression=False, thermal=True,
                                                 property_coupling='node')))
    on = hydraulic(compile_project(chain_project(5, compression=True, thermal=True,
                                                property_coupling='node')))
    assert_close(off, on)
    # node 耦合逐原支路回填物性：与未压缩结果的每个原支路值一致（只差耦合迭代末位）。
    assert len(on.hydraulic.branch_density) == len(off.hydraulic.branch_density)
    assert np.allclose(on.hydraulic.branch_density, off.hydraulic.branch_density, rtol=1e-9, atol=0.0)
    assert np.allclose(on.hydraulic.branch_viscosity, off.hydraulic.branch_viscosity, rtol=1e-6, atol=0.0)


# --------------------------------------------------------------------------- 证据
def test_report_series_compression_timing():
    """打印 500 串联 A/B、1000 串联压缩侧与真实项目端到端（编译与 solve_steady 分开计时）。"""
    rows = []
    for count in (500,):
        off_time, off = median_seconds(lambda: solve_hydraulics(synthetic_chain(count, compression=False), {}), 1)
        on_time, on = median_seconds(lambda: solve_hydraulics(synthetic_chain(count, compression=True), {}), 3)
        assert_hydraulic_close(off, on)
        rows.append((count, off.matrix_size, on.matrix_size, off_time, on_time,
                     off.counters['nfev'], on.counters['nfev'],
                     off.counters['residual_calls'], on.counters['residual_calls']))
    thousand_time, thousand = median_seconds(
        lambda: solve_hydraulics(synthetic_chain(1000, compression=True), {}), 3)
    assert thousand.matrix_size == 1
    thousand_steady_time, thousand_frame = median_seconds(
        lambda: solve_steady(synthetic_chain(1000, compression=True)), 3)
    assert thousand_frame.status == 'converged'
    project_rows = []
    for count in (20, 200):
        for compression in (False, True):
            project = chain_project(count, compression=compression)
            compile_time, network = median_seconds(lambda p=project: compile_project(p), 3)
            solve_time, frame = median_seconds(lambda n=network: solve_steady(n), 3)
            project_rows.append((count, compression, compile_time, solve_time, frame))
    assert project_rows[-1][4].status == 'converged'
    if REPORT:
        print('')
        print('== C 串联压缩 A/B（solve_hydraulics，未压缩 -> 压缩）==')
        for (count, size_off, size_on, off_time, on_time, nfev_off, nfev_on,
             calls_off, calls_on) in rows:
            print(f'  {count:5d} 支路：未知量 {size_off:5d} -> {size_on:1d}  '
                  f'{off_time * 1000:9.1f} ms -> {on_time * 1000:7.2f} ms（{off_time / on_time:6.1f}x）'
                  f'  nfev {nfev_off}->{nfev_on}  res {calls_off}->{calls_on}')
        print(f'  1000 支路压缩侧：未知量 1，{thousand_time * 1000:.2f} ms（nfev={thousand.iterations}，'
              f'res={thousand.counters["residual_calls"]}）；solve_steady 端到端 '
              f'{thousand_steady_time * 1000:.1f} ms（含帧构建）')
        print('== 真实项目端到端（compile_project / solve_steady 分开计时）==')
        for count, compression, compile_time, solve_time, frame in project_rows:
            print(f'  {count:4d} 串联 compression={compression!s:5} '
                  f'compile {compile_time * 1000:6.1f} ms  solve {solve_time * 1000:7.2f} ms '
                  f'q={frame.variables["P0.ch0.mass_flow_kg_s"]:.12g}')
