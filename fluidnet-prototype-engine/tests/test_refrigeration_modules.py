"""Refrigeration contracts: frozen schemas, explicit roles, typed Workers and public execution."""
from copy import deepcopy
import json
import math
from pathlib import Path
import time

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from fn_engine.api import create_app
from fn_engine.bench import run_module_test
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import (CommitStepRequest, EvaluateRequest, FluidConfig, ModuleDefinition,
    ModuleInstance, ModuleRequestContext, ModuleTestRequest, RefrigerationEvaluateRequest)
from fn_engine.module_contracts import check_module_compatibility, canonical_contract_bytes
from fn_engine.module_transactions import ModuleStepTransaction
from fn_engine.refrigeration.examples import station_example
from fn_engine.refrigeration.station import StationSession, evaluate
from fn_engine.refrigeration_models import RefrigerationThrottleInput, RefrigerationThrottleFlow
from fn_engine.runtime import WorkerProcess, RuntimeErrorBase, module_content_hash, module_definition_hash

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/refrigeration_extensions/sdk_throttle.py').read_text(encoding='utf-8')
MANIFEST=json.loads((ROOT/'examples/refrigeration_extensions/sdk_throttle.manifest.json').read_text(encoding='utf-8'))


def definition(source=SOURCE):
    module=ModuleDefinition.model_validate({**deepcopy(MANIFEST),'source':{'runtime':source}})
    module.content_hash=module_content_hash(module)
    module.definition_hash=module_definition_hash(module)
    return module


def project_with(module=None):
    module=module or definition()
    project=station_example()
    project.modules.append(module)
    next(i for i in project.instances if i.id=='EV1').module_id=module.id
    return project


def point(**changes):
    return RefrigerationThrottleInput(inlet_pressure_pa=1e6,outlet_pressure_pa=2e5,inlet_temperature_k=300.,
        inlet_enthalpy_j_kg=-12000.,inlet_density_kg_m3=600.,**{'opening_ratio':.5,'rated_kv_m3_h':.6,**changes})


def request(**changes):
    return RefrigerationEvaluateRequest(**{'run_id':'rf1-run','instance_id':'Valve42','iteration_id':0,
        'time_s':0.,'throttle':point(),**changes})


def worker(module=None):
    return WorkerProcess(module or definition(),{},FluidConfig(fluid='Ammonia',phase_policy='any'),
        run_id='rf1-run',instance_id='Valve42')


def test_schema4_roundtrip_hash_and_extra_author_parameters():
    module=definition()
    restored=ModuleDefinition.model_validate_json(module.model_dump_json())
    assert canonical_contract_bytes(module)==canonical_contract_bytes(restored)
    assert module_definition_hash(restored)==module.definition_hash
    assert restored.execution_role=='refrigeration.isenthalpic_throttle.v1'
    payload=module.model_dump(mode='json');payload['definition_hash']=None
    payload['parameters'].append({'id':'characteristic','label':'特性','value_type':'text','default':'linear'})
    assert compile_project(project_with(ModuleDefinition.model_validate(payload))).refrigeration_modules


def test_schema3_snapshot_keeps_its_pre_refrigeration_hash_and_export():
    before=json.loads((ROOT/'tests/fixtures/module-system/v3-before-refrigeration.json').read_text(encoding='utf-8'))
    module=ModuleDefinition.model_validate(before['module'])
    assert module_definition_hash(module)==before['hash']
    assert module.model_dump(mode='json')==before['module']


def test_published_schema_and_openapi_can_resolve_all_references():
    from jsonschema import Draft202012Validator
    schema=ModuleDefinition.model_json_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(definition().model_dump(mode='json'))
    bad=definition().model_dump(mode='json');bad['applicability']['execution_domains']=['fluid']
    assert list(Draft202012Validator(schema).iter_errors(bad))
    openapi=create_app().openapi()
    def visit(value):
        if isinstance(value,dict):
            if '$ref' in value:
                target=openapi
                assert value['$ref'].startswith('#/'),value['$ref']
                for name in value['$ref'][2:].split('/'):
                    target=target[name]
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(openapi)


@pytest.mark.parametrize('fault',['role','missing_role','domain','state','thermal','channel','port','unit','opening','kv','source_format'])
def test_invalid_role_contracts_rejected_before_loading_source(fault):
    payload=deepcopy(MANIFEST)
    if fault=='role':payload['execution_role']='refrigeration.compressor.v1'
    elif fault=='missing_role':payload.pop('execution_role')
    elif fault=='domain':payload['applicability']['execution_domains']=['fluid']
    elif fault=='state':payload['state_model']='saturated_vessel'
    elif fault=='thermal':payload['thermal_model']='heat_exchanger'
    elif fault=='channel':payload['channels']=[{}]
    elif fault=='port':payload['ports'][0]['direction']='out'
    elif fault=='unit':payload['parameters'][0]['unit']['canonical_unit']='Pa'
    elif fault=='opening':payload['parameters'][1]['runtime']=False
    elif fault=='kv':payload['parameters'][0]['minimum']=0
    else:payload['source_format']='legacy-lua'
    with pytest.raises(ValidationError):ModuleDefinition.model_validate(payload)


@pytest.mark.parametrize('fault',['old_sdk','missing_capability','fluid_capability','hash','version_hash'])
def test_incompatible_or_changed_versions_rejected_before_worker_spawn(fault):
    module=definition()
    if fault=='old_sdk':module.sdk.api_version='0.6.0'
    elif fault=='missing_capability':module.sdk.capabilities.remove('refrigeration.throttle.v1')
    elif fault=='fluid_capability':module.sdk.capabilities.append('net.valve')
    elif fault=='hash':module.content_hash='0'*64
    else:module.version+=1
    with pytest.raises(ValueError):worker(module)


def test_old_schema_cannot_claim_refrigeration_capability():
    from fn_engine.module_templates import create_template
    module=create_template('resistance','old_sdk_role','Old')
    module.sdk.api_version='0.7.0';module.sdk.capabilities.append('refrigeration.throttle.v1')
    with pytest.raises(ValueError):check_module_compatibility(module)


def test_compiler_keeps_real_topology_and_never_substitutes_the_builtin_at_runtime():
    module=definition("raise AssertionError('user code executed during compile')")
    network=compile_project(project_with(module))
    assert network.kinds['EV1']=='expansion_valve'
    assert network.refrigeration_modules['EV1'].id==module.id
    assert network.vessel('EV1','in0')=='HP1' and network.vessel('EV1','out0')=='LP1'
    session=StationSession(network,1.,.1)
    try:
        with pytest.raises(ValueError,match='user code executed during compile'):session.initialize()
        assert session.closed
        assert all(r.process is None or r.process.poll() is not None for r in session.runners.values())
    finally:session.close()
    with pytest.raises(CompilationError):evaluate(network,{}, {}, {}, {})


@pytest.mark.parametrize('fault',['moist','fluid','cold_store','phase','whitelist'])
def test_incompatible_execution_domains_and_fluids_rejected(fault):
    project=project_with()
    if fault=='moist':project.solver.moist_air=True
    elif fault=='fluid':
        project.modules.append(catalog_map()['pipe'])
        project.instances.append(ModuleInstance(id='WaterPipe',name='pipe',module_id='pipe'))
    elif fault=='cold_store':
        project.modules.append(catalog_map()['storage_room'])
        project.instances.append(ModuleInstance(id='ColdStore',name='room',module_id='storage_room'))
    elif fault=='phase':
        with pytest.raises(ValueError):WorkerProcess(definition(),{},FluidConfig(fluid='Ammonia',phase_policy='liquid'))
        return
    else:
        module=project.modules[-1];module.applicability.fluids=['CarbonDioxide'];module.definition_hash=None
    with pytest.raises(CompilationError):compile_project(project)


@pytest.fixture(scope='module')
def running_worker():
    runner=worker()
    try:
        runner.initialize()
        yield runner
    finally:runner.close()


@pytest.mark.parametrize('opening',[0.,.25,1.])
@pytest.mark.parametrize('outlet',[2e5,1e6,1.2e6])
def test_typed_worker_kv_grid_and_candidate_state_stays_readonly(running_worker,opening,outlet):
    runner=running_worker;runner.update_parameters({'opening_ratio':opening})
    data=point(opening_ratio=opening).model_copy(update={'outlet_pressure_pa':outlet})
    result=runner.evaluate_refrigeration(request(throttle=data))
    expected=.6*opening/3600*math.sqrt(1000*600*max(1e6-outlet,0)/100000)
    assert result.flow.mass_flow_kg_s==pytest.approx(expected,rel=1e-12,abs=1e-14)
    assert result.flow.effective_kv_m3_h==.6*opening
    assert result.variables['opening']==opening
    assert runner.state=={'accepted_segments':0}


@pytest.mark.parametrize('field,value',[('inlet_pressure_pa',0),('inlet_density_kg_m3',float('nan')),
    ('inlet_temperature_k',True),('inlet_enthalpy_j_kg','12 kJ/kg'),('rated_kv_m3_h',float('inf'))])
def test_typed_input_rejects_nonfinite_units_and_non_numbers(field,value):
    payload=point().model_dump();payload[field]=value
    with pytest.raises(ValidationError):RefrigerationThrottleInput.model_validate(payload)


@pytest.mark.parametrize('value',[True,'1 kg/s',-1.,float('nan'),float('inf')])
def test_typed_flow_rejects_invalid_numbers(value):
    with pytest.raises(ValidationError):RefrigerationThrottleFlow(mass_flow_kg_s=value,effective_kv_m3_h=.3)


def test_worker_identity_revision_stale_parameters_and_old_call_are_rejected():
    runner=worker()
    try:
        runner.initialize()
        for change in [{'run_id':'wrong'},{'instance_id':'wrong'},{'state_revision':9},
                       {'context':ModuleRequestContext(request_id='bad-time',accepted_time_s=1.)}]:
            with pytest.raises(ValueError):runner.evaluate_refrigeration(request(**change))
        with pytest.raises(ValueError):runner.evaluate_refrigeration(request(throttle=point(opening_ratio=.7)))
        with pytest.raises(RuntimeErrorBase):runner.evaluate(EvaluateRequest(run_id='rf1-run',instance_id='Valve42',iteration_id=0,time_s=0))
        assert runner.state=={'accepted_segments':0}
    finally:runner.close()


def test_runtime_partial_updates_preserve_frozen_instance_values_and_reject_kv_changes():
    runner=WorkerProcess(definition(),{'kv_m3_h':1.2},FluidConfig(fluid='Ammonia',phase_policy='any'),
        run_id='rf1-run',instance_id='Valve42')
    try:
        runner.initialize();runner.update_parameters({'opening_ratio':.25})
        assert runner.parameters['kv_m3_h']==1.2
        result=runner.evaluate_refrigeration(request(throttle=point(opening_ratio=.25,rated_kv_m3_h=1.2)))
        assert result.flow.effective_kv_m3_h==.3
        with pytest.raises(ValueError):runner.update_parameters({'kv_m3_h':2.})
        with pytest.raises(ValueError):runner._request({'action':'parameters','parameters':{'kv_m3_h':2.}})
        assert runner.parameters['kv_m3_h']==1.2
    finally:runner.close()


def test_new_worker_lifecycle_preserves_prepare_accept_and_duplicate_sync():
    runner=worker()
    try:
        runner.initialize();runner.evaluate_refrigeration(request())
        transaction=ModuleStepTransaction({'Valve42':runner},'rf1-step',.1)
        transaction.prepare('Valve42',CommitStepRequest(run_id='rf1-run',instance_id='Valve42',time_s=.1,dt_s=.1,
            context=ModuleRequestContext(request_id='commit',step_id='rf1-step',accepted_time_s=0.)),{})
        assert runner.state['accepted_segments']==0
        transaction.promote();transaction.synchronize();transaction.synchronize()
        assert runner.state['accepted_segments']==1 and runner.state_revision==1
        result=runner.evaluate_refrigeration(request(time_s=.1,state_revision=1))
        assert result.flow.mass_flow_kg_s>0
        process=runner.process;runner.finalize();runner.close()
        assert process.poll() is not None
    finally:runner.close()


@pytest.mark.parametrize('change',['missing','duplicate','reserved','inconsistent','frozen_input','exception'])
def test_bad_callback_does_not_produce_an_accepted_result(change):
    call='ctx.refrigeration.flow(mass_flow_kg_s=mass,effective_kv_m3_h=effective)'
    replacement={'missing':'pass','duplicate':call+'\n        '+call,
        'reserved':call+"\n        ctx.var('mass_flow_kg_s',mass)",
        'inconsistent':call.replace('mass_flow_kg_s=mass','mass_flow_kg_s=mass/2'),
        'frozen_input':'point.inlet_pressure_pa = 1.0',
        'exception':"raise ValueError('author fault')"}[change]
    runner=worker(definition(SOURCE.replace(call,replacement)))
    try:
        runner.initialize()
        with pytest.raises(ValueError):runner.evaluate_refrigeration(request())
        assert runner.state['accepted_segments']==0
    finally:runner.close()


def test_refrigeration_error_replay_carries_typed_boundary_and_source_line():
    runner=worker(definition(SOURCE.replace("point = ctx.refrigeration.throttle","raise ValueError('replay probe')\n        point = ctx.refrigeration.throttle")))
    try:
        runner.initialize()
        with pytest.raises(RuntimeErrorBase) as failure:runner.evaluate_refrigeration(request())
        assert failure.value.replay['refrigeration']==point().model_dump()
        assert failure.value.diagnostics[0].source_line is not None
        assert failure.value.diagnostics[0].instance_id=='Valve42'
    finally:runner.close()


def test_typed_worker_timeout_reclaims_process():
    source=SOURCE.replace('import math','import math\nimport time').replace('point = ctx.refrigeration.throttle',
        'time.sleep(1)\n        point = ctx.refrigeration.throttle')
    runner=worker(definition(source))
    try:
        runner.initialize();process=runner.process;runner.timeout_s=.05
        with pytest.raises(RuntimeErrorBase):runner.evaluate_refrigeration(request())
        assert process.poll() is not None and runner.state['accepted_segments']==0
    finally:runner.close()


@pytest.mark.parametrize('fault',['module_id','version','content_hash','definition_hash'])
def test_worker_rejects_wrong_initialization_package_before_user_code(fault):
    from fn_engine.models import InitializeRequest
    module=definition("raise AssertionError('must not load this source')")
    runner=worker(module)
    package={'module_id':module.id,'version':'1.0.0','content_hash':module.content_hash,'definition_hash':module.definition_hash}
    package[fault]={'module_id':'wrong','version':'2.0.0','content_hash':'0'*64,'definition_hash':'0'*64}[fault]
    message=InitializeRequest(run_id='rf1-run',instance_id='Valve42',package=package,parameters=runner.parameters,fluid=runner.fluid)
    try:
        with pytest.raises(RuntimeErrorBase) as failure:
            runner._request({'action':'initialize','definition':module.model_dump(mode='json'),'request':message.model_dump(mode='json')})
        assert failure.value.code=='MODULE_PACKAGE_MISMATCH'
    finally:runner.close()


def test_parent_rechecks_a_forged_worker_result(monkeypatch):
    runner=worker()
    try:
        monkeypatch.setattr(runner,'_request',lambda payload:{'flow':{'mass_flow_kg_s':1.,'effective_kv_m3_h':.3}})
        with pytest.raises(ValueError):runner.evaluate_refrigeration(request())
        assert runner.process is None
    finally:runner.close()


@pytest.mark.parametrize('source',[SOURCE.replace('def finalize(', 'def missing_finalize('),
    SOURCE.replace('def evaluate(', 'async def evaluate(')])
def test_role_initialize_rejects_missing_or_async_lifecycle(source):
    runner=worker(definition(source))
    try:
        with pytest.raises(ValueError):runner.initialize()
    finally:runner.close()


def test_public_validation_publication_and_run_execute_the_author_module(tmp_path):
    module=definition();project=project_with(module)
    with TestClient(create_app(data_root=tmp_path/'data',module_storage_root=tmp_path/'modules')) as client:
        validation=client.post('/api/v1/modules/validate',json=module.model_dump(mode='json'))
        assert validation.status_code==200,validation.text
        assert validation.json()['valid'],validation.text
        topology=client.post('/api/v1/projects/validate',json=project.model_dump(mode='json'))
        assert topology.status_code==200 and topology.json()['valid'],topology.text
        assert not any(d['code']=='REFRIGERATION_MODULE_EXECUTION_PENDING' for d in topology.json()['diagnostics'])
        published=client.post('/api/v1/modules/versions',json={'module':module.model_dump(mode='json'),'expected_latest_version':0})
        assert published.status_code==201,published.text
        assert published.json()['test_result']['execution_domain']=='refrigeration'
        response=client.post('/api/v1/runs',json={'project':project.model_dump(mode='json'),'mode':'dynamic','duration_s':.1,'dt_s':.1})
        assert response.status_code==201,response.text
        for _ in range(500):
            record=client.get('/api/v1/runs/'+response.json()['run_id']).json()
            if record['status'] in {'failed','completed'}:break
            time.sleep(.01)
        assert record['status']=='completed',record
        assert record['frame']['variables']['EV1.state.accepted_segments']==1
    result=run_module_test(ModuleTestRequest(module=module))
    assert result.frame.valid and result.execution_domain=='refrigeration'
