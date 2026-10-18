"""Trend history (RunRequest.history='trend'): key frames keep everything, the rest only the curves."""
import json
import math
import time

import pytest
from fastapi.testclient import TestClient

import fn_engine.jobs as jobs
from fn_engine.api import apply_scenario, create_app
from fn_engine.jobs import RunManager
from fn_engine.models import RunRequest
from fn_engine.storage import WorkspaceStore
from test_run_control import custom_project
from test_thermal import project, prototype

TREND = ['P1.mass_flow_kg_s', 'V1.mass_flow_kg_s', 'V2.mass_flow_kg_s', 'P1.out0.pressure_pa', 'P1.out0.temperature_k']


def valve_line():
    return project([('B1', 'source', {'pressure_pa': 250000}), ('V1', 'valve', {}), ('L1', 'pipe', {}),
                    ('B2', 'source', {'pressure_pa': 120000})],
                   [('B1:out0', 'V1:in0'), ('V1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')])


def wait_record(client, run_id, predicate, timeout=60.):
    end = time.monotonic() + timeout
    record = None
    while time.monotonic() < end:
        record = client.get(f'/api/v1/runs/{run_id}').json()
        if predicate(record):
            return record
        time.sleep(.01)
    raise AssertionError(record)


def test_archive_writes_are_batched_and_consistent_after_restart(tmp_path, monkeypatch):
    """Per-frame archives go through bounded batches, and a stopped workspace reloads them."""
    # A wide coalescing window makes the batching deterministic even on a fast machine.
    monkeypatch.setattr(jobs, 'ARCHIVE_COALESCE_S', 0.05)
    calls = []
    original = WorkspaceStore.save_run

    def counting(store, record, rows=(), total_rows=0, window=2001, overview=None):
        calls.append(len(rows))
        return original(store, record, rows, total_rows, window, overview)

    monkeypatch.setattr(WorkspaceStore, 'save_run', counting)
    body = {'project': valve_line().model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': 30., 'dt_s': .05}
    with TestClient(create_app(data_root=tmp_path)) as client:
        run_id = client.post('/api/v1/runs?background=true', json=body).json()['run_id']
        record = wait_record(client, run_id, lambda r: r['status'] == 'completed')
        live_history = client.get(f'/api/v1/runs/{run_id}/history').json()
        live_overview = client.get(f'/api/v1/runs/{run_id}/overview').json()
    assert record['total_rows'] == 601
    # `status=completed` is only visible after the terminal write-through committed.
    assert record['persisted_rows'] == record['total_rows'] == 601 and record['persisted_at']
    # Batched: fewer transactions than frames, and most batches carry several rows.
    assert len(calls) < record['total_rows'] // 2
    assert max(calls) > 1

    # A stopped workspace is the archive of record: the same window/overview must reload.
    store = WorkspaceStore(tmp_path)
    try:
        restored = store.record(run_id)
        history = store.history(run_id, 0, 2001)
        overview = store.overview(run_id)
    finally:
        store.close()
    assert restored['status'] == 'completed' and restored['persisted_rows'] == 601
    assert history['total_rows'] == 601 and len(history['rows']) == 601
    assert [row['sequence'] for row in history['rows']] == [row['sequence'] for row in live_history['rows']]
    assert overview['total_rows'] == 601 and len(overview['rows']) == len(live_overview['rows']) == 601
    assert overview['rows'][-1]['time_s'] == live_overview['rows'][-1]['time_s'] == pytest.approx(30.)


def test_slow_archive_write_does_not_block_run_snapshots(tmp_path):
    """A 50 ms archive transaction must not stall threads that only need in-memory state.

    Before the writer thread existed, every frame's `save_run` ran under the global `wake`
    lock, so `snapshot()` waited about one disk transaction per call.
    """
    store = WorkspaceStore(tmp_path)
    manager = RunManager(apply_scenario, store)
    original = store.save_run

    def slow(record, rows=(), total_rows=0, window=2001, overview=None):
        time.sleep(.05)
        return original(record, rows, total_rows, window, overview)

    store.save_run = slow
    try:
        body = {'project': valve_line().model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': 300., 'dt_s': .1}
        run_id = manager.submit(RunRequest.model_validate(body))
        deadline = time.monotonic() + 10
        while manager.jobs[run_id].record['status'] != 'running':
            assert time.monotonic() < deadline
            time.sleep(.005)
        latencies = []
        end = time.monotonic() + .8
        while time.monotonic() < end:
            started = time.perf_counter()
            manager.snapshot(run_id)
            latencies.append(time.perf_counter() - started)
            time.sleep(.002)
    finally:
        store.save_run = original
        manager.close()
        store.close()
    assert len(latencies) > 50
    assert max(latencies) < .04


def run(client, project, duration_s, dt_s, history='full', trend=()):
    body = {'project': project.model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': duration_s, 'dt_s': dt_s,
            'history': history, 'trend_variables': list(trend)}
    created = client.post('/api/v1/runs', json=body)
    assert created.status_code == 201, created.text
    record = created.json()
    rows = client.get(f"/api/v1/runs/{record['run_id']}/history").json()['rows']
    return record, rows


def key_indices(rows):
    return [index for index, row in enumerate(rows) if row['full']]


def test_trend_history_of_2001_frames_is_small_and_keeps_key_frames():
    with TestClient(create_app()) as client:
        record, rows = run(client, prototype('water-net'), 200., .1, 'trend', TREND)
    assert record['status'] == 'completed' and len(rows) == 2001
    assert len(json.dumps(rows)) < 3e6
    keys = key_indices(rows)
    assert keys[0] == 0 and keys[-1] == 2000 and len(keys) <= 51
    every = math.ceil(2001 / 50)
    assert set(keys) == {i for i in range(2001) if i % every == 0} | {2000}
    full_keys = set(rows[0]['variables'])
    assert all(set(rows[i]['variables']) == full_keys for i in keys)
    slim = [row for row in rows if not row['full']]
    assert slim and all(set(row['variables']) == set(TREND) for row in slim)
    # Metrics are kept on every frame (they differ per frame: warm starts need fewer iterations).
    assert all(set(row['metrics']) == set(rows[0]['metrics']) for row in slim)


def test_trend_values_match_full_history_frame_by_frame():
    with TestClient(create_app()) as client:
        _, full = run(client, prototype('heat-loop'), 10., .1)
        _, trend = run(client, prototype('heat-loop'), 10., .1, 'trend', ['P1.mass_flow_kg_s', 'HX1.ch1.outlet_temperature_k'])
    assert len(full) == len(trend) == 101
    for a, b in zip(full, trend):
        assert a['time_s'] == b['time_s']
        for key in ('P1.mass_flow_kg_s', 'HX1.ch1.outlet_temperature_k'):
            assert b['variables'][key] == pytest.approx(a['variables'][key], rel=1e-12, abs=1e-12)
        if b['full']:
            assert b['variables'] == a['variables']


def test_unknown_trend_variable_fails_the_run():
    with TestClient(create_app()) as client:
        record, rows = run(client, prototype('water-net'), 1., .1, 'trend', ['P1.mass_flow_kg_s', 'nope.x'])
    assert record['status'] == 'failed' and rows == []
    assert record['frame']['diagnostics'][0]['code'] == 'TREND_VARIABLE_UNKNOWN'


def test_trend_is_ignored_in_steady_mode():
    with TestClient(create_app()) as client:
        body = {'project': prototype('water-net').model_dump(mode='json'), 'history': 'trend', 'trend_variables': ['nope.x']}
        record = client.post('/api/v1/runs', json=body).json()
    assert record['status'] == 'completed' and record['frame']['full'] is True


def test_module_state_survives_on_slim_frames(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        _, rows = run(client, custom_project(), 6., .1, 'trend', ['V1.mass_flow_kg_s'])
    slim = [row for row in rows if not row['full']]
    assert slim
    for row in slim:
        assert set(row['variables']) == {'V1.mass_flow_kg_s', 'V1.state.throughput_kg', 'V1.state.commit_count'}
    counts = [row['variables']['V1.state.commit_count'] for row in rows[1:]]
    assert counts == list(range(1, len(rows)))


