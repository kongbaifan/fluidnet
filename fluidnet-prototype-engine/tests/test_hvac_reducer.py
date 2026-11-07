"""Reducer acceptance: independent minor-loss values, real Workers, and three-loop HVAC use."""
import math
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine.air_examples import air_example
from fn_engine.api import create_app
from fn_engine.bench import run_module_test
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import ModuleSaveRequest, ModuleTestRequest, Project
from fn_engine.packages import ModuleStore, load_module_package
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady

ROOT = Path(__file__).resolve().parents[1]


def reducer():
    return load_module_package(ROOT / 'modules/pipe_reducer')


def network_project(parameters=None, delta=10000., method='dense'):
    module = reducer()
    return Project(id='reducer-acceptance', name='异径管验收', modules=[catalog_map()['source'], module],
        instances=[{'id':'B1', 'module_id':'source', 'name':'入口', 'parameters':{'pressure_pa':250000.}},
                   {'id':'R1', 'module_id':module.id, 'name':'异径管', 'parameters':parameters or {}},
                   {'id':'B2', 'module_id':'source', 'name':'出口', 'parameters':{'pressure_pa':250000.-delta}}],
        connections=[{'id':'c1', 'source':{'instance_id':'B1','port_id':'out0'}, 'target':{'instance_id':'R1','port_id':'in0'}},
                     {'id':'c2', 'source':{'instance_id':'R1','port_id':'out0'}, 'target':{'instance_id':'B2','port_id':'out0'}}],
        solver={'hydraulic_method':method, 'module_cache':True, 'module_mixed_jacobian':True})


@pytest.mark.parametrize('profile,contraction_k,expansion_k', [
    ('sudden', .375, .5625),
    ('gradual', .15529142706151244, .3785228534624367),
])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('method', ['dense', 'sparse'])
def test_real_network_matches_small_bore_loss_reference(profile, contraction_k, expansion_k, reverse, method):
    # 100 -> 50 mm; gradual length gives a 30-degree included angle. Constants are
    # independent reference values; the module's geometry helper is never called.
    parameters = {'inlet_diameter_m':.1, 'outlet_diameter_m':.05,
                  'transition_length_m':.09330127018922194, 'profile':profile}
    delta = -10000. if reverse else 10000.
    frame = solve_steady(compile_project(network_project(parameters, delta, method)))
    values = frame.variables
    assert frame.valid
    coefficient = expansion_k if reverse else contraction_k
    assert values['R1.loss_coefficient'] == pytest.approx(coefficient, rel=1e-12)
    density = values['R1.in0.density_kg_m3']
    area = math.pi * .05**2 / 4
    expected = math.copysign(area * math.sqrt(2*density*abs(delta)/coefficient), delta)
    assert values['R1.main.mass_flow_kg_s'] == pytest.approx(expected, rel=2e-5)
    assert values['R1.pressure_loss_pa'] == pytest.approx(delta, abs=.01)
    assert values['R1.outlet_velocity_m_s']/values['R1.inlet_velocity_m_s'] == pytest.approx(4., rel=2e-5)
    assert values['R1.is_contraction'] == int(not reverse)
    assert frame.metrics['mass_residual_kg_s'] < 1e-7


def test_swapping_the_bores_matches_reversing_the_connections():
    original = {'profile':'sudden', 'inlet_diameter_m':.1, 'outlet_diameter_m':.05}
    swapped = {'profile':'sudden', 'inlet_diameter_m':.05, 'outlet_diameter_m':.1}
    reverse = solve_steady(compile_project(network_project(original, -10000.)))
    forward = solve_steady(compile_project(network_project(swapped, 10000.)))
    assert forward.variables['R1.main.mass_flow_kg_s'] == pytest.approx(-reverse.variables['R1.main.mass_flow_kg_s'], rel=2e-5)
    assert forward.variables['R1.loss_coefficient'] == reverse.variables['R1.loss_coefficient']


def test_zero_pressure_has_zero_flow_and_no_mass_accumulation():
    response = run_module_test(ModuleTestRequest(module=reducer(), inlet_pressure_pa=250000.,
        outlet_pressure_pa=250000., duration_s=.2, dt_s=.1))
    assert response.frame.valid
    assert abs(response.frame.variables['D1.main.mass_flow_kg_s']) < 1e-8
    assert abs(response.committed.state['throughput_kg']) < 1e-8


def test_dynamic_mass_is_committed_once_per_accepted_step():
    session = SimulationSession(compile_project(network_project()), .3, .1)
    try:
        session.initialize()
        frames = [session.advance() for _ in range(3)]
        mass = sum(abs(frame.variables['R1.main.mass_flow_kg_s'])*.1 for frame in frames)
        assert frames[-1].variables['R1.state.throughput_kg'] == pytest.approx(mass, rel=1e-10)
    finally:
        session.close()


@pytest.mark.parametrize('parameters', [
    {'profile':'unknown'}, {'profile':'gradual', 'transition_length_m':0},
    {'inlet_diameter_m':0}, {'outlet_diameter_m':float('nan')},
])
def test_invalid_geometry_cannot_start_a_network(parameters):
    with pytest.raises(ValueError):
        solve_steady(compile_project(network_project(parameters)))


def test_reducer_runs_in_the_real_air_chilled_water_cooling_water_project():
    project = air_example('chiller-air-loop')
    project.modules.append(reducer())
    # Revalidate after replacing the existing Chiller -> WaterValve connection.
    data = project.model_dump(mode='json')
    data['instances'].append({'id':'Reducer', 'module_id':'pipe_reducer', 'name':'冷冻水异径管'})
    for connection in data['connections']:
        if connection['id'] == 'water3':
            connection['target'] = {'instance_id':'Reducer', 'port_id':'in0'}
    data['connections'].append({'id':'reducer-out', 'source':{'instance_id':'Reducer','port_id':'out0'},
                                'target':{'instance_id':'WaterValve','port_id':'in0'}})
    frame = solve_steady(compile_project(Project.model_validate(data)))
    values = frame.variables
    assert frame.valid
    assert values['Reducer.main.mass_flow_kg_s'] == pytest.approx(values['Coil.ch1.mass_flow_kg_s'], abs=1e-7)
    assert values['Reducer.pressure_loss_pa'] > 0
    assert abs(values['ChilledRef.out0.mass_flow_kg_s']) < 1e-9
    assert values['Chiller.cooling_power_w'] == pytest.approx(values['Coil.water_heat_w']+values['ChilledPump.shaft_power_w'], abs=.04)
    assert values['Tower.heat_rejected_w'] == pytest.approx(values['Chiller.condenser_heat_w']+values['CoolingPump.shaft_power_w'], abs=.04)


def test_catalog_and_immutable_versions_include_the_new_module(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path/'api')) as client:
        response = client.get('/api/v1/modules')
        assert response.status_code == 200
        module = next(item for item in response.json()['modules'] if item['id'] == 'pipe_reducer')
        assert module['category'] == '暖通基础设备'
        assert module['version'] == 1
    store = ModuleStore(ROOT/'modules', tmp_path/'versions')
    first = store.get('pipe_reducer', 1).module
    saved = store.save(ModuleSaveRequest(module=first, expected_latest_version=1))
    assert saved.module.version == 2
    assert store.get('pipe_reducer', 1).module.content_hash == first.content_hash
    assert store.get('pipe_reducer', 2).module.definition_hash == saved.module.definition_hash
