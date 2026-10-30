"""Run the shipped clients against a real authenticated HTTP/WebSocket server."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time

from fastapi.testclient import TestClient
import httpx
import psutil
import pytest
import uvicorn

from fn_engine.api import create_app
from fn_engine.auth import AuthConfig, TokenStore
from test_saved_project_runs import saved_workspace


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('language', ['python', 'javascript'])
def test_external_client_controls_saved_project_and_preserves_archive(tmp_path, language):
    if language == 'javascript':
        node = shutil.which('node')
        if not node:
            pytest.skip('JavaScript client requires Node 24+')
        version = subprocess.check_output([node, '--version'], text=True, timeout=10)
        if int(version.lstrip('v').split('.')[0]) < 24:
            pytest.skip('JavaScript client requires Node 24+')
        command = [node, 'examples/external_clients/saved_project.mjs']
    else:
        command = [sys.executable, 'examples/external_clients/saved_project.py']

    data, _ = saved_workspace()
    tokens = TokenStore(tmp_path / 'tokens.json')
    _, token = tokens.create('external-client-test', 'control')
    options = {'data_root': tmp_path / 'data', 'module_storage_root': tmp_path / 'modules',
               'auth': AuthConfig(required=True, store=tokens)}
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(**options), log_level='error', lifespan='on'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started, 'Headless test server did not start'
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False,
                          headers={'Authorization': 'Bearer ' + token}, timeout=15) as setup:
            assert setup.get('/api/v1/health').json()['mode'] == 'headless'
            assert setup.get('/').status_code == 404
            setup.post('/api/v1/workspace', json={'data': data, 'expected_revision': 0}).raise_for_status()
        environment = {**os.environ, 'FLUIDNET_URL': f'http://127.0.0.1:{port}', 'FLUIDNET_TOKEN': token,
            'FLUIDNET_PROJECT_ID': 'saved-water', 'FLUIDNET_REVISION': '1', 'FLUIDNET_SCENARIO': 'throttle',
            'FLUIDNET_VARIABLES': 'V2.param.opening_ratio,V2.mass_flow_kg_s',
            'FLUIDNET_WRITE_VALUES': json.dumps({'V2.param.opening_ratio': .6})}
        result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=75)
        assert result.returncode == 0, result.stderr
        output = [json.loads(line) for line in result.stdout.splitlines()]
        run_id = output[0]['run_id']
        assert output[0]['project_revision'] == 1
        assert output[-1]['status'] == 'cancelled'
        frames = [item for item in output if 'sequence' in item]
        assert len(frames) == 3
        assert frames[0]['values']['V2.param.opening_ratio'] == .55
        assert frames[-1]['values']['V2.param.opening_ratio'] == .6
        assert frames[-1]['sequence'] > frames[0]['sequence']
        # The saved fixture runs both a Python module and a Python controller.
        workers = []
        for child in psutil.Process().children(recursive=True):
            try:
                if 'fn_engine.worker' in child.cmdline():
                    workers.append(child.pid)
            except psutil.Error:
                pass
        assert not workers, f'Stopped client left module Workers: {workers}'
    finally:
        server.should_exit = True
        thread.join(15)
        listener.close()
        assert not thread.is_alive(), 'Headless test server did not stop'

    with TestClient(create_app(**options)) as restarted:
        record = restarted.get('/api/v1/runs/' + run_id,
            headers={'Authorization': 'Bearer ' + token}).json()
        assert record['status'] == 'cancelled'
        assert record['request']['project_revision'] == 1
        assert record['frame']['variables']['V2.param.opening_ratio'] == .6
        commands = [event for event in record['events'] if event.get('command_status') == 'accepted']
        assert [event['command']['action'] for event in commands] == ['write', 'resume', 'pause', 'resume', 'stop']
        applied = {event['command_id'] for event in record['events'] if event.get('command_status') == 'applied'}
        assert {event['command_id'] for event in commands} == applied
