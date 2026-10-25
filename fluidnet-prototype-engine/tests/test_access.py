"""Variables API, run stream, bearer tokens and the token CLI."""
import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fn_engine import cli
from fn_engine.api import create_app
from fn_engine.auth import AuthConfig, TokenStore, WS_PROTOCOL, is_loopback, resolve_auth
from fn_engine.examples import pid_example


def level_run(client, **changes):
    body = {'project': pid_example('level').model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': None, 'dt_s': .5,
            'start_paused': True} | changes
    run_id = client.post('/api/v1/runs?background=true', json=body).json()['run_id']
    for _ in range(500):
        record = client.get('/api/v1/runs/' + run_id).json()
        if record['status'] in ('paused', 'running') and record['frame']:
            return run_id
        time.sleep(.01)
    pytest.fail(str(record))


def step(client, run_id):
    sequence = client.get('/api/v1/runs/' + run_id).json()['frame']['sequence']
    key = client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'step'}).json()['command_id']
    for _ in range(500):
        events = client.get(f'/api/v1/runs/{run_id}/events').json()['events']
        if any(e.get('command_id') == key and e.get('command_status') == 'applied' for e in events):
            record = client.get('/api/v1/runs/' + run_id).json()
            # The receipt acknowledges scheduling; the paused run can still expose
            # its old frame while advance() is executing outside the manager lock.
            if record['status'] == 'paused' and record['frame']['sequence'] > sequence:
                return record
        time.sleep(.01)
    pytest.fail('step not applied')


def test_read_selected_variables_of_the_latest_frame():
    with TestClient(create_app()) as client:
        run_id = level_run(client)
        data = client.get(f'/api/v1/runs/{run_id}/variables?keys=T1.state.level_m,controller.level.output').json()
        assert set(data['values']) == {'T1.state.level_m', 'controller.level.output'}
        assert data['values']['T1.state.level_m'] == pytest.approx(1.)
        assert data['time_s'] == 0 and data['sequence'] == 0 and data['status'] == 'paused'
        everything = client.get(f'/api/v1/runs/{run_id}/variables').json()['values']
        assert len(everything) > 50 and 'V1.param.opening_ratio' in everything
        unknown = client.get(f'/api/v1/runs/{run_id}/variables?keys=T1.state.level_m,T1.nope')
        assert unknown.status_code == 422 and unknown.json()['detail']['keys'] == ['T1.nope']
        assert client.get('/api/v1/runs/nope/variables').status_code == 404
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'stop'})


def test_batch_write_applies_together_at_one_frame_boundary():
    with TestClient(create_app()) as client:
        run_id = level_run(client)
        written = client.post(f'/api/v1/runs/{run_id}/variables', json={'wait_s': 5, 'values': {
            'V2.param.opening_ratio': .3, 'controller.level.setpoint': 1.2}}).json()
        assert written['command_status'] == 'applied' and written['applied_time_s'] == 0
        events = client.get(f'/api/v1/runs/{run_id}/events').json()['events']
        applied = next(e for e in events if e.get('command_id') == written['command_id'] and e['command_status'] == 'applied')
        assert applied['parameter_revision'] == 1  # two values, one revision
        record = step(client, run_id)
        values = client.get(f'/api/v1/runs/{run_id}/variables?keys=V2.param.opening_ratio,controller.level.setpoint').json()
        assert values['values'] == {'V2.param.opening_ratio': .3, 'controller.level.setpoint': 1.2}
        assert record['frame']['time_s'] == .5
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'stop'})


@pytest.mark.parametrize('values, code', [
    ({'V2.param.opening_ratio': .3, 'V2.param.kv_m3_h': 9.}, 'PARAMETER_NOT_RUNTIME'),
    ({'V2.param.opening_ratio': .3, 'V1.param.opening_ratio': .4}, 'PARAMETER_CONTROLLED'),
    ({'V2.param.opening_ratio': .3, 'controller.level.kp': 1.}, 'PID_COMMAND_INVALID'),
    ({'V2.param.opening_ratio': .3, 'T1.state.level_m': 2.}, 'VARIABLE_NOT_WRITABLE'),
    ({'V2.param.opening_ratio': 1.5}, 'PARAMETER_RANGE'),
])
def test_a_rejected_entry_rejects_the_whole_batch(values, code):
    with TestClient(create_app()) as client:
        run_id = level_run(client)
        written = client.post(f'/api/v1/runs/{run_id}/variables', json={'wait_s': 5, 'values': values}).json()
        assert written['command_status'] == 'rejected'
        events = client.get(f'/api/v1/runs/{run_id}/events').json()['events']
        assert any(e.get('command_id') == written['command_id'] and e['command_status'] == 'rejected' for e in events)
        expected = {'PARAMETER_NOT_RUNTIME': '不允许运行时修改', 'PARAMETER_CONTROLLED': '由 PID level 控制',
                    'PID_COMMAND_INVALID': '可调字段', 'VARIABLE_NOT_WRITABLE': '不能写入', 'PARAMETER_RANGE': '超出范围'}
        assert expected[code] in written['message']
        after = client.get(f'/api/v1/runs/{run_id}/variables?keys=V2.param.opening_ratio').json()
        assert after['values']['V2.param.opening_ratio'] == .5 and after['parameter_revision'] == 0
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'stop'})


def test_stream_pushes_new_frames_then_ends():
    with TestClient(create_app()) as client:
        body = {'project': pid_example('level').model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': 20., 'dt_s': .5,
                'execution_mode': 'realtime', 'speed_ratio': 20}
        run_id = client.post('/api/v1/runs?background=true', json=body).json()['run_id']
        with client.websocket_connect(f'/api/v1/runs/{run_id}/stream?keys=T1.state.level_m&interval_ms=10') as ws:
            messages = []
            while True:
                message = ws.receive_json()
                messages.append(message)
                if message['type'] == 'end':
                    break
    frames = [m for m in messages if m['type'] == 'frame']
    assert messages[-1] == {'type': 'end', 'status': 'completed'}
    assert len(frames) > 5 and all(set(f['values']) == {'T1.state.level_m'} for f in frames)
    sequences = [f['sequence'] for f in frames]
    assert sequences == sorted(set(sequences)) and frames[-1]['time_s'] == pytest.approx(20.)


def test_stream_rejects_unknown_runs_and_keys():
    with TestClient(create_app()) as client:
        with client.websocket_connect('/api/v1/runs/nope/stream') as ws:
            assert ws.receive_json()['code'] == 'RUN_NOT_FOUND'
        run_id = level_run(client)
        with client.websocket_connect(f'/api/v1/runs/{run_id}/stream?keys=T1.nope') as ws:
            assert ws.receive_json() == {'type': 'error', 'code': 'VARIABLE_UNKNOWN', 'keys': ['T1.nope']}
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'stop'})


@pytest.fixture
def secured(tmp_path):
    store = TokenStore(tmp_path / 'tokens.json')
    _, reader = store.create('dashboard', 'read')
    record, controller = store.create('plc', 'control')
    with TestClient(create_app(auth=AuthConfig(required=True, store=store), cors_origins=['http://twin.local'])) as client:
        yield client, store, reader, controller, record


def header(secret):
    return {'Authorization': 'Bearer ' + secret}


def test_tokens_gate_the_api_by_scope(secured):
    client, store, reader, controller, record = secured
    health = client.get('/api/v1/health')
    assert health.status_code == 200 and health.json()['auth'] == {'required': True}
    assert client.get('/').status_code in (200, 404)  # static files are not behind the token
    assert client.get('/api/v1/catalog').status_code == 401
    assert client.get('/api/v1/catalog', headers=header('fn_wrong')).status_code == 401
    assert client.get('/api/v1/catalog', headers=header(reader)).status_code == 200
    project = pid_example('level').model_dump(mode='json')
    denied = client.post('/api/v1/projects/validate', json=project, headers=header(reader))
    assert denied.status_code == 403 and denied.json()['detail']['code'] == 'AUTH_SCOPE'
    assert client.post('/api/v1/projects/validate', json=project, headers=header(controller)).json()['valid']
    store.revoke(record['id'])
    assert client.post('/api/v1/projects/validate', json=project, headers=header(controller)).status_code == 401


def test_stream_accepts_the_token_as_header_or_subprotocol(secured):
    client, _, reader, controller, _ = secured
    body = {'project': pid_example('level').model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': None, 'dt_s': .5,
            'start_paused': True}
    run_id = client.post('/api/v1/runs?background=true', json=body, headers=header(controller)).json()['run_id']
    with client.websocket_connect(f'/api/v1/runs/{run_id}/stream') as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4401
    with client.websocket_connect(f'/api/v1/runs/{run_id}/stream?keys=T1.state.level_m', headers=header(reader)) as ws:
        assert ws.receive_json()['type'] == 'frame'
    with client.websocket_connect(f'/api/v1/runs/{run_id}/stream?keys=T1.state.level_m', subprotocols=[WS_PROTOCOL + reader]) as ws:
        assert ws.accepted_subprotocol == WS_PROTOCOL + reader
        assert ws.receive_json()['type'] == 'frame'
    client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'stop'}, headers=header(controller))


def test_cors_preflight_for_configured_origins(secured):
    client = secured[0]
    response = client.options('/api/v1/catalog', headers={'Origin': 'http://twin.local', 'Access-Control-Request-Method': 'GET',
                                                          'Access-Control-Request-Headers': 'Authorization'})
    assert response.status_code == 200 and response.headers['access-control-allow-origin'] == 'http://twin.local'
    other = client.options('/api/v1/catalog', headers={'Origin': 'http://evil.local', 'Access-Control-Request-Method': 'GET'})
    assert 'access-control-allow-origin' not in other.headers


def test_token_file_keeps_only_hashes(tmp_path):
    store = TokenStore(tmp_path / 'tokens.json')
    record, secret = store.create('twin', 'read')
    text = (tmp_path / 'tokens.json').read_text(encoding='utf-8')
    assert secret not in text and record['id'] in text and 'sha256' in text
    assert store.verify(secret)['name'] == 'twin' and store.verify(secret + 'x') is None
    assert 'sha256' not in store.list()[0]
    with pytest.raises(ValueError):
        store.create('x', 'admin')


@pytest.mark.parametrize('host, local', [('127.0.0.1', True), ('localhost', True), ('::1', True), ('0.0.0.0', False),
                                         ('192.168.1.5', False), ('example.org', False)])
def test_loopback_detection(host, local):
    assert is_loopback(host) is local


def test_serve_refuses_unsafe_configurations(tmp_path):
    empty = TokenStore(tmp_path / 'tokens.json')
    assert not resolve_auth('auto', '127.0.0.1', empty).required
    with pytest.raises(ValueError, match='token create'):
        resolve_auth('auto', '0.0.0.0', empty)
    with pytest.raises(ValueError, match='不能关闭认证'):
        resolve_auth('off', '0.0.0.0', empty)
    with pytest.raises(ValueError, match='token create'):
        resolve_auth('required', '127.0.0.1', empty)
    empty.create('x', 'control')
    assert resolve_auth('auto', '0.0.0.0', empty).required
    assert resolve_auth('required', '127.0.0.1', empty).required


def test_token_cli_create_list_revoke(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('FLUIDNET_TOKEN_FILE', str(tmp_path / 'tokens.json'))
    cli.main(['token', 'create', '三维看板', '--scope', 'read'])
    secret = capsys.readouterr().out.strip().splitlines()[-1]
    assert secret.startswith('fn_') and TokenStore(tmp_path / 'tokens.json').verify(secret)['scope'] == 'read'
    cli.main(['token', 'list'])
    listing = capsys.readouterr().out
    token_id = listing.split()[0]
    assert '三维看板' in listing and secret not in listing
    cli.main(['token', 'revoke', token_id])
    assert TokenStore(tmp_path / 'tokens.json').list() == []
    with pytest.raises(SystemExit):
        cli.main(['token', 'revoke', token_id])
    assert json.loads((tmp_path / 'tokens.json').read_text(encoding='utf-8')) == {'tokens': []}
