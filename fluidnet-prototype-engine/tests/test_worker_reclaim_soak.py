"""Compressed 24 h soak path: Worker reclaim after pause/step/resume cycles, backups and stop.

`scripts/soak_workspace.py` only sends commands every 60 s and backs up every 300 s, so its short
smoke runs never exercised those paths. This test replays the same sequence quickly and checks every
child process except the console host.

The 2026-10-15 24 h run reported 「停止后仍残留 Worker」 because it counted that console host: it was
launched hidden in the background, which gives python a `conhost.exe` child for its whole lifetime
(3 children from the first sample = 2 Workers + conhost). The soak script now counts only
`fn_engine.worker` processes; `test_soak_counts_only_engine_workers` pins that.
"""
import sys
import time
from pathlib import Path

import psutil
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.models import ControlScript

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from acceptance_cases import parallel  # noqa: E402

POLL_CAP = 600
CYCLES = 5


# A hidden background launch attaches a console host that lives as long as python itself; it is
# not ours to reclaim (that is what turned the 24 h run into a false 「残留 Worker」).
CONSOLE_HOSTS = {'conhost.exe'}


def children():
    found = {}
    for child in psutil.Process().children(recursive=True):
        try:
            if child.is_running() and child.name().lower() not in CONSOLE_HOSTS:
                found[child.pid] = child
        except psutil.Error:
            continue
    return found


def wait_children_exit(timeout_s=30.):
    deadline = time.monotonic() + timeout_s
    while children() and time.monotonic() < deadline:
        time.sleep(.05)
    return children()


def soak_request():
    model = parallel(python_valve=True)
    model.control_scripts = [ControlScript(id='soak', enabled=True, sample_s=1., inputs=['V1.mass_flow_kg_s'],
        outputs=['P1.param.speed_ratio'], source='''def initialize(ctx): ctx.state["samples"] = 0
def step(ctx, dt_s):
    ctx.read("V1.mass_flow_kg_s")
    ctx.write("P1.param.speed_ratio", 0.6 + 0.1 * (int(ctx.time_s) % 2))
    ctx.state["samples"] += 1
def finalize(ctx): pass
''')]
    return {'project': model.model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': None, 'dt_s': 1.,
            'execution_mode': 'realtime', 'speed_ratio': 20., 'history_window': 100, 'history': 'trend',
            'trend_variables': ['V1.mass_flow_kg_s']}


def wait_status(client, run_id, wanted):
    for _ in range(POLL_CAP):
        record = client.get(f'/api/v1/runs/{run_id}').json()
        assert record['status'] != 'failed', record['frame']
        if record['status'] in wanted and record['frame']:
            return record
        time.sleep(.05)
    raise AssertionError(f'{run_id} 没有进入 {wanted}')


def apply(client, run_id, action):
    receipt = client.post(f'/api/v1/runs/{run_id}/command', json={'action': action})
    assert receipt.status_code == 200, receipt.text
    key = receipt.json()['command_id']
    for _ in range(POLL_CAP):
        events = client.get(f'/api/v1/runs/{run_id}/events').json()['events']
        latest = next((e for e in reversed(events) if e['command_id'] == key), None)
        if latest and latest['command_status'] == 'applied':
            return
        assert not (latest and latest['command_status'] == 'rejected'), latest
        time.sleep(.05)
    raise AssertionError(f'{action} 没有生效')


def test_soak_cycle_stop_and_reopen_leave_no_child_process(tmp_path):
    assert not children(), f'测试开始前已有子进程：{children()}'
    app = dict(data_root=tmp_path / 'workspace', module_storage_root=tmp_path / 'modules')
    with TestClient(create_app(**app)) as client:
        response = client.post('/api/v1/runs?background=true', json=soak_request())
        assert response.status_code == 202, response.text
        run_id = response.json()['run_id']
        wait_status(client, run_id, {'running'})
        workers = children()
        assert len(workers) == 2, f'预期阀门与控制脚本各 1 个 Worker：{workers}'
        for cycle in range(CYCLES):
            apply(client, run_id, 'pause')
            apply(client, run_id, 'step')
            wait_status(client, run_id, {'paused'})
            apply(client, run_id, 'resume')
            if cycle == 2:
                backup = client.post('/api/v1/workspace/backup', json={})
                assert backup.status_code == 200, backup.text
            # Same Workers stay in use; a cycle must not spawn replacements.
            assert children().keys() == workers.keys(), f'第 {cycle + 1} 轮后 Worker 变化：{children()}'
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'stop'}).raise_for_status()
        wait_status(client, run_id, {'cancelled'})
        assert not wait_children_exit(), f'停止后仍残留子进程：{children()}'
    with TestClient(create_app(**app)) as client:
        assert client.get(f'/api/v1/runs/{run_id}').json()['status'] in {'cancelled', 'interrupted'}
    assert not wait_children_exit(), f'重开应用后仍残留子进程：{children()}'


class FakeChild:
    def __init__(self, name, cmdline):
        self._name, self._cmdline = name, cmdline

    def is_running(self):
        return True

    def name(self):
        return self._name

    def cmdline(self):
        return self._cmdline


class FakeProcess:
    def __init__(self, children):
        self._children = children

    def children(self, recursive=False):
        return self._children


def test_soak_counts_only_engine_workers(monkeypatch):
    # The soak script pins BLAS threads at import; keep that out of the rest of the session.
    for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        monkeypatch.setenv(variable, '1')
    from soak_workspace import child_processes
    conhost = FakeChild('conhost.exe', [r'\??\C:\Windows\system32\conhost.exe', '0xffffffff', '-ForceV1'])
    worker = FakeChild('python.exe', ['python', '-m', 'fn_engine.worker'])
    workers, others = child_processes(FakeProcess([conhost, worker]))
    assert workers == [worker] and others == [conhost]
    # The 2026-10-15 failure shape: only the console host is left after stop.
    assert child_processes(FakeProcess([conhost])) == ([], [conhost])
