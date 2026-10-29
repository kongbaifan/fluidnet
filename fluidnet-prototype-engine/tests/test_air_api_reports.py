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
