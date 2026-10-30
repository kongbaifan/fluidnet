"""Drive a saved FluidNet project over HTTP and WebSocket, without opening Studio.

Environment: FLUIDNET_URL (default http://127.0.0.1:8798), FLUIDNET_PROJECT_ID,
FLUIDNET_TOKEN (when authentication is enabled), optional FLUIDNET_REVISION,
FLUIDNET_SCENARIO, FLUIDNET_VARIABLES (comma-separated frame keys), and
FLUIDNET_WRITE_VALUES (JSON object of canonical runtime variable keys/values).

Run `python examples/external_clients/saved_project.py` against `serve --headless`.
HTTP uses the standard library; WebSocket uses the engine's pinned `websockets`
dependency. No token is created or
printed. Start with a saved dynamic project; writes are sent only when supplied.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from websockets.sync.client import connect


BASE = os.environ.get('FLUIDNET_URL', 'http://127.0.0.1:8798').rstrip('/')
TOKEN = os.environ.get('FLUIDNET_TOKEN', '')
HEADERS = {'Authorization': 'Bearer ' + TOKEN} if TOKEN else {}


def request(path, body=None):
    data = None if body is None else json.dumps(body, allow_nan=False).encode('utf-8')
    headers = {'Content-Type': 'application/json', **HEADERS}
    try:
        with urlopen(Request(BASE + '/api/v1' + path, data=data, headers=headers), timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f'HTTP {error.code}: {error.read().decode("utf-8", errors="replace")}') from None


def await_record(run_id, statuses, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = request('/runs/' + run_id)
        if record['status'] == 'failed':
            raise RuntimeError(json.dumps(record.get('frame'), ensure_ascii=False))
        if record['status'] in statuses:
            return record
        time.sleep(.1)
    raise TimeoutError(f'Run did not reach {sorted(statuses)}')


def await_receipt(run_id, receipt, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = receipt.get('command_status')
        if status == 'applied':
            return receipt
        if status == 'rejected':
            raise RuntimeError(json.dumps(receipt, ensure_ascii=False))
        time.sleep(.1)
        events = request(f'/runs/{run_id}/events')['events']
        receipt = next((event for event in reversed(events)
                        if event.get('command_id') == receipt['command_id']), receipt)
    raise TimeoutError('Command was accepted but did not receive an applied/rejected receipt')


def command(run_id, action):
    receipt = request(f'/runs/{run_id}/command', {'action': action, 'command_id': uuid.uuid4().hex})
    return await_receipt(run_id, receipt)


def next_frame(stream, after=-1):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        value = json.loads(stream.recv(timeout=max(.01, deadline - time.monotonic())))
        if value['type'] == 'frame' and value['sequence'] > after:
            print(json.dumps({'sequence': value['sequence'], 'time_s': value['time_s'],
                              'values': dict(list(value['values'].items())[:8])}, ensure_ascii=False))
            return value
        if value['type'] in {'error', 'end'}:
            raise RuntimeError(json.dumps(value, ensure_ascii=False))
    raise TimeoutError('No new subscribed frame')


def main():
    project_id = os.environ.get('FLUIDNET_PROJECT_ID')
    if not project_id:
        raise ValueError('Set FLUIDNET_PROJECT_ID to an existing saved project ID')
    body = {'mode': 'dynamic', 'duration_s': None, 'dt_s': .1, 'start_paused': True,
            'execution_mode': 'realtime'}
    if os.environ.get('FLUIDNET_REVISION'):
        body['revision'] = int(os.environ['FLUIDNET_REVISION'])
    if os.environ.get('FLUIDNET_SCENARIO'):
        body['scenario_id'] = os.environ['FLUIDNET_SCENARIO']
    writes = json.loads(os.environ.get('FLUIDNET_WRITE_VALUES', '{}'))
    if not isinstance(writes, dict):
        raise ValueError('FLUIDNET_WRITE_VALUES must be a JSON object')
    run_id = None
    stopped = False
    try:
        created = request('/projects/' + quote(project_id, safe='') + '/runs', body)
        run_id = created['run_id']
        record = await_record(run_id, {'paused'})
        print(json.dumps({'run_id': run_id, 'project_revision': record['request']['project_revision']}))
        parts = urlsplit(BASE)
        query = urlencode({'keys': os.environ['FLUIDNET_VARIABLES']}) if os.environ.get('FLUIDNET_VARIABLES') else ''
        url = urlunsplit(('wss' if parts.scheme == 'https' else 'ws', parts.netloc,
                         parts.path + f'/api/v1/runs/{run_id}/stream', query, ''))
        with connect(url, additional_headers=HEADERS, open_timeout=15, close_timeout=2) as stream:
            first = next_frame(stream)
            if writes:
                receipt = request(f'/runs/{run_id}/variables', {
                    'values': writes, 'command_id': uuid.uuid4().hex, 'wait_s': 2})
                await_receipt(run_id, receipt)
            command(run_id, 'resume')
            second = next_frame(stream, first['sequence'])
            command(run_id, 'pause')
            await_record(run_id, {'paused'})
            command(run_id, 'resume')
            next_frame(stream, second['sequence'])
            command(run_id, 'stop')
            final = await_record(run_id, {'cancelled'})
            stopped = True
            print(json.dumps({'status': final['status'], 'project_revision': final['request']['project_revision'],
                              'final_time_s': final['frame']['time_s']}))
    finally:
        if run_id and not stopped:
            try:
                request(f'/runs/{run_id}/command', {'action': 'stop', 'command_id': uuid.uuid4().hex})
            except (OSError, RuntimeError):
                pass


if __name__ == '__main__':
    main()
