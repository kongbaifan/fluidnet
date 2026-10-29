import csv
from io import StringIO

from fastapi.testclient import TestClient
import pytest

from fn_engine.air_examples import air_example
from fn_engine.api import create_app
from fn_engine.auth import AuthConfig,TokenStore
from fn_engine.batches import observation_choices


def test_property_modes_and_grid():
    with TestClient(create_app()) as client:
        response=client.post('/api/v1/air/properties',json={'input_mode':'ptrh','pressure_pa':101325,'temperature_k':299.15,'relative_humidity':.5})
        assert response.status_code==200,response.text
        state=response.json()['state']
        back=client.post('/api/v1/air/properties',json={'input_mode':'phw','pressure_pa':101325,
            'enthalpy_j_kg_dry_air':state['enthalpy_j_kg_dry_air'],'humidity_ratio_kg_kg':state['humidity_ratio_kg_kg']})
        assert back.json()['state']['temperature_k']==pytest.approx(299.15,abs=1e-5)
        assert client.post('/api/v1/air/properties',json={'input_mode':'ptrh','pressure_pa':101325,'temperature_k':299.15,
                                                        'relative_humidity':.5,'humidity_ratio_kg_kg':.008}).status_code==422
        grid=client.get('/api/v1/air/psychrometric-grid').json()
        assert len(grid['lines'])==10
        assert all(point['humidity_ratio_kg_kg']<=.03 for line in grid['lines'] for segment in line['segments'] for point in segment)


def test_frozen_catalog_reports_and_restart(tmp_path,monkeypatch):
    project=air_example('air-coil-wet')
    project.name='<script>alert(1)</script>'
    with TestClient(create_app(data_root=tmp_path)) as client:
        preview=client.post('/api/v1/air/variables/preview',json=project.model_dump(mode='json'))
        assert preview.status_code==200,preview.text
        created=client.post('/api/v1/runs',json={'project':project.model_dump(mode='json'),'mode':'dynamic','duration_s':1.,'dt_s':1.})
        assert created.status_code==201,created.text
        assert created.json()['status']=='completed',created.text
        run_id=created.json()['run_id']
        record=client.get('/api/v1/runs/'+run_id).json()
        metadata=record['air_metadata']
        catalog=client.get(f'/api/v1/runs/{run_id}/air-variables').json()['variables']
        assert catalog==metadata['variable_catalog']==preview.json()['variables']
        # 报告不允许重新编译/求解原项目。
        import fn_engine.api as api
        monkeypatch.setattr(api,'compile_project',lambda *a:pytest.fail('报告不得重新编译'))
        html=client.get(f'/api/v1/runs/{run_id}/report.html')
        assert html.status_code==200,html.text
        assert '<script>alert' not in html.text and '&lt;script&gt;' in html.text
        csv_response=client.get(f'/api/v1/runs/{run_id}/report.csv')
        rows=list(csv.DictReader(StringIO(csv_response.content.decode('utf-8-sig'))))
        actual=[r for r in rows if r['变量键']=='Coil.state.condensate_kg' and float(r['时间(s)'])==1.][0]
        assert float(actual['规范数值'])==pytest.approx(record['frame']['variables']['Coil.state.condensate_kg'],rel=1e-10)
    with TestClient(create_app(data_root=tmp_path)) as client:
        assert client.get('/api/v1/runs/'+run_id).json()['air_metadata']==metadata
        assert client.get(f'/api/v1/runs/{run_id}/report.html').status_code==200


def test_batch_choices_and_authentication(tmp_path):
    choices={v.key for v in observation_choices(air_example('ahu-room'))}
    assert {'Coil.condensate_kg_s','Room.state.humidity_ratio_kg_kg','Humidifier.state.water_added_kg'} <= choices
    tokens=TokenStore(tmp_path/'tokens.json');_,read=tokens.create('只读','read')
    with TestClient(create_app(auth=AuthConfig(required=True,store=tokens))) as client:
        assert client.get('/api/v1/air/psychrometric-grid').status_code==401
        assert client.get('/api/v1/air/psychrometric-grid',headers={'Authorization':'Bearer '+read}).status_code==200
        assert client.post('/api/v1/air/properties',json={},headers={'Authorization':'Bearer '+read}).status_code==403


def test_websocket_rest_and_report_share_parameter_revision(tmp_path):
    from test_continuous import wait
    with TestClient(create_app(data_root=tmp_path)) as client:
        created=client.post('/api/v1/runs?background=true',json={'project':air_example('air-coil-wet').model_dump(mode='json'),
            'mode':'dynamic','duration_s':1.,'dt_s':1.,'start_paused':True}).json()
        rid=created['run_id']
        wait(client,rid,lambda r:r['status']=='paused')
        with client.websocket_connect(f'/api/v1/runs/{rid}/stream?keys=Coil.condensate_kg_s') as socket:
            initial=socket.receive_json()
            assert initial['type']=='frame'
            response=client.post(f'/api/v1/runs/{rid}/variables',json={'values':{'Coil.param.bypass_factor':.5},'wait_s':1.})
            assert response.status_code==200,response.text
            assert client.post(f'/api/v1/runs/{rid}/command',json={'action':'step'}).status_code==200
            record=wait(client,rid,lambda r:r['status']=='completed')
            message=socket.receive_json()
            while message['type']=='frame' and message['time_s']<1.:
                message=socket.receive_json()
            assert message['type']=='frame'
            rest=client.get(f'/api/v1/runs/{rid}/variables?keys=Coil.condensate_kg_s').json()
            assert message['sequence']==rest['sequence']==record['frame']['sequence']
            assert message['parameter_revision']==rest['parameter_revision']==1
            assert message['values']==rest['values']
        rows=list(csv.DictReader(StringIO(client.get(f'/api/v1/runs/{rid}/report.csv').content.decode('utf-8-sig'))))
        last=[row for row in rows if row['变量键']=='Coil.condensate_kg_s' and float(row['时间(s)'])==1.][0]
        assert float(last['规范数值'])==pytest.approx(rest['values']['Coil.condensate_kg_s'],rel=1e-10)


def test_trimmed_history_keeps_exact_accumulator(tmp_path):
    from test_continuous import wait
    with TestClient(create_app(data_root=tmp_path)) as client:
        rid=client.post('/api/v1/runs?background=true',json={'project':air_example('air-coil-wet').model_dump(mode='json'),
            'mode':'dynamic','duration_s':12.,'dt_s':1.,'history_window':10,'history':'trend'}).json()['run_id']
        record=wait(client,rid,lambda r:r['status']=='completed')
        assert client.get(f'/api/v1/runs/{rid}/history').json()['truncated']
        values=record['frame']['variables']
        assert values['Coil.state.condensate_kg']==pytest.approx(values['Coil.condensate_kg_s']*12,rel=1e-6)
        assert '抽稀概览' in client.get(f'/api/v1/runs/{rid}/report.html').text
