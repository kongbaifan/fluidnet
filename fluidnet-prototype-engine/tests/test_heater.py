"""电加热器：声明功率、温度变化与零流量拒绝（内置理想加热段）。"""
from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance, Project
from fn_engine.solver import solve_steady
from test_continuous import wait


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


def heater_prototype(power_kw=5.):
    model = heater_project()
    # Literal Studio names and display units exercise the UI boundary independently
    # of PARAMETER_BINDINGS, including a renamed legacy built-in module.
    parameters = {'B1': {'pressure': 250., 'temperature': 20.},
                  'V1': {'opening': 50., 'kv': 10.},
                  'H1': {'power': power_kw, 'loss': 0., 'diameter': 40.},
                  'B2': {'pressure': 120., 'temperature': 20.}}
    nodes = [{'id': node.id, 'moduleId': 'legacy-heater' if node.id == 'H1' else node.module_id,
              'params': parameters[node.id]} for node in model.instances]
    heater = next(node for node in nodes if node['id'] == 'H1')
    heater.update(draft={'power': 7.}, variableState={
        'banks': [{'param:power': 3.}], 'bankNames': ['低功率']})
    return {'format': 'fluidnet-studio-prototype', 'schema': 1, 'activeProject': model.id,
            'models': [], 'charts': {'extra': []},
            'modules': [{'id': 'source', 'kind': 'source'}, {'id': 'valve', 'kind': 'valve'},
                        {'id': 'legacy-heater', 'kind': 'heater',
                         'ports': [{'id': 'in0', 'direction': 'in', 'domain': 'fluid'},
                                   {'id': 'out0', 'direction': 'out', 'domain': 'fluid'}],
                         'channels': [{'id': 'ch0', 'input': 'in0', 'output': 'out0',
                                       'kind': 'resistance', 'enabled': True}]}],
            'projects': [{'id': model.id, 'name': model.name, 'medium': 'water',
                'pages': [{'id': 'main', 'nodes': nodes,
                    'edges': [[c.id, c.source.instance_id, c.source.port_id,
                               c.target.instance_id, c.target.port_id] for c in model.connections]}],
                'scenarios': [{'id': 'half-power', 'name': '半功率',
                               'overrides': {'H1': {'power': power_kw / 2}}}]}]}


@pytest.mark.parametrize('power_kw', [5., -5.])
def test_studio_heater_units_drafts_banks_and_scenarios_reach_the_solver(power_kw):
    project = normalize_prototype_export(heater_prototype(power_kw))
    heater = next(node for node in project.instances if node.id == 'H1')
    assert heater.parameters == {'heat_input_w': power_kw * 1000.,
                                 'loss_coefficient': 0., 'diameter_m': .04}
    assert heater.draft_parameters['heat_input_w'] == 7000.
    assert heater.banks[0].values['heat_input_w'] == 3000.
    assert project.scenarios[0].overrides['H1']['heat_input_w'] == power_kw * 500.
    frame = solve_steady(compile_project(project))
    assert frame.variables['H1.heat_w'] == pytest.approx(power_kw * 1000.)
    assert frame.metrics['energy_residual_w'] == pytest.approx(0., abs=1e-6)


def test_studio_heater_normalizes_and_saved_scenario_runs_after_restart(tmp_path):
    payload = heater_prototype()
    settings = {'data_root': tmp_path / 'data', 'module_storage_root': tmp_path / 'modules'}
    with TestClient(create_app(**settings)) as client:
        normalized = client.post('/api/v1/prototype/normalize', json=payload)
        assert normalized.status_code == 200, normalized.text
        solved = client.post('/api/v1/solve', json=normalized.json())
        assert solved.status_code == 200, solved.text
        assert solved.json()['variables']['H1.heat_w'] == pytest.approx(5000.)
        saved = client.post('/api/v1/workspace', json={'data': payload, 'expected_revision': 0})
        assert saved.status_code == 200, saved.text

    with TestClient(create_app(**settings)) as client:
        submitted = client.post('/api/v1/projects/heater/runs', json={
            'mode': 'dynamic', 'duration_s': 1., 'dt_s': 1., 'scenario_id': 'half-power'})
        assert submitted.status_code == 202, submitted.text
        record = wait(client, submitted.json()['run_id'], lambda item: item['status'] in {'completed', 'failed'})
        assert record['status'] == 'completed', record.get('frame')
        assert record['request']['project_revision'] == 1
        assert record['frame']['variables']['H1.heat_w'] == pytest.approx(2500.)
