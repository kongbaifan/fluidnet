"""A1 acceptance: independent heat reference, accepted state and public persistence."""
from copy import deepcopy
import math

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import apply_scenario, create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, circuit_info, compile_project
from fn_engine.models import ControlScript, ModuleInstance, Scenario
from fn_engine.refrigeration.examples import ideal_room_example
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed, solve_dynamic, solve_steady
from test_continuous import wait


def room_project():
    project = ideal_room_example()
    project.controllers = []
    project.instances[1].parameters = {'capacity_ratio': .4}
    return project


def prototype(project=None):
    project = project or room_project()
    definitions = {m.id: m for m in project.modules}
    nodes = []
    for instance in project.instances:
        definition = definitions[instance.module_id]
        values = {p.id: p.unit.from_canonical(instance.parameters.get(p.id, p.default))
                  for p in definition.parameters}
        nodes.append({'id': instance.id, 'moduleId': instance.module_id, 'params': values,
                      'draft': values | {'heat_input_w': 2.} if instance.id == 'ROOM1' else values})
    return {'format': 'fluidnet-studio-prototype', 'schema': 1, 'activeProject': project.id,
            'modules': [{'id': m.id, 'kind': m.id, 'runtime': 'builtin', 'name': m.name,
                         'version': 1, 'ports': [p.model_dump(mode='json') for p in m.ports],
                         'channels': []} for m in project.modules],
            'models': [], 'charts': {'extra': []},
            'projects': [{'id': project.id, 'name': project.name, 'caseId': project.id,
                          'controllers': [c.model_dump(mode='json') for c in project.controllers],
                          'solver': {'dt': 30},
                          'scenarios': [{'id': 'load', 'name': '附加 1 kW',
                                         'overrides': {'ROOM1': {'heat_input_w': 1.}}}],
                          'pages': [{'id': 'main', 'nodes': nodes,
                                     'edges': [['heat1', 'COLD1', 'heat', 'ROOM1', 'heat']]}]}]}


def test_implicit_heat_balance_converges_to_independent_analytic_solution():
    project = room_project()
    errors = []
    for step in (10., 5., 2.5):
        project.solver.dynamic_step_s = step
        network = compile_project(project)
        p = network.parameters['ROOM1']
        ua_air = p['wall_ua_w_k'] + p['roof_ua_w_k']
        ua = ua_air + p['floor_ua_w_k']
        steady = (ua_air * p['ambient_temperature_k'] + p['floor_ua_w_k'] * p['ground_temperature_k']
                  - 4000.) / ua
        expected = steady + (p['temperature_k'] - steady) * math.exp(-ua * 3600. / p['heat_capacity_j_k'])
        frame = solve_dynamic(network, 3600., 30.)[-1]
        errors.append(abs(frame.variables['ROOM1.state.temperature_k'] - expected))
        assert frame.variables['COLD1.state.cooling_energy_j'] == pytest.approx(4000. * 3600.)
        stored = p['heat_capacity_j_k'] * (frame.variables['ROOM1.state.temperature_k'] - p['temperature_k'])
        net = frame.variables['ROOM1.state.external_energy_j'] - frame.variables['COLD1.state.cooling_energy_j']
        assert stored == pytest.approx(net, abs=.001)
        assert abs(frame.metrics['energy_residual_j']) < .001
        assert abs(frame.metrics['energy_residual_w']) < 1e-6
    assert errors[-1] < .001
    assert errors[1] / errors[0] == pytest.approx(.5, abs=.01)
    assert errors[2] / errors[1] == pytest.approx(.5, abs=.01)


def test_thermal_variables_and_steady_heat_balance_use_registered_contract():
    project = room_project()
    network = compile_project(project)
    assert circuit_info(network) == []
    frame = solve_steady(network)
    assert abs(frame.metrics['storage_power_w']) < 1e-9
    declared = {f'{i.id}.{v.id}' for i in project.instances
                for v in network.modules[i.module_id].variables}
    assert frame.variables.keys() == declared
    with pytest.raises(CompilationError, match='动态'):
        solve_steady(compile_project(ideal_room_example()))
    for m in project.modules:
        for p in m.parameters:
            if p.id.endswith('ua_w_k'):
                p.default = 0.
    with pytest.raises(CompilationError, match='稳态热参考'):
        solve_steady(compile_project(project))


@pytest.mark.parametrize('mutation,code', [
    ('disconnect', 'THERMAL_CONNECTION_MISSING'),
    ('mixed', 'THERMAL_MODEL_UNSUPPORTED'),
    ('port', 'THERMAL_PORT_INVALID'),
    ('limits', 'THERMAL_PARAMETER_CONTRACT'),
    ('thermal_off', 'THERMAL_REQUIRED'),
    ('custom_runtime', 'THERMAL_MODEL_UNSUPPORTED'),
    ('bad_state', 'THERMAL_TOPOLOGY_UNSUPPORTED'),
])
def test_thermal_compile_rejects_unsupported_contracts(mutation, code):
    project = room_project()
    if mutation == 'disconnect':
        project.connections = []
    elif mutation == 'mixed':
        project.modules.append(catalog_map()['pipe'])
        project.instances.append(ModuleInstance(id='L1', module_id='pipe', name='管道'))
    elif mutation == 'port':
        project.modules[0].ports[0].direction = 'out'
    elif mutation == 'limits':
        project.modules[1].parameters[1].maximum = 2.
    elif mutation == 'thermal_off':
        project.solver.thermal = False
    elif mutation == 'custom_runtime':
        project.modules[0].runtime = 'python'
    elif mutation == 'bad_state':
        project.modules[0].state_model = 'open_tank'
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == code


def test_control_drops_temperature_toward_minus18_without_fake_power_or_cop():
    frames = solve_dynamic(compile_project(ideal_room_example()), 7200., 30.)
    assert frames[0].variables['ROOM1.state.temperature_k'] == 263.15
    assert frames[-1].variables['ROOM1.state.temperature_k'] == pytest.approx(255.15, abs=.02)
    assert frames[-1].variables['COLD1.cooling_power_w'] == pytest.approx(2864., abs=20.)
    assert not any('cop' in key or 'electric' in key for key in frames[-1].variables)


def test_runtime_writes_are_atomic_and_initial_temperature_is_read_only():
    session = create_session(compile_project(room_project()), 60., 30.)
    try:
        session.initialize()
        original = deepcopy(session.network.parameters)
        with pytest.raises(CompilationError):
            session.write_variables({'ROOM1.param.heat_input_w': 5000., 'COLD1.param.capacity_ratio': 2.})
        assert session.network.parameters == original
        with pytest.raises(CompilationError):
            session.set_parameter('ROOM1', 'temperature_k', 260.)
        session.write_variables({'ROOM1.param.heat_input_w': 5000., 'COLD1.param.capacity_ratio': 0.})
        frame = session.advance()
        assert frame.variables['ROOM1.state.temperature_k'] > 263.15
        assert frame.variables['COLD1.state.cooling_energy_j'] == 0.
        assert frame.parameter_revision == 1
    finally:
        session.close()


def test_failed_thermal_trial_preserves_state_counters_and_script_commit():
    project = room_project()
    project.instances[1].parameters['cooling_power_w'] = 1e12
    project.control_scripts = [ControlScript(enabled=True, sample_s=5.,
        inputs=['ROOM1.state.temperature_k'], outputs=['ROOM1.param.heat_input_w'],
        source='''def initialize(ctx):
    ctx.state["count"] = 0
def step(ctx, dt_s):
    ctx.state["count"] += 1
    ctx.write("ROOM1.param.heat_input_w", 100.)
def finalize(ctx):
    pass
''')]
    session = create_session(compile_project(project), 30., 30.)
    try:
        first = session.initialize()
        with pytest.raises(SolveFailed):
            session.advance()
        assert session.time == 0.
        assert session.temperatures['ROOM1'] == first.variables['ROOM1.state.temperature_k']
        assert session.cooling_energy['COLD1'] == session.external_energy['ROOM1'] == 0.
        assert session.scripts['control'].state['count'] == 0
        worker = session.scripts['control'].process
    finally:
        session.close()
    assert worker.poll() is not None


def test_bridge_units_drafts_scenarios_and_old_fluid_projects():
    data = prototype()
    project = normalize_prototype_export(data)
    assert project.solver.dynamic_step_s == 10.
    assert project.instances[0].parameters['temperature_k'] == 263.15
    assert project.instances[0].parameters['heat_capacity_j_k'] == 1200000.
    assert project.instances[0].draft_parameters['heat_input_w'] == 2000.
    assert project.instances[1].parameters['capacity_ratio'] == .4
    changed = compile_project(apply_scenario(project, 'load'))
    assert changed.parameters['ROOM1']['heat_input_w'] == 1000.
    assert compile_project(project).parameters['ROOM1']['heat_input_w'] == 0.
    from test_continuous import valve_line
    assert type(create_session(compile_project(valve_line()), 1., .1)).__name__ == 'SimulationSession'


def test_shared_api_pause_step_parameter_change_and_script_preview(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        project = client.get('/api/v1/examples/cold-storage').json()
        health = client.get('/api/v1/health').json()
        assert 'thermal' in health['supported_domains']
        assert health['capabilities']['cold_room_ideal_source']
        run_id = client.post('/api/v1/runs?background=true', json={'project': project,
            'mode': 'dynamic', 'duration_s': 60., 'dt_s': 30., 'start_paused': True}).json()['run_id']
        wait(client, run_id, lambda r: r['status'] == 'paused')
        base = '/api/v1/runs/' + run_id
        command = client.post(base + '/command', json={'action': 'step'})
        command.raise_for_status()
        record = wait(client, run_id, lambda r: r['status'] == 'paused' and r['frame']['time_s'] == 30.)
        cold_energy = record['frame']['variables']['COLD1.state.cooling_energy_j']
        client.post(base + '/command', json={'action': 'controller', 'controller_id': 'room_temperature',
                                           'parameter_id': 'setpoint', 'value': 253.15}).raise_for_status()
        client.post(base + '/command', json={'action': 'resume'}).raise_for_status()
        record = wait(client, run_id, lambda r: r['status'] == 'completed')
        assert record['frame']['variables']['COLD1.state.cooling_energy_j'] > cold_energy
        assert record['frame']['variables']['controller.room_temperature.setpoint'] == 253.15
        script = ControlScript(enabled=True, inputs=['ROOM1.state.temperature_k'],
            outputs=['ROOM1.param.heat_input_w'], source='''def initialize(ctx):
    pass
def step(ctx, dt_s):
    ctx.write("ROOM1.param.heat_input_w", 100.)
def finalize(ctx):
    pass
''')
        response = client.post('/api/v1/controls/preview', json={'project': project, 'script': script.model_dump()})
        response.raise_for_status()
        assert response.json()['writes']['ROOM1.param.heat_input_w'] == 100.


def test_saved_room_archive_and_backup_recompute_after_restart(tmp_path):
    root = tmp_path / 'data'
    data = prototype()
    with TestClient(create_app(data_root=root)) as client:
        client.post('/api/v1/workspace', json={'data': data, 'expected_revision': 0}).raise_for_status()
        normalized = client.post('/api/v1/prototype/normalize', json=data)
        normalized.raise_for_status()
        body = {'project': normalized.json(), 'mode': 'dynamic', 'duration_s': 60., 'dt_s': 30.}
        record = client.post('/api/v1/runs', json=body).json()
        assert record['status'] == 'completed'
        run_id = record['run_id']
        backup = client.post('/api/v1/workspace/backup')
        backup.raise_for_status()
        restored = client.post('/api/v1/workspace/restore', content=backup.content)
        restored.raise_for_status()
        target = restored.json()['directory']
    for directory in (root, target):
        with TestClient(create_app(data_root=directory)) as client:
            saved = client.get('/api/v1/workspace').json()['data']
            assert saved == data
            archive = client.get('/api/v1/runs/' + run_id).json()
            assert archive['status'] == 'completed'
            assert archive['frame']['variables'] == record['frame']['variables']
            normalized = client.post('/api/v1/prototype/normalize', json=saved).json()
            replay = client.post('/api/v1/runs', json=body | {'project': normalized}).json()
            assert replay['frame']['variables'] == record['frame']['variables']


def test_24h_thermal_run_uses_bounded_background_history():
    with TestClient(create_app()) as client:
        project = room_project()
        project.scenarios = [Scenario(id='off', name='停机', overrides={'COLD1': {'capacity_ratio': 0.}})]
        body = {'project': project.model_dump(mode='json'), 'mode': 'dynamic',
                'duration_s': 86400., 'dt_s': 30., 'history_window': 20, 'scenario_id': 'off'}
        assert client.post('/api/v1/runs', json=body).status_code == 422
        run_id = client.post('/api/v1/runs?background=true', json=body).json()['run_id']
        record = wait(client, run_id, lambda r: r['status'] == 'completed')
        assert record['total_rows'] == 2881
        assert record['frame']['variables']['COLD1.state.cooling_energy_j'] == 0.
        assert len(client.get(f'/api/v1/runs/{run_id}/history').json()['rows']) == 20
