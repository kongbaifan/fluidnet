import time
from fastapi.testclient import TestClient
from fn_engine.api import create_app
from fn_engine.module_templates import create_template
from fn_engine.runtime import WorkerProcess
from test_module_execution_network import network_for


def terminal(client,identifier):
    for _ in range(1000):
        record=client.get('/api/v1/runs/'+identifier).json()
        if record['status']=='failed':return record
        time.sleep(.01)
    raise AssertionError('failure did not terminalize')


def test_background_lost_sync_keeps_internal_accepted_frame_and_state(monkeypatch,tmp_path):
    module=create_template('managed_state','sync_probe','Sync probe')
    project=network_for(module,2,batch=False).project
    original=WorkerProcess.synchronize_state
    def lost(worker,candidate):
        if worker.execution.instance_id=='D2':raise OSError('lost sync acknowledgement')
        return original(worker,candidate)
    monkeypatch.setattr(WorkerProcess,'synchronize_state',lost)
    with TestClient(create_app(data_root=tmp_path)) as client:
        response=client.post('/api/v1/runs?background=true',json={'project':project.model_dump(mode='json'),'mode':'dynamic','duration_s':.5,'dt_s':.5})
        assert response.status_code==202,response.text
        record=terminal(client,response.json()['run_id'])
        assert record['frame']['time_s']==.5
        assert record['frame']['variables']['D1.state.commit_count']==1
        assert record['frame']['variables']['D2.state.commit_count']==1
        rows=client.get(f"/api/v1/runs/{response.json()['run_id']}/history").json()['rows']
        assert rows[-1]['time_s']==.5
        assert rows[-1]['valid']
        assert any(d['code']=='MODULE_SYNC_FAILED' for d in record['frame']['diagnostics'])


def test_background_runtime_exception_retains_source_location(tmp_path):
    module=create_template('managed_state','line_probe','Line probe')
    module.source['runtime']=module.source['runtime'].replace('def evaluate(self, ctx: ModuleContext) -> None:',
        'def evaluate(self, ctx: ModuleContext) -> None:\n        raise ValueError("background line probe")')
    with TestClient(create_app(data_root=tmp_path)) as client:
        response=client.post('/api/v1/runs?background=true',json={'project':network_for(module).project.model_dump(mode='json'),
            'mode':'dynamic','duration_s':.5,'dt_s':.5})
        record=terminal(client,response.json()['run_id'])
        diagnostic=record['frame']['diagnostics'][0]
        assert diagnostic['instance_id']=='D1'
        assert diagnostic['source_file']=='module.py' and diagnostic['source_line']>0
        assert diagnostic['phase']=='evaluate'
