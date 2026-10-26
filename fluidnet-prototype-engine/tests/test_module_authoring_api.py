import json

from fastapi.testclient import TestClient
import pytest
from fn_engine.api import create_app


def test_template_and_suite_endpoints_use_json_request_bodies(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        response=client.post('/api/v1/modules/from-template',json={'template':'resistance','id':'api_resistance','name':'API resistance'})
        assert response.status_code==200,response.text
        module=response.json()
        response=client.post('/api/v1/modules/test-suite',json={'module':module,'cases':[{'id':'forward'}]})
        assert response.status_code==200,response.text
        assert response.json()['passed']


def test_suite_api_returns_assertion_evidence_and_continues_after_mismatch(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        module = client.post('/api/v1/modules/from-template', json={
            'template': 'resistance', 'id': 'asserted_resistance', 'name': 'Asserted resistance'}).json()
        response = client.post('/api/v1/modules/test-suite', json={'module': module, 'cases': [
            {'id': 'wrong', 'assertions': [{'key': 'D1.in0.pressure_pa', 'expected': 0}]},
            {'id': 'correct', 'assertions': [{'key': 'D1.in0.pressure_pa', 'expected': 250000, 'absolute_tolerance': .01}]},
        ]})
        assert response.status_code == 200, response.text
        result = response.json()
        assert not result['passed']
        assert [case['passed'] for case in result['cases']] == [False, True]
        failed, passed = [case['assertions'][0] for case in result['cases']]
        assert failed['status'] == 'outside_tolerance' and failed['actual'] == pytest.approx(250000)
        assert passed['expected'] == 250000 and passed['absolute_error'] <= passed['allowed_error']


@pytest.mark.parametrize('assertions', [
    [{'key': 'D1.value', 'expected': True}],
    [{'key': 'D1.value', 'expected': 1, 'absolute_tolerance': -1}],
    [{'key': 'D1.value', 'expected': 1}, {'key': 'D1.value', 'expected': 2}],
])
def test_suite_api_rejects_invalid_assertion_definitions(tmp_path, assertions):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        module = client.post('/api/v1/modules/from-template', json={
            'template': 'resistance', 'id': 'validation_resistance', 'name': 'Validation resistance'}).json()
        response = client.post('/api/v1/modules/test-suite', json={
            'module': module, 'cases': [{'id': 'invalid', 'assertions': assertions}]})
        assert response.status_code == 422, response.text


@pytest.mark.parametrize('field', ['expected', 'absolute_tolerance', 'relative_tolerance'])
@pytest.mark.parametrize('literal', ['NaN', 'Infinity', '-Infinity', '1e999'])
def test_suite_api_returns_serializable_validation_error_for_non_finite_json(tmp_path, field, literal):
    with TestClient(create_app(module_storage_root=tmp_path), raise_server_exceptions=False) as client:
        module = client.post('/api/v1/modules/from-template', json={
            'template': 'resistance', 'id': 'finite_resistance', 'name': 'Finite resistance'}).json()
        assertion = {'key': 'D1.value', 'expected': 1, field: 'ASSERTION_VALUE'}
        payload = json.dumps({'module': module, 'cases': [{'id': 'invalid', 'assertions': [assertion]}]})
        response = client.post('/api/v1/modules/test-suite', content=payload.replace('"ASSERTION_VALUE"', literal),
            headers={'content-type': 'application/json'})
        assert response.status_code == 422, response.text
        detail = response.json()['detail']
        assert any(item['loc'][-1] == field for item in detail)
        json.dumps(response.json(), allow_nan=False)
