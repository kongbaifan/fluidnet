"""Exact callback inputs, isolated Workers and durable project failure evidence."""
from copy import deepcopy
import json
import time

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.models import (CommitStepRequest, EvaluateRequest, FluidConfig, ModulePhaseRequest,
    ModuleReplayRequest, ModuleRequestContext, PortState)
from fn_engine.module_replay import replay_module
from fn_engine.module_templates import create_template
from fn_engine.runtime import InProcessModuleRunner, RuntimeErrorBase
from test_module_execution_network import network_for


def failing_module(phase='evaluate', conditional=False):
    module = create_template('resistance', 'replay_probe', '失败复现设备')
    module.sdk.capabilities += ['thermal.v1', 'observe.v1', 'hydraulic.derivatives.v1']
    module.source = {'runtime': f'''class Module:
    def initialize(self, ctx):
        if {phase!r} == 'initialize': self.fault(ctx)
        ctx.state['counter'] = 7
    def fault(self, ctx):
        info=ctx.execution
        before=(info.phase, info.time_s, info.dt_s, info.iteration_id, info.request_id, ctx.state.get('counter'),
                ctx.port('in0').pressure_pa, ctx.parameters.get('diameter_m'), ctx.channel('main').mass_flow_kg_s)
        ctx.state['counter']=999
        ctx.parameters['diameter_m']=999
        if 'in0' in ctx.ports: ctx.ports['in0'].pressure_pa=999
        raise ValueError(str(before))
    def evaluate(self, ctx):
        if {phase!r} == 'evaluate' and ({not conditional!r} or ctx.time_s >= .1): self.fault(ctx)
        ctx.net.resistance(channel='main',diameter_m=.04,loss_coefficient=12.,density_kg_m3=998.2)
    def thermal(self, ctx):
        if {phase!r} == 'thermal': self.fault(ctx)
        ctx.heat('main',0.)
    def observe(self, ctx):
        if {phase!r} == 'observe': self.fault(ctx)
    def jacobian(self, ctx):
        if {phase!r} == 'jacobian': self.fault(ctx)
    def commit_step(self, ctx, dt):
        if {phase!r} == 'commit_step': self.fault(ctx)
    def finalize(self, ctx): pass
'''}
    return module


def capture(phase='evaluate'):
    module=failing_module(phase)
    runner=InProcessModuleRunner(module, {'diameter_m':.04}, FluidConfig(), run_id='capture-run',instance_id='valve1')
    context=ModuleRequestContext(request_id='original-request',step_id='original-step',accepted_time_s=.2)
    ports={'in0':PortState(pressure_pa=250000.,temperature_k=293.15,density_kg_m3=998.2),
           'out0':PortState(pressure_pa=120000.,temperature_k=293.15,density_kg_m3=998.2)}
    if phase!='initialize':
        runner.initialize()
        runner.state['counter']=23
    with pytest.raises(RuntimeErrorBase) as caught:
        if phase=='initialize':runner.initialize(context)
        elif phase=='evaluate':
            runner.evaluate(EvaluateRequest(run_id='capture-run',instance_id='valve1',iteration_id=13,
                time_s=.5,trial_ports=ports,readonly_state=deepcopy(runner.state),context=context))
        elif phase=='commit_step':
            runner.prepare_step(CommitStepRequest(run_id='capture-run',instance_id='valve1',time_s=.5,dt_s=.3,
                converged_ports=ports,converged_channels={'main':{'mass_flow_kg_s':2.3}},context=context))
        else:
            runner.phase_call(phase,ModulePhaseRequest(run_id='capture-run',instance_id='valve1',time_s=.5,
                ports=ports,channels={'main':{'mass_flow_kg_s':2.3}},context=context))
    return caught.value.replay, runner


@pytest.mark.parametrize('phase',['initialize','evaluate','thermal','observe','jacobian','commit_step'])
def test_fresh_worker_replays_original_callback_inputs_without_initializing_again(phase):
    snapshot, original=capture(phase)
    before=deepcopy(snapshot)
    assert snapshot['parameters']['diameter_m']==.04
    assert snapshot['state']==({} if phase=='initialize' else {'counter':23})
    if phase!='initialize':assert snapshot['ports']['in0']['pressure_pa']==250000.
    if phase=='evaluate':assert snapshot['execution']['iteration_id']==13
    if phase=='commit_step':assert snapshot['execution']['dt_s']==.3
    response=replay_module(ModuleReplayRequest(replay=snapshot))
    assert response.status=='failed' and response.matched_failure
    assert response.diagnostics[0].message==snapshot['failure']['message']
    assert response.diagnostics[0].source_line==snapshot['failure']['source_line']
    assert response.execution.request_id=='original-request'
    assert snapshot==before
    if phase!='initialize':assert original.state=={'counter':23}


@pytest.mark.parametrize('background',[False,True])
def test_run_failure_is_archived_once_and_survives_restart_without_modifying_run(tmp_path,background):
    project=network_for(failing_module(conditional=True),batch=False).project
    with TestClient(create_app(data_root=tmp_path)) as client:
        response=client.post('/api/v1/runs',params={'background':background},json={
            'project':project.model_dump(mode='json'),'mode':'dynamic','duration_s':.2,'dt_s':.1})
        assert response.status_code==(202 if background else 201),response.text
        run_id=response.json()['run_id']
        deadline=time.monotonic()+20
        while True:
            record=client.get('/api/v1/runs/'+run_id).json()
            if record['status']=='failed':break
            assert time.monotonic()<deadline
            time.sleep(.025)
        assert 'module_failure' not in record
        captured=client.get(f'/api/v1/runs/{run_id}/module-failure')
        assert captured.status_code==200,captured.text
        replay=captured.json()['replay']
        assert replay['execution']['time_s']==.1
        assert record['frame']['time_s']==0.
        assert replay['ports']['in0']['pressure_pa']!=999
        assert replay['state']['counter']==7
        rerun=client.post('/api/v1/modules/replay',json={'replay':replay})
        assert rerun.status_code==200,rerun.text
        assert rerun.json()['matched_failure'] is True
        assert client.get('/api/v1/runs/'+run_id).json()==record
        history=client.get('/api/v1/runs/'+run_id+'/history').json()
        assert all('module_failure' not in row and 'replay' not in row for row in history['rows'])
    with TestClient(create_app(data_root=tmp_path)) as client:
        restored=client.get(f'/api/v1/runs/{run_id}/module-failure')
        assert restored.json()==captured.json()
        assert client.post('/api/v1/modules/replay',json={'replay':restored.json()['replay']}).json()['matched_failure']


def test_invalid_and_legacy_snapshots_rejected_before_worker_launch(tmp_path,monkeypatch):
    from fn_engine.runtime import WorkerProcess
    snapshot,_=capture()
    def no_launch(*args,**kwargs):raise AssertionError('must not launch')
    monkeypatch.setattr(WorkerProcess,'_ensure_process',no_launch)
    with TestClient(create_app(data_root=tmp_path)) as client:
        bad=deepcopy(snapshot);bad['module']['source']['runtime']+='\n# tampered\n'
        assert client.post('/api/v1/modules/replay',json={'replay':bad}).status_code==422
        bad=deepcopy(snapshot);bad['execution']['phase']='finalize'
        assert client.post('/api/v1/modules/replay',json={'replay':bad}).status_code==422
        bad=deepcopy(snapshot);bad.pop('format_version')
        assert client.post('/api/v1/modules/replay',json={'replay':bad}).status_code==422
        bad=deepcopy(snapshot);bad['state']={'oversize':'x'*65537}
        assert client.post('/api/v1/modules/replay',json={'replay':bad}).status_code==422


def test_completed_run_has_no_failure_snapshot(tmp_path):
    from fn_engine.regulating_valves import example
    with TestClient(create_app(data_root=tmp_path)) as client:
        result=client.post('/api/v1/runs',json={'project':example().model_dump(mode='json')})
        assert result.status_code==201 and result.json()['status']=='completed',result.text
        failure=client.get('/api/v1/runs/'+result.json()['run_id']+'/module-failure').json()
        assert failure['replay'] is None
        assert client.get('/api/v1/runs/missing/module-failure').status_code==404


def test_worker_uses_snapshot_source_even_when_original_object_changes():
    snapshot,original=capture()
    original.definition.source['runtime']='raise AssertionError("new source must not execute")'
    response=replay_module(ModuleReplayRequest.model_validate_json(json.dumps({'replay':snapshot})))
    assert response.matched_failure


def test_refrigeration_callback_keeps_typed_boundary():
    from test_refrigeration_modules import SOURCE, definition, worker, request, point
    runner=worker(definition(SOURCE.replace('point = ctx.refrigeration.throttle',
        "raise ValueError('typed failure')\n        point = ctx.refrigeration.throttle")))
    try:
        runner.initialize()
        with pytest.raises(RuntimeErrorBase) as failure:runner.evaluate_refrigeration(request())
        snapshot=failure.value.replay
        assert snapshot['refrigeration']==point().model_dump(mode='json')
        assert replay_module(ModuleReplayRequest(replay=snapshot)).matched_failure
    finally:runner.close()


def test_error_diagnostic_is_replayable_and_has_original_state():
    module=failing_module('commit_step')
    module.source['runtime']=module.source['runtime'].replace('raise ValueError(str(before))',
        "ctx.diagnostic('PROBE_LIMIT',str(before),severity='error')")
    runner=InProcessModuleRunner(module,{'diameter_m':.04},FluidConfig())
    runner.initialize()
    with pytest.raises(RuntimeErrorBase) as failure:
        runner.prepare_step(CommitStepRequest(run_id='run1',instance_id='D1',time_s=.5,dt_s=.5))
    assert runner.state=={'counter':7}
    assert failure.value.replay['state']=={'counter':7}
    assert replay_module(ModuleReplayRequest(replay=failure.value.replay)).matched_failure
