import pytest

from fn_engine.catalog import catalog_map
from fn_engine.composites import module_from_group
from fn_engine.compiler import compile_project
from fn_engine.models import Project, ModuleInstance, Endpoint, Connection, ModuleTestRequest
from fn_engine.module_templates import create_template,template_conditions
from fn_engine.bench import run_module_test
from fn_engine.solver import solve_steady


def test_composed_pump_valve_branch_matches_independent_pressure_balance():
    catalog=catalog_map()
    valve=create_template('managed_state','group_valve','Valve')
    project=Project(id='pump-valve',name='Pump valve',modules=[catalog['source'],catalog['pump'],valve],
        instances=[ModuleInstance(id='B1',module_id='source',name='In',parameters={'pressure_pa':200000}),
            ModuleInstance(id='P1',module_id='pump',name='Pump'),ModuleInstance(id='V1',module_id=valve.id,name='Valve'),
            ModuleInstance(id='B2',module_id='source',name='Out',parameters={'pressure_pa':200000})],
        connections=[Connection(id=str(i),source=Endpoint(instance_id=a,port_id=ap),target=Endpoint(instance_id=b,port_id=bp))
            for i,(a,ap,b,bp) in enumerate([('B1','out0','P1','in0'),('P1','out0','V1','in0'),('V1','out0','B2','out0')])])
    reference=solve_steady(compile_project(project))
    composite=module_from_group(project,['P1','V1'],'pump_valve_group','Pump valve group')
    result=run_module_test(ModuleTestRequest(module=composite,inlet_pressure_pa=200000,outlet_pressure_pa=200000))
    values=result.frame.variables
    assert values['D1.main.mass_flow_kg_s']==pytest.approx(reference.variables['V1.main.mass_flow_kg_s'],rel=1e-6)
    assert values['D1__P1.pressure_drop_pa']+values['D1__V1.main.pressure_drop_pa']==pytest.approx(0,abs=1)
    assert values['D1.main.heat_w']==pytest.approx(values['D1__P1.heat_w'],rel=1e-6,abs=1e-6)


@pytest.mark.parametrize('mode',['reference','node'])
def test_composed_dual_exchanger_distinct_fluids_preserves_heat_and_energy(mode):
    module=create_template('heat_exchanger','dual_hx','Dual HX')
    conditions=template_conditions('heat_exchanger').model_dump(mode='json')
    conditions['property_coupling']=mode
    conditions['channel_boundaries']['cold']['fluid']={'fluid':'Air','phase_policy':'gas'}
    reference=run_module_test(ModuleTestRequest(module=module,**conditions))
    original=Project(id='device-group',name='HX group',modules=[module],instances=[ModuleInstance(id='HX',module_id=module.id,name='HX')])
    composite=module_from_group(original,['HX'],'hx_group','HX group')
    boundaries={channel.id:conditions['channel_boundaries']['hot' if 'hot' in channel.input_port else 'cold'] for channel in composite.channels}
    result=run_module_test(ModuleTestRequest(module=composite,channel_boundaries=boundaries,property_coupling=mode))
    assert result.frame.variables['D1.HX.transferred_heat_w']==pytest.approx(reference.frame.variables['D1.transferred_heat_w'],rel=1e-6)
    assert sum(result.frame.variables[f'D1.{channel.id}.heat_w'] for channel in composite.channels)==pytest.approx(0,abs=1e-6)
    assert result.frame.variables['D1.state.HX.transferred_energy_j']==pytest.approx(reference.committed.state['transferred_energy_j'],rel=1e-6)
