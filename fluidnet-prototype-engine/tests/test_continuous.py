import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import fn_engine.jobs as jobs
from fn_engine.api import apply_scenario, create_app
from fn_engine.compiler import compile_project
from fn_engine.models import RunCommand, RunRequest
from fn_engine.simulation import SimulationSession
from test_thermal import project


def valve_line():
    return project([('B1', 'source', {'pressure_pa': 250000}), ('V1', 'valve', {}), ('L1', 'pipe', {}),
                    ('B2', 'source', {'pressure_pa': 120000})],
                   [('B1:out0', 'V1:in0'), ('V1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')])


def request(**changes):
    return {'project': valve_line().model_dump(mode='json'), 'mode': 'dynamic', 'dt_s': .1} | changes


def wait(client, run_id, predicate, timeout=60.):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        record = client.get('/api/v1/runs/' + run_id).json()
        if predicate(record):
            return record
        time.sleep(.02)
    pytest.fail(str(record))


def test_only_dynamic_runs_may_omit_the_duration():
    with pytest.raises(ValidationError):
        RunRequest(project=valve_line(), mode='steady', duration_s=None)
    assert RunRequest(project=valve_line(), mode='dynamic', duration_s=None).frame_count() is None
    assert RunRequest(project=valve_line(), mode='dynamic', duration_s=2.2, dt_s=.1).frame_count() == 23


@pytest.mark.parametrize('body', [{'duration_s': None}, {'duration_s': 300.}])
def test_synchronous_runs_stay_limited_to_2001_frames(body):
    with TestClient(create_app()) as client:
        response = client.post('/api/v1/runs', json=request(**body))
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'RUN_TOO_LONG'


def test_long_background_run_keeps_a_window_and_a_decimated_overview(monkeypatch):
    monkeypatch.setattr(jobs, 'OVERVIEW_POINTS', 50)
    with TestClient(create_app()) as client:
        run_id = client.post('/api/v1/runs?background=true', json=request(duration_s=300., history_window=100)).json()['run_id']
        record = wait(client, run_id, lambda r: r['status'] == 'completed')
        assert record['total_rows'] == 3001 and record['frame']['time_s'] == pytest.approx(300.)
        history = client.get(f'/api/v1/runs/{run_id}/history').json()
        assert history['truncated'] and history['first_offset'] == history['offset'] == 2901
        assert [row['sequence'] for row in history['rows']] == list(range(2901, 3001))
        tail = client.get(f'/api/v1/runs/{run_id}/history?offset=2990').json()
        assert not tail['truncated'] and len(tail['rows']) == 11
        overview = client.get(f'/api/v1/runs/{run_id}/overview').json()
    stride = overview['stride']
    assert stride == 64 and overview['total_rows'] == 3001
    sequences = [row['sequence'] for row in overview['rows']]
    assert sequences == list(range(0, 3001, stride)) + [3000]
    assert [row['time_s'] for row in overview['rows']] == pytest.approx([s * .1 for s in sequences])


def test_continuous_run_advances_until_stopped_with_bounded_trend_history():
    with TestClient(create_app()) as client:
        body = request(duration_s=None, history_window=20, history='trend', trend_variables=['V1.mass_flow_kg_s'])
        run_id = client.post('/api/v1/runs?background=true', json=body).json()['run_id']
        record = wait(client, run_id, lambda r: r['total_rows'] > 80)
        assert record['status'] == 'running'
        history = client.get(f'/api/v1/runs/{run_id}/history').json()
        assert len(history['rows']) == 20
        # Key frames every ceil(window / 50) = 1 frame: a window this small keeps every frame full.
        assert all(row['full'] for row in history['rows'])
        stop = client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'stop'})
        assert stop.status_code == 200 and stop.json()['progress'] == 0
        record = wait(client, run_id, lambda r: r['status'] == 'cancelled')
        final = client.get(f'/api/v1/runs/{run_id}/history?offset={record["total_rows"] - 1}').json()['rows'][-1]
        assert final['sequence'] == record['total_rows'] - 1 and final['full']


def test_trend_history_in_a_continuous_run_has_key_frames_per_window():
    with TestClient(create_app()) as client:
        body = request(duration_s=None, history_window=200, history='trend', trend_variables=['V1.mass_flow_kg_s'])
        run_id = client.post('/api/v1/runs?background=true', json=body).json()['run_id']
        wait(client, run_id, lambda r: r['total_rows'] > 30)
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'pause'})
        wait(client, run_id, lambda r: r['status'] == 'paused')
        rows = client.get(f'/api/v1/runs/{run_id}/history').json()['rows'][:-1]
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'stop'})
    every = 4  # ceil(200 / 50)
    assert [row['full'] for row in rows] == [row['sequence'] % every == 0 for row in rows]
    assert all(set(row['variables']) == {'V1.mass_flow_kg_s'} for row in rows if not row['full'])


@pytest.mark.parametrize('changes, code', [({'selected_variables': ['nope']}, 'TREND_VARIABLE_UNKNOWN'),
                                           ({'history': 'trend', 'trend_variables': ['nope']}, 'TREND_VARIABLE_UNKNOWN')])
def test_a_background_run_rejecting_its_first_frame_reports_why(changes, code):
    with TestClient(create_app()) as client:
        run_id = client.post('/api/v1/runs?background=true', json=request(duration_s=1., **changes)).json()['run_id']
        record = wait(client, run_id, lambda r: r['status'] == 'failed')
    assert [d['code'] for d in record['frame']['diagnostics']] == [code]
    assert record['events'][-1]['type'] == 'failed'


def test_events_and_receipts_stay_bounded_on_a_long_run(monkeypatch):
    monkeypatch.setattr(jobs, 'EVENT_LIMIT', 10)
    monkeypatch.setattr(jobs, 'RECEIPT_LIMIT', 5)
    manager = jobs.RunManager(apply_scenario)
    try:
        run_id = manager.submit(RunRequest.model_validate(request(start_paused=True)))
        for n in range(12):
            command = RunCommand(action='write', values={'V1.param.opening_ratio': .5 + n / 100})
            key = manager.command(run_id, command)['command_id']
            assert manager.wait_receipt(run_id, key, 10.)['command_status'] == 'applied'
        job = manager.jobs[run_id]
        events = manager.snapshot(run_id)['events']
        assert len(events) == 10 and events[-1]['command_status'] == 'applied'
        assert len(job.receipts) == 5 and key in job.receipts
    finally:
        manager.close()


def test_health_reports_continuous_runs_and_refprop_as_capabilities():
    with TestClient(create_app()) as client:
        health = client.get('/api/v1/health').json()
    assert health['capabilities']['continuous_runs'] is True
    assert set(health['capabilities']['refprop']) == {'installed', 'source', 'path', 'version'}
    assert health['history_window_max'] == 20001 and health['overview_points'] == 2000


def test_session_holds_only_recent_frames_and_does_not_drift():
    session = SimulationSession(compile_project(valve_line()), None, .1, keep=8)
    try:
        frames = [session.advance() for _ in range(1001)]
        assert not session.done and len(session.frames) == 8 and session.sequence == 1001
        assert [f.time_s for f in frames] == [i * .1 for i in range(1001)]
        assert [f.sequence for f in session.frames] == list(range(993, 1001))
    finally:
        session.close()


def test_sessions_returning_every_frame_need_a_finite_duration():
    network = compile_project(valve_line())
    for duration in (None, 300.):
        with pytest.raises(ValueError):
            SimulationSession(network, duration, .1)
