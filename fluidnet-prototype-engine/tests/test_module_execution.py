"""S3 callback provenance, optional wire metadata and lazy single-Worker integration."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fn_engine.models import (
    ChannelState, CommitStepRequest, EvaluateRequest, FluidConfig, InitializeRequest,
    ModuleDefinition, ModuleExecutionInfo, ModuleRequestContext, PortState,
)
from fn_engine.module_contracts import check_module_compatibility
from fn_engine.module_execution import begin_module_step, mark_module_accepted
from fn_engine.runtime import InProcessModuleRunner, ModuleContext, WorkerProcess

ROOT = Path(__file__).resolve().parents[1]
INFO_FIELDS = list(ModuleExecutionInfo.model_fields)


def probe_definition(log_dir=None, fail_on=None):
    frozen = json.loads((ROOT / 'tests/fixtures/module-system/v2-snapshots.json').read_text(encoding='utf-8'))
    payload = deepcopy(frozen['modules'][0]['definition'])
    payload.update(id='execution_probe', name='Execution probe', content_hash=None, definition_hash=None)
    payload['sdk'] = {'api_version':'0.3.0', 'capabilities':['context.execution.v1']}
    payload['variables'] = []
    payload['source'] = {'runtime': f'''
import json
import math
from pathlib import Path
def record(ctx):
    info = {{key:getattr(ctx.execution,key) for key in {INFO_FIELDS!r}}}
    info.update(port_names=list(ctx.ports), channel_names=list(ctx.channels))
    log_dir = {str(log_dir) if log_dir else None!r}
    if log_dir is not None:
        path = Path(log_dir) / (str(ctx.execution.instance_id) + '.jsonl')
        with path.open('a',encoding='utf-8') as output:
            output.write(json.dumps(info) + '\\n')
    ctx.var('execution_info', json.dumps(info))
    return info
class Module:
    def initialize(self,ctx):
        record(ctx)
        ctx.state.setdefault('commit_count',0)
    def evaluate(self,ctx):
        record(ctx)
        ctx.net.valve(channel='main',kv=10*(1+.1*math.sin(ctx.time_s)),opening=.8)
    def commit_step(self,ctx,dt_s):
        record(ctx)
        if ctx.execution.instance_id == {fail_on!r}:
            raise ValueError('injected commit failure')
        ctx.state['commit_count']+=1
    def finalize(self,ctx):
        self.final_info=record(ctx)
'''}
    return ModuleDefinition.model_validate(payload)


def request(time_s=1., context=None):
    return EvaluateRequest(run_id='run-test', instance_id='D1', iteration_id=7, time_s=time_s,
        trial_ports={'in0':PortState(pressure_pa=250000.)}, readonly_state={'commit_count':0}, context=context)


@pytest.mark.parametrize('runner_type', [InProcessModuleRunner, WorkerProcess])
def test_trial_converged_commit_identity_and_no_implicit_acceptance(runner_type, tmp_path):
    runner = runner_type(probe_definition(tmp_path), {}, FluidConfig(), run_id='run-test', instance_id='D1')
    try:
        runner.initialize()
        step = begin_module_step({'D1':runner})
        mark_module_accepted({'D1':runner}, 0.)
        first = runner.evaluate(request())
        second = runner.evaluate(request())
        info = json.loads(first.variables['execution_info'])
        other = json.loads(second.variables['execution_info'])
        assert info['phase'] == 'evaluate' and info['time_s'] == 1.
        assert info['iteration_id'] == 7 and info['dt_s'] is None
        assert info['step_id'] == step and other['step_id'] == step
        assert info['request_id'] != other['request_id']
        assert info['port_data'] == 'trial' and info['channel_data'] == 'unavailable'
        assert info['state_data'] == 'input_copy' and info['accepted_time_s'] == 0.
        assert first.relations == second.relations
        assert runner.state == {'commit_count':0}
        committed = runner.commit_step(CommitStepRequest(run_id='run-test',instance_id='D1',time_s=1.,dt_s=1.,
            converged_ports={'in0':PortState(pressure_pa=250000.,mass_flow_kg_s=.5)},
            converged_channels={'main':ChannelState(mass_flow_kg_s=.5)}))
        info = json.loads(committed.variables['execution_info'])
        assert info['phase'] == 'commit_step' and info['dt_s'] == 1.
        assert info['port_data'] == info['channel_data'] == 'converged'
        assert info['state_data'] == 'candidate'
        assert info['accepted_time_s'] == 0.  # Callback completion is not owner acceptance.
        assert committed.state['commit_count'] == 1
        mark_module_accepted({'D1':runner}, 1.)
    finally:
        if isinstance(runner, WorkerProcess): runner.close()
        else: runner.finalize()
    records = [json.loads(line) for line in (tmp_path/'D1.jsonl').read_text(encoding='utf-8').splitlines()]
    assert records[0]['phase'] == 'initialize' and records[0]['time_s'] == 0.
    assert records[0]['accepted_time_s'] is None
    final = records[-1]
    assert final['phase'] == 'finalize' and final['time_s'] == 1.
    assert final['step_id'] is None
    assert final['accepted_time_s'] == 1.
    assert final['port_data'] == final['channel_data'] == 'unavailable'
    assert final['port_names'] == final['channel_names'] == []
    assert all(row['run_id']=='run-test' and row['instance_id']=='D1' for row in records)
    assert len({row['request_id'] for row in records}) == len(records)


def test_direct_context_is_manual_unknown_and_public_metadata_is_read_only():
    ctx = ModuleContext({}, FluidConfig())
    assert ctx.phase == 'manual' and ctx.time_s is None
    assert ctx.execution.request_id is None and ctx.execution.step_id is None
    assert ctx.execution.state_data == 'unavailable'
    with pytest.raises(AttributeError): ctx.time_s = 1.
    with pytest.raises(AttributeError): ctx.phase = 'evaluate'
    with pytest.raises(AttributeError): ctx.execution = ModuleExecutionInfo()
    with pytest.raises(ValidationError): ctx.execution.phase = 'evaluate'


@pytest.mark.parametrize('context,phase', [(None,'trial'), (ModuleRequestContext(request_id='fixed-request',
    step_id='fixed-step',port_data='converged'),'converged')])
def test_explicit_or_old_requests_work_and_inputs_are_not_rewritten(context, phase):
    runner = InProcessModuleRunner(probe_definition(), {}, FluidConfig())
    original = request(context=context)
    saved = original.model_dump_json()
    result = runner.evaluate(original)
    info = json.loads(result.variables['execution_info'])
    assert info['port_data'] == phase
    assert original.model_dump_json() == saved
    if context is not None:
        assert info['request_id'] == 'fixed-request' and info['step_id'] == 'fixed-step'
    else:
        assert info['step_id'] is None
        assert 'context' not in original.model_dump(mode='json')


def test_unavailable_data_is_not_reported_as_converged_zero():
    runner = InProcessModuleRunner(probe_definition(), {}, FluidConfig())
    empty = request().model_copy(update={'trial_ports':{}})
    info = json.loads(runner.evaluate(empty).variables['execution_info'])
    assert info['port_data'] == info['channel_data'] == 'unavailable'
    committed = runner.commit_step(CommitStepRequest(run_id='run-test',instance_id='D1',time_s=1.,dt_s=1.))
    info = json.loads(committed.variables['execution_info'])
    assert info['port_data'] == info['channel_data'] == 'unavailable'


@pytest.mark.parametrize('runner_type', [InProcessModuleRunner, WorkerProcess])
def test_failed_future_evaluation_does_not_change_finalize_time_or_accepted_watermark(runner_type,tmp_path):
    module = probe_definition(tmp_path)
    module.source['runtime'] = module.source['runtime'].replace('        ctx.net.valve(',
        "        if ctx.time_s > 0: raise ValueError('injected evaluation failure')\n        ctx.net.valve(")
    runner = runner_type(module, {}, FluidConfig(), run_id='run-test',instance_id='D1')
    try:
        runner.initialize()
        mark_module_accepted({'D1':runner},0.)
        with pytest.raises(ValueError,match='injected evaluation failure'):
            runner.evaluate(request(time_s=3.))
    finally:
        if isinstance(runner,WorkerProcess): runner.close()
        else: runner.finalize()
    rows = [json.loads(line) for line in (tmp_path/'D1.jsonl').read_text(encoding='utf-8').splitlines()]
    assert rows[-2]['phase']=='evaluate' and rows[-2]['time_s']==3.
    assert rows[-1]['phase']=='finalize' and rows[-1]['time_s']==0.
    assert rows[-1]['step_id'] is None
    assert rows[-1]['accepted_time_s']==0.


@pytest.mark.parametrize('field,value', [('request_id',''),('step_id','bad step'),
    ('accepted_time_s',float('nan')),('accepted_time_s',float('inf')),('accepted_time_s',-1.),
    ('port_data','accepted'),('phase','commit_step')])
def test_invalid_transport_metadata_cannot_spoof_phase_or_accepted_port_data(field, value):
    with pytest.raises(ValidationError):
        ModuleRequestContext.model_validate({'request_id':'valid',field:value})


def test_old_wire_dump_does_not_gain_metadata_defaults():
    old = request().model_dump(mode='json')
    assert 'context' not in old
    assert 'context' not in CommitStepRequest(run_id='r',instance_id='D1',time_s=1.,dt_s=1.).model_dump()
    init = InitializeRequest(run_id='r',instance_id='D1',package={'module_id':'test','version':'1.0.0','content_hash':'0'*64})
    assert 'context' not in init.model_dump()


@pytest.mark.parametrize('api,accepted', [('0.1.0',False),('0.2.0',False),('0.3.0',True)])
def test_execution_capability_requires_new_sdk(api, accepted):
    module = probe_definition()
    module.sdk.api_version = api
    if accepted:
        check_module_compatibility(module)
    else:
        with pytest.raises(ValueError, match='不支持能力'):
            check_module_compatibility(module)
