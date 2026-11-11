"""HTTP/Python parity, native engine reuse and host authorization for all businesses."""
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine.adapters import AdapterRegistry, default_registry
from fn_engine.api import create_app
from fn_engine.auth import AuthConfig, TokenStore
from fn_engine.packages import load_module_package
from test_adapters import electrical_definition
from test_contracts_and_physics import simple

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as value:
        yield value


def execute(client, adapter, inputs, **extra):
    return client.post('/api/v1/adapters/execute', json={'adapter_id': adapter, 'inputs': inputs, **extra})


def test_catalog_describes_schemas_versions_and_units(client):
    response = client.get('/api/v1/adapters')
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['contract_version'] == 1
    assert len(catalog['adapters']) == 16
    description = client.get('/api/v1/adapters/hydraulics.pipe_pressure_drop').json()
    assert description['input_schema']['additionalProperties'] is False
    assert 'diameter' in description['input_schema']['required']
    assert description['input_units']['diameter']['canonical_unit'] == 'm'
    assert 'mm' in description['input_units']['diameter']['accepted_units']
    assert client.get('/api/v1/adapters/hydraulics.pipe_pressure_drop?version=2').status_code == 404
    assert client.get('/api/v1/adapters/hydraulics.pipe_pressure_drop?version=0').status_code == 422


def test_http_and_python_share_identical_results(client):
    body = {'adapter_id': 'hydraulics.volume_to_mass_flow', 'request_id': 'external-app-3',
        'inputs': {'volume_flow': 3.6, 'density': 1000.}, 'output_units': {'mass_flow': 'kg/h'}}
    response = client.post('/api/v1/adapters/execute', json=body)
    assert response.status_code == 200
    assert response.json() == default_registry().execute(body).model_dump(mode='json')
    assert response.json()['outputs']['mass_flow'] == pytest.approx(3600.)


def test_third_party_adapter_uses_existing_routes_without_changes(tmp_path):
    registry = AdapterRegistry([electrical_definition()])
    with TestClient(create_app(data_root=tmp_path, adapter_registry=registry)) as client:
        response = execute(client, 'electrical.consumption', {'power': 5., 'efficiency': 80.},
            input_units={'power': 'kW', 'efficiency': '%'}, output_units={'consumed_power': 'kW'})
        assert response.status_code == 200
        assert response.json()['outputs']['consumed_power'] == pytest.approx(6.25)
        assert len(client.get('/api/v1/adapters').json()['adapters']) == 1
    # Empty registries remain empty; app construction does not substitute global defaults.
    with TestClient(create_app(adapter_registry=AdapterRegistry())) as empty:
        assert empty.get('/api/v1/adapters').json()['adapters'] == []


@pytest.mark.parametrize('body', [[], {'adapter_id': 'no-dots'},
    {'adapter_id': 'hydraulics.mass_to_volume_flow', 'version': True},
    {'adapter_id': 'hydraulics.mass_to_volume_flow', 'input_units': []},
    {'adapter_id': 'hydraulics.mass_to_volume_flow', 'unknown': 'field'},
])
def test_invalid_envelope_has_uniform_error(client, body):
    response = client.post('/api/v1/adapters/execute', json=body)
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'ADAPTER_INPUT_INVALID'


def test_invalid_number_json_and_malformed_json_do_not_break_service(client):
    for content in ('{broken', '{"adapter_id":"hydraulics.mass_to_volume_flow","inputs":{"mass_flow":1e999,"density":1000}}'):
        response = client.post('/api/v1/adapters/execute', content=content, headers={'Content-Type': 'application/json'})
        assert response.status_code == 422
        assert response.json()['detail']['code'] == 'ADAPTER_INPUT_INVALID'
    assert client.get('/api/v1/adapters').status_code == 200


def test_invalid_envelope_preserves_bounded_correlation_fields(client):
    response = client.post('/api/v1/adapters/execute',
        content='{"adapter_id":"hydraulics.mass_to_volume_flow","request_id":"job-5","version":1,"inputs":{"mass_flow":1e999,"density":1000}}',
        headers={'Content-Type': 'application/json'})
    detail = response.json()['detail']
    assert response.status_code == 422
    assert detail['request_id'] == 'job-5'
    assert detail['adapter_id'] == 'hydraulics.mass_to_volume_flow'
    assert detail['version'] == 1
    invalid = client.post('/api/v1/adapters/execute', json={'adapter_id': 'x'*101, 'request_id': 'x'*129, 'version': True})
    assert invalid.status_code == 422
    detail = invalid.json()['detail']
    assert all(detail[key] is None for key in ('adapter_id', 'version', 'request_id'))


def test_unit_errors_echo_request_and_native_routes_keep_their_errors(client):
    response = execute(client, 'hydraulics.mass_to_volume_flow', {'mass_flow': 1., 'density': 1000.},
                       request_id='correlation-7', input_units={'mass_flow': 'm3/h'})
    detail = response.json()['detail']
    assert response.status_code == 422
    assert detail['code'] == 'ADAPTER_UNIT_INVALID'
    assert detail['field'] == 'input_units.mass_flow'
    assert detail['request_id'] == 'correlation-7'
    # Existing FastAPI validation envelope is deliberately preserved on pre-existing routes.
    assert isinstance(client.post('/api/v1/solve', json={}).json()['detail'], list)


def test_moist_air_matches_native_property_endpoint_and_converts_mass_basis(client):
    inputs = {'input_mode': 'ptrh', 'pressure': 101.325, 'temperature': 26., 'relative_humidity': 55.}
    response = execute(client, 'properties.moist_air', inputs,
        input_units={'pressure': 'kPa', 'temperature': 'degC', 'relative_humidity': '%'},
        output_units={'temperature': 'degC', 'dew_point': 'degC', 'humidity_ratio': 'g/kg_da', 'enthalpy_dry_air': 'kJ/kg_da'})
    assert response.status_code == 200, response.text
    native = client.post('/api/v1/air/properties', json={'input_mode': 'ptrh', 'pressure_pa': 101325.,
        'temperature_k': 299.15, 'relative_humidity': .55}).json()['state']
    result = response.json()['outputs']
    assert result['temperature'] == pytest.approx(26.)
    assert result['humidity_ratio'] == pytest.approx(native['humidity_ratio_kg_kg']*1000)
    assert result['enthalpy_dry_air'] == pytest.approx(native['enthalpy_j_kg_dry_air']/1000)
    assert result['dew_point'] == pytest.approx(native['dew_point_k']-273.15)
    inputs['relative_humidity'] = 0.
    dry = execute(client, 'properties.moist_air', inputs,
        input_units={'pressure': 'kPa', 'temperature': 'degC', 'relative_humidity': '%'}, output_units={'dew_point': 'degC'})
    assert dry.status_code == 200
    assert dry.json()['outputs']['dew_point'] is None


def test_fluid_state_uses_input_units_and_preserves_nested_si(client):
    response = execute(client, 'properties.fluid_state_pt', {'pressure': 2., 'temperature': 20.,
        'fluid': {'fluid': 'Water', 'phase_policy': 'liquid'}}, input_units={'pressure': 'bar', 'temperature': 'degC'})
    assert response.status_code == 200, response.text
    state = response.json()['outputs']['state']
    assert state['pressure_pa'] == pytest.approx(200000.)
    assert state['temperature_k'] == pytest.approx(293.15)
    assert 997 < state['density_kg_m3'] < 999


def test_network_validation_and_solving_reuse_native_contracts(client):
    project = simple().model_dump(mode='json')
    validated = execute(client, 'network.validate', {'project': project})
    assert validated.status_code == 200
    assert validated.json()['outputs'] == client.post('/api/v1/projects/validate', json=project).json()
    solved = execute(client, 'network.solve_steady', {'project': project})
    assert solved.status_code == 200, solved.text
    native = client.post('/api/v1/solve', json=project).json()
    result = solved.json()['outputs']
    assert result['valid']
    assert result['variables'] == pytest.approx(native['variables'])
    assert client.get('/api/v1/runs').json()['runs'] == []
    project['instances'][1]['parameters'] = {'opening_ratio': 2.}
    validated = execute(client, 'network.validate', {'project': project})
    assert validated.status_code == 200 and not validated.json()['outputs']['valid']
    failed = execute(client, 'network.solve_steady', {'project': project})
    assert failed.status_code == 422
    assert failed.json()['detail']['diagnostics'][0]['code'] == 'PARAMETER_RANGE'


def test_module_design_runs_real_worker_and_returns_native_proposal(client):
    module = load_module_package(ROOT/'modules/design_valve').model_dump(mode='json')
    inputs = {'module': module, 'parameters': {'design_flow_m3_s': 10/3600,
        'design_pressure_drop_pa': 100000., 'opening_ratio': 1.}, 'fluid': {'fluid': 'Water', 'phase_policy': 'liquid'}}
    adapted = execute(client, 'modules.design', inputs)
    assert adapted.status_code == 200, adapted.text
    native = client.post('/api/v1/modules/design', json=inputs)
    assert adapted.json()['outputs'] == native.json()
    assert 9.9 < adapted.json()['outputs']['parameters']['kv_m3_h'] < 10.1


def test_adapter_routes_inherit_host_auth(tmp_path):
    store = TokenStore(tmp_path/'tokens.json')
    _, read = store.create('reader', 'read')
    _, control = store.create('caller', 'control')
    headers = lambda token: {'Authorization': 'Bearer '+token}
    body = {'adapter_id': 'hydraulics.mass_to_volume_flow', 'inputs': {'mass_flow': 1., 'density': 1000.}}
    with TestClient(create_app(auth=AuthConfig(required=True, store=store))) as client:
        assert client.get('/api/v1/adapters').status_code == 401
        assert client.get('/api/v1/adapters', headers=headers(read)).status_code == 200
        assert client.post('/api/v1/adapters/execute', json=body, headers=headers(read)).status_code == 403
        assert client.post('/api/v1/adapters/execute', json=body, headers=headers(control)).status_code == 200
