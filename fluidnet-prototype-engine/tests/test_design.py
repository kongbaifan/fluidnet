import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.packages import load_module_package
from fn_engine.runtime import module_definition_hash
from test_module_versions import save_payload
from test_platform_contracts import custom_module

# Kv for 10 m³/h at 1 bar on the reference fluid, scaled by the design opening.
DESIGN = '''import math

def design(ctx):
    rho = ctx.fluid.state_pt(101325.0, 293.15).density_kg_m3
    kv = 10.0 * math.sqrt(rho / 1000.0) / ctx.parameter("opening_ratio")
    ctx.set("kv_m3_h", round(kv, 6))
    ctx.log(f"rho={rho:.1f}")
'''


def design_module(source=DESIGN):
    module = custom_module().model_dump(mode='json')
    module.update(content_hash=None, definition_hash=None)
    module['source']['design'] = source
    return module


def post(client, source=DESIGN, parameters=None):
    return client.post('/api/v1/modules/design', json={'module': design_module(source),
                                                       'parameters': parameters or {'opening_ratio': 0.5}})


def test_design_proposes_values_without_storing_them(tmp_path):
    client = TestClient(create_app(module_storage_root=tmp_path))
    response = post(client)
    assert response.status_code == 200, response.text
    body = response.json()
    kv = body['parameters']['kv_m3_h']
    assert 19.9 < kv < 20.0  # water at 20 °C is slightly lighter than 1000 kg/m³
    assert body['changes'] == [{'id': 'kv_m3_h', 'before': 16.0, 'after': kv}]
    assert body['parameters']['opening_ratio'] == 0.5
    assert body['diagnostics'][0]['code'] == 'DESIGN_LOG'
    assert len(body['design_hash']) == 64
    assert not list(tmp_path.rglob('*.py'))


@pytest.mark.parametrize('source,parameters,code,text', [
    ('def design(ctx):\n    ctx.set("kv_m3_h", -1.0)\n', None, 'DESIGN_OUTPUT_INVALID', '超出范围'),
    ('def design(ctx):\n    ctx.set("kv_m3_h", float("nan"))\n', None, None, '有限值'),
    ('def design(ctx):\n    ctx.set("missing", 1.0)\n', None, None, '未声明的模块参数'),
    ('def design(ctx):\n    x = 1\n    raise ValueError("boom")\n', None, None, '第 3 行'),
    ('def run(ctx):\n    pass\n', None, None, 'design(ctx)'),
    ('', None, None, '没有 design.py'),
    (DESIGN, {'opening_ratio': 2.0}, 'PARAMETER_RANGE', '超出范围'),
])
def test_design_failures_are_reported_not_applied(source, parameters, code, text):
    response = post(TestClient(create_app()), source, parameters)
    assert response.status_code == 422, response.text
    detail = response.json()['detail']
    assert text in detail['message']
    if code:
        assert detail['code'] == code


def test_builtin_module_has_no_executable_design():
    client = TestClient(create_app())
    pipe = next(m for m in client.get('/api/v1/catalog').json()['modules'] if m['id'] == 'pipe')
    pipe['source'] = {'design': DESIGN}
    response = client.post('/api/v1/modules/design', json={'module': pipe})
    assert response.status_code == 422
    assert 'Python 模块' in response.json()['detail']['message']


def test_design_is_saved_with_the_version_and_covered_by_its_hash(tmp_path):
    client = TestClient(create_app(module_storage_root=tmp_path))
    payload = save_payload()
    payload['module']['source']['design'] = DESIGN.replace('\n', '\r\n')
    release = client.post('/api/v1/modules/versions', json=payload)
    assert release.status_code == 201, release.text
    saved = release.json()['module']
    assert saved['source']['design'] == DESIGN
    package = next(tmp_path.rglob('design.py')).parent
    reloaded = load_module_package(package)
    assert reloaded.source['design'] == DESIGN
    assert reloaded.definition_hash == saved['definition_hash'] == module_definition_hash(reloaded)
    # Same runtime code: design.py changes the contract hash only.
    plain = client.post('/api/v1/modules/versions', json={**save_payload(), 'expected_latest_version': 1})
    assert plain.status_code == 201, plain.text
    assert plain.json()['package']['content_hash'] == release.json()['package']['content_hash']
    assert plain.json()['package']['definition_hash'] != release.json()['package']['definition_hash']
    assert 'design' not in plain.json()['module']['source']
    # The stored version runs its own design.py after a restart.
    restarted = TestClient(create_app(module_storage_root=tmp_path))
    stored = restarted.get('/api/v1/modules/saved_valve/versions/1').json()['module']
    rerun = restarted.post('/api/v1/modules/design', json={'module': stored, 'parameters': {'opening_ratio': 0.5}})
    assert rerun.status_code == 200, rerun.text


@pytest.mark.parametrize('source,match', [
    ('def design(ctx):\n    return (\n', 'design.py 第'),
    ('def other(ctx):\n    pass\n', 'design(ctx)'),
    ('def design():\n    pass\n', 'design.py'),
])
def test_invalid_design_blocks_validation_and_save(tmp_path, source, match):
    client = TestClient(create_app(module_storage_root=tmp_path))
    payload = save_payload()
    payload['module']['source']['design'] = source
    body = client.post('/api/v1/modules/validate', json=payload['module']).json()
    assert not body['valid']
    assert match in body['diagnostics'][0]['message']
    assert body['diagnostics'][0]['field'].startswith('source.design')
    assert client.post('/api/v1/modules/versions', json=payload).status_code == 422
    assert not list(tmp_path.rglob('manifest.json'))
