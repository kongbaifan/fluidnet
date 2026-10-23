"""check_valve V0–V2 验收：独立 Δp–q 参考 + 真实求解器 + 版本发布/回滚。

覆盖：
- V0：冻结语义的纯函数（开启压差、精确反向截止、互补残差、迟滞状态机、方案 (a) 有界泄漏上界）；
- V1：v2 模块包契约、evaluate 幂等与精确零开度、Δp–q 曲线（正向/反向/阈值两侧）、冷/热启动、
  泵旁路、并联、方案 (a)/(b) 对照、迭代次数与 RPC；
- V2：动态扫压差（步长变化不产生虚假反向质量）、状态只在接受步提交、版本列表/升级预览/回滚、
  旧 v1 快照保持旧行为、Python 关闭产生无参考段的剩余限制。

运行：
    python -m pytest tests/test_check_valve_numerics.py -q
    # 打印实测曲线/迭代/RPC（docs/numerics/results/V1.md 的数字来源）：
    $env:CHECK_VALVE_REPORT="1"; python -m pytest tests/test_check_valve_numerics.py -q -s -k report
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from fn_engine.bench import run_module_test
from fn_engine.catalog import catalog_map
from fn_engine.check_valve import (
    DEFAULT_HYSTERESIS_PA,
    DEFAULT_OPENING_MAX,
    DEFAULT_P_CRACK_PA,
    REVERSE_LEAK_UPPER_BOUND_KG_S,
    ValveParameters,
    complementarity_residual,
    is_open,
    next_open_state,
    opening_slack_pa,
    reference_mass_flow_kg_s,
    reference_pressure_drop_pa,
    reference_volume_flow_m3_h,
    required_opening,
    smooth_diode_mass_flow_kg_s,
    smooth_reverse_leak_upper_bound,
    smooth_threshold_flow_kg_s,
    valve_mass_flow_kg_s,
)
from fn_engine.compiler import compile_project
from fn_engine.models import (
    ChannelState,
    CommitStepRequest,
    Connection,
    Endpoint,
    EvaluateRequest,
    ModuleDefinition,
    ModuleInstance,
    ModuleTestRequest,
    PortState,
    Project,
    SolverOptions,
)
from fn_engine.packages import ModuleStore, load_module_package
from fn_engine.projects import upgrade_project
from fn_engine.runtime import InProcessModuleRunner, RuntimeErrorBase
from fn_engine.solver import HydraulicNotConverged, solve_dynamic, solve_network, solve_steady

ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT / 'modules'
V1_DIR = MODULE_ROOT / 'check_valve'
V2_DIR = MODULE_ROOT / 'check_valve_v2'

#: v1 包（version=1）的源码哈希：V2 发布不允许改写旧版本。
V1_CONTENT_HASH = 'bf0afdbc960503b47e60f5231e41a23109591d3ead2e20a8b6fcec1d06ae8abc'

KV = 50.0
P_CRACK = 5000.0
REPORT = bool(os.environ.get('CHECK_VALVE_REPORT'))


# --------------------------------------------------------------------------- 夹具与工具
def v1_definition():
    return load_module_package(V1_DIR)


def v2_definition():
    return load_module_package(V2_DIR)


def series_project(definition, parameters, *, delta_p, p0=250000.0, extra_modules=()):
    """source(B1) → D1(target) → source(B2) 的最小网络；Δp = 入口 − 出口。"""
    catalog = catalog_map()
    inlet, outlet = p0 + delta_p / 2, p0 - delta_p / 2
    return Project(
        id=f'cv-{definition.id}', name='check valve 验收', modules=[catalog['source'], *extra_modules, definition],
        solver=SolverOptions(thermal=False, hydraulic_diagnostics=True),
        instances=[
            ModuleInstance(id='B1', module_id='source', name='入口边界',
                           parameters={'pressure_pa': inlet, 'temperature_k': 293.15}),
            ModuleInstance(id='B2', module_id='source', name='出口边界',
                           parameters={'pressure_pa': outlet, 'temperature_k': 293.15}),
            ModuleInstance(id='D1', module_id=definition.id, name='止回阀', parameters=dict(parameters)),
        ],
        connections=[
            Connection(id='e1', source=Endpoint(instance_id='B1', port_id='out0'),
                       target=Endpoint(instance_id='D1', port_id='in0')),
            Connection(id='e2', source=Endpoint(instance_id='D1', port_id='out0'),
                       target=Endpoint(instance_id='B2', port_id='out0')),
        ],
    )


def branch_index(network, instance_id='D1'):
    return next(index for index, branch in enumerate(network.branches) if branch.instance_id == instance_id)


def measured(network, result, instance_id='D1'):
    counters = result.hydraulic.counters or {}
    index = branch_index(network, instance_id)
    return {
        'q': float(result.hydraulic.flows[index]),
        'opening': float(result.hydraulic.module_variables.get(f'{instance_id}.opening_ratio', float('nan'))),
        'nfev': int(result.hydraulic.iterations),
        'residual_calls': counters.get('residual_calls'),
        'rpc_batches': counters.get('rpc_batches'),
        'rpc_instances': counters.get('rpc_instances'),
        'pressure_residual': result.hydraulic.pressure_residual,
        'mass_residual': result.hydraulic.mass_residual,
        'density': float(result.hydraulic.density),
    }


def solve_case(definition, parameters, delta_p, *, runner=None, warm=None):
    network = compile_project(series_project(definition, parameters, delta_p=delta_p))
    if runner is None:
        runner = InProcessModuleRunner(definition, network.parameters['D1'], network.project.fluid)
        runner.initialize()
    result = solve_network(network, {'D1': runner}, warm=warm)
    return network, result


def measured_case(definition, parameters, delta_p):
    network, result = solve_case(definition, parameters, delta_p)
    return measured(network, result)


def report_table(title, rows):
    if not REPORT:
        return
    print(f'\n== {title} ==')
    print(f"{'dp_pa':>12} {'q_kg_s':>16} {'q_ref':>16} {'opening':>12} {'nfev':>5} {'res':>5} {'rpc_b':>6} {'rpc_i':>6}")
    for row in rows:
        print(f"{row['delta_p']:>12.4f} {row['q']:>16.9g} {row.get('q_ref', float('nan')):>16.9g} "
              f"{row['opening']:>12.6g} {row['nfev']:>5} {row['residual_calls']:>5} "
              f"{row['rpc_batches']:>6} {row['rpc_instances']:>6}")


# --------------------------------------------------------------------------- V0：独立参考
def test_v0_frozen_defaults():
    assert DEFAULT_P_CRACK_PA == 0.0
    assert DEFAULT_OPENING_MAX == 1.0
    assert DEFAULT_HYSTERESIS_PA == 0.0
    # 冻结选择是“反向精确零流”，不是“有界泄漏”。
    assert REVERSE_LEAK_UPPER_BOUND_KG_S == 0.0


def test_v0_reference_curve_is_the_cracked_valve_law():
    params = ValveParameters(kv_m3_h=KV, p_crack_pa=P_CRACK)
    scale = 100000.0 * (params.density_kg_m3 / 1000.0)
    for delta_p in (5000.5, 5010.0, 5500.0, 10000.0, 50000.0, 200000.0):
        opening = required_opening(delta_p, P_CRACK, 1.0)
        assert 0.0 < opening <= 1.0
        assert opening == pytest.approx(math.sqrt(1.0 - P_CRACK / delta_p), rel=1e-12)
        volume = reference_volume_flow_m3_h(params, delta_p)
        assert volume == pytest.approx(KV * math.sqrt((delta_p - P_CRACK) / scale), rel=1e-12)
        mass = reference_mass_flow_kg_s(params, delta_p)
        assert mass == pytest.approx(volume * params.density_kg_m3 / 3600.0, rel=1e-12)
        # 模块实际使用的阀门律（opening 代入 Kv_eff）与参考曲线一致。
        valve = valve_mass_flow_kg_s(KV, opening, delta_p, params.density_kg_m3)
        assert valve == pytest.approx(mass, rel=1e-12)
        # 解析反解回压差。
        assert reference_pressure_drop_pa(params, mass) == pytest.approx(delta_p, rel=1e-12)


def test_v0_reference_curve_is_exactly_zero_at_and_below_crack():
    params = ValveParameters(kv_m3_h=KV, p_crack_pa=P_CRACK)
    for delta_p in (P_CRACK, P_CRACK - 1e-6, P_CRACK - 1.0, 1000.0, 0.0, -1e-9, -1.0, -1e6):
        assert reference_mass_flow_kg_s(params, delta_p) == 0.0
        assert required_opening(delta_p, P_CRACK, 1.0) == 0.0
    # 默认 p_crack=0 时退化为 v1 的正向阀门律：q = Kv·sqrt(Δp/(1e5·ρ/1000))。
    default = ValveParameters(kv_m3_h=KV)
    expected = KV * math.sqrt(10000.0 / (100000.0 * (default.density_kg_m3 / 1000.0)))
    assert reference_volume_flow_m3_h(default, 10000.0) == pytest.approx(expected, rel=1e-12)
    assert reference_mass_flow_kg_s(default, -10000.0) == 0.0


def test_v0_complementarity_residual_and_slack():
    for delta_p, flow in ((10000.0, 3.0), (P_CRACK + 1.0, 1e-4)):
        residual = complementarity_residual(delta_p, flow, P_CRACK)
        assert residual['opening_slack_pa'] < 0.0 and residual['mass_flow_kg_s'] > 0.0
        assert residual['product'] == pytest.approx(residual['opening_slack_pa'] * residual['mass_flow_kg_s'])
        assert residual['open_consistent'] is True
        assert opening_slack_pa(delta_p, P_CRACK) < 0.0
    for delta_p in (-1000.0, 0.0, P_CRACK):
        residual = complementarity_residual(delta_p, 0.0, P_CRACK)
        assert residual['opening_slack_pa'] >= 0.0 and residual['mass_flow_kg_s'] == 0.0
        assert residual['product'] == 0.0 and residual['closed_consistent'] is True


def test_v0_hysteresis_state_machine_pure_function():
    # h = 0：与 accepted state 无关，且 Δp ≤ 0 恒关。
    for delta_p in (-1e6, -1.0, 0.0, P_CRACK):
        assert not is_open(delta_p, P_CRACK, 0.0, was_open=False)
        assert not is_open(delta_p, P_CRACK, 0.0, was_open=True)
    assert is_open(P_CRACK + 1.0, P_CRACK, 0.0)
    assert is_open(P_CRACK + 1.0, P_CRACK, 0.0, was_open=True)
    # h > 0：关闭→开启要用 p_crack+h，开启→关闭用 max(0,p_crack−h)，反向始终关。
    band = 500.0
    assert not is_open(P_CRACK + 100.0, P_CRACK, band, was_open=False)
    assert is_open(P_CRACK + 600.0, P_CRACK, band, was_open=False)
    assert is_open(P_CRACK - 100.0, P_CRACK, band, was_open=True)
    assert not is_open(max(0.0, P_CRACK - band) - 1.0, P_CRACK, band, was_open=True)
    assert not is_open(-1.0, P_CRACK, band, was_open=True)
    assert next_open_state(True, P_CRACK - 100.0, P_CRACK, band) is True
    assert next_open_state(True, -1.0, P_CRACK, band) is False


def test_v0_smooth_variant_has_bounded_but_nonzero_leak():
    params = ValveParameters(kv_m3_h=KV, p_crack_pa=P_CRACK)
    for width in (100.0, 500.0, 2000.0):
        leak, at = smooth_reverse_leak_upper_bound(params, width)
        assert leak >= 0.0 and math.isfinite(leak)
        if width >= 2000.0:
            assert leak > 0.0 and at < 0.0
    # 光滑方案在“开启压差”处已经半开，物理上不存在真正的开启压差。
    assert smooth_threshold_flow_kg_s(params, 500.0) > 1.0
    assert smooth_diode_mass_flow_kg_s(params, 500.0, P_CRACK) > 1.0


# --------------------------------------------------------------------------- 模块契约与 evaluate
def test_v1_package_is_unchanged():
    definition = v1_definition()
    assert definition.version == 1
    assert definition.content_hash == V1_CONTENT_HASH
    assert {parameter.id for parameter in definition.parameters} == {
        'kv_m3_h', 'opening_ratio', 'cracking_pressure_pa', 'density_kg_m3'}
    assert {variable.id for variable in definition.variables} == {
        'opening_ratio', 'direction', 'state.closed_steps', 'state.throughput_kg'}


def test_v2_package_contract():
    definition = v2_definition()
    assert definition.id == 'check_valve'
    assert definition.version == 2
    assert definition.runtime == 'python'
    assert definition.entrypoint == 'module:Module'
    assert len(definition.content_hash) == 64 and len(definition.definition_hash) == 64
    assert [(channel.id, channel.relation, channel.solver_model, channel.enabled) for channel in definition.channels] == [
        ('main', 'resistance', 'valve', True)]
    parameters = {parameter.id: parameter for parameter in definition.parameters}
    assert parameters['p_crack_pa'].default == 0.0
    assert parameters['hysteresis_pa'].default == 0.0
    assert parameters['opening_ratio'].default == 1.0
    # v1 遗留参数保留（升级兼容），但 v2 不参与计算。
    assert parameters['cracking_pressure_pa'].default == 0.0
    assert {variable.id for variable in definition.variables} >= {
        'opening_ratio', 'is_open', 'direction', 'state.is_open', 'state.closed_steps', 'state.open_steps',
        'state.throughput_kg', 'state.reverse_throughput_kg'}


def evaluate_request(delta_p, *, state=None, p0=250000.0):
    ports = {
        'in0': PortState(pressure_pa=p0 + delta_p / 2, temperature_k=293.15, density_kg_m3=998.275),
        'out0': PortState(pressure_pa=p0 - delta_p / 2, temperature_k=293.15, density_kg_m3=998.275),
    }
    return EvaluateRequest(run_id='cv-eval', instance_id='D1', iteration_id=0, time_s=0.0,
                           trial_ports=ports, readonly_state=dict(state or {}))


def make_runner(definition, parameters):
    from fn_engine.models import FluidConfig
    runner = InProcessModuleRunner(definition, dict(parameters), FluidConfig())
    runner.initialize()
    return runner


def test_evaluate_returns_exact_zero_and_is_idempotent():
    definition = v2_definition()
    runner = make_runner(definition, {'kv_m3_h': KV, 'p_crack_pa': P_CRACK, 'opening_ratio': 1.0})
    before = dict(runner.state)
    for delta_p in (-20000.0, -1.0, 0.0, P_CRACK):
        request = evaluate_request(delta_p, state=before)
        first, second = runner.evaluate(request), runner.evaluate(request)
        assert first.model_dump() == second.model_dump()
        relation = first.relations[0]
        assert relation.kind == 'valve'
        assert relation.parameters['opening_ratio'] == 0.0  # 精确 0，不是 1e-12
        assert relation.parameters['kv_m3_h'] == KV
        assert first.variables['opening_ratio'] == 0.0
        assert first.variables['is_open'] == 0.0
    assert runner.state == before  # evaluate 不污染已提交状态
    # 正向：opening = sqrt(1 − p_crack/Δp)，与独立参考一致。
    for delta_p in (P_CRACK + 1.0, 10000.0, 200000.0):
        relation = runner.evaluate(evaluate_request(delta_p, state=before)).relations[0]
        assert relation.parameters['opening_ratio'] == pytest.approx(
            required_opening(delta_p, P_CRACK, 1.0), rel=1e-12)
        assert 0.0 < relation.parameters['opening_ratio'] <= 1.0


def test_evaluate_ignores_legacy_parameter_and_reports_it():
    definition = v2_definition()
    runner = make_runner(definition, {'kv_m3_h': KV, 'p_crack_pa': 0.0, 'cracking_pressure_pa': 5000.0})
    response = runner.evaluate(evaluate_request(-1000.0))
    assert response.relations[0].parameters['opening_ratio'] == 0.0
    codes = [diagnostic.code for diagnostic in response.diagnostics]
    assert 'CHECK_VALVE_LEGACY_PARAMETER' in codes
    assert all(diagnostic.severity != 'error' for diagnostic in response.diagnostics)


# --------------------------------------------------------------------------- V1：真实网络 Δp–q
def test_v1_forward_curve_matches_independent_reference():
    definition = v2_definition()
    parameters = {'kv_m3_h': KV, 'p_crack_pa': P_CRACK}
    probes = [5000.5, 5010.0, 5500.0, 10000.0, 50000.0, 200000.0]
    rows = []
    density = None
    for delta_p in probes:
        network, result = solve_case(definition, parameters, delta_p)
        row = measured(network, result)
        density = density or row['density']
        reference = reference_mass_flow_kg_s(ValveParameters(kv_m3_h=KV, p_crack_pa=P_CRACK, density_kg_m3=density),
                                             delta_p)
        row.update(delta_p=delta_p, q_ref=reference)
        rows.append(row)
        assert row['q'] == pytest.approx(reference, rel=2e-9), (delta_p, row['q'], reference)
        assert row['pressure_residual'] <= 1.0 and row['mass_residual'] <= 1e-8
        assert 0.0 < row['opening'] <= 1.0
    report_table('v2 forward curve vs independent reference', rows)


def test_v1_reverse_and_sub_crack_are_exactly_zero():
    definition = v2_definition()
    parameters = {'kv_m3_h': KV, 'p_crack_pa': P_CRACK}
    rows = []
    for delta_p in (-200000.0, -5000.0, -1000.0, -1.0, -1e-6, 0.0, 1e-6, 1000.0, 4999.0, P_CRACK):
        network, result = solve_case(definition, parameters, delta_p)
        row = measured(network, result)
        row.update(delta_p=delta_p, q_ref=0.0)
        rows.append(row)
        assert row['q'] == 0.0, (delta_p, row['q'])  # 精确零流，不是 1e-9 近似
        assert row['opening'] == 0.0
        assert row['pressure_residual'] == 0.0 and row['mass_residual'] == 0.0
    report_table('v2 reverse / sub-crack exact zero', rows)


def test_v1_threshold_sides_converge_without_dt_hacks():
    definition = v2_definition()
    parameters = {'kv_m3_h': KV, 'p_crack_pa': P_CRACK}
    rows = []
    for offset in (1e-3, 1e-2, 0.1, 1.0, 10.0, 100.0, 1000.0):
        for delta_p in (P_CRACK + offset, P_CRACK - offset):
            network, result = solve_case(definition, parameters, delta_p)
            row = measured(network, result)
            row.update(delta_p=delta_p)
            rows.append(row)
            assert row['pressure_residual'] <= 1.0 and row['mass_residual'] <= 1e-8
            assert row['nfev'] <= 40
            if delta_p > P_CRACK:
                assert row['q'] > 0.0
            else:
                assert row['q'] == 0.0
    report_table('v2 threshold neighbourhood', rows)


def test_v1_default_crack_zero_matches_v1():
    """p_crack 默认 0 退化为 v1 正向语义：同解、同迭代数。"""
    v1, v2 = v1_definition(), v2_definition()
    rows = []
    for delta_p in (20000.0, 10000.0, 5001.0, 5000.01, 1000.0, -1.0, -20000.0):
        network1, result1 = solve_case(v1, {'kv_m3_h': KV, 'cracking_pressure_pa': 0.0}, delta_p)
        network2, result2 = solve_case(v2, {'kv_m3_h': KV, 'p_crack_pa': 0.0}, delta_p)
        row1, row2 = measured(network1, result1), measured(network2, result2)
        assert row2['q'] == pytest.approx(row1['q'], rel=1e-12, abs=1e-15)
        assert row2['nfev'] == row1['nfev']
        rows.append({**row2, 'delta_p': delta_p, 'q_ref': row1['q']})
    report_table('v1 vs v2 at p_crack=0 (must be identical)', rows)


def test_v1_old_parameter_keeps_v1_reverse_flow():
    """旧项目绑定 v1：cracking=5000 在反向 1000 Pa 下仍反向导通（旧行为不覆写）。"""
    network1, result1 = solve_case(v1_definition(), {'kv_m3_h': KV, 'cracking_pressure_pa': P_CRACK}, -1000.0)
    old = measured(network1, result1)
    assert old['q'] < -1.0
    network2, result2 = solve_case(v2_definition(), {'kv_m3_h': KV, 'p_crack_pa': 0.0}, -1000.0)
    assert measured(network2, result2)['q'] == 0.0


def test_v1_cold_and_warm_start_agree():
    definition = v2_definition()
    parameters = {'kv_m3_h': KV, 'p_crack_pa': P_CRACK}
    deltas = [20000.0, 10000.0, 5001.0, 5000.01, 5000.0, 1000.0, -1.0, -20000.0]
    runner = make_runner(definition, parameters)
    rows, previous, warm_solution = [], None, None
    for delta_p in deltas:
        network, result = solve_case(definition, parameters, delta_p, runner=runner, warm=previous)
        row = measured(network, result)
        if warm_solution is not None:
            row['q_warm_ref'] = warm_solution
        row.update(delta_p=delta_p, q_ref=reference_mass_flow_kg_s(
            ValveParameters(kv_m3_h=KV, p_crack_pa=P_CRACK, density_kg_m3=row['density']), delta_p))
        rows.append(row)
        previous = result
        warm_solution = row['q']
        assert row['pressure_residual'] <= 1.0 and row['mass_residual'] <= 1e-8
        # 热启动只作为初值；验收以同一收敛门 + 与参考曲线一致为准。
        assert row['q'] == pytest.approx(row['q_ref'], rel=2e-9, abs=0.0)
    report_table('v2 cold then warm start', rows)


def _pump_bypass_project():
    catalog = catalog_map()
    valve = v2_definition()
    return Project(
        id='cv-bypass', name='泵旁路', modules=[catalog['source'], catalog['junction'], catalog['pump'], valve],
        solver=SolverOptions(thermal=False, hydraulic_diagnostics=True),
        instances=[
            ModuleInstance(id='B1', module_id='source', name='低压侧', parameters={'pressure_pa': 150000.0}),
            ModuleInstance(id='B2', module_id='source', name='高压侧', parameters={'pressure_pa': 250000.0}),
            ModuleInstance(id='J1', module_id='junction', name='泵前'),
            ModuleInstance(id='J2', module_id='junction', name='泵后'),
            ModuleInstance(id='P1', module_id='pump', name='泵', parameters={'speed_ratio': 1.0}),
            ModuleInstance(id='D1', module_id='check_valve', name='旁路止回阀', parameters={'p_crack_pa': P_CRACK}),
        ],
        connections=[
            Connection(id='c1', source=Endpoint(instance_id='B1', port_id='out0'),
                       target=Endpoint(instance_id='J1', port_id='in0')),
            Connection(id='c2', source=Endpoint(instance_id='J1', port_id='out0'),
                       target=Endpoint(instance_id='P1', port_id='in0')),
            Connection(id='c3', source=Endpoint(instance_id='P1', port_id='out0'),
                       target=Endpoint(instance_id='J2', port_id='in0')),
            Connection(id='c4', source=Endpoint(instance_id='J1', port_id='out1'),
                       target=Endpoint(instance_id='D1', port_id='in0')),
            Connection(id='c5', source=Endpoint(instance_id='D1', port_id='out0'),
                       target=Endpoint(instance_id='J2', port_id='out1')),
            Connection(id='c6', source=Endpoint(instance_id='J2', port_id='out0'),
                       target=Endpoint(instance_id='B2', port_id='out0')),
        ])


def test_v1_pump_bypass_closes_check_valve_exactly():
    network = compile_project(_pump_bypass_project())
    result = solve_network(network)
    valve = measured(network, result, 'D1')
    pump_index = branch_index(network, 'P1')
    assert valve['q'] == 0.0
    assert valve['opening'] == 0.0
    assert float(result.hydraulic.flows[pump_index]) > 5.0
    assert valve['pressure_residual'] <= 1.0 and valve['mass_residual'] <= 1e-8
    if REPORT:
        print('\n== pump bypass ==', {'q_valve': valve['q'], 'q_pump': float(result.hydraulic.flows[pump_index]),
                                      'nfev': valve['nfev'], 'residual_calls': valve['residual_calls'],
                                      'rpc_batches': valve['rpc_batches']})


def test_v1_parallel_check_valves():
    catalog = catalog_map()
    valve = v2_definition()

    def project(delta_p):
        inlet, outlet = 250000.0 + delta_p / 2, 250000.0 - delta_p / 2
        return Project(
            id='cv-parallel', name='并联止回阀',
            modules=[catalog['source'], catalog['junction'], valve],
            solver=SolverOptions(thermal=False, hydraulic_diagnostics=True),
            instances=[
                ModuleInstance(id='B1', module_id='source', name='入口', parameters={'pressure_pa': inlet}),
                ModuleInstance(id='B2', module_id='source', name='出口', parameters={'pressure_pa': outlet}),
                ModuleInstance(id='J1', module_id='junction', name='分配'),
                ModuleInstance(id='J2', module_id='junction', name='汇合'),
                ModuleInstance(id='D1', module_id='check_valve', name='阀 1', parameters={'kv_m3_h': 50.0}),
                ModuleInstance(id='D2', module_id='check_valve', name='阀 2', parameters={'kv_m3_h': 30.0}),
            ],
            connections=[
                Connection(id='t1', source=Endpoint(instance_id='B1', port_id='out0'),
                           target=Endpoint(instance_id='J1', port_id='in0')),
                Connection(id='t2', source=Endpoint(instance_id='J1', port_id='out0'),
                           target=Endpoint(instance_id='D1', port_id='in0')),
                Connection(id='t3', source=Endpoint(instance_id='D1', port_id='out0'),
                           target=Endpoint(instance_id='J2', port_id='in0')),
                Connection(id='t4', source=Endpoint(instance_id='J1', port_id='out1'),
                           target=Endpoint(instance_id='D2', port_id='in0')),
                Connection(id='t5', source=Endpoint(instance_id='D2', port_id='out0'),
                           target=Endpoint(instance_id='J2', port_id='out1')),
                Connection(id='t6', source=Endpoint(instance_id='J2', port_id='out0'),
                           target=Endpoint(instance_id='B2', port_id='out0')),
            ])

    network = compile_project(project(50000.0))
    result = solve_network(network)
    q1 = measured(network, result, 'D1')['q']
    q2 = measured(network, result, 'D2')['q']
    assert q1 > 0.0 and q2 > 0.0
    assert q1 / q2 == pytest.approx(50.0 / 30.0, rel=1e-9)
    forward_row = measured(network, result, 'D1')
    if REPORT:
        print('\n== parallel forward ==', {'q1': q1, 'q2': q2, 'nfev': forward_row['nfev'],
                                           'residual_calls': forward_row['residual_calls'],
                                           'rpc_batches': forward_row['rpc_batches'],
                                           'rpc_instances': forward_row['rpc_instances']})

    network = compile_project(project(-50000.0))
    result = solve_network(network)
    assert measured(network, result, 'D1')['q'] == 0.0
    assert measured(network, result, 'D2')['q'] == 0.0
    assert result.hydraulic.pressure_residual == 0.0 and result.hydraulic.mass_residual == 0.0


# --------------------------------------------------------------------------- V1：方案 (a) 对照
SMOOTH_SOURCE = '''import math


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("closed_steps", 0)

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        p_in, p_out = inlet.pressure_pa, ctx.port("out0").pressure_pa
        density = inlet.density_kg_m3 or 998.2
        gate = 0.5
        if p_in is not None and p_out is not None:
            width = max(1e-9, float(ctx.parameter("width_pa")))
            gate = 0.5 * (1.0 + math.tanh(((float(p_in) - float(p_out)) - float(ctx.parameter("p_crack_pa"))) / width))
        opening = max(0.0, min(1.0, float(ctx.parameter("opening_ratio")) * gate))
        ctx.net.valve(channel="main", kv=float(ctx.parameter("kv_m3_h")), opening=opening, density_kg_m3=density)
        ctx.var("opening_ratio", opening)

    def commit_step(self, ctx, dt_s):
        pass

    def finalize(self, ctx):
        pass
'''


def smooth_definition():
    return ModuleDefinition.model_validate({
        'id': 'smooth_valve_fixture', 'name': '光滑二极管对照', 'category': '对比试验', 'version': 1,
        'description': '方案 (a) 对照：tanh 光滑过渡，无真正开启压差、反向泄漏有界非零。',
        'entrypoint': 'module:Module', 'runtime': 'python', 'solver_model': 'generic',
        'source': {'runtime': SMOOTH_SOURCE}, 'source_format': 'python-v1',
        'ports': [
            {'id': 'in0', 'label': '入口', 'domain': 'fluid', 'direction': 'in', 'required': True, 'circuit': 'fluid'},
            {'id': 'out0', 'label': '出口', 'domain': 'fluid', 'direction': 'out', 'required': True, 'circuit': 'fluid'},
        ],
        'parameters': [
            {'id': 'kv_m3_h', 'label': 'Kv', 'default': 50.0, 'minimum': 0.001},
            {'id': 'p_crack_pa', 'label': '开关中心压差', 'default': 5000.0, 'minimum': 0.0},
            {'id': 'width_pa', 'label': '过渡带宽', 'default': 500.0, 'minimum': 0.001},
            {'id': 'opening_ratio', 'label': '最大开度', 'default': 1.0, 'minimum': 0.0, 'maximum': 1.0},
        ],
        'variables': [{'id': 'opening_ratio', 'label': '开度', 'quantity': 'ratio', 'source': 'derived'}],
        'channels': [{'id': 'main', 'name': '主通路', 'input_port': 'in0', 'output_port': 'out0',
                      'relation': 'resistance', 'solver_model': 'valve', 'enabled': True}],
    })


def test_v1_smooth_variant_tradeoff_is_measured():
    definition = smooth_definition()
    parameters = {'kv_m3_h': KV, 'p_crack_pa': P_CRACK, 'width_pa': 500.0}

    # ① 没有真正的开启压差：Δp = p_crack 处已经半开（方案 (b) 此处精确零流）。
    network, result = solve_case(definition, parameters, P_CRACK)
    row = measured(network, result)
    assert row['q'] > 1.0
    assert row['opening'] == pytest.approx(0.5, rel=1e-9)

    # 光滑曲线自身可复算：q = Kv·gate(Δp)·sqrt(Δp/C)，与实测一致。
    smooth_rows = {}
    for delta_p in (50000.0, 10000.0, 5001.0):
        network, result = solve_case(definition, parameters, delta_p)
        measured_row = measured(network, result)
        gate = 0.5 * (1.0 + math.tanh((delta_p - P_CRACK) / parameters['width_pa']))
        expected = valve_mass_flow_kg_s(KV, gate, delta_p, measured_row['density'])
        assert measured_row['q'] == pytest.approx(expected, rel=1e-9)
        smooth_rows[delta_p] = measured_row

    # ② 过渡带下方靠极小开度近似截止：收敛门失败（正是计划禁止的 1e-9 开度近似）。
    failed_cases = []
    for delta_p in (-1000.0, -1.0, 0.0):
        try:
            network, result = solve_case(definition, parameters, delta_p)
        except HydraulicNotConverged:
            failed_cases.append(delta_p)
            continue
        if result.hydraulic.pressure_residual > 1.0 or result.hydraulic.mass_residual > 1e-8:
            failed_cases.append(delta_p)
    assert failed_cases == [-1000.0, -1.0, 0.0]
    if REPORT:
        print('\n== smooth variant (a) ==', {'q_at_crack': row['q'], 'opening_at_crack': row['opening'],
                                             'failed_cases': failed_cases})
        print('   forward rows:', {k: (v['q'], v['nfev']) for k, v in smooth_rows.items()})

    # ③ 方案 (b) 在同样的点上精确零流且一次收敛。
    for delta_p in (-1000.0, -1.0, 0.0):
        network, result = solve_case(v2_definition(), {'kv_m3_h': KV, 'p_crack_pa': P_CRACK}, delta_p)
        assert measured(network, result)['q'] == 0.0


# --------------------------------------------------------------------------- V2：动态与发布
def dynamic_sweep(definition, parameters, deltas, *, dt_s, runner=None):
    """按 accepted 步推进的扫压差 harness：solve_network → commit_step → 下一步。

    与 SimulationSession 的接受步语义一致（每个 Δp 一个时间步）；这里显式构造时间轴，
    以便把同一条压差序列在不同 dt 下重放并比较累计反向质量。
    """
    created = runner is None
    total_forward = total_reverse = 0.0
    previous = None
    for index, delta_p in enumerate(deltas):
        network = compile_project(series_project(definition, parameters, delta_p=delta_p))
        if created:
            runner = InProcessModuleRunner(definition, network.parameters['D1'], network.project.fluid)
            runner.initialize()
            created = False
        result = solve_network(network, {'D1': runner}, time_s=index * dt_s, warm=previous)
        index_branch = branch_index(network)
        flow = float(result.hydraulic.flows[index_branch])
        link = network.branches[index_branch]
        runner.commit_step(
            CommitStepRequest(run_id='cv-sweep', instance_id='D1', time_s=(index + 1) * dt_s, dt_s=dt_s,
                              converged_ports={key.split(':', 1)[1]: state
                                               for key, state in result.port_states.items()
                                               if key.startswith('D1:')}),
            channels={'main': ChannelState(
                mass_flow_kg_s=flow,
                pressure_drop_pa=float(result.hydraulic.pressures[link.start_node]
                                       - result.hydraulic.pressures[link.end_node]))})
        total_forward += max(0.0, flow) * dt_s
        total_reverse += min(0.0, flow) * dt_s
        previous = result
    return {'forward_kg': total_forward, 'reverse_kg': total_reverse, 'state': dict(runner.state)}


def test_v2_dynamic_sweep_has_no_spurious_reverse_mass():
    definition = v2_definition()
    parameters = {'kv_m3_h': KV, 'p_crack_pa': P_CRACK}
    sweep = [20000.0, 10000.0, 5001.0, 5000.01, P_CRACK, 1000.0, -1.0, -1000.0, -20000.0, -1000.0, 20000.0]
    results = {dt_s: dynamic_sweep(definition, parameters, sweep, dt_s=dt_s) for dt_s in (0.1, 0.05, 0.02)}
    for dt_s, result in results.items():
        assert result['reverse_kg'] == 0.0, (dt_s, result['reverse_kg'])
        assert result['state']['reverse_throughput_kg'] == 0.0
        assert result['state']['closed_steps'] == 6 and result['state']['open_steps'] == 5
    # 同一压差序列：正向通过质量 ∝ dt（时间轴被重放而不是被压缩）。
    for dt_s, result in results.items():
        expected = results[0.1]['forward_kg'] * (dt_s / 0.1)
        assert result['forward_kg'] == pytest.approx(expected, rel=1e-12)
    if REPORT:
        print('\n== dynamic sweep ==',
              {k: (v['forward_kg'], v['reverse_kg']) for k, v in results.items()})


def test_v2_state_commits_only_on_accepted_steps():
    definition = v2_definition()
    forward = compile_project(series_project(definition, {'p_crack_pa': P_CRACK}, delta_p=20000.0))
    frames = solve_dynamic(forward, 0.5, 0.1)
    first, last = frames[0], frames[-1]
    # t=0 的 state 是 initialize 的初值，不是一次 commit：之后每接受一步恰好 +1 次提交。
    assert first.variables['D1.state.closed_steps'] == 0
    assert first.variables['D1.state.open_steps'] == 0
    assert first.variables['D1.state.throughput_kg'] == 0.0
    for index, frame in enumerate(frames[1:], start=1):
        commits = frame.variables['D1.state.closed_steps'] + frame.variables['D1.state.open_steps']
        assert commits == index
    assert last.variables['D1.state.throughput_kg'] > 0.0
    assert last.variables['D1.state.reverse_throughput_kg'] == 0.0
    assert last.variables['D1.state.is_open'] is True
    assert last.variables['D1.state.open_steps'] == 5

    reverse = compile_project(series_project(definition, {'p_crack_pa': P_CRACK}, delta_p=-20000.0))
    frames = solve_dynamic(reverse, 0.5, 0.1)
    assert all(frame.variables.get('D1.main.mass_flow_kg_s') == 0.0 for frame in frames)
    assert frames[-1].variables['D1.state.closed_steps'] == 5
    assert frames[-1].variables['D1.state.throughput_kg'] == 0.0
    assert frames[-1].variables['D1.state.reverse_throughput_kg'] == 0.0


def test_v2_evaluate_idempotent_under_same_accepted_state():
    definition = v2_definition()
    runner = make_runner(definition, {'kv_m3_h': KV, 'p_crack_pa': P_CRACK, 'hysteresis_pa': 500.0})
    runner.state['is_open'] = True  # 模拟已接受步：阀处于开启
    accepted = dict(runner.state)
    for delta_p in (-1000.0, 0.0, 100.0, P_CRACK + 100.0):
        first = runner.evaluate(evaluate_request(delta_p, state=accepted))
        second = runner.evaluate(evaluate_request(delta_p, state=accepted))
        assert first.model_dump() == second.model_dump()
        assert runner.state == accepted
    # Δp ≤ 0 恒关（反向精确零流不受迟滞影响）；h>0 且已开启时在关闭阈值之上保持开启。
    assert runner.evaluate(evaluate_request(-1000.0, state=accepted)).relations[0].parameters['opening_ratio'] == 0.0
    held = runner.evaluate(evaluate_request(P_CRACK - 100.0, state=accepted)).relations[0].parameters['opening_ratio']
    assert held == 1.0
    # 同一输入在 accepted state 为“关闭”时按 p_crack+h 才开启（迟滞动作正确）。
    closed = dict(runner.state, is_open=False)
    assert runner.evaluate(evaluate_request(P_CRACK + 100.0, state=closed)).relations[0].parameters['opening_ratio'] == 0.0
    assert runner.evaluate(evaluate_request(P_CRACK + 600.0, state=closed)).relations[0].parameters['opening_ratio'] > 0.0


def test_v2_hysteresis_band_is_path_dependent_and_never_leaks_reverse():
    """h>0 只改变正向开/关带；动态按 accepted 步推进即可，不需要求解器改动。"""
    definition = v2_definition()
    banded = {'kv_m3_h': KV, 'p_crack_pa': P_CRACK, 'hysteresis_pa': 500.0}
    base = {'kv_m3_h': KV, 'p_crack_pa': P_CRACK}

    # 冷启动 accepted state = 关闭：Δp=5200 在 (p_crack, p_crack+h] 内 → 保持关闭（迟滞带），
    # 无迟滞对照则 5200 > 5000 → 开启。这就是“路径相关”，不是数值缺陷。
    frames = solve_dynamic(compile_project(series_project(definition, banded, delta_p=5200.0)), 0.3, 0.1)
    assert all(frame.variables['D1.main.mass_flow_kg_s'] == 0.0 for frame in frames[1:])
    assert frames[-1].variables['D1.state.is_open'] is False
    frames = solve_dynamic(compile_project(series_project(definition, base, delta_p=5200.0)), 0.3, 0.1)
    assert frames[-1].variables['D1.main.mass_flow_kg_s'] > 0.0

    # 先大压差开启，再回落到开启压差以下（仍在关闭阈值 4500 之上）→ 保持开启并正向通过；
    # 全程反向压差仍精确零流、累计反向质量 0。
    sweep = dynamic_sweep(definition, banded, [20000.0, 4800.0, 4800.0, -1000.0], dt_s=0.1)
    assert sweep['reverse_kg'] == 0.0
    assert sweep['state']['reverse_throughput_kg'] == 0.0
    assert sweep['state']['open_steps'] == 3 and sweep['state']['closed_steps'] == 1


def test_v2_hysteresis_disabled_does_not_change_results():
    definition = v2_definition()
    for delta_p in (-20000.0, -1.0, 0.0, P_CRACK, P_CRACK + 500.0, 20000.0):
        base = measured_case(definition, {'kv_m3_h': KV, 'p_crack_pa': P_CRACK}, delta_p)
        with_param = measured_case(definition, {'kv_m3_h': KV, 'p_crack_pa': P_CRACK, 'hysteresis_pa': 0.0}, delta_p)
        assert with_param['q'] == base['q']
        assert with_param['nfev'] == base['nfev']


def test_v2_dead_end_after_close_reports_missing_reference():
    catalog = catalog_map()
    definition = v2_definition()
    project = Project(
        id='cv-dead-end', name='关闭后无参考段', modules=[catalog['source'], catalog['junction'], definition],
        solver=SolverOptions(thermal=False),
        instances=[
            ModuleInstance(id='B1', module_id='source', name='入口', parameters={'pressure_pa': 250000.0}),
            ModuleInstance(id='D1', module_id='check_valve', name='阀', parameters={'p_crack_pa': P_CRACK}),
            ModuleInstance(id='T1', module_id='junction', name='下游死端'),
        ],
        connections=[
            Connection(id='d1', source=Endpoint(instance_id='B1', port_id='out0'),
                       target=Endpoint(instance_id='D1', port_id='in0')),
            Connection(id='d2', source=Endpoint(instance_id='D1', port_id='out0'),
                       target=Endpoint(instance_id='T1', port_id='in0')),
        ])
    with pytest.raises(RuntimeErrorBase, match='缺少压力参考'):
        solve_steady(compile_project(project))


def test_v2_version_store_lists_both_versions(tmp_path):
    store = ModuleStore(MODULE_ROOT, tmp_path)
    versions = store.versions('check_valve')
    assert [(item.package.module_id, item.package.version) for item in versions] == [
        ('check_valve', '2.0.0'), ('check_valve', '1.0.0')]
    release = store.get('check_valve', 2)
    assert release.tested is True and release.release_notes
    assert release.module.content_hash == v2_definition().content_hash
    old = store.get('check_valve', 1)
    assert old.module.version == 1 and old.module.content_hash == V1_CONTENT_HASH
    assert next(module for module in store.latest() if module.id == 'check_valve').version == 2


def _v1_project(parameters=None):
    catalog = catalog_map()
    return Project(
        id='cv-upgrade', name='升级验收', modules=[catalog['source'], v1_definition()],
        solver=SolverOptions(thermal=False),
        instances=[
            ModuleInstance(id='B1', module_id='source', name='入口', parameters={'pressure_pa': 255000.0}),
            ModuleInstance(id='B2', module_id='source', name='出口', parameters={'pressure_pa': 245000.0}),
            ModuleInstance(id='D1', module_id='check_valve', name='旧项目阀', parameters=dict(parameters or {})),
        ],
        connections=[
            Connection(id='u1', source=Endpoint(instance_id='B1', port_id='out0'),
                       target=Endpoint(instance_id='D1', port_id='in0')),
            Connection(id='u2', source=Endpoint(instance_id='D1', port_id='out0'),
                       target=Endpoint(instance_id='B2', port_id='out0')),
        ])


def test_v2_upgrade_preview_keeps_old_project_and_rolls_back():
    project = _v1_project({'cracking_pressure_pa': P_CRACK})
    original = project.model_dump()
    before = solve_steady(compile_project(project)).variables['D1.main.mass_flow_kg_s']

    result = upgrade_project(project, v2_definition())
    assert result['compatible'] is True, result['reasons']
    changed = {(change['field'], change['id']) for change in result['changes']}
    assert ('parameters', 'p_crack_pa') in changed
    assert ('parameters', 'hysteresis_pa') in changed
    assert ('parameters', 'cracking_pressure_pa') in changed
    assert project.model_dump() == original  # 预览不写库：回滚即“不写入”

    upgraded = Project.model_validate(result['project'])
    assert all(node.package.version == '2.0.0' for node in upgraded.instances if node.module_id == 'check_valve')
    after = solve_steady(compile_project(upgraded)).variables['D1.main.mass_flow_kg_s']
    assert after == pytest.approx(before, rel=1e-12)  # 正向工况不变（p_crack 默认 0）

    # 不兼容目标：删除已有参数 → 预览拒绝且不产生候选项目（失败回滚路径）。
    broken = v2_definition().model_copy(deep=True)
    broken.version = 3
    broken.parameters = [parameter for parameter in broken.parameters if parameter.id != 'opening_ratio']
    rejected = upgrade_project(project, broken)
    assert rejected['compatible'] is False and rejected['reasons']
    assert 'project' not in rejected
    assert project.model_dump() == original


def test_v2_module_bench_end_to_end_with_worker():
    """独立验证台（真实 Worker）覆盖 evaluate/commit 与全部声明变量。"""
    definition = v2_definition()
    forward = run_module_test(ModuleTestRequest(
        module=definition, parameters={'kv_m3_h': KV, 'p_crack_pa': P_CRACK},
        inlet_pressure_pa=255000.0, outlet_pressure_pa=245000.0, duration_s=0.2, dt_s=0.1))
    variable_ids = {variable.id for variable in definition.variables}
    missing = [variable_id for variable_id in variable_ids
               if f'D1.{variable_id}' not in forward.frame.variables]
    assert not missing
    assert forward.frame.variables['D1.opening_ratio'] > 0.0
    assert forward.frame.variables['D1.state.is_open'] is True
    assert forward.frame.variables['D1.state.reverse_throughput_kg'] == 0.0
    assert len(forward.evaluation.relations) == 1

    reverse = run_module_test(ModuleTestRequest(
        module=definition, parameters={'kv_m3_h': KV, 'p_crack_pa': P_CRACK},
        inlet_pressure_pa=245000.0, outlet_pressure_pa=255000.0, duration_s=0.2, dt_s=0.1))
    assert reverse.frame.variables['D1.main.mass_flow_kg_s'] == 0.0
    assert reverse.frame.variables['D1.opening_ratio'] == 0.0
    assert reverse.frame.variables['D1.state.closed_steps'] >= 1
