import json
import math
from pathlib import Path
import pytest
from fn_engine.models import ModuleDesignRequest,ModuleTestRequest,Project
from fn_engine.design import run_design
from fn_engine.bench import run_module_test
from fn_engine.packages import load_module_package
from fn_engine.compiler import compile_project
from fn_engine.solver import solve_steady
from fn_engine.catalog import catalog_map
from fn_engine.properties import property_service
from fn_engine.models import FluidConfig
ROOT=Path(__file__).resolve().parents[1]

def load(name):return load_module_package(ROOT/'modules'/name)

@pytest.mark.parametrize('name,fluid',[('design_pump','Water'),('design_pump','INCOMP::MEG[0.3]'),('design_fan','Air')])
def test_curve_design_and_real_network(name,fluid):
    m=load(name);gas=fluid=='Air';config=FluidConfig(fluid=fluid,phase_policy='gas' if gas else 'liquid')
    p={s.id:s.default for s in m.parameters};p['design_flow_m3_s']*=.8
    result=run_design(ModuleDesignRequest(module=m,parameters=p,fluid=config));p=result.parameters
    rho=property_service(config).state_pt(p['design_inlet_pressure_pa'],p['design_temperature_k']).density_kg_m3
    rise=p['design_pressure_rise_pa'] if gas else p['design_head_m']*rho*9.80665
    frame=run_module_test(ModuleTestRequest(module=m,parameters=p,fluid=config,property_coupling='node',
        inlet_pressure_pa=p['design_inlet_pressure_pa'],outlet_pressure_pa=p['design_inlet_pressure_pa']+rise,
        temperature_k=p['design_temperature_k'])).frame
    v=frame.variables
    assert v['D1.main.mass_flow_kg_s']/v['D1.in0.density_kg_m3']==pytest.approx(p['design_flow_m3_s'],rel=2e-5)
    assert v['D1.electric_power_w']>=v['D1.shaft_power_w']>0
    assert p['minimum_speed_ratio']<=p['speed_ratio']<=p['maximum_speed_ratio']

@pytest.mark.parametrize('changes',[{'design_flow_m3_s':0.},{'design_head_m':10000.},{'head_curve':[[0.,30.],[10.,35.],[25.,0.]]},{'efficiency_curve':[[0.,0.],[25.,.8]]},{'minimum_speed_ratio':1.5,'maximum_speed_ratio':.2},{'data_source':''}])
def test_curve_design_rejects_invalid_or_unreachable(changes):
    with pytest.raises(ValueError):run_design(ModuleDesignRequest(module=load('design_pump'),parameters=changes))

def test_plate_design_uses_independent_cp_then_real_water_glycol_network():
    m=load('design_plate_exchanger');p={s.id:s.default for s in m.parameters}
    hot=property_service(FluidConfig(fluid='Water',phase_policy='liquid')).state_pt(250000.,333.15)
    cold=property_service(FluidConfig(fluid='INCOMP::MEG[0.3]',phase_policy='liquid')).state_pt(250000.,293.15)
    p.update(design_hot_cp_j_kg_k=hot.specific_heat_j_kg_k,design_cold_cp_j_kg_k=cold.specific_heat_j_kg_k)
    designed=run_design(ModuleDesignRequest(module=m,parameters=p)).parameters
    bounds={}
    for side,state,fluid in [('hot',hot,'Water'),('cold',cold,'INCOMP::MEG[0.3]')]:
        area=math.pi*designed[side+'_diameter_m']**2/4
        drop=designed[side+'_loss_coefficient']*.5**2/(2*state.density_kg_m3*area**2)
        bounds[side]={'inlet_pressure_pa':250000.,'outlet_pressure_pa':250000.-drop,'inlet_temperature_k':333.15 if side=='hot' else 293.15,'outlet_temperature_k':333.15 if side=='hot' else 293.15,'fluid':{'fluid':fluid,'phase_policy':'liquid'}}
    v=run_module_test(ModuleTestRequest(module=m,parameters=designed,channel_boundaries=bounds,property_coupling='node')).frame.variables
    assert v['D1.transferred_heat_w']==pytest.approx(p['design_heat_w'],rel=3e-5)
    assert v['D1.hot.mass_flow_kg_s']*(v['D1.hot_in.enthalpy_j_kg']-v['D1.hot_out.enthalpy_j_kg'])==pytest.approx(p['design_heat_w'],rel=3e-5)

@pytest.mark.parametrize('changes',[{'design_heat_w':1e9},{'design_cold_mass_flow_kg_s':0.},{'design_hot_temperature_k':290.},{'cold_fouling_resistance_k_w':1.}])
def test_plate_infeasible_design_rejected(changes):
    with pytest.raises(ValueError):run_design(ModuleDesignRequest(module=load('design_plate_exchanger'),parameters=changes))

@pytest.mark.parametrize('name',['group_pump_branch','group_parallel_pumps','group_filter_fan'])
def test_two_frozen_group_copies_are_independent_and_roundtrip(name):
    m=load(name);air=name=='group_filter_fan';c=catalog_map();instances=[];edges=[]
    for index in (1,2):
        for suffix,pressure in [('In',101325. if air else 250000.),('Out',101375. if air else 260000.)]:
            instances.append({'id':suffix+str(index),'module_id':'source','name':suffix,'parameters':{'pressure_pa':pressure,'temperature_k':293.15}})
        instances.append({'id':'Group'+str(index),'module_id':name,'name':'组'+str(index)})
        edges.extend([{'id':'in'+str(index),'source':{'instance_id':'In'+str(index),'port_id':'out0'},'target':{'instance_id':'Group'+str(index),'port_id':'in0'}},{'id':'out'+str(index),'source':{'instance_id':'Group'+str(index),'port_id':'out0'},'target':{'instance_id':'Out'+str(index),'port_id':'out0'}}])
    project=Project(id='groups',name='独立组',modules=[c['source'],m],instances=instances,connections=edges,fluid={'fluid':'Air' if air else 'Water','phase_policy':'gas' if air else 'liquid'},solver={'property_coupling':'node'})
    baseline=solve_steady(compile_project(project)).variables
    key=next(s.id for s in m.parameters if s.id.endswith('speed_ratio'))
    project.instances[2].parameters[key]=.7
    changed=solve_steady(compile_project(project)).variables
    assert changed['Group1.in0.mass_flow_kg_s']!=pytest.approx(baseline['Group1.in0.mass_flow_kg_s'])
    assert changed['Group2.in0.mass_flow_kg_s']==pytest.approx(baseline['Group2.in0.mass_flow_kg_s'])
    restored=Project.model_validate(json.loads(project.model_dump_json()))
    assert solve_steady(compile_project(restored)).variables==changed
    assert all(child.content_hash or child.definition_hash for child in m.composite.children)


def test_library_allowlist_prefix_counts_and_shared_inventory(tmp_path):
    from fastapi.testclient import TestClient
    from fn_engine.api import create_app
    from fn_engine.equipment_library import build,LibraryRequest
    p=build(LibraryRequest(name='modular-room',prefix='BranchOwn',room_count=3,compressor_count=2))
    assert all(n.id.startswith('BranchOwn-') for n in p.instances)
    assert sum(n.module_id=='cold_room' for n in p.instances)==3
    assert sum(n.module_id=='refrigerant_compressor' for n in p.instances)==2
    assert len({n.id for n in p.instances})==len(p.instances)
    compile_project(p)
    with TestClient(create_app(data_root=tmp_path)) as c:
        assert c.get('/api/v1/equipment-library').status_code==200
        assert c.post('/api/v1/equipment-library/project',json={'name':'missing'}).status_code==422
        assert c.post('/api/v1/equipment-library/project',json={'name':'group_pump_branch','prefix':'Own'}).status_code==200


def test_coil_geometry_independent_area_pressure_basis_and_real_coil():
    from fn_engine.coil_geometry import CoilGeometryRequest,design
    p=CoilGeometryRequest();result=design(p)
    assert result.areas['water_wetted_m2']==pytest.approx(20*math.pi*.01)
    assert result.parameters['secondary_diameter_m']**2==pytest.approx(20*.01**2)
    assert result.parameters['secondary_loss_coefficient']==pytest.approx(5.)
    assert result.effective_ua_w_k<min(result.parameters['air_side_ua_w_k'],result.parameters['water_side_ua_w_k'])
    # Use the public water-coil example; geometry proposal changes the same ordinary device fields.
    from fn_engine.chiller_examples import chiller_air_example
    project=chiller_air_example()
    coil=next(n for n in project.instances if n.module_id=='water_coil');coil.parameters.update(result.parameters)
    v=solve_steady(compile_project(project)).variables
    assert all(math.isfinite(x) for x in v.values() if isinstance(x,float))

@pytest.mark.parametrize('change',[{'tube_outer_diameter_m':.009},{'fins':10000},{'air_free_area_m2':100},{'source':' '}])
def test_coil_geometry_rejects_inconsistent_geometry(change):
    from fn_engine.coil_geometry import CoilGeometryRequest
    with pytest.raises(ValueError):CoilGeometryRequest(**change)


@pytest.mark.parametrize('name',['group_secondary_exchanger','group_recovery_section'])
def test_two_dual_path_groups_remain_isolated_after_serialization(name):
    from fn_engine.equipment_library import group_example
    p=group_example(name);second=Project.model_validate_json(p.model_dump_json())
    for n in second.instances:n.id='Copy-'+n.id
    for c in second.connections:
        c.id='Copy-'+c.id;c.source.instance_id='Copy-'+c.source.instance_id;c.target.instance_id='Copy-'+c.target.instance_id
    for f in second.circuit_fluids:f.id='Copy-'+f.id;f.anchor.instance_id='Copy-'+f.anchor.instance_id
    p.instances+=second.instances;p.connections+=second.connections;p.circuit_fluids+=second.circuit_fluids
    before=solve_steady(compile_project(p)).variables
    key='Exchanger_clean_ua_w_k' if name=='group_secondary_exchanger' else 'Recovery_ua_w_k'
    p.instances[0].parameters[key]=100.
    after=solve_steady(compile_project(Project.model_validate_json(p.model_dump_json()))).variables
    output='Exchanger.transferred_heat_w' if name=='group_secondary_exchanger' else 'Recovery.recovered_heat_w'
    assert after['Equipment.'+output]!=pytest.approx(before['Equipment.'+output])
    assert after['Copy-Equipment.'+output]==pytest.approx(before['Copy-Equipment.'+output])


def test_group_accumulations_belong_to_each_copy():
    from fn_engine.equipment_library import group_example
    from fn_engine.simulation import SimulationSession
    p=group_example('group_pump_branch');session=SimulationSession(compile_project(p),.2,.1)
    try:
        session.initialize();session.advance();frame=session.advance()
        energy=frame.variables['Equipment.state.Pump.electric_energy_j']
        assert energy>0
        assert frame.variables['Equipment.state.Strainer.throughput_kg']>0
    finally:session.close()
