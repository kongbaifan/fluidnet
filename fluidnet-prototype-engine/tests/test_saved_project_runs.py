from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.auth import AuthConfig, TokenStore
from fn_engine.models import ControlScript, RunOptions, RunRequest, SavedProjectRunRequest
from fn_engine.packages import load_module_package, package_ref
from fn_engine.runtime import module_content_hash, module_definition_hash
from fn_engine.storage import StorageError, WorkspaceStore
from test_continuous import wait


ROOT = Path(__file__).resolve().parents[1]
SOURCE = '''def initialize(ctx):
    ctx.state['samples'] = 0

def step(ctx, dt_s):
    ctx.state['samples'] += 1

def finalize(ctx):
    pass
'''


def saved_workspace():
    data = json.loads((ROOT / 'tests/fixtures/prototype.json').read_text(encoding='utf-8'))
    data.update(schema=1, models=[], charts={'extra': []})
    data['projects'] = [data['projects'][0]]
    project = data['projects'][0]
    project['id'] = data['activeProject'] = 'saved-water'
    module = load_module_package(ROOT / 'modules/programmable_valve_sdk')
    data['modules'].append(module.model_dump(mode='json'))
    project['moduleSnapshots'] = {module.id: module.model_dump(mode='json')}
    valve = next(node for page in project['pages'] for node in page['nodes'] if node['id'] == 'V1')
    valve.update(moduleId=module.id, params={'opening_ratio': .5, 'kv_m3_h': 10.},
                 draft={'opening_ratio': .99, 'kv_m3_h': 99.}, package=package_ref(module).model_dump(mode='json'))
    project['controlScripts'] = [ControlScript(id='counter', source=SOURCE, enabled=True).model_dump(mode='json')]
    project['scenarios'] = [{'id': 'throttle', 'name': 'Throttle', 'overrides': {'V1': {'opening_ratio': .25}}}]
    return data, module


def submit(client, **options):
    response = client.post('/api/v1/projects/saved-water/runs', json={
        'mode': 'dynamic', 'duration_s': .2, 'dt_s': .1, **options})
    assert response.status_code == 202, response.text
    record = wait(client, response.json()['run_id'], lambda value: value['status'] in {'completed', 'failed'})
    assert record['status'] == 'completed', record.get('frame')
    return record


def test_saved_run_pins_actual_revision_module_and_script_snapshots(tmp_path):
    data, original = saved_workspace()
    with TestClient(create_app(data_root=tmp_path)) as client:
        client.post('/api/v1/workspace', json={'data': data, 'expected_revision': 0}).raise_for_status()
        document = client.get('/api/v1/projects/saved-water').json()['document']
        changed = original.model_copy(deep=True)
        changed.version += 1
        changed.source['runtime'] += '\n# second saved module revision\n'
        changed.content_hash = module_content_hash(changed)
        changed.definition_hash = module_definition_hash(changed)
        document['modules'] = [changed.model_dump(mode='json') if module['id'] == changed.id else module
                               for module in document['modules']]
        project = document['project']
        project['moduleSnapshots'][changed.id] = changed.model_dump(mode='json')
        valve = next(node for page in project['pages'] for node in page['nodes'] if node['id'] == 'V1')
        valve['package'] = package_ref(changed).model_dump(mode='json')
        project['controlScripts'] = [ControlScript(id='counter', enabled=True,
            source=SOURCE.replace("+= 1", "+= 2")).model_dump(mode='json')]
        project['projectRevision'] = 999  # Opaque UI metadata cannot forge the recorded revision.
        client.post('/api/v1/projects/saved-water', json={'document': document, 'expected_revision': 1}).raise_for_status()

        old = submit(client, revision=1, scenario_id='throttle')
        latest = submit(client)
        assert old['request']['project_revision'] == 1
        assert latest['request']['project_revision'] == 2
        old_module = next(module for module in old['request']['project']['modules'] if module['id'] == original.id)
        new_module = next(module for module in latest['request']['project']['modules'] if module['id'] == original.id)
        assert old_module['content_hash'] == original.content_hash
        assert new_module['content_hash'] == changed.content_hash
        assert old_module['version'] == original.version and new_module['version'] == changed.version
        assert old['request']['project']['control_scripts'][0]['source'] == SOURCE
        assert latest['request']['project']['control_scripts'][0]['source'] == SOURCE.replace('+= 1', '+= 2')
        assert old['frame']['variables']['script.counter.state.samples'] == 2
        assert latest['frame']['variables']['script.counter.state.samples'] == 4
        assert old['frame']['variables']['V1.param.opening_ratio'] == .25
        assert latest['frame']['variables']['V1.param.opening_ratio'] == .5
        assert latest['frame']['variables']['V1.param.kv_m3_h'] == 10.  # Never applies pending editor values.
        latest_id = latest['id']
    with TestClient(create_app(data_root=tmp_path)) as restarted:
        archive = restarted.get('/api/v1/runs/' + latest_id).json()
        assert archive['request'] == latest['request']
        assert archive['status'] == 'completed'


def test_saved_run_uses_revision_captured_before_a_concurrent_save(tmp_path, monkeypatch):
    data, _ = saved_workspace()
    original = WorkspaceStore.project
    with TestClient(create_app(data_root=tmp_path)) as client:
        client.post('/api/v1/workspace', json={'data': data, 'expected_revision': 0}).raise_for_status()
        saved_once = False

        def read_then_save(store, project_id, revision=None):
            nonlocal saved_once
            captured = original(store, project_id, revision)
            if not saved_once:
                saved_once = True
                document = deepcopy(captured['document'])
                document['project']['name'] = 'Saved while the run request was normalizing'
                store.save_project(document, captured['revision'])
            return captured

        monkeypatch.setattr(WorkspaceStore, 'project', read_then_save)
        record = submit(client)
        assert record['request']['project_revision'] == 1
        assert record['request']['project']['name'] == data['projects'][0]['name']
        assert client.get('/api/v1/projects/saved-water').json()['revision'] == 2


@pytest.mark.parametrize('extra', [{'project_revision': 100}, {'project': {}}, {'revision': 0},
                                 {'mode': 'steady', 'duration_s': None}, {'dt_s': 0}])
def test_saved_run_rejects_forged_snapshot_and_invalid_options(tmp_path, extra):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post('/api/v1/projects/missing/runs', json=extra)
        assert response.status_code == 422
        assert client.get('/api/v1/runs').json()['runs'] == []


def test_saved_run_reports_missing_storage_project_revision_and_invalid_document(tmp_path, monkeypatch):
    with TestClient(create_app()) as client:
        assert client.post('/api/v1/projects/missing/runs', json={}).status_code == 503
    data, _ = saved_workspace()
    with TestClient(create_app(data_root=tmp_path)) as client:
        assert client.post('/api/v1/projects/missing/runs', json={}).status_code == 404
        client.post('/api/v1/workspace', json={'data': data, 'expected_revision': 0}).raise_for_status()
        assert client.post('/api/v1/projects/saved-water/runs', json={'revision': 99}).status_code == 404
        document = client.get('/api/v1/projects/saved-water').json()['document']
        document['project']['pages'][0]['nodes'][0]['moduleId'] = 'not_saved'
        client.post('/api/v1/projects/saved-water', json={'document': document, 'expected_revision': 1}).raise_for_status()
        assert client.post('/api/v1/projects/saved-water/runs', json={}).status_code == 422
        assert client.get('/api/v1/runs').json()['runs'] == []

        def unavailable(*args, **kwargs):
            raise StorageError('read failed')
        monkeypatch.setattr(WorkspaceStore, 'project', unavailable)
        response = client.post('/api/v1/projects/saved-water/runs', json={})
        assert response.status_code == 507 and response.json()['detail']['code'] == 'STORAGE_FAILED'


def test_saved_run_unknown_scenario_uses_existing_background_failure_contract(tmp_path):
    data, _ = saved_workspace()
    with TestClient(create_app(data_root=tmp_path)) as client:
        client.post('/api/v1/workspace', json={'data': data, 'expected_revision': 0}).raise_for_status()
        response = client.post('/api/v1/projects/saved-water/runs', json={'scenario_id': 'missing'})
        assert response.status_code == 202
        record = wait(client, response.json()['run_id'], lambda item: item['status'] == 'failed')
        assert any(item['code'] == 'SCENARIO_NOT_FOUND' for item in record['frame']['diagnostics'])
        assert record['request']['project_revision'] == 1


@pytest.mark.parametrize('field', ['solver', 'solverOptions'])
def test_saved_run_rejects_malformed_saved_editor_metadata(tmp_path, field):
    data, _ = saved_workspace()
    with TestClient(create_app(data_root=tmp_path)) as client:
        client.post('/api/v1/workspace', json={'data': data, 'expected_revision': 0}).raise_for_status()
        document = client.get('/api/v1/projects/saved-water').json()['document']
        # Storage deliberately accepts unfinished editor documents. A run must
        # report invalid nested metadata as a client error, without creating a job.
        document['project'][field] = []
        client.post('/api/v1/projects/saved-water', json={
            'document': document, 'expected_revision': 1}).raise_for_status()
        response = client.post('/api/v1/projects/saved-water/runs', json={})
        assert response.status_code == 422, response.text
        assert client.get('/api/v1/runs').json()['runs'] == []


def test_saved_run_obeys_existing_read_and_control_permissions(tmp_path):
    tokens = TokenStore(tmp_path / 'tokens.json')
    _, read = tokens.create('read', 'read')
    _, control = tokens.create('control', 'control')
    data, _ = saved_workspace()
    headers = lambda value: {'Authorization': 'Bearer ' + value}
    with TestClient(create_app(data_root=tmp_path / 'data', auth=AuthConfig(required=True, store=tokens))) as client:
        client.post('/api/v1/workspace', json={'data': data, 'expected_revision': 0}, headers=headers(control)).raise_for_status()
        assert client.post('/api/v1/projects/saved-water/runs', json={}).status_code == 401
        assert client.post('/api/v1/projects/saved-water/runs', json={}, headers=headers(read)).status_code == 403
        response = client.post('/api/v1/projects/saved-water/runs', json={
            'mode': 'dynamic', 'duration_s': .1}, headers=headers(control))
        assert response.status_code == 202


def test_saved_and_explicit_requests_share_the_same_run_option_contract():
    fields = set(RunOptions.model_fields)
    assert set(SavedProjectRunRequest.model_fields) == fields | {'revision'}
    assert set(RunRequest.model_fields) == fields | {'project', 'project_revision'}
    assert SavedProjectRunRequest().model_dump(exclude={'revision'}) == RunOptions().model_dump()
