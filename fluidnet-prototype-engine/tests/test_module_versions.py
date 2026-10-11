from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.models import ModuleDefinition, Project, Direction
from fn_engine.compiler import compile_project, CompilationError
from fn_engine.solver import solve_steady
from fn_engine.runtime import module_definition_hash
from fn_engine.bridge import normalize_prototype_export
from test_platform_contracts import custom_module, custom_project


def save_payload():
    module = custom_module().model_dump(mode="json")
    module.update(id="saved_valve", content_hash=None, definition_hash=None)
    return {"module": module, "expected_latest_version": 0, "release_notes": "首个验证版本"}


TWO_SIDE_SOURCE = '''class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("commit_count", 0)

    def evaluate(self, ctx):
        rho = ctx.port("in0").density_kg_m3 or 998.2
        for channel in ("primary", "secondary"):
            ctx.net.valve(channel=channel, kv=ctx.parameter("kv_m3_h"),
                          opening=ctx.parameter("opening_ratio"), density_kg_m3=rho)
        ctx.var("opening_ratio", ctx.parameter("opening_ratio"))

    def commit_step(self, ctx, dt_s):
        ctx.state["commit_count"] += 1

    def finalize(self, ctx):
        pass
'''


def two_side_module():
    """A two-fluid-side module: two independent channels, four ports, one enabled each."""
    module = custom_module().model_dump(mode="json")
    module.update(id="two_side_valve", name="双侧可编程阀", content_hash=None, definition_hash=None)
    module["ports"] = [
        {"id":"in0","label":"一次侧入口","domain":"fluid","direction":"in","required":True,"circuit":"fluid"},
        {"id":"out0","label":"一次侧出口","domain":"fluid","direction":"out","required":True,"circuit":"fluid"},
        {"id":"in1","label":"二次侧入口","domain":"fluid","direction":"in","required":True,"circuit":"fluid"},
        {"id":"out1","label":"二次侧出口","domain":"fluid","direction":"out","required":True,"circuit":"fluid"},
    ]
    module["channels"] = [
        {"id":"primary","name":"一次侧","input_port":"in0","output_port":"out0","relation":"resistance","solver_model":"valve","enabled":True},
        {"id":"secondary","name":"二次侧","input_port":"in1","output_port":"out1","relation":"resistance","solver_model":"valve","enabled":True},
    ]
    module["variables"] = [
        {"id":"opening_ratio","label":"有效开度","quantity":"ratio","source":"derived"},
        {"id":"state.commit_count","label":"已接受时间步","quantity":"count","source":"state"},
    ]
    module["source"] = {"runtime": TWO_SIDE_SOURCE}
    return module


def test_multi_channel_module_is_tested_and_saved_with_per_channel_boundaries(tmp_path):
    client = TestClient(create_app(module_storage_root=tmp_path))
    response = client.post('/api/v1/modules/versions', json={
        "module": two_side_module(), "expected_latest_version": 0, "release_notes": "双侧通路首个版本",
        "test": {"parameters": {"opening_ratio": 0.5, "kv_m3_h": 10.0}}})
    assert response.status_code == 201, response.text
    release = response.json()
    frame = release['test_result']['frame']['variables']
    # Both enabled channels are wired to their own boundary pair and solved in one network.
    assert frame['D1.primary.mass_flow_kg_s'] > 0
    assert frame['D1.secondary.mass_flow_kg_s'] > 0
    assert frame['D1.opening_ratio'] == pytest.approx(0.5)
    assert release['test_result']['committed']['state']['commit_count'] == 1
    assert len(release['module']['channels']) == 2
    # The saved version re-runs from disk after a restart.
    restarted = TestClient(create_app(module_storage_root=tmp_path))
    replay = restarted.post('/api/v1/modules/test', json={'module': release['module'],
        "parameters": {"opening_ratio": 0.5, "kv_m3_h": 10.0}})
    assert replay.status_code == 200, replay.text
    assert replay.json()['frame']['variables']['D1.primary.mass_flow_kg_s'] == pytest.approx(frame['D1.primary.mass_flow_kg_s'])


@pytest.mark.parametrize('change,match', [
    ('shared_port', '独立端口'),
    ('unbound_port', '未绑定'),
    ('non_fluid_port', '流体端口'),
    ('disabled_all', '至少一条启用通路'),
])
def test_bench_rejects_channel_wiring_it_cannot_solve(tmp_path, change, match):
    module = two_side_module()
    if change == 'shared_port':
        module['channels'][1]['input_port'] = 'in0'
    elif change == 'unbound_port':
        module['channels'][1]['enabled'] = False
    elif change == 'non_fluid_port':
        module['ports'][2].update(domain='info')
        module['ports'][0].update(domain='info')
        module['ports'][3].update(domain='info')
    else:
        for channel in module['channels']:
            channel['enabled'] = False
    response = TestClient(create_app(module_storage_root=tmp_path)).post('/api/v1/modules/versions',
        json={"module": module, "expected_latest_version": 0})
    assert response.status_code == 422, response.text
    assert match in response.json()['detail']['message']
    assert not list(tmp_path.rglob('manifest.json'))


def test_definition_hash_survives_browser_json_number_roundtrip():
    module = custom_module()
    before = module_definition_hash(module)
    module.parameters[1].default = int(module.parameters[1].default)
    assert module_definition_hash(module) == before


def test_frozen_snapshot_preserves_bidirectional_ports_over_ui_projection():
    module = custom_module()
    module.ports[0].direction = Direction.bidirectional
    module.definition_hash = module_definition_hash(module)
    definition = module.model_dump(mode='json')
    # UI draws the first bidirectional port on the input side; this is presentation only.
    snapshot = {'id':module.id, 'kind':module.id, 'name':module.name, 'version':module.version,
                'runtime':'python', 'frozen':True, 'manifest':definition,
                'ports':[{'id':'in0','direction':'in'}]}
    prototype = {'format':'fluidnet-studio-prototype','modules':[{'id':module.id,'kind':'valve'}],
                 'projects':[{'id':'snapshot','moduleSnapshots':{module.id:snapshot},
                              'pages':[{'nodes':[{'id':'D1','moduleId':module.id}]}]}]}
    normalized = normalize_prototype_export(prototype).modules[0]
    assert normalized.ports[0].direction == 'bidirectional'
    assert module_definition_hash(normalized) == module.definition_hash


def test_save_restart_reproduce_and_pin_old_project(tmp_path):
    client = TestClient(create_app(module_storage_root=tmp_path))
    payload = save_payload()
    response = client.post('/api/v1/modules/versions', json=payload)
    assert response.status_code == 201, response.text
    release = response.json()
    assert release['tested'] and release['test_result']['committed']['state']['commit_count'] == 1
    assert len(release['package']['definition_hash']) == 64
    project = custom_project()
    project.modules[-1] = ModuleDefinition.model_validate(release['module'])
    project.instances[1].module_id = 'saved_valve'
    project.instances[1].package = release['package']
    frozen = project.model_dump(mode='json', warnings=False)
    project = Project.model_validate(frozen)
    old_flow = solve_steady(compile_project(project)).variables['V1.mass_flow_kg_s']
    payload['expected_latest_version'] = 1
    payload['module']['source']['runtime'] = payload['module']['source']['runtime'].replace('kv=ctx.parameter("kv_m3_h")', 'kv=2 * ctx.parameter("kv_m3_h")')
    second = client.post('/api/v1/modules/versions', json=payload)
    assert second.status_code == 201, second.text
    restarted = TestClient(create_app(module_storage_root=tmp_path))
    versions = restarted.get('/api/v1/modules/saved_valve/versions').json()['versions']
    assert [v['package']['version'] for v in versions] == ['2.0.0', '1.0.0']
    assert restarted.get('/api/v1/modules/saved_valve/versions/1').json() == release
    latest = next(m for m in restarted.get('/api/v1/modules').json()['modules'] if m['id'] == 'saved_valve')
    assert latest['version'] == 2
    # A serialized project keeps the old source and contract after the catalog advances.
    assert solve_steady(compile_project(Project.model_validate(frozen))).variables['V1.mass_flow_kg_s'] == pytest.approx(old_flow)
    result = restarted.post('/api/v1/modules/test', json={'module': second.json()['module']})
    assert result.status_code == 200
    assert result.json()['frame']['variables']['D1.mass_flow_kg_s'] > release['test_result']['frame']['variables']['D1.mass_flow_kg_s']


@pytest.mark.parametrize('change', ['syntax', 'entrypoint', 'runtime', 'finalize', 'default', 'variable', 'path', 'missing_source', 'missing_output'])
def test_invalid_release_is_never_persisted(tmp_path, change):
    client = TestClient(create_app(module_storage_root=tmp_path))
    payload = save_payload()
    module = payload['module']
    if change == 'syntax':
        module['source']['runtime'] = 'class Module:\n    def evaluate(\n'
    elif change == 'entrypoint':
        module['entrypoint'] = 'module:Missing'
    elif change == 'runtime':
        module['source']['runtime'] = module['source']['runtime'].replace('        inlet = ctx.port("in0")', '        raise ValueError("算法试算失败")')
    elif change == 'default':
        module['parameters'][0]['default'] = 10
    elif change == 'variable':
        module['variables'][0]['parameter_id'] = 'missing'
    elif change == 'finalize':
        module['source']['runtime'] = module['source']['runtime'].replace('    def finalize(self, ctx):\n        pass', '    def finalize(self, ctx):\n        raise ValueError("finalize 失败")')
    elif change == 'missing_source':
        module['source'] = {}
    elif change == 'missing_output':
        module['variables'].append({'id':'missing_output','label':'未实现输出','quantity':'ratio','source':'derived'})
    else:
        module['id'] = '../escape'
    response = client.post('/api/v1/modules/versions', json=payload)
    assert response.status_code == 422, response.text
    assert not list(tmp_path.rglob('manifest.json'))


def test_validation_uses_python_and_worker_entrypoint_checks(tmp_path):
    client = TestClient(create_app(module_storage_root=tmp_path))
    module = save_payload()['module']
    module['source']['runtime'] = 'class Module:\n    def evaluate(self, ctx):\n        pass\n'
    body = client.post('/api/v1/modules/validate', json=module).json()
    assert not body['valid'] and 'initialize' in body['diagnostics'][0]['message']
    module['source']['runtime'] = 'class Module:\n invalid syntax\n'
    body = client.post('/api/v1/modules/validate', json=module).json()
    assert body['diagnostics'][0]['code'] == 'MODULE_SYNTAX_ERROR'
    assert 'source.runtime:' in body['diagnostics'][0]['field']


def test_concurrent_saves_conflict_without_overwriting(tmp_path):
    clients = [TestClient(create_app(module_storage_root=tmp_path)) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda c: c.post('/api/v1/modules/versions', json=save_payload()), clients))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len(list(tmp_path.rglob('manifest.json'))) == 1


def test_saved_contract_tampering_and_wrong_binding_are_rejected(tmp_path):
    release = TestClient(create_app(module_storage_root=tmp_path)).post('/api/v1/modules/versions', json=save_payload()).json()
    project = custom_project().model_dump(mode='json')
    project['modules'][-1] = release['module']
    project['instances'][1].update(module_id='saved_valve', package=release['package'])
    project['modules'][-1]['parameters'][0]['default'] = .3
    with pytest.raises(CompilationError, match='契约'):
        compile_project(Project.model_validate(project))
    project['instances'][1]['package']['version'] = '9.0.0'
    with pytest.raises(ValueError, match='版本绑定'):
        Project.model_validate(project)
