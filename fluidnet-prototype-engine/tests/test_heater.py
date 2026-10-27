"""电加热器：声明功率、温度变化与零流量拒绝（内置理想加热段）。"""
import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance, Project
from fn_engine.solver import solve_steady


def heater_project(heat=5000., opening=.5, kv=10., loss=0., diameter=.04):
    definitions = catalog_map()
    return Project(id='heater', name='加热器测试',
        modules=[definitions[key] for key in ('source', 'valve', 'heater')],
        instances=[
            ModuleInstance(id='B1', module_id='source', name='入口边界',
                           parameters={'pressure_pa': 250000., 'temperature_k': 293.15}),
            ModuleInstance(id='V1', module_id='valve', name='调节阀',
                           parameters={'opening_ratio': opening, 'kv_m3_h': kv}),
            ModuleInstance(id='H1', module_id='heater', name='电加热器',
                           parameters={'heat_input_w': heat, 'loss_coefficient': loss, 'diameter_m': diameter}),
            ModuleInstance(id='B2', module_id='source', name='出口边界',
                           parameters={'pressure_pa': 120000., 'temperature_k': 293.15})],
        connections=[
            Connection(id='e1', source=Endpoint(instance_id='B1', port_id='out0'),
                       target=Endpoint(instance_id='V1', port_id='in0')),
            Connection(id='e2', source=Endpoint(instance_id='V1', port_id='out0'),
                       target=Endpoint(instance_id='H1', port_id='in0')),
            Connection(id='e3', source=Endpoint(instance_id='H1', port_id='out0'),
                       target=Endpoint(instance_id='B2', port_id='out0'))])


@pytest.mark.parametrize('heat', [5000., -5000.])
def test_heater_adds_the_declared_power_and_raises_or_lowers_temperature(heat):
    frame = solve_steady(compile_project(heater_project(heat)))
    flow = frame.variables['H1.mass_flow_kg_s']
    assert flow > 0
    assert frame.variables['H1.heat_w'] == pytest.approx(heat, rel=1e-9)
    inlet = frame.variables['H1.inlet_temperature_k']
    outlet = frame.variables['H1.outlet_temperature_k']
    # Water cp ≈ 4.18 kJ/(kg·K): the specific enthalpy change must equal Q/w.
    specific_heat = abs(heat) / abs(flow * (outlet - inlet))
    assert specific_heat == pytest.approx(4180., rel=.05)
    assert frame.metrics['energy_residual_w'] == pytest.approx(0., abs=1e-6)


def test_zero_flow_heat_is_rejected():
    with pytest.raises(CompilationError, match='零流量'):
        solve_steady(compile_project(heater_project(opening=0.)))


def test_heat_input_is_a_runtime_parameter():
    parameters = {p.id: p for p in catalog_map()['heater'].parameters}
    assert parameters['heat_input_w'].runtime
    assert parameters['loss_coefficient'].minimum == 0.
