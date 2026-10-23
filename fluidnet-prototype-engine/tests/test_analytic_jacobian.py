"""J2/J3：解析 Jacobian 的启用条件、与有限差分的一致性、以及解的一致性回归。"""
import numpy as np
import pytest
from scipy.optimize._numdiff import approx_derivative

from fn_engine import solver as solver_module
from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance
from fn_engine.solver import solve_dynamic, solve_hydraulics, solve_steady
from test_thermal import project, prototype
from test_run_control import custom_project


def inst(iid, module_id, **parameters):
    return ModuleInstance(id=iid, module_id=module_id, name=iid, parameters=parameters)


def link(cid, a, b):
    (si, sp), (ti, tp) = a.split(':'), b.split(':')
    return Connection(id=cid, source=Endpoint(instance_id=si, port_id=sp),
                      target=Endpoint(instance_id=ti, port_id=tp))


def two_valve_project():
    return project([('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                    ('V1', 'valve', {'kv_m3_h': 12.}), ('V2', 'valve', {'kv_m3_h': 6.}),
                    ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
                   [('B1:out0', 'V1:in0'), ('V1:out0', 'V2:in0'), ('V2:out0', 'B2:out0')])


def exchanger_project():
    """换热器是内置但本轮未注册解析导数的模型（两侧各一条阻力通路）。"""
    return project([('B1', 'source', {'pressure_pa': 400000., 'temperature_k': 293.15}),
                    ('B2', 'source', {'pressure_pa': 350000., 'temperature_k': 300.15}),
                    ('C1', 'source', {'pressure_pa': 200000., 'temperature_k': 280.15}),
                    ('C2', 'source', {'pressure_pa': 150000., 'temperature_k': 285.15}),
                    ('E1', 'exchanger', {'ua_w_k': 5000., 'loss_coefficient': 5.})],
                   [('B1:out0', 'E1:in0'), ('E1:out0', 'B2:out0'),
                    ('C1:out0', 'E1:in1'), ('E1:out1', 'C2:out0')])


def capture_jacobian_mismatch(model, compare_calls=3):
    """在 least_squares 里取出解析 Jacobian，与该点的 2-point 差分逐元素比较。"""
    network = compile_project(model)
    worst = {'rel': 0.0, 'calls': 0}
    original = solver_module.least_squares

    def spy(residual, x0, **options):
        jac = options.get('jac')
        if callable(jac) and worst['calls'] < compare_calls:
            sparse = jac(x0)
            analytic = np.asarray(sparse.todense() if hasattr(sparse, 'todense') else sparse)
            numeric = np.asarray(approx_derivative(residual, x0, method='2-point'))
            scale = max(float(np.max(np.abs(numeric))), 1e-30)
            worst['rel'] = max(worst['rel'], float(np.max(np.abs(analytic - numeric))) / scale)
            worst['calls'] += 1
        return original(residual, x0, **options)

    solver_module.least_squares = spy
    try:
        solve_dynamic(network, .2, .1) if model.id in ('water-net', 'heat-loop', 'tank-control') else \
            solve_hydraulics(network)
    finally:
        solver_module.least_squares = original
    return worst


def test_analytic_path_records_mode_and_removes_perturbation_calls():
    model = two_valve_project()
    model.solver.hydraulic_diagnostics = True
    result = solve_hydraulics(compile_project(model))
    assert result.jacobian_mode == 'analytic'
    assert '内置' in result.jacobian_reason
    counters = result.counters
    assert counters['perturbation_calls'] == 0, '解析路径不应再有 Jacobian 有限差分扰动'
    assert counters['residual_calls'] == counters['nfev']
    assert counters['njev'] >= 1


def test_python_module_keeps_finite_difference():
    model = custom_project()
    model.solver.hydraulic_diagnostics = True
    result = solve_hydraulics(compile_project(model))
    assert result.jacobian_mode == 'finite_difference'
    assert 'Python' in result.jacobian_reason
    assert result.counters['perturbation_calls'] > 0


def test_degenerate_zero_flow_station_falls_back_to_numeric():
    """单支路偏置网络：q=0 是 q|q| 的驻点，解析 Newton 步可能停在假收敛点。

    必须只回退一次到有限差分、得到正确反向流量，并在结果里说明原因（容差不放宽）。
    """
    from test_contracts_and_physics import simple
    model = simple(params={'opening_ratio': 0.5, 'kv_m3_h': 10}, inlet=100000., outlet=200000.)
    model.solver.hydraulic_diagnostics = True
    result = solve_hydraulics(compile_project(model))
    assert result.flows[0] == pytest.approx(-1.38769063, rel=1e-6)
    assert result.jacobian_mode == 'finite_difference'
    assert '回退有限差分' in result.jacobian_reason
    assert result.counters['jacobian_fallback'] == 'finite_difference'


def test_heat_exchanger_channels_use_resistance_derivatives():
    """换热器的每条通路被编译为阻力关系，因此纯内置换热器网络同样走解析路径。"""
    model = exchanger_project()
    model.solver.thermal = False
    model.solver.hydraulic_diagnostics = True
    result = solve_hydraulics(compile_project(model))
    assert result.jacobian_mode == 'analytic'
    assert result.counters['perturbation_calls'] == 0


def test_explicit_switch_disables_analytic():
    model = two_valve_project()
    model.solver.analytic_jacobian = False
    model.solver.hydraulic_diagnostics = True
    result = solve_hydraulics(compile_project(model))
    assert result.jacobian_mode == 'finite_difference'
    assert '显式关闭' in result.jacobian_reason
    assert result.counters['perturbation_calls'] > 0


@pytest.mark.parametrize('name', ['water-net', 'heat-loop', 'tank-control'])
def test_jacobian_matches_two_point_difference(name):
    model = prototype(name)
    network = compile_project(model)
    worst = {'rel': 0.0, 'calls': 0}
    original = solver_module.least_squares

    def spy(residual, x0, **options):
        jac = options.get('jac')
        if callable(jac) and worst['calls'] < 3:
            sparse = jac(x0)
            analytic = np.asarray(sparse.todense() if hasattr(sparse, 'todense') else sparse)
            numeric = np.asarray(approx_derivative(residual, x0, method='2-point'))
            scale = max(float(np.max(np.abs(numeric))), 1e-30)
            worst['rel'] = max(worst['rel'], float(np.max(np.abs(analytic - numeric))) / scale)
            worst['calls'] += 1
        return original(residual, x0, **options)

    solver_module.least_squares = spy
    try:
        solve_dynamic(network, .2, .1)
    finally:
        solver_module.least_squares = original
    assert worst['calls'] > 0
    assert worst['rel'] < 1e-6, f'解析 Jacobian 与 2-point 差分的最大相对误差 {worst["rel"]:.3e}'


def test_closed_valve_row_stays_zero_flow():
    """精确关闭的阀门仍是零流量约束行，解析路径不能把它“导数抹平”。"""
    model = project([('B1', 'source', {'pressure_pa': 250000.}), ('V1', 'valve', {'kv_m3_h': 10., 'opening_ratio': 0.}),
                     ('B2', 'source', {'pressure_pa': 120000.})],
                    [('B1:out0', 'V1:in0'), ('V1:out0', 'B2:out0')])
    model.solver.thermal = False
    compiled = compile_project(model)
    assert compiled.branches[0].closed, 'opening_ratio=0 的阀应被编译为关闭支路'
    automatic = solve_hydraulics(compiled)
    model.solver.analytic_jacobian = False
    numeric = solve_hydraulics(compile_project(model))
    assert automatic.jacobian_mode == 'analytic'
    assert automatic.flows == pytest.approx(numeric.flows, rel=1e-12, abs=1e-14)
    assert automatic.pressures == pytest.approx(numeric.pressures, rel=1e-12, abs=1e-9)


@pytest.mark.parametrize('name', ['water-net', 'heat-loop', 'tank-control'])
def test_analytic_solution_matches_numeric(name):
    model = prototype(name)
    analytic = solve_dynamic(compile_project(model), .2, .1)
    model.solver.analytic_jacobian = False
    numeric = solve_dynamic(compile_project(model), .2, .1)
    for a, b in zip(analytic, numeric):
        for key, value in a.variables.items():
            if isinstance(value, float):
                assert b.variables[key] == pytest.approx(value, rel=1e-6, abs=1e-7), key
    assert analytic[-1].solve_summary['jacobian_mode'] == 'analytic'
    assert numeric[-1].solve_summary['jacobian_mode'] == 'finite_difference'


def test_steady_and_node_coupling_with_analytic():
    model = prototype('heat-loop')
    model.solver.property_coupling = 'node'
    model.solver.thermal = True
    analytic = solve_steady(compile_project(model))
    model.solver.analytic_jacobian = False
    numeric = solve_steady(compile_project(model))
    for key, value in analytic.variables.items():
        if isinstance(value, float):
            assert numeric.variables[key] == pytest.approx(value, rel=1e-6, abs=1e-7), key
