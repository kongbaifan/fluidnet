"""Author-facing refrigeration boundaries and independently calculated expected flows."""
import math

import pytest

from fn_engine.bench import run_module_test
from fn_engine.models import ModuleTestRequest, ModuleTestSuiteRequest
from fn_engine.module_templates import create_template
from fn_engine.module_testing import run_module_suite
from fn_engine.properties import property_service
from fn_engine.runtime import RuntimeErrorBase


@pytest.mark.parametrize('fluid,high,low',[('Ammonia',1350000.,110000.),('CO2',3500000.,2500000.)])
@pytest.mark.parametrize('opening',[0.,.4,1.])
@pytest.mark.parametrize('characteristic',['linear','equal_percentage'])
def test_author_template_matches_independent_kv_and_isenthalpic_reference(fluid,high,low,opening,characteristic):
    module=create_template('refrigeration_throttle','author_throttle','作者设备')
    request=ModuleTestRequest(module=module,fluid={'fluid':fluid,'phase_policy':'any'},
        inlet_pressure_pa=high,outlet_pressure_pa=low,duration_s=.25,dt_s=.1,
        parameters={'opening_ratio':opening,'characteristic':characteristic,'kv_m3_h':.8,'rangeability':50.})
    result=run_module_test(request)
    liquid=property_service(request.fluid).state_pq(high,0.)
    fraction=opening if characteristic=='linear' else (50.**opening-1.)/49.
    expected=.8*fraction/3600*math.sqrt(1000*liquid.density_kg_m3*(high-low)/1e5)
    values=result.frame.variables
    assert values['D1.mass_flow_kg_s']==pytest.approx(expected,rel=1e-12,abs=1e-14)
    assert values['D1.in0.enthalpy_j_kg']==values['D1.out0.enthalpy_j_kg']==liquid.enthalpy_j_kg
    assert values['D1.in0.temperature_k']==liquid.temperature_k
    assert values['D1.state.transferred_mass_kg']==pytest.approx(expected*.25)
    assert values['D1.state.accepted_segments']==3
    assert [f.time_s for f in result.history]==[0.,.1,.2,.25]
    assert result.execution_domain=='refrigeration' and result.refrigeration_evaluation is not None


@pytest.mark.parametrize('outlet',[1350000.,1500000.])
def test_no_forward_pressure_drop_returns_zero_flow(outlet):
    result=run_module_test(ModuleTestRequest(module=create_template('refrigeration_throttle','zero_flow','零流量'),
        outlet_pressure_pa=outlet))
    assert result.frame.variables['D1.mass_flow_kg_s']==0
    assert result.frame.variables['D1.state.transferred_mass_kg']==0


def test_floating_point_duration_does_not_commit_a_duplicate_final_step():
    result=run_module_test(ModuleTestRequest(module=create_template('refrigeration_throttle','floating_end','浮点时长'),
        duration_s=3*.1,dt_s=.1))
    assert len(result.history)==4
    assert result.committed.state['accepted_segments']==3


@pytest.mark.parametrize('options',[{'moist_air':True},{'property_coupling':'node'},
    {'channel_boundaries':{'main':{}}},{'fluid':{'fluid':'Ammonia','phase_policy':'liquid'}}])
def test_incompatible_bench_options_are_rejected(options):
    module=create_template('refrigeration_throttle','bad_boundary','边界检查')
    with pytest.raises(ValueError):run_module_test(ModuleTestRequest(module=module,**options))


def test_suite_uses_effective_boundaries_and_keeps_failures_local_to_each_case():
    module=create_template('refrigeration_throttle','suite_throttle','组合检查')
    suite=run_module_suite(ModuleTestSuiteRequest(module=module,cases=[
        {'id':'defaults','assertions':[{'key':'D1.in0.pressure_pa','expected':1350000.}]},
        {'id':'bad','conditions':{'parameters':{'characteristic':'unknown'}},
         'assertions':[{'key':'D1.mass_flow_kg_s','expected':0.}]},
        {'id':'closed','conditions':{'parameters':{'opening_ratio':0.}},
         'assertions':[{'key':'D1.mass_flow_kg_s','expected':0.}]}]))
    assert [c.passed for c in suite.cases]==[True,False,True]
    assert suite.cases[1].assertions[0].status=='not_evaluated'
    assert any(d.source_line and d.phase=='evaluate' for d in suite.cases[1].diagnostics)
    explicit=run_module_suite(ModuleTestSuiteRequest(module=module,cases=[{'id':'defaults',
        'conditions':{'fluid':{'fluid':'Ammonia','phase_policy':'any'},'inlet_pressure_pa':1350000.,'outlet_pressure_pa':110000.},
        'assertions':[{'key':'D1.in0.pressure_pa','expected':1350000.}]}]))
    assert explicit.cases[0].input_hash==suite.cases[0].input_hash


@pytest.mark.parametrize('source',["ctx.var('undeclared', 1)","ctx.state['transferred_mass_kg'] = 1"])
def test_author_cannot_invent_observations_or_override_host_mass(source):
    module=create_template('refrigeration_throttle','reserved_state','状态检查')
    module.source['runtime']=module.source['runtime'].replace("ctx.state['accepted_segments'] = count+1",
        "ctx.state['accepted_segments'] = count+1\n        "+source)
    with pytest.raises(RuntimeErrorBase):run_module_test(ModuleTestRequest(module=module))
