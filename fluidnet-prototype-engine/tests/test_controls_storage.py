import time

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import ControlScript
from fn_engine.simulation import SimulationSession
from fn_engine.storage import StorageError, WorkspaceStore
from test_continuous import valve_line, wait


SOURCE = '''def initialize(ctx):
    ctx.state["count"] = 0
def step(ctx, dt_s):
    ctx.read("V1.mass_flow_kg_s")
    ctx.state["count"] += 1
    ctx.write("V1.param.opening_ratio", 0.4 + ctx.state["count"] * 0.1)
    ctx.log("sample")
def finalize(ctx):
    pass
'''


def controlled(source=SOURCE, **changes):
    p = valve_line()
    p.control_scripts = [ControlScript(source=source, enabled=True, sample_s=.1,
        inputs=['V1.mass_flow_kg_s'], outputs=['V1.param.opening_ratio'], **changes)]
    return p


def body(project=None, **changes):
    return {'project': (project or controlled()).model_dump(mode='json'), 'mode': 'dynamic',
            'duration_s': .3, 'dt_s': .1} | changes


def workspace():
    # The server preserves the entire authoring document, including opaque UI drafts.
    return {'schema': 1, 'activeProject': 'p', 'projects': [{'id': 'p', 'control': SOURCE,
        'pages': [{'draft': {'opening': 27}}], 'moduleSnapshots': {'v': {'hash': 'original'}}}],
        'modules': [{'id': 'v', 'source': {'runtime': 'draft source'}}], 'models': [], 'charts': {'extra': ['x']}}


def test_controls_sample_by_simulation_time_and_archive_state():
    session = SimulationSession(compile_project(controlled()), .3, .25)
    try:
        first = session.initialize()
        assert first.variables['script.control.samples'] == 0
        frame = session.advance()
        assert frame.variables['script.control.samples'] == 3
        assert frame.variables['script.control.state.count'] == 3
        assert frame.variables['V1.param.opening_ratio'] == pytest.approx(.7)
        assert frame.variables['V1.mass_flow_kg_s'] < first.variables['V1.mass_flow_kg_s']
        assert session.advance().variables['script.control.samples'] == 3
        worker = session.scripts['control'].process
    finally:
        session.close()
    assert worker.poll() is not None


def test_failed_substep_reuses_proposal_and_commits_state_once(monkeypatch):
    session = SimulationSession(compile_project(controlled()), .1, .1)
    try:
        session.initialize()
        original = session._trial
        calls = []

        def retry(h):
            calls.append(h)
            if len(calls) == 1:
                raise ValueError('retry')
            return original(h)

        monkeypatch.setattr(session, 'stateful', True)
        monkeypatch.setattr(session, '_trial', retry)
        monkeypatch.setattr('fn_engine.solver._retryable', lambda error: True)
        frame = session.advance()
        assert len(calls) == 3  # rejected .1, accepted .05, remaining .05
        assert frame.variables['script.control.samples'] == 1
        assert frame.variables['script.control.state.count'] == 1
    finally:
        session.close()


@pytest.mark.parametrize('source,code', [
    (SOURCE.replace('ctx.read("V1.mass_flow_kg_s")', 'ctx.read("unknown")'), 'CONTROL_SCRIPT_ERROR'),
    (SOURCE.replace('0.4 + ctx.state["count"] * 0.1', '2'), 'CONTROL_WRITE_REJECTED'),
    (SOURCE.replace('ctx.log("sample")', 'raise RuntimeError("bad control")'), 'CONTROL_SCRIPT_ERROR'),
    (SOURCE.replace('ctx.log("sample")', 'ctx.state["bad"] = float("nan")'), 'CONTROL_SCRIPT_ERROR'),
    (SOURCE.replace('ctx.log("sample")', 'while True: pass'), 'CONTROL_TIMEOUT'),
])
def test_control_failures_preserve_accepted_history_and_report_line(source, code):
    with TestClient(create_app()) as client:
        result = client.post('/api/v1/runs', json=body(controlled(source, timeout_s=1))).json()
        assert result['status'] == 'failed', result
        assert result['frame']['diagnostics'][0]['code'] == code
        record = client.get('/api/v1/runs/' + result['run_id']).json()
        assert record['total_rows'] == 1
        rows = client.get('/api/v1/runs/' + result['run_id'] + '/history').json()['rows']
        assert len(rows) == 1 and rows[0]['time_s'] == 0
        if 'unknown' in source or 'bad control' in source:
            assert '第 ' in result['frame']['diagnostics'][0]['message']


def test_preview_is_real_but_does_not_enable_or_modify_project():
    p = controlled()
    p.control_scripts[0].enabled = False
    with TestClient(create_app()) as client:
        result = client.post('/api/v1/controls/preview', json={'project': p.model_dump(mode='json'),
            'script': p.control_scripts[0].model_dump(mode='json')})
    assert result.status_code == 200, result.text
    assert result.json()['writes'] == {'V1.param.opening_ratio': .5}
    assert result.json()['state'] == {'count': 1} and not result.json()['applied']
    assert not p.control_scripts[0].enabled


def test_declared_targets_own_parameters_and_steady_requires_disabling():
    session = SimulationSession(compile_project(controlled()), .1, .1)
    try:
        session.initialize()
        with pytest.raises(CompilationError, match='Python'):
            session.set_parameter('V1', 'opening_ratio', .2)
        with pytest.raises(CompilationError, match='Python'):
            session.write_variables({'V1.param.opening_ratio': .2})
    finally:
        session.close()
    with TestClient(create_app()) as client:
        result = client.post('/api/v1/runs', json=body(mode='steady')).json()
    assert result['frame']['diagnostics'][0]['code'] == 'CONTROL_DYNAMIC_REQUIRED'


def test_script_changes_pid_setpoint_before_its_next_sample():
    from fn_engine.examples import pid_example
    p = pid_example('temperature')
    source = '''def initialize(ctx): pass
def step(ctx, dt_s): ctx.write("controller.temperature.setpoint", 304.15)
def finalize(ctx): pass
'''
    p.control_scripts = [ControlScript(source=source, enabled=True, outputs=['controller.temperature.setpoint'])]
    session = SimulationSession(compile_project(p), .2, .1)
    try:
        session.initialize()
        frame = session.advance()
        assert frame.variables['controller.temperature.setpoint'] == 304.15
        assert frame.variables['script.control.samples'] == 1
        with pytest.raises(CompilationError, match='Python'):
            session.update_controller('temperature', 'setpoint', 300)
    finally:
        session.close()


def test_control_write_batch_rejects_every_value_if_one_is_out_of_range():
    from test_thermal import project
    p = project([('B1', 'source', {'pressure_pa': 250000}), ('V1', 'valve', {}), ('V2', 'valve', {}),
                 ('B2', 'source', {'pressure_pa': 120000})],
                [('B1:out0', 'V1:in0'), ('V1:out0', 'V2:in0'), ('V2:out0', 'B2:out0')])
    source = SOURCE.replace('ctx.log("sample")', 'ctx.write("V2.param.opening_ratio", 2)')
    p.control_scripts = [ControlScript(source=source, enabled=True, inputs=['V1.mass_flow_kg_s'],
        outputs=['V1.param.opening_ratio', 'V2.param.opening_ratio'])]
    session = SimulationSession(compile_project(p), .1, .1)
    try:
        session.initialize()
        before = session.network.parameters['V1']['opening_ratio']
        with pytest.raises(CompilationError):
            session.advance()
        assert session.network.parameters['V1']['opening_ratio'] == before
        assert session.scripts['control'].state['count'] == 0
    finally:
        session.close()


def test_invalid_or_conflicting_declarations_are_rejected():
    p = controlled()
    p.control_scripts.append(p.control_scripts[0].model_copy(update={'id': 'other'}))
    with pytest.raises(CompilationError, match='已由'):
        compile_project(p)
    p = controlled()
    p.control_scripts[0].outputs = ['V1.mass_flow_kg_s']
    with pytest.raises(CompilationError, match='不可写'):
        compile_project(p)


def test_workspace_roundtrip_revisions_and_stale_save_conflict(tmp_path):
    root = tmp_path / 'data'
    with TestClient(create_app(data_root=root)) as client:
        assert client.get('/api/v1/workspace').json()['revision'] == 0
        original = workspace()
        assert client.post('/api/v1/workspace', json={'data': original, 'expected_revision': 0}).status_code == 200
        response = client.post('/api/v1/workspace', json={'data': workspace(), 'expected_revision': 0})
        assert response.status_code == 409
        assert response.json()['detail']['code'] == 'WORKSPACE_CONFLICT'
        assert client.get('/api/v1/workspace').json()['data'] == original
    with TestClient(create_app(data_root=root)) as client:
        assert client.get('/api/v1/workspace').json()['data'] == original
        for revision in range(1, 7):
            assert client.post('/api/v1/workspace', json={'data': original, 'expected_revision': revision}).status_code == 200
        assert [r['revision'] for r in client.get('/api/v1/workspace/revisions').json()['revisions']] == [7, 6, 5, 4, 3]
        assert client.get('/api/v1/workspace?revision=1').status_code == 404


def test_storage_failed_transaction_does_not_claim_a_new_revision(tmp_path):
    store = WorkspaceStore(tmp_path)
    try:
        store.save_workspace(workspace(), 0)
        store.db.execute('PRAGMA query_only=ON')
        with pytest.raises(StorageError):
            store.save_workspace(workspace(), 1)
        assert store.workspace()['revision'] == 1
        store.db.execute('PRAGMA query_only=OFF')
        assert store.save_workspace(workspace(), 1)['revision'] == 2
        with pytest.raises(StorageError):
            WorkspaceStore(tmp_path)
    finally:
        store.close()


def test_completed_run_survives_restart_with_hashes_state_and_curves(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post('/api/v1/runs?background=true', json=body())
        run_id = response.json()['run_id']
        record = wait(client, run_id, lambda r: r['status'] == 'completed')
        rows = client.get(f'/api/v1/runs/{run_id}/history').json()
        summary = client.get(f'/api/v1/runs/{run_id}/overview').json()
        assert record['persisted_rows'] == 4 and record['persisted_at']
    with TestClient(create_app(data_root=tmp_path)) as client:
        restored = client.get(f'/api/v1/runs/{run_id}').json()
        assert restored == record
        assert client.get(f'/api/v1/runs/{run_id}/history').json() == rows
        assert client.get(f'/api/v1/runs/{run_id}/overview').json() == summary
        assert restored['request']['project']['control_scripts'][0]['content_hash']
        assert restored['frame']['variables']['script.control.state.count'] == 3
        assert client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'resume'}).status_code == 409
        assert client.post(f'/api/v1/runs/{run_id}/delete', json={}).status_code == 200
        assert client.get(f'/api/v1/runs/{run_id}').status_code == 404


def test_recovery_of_unfinished_archive_rejects_unconfirmed_commands(tmp_path):
    store = WorkspaceStore(tmp_path)
    record = {'id': 'r', 'status': 'running', 'mode': 'dynamic', 'request': body(),
        'frame': {'time_s': 1, 'status': 'running', 'valid': True},
        'events': [{'type': 'command', 'time_s': 1, 'command_id': 'write1', 'command_status': 'accepted'}]}
    store.save_run(record, [(0, {'time_s': 1, 'variables': {}})], 1)
    store.close()  # Equivalent persisted state to losing the service before a terminal write.
    store = WorkspaceStore(tmp_path)
    try:
        restored = store.record('r')
        assert restored['status'] == 'interrupted' and not restored['frame']['valid']
        assert restored['events'][-2]['command_status'] == 'rejected'
        assert restored['events'][-1]['type'] == 'interrupted'
        assert store.history('r', 0, 10)['rows'][0]['time_s'] == 1
    finally:
        store.close()


def test_archived_history_and_disk_retention_are_bounded(tmp_path):
    store = WorkspaceStore(tmp_path)
    try:
        record = {'id': 'r', 'status': 'completed', 'mode': 'dynamic', 'request': body()}
        store.save_run(record, list(enumerate({'time_s': i} for i in range(30))), 30, window=5)
        history = store.history('r', 0, 100)
        assert history['first_offset'] == 25 and history['truncated'] and len(history['rows']) == 5
        for index in range(21):
            store.save_run(record | {'id': str(index)}, total_rows=0)
        assert len(store.records()) == 20
        with pytest.raises(KeyError):
            store.record('r')
        assert store.db.execute('SELECT count(*) FROM frames').fetchone()[0] == 0
    finally:
        store.close()


def test_storage_failure_rejects_command_and_stops_run_with_diagnostic(tmp_path, monkeypatch):
    from fn_engine.jobs import RunManager
    from fn_engine.api import apply_scenario
    from fn_engine.models import RunCommand, RunRequest
    store = WorkspaceStore(tmp_path)
    manager = RunManager(apply_scenario, store)
    try:
        run_id = manager.submit(RunRequest.model_validate(body(valve_line(), start_paused=True)))
        deadline = time.monotonic() + 10
        while manager.snapshot(run_id)['status'] != 'paused':
            assert time.monotonic() < deadline
            time.sleep(.02)

        def fail(*args, **kwargs):
            raise StorageError('disk full')

        monkeypatch.setattr(store, 'save_run', fail)
        with pytest.raises(StorageError):
            manager.command(run_id, RunCommand(action='step', command_id='failed-save'))
        job = manager.jobs[run_id]
        assert not job.pending and 'failed-save' not in job.receipts
        # A disk fault during the next physical frame must terminate visibly.
        job.record['status'] = 'running'
        with manager.wake:
            manager.wake.notify_all()
        deadline = time.monotonic() + 10
        while manager.snapshot(run_id)['status'] != 'failed':
            assert time.monotonic() < deadline
            time.sleep(.02)
        assert manager.snapshot(run_id)['frame']['diagnostics'][0]['code'] == 'STORAGE_FAILED'
    finally:
        manager.close()
        store.close()


def test_stopped_workspace_backup_restores_to_another_directory(tmp_path):
    import shutil
    source, restored = tmp_path / 'source', tmp_path / 'restored'
    store = WorkspaceStore(source)
    store.save_workspace(workspace(), 0)
    store.save_run({'id': 'r', 'status': 'completed', 'mode': 'steady', 'request': body()},
                   [(0, {'time_s': 0, 'variables': {'value': 1.5}})], 1)
    store.close()
    shutil.copytree(source, restored)
    store = WorkspaceStore(restored)
    try:
        assert store.workspace()['data'] == workspace()
        assert store.record('r')['status'] == 'completed'
        assert store.history('r', 0, 1)['rows'][0]['variables']['value'] == 1.5
    finally:
        store.close()


def test_restart_applies_retention_to_newly_interrupted_runs(tmp_path):
    store = WorkspaceStore(tmp_path)
    for index in range(24):
        store.save_run({'id': str(index), 'status': 'paused', 'mode': 'dynamic', 'request': body()})
    store.close()
    store = WorkspaceStore(tmp_path)
    try:
        assert len(store.records()) == 20
        assert all(r['status'] == 'interrupted' for r in store.records())
    finally:
        store.close()
