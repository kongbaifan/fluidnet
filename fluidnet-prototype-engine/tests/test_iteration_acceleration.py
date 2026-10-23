"""L1/L2：热力 Picard 与 node 外循环的迭代加速（默认关闭，旧路径不变）。"""
import numpy as np
import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, FluidConfig, ModuleInstance, Project
from fn_engine.properties import property_service
from fn_engine.solver import _coupling_relaxation, solve_steady
from fn_engine.thermal import _acceleration_guard, _next_damping


def link(cid, a, b):
    (si, sp), (ti, tp) = a.split(':'), b.split(':')
    return Connection(id=cid, source=Endpoint(instance_id=si, port_id=sp),
                      target=Endpoint(instance_id=ti, port_id=tp))


def pipe_chain(count, ua=2000.0, ambient=278.15, inlet=353.15):
    catalog = catalog_map()
    project = Project(id='l1', name='l1', fluid=FluidConfig(),
                      modules=[catalog['source'], catalog['pipe']],
                      instances=[ModuleInstance(id='B1', module_id='source', name='入口',
                                                parameters={'pressure_pa': 400000., 'temperature_k': inlet}),
                                 ModuleInstance(id='B2', module_id='source', name='出口',
                                                parameters={'pressure_pa': 100000., 'temperature_k': inlet})],
                      connections=[])
    previous = 'B1:out0'
    for i in range(count):
        project.instances.append(ModuleInstance(id=f'P{i}', module_id='pipe', name=f'P{i}', parameters={
            'length_m': 20.0, 'diameter_m': 0.05, 'roughness_m': 0.0,
            'heat_loss_ua_w_k': ua, 'ambient_temperature_k': ambient}))
        project.connections.append(link(f'in{i}', previous, f'P{i}:in0'))
        previous = f'P{i}:out0'
    project.connections.append(link('end', previous, 'B2:out0'))
    return project


def run(project, **solver):
    for key, value in solver.items():
        setattr(project.solver, key, value)
    return solve_steady(compile_project(project))


# --- L1：热力 Picard ---------------------------------------------------------

def test_adaptive_damping_reduces_thermal_iterations():
    baseline = run(pipe_chain(16))
    accelerated = run(pipe_chain(16), thermal_acceleration='adaptive')
    assert accelerated.metrics['thermal_iterations'] <= baseline.metrics['thermal_iterations'] * 0.7
    reference = baseline.variables['B2.out0.temperature_k']
    assert accelerated.variables['B2.out0.temperature_k'] == pytest.approx(reference, rel=1e-7)
    assert abs(accelerated.metrics['energy_residual_w']) < 1e-3


def test_aitken_damping_converges_to_same_state():
    baseline = run(pipe_chain(16))
    accelerated = run(pipe_chain(16), thermal_acceleration='aitken')
    assert accelerated.variables['B2.out0.temperature_k'] == pytest.approx(
        baseline.variables['B2.out0.temperature_k'], rel=1e-6)
    assert accelerated.metrics['thermal_iterations'] <= baseline.metrics['thermal_iterations']


def test_default_mode_keeps_legacy_damping():
    implicit = run(pipe_chain(8))
    explicit = run(pipe_chain(8), thermal_acceleration='none')
    assert implicit.variables == explicit.variables
    assert implicit.metrics['thermal_iterations'] == explicit.metrics['thermal_iterations']


def test_damping_coefficient_is_bounded():
    scale = np.array([4180.0, 4180.0])
    delta = np.array([1.0, -2.0])
    for mode in ('adaptive', 'aitken'):
        for damping in (0.05, 0.5, 1.0):
            alpha = _next_damping(mode, damping, delta, delta * 0.5, 0.1, 0.2, scale)
            assert 0.1 <= alpha <= 1.0
    # Aitken 在残差方向稳定时给出有界系数；分母为零时退回 0.7。
    assert _next_damping('aitken', 0.8, delta, delta.copy(), 0.1, 0.2, scale) == pytest.approx(0.7)


def test_acceleration_guard_rejects_phase_and_step_overrun():
    service = property_service(FluidConfig())
    pressure = 1.0e7  # 10 MPa：饱和温度足够高，210 K 的跳变仍在单相液体内
    states = [service.state_pt(pressure, 293.15), service.state_pt(pressure, 293.15)]

    def node_states(enthalpies):
        return [service.state_ph(pressure, float(value)) for value in enthalpies]

    base = np.array([state.enthalpy_j_kg for state in states])
    overrun = base + 210.0 * np.array([4180.0, 4180.0])
    assert '温度变化' in _acceleration_guard(base, overrun, node_states)
    assert _acceleration_guard(base, np.array([np.nan, 0.0]), node_states) == '出现非有限值'
    assert _acceleration_guard(base, base, node_states) is None

    # 相态越界（进入两相）也必须被保护捕获，而不是让物性异常冒到外层。
    def two_phase_states(enthalpies):
        return [service.state_ph(250000.0, float(value)) for value in enthalpies]

    low_pressure_base = np.array([service.state_pt(250000.0, 293.15).enthalpy_j_kg] * 2)
    assert '物性/相态越界' in _acceleration_guard(low_pressure_base, low_pressure_base + 250.0 * 4180.0,
                                                 two_phase_states)


# --- L2：node 外循环 -------------------------------------------------------

def test_coupling_relaxation_is_bounded_and_resets():
    scale = np.array([1000.0, 1000.0])
    defect = np.array([1.0, -1.0])
    assert _coupling_relaxation('adaptive', 1.0, defect, None, scale) == 1.0
    for mode in ('adaptive', 'aitken'):
        alpha = _coupling_relaxation(mode, 0.5, defect, defect * 0.5, scale)
        assert 0.2 <= alpha <= 1.0


def test_node_coupling_acceleration_matches_reference():
    baseline = run(pipe_chain(8), property_coupling='node')
    accelerated = run(pipe_chain(8), property_coupling='node', coupling_acceleration='adaptive')
    for key, value in baseline.variables.items():
        if isinstance(value, float):
            assert accelerated.variables[key] == pytest.approx(value, rel=1e-9, abs=1e-9), key
    assert accelerated.metrics['coupling_iterations'] <= baseline.metrics['coupling_iterations']
    # 收敛判据仍是“未松弛目标的固定点缺陷”，不是松弛后的步长。
    assert baseline.metrics['coupling_iterations'] >= 1
