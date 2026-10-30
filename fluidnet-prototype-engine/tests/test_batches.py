from copy import deepcopy
import csv
from io import StringIO
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.batch_store import BatchStore
from fn_engine import batch_store
from fn_engine.bridge import normalize_prototype_export
from fn_engine.compiler import compile_project
from fn_engine.models import ControlScript
from fn_engine.packages import package_ref
from fn_engine.runtime import module_content_hash, module_definition_hash
from fn_engine.solver import solve_steady
from fn_engine.storage import StorageError, WorkspaceStore
from test_continuous import wait
from test_heater import heater_prototype
from test_saved_project_runs import saved_workspace

ROOT = Path(__file__).resolve().parents[1]


def workspace():
    payload = json.loads((ROOT / 'tests/fixtures/prototype.json').read_text(encoding='utf-8'))
    payload.update(schema=1, models=[], charts={'extra': []})
    payload['projects'] = [payload['projects'][0]]
    payload['activeProject'] = payload['projects'][0]['id']
    payload['projects'][0]['scenarios'] = [
        {'id': 'low', 'name': '小开度', 'overrides': {'V1': {'opening': 20.}}},
        {'id': 'high', 'name': '大开度', 'overrides': {'V1': {'opening': 80.}}},
    ]
    return payload


def app(tmp_path):
    return create_app(data_root=tmp_path / 'data', module_storage_root=tmp_path / 'modules')


def save(client, payload=None):
    payload = workspace() if payload is None else payload
    response = client.post('/api/v1/workspace', json={'data': payload, 'expected_revision': 0})
    assert response.status_code == 200, response.text
    return payload['activeProject']


def definition(**updates):
    return {'revision': 1,
            'sweep': {'instance_id': 'V1', 'parameter_id': 'opening_ratio',
                      'range': {'start': 20, 'stop': 100, 'count': 5}},
            'variables': ['V1.mass_flow_kg_s', 'P1.shaft_power_w'],
            'options': {'mode': 'dynamic', 'duration_s': .2, 'dt_s': .1}, **updates}


def create(client, pid, body=None, request_id='batch-test'):
    body = definition() if body is None else body
    preview = client.post(f'/api/v1/projects/{pid}/batches/preview', json=body)
    assert preview.status_code == 200, preview.text
    response = client.post(f'/api/v1/projects/{pid}/batches', json={
        **body, 'request_id': request_id, 'name': '五档开度', 'preview_hash': preview.json()['preview_hash']})
    assert response.status_code == 201, response.text
    return response.json(), preview.json()


def finished(client, batch_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get('/api/v1/batches/' + batch_id)
        assert response.status_code == 200, response.text
        record = response.json()
        if record['status'] != 'running':
            return record
        time.sleep(.02)
    pytest.fail('批次未按时结束：' + str(record))


def start(client, batch_id):
    response = client.post(f'/api/v1/batches/{batch_id}/start')
    assert response.status_code == 200, response.text
    return finished(client, batch_id)


def test_preview_units_and_input_validation(tmp_path):
    with TestClient(app(tmp_path)) as client:
        pid = save(client)
        options = client.get(f'/api/v1/projects/{pid}/batch-options')
        assert options.status_code == 200, options.text
        opening = next(p for p in options.json()['parameters'] if p['instance_id'] == 'V1' and p['parameter_id'] == 'opening_ratio')
        assert opening['unit']['display_unit'] == '%'
        preview = client.post(f'/api/v1/projects/{pid}/batches/preview', json=definition())
        assert preview.status_code == 200, preview.text
        assert [i['scenario']['overrides']['V1']['opening_ratio'] for i in preview.json()['items']] == pytest.approx([.2, .4, .6, .8, 1.])
        for change in (
            {'values': [20, 101]}, {'values': [20, 20]}, {'values': [True]}, {'values': ['20']},
            {'values': list(range(21))}, {'range': {'start': 20, 'stop': 60, 'count': 1}},
            {'values': [20], 'range': {'start': 20, 'stop': 60, 'count': 3}},
        ):
            invalid = definition(sweep={'instance_id': 'V1', 'parameter_id': 'opening_ratio', **change})
            refused = client.post(f'/api/v1/projects/{pid}/batches/preview', json=invalid)
            assert refused.status_code == 422, refused.text
        malformed = json.dumps(definition()).replace('"start": 20', '"start": 1e999')
        assert client.post(f'/api/v1/projects/{pid}/batches/preview', content=malformed,
                           headers={'Content-Type': 'application/json'}).status_code == 422


def test_batch_matches_independent_runs_and_creation_is_idempotent(tmp_path):
    payload = workspace()
    with TestClient(app(tmp_path)) as client:
        pid = save(client, payload)
        batch, preview = create(client, pid)
        duplicate = client.post(f'/api/v1/projects/{pid}/batches', json={
            **definition(), 'request_id': 'batch-test', 'name': '五档开度', 'preview_hash': preview['preview_hash']})
        assert duplicate.status_code == 201 and duplicate.json()['id'] == batch['id']
        conflict = client.post(f'/api/v1/projects/{pid}/batches', json={
            **definition(), 'request_id': 'batch-test', 'name': '不同内容'})
        assert conflict.status_code == 409
        result = start(client, batch['id'])
        assert result['status'] == 'completed', result
        assert result['completed'] == 5
        assert len({item['run_id'] for item in result['items']}) == 5
        for value, item in zip([20, 40, 60, 80, 100], result['items'], strict=True):
            single = deepcopy(payload)
            valve = next(n for n in single['projects'][0]['pages'][0]['nodes'] if n['id'] == 'V1')
            valve['params']['opening'] = value
            frame = solve_steady(compile_project(normalize_prototype_export(single)))
            for key in definition()['variables']:
                assert item['values'][key] == pytest.approx(frame.variables[key], rel=1e-9)
            curve = client.get(f"/api/v1/batches/{batch['id']}/items/{item['id']}/curve",
                               params={'key': 'V1.mass_flow_kg_s'}).json()
            assert len(curve['points']) == 3
            assert curve['points'][-1][1] == pytest.approx(item['values']['V1.mass_flow_kg_s'])
        csv_response = client.get(f"/api/v1/batches/{batch['id']}/export")
        assert csv_response.status_code == 200
        rows = list(csv.reader(StringIO(csv_response.text.lstrip('\ufeff'))))
        assert len(rows) == 6
        assert [row[5] for row in rows[1:]] == ['completed'] * 5
        assert float(rows[1][-2]) == pytest.approx(result['items'][0]['values']['V1.mass_flow_kg_s'])


def test_batch_survives_project_revision_and_run_retention_and_restart(tmp_path):
    with TestClient(app(tmp_path)) as client:
        pid = save(client)
        batch, _ = create(client, pid)
        old_hash = batch['snapshot_hash']
        for number in range(7):
            saved = client.get('/api/v1/projects/' + pid).json()
            document = saved['document']
            next(n for n in document['project']['pages'][0]['nodes'] if n['id'] == 'V1')['params']['kv'] = 100 + number
            updated = client.post('/api/v1/projects/' + pid, json={'document': document, 'expected_revision': saved['revision']})
            assert updated.status_code == 200, updated.text
        assert client.get(f'/api/v1/projects/{pid}?revision=1').status_code == 404
        before = start(client, batch['id'])
        assert before['status'] == 'completed', before
        assert before['snapshot_hash'] == old_hash and before['project_revision'] == 1
        original_run = before['items'][0]['run_id']
        request = client.get('/api/v1/runs/' + original_run).json()['request']
        assert next(n for n in request['project']['instances'] if n['id'] == 'V1')['parameters']['kv_m3_h'] == 16.
        before_curve = client.get(f"/api/v1/batches/{batch['id']}/items/item-1/curve",
                                  params={'key': 'V1.mass_flow_kg_s'}).json()
        for _ in range(21):
            posted = client.post('/api/v1/runs?background=true', json=request)
            assert posted.status_code == 202, posted.json().get('detail', posted.status_code)
            wait(client, posted.json()['run_id'], lambda r: r['status'] in {'completed', 'failed'})
        assert client.get('/api/v1/runs/' + original_run).status_code == 404
    with TestClient(app(tmp_path)) as client:
        after = client.get('/api/v1/batches/' + batch['id'])
        assert after.status_code == 200, after.text
        assert after.json()['items'] == before['items']
        assert client.get(f"/api/v1/batches/{batch['id']}/items/item-1/curve",
                          params={'key': 'V1.mass_flow_kg_s'}).json() == before_curve
        assert client.post(f"/api/v1/batches/{batch['id']}/delete").json()['deleted']
        assert client.get('/api/v1/batches/' + batch['id']).status_code == 404


def test_heater_failed_case_keeps_diagnostics_and_does_not_abort_following_cases(tmp_path):
    with TestClient(app(tmp_path)) as client:
        pid = save(client, heater_prototype())
        body = definition(sweep={'instance_id': 'V1', 'parameter_id': 'opening_ratio', 'values': [50, 0, 80]},
                          variables=['H1.heat_w', 'H1.outlet_temperature_k'])
        batch, _ = create(client, pid, body)
        result = start(client, batch['id'])
        assert result['status'] == 'completed_with_errors', result
        assert [item['status'] for item in result['items']] == ['completed', 'failed', 'completed']
        assert result['items'][1]['diagnostics'][0]['code'] == 'NO_FLOW_HEAT'
        assert result['items'][0]['values']['H1.heat_w'] == pytest.approx(5000.)
        assert result['items'][2]['values']['H1.heat_w'] == pytest.approx(5000.)
        rows = list(csv.reader(StringIO(client.get(f"/api/v1/batches/{batch['id']}/export").text.lstrip('\ufeff'))))
        assert rows[2][5] == 'failed' and rows[2][-2:] == ['', '']


def test_existing_scenarios_can_be_selected_and_stale_preview_is_rejected(tmp_path):
    with TestClient(app(tmp_path)) as client:
        pid = save(client)
        body = definition(sweep=None, scenario_ids=['high', 'low'])
        batch, preview = create(client, pid, body)
        assert [item['source_scenario_id'] for item in preview['items']] == ['high', 'low']
        result = start(client, batch['id'])
        assert result['status'] == 'completed', result
        assert result['items'][0]['values']['V1.mass_flow_kg_s'] > result['items'][1]['values']['V1.mass_flow_kg_s']
        refusal = client.post(f'/api/v1/projects/{pid}/batches', json={
            **body, 'request_id': 'stale-preview', 'preview_hash': '0' * 64})
        assert refusal.status_code == 409


def test_storage_is_required_and_health_advertises_batches(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path / 'modules')) as client:
        assert not client.get('/api/v1/health').json()['capabilities']['scenario_batches']
        assert client.get('/api/v1/batches').status_code == 503
    with TestClient(app(tmp_path)) as client:
        assert client.get('/api/v1/health').json()['capabilities']['scenario_batches']


def active_item(client, batch_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        detail = client.get('/api/v1/batches/' + batch_id).json()
        running = next((item for item in detail['items'] if item['status'] == 'running' and item['run_id']), None)
        if running:
            return running
        time.sleep(.01)
    pytest.fail('批次没有启动工况：' + str(detail))


def test_cancel_remaining_and_stop_current_and_single_active_batch(tmp_path):
    with TestClient(app(tmp_path)) as client:
        pid = save(client)
        body = definition(options={'mode': 'dynamic', 'duration_s': 3600, 'dt_s': .1})
        batch, _ = create(client, pid, body)
        other, _ = create(client, pid, request_id='second-batch')
        assert client.post(f"/api/v1/batches/{batch['id']}/start").status_code == 200
        running = active_item(client, batch['id'])
        assert client.post(f"/api/v1/batches/{other['id']}/start").status_code == 409
        assert client.post(f"/api/v1/batches/{batch['id']}/delete").status_code == 409
        cancelled = client.post(f"/api/v1/batches/{batch['id']}/cancel").json()
        assert cancelled['cancelled'] == 4
        assert cancelled['items'][0]['status'] == 'running'
        stopped = client.post('/api/v1/runs/' + running['run_id'] + '/command', json={'action': 'stop'})
        assert stopped.status_code == 200, stopped.text
        result = finished(client, batch['id'])
        assert result['status'] == 'cancelled' and result['cancelled'] == 5
        assert client.post(f"/api/v1/batches/{batch['id']}/start").status_code == 409
        assert start(client, other['id'])['status'] == 'completed'


def test_service_restart_marks_interrupted_and_resume_creates_a_new_run(tmp_path):
    with TestClient(app(tmp_path)) as client:
        pid = save(client)
        batch, _ = create(client, pid, definition(options={'mode': 'dynamic', 'duration_s': 3600, 'dt_s': .1}))
        assert client.post(f"/api/v1/batches/{batch['id']}/start").status_code == 200
        previous = active_item(client, batch['id'])
    with TestClient(app(tmp_path)) as client:
        restored = client.get('/api/v1/batches/' + batch['id']).json()
        assert restored['status'] == 'interrupted', restored
        assert restored['items'][0]['status'] == 'interrupted'
        assert all(item['status'] == 'pending' for item in restored['items'][1:])
        assert client.post(f"/api/v1/batches/{batch['id']}/start").status_code == 200
        restarted = active_item(client, batch['id'])
        assert restarted['run_id'] != previous['run_id']
        assert restarted['attempts'][0]['run_id'] == previous['run_id']
        assert restarted['attempts'][0]['status'] == 'interrupted'
        assert len(restarted['attempts']) == 2
        assert client.post(f"/api/v1/batches/{batch['id']}/cancel").status_code == 200
        assert client.post('/api/v1/runs/' + restarted['run_id'] + '/command',
                           json={'action': 'stop'}).status_code == 200
        assert finished(client, batch['id'])['status'] == 'cancelled'


def test_dispatch_failure_preserves_completed_items_and_can_resume(tmp_path, monkeypatch):
    original = BatchStore.begin_next
    injected = False

    def fail_once(store, batch_id):
        nonlocal injected
        if not injected and store.summary(batch_id)['completed'] == 1:
            injected = True
            raise StorageError('测试：派发前存储失败')
        return original(store, batch_id)

    monkeypatch.setattr(BatchStore, 'begin_next', fail_once)
    with TestClient(app(tmp_path)) as client:
        pid = save(client)
        batch, _ = create(client, pid)
        failed = start(client, batch['id'])
        assert failed['status'] == 'failed' and failed['completed'] == 1, failed
        assert '存储失败' in failed['error']
        first = deepcopy(failed['items'][0])
        resumed = start(client, batch['id'])
        assert resumed['status'] == 'completed', resumed
        assert resumed['completed'] == 5
        assert resumed['items'][0] == first


def test_heater_sweep_converts_kw_and_csv_uses_declared_units(tmp_path):
    with TestClient(app(tmp_path)) as client:
        pid = save(client, heater_prototype())
        body = definition(sweep={'instance_id': 'H1', 'parameter_id': 'heat_input_w', 'values': [2, 5]},
                          variables=['H1.heat_w'])
        batch, preview = create(client, pid, body)
        assert [item['scenario']['overrides']['H1']['heat_input_w'] for item in preview['items']] == [2000., 5000.]
        result = start(client, batch['id'])
        assert result['status'] == 'completed', result
        assert [item['values']['H1.heat_w'] for item in result['items']] == pytest.approx([2000., 5000.])
        unit = result['variables'][0]['unit']
        assert unit['canonical_unit'] == 'W'
        rows = list(csv.reader(StringIO(client.get(f"/api/v1/batches/{batch['id']}/export").text.lstrip('\ufeff'))))
        assert float(rows[1][-1]) == pytest.approx(2000 / unit['display_scale'] + unit['display_offset'])


def test_module_and_control_sources_are_frozen_before_later_edits(tmp_path):
    payload, module = saved_workspace()
    old_script = payload['projects'][0]['controlScripts'][0]['source']
    with TestClient(app(tmp_path)) as client:
        pid = save(client, payload)
        setup = client.get(f'/api/v1/projects/{pid}/batch-options').json()
        parameter = next(p for p in setup['parameters'] if p['instance_id'] == 'V1' and p['parameter_id'] == 'opening_ratio')
        unit = parameter['unit']
        body = definition(sweep={'instance_id': 'V1', 'parameter_id': 'opening_ratio',
                                'values': [value / unit['display_scale'] + unit['display_offset'] for value in (.2, .4)]},
                          variables=['V1.param.opening_ratio'])
        batch, _ = create(client, pid, body)
        stored = client.get('/api/v1/projects/' + pid).json()
        document = stored['document']
        changed = module.model_copy(deep=True)
        changed.version += 1
        changed.source['runtime'] += '\n# next module version\n'
        changed.content_hash = module_content_hash(changed)
        changed.definition_hash = module_definition_hash(changed)
        document['modules'] = [changed.model_dump(mode='json') if item['id'] == module.id else item
                               for item in document['modules']]
        document['project']['moduleSnapshots'][module.id] = changed.model_dump(mode='json')
        valve = next(n for page in document['project']['pages'] for n in page['nodes'] if n['id'] == 'V1')
        valve['package'] = package_ref(changed).model_dump(mode='json')
        document['project']['controlScripts'] = [
            ControlScript(id='counter', enabled=True, source=old_script.replace('+= 1', '+= 9')).model_dump(mode='json')]
        assert client.post('/api/v1/projects/' + pid, json={
            'document': document, 'expected_revision': stored['revision']}).status_code == 200
        result = start(client, batch['id'])
        assert result['status'] == 'completed', result
        for item in result['items']:
            run = client.get('/api/v1/runs/' + item['run_id']).json()
            frozen = next(m for m in run['request']['project']['modules'] if m['id'] == module.id)
            assert frozen['content_hash'] == module.content_hash
            assert frozen['version'] == module.version
            assert run['request']['project']['control_scripts'][0]['source'] == old_script


def test_terminal_storage_failure_stops_dispatch_and_retries_from_frozen_input(tmp_path, monkeypatch):
    original = WorkspaceStore.save_run
    injected = False

    def failed_write(store, record, *args, **kwargs):
        nonlocal injected
        if record['status'] == 'completed' and not injected:
            injected = True
            raise StorageError('测试：最终结果无法落盘')
        return original(store, record, *args, **kwargs)

    monkeypatch.setattr(WorkspaceStore, 'save_run', failed_write)
    with TestClient(app(tmp_path)) as client:
        pid = save(client)
        batch, _ = create(client, pid)
        failed = start(client, batch['id'])
        assert failed['status'] == 'failed', failed
        assert failed['completed'] == 0
        assert failed['items'][0]['status'] == 'interrupted'
        assert all(item['status'] == 'pending' for item in failed['items'][1:])
        assert '落盘' in failed['error']
        result = start(client, batch['id'])
        assert result['status'] == 'completed', result
        assert len(result['items'][0]['attempts']) == 2


def test_terminal_run_and_batch_result_are_atomic_and_curves_are_bounded(tmp_path, monkeypatch):
    from fn_engine.api import apply_scenario
    from fn_engine.batches import BatchService
    from fn_engine.jobs import RunManager
    from fn_engine.batch_models import BatchCreateRequest

    storage = WorkspaceStore(tmp_path / 'data')
    manager = RunManager(apply_scenario, storage)
    service = BatchService(storage, manager)
    try:
        payload = workspace()
        storage.save_workspace(payload, 0)
        body = definition(sweep={'instance_id': 'V1', 'parameter_id': 'opening_ratio', 'values': [20]})
        created = service.create(payload['activeProject'], BatchCreateRequest(**body, request_id='atomic-result'))
        service.store.start(created['id'])
        item_id, _, run_id = service.store.begin_next(created['id'])
        rows = [{'time_s': float(i), 'variables': {'V1.mass_flow_kg_s': float(i), 'P1.shaft_power_w': 1000.},
                 'metrics': {}, 'diagnostics': [], 'valid': True} for i in range(3001)]
        record = {'id': run_id, 'status': 'running', 'request': {'project': {'name': '存档事务测试'}},
                  'frame': rows[-1], 'events': []}
        storage.save_run(record, [(3000, rows[-1])], total_rows=3001)
        original_pack = batch_store.pack

        def fail_curve(value):
            if isinstance(value, dict) and 'points' in value:
                raise OSError('测试：曲线写入失败')
            return original_pack(value)

        monkeypatch.setattr(batch_store, 'pack', fail_curve)
        record = {**record, 'status': 'completed'}
        with pytest.raises(StorageError, match='曲线写入失败'):
            storage.save_run(record, total_rows=3001, overview={'rows': rows, 'stride': 1})
        assert storage.record(run_id)['status'] == 'running'
        assert service.store.item_state(created['id'], item_id) == 'running'
        monkeypatch.setattr(batch_store, 'pack', original_pack)
        storage.save_run(record, total_rows=3001, overview={'rows': rows, 'stride': 1})
        assert service.store.detail(created['id'])['status'] == 'completed'
        curve = service.store.curve(created['id'], item_id, 'V1.mass_flow_kg_s')
        assert len(curve['points']) <= 2000
        assert curve['points'][0] == [0., 0.]
        assert curve['points'][-1] == [3000., 3000.]
        assert curve['total_rows'] == 3001
    finally:
        service.close()
        manager.close()
        storage.close()


def test_version_two_workspace_migrates_without_changing_saved_project(tmp_path):
    root = tmp_path / 'data'
    storage = WorkspaceStore(root)
    payload = workspace()
    storage.save_workspace(payload, 0)
    before = storage.project(payload['activeProject'])
    with storage.transaction() as db:
        db.execute('DROP TABLE batch_items')
        db.execute('DROP TABLE batches')
        db.execute('PRAGMA user_version=2')
    storage.close()
    restored = WorkspaceStore(root)
    try:
        assert restored.db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert restored.project(payload['activeProject']) == before
        assert BatchStore(restored).list()['batches'] == []
    finally:
        restored.close()
