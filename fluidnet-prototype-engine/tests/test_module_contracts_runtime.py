"""S2 host/Worker/save boundaries; unsupported requirements never execute source."""
from copy import deepcopy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.batch import BatchRunners
from fn_engine.bridge import normalize_prototype_export
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import FluidConfig, InitializeRequest, ModuleDefinition, ModulePackageRef, Project
from fn_engine.module_contracts import ModuleCompatibilityError
from fn_engine.module_validation import validate_module_definition
from fn_engine.packages import load_module_package, package_ref
from fn_engine.runtime import InProcessModuleRunner, RuntimeErrorBase, WorkerProcess, module_definition_hash
from fn_engine.solver import solve_steady
from test_platform_contracts import custom_project
from test_module_sdk_contracts import V2, schema2_payload


def unsupported_module(tmp_path, reason='api'):
    payload = schema2_payload()
    marker = tmp_path / 'source-executed.txt'
    source = f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n'
    payload.update(source={'runtime':source, 'design':source + '\ndef design(ctx): pass\n'},
                   content_hash=None, definition_hash=None)
    payload['sdk'] = {
        'api': {'api_version':'9.0.0'},
        'capability': {'api_version':'0.2.0', 'capabilities':['thermal.future']},
        'state': {'api_version':'0.2.0', 'state_contract_version':2},
    }[reason]
    return ModuleDefinition.model_validate(payload), marker


def project_with(module):
    project = custom_project()
    project.modules[-1] = module
    project.instances[1].module_id = module.id
    project.instances[1].parameters = {}
    return project


@pytest.mark.parametrize('reason,code', [('api','MODULE_SDK_UNSUPPORTED'),
    ('capability','MODULE_CAPABILITY_UNSUPPORTED'), ('state','MODULE_STATE_CONTRACT_UNSUPPORTED')])
def test_compile_validation_and_runner_reject_before_process_or_source(tmp_path, monkeypatch, reason, code):
    module, marker = unsupported_module(tmp_path, reason)
    def no_process(*args, **kwargs):
        pytest.fail('unsupported module started a Worker')
    monkeypatch.setattr('fn_engine.runtime.subprocess.Popen', no_process)
    with pytest.raises(CompilationError) as compiled:
        compile_project(project_with(module))
    assert compiled.value.diagnostic.code == code
    assert compiled.value.diagnostic.instance_id == 'V1'
    diagnostics = validate_module_definition(module).diagnostics
    assert diagnostics[0].code == code
    assert diagnostics[0].field.startswith('sdk.')
    for runner in [InProcessModuleRunner, WorkerProcess]:
        with pytest.raises(ModuleCompatibilityError) as caught:
            runner(module, {}, FluidConfig())
        assert caught.value.code == code
    assert not marker.exists()


@pytest.mark.parametrize('action', ['validate', 'initialize', 'design', 'batch'])
def test_worker_rechecks_individual_wire_definitions_before_exec(tmp_path, action):
    invalid, marker = unsupported_module(tmp_path)
    valid = ModuleDefinition.model_validate(schema2_payload())
    runner = WorkerProcess(valid, {}, FluidConfig())
    payload = {'action':action, 'definition':invalid.model_dump(mode='json')}
    if action == 'initialize':
        request = InitializeRequest(run_id='s2', instance_id=invalid.id,
            package=package_ref(invalid), fluid=FluidConfig())
        payload['request'] = request.model_dump(mode='json')
    elif action == 'design':
        payload.update(parameters={}, fluid=FluidConfig().model_dump(mode='json'))
    elif action == 'batch':
        payload = {'action':'batch', 'items':{'other':{'action':'validate', 'definition':invalid.model_dump(mode='json')}}}
    try:
        with pytest.raises(RuntimeErrorBase, match='不支持的 SDK'):
            runner._request(payload)
    finally:
        runner.close(force=True)
    assert not marker.exists()


def test_batch_checks_all_instances_before_creating_first_worker(tmp_path, monkeypatch):
    valid = ModuleDefinition.model_validate(V2['modules'][0]['definition'])
    network = compile_project(project_with(valid))
    invalid, marker = unsupported_module(tmp_path)
    invalid.id = 'unsupported_second'
    network.modules[invalid.id] = invalid
    second = network.instances['V1'].model_copy(update={'id':'V2', 'module_id':invalid.id})
    def no_process(*args, **kwargs):
        pytest.fail('batch started a Worker before validating its instances')
    monkeypatch.setattr('fn_engine.batch.WorkerProcess', no_process)
    with pytest.raises(ModuleCompatibilityError):
        BatchRunners(network, [network.instances['V1'], second])
    assert not marker.exists()


@pytest.mark.parametrize('reason', ['api', 'capability', 'state'])
def test_api_rejects_unsupported_save_test_and_design_without_persisting(tmp_path, reason):
    module, marker = unsupported_module(tmp_path, reason)
    client = TestClient(create_app(module_storage_root=tmp_path / 'modules'))
    validation = client.post('/api/v1/modules/validate', json=module.model_dump(mode='json'))
    assert validation.status_code == 200
    assert not validation.json()['valid']
    for url, body in [
        ('/api/v1/modules/versions', {'module':module.model_dump(mode='json'), 'expected_latest_version':0}),
        ('/api/v1/modules/test', {'module':module.model_dump(mode='json')}),
        ('/api/v1/modules/design', {'module':module.model_dump(mode='json')}),
    ]:
        response = client.post(url, json=body)
        assert response.status_code == 422, response.text
    assert not marker.exists()
    assert not list(tmp_path.rglob('manifest.json'))


@pytest.mark.parametrize('sample', V2['modules'], ids=lambda sample: sample['id'])
def test_schema2_api_save_restart_immutable_project_and_runtime(sample, tmp_path):
    module = deepcopy(sample['definition'])
    client = TestClient(create_app(module_storage_root=tmp_path))
    response = client.post('/api/v1/modules/versions', json={'module':module, 'expected_latest_version':0})
    assert response.status_code == 201, response.text
    release = response.json()
    assert release['module']['sdk'] == module['sdk']
    assert release['package']['definition_hash'] == sample['definition_hash']
    project = project_with(ModuleDefinition.model_validate(release['module']))
    project.instances[1].package = ModulePackageRef.model_validate(release['package'])
    project = Project.model_validate(project.model_dump(mode='json'))
    snapshot = project.model_dump_json()
    expected = solve_steady(compile_project(project)).variables['V1.mass_flow_kg_s']
    assert expected > 0
    restored = load_module_package(tmp_path / f'module-{module["id"]}' / 'v1')
    assert module_definition_hash(restored) == sample['definition_hash']
    restarted = TestClient(create_app(module_storage_root=tmp_path))
    loaded = restarted.get(f'/api/v1/modules/{module["id"]}/versions/1')
    assert loaded.status_code == 200
    assert loaded.json() == release
    # A new release explicitly changes capabilities/hash; the old project stays pinned.
    module['sdk']['capabilities'] = []
    second = restarted.post('/api/v1/modules/versions', json={'module':module, 'expected_latest_version':1})
    assert second.status_code == 201, second.text
    assert second.json()['package']['definition_hash'] != sample['definition_hash']
    replay = solve_steady(compile_project(Project.model_validate_json(snapshot)))
    assert replay.variables['V1.mass_flow_kg_s'] == pytest.approx(expected)
    assert load_module_package(tmp_path / f'module-{module["id"]}' / 'v1').sdk == restored.sdk


def test_schema2_declaration_tampering_fails_package_and_project_hash_checks(tmp_path):
    payload = schema2_payload()
    package = tmp_path / 'package'
    package.mkdir()
    source = payload.pop('source')['runtime']
    payload.pop('package_path')
    (package / 'module.py').write_text(source, encoding='utf-8', newline='')
    payload['sdk']['capabilities'] = []
    (package / 'manifest.json').write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError, match='契约哈希'):
        load_module_package(package)
    module = ModuleDefinition.model_validate({**payload, 'source':{'runtime':source}})
    with pytest.raises(CompilationError) as caught:
        compile_project(project_with(module))
    assert caught.value.diagnostic.code == 'MODULE_DEFINITION_HASH_MISMATCH'


def test_schema2_frozen_ui_manifest_preserves_sdk_and_hash():
    payload = schema2_payload()
    module_id = payload['id']
    snapshot = {'id':module_id, 'kind':module_id, 'name':payload['name'], 'version':1,
                'runtime':'python', 'frozen':True, 'manifest':payload}
    prototype = {'format':'fluidnet-studio-prototype', 'modules':[snapshot],
        'projects':[{'id':'schema2', 'moduleSnapshots':{module_id:snapshot},
                     'pages':[{'nodes':[{'id':'D1', 'moduleId':module_id}]}]}]}
    module = normalize_prototype_export(prototype).modules[0]
    assert module.sdk.model_dump() == payload['sdk']
    assert module_definition_hash(module) == payload['definition_hash']
    assert hashlib.sha256(module.source['runtime'].encode()).hexdigest() == payload['content_hash']
