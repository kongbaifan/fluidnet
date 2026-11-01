"""Author-defined hydraulic laws, exercised through real Workers and network solves."""
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from fn_engine.bench import run_module_test
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import EvaluateRequest, FluidConfig, ModuleDefinition, ModuleTestRequest, NetworkRelation, Project
from fn_engine.module_contracts import ModuleCompatibilityError, check_module_compatibility
from fn_engine.module_templates import create_template
from fn_engine.module_validation import validate_module_definition
from fn_engine.packages import ModuleStore, load_module_package
from fn_engine.runtime import RuntimeErrorBase, WorkerProcess, module_definition_hash
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady

ROOT = Path(__file__).resolve().parents[1]


def author(package='porous_filter'):
    return load_module_package(ROOT / 'modules' / package)


def project_for(module, delta=130000., **options):
    boundary = catalog_map()['source']
    return Project(id='author-project', name='作者自建项目', modules=[boundary, module],
        instances=[{'id':'upstream','module_id':'source','name':'入口','parameters':{'pressure_pa':250000.}},
                   {'id':'device-custom','module_id':module.id,'name':'作者设备'},
                   {'id':'downstream','module_id':'source','name':'出口','parameters':{'pressure_pa':250000.-delta}}],
        connections=[{'id':'a','source':{'instance_id':'upstream','port_id':'out0'},'target':{'instance_id':'device-custom','port_id':'in0'}},
                     {'id':'b','source':{'instance_id':'device-custom','port_id':'out0'},'target':{'instance_id':'downstream','port_id':'out0'}}],
        solver=options)


def expected_flow(package, delta, parameters=None):
    p = {spec.id: spec.default for spec in author(package).parameters} | (parameters or {})
    if package == 'porous_filter':
        a, b = p['linear_coefficient'], p['quadratic_coefficient']
        pressure = abs(delta)/(1+p['clogging_ratio'])
        value = 2*pressure/(a+math.sqrt(a*a+4*b*pressure))
    elif p['opening_ratio'] == 0:
        return 0.
    else:
        knee = p['knee_flow_kg_s']*p['opening_ratio']
        pivot = knee*p['low_slope']
        value = abs(delta)/p['low_slope'] if abs(delta)<=pivot else knee+(abs(delta)-pivot)/p['high_slope']
    return math.copysign(value, delta)


@pytest.mark.parametrize('package', ['porous_filter', 'flow_limiter'])
@pytest.mark.parametrize('delta', [130000., -80000., 0.])
@pytest.mark.parametrize('method,mixed', [('dense',False), ('sparse',True)])
def test_author_laws_match_independent_inverse_with_real_worker(package, delta, method, mixed):
    module = author(package)
    project = project_for(module, delta, hydraulic_method=method, module_mixed_jacobian=mixed, module_cache=True,
                          series_compression=True, hydraulic_blocks=True)
    frame = solve_steady(compile_project(project))
    assert frame.valid
    assert frame.variables['device-custom.main.mass_flow_kg_s'] == pytest.approx(expected_flow(package, delta), abs=1e-7)
    assert frame.variables['device-custom.actual_drop_pa'] == pytest.approx(delta, abs=.01)
    assert frame.metrics['mass_residual_kg_s'] < 1e-7


@pytest.mark.parametrize('package', ['porous_filter', 'flow_limiter'])
def test_bench_runtime_parameter_and_accepted_state(package):
    result = run_module_test(ModuleTestRequest(module=author(package), duration_s=.2, dt_s=.1))
    assert result.frame.valid
    assert result.committed.state['transferred_mass_kg'] == pytest.approx(.2*expected_flow(package,130000.))
    session = SimulationSession(compile_project(project_for(author(package))), .3, .1)
    try:
        session.initialize()
        first = session.advance()
        parameter, value = ('clogging_ratio',1.) if package=='porous_filter' else ('opening_ratio',0.)
        session.set_parameter('device-custom', parameter, value)
        changed = session.advance()
        q = expected_flow(package,130000.,{parameter:value})
        assert changed.variables['device-custom.main.mass_flow_kg_s'] == pytest.approx(q,abs=1e-7)
        assert changed.variables['device-custom.state.transferred_mass_kg'] == pytest.approx(
            first.variables['device-custom.state.transferred_mass_kg']+.1*abs(q))
    finally:
        session.close()


def request(flow):
    return EvaluateRequest(run_id='run',instance_id='device',iteration_id=1,time_s=0.,
        trial_ports={'in0':{'pressure_pa':250000.},'out0':{'pressure_pa':120000.}},
        trial_channels={'main':{'mass_flow_kg_s':flow,'pressure_drop_pa':130000.}})


def test_cache_key_tracks_flow_even_when_pressures_time_and_state_are_identical():
    module = author()
    runner = WorkerProcess(module,{p.id:p.default for p in module.parameters},FluidConfig(),cache_enabled=True)
    try:
        runner.initialize()
        for _ in range(3):
            first = runner.evaluate(request(1.))
        assert first.relations[0].parameters['pressure_drop_pa'] == 16000.
        assert runner._parent_cache.hits > 0
        second = runner.evaluate(request(2.))
        assert second.relations[0].parameters['pressure_drop_pa'] == 40000.
        assert runner.state['transferred_mass_kg'] == 0.
    finally:
        runner.close()


@pytest.mark.parametrize('replacement,code', [
    ("drop = -flow", 'MODULE_PRESSURE_DROP_ACTIVE'),
    ("flow = ctx.channel('main').mass_flow_kg_s; ctx.channels['main'].mass_flow_kg_s = 123", 'MODULE_TRIAL_INPUT_MUTATION'),
    ("raise ValueError('作者公式错误')", 'MODULE_RUNTIME_ERROR'),
])
def test_invalid_author_response_has_actionable_failure(replacement, code):
    module = author()
    source = module.source['runtime']
    if replacement.startswith('drop ='):
        source = source.replace("ctx.net.pressure_drop(channel='main', pressure_drop_pa=drop)",
                                replacement+"\n        ctx.net.pressure_drop(channel='main', pressure_drop_pa=drop)")
    else:
        source = source.replace("flow = ctx.channel('main').mass_flow_kg_s", replacement)
    module = module.model_copy(update={'source':{'runtime':source},'content_hash':None,'definition_hash':None})
    runner = WorkerProcess(module,{p.id:p.default for p in module.parameters},FluidConfig())
    try:
        runner.initialize()
        with pytest.raises(RuntimeErrorBase) as caught:
            runner.evaluate(request(1.))
        assert caught.value.code == code
        if replacement.startswith('raise'):
            assert caught.value.diagnostics[0].source_line is not None
            assert caught.value.replay['channels']['main']['mass_flow_kg_s'] == 1.
    finally:
        runner.close()


def test_old_sdk_cannot_claim_new_relation_and_old_evaluate_wire_is_unchanged():
    module = author()
    module.sdk.api_version='0.7.0'
    with pytest.raises(ModuleCompatibilityError,match='net.pressure_drop'):
        check_module_compatibility(module)
    module.sdk.capabilities.remove('net.pressure_drop')
    invalid = validate_module_definition(module)
    assert not invalid.valid
    assert any(d.code=='MODULE_CAPABILITY_UNSUPPORTED' and d.source_line for d in invalid.diagnostics)
    legacy = EvaluateRequest(run_id='old',instance_id='old',iteration_id=0,time_s=0.)
    assert 'trial_channels' not in legacy.model_dump(mode='json')


@pytest.mark.parametrize('value', [True,float('nan'),float('inf')])
def test_pressure_drop_rejects_invalid_numeric_values(value):
    with pytest.raises(ValidationError):
        NetworkRelation(relation_id='main',channel='main',kind='pressure_drop',parameters={'pressure_drop_pa':value})


def test_multiple_channels_keep_cross_flow_dependence_in_sparse_mixed_solver():
    module = author()
    payload = module.model_dump(mode='json',exclude={'content_hash','definition_hash'})
    payload['id']='cross-coupled-author'
    payload['ports']=[{'id':side+suffix,'label':side+suffix,'direction':'in' if suffix=='in' else 'out','circuit':side}
                      for side in ('a','b') for suffix in ('in','out')]
    payload['channels']=[{'id':side,'name':side,'input_port':side+'in','output_port':side+'out','relation':'resistance','solver_model':'generic'}
                         for side in ('a','b')]
    payload['variables']=[]
    payload['source']={'runtime':'''class Module:
    def initialize(self,ctx): pass
    def evaluate(self,ctx):
        a,b=ctx.channel('a').mass_flow_kg_s,ctx.channel('b').mass_flow_kg_s
        ctx.net.pressure_drop(channel='a',pressure_drop_pa=10000*a*(1+b*b))
        ctx.net.pressure_drop(channel='b',pressure_drop_pa=20000*b*(1+a*a))
    def commit_step(self,ctx,dt): pass
    def observe(self,ctx): pass
    def finalize(self,ctx): pass
'''}
    # Independently chosen solution a=1, b=2 gives drops 50 kPa / 80 kPa.
    module = ModuleDefinition.model_validate(payload)
    result = run_module_test(ModuleTestRequest(module=module,channel_boundaries={
        'a':{'inlet_pressure_pa':170000.,'outlet_pressure_pa':120000.},
        'b':{'inlet_pressure_pa':200000.,'outlet_pressure_pa':120000.}}))
    assert result.frame.variables['D1.a.mass_flow_kg_s'] == pytest.approx(1.,abs=1e-6)
    assert result.frame.variables['D1.b.mass_flow_kg_s'] == pytest.approx(2.,abs=1e-6)
    # Bench uses default dense; also explicitly verify the sparse grouping pattern.
    from fn_engine.solver import jacobian_pattern
    from fn_engine.bench import bench_channels
    assert len(bench_channels(module))==2
    # Construct the same four-boundary project to exercise full sparse/mixed differences.
    boundary = catalog_map()['source']
    project = Project(id='cross',name='cross',modules=[module,boundary],instances=[
        {'id':'D','module_id':module.id,'name':'cross'}, *[
        {'id':key,'module_id':'source','name':key,'parameters':{'pressure_pa':pressure}}
        for key,pressure in [('ai',170000.),('ao',120000.),('bi',200000.),('bo',120000.)]]],
        connections=[{'id':key,'source':{'instance_id':key,'port_id':'out0'},'target':{'instance_id':'D','port_id':port}}
                     for key,port in [('ai','ain'),('ao','aout'),('bi','bin'),('bo','bout')]],
        solver={'hydraulic_method':'sparse','module_mixed_jacobian':True,'module_cache':True})
    network = compile_project(project)
    pattern = jacobian_pattern(network,[],[],{'D':object()})
    assert pattern.toarray().tolist()==[[1,1],[1,1]]
    frame=solve_steady(network)
    assert frame.variables['D.a.mass_flow_kg_s'] == pytest.approx(1.,abs=1e-6)
    assert frame.variables['D.b.mass_flow_kg_s'] == pytest.approx(2.,abs=1e-6)


def test_two_modules_batch_workers_and_package_version_round_trip(tmp_path):
    modules=[author('porous_filter'),author('flow_limiter')]
    project=project_for(modules[0])
    project.modules.append(modules[1])
    data=project.model_dump(mode='json')
    data['instances'].append({'id':'other','module_id':'flow_limiter','name':'other'})
    data['connections'][1]['source']={'instance_id':'other','port_id':'out0'}
    data['connections'].append({'id':'between','source':{'instance_id':'device-custom','port_id':'out0'},
                               'target':{'instance_id':'other','port_id':'in0'}})
    data['solver'].update(batch_modules=True,module_parallelism=2,module_cache=True,hydraulic_method='sparse',module_mixed_jacobian=True)
    project=Project.model_validate(data)
    frame=solve_steady(compile_project(project))
    assert frame.valid
    flow=frame.variables['device-custom.main.mass_flow_kg_s']
    assert flow==pytest.approx(frame.variables['other.main.mass_flow_kg_s'],abs=1e-8)
    assert frame.variables['device-custom.actual_drop_pa']+frame.variables['other.actual_drop_pa']==pytest.approx(130000.,abs=.01)
    from fn_engine.models import ModuleSaveRequest
    store=ModuleStore(ROOT/'modules',tmp_path)
    fresh=create_template('custom_pressure_drop','entirely_user_named','任意作者名称')
    saved=store.save(ModuleSaveRequest(module=fresh,expected_latest_version=0))
    restored=store.get(fresh.id,saved.module.version).module
    assert module_definition_hash(restored)==module_definition_hash(saved.module)
    assert solve_steady(compile_project(project_for(restored))).valid


def test_failed_formula_keeps_last_accepted_time_and_mass():
    module=author()
    source=module.source['runtime'].replace("flow = ctx.channel('main').mass_flow_kg_s",
        "if ctx.time_s > .100001: raise ValueError('公式在此工况不可用')\n        flow = ctx.channel('main').mass_flow_kg_s")
    module=module.model_copy(update={'source':{'runtime':source},'content_hash':None,'definition_hash':None})
    session=SimulationSession(compile_project(project_for(module)),.3,.1)
    try:
        session.initialize()
        accepted=session.advance()
        mass=accepted.variables['device-custom.state.transferred_mass_kg']
        with pytest.raises(ValueError,match='公式在此工况不可用'):
            session.advance()
        assert session.time==pytest.approx(.1)
        assert session.last_accepted_frame.variables['device-custom.state.transferred_mass_kg']==mass
        assert session.runners['device-custom'].state['transferred_mass_kg']==mass
    finally:
        session.close()


def test_new_law_rejects_missing_trial_flow_and_unsupported_air_domain():
    module=author()
    runner=WorkerProcess(module,{p.id:p.default for p in module.parameters},FluidConfig())
    try:
        runner.initialize()
        with pytest.raises(RuntimeErrorBase) as caught:
            runner.evaluate(request(1.).model_copy(update={'trial_channels':{}}))
        assert caught.value.code=='MODULE_TRIAL_FLOW_REQUIRED'
    finally:
        runner.close()
    project=project_for(module,moist_air=True,moist_air_options={'contract_version':1},property_coupling='node')
    project.fluid=FluidConfig(fluid='Air',phase_policy='gas')
    from fn_engine.compiler import CompilationError
    with pytest.raises(CompilationError) as caught:
        compile_project(project)
    assert caught.value.diagnostic.code=='MODULE_PRESSURE_DROP_DOMAIN_UNSUPPORTED'
