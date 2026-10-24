from fastapi.testclient import TestClient
from fn_engine.api import create_app


def test_template_and_suite_endpoints_use_json_request_bodies(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        response=client.post('/api/v1/modules/from-template',json={'template':'resistance','id':'api_resistance','name':'API resistance'})
        assert response.status_code==200,response.text
        module=response.json()
        response=client.post('/api/v1/modules/test-suite',json={'module':module,'cases':[{'id':'forward'}]})
        assert response.status_code==200,response.text
        assert response.json()['passed']
