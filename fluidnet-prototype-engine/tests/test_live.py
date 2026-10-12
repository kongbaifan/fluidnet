import time

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.compiler import compile_project
from fn_engine.models import PIDController
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_dynamic
from test_run_control import custom_project, dynamic_request
from test_states import fed_tank
from test_thermal import project


def wait(client, run_id, predicate):
    for _ in range(600):
        record = client.get('/api/v1/runs/' + run_id).json()
        if predicate(record):
            return record
        time.sleep(.01)
    pytest.fail(str(record))


def command(client, run_id, payload):
    response = client.post(f'/api/v1/runs/{run_id}/command', json=payload)
    assert response.status_code == 200, response.text
    key = response.json()['command_id']
    record = wait(client, run_id, lambda r: any(e.get('command_id') == key and e.get('command_status') != 'accepted' for e in r['events']))
    return next(e for e in reversed(record['events']) if e.get('command_id') == key)


def test_paused_sessions_release_compute_slots_and_step_keeps_worker(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        model=custom_project()
        model.modules[-1].parameters[0].runtime=True
        model.modules[-1].definition_hash=None
        ids = [client.post('/api/v1/runs?background=true', json=dynamic_request(model, .4, .1) | {'start_paused': True}).json()['run_id'] for _ in range(3)]
        for run_id in ids:
            wait(client, run_id, lambda r: r['status'] == 'paused')
        run_id = ids[0]
        for count in (1, 2):
            assert command(client, run_id, {'action': 'step'})['command_status'] == 'applied'
            record = wait(client, run_id, lambda r: r['status'] == 'paused' and r['frame']['time_s'] == pytest.approx(count*.1))
        reference = solve_dynamic(compile_project(custom_project()), .2, .1)[-1]
        assert record['frame']['variables']['V1.state.commit_count'] == reference.variables['V1.state.commit_count']
        key = 'set-opening-1'
        body = {'action':'set', 'command_id':key, 'instance_id':'V1', 'parameter_id':'opening_ratio', 'value':.2}
        event = command(client, run_id, body)
        assert event['command_status'] == 'applied'
        assert event['time_s'] == pytest.approx(.2)
        assert client.post(f'/api/v1/runs/{run_id}/command',json=body).json()['command_status'] == 'applied'
        assert client.post(f'/api/v1/runs/{run_id}/command',json=body | {'value':.3}).status_code == 409
        assert command(client, run_id, {'action':'set','instance_id':'V1','parameter_id':'kv_m3_h','value':5})['command_status']=='rejected'
        command(client, run_id, {'action':'step'})
        changed = wait(client, run_id, lambda r: r['frame']['time_s'] == pytest.approx(.3))
        assert changed['frame']['variables']['V1.mass_flow_kg_s'] < reference.variables['V1.mass_flow_kg_s']
        assert changed['request']['project']['instances'][1]['parameters']['opening_ratio'] == .5


def test_realtime_publishes_before_completion_and_pause_does_not_expire(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        payload={'project':fed_tank().model_dump(mode='json'),'mode':'dynamic','duration_s':2.,'dt_s':.1,'execution_mode':'realtime'}
        run_id=client.post('/api/v1/runs?background=true',json=payload).json()['run_id']
        record=wait(client,run_id,lambda r:r['frame'] and r['frame']['time_s']>=.1)
        assert record['status']=='running'
        command(client,run_id,{'action':'pause'})
        before=client.get('/api/v1/runs/'+run_id).json()['frame']['time_s']
        time.sleep(.25)
        record=client.get('/api/v1/runs/'+run_id).json()
        assert record['status']=='paused' and record['frame']['time_s']==before
        command(client,run_id,{'action':'stop'})
        assert client.get('/api/v1/runs/'+run_id).json()['status']=='cancelled'


def test_pid_heated_tank_reaches_target_and_limits_output():
    model=project([('B1','source',{}),('V1','valve',{'opening_ratio':0}),('T1','tank',{'area_m2':.05,'level_m':1.,'height_m':3.,'heat_loss_ua_w_k':100.})], [('B1:out0','V1:in0'),('V1:out0','T1:in0')])
    model.controllers=[PIDController(id='temperature',measurement='T1.state.temperature_k',instance_id='T1',parameter_id='heat_input_w',
        setpoint=303.15,kp=2000,ki=30,sample_s=1.,minimum=0,maximum=10000)]
    frames=solve_dynamic(compile_project(model),1200,1)
    assert abs(frames[-1].variables['T1.state.temperature_k']-303.15)<.2
    assert all(0<=f.variables['controller.temperature.output']<=10000 for f in frames)
    assert all(abs(f.metrics['energy_residual_w']) < 1e-4 for f in frames)


def test_isolated_passive_pipe_holds_pressure_and_reconnects():
    model=project([('B1','source',{'pressure_pa':250000}),('V1','valve',{}),('L1','pipe',{'thermal_cells':3}),('V2','valve',{}),('B2','source',{'pressure_pa':120000})],
        [('B1:out0','V1:in0'),('V1:out0','L1:in0'),('L1:out0','V2:in0'),('V2:out0','B2:out0')])
    session=SimulationSession(compile_project(model),.3,.1)
    try:
        initial=session.advance()
        for valve in ('V1','V2'):session.set_parameter(valve,'opening_ratio',0)
        isolated=session.advance()
        assert abs(isolated.variables['L1.mass_flow_kg_s'])<1e-8
        assert any(d.code=='ISOLATED_PRESSURE_HELD' for d in isolated.diagnostics)
        for valve in ('V1','V2'):session.set_parameter(valve,'opening_ratio',.8)
        reconnected=session.advance()
        assert reconnected.variables['L1.mass_flow_kg_s']==pytest.approx(initial.variables['L1.mass_flow_kg_s'],rel=1e-6)
    finally:session.close()


def test_pid_level_example_tracks_target():
    from fn_engine.examples import pid_example
    frames=solve_dynamic(compile_project(pid_example('level')),600,.5)
    assert abs(frames[-1].variables['T1.state.level_m']-1.5)<.015
    assert all(abs(f.metrics['mass_residual_kg_s'])<=1e-8 for f in frames)
