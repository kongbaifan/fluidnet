"""Trend history (RunRequest.history='trend'): key frames keep everything, the rest only the curves."""
import json
import math

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from test_run_control import custom_project
from test_thermal import prototype

TREND = ['P1.mass_flow_kg_s', 'V1.mass_flow_kg_s', 'V2.mass_flow_kg_s', 'P1.out0.pressure_pa', 'P1.out0.temperature_k']


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


