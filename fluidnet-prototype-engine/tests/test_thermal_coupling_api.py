"""Background control and selected-key WebSocket delivery of coupled results."""
from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from test_continuous import wait


def test_coupled_background_write_and_step_publish_selected_websocket_values(tmp_path):
    keys = ['coupling.HX1.heat_w', 'coupling.HX1.mass_flow_kg_s',
            'HX_W.out0.temperature_k', 'LP1.state.temperature_k', 'WV1.param.opening_ratio']
    with TestClient(create_app(data_root=tmp_path / 'data', module_storage_root=tmp_path / 'modules')) as client:
        example = client.get('/api/v1/examples/thermal-coupling')
        example.raise_for_status()
        submitted = client.post('/api/v1/runs?background=true', json={
            'project': example.json(), 'mode': 'dynamic', 'duration_s': 2., 'dt_s': 1.,
            'start_paused': True, 'selected_variables': keys,
        })
        assert submitted.status_code == 202, submitted.text
        run_id = submitted.json()['run_id']
        wait(client, run_id, lambda record: record['status'] in {'paused', 'failed'})
        path = f'/api/v1/runs/{run_id}'
        with client.websocket_connect(path + '/stream?keys=' + ','.join(keys)) as stream:
            first = stream.receive_json()
            assert first['type'] == 'frame' and first['status'] == 'paused', first
            assert set(first['values']) == set(keys)
            assert first['values']['WV1.param.opening_ratio'] == .8
            assert first['values']['coupling.HX1.heat_w'] > 0.

            response = client.post(path + '/variables', json={
                'values': {'WV1.param.opening_ratio': .4}, 'command_id': 'coupled-valve', 'wait_s': 2,
            })
            assert response.status_code == 200, response.text
            assert response.json()['command_status'] == 'applied'
            client.post(path + '/command', json={'action': 'step'}).raise_for_status()
            record = wait(client, run_id, lambda item: item['status'] == 'failed' or (
                item['status'] == 'paused' and item['frame']['time_s'] == 1.))
            assert record['status'] == 'paused', record['frame']
            while True:
                updated = stream.receive_json()
                assert updated['type'] == 'frame', updated
                if updated['time_s'] == 1.:
                    break
            assert set(updated['values']) == set(keys)
            assert updated['sequence'] > first['sequence']
            assert updated['parameter_revision'] == 1
            assert updated['values']['WV1.param.opening_ratio'] == .4
            assert updated['values']['coupling.HX1.mass_flow_kg_s'] < first['values']['coupling.HX1.mass_flow_kg_s']
            read = client.get(path + '/variables', params={'keys': ','.join(keys)})
            assert read.status_code == 200
            assert read.json()['values'] == pytest.approx(updated['values'])

            client.post(path + '/command', json={'action': 'stop'}).raise_for_status()
            final = wait(client, run_id, lambda item: item['status'] in {'cancelled', 'failed'})
            assert final['status'] == 'cancelled'
            while True:
                ending = stream.receive_json()
                if ending['type'] == 'end':
                    assert ending['status'] == 'cancelled'
                    break
                assert ending['type'] == 'frame', ending
