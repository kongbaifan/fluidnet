"""HVAC acceptance through real Workers and networks, with independent balances."""
import math
from pathlib import Path

import pytest

from fn_engine.air_variables import collect_air_variables
from fn_engine.bench import run_module_test
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.hvac_examples import HVAC_EXAMPLES, hvac_example, meter
from fn_engine.measurements import apply_measurements
from fn_engine.models import MeasurementSpec, ModuleTestRequest, PIDController, Project, RunFrame
from fn_engine.packages import load_module_package
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady

ROOT = Path(__file__).resolve().parents[1]


def module(kind):
    return load_module_package(ROOT/'modules'/kind)


def two_boundary(kind, parameters=None, delta=10000., thermal=False):
    return Project(id='hvac-acceptance', name='暖通设备验收', modules=[catalog_map()['source'],module(kind)],
        instances=[{'id':'In','module_id':'source','name':'入口','parameters':{'pressure_pa':250000.}},
            {'id':'D','module_id':kind,'name':'设备','parameters':parameters or {}},
            {'id':'Out','module_id':'source','name':'出口','parameters':{'pressure_pa':250000.-delta}}],
        connections=[{'id':'a','source':{'instance_id':'In','port_id':'out0'},'target':{'instance_id':'D','port_id':'in0'}},
            {'id':'b','source':{'instance_id':'D','port_id':'out0'},'target':{'instance_id':'Out','port_id':'out0'}}],
        solver={'thermal':thermal,'module_cache':True,'module_mixed_jacobian':True})


@pytest.mark.parametrize('kind,position,effective',[
    ('water_balancing_valve',0.,0.),('water_balancing_valve',.5,.4),
    ('water_balancing_valve',.625,.55),('water_balancing_valve',1.,1.),
    ('water_shutoff_valve',.49,0.),('water_shutoff_valve',.5,1.)])
@pytest.mark.parametrize('delta',[10000.,-10000.])
def test_valve_characteristics_and_signed_closure(kind,position,effective,delta):
    frame=solve_steady(compile_project(two_boundary(kind,{'opening_ratio':position},delta,thermal=True)))
    v=frame.variables
    expected=math.copysign(16*effective/3600*math.sqrt(v['D.in0.density_kg_m3']*1000*abs(delta)/100000),delta)
    assert frame.valid
    assert v['D.effective_opening']==pytest.approx(effective)
    assert v['D.main.mass_flow_kg_s']==pytest.approx(expected,rel=2e-5,abs=1e-8)


@pytest.mark.parametrize('loading,multiplier',[(0.,1.),(.5,2.),(1.,3.)])
def test_filter_nominal_pressure_drop_and_loading(loading,multiplier):
    frame=solve_steady(compile_project(two_boundary('water_strainer',{'loading_ratio':loading},5000*multiplier,thermal=True)))
    v=frame.variables
    volume=v['D.main.mass_flow_kg_s']/v['D.in0.density_kg_m3']*3600
    assert volume==pytest.approx(10.,rel=2e-5)
    assert v['D.actual_drop_pa']==pytest.approx(5000*multiplier,abs=.01)


@pytest.mark.parametrize('delta',[-10000.,0.,400.,750.,1000.,1500.])
def test_check_valve_opening_pressure_and_no_reverse(delta):
    result=run_module_test(ModuleTestRequest(module=module('hvac_check_valve'),
        inlet_pressure_pa=250000.,outlet_pressure_pa=250000.-delta,duration_s=.1,dt_s=.1))
    v=result.frame.variables
    assert result.frame.valid
    assert v['D1.main.mass_flow_kg_s']>=-1e-8
    assert v['D1.flowing']==int(delta>1000.)
    assert result.committed.state['is_open']==(delta>1000.)
    if delta<=1000.:
        assert abs(v['D1.main.mass_flow_kg_s'])<1e-8


def test_check_hysteresis_is_committed_at_accepted_steps():
    session=SimulationSession(compile_project(two_boundary('hvac_check_valve',delta=1500)),.4,.1)
    try:
        session.initialize()
        first=session.advance()
        assert first.variables['D.state.is_open'] is True
        session.set_parameter('Out','pressure_pa',249250.)
        retained=session.advance()
        assert retained.variables['D.flowing']==1
        session.set_parameter('Out','pressure_pa',249600.)
        closed=session.advance()
        assert closed.variables['D.state.is_open'] is False
        assert closed.variables['D.flowing']==0
        session.set_parameter('Out','pressure_pa',249250.)
        final=session.advance()
        assert final.variables['D.flowing']==0
        expected=sum(abs(f.variables['D.main.mass_flow_kg_s'])*.1 for f in (first,retained,closed,final))
        assert final.variables['D.state.throughput_kg']==pytest.approx(expected,abs=1e-8)
    finally:
        session.close()


@pytest.mark.parametrize('delta',[10000.,-10000.])
def test_stopped_pump_is_a_passive_signed_resistance(delta):
    frame=solve_steady(compile_project(two_boundary('hvac_water_pump',{'running':0.},delta,thermal=True)))
    v=frame.variables
    expected=math.copysign(math.pi*.05**2/4*math.sqrt(2*v['D.in0.density_kg_m3']*abs(delta)/20),delta)
    assert v['D.main.mass_flow_kg_s']==pytest.approx(expected,rel=2e-5)
    assert v['D.electric_power_w']==0


def test_duty_standby_switch_closes_stopped_branch_and_commits_energy_once():
    session=SimulationSession(compile_project(hvac_example('hvac-pump-switch')),10.,1.)
    try:
        session.initialize()
        frames=[session.advance() for _ in range(10)]
        for index,f in enumerate(frames):
            v=f.variables
            active,stopped=(1,2) if index<5 else (2,1)
            assert f.valid
            assert v[f'Pump{active}.main.mass_flow_kg_s']>6
            assert abs(v[f'Pump{stopped}.main.mass_flow_kg_s'])<1e-8
            assert v[f'Check{active}.flowing']==1
            assert v[f'Check{stopped}.flowing']==0
            assert abs(v['Ref.out0.mass_flow_kg_s'])<1e-8
        for index in (1,2):
            energy=sum(f.variables[f'Pump{index}.electric_power_w'] for f in frames)
            assert frames[-1].variables[f'Pump{index}.state.electric_energy_j']==pytest.approx(energy,rel=1e-8)
    finally:
        session.close()


@pytest.mark.parametrize('opening',[0.,.5,1.])
@pytest.mark.parametrize('diverting',[False,True])
def test_three_way_endpoints_and_mass_enthalpy_conservation(opening,diverting):
    project=hvac_example('hvac-three-way-mixing')
    next(i for i in project.instances if i.id=='ThreeWay').parameters['Valve_opening_ratio']=opening
    if diverting:
        for i in project.instances:
            if i.id in ('Hot','Cold'):i.parameters['pressure_pa']=200000.
            if i.id=='Return':i.parameters.update(pressure_pa=250000.,temperature_k=303.15)
    f=solve_steady(compile_project(project))
    v=f.variables
    ports=['ThreeWay.'+p for p in ('common','a','b')]
    assert f.valid
    assert sum(v[p+'.mass_flow_kg_s'] for p in ports)==pytest.approx(0.,abs=1e-7)
    assert sum(v[p+'.mass_flow_kg_s']*v[p+'.enthalpy_j_kg'] for p in ports)==pytest.approx(0.,abs=.02)
    shut='a' if opening==0 else 'b' if opening==1 else None
    if shut:assert abs(v['ThreeWay.'+shut+'.mass_flow_kg_s'])<1e-8
    assert v['measurement.mixed-temperature']==v['ThreeWay.common.temperature_k']
    assert f.metrics['energy_residual_w']<.02


@pytest.mark.parametrize('kind',['water_tee','water_header_2','water_collector_2'])
@pytest.mark.parametrize('ideal',[False,True])
def test_three_port_header_and_tee_mixing_conservation(kind,ideal):
    p=hvac_example('hvac-three-way-mixing')
    p.controllers=[]
    p.scenarios=[]
    p.modules=[m for m in p.modules if m.id!='water_three_way_valve']+[module(kind)]
    device=next(i for i in p.instances if i.id=='ThreeWay')
    device.module_id=kind
    device.parameters={'Branch1_loss_coefficient':0.,'Branch2_loss_coefficient':0.} if ideal else {}
    # Keep unequal boundary pressures in ideal mode; boundary resistance valves
    # are required because zero-K manifolds equate connected pressures.
    if ideal:
        p.modules.append(module('water_balancing_valve'))
        from fn_engine.models import ModuleInstance,Connection
        for index in (1,2):
            iid='V'+str(index)
            p.instances.append(ModuleInstance(id=iid,name=iid,module_id='water_balancing_valve'))
            edge=p.connections[index-1]
            edge.target.instance_id,edge.target.port_id=iid,'in0'
            p.connections.append(Connection(id='v'+str(index),source={'instance_id':iid,'port_id':'out0'},
                target={'instance_id':'ThreeWay','port_id':'branch'+str(index)}))
    else:
        for edge in p.connections:
            if edge.target.instance_id=='ThreeWay':edge.target.port_id={'a':'branch1','b':'branch2'}[edge.target.port_id]
    f=solve_steady(compile_project(p))
    v=f.variables
    ports=['ThreeWay.'+x for x in ('common','branch1','branch2')]
    assert f.valid
    assert sum(v[x+'.mass_flow_kg_s'] for x in ports)==pytest.approx(0.,abs=1e-7)
    assert sum(v[x+'.mass_flow_kg_s']*v[x+'.enthalpy_j_kg'] for x in ports)==pytest.approx(0.,abs=.02)


def test_two_coil_plant_has_three_separate_balanced_circuits_and_no_hidden_makeup():
    f=solve_steady(compile_project(hvac_example('hvac-basic-plant')))
    v=f.variables
    assert f.valid
    assert v['measurement.branch1-flow']>0
    assert v['measurement.branch2-flow']>0
    assert v['Header.common.mass_flow_kg_s']==pytest.approx(v['Coil.ch1.mass_flow_kg_s']+v['Coil2.ch1.mass_flow_kg_s'],abs=1e-7)
    assert v['Chiller.cooling_power_w']==pytest.approx(v['Coil.water_heat_w']+v['Coil2.water_heat_w']+v['ChilledPump.shaft_power_w'],abs=.02)
    assert v['Tower.heat_rejected_w']==pytest.approx(v['Chiller.condenser_heat_w']+v['CoolingPump.shaft_power_w'],abs=.02)
    assert v['measurement.coil2-power']==pytest.approx(v['Coil2.water_heat_w'],abs=.02)
    for iid in ('ChilledRef','CoolingRef'):assert abs(v[iid+'.out0.mass_flow_kg_s'])<1e-8
    assert f.metrics['reference_heat_w']==0


@pytest.mark.parametrize('invalid',[
    {'sources':['NoSuch.main.mass_flow_kg_s','D.in0.density_kg_m3']},
    {'sources':['D.in0.pressure_pa','D.in0.density_kg_m3']},
    {'unit':{'quantity':'pressure','canonical_unit':'Pa','display_unit':'Pa'}},
    {'unit':{'quantity':'volume_flow','canonical_unit':'m3/s','display_unit':'m3/s','display_offset':1.}},
])
def test_meter_rejects_reference_and_unit_mistakes(invalid):
    p=two_boundary('water_balancing_valve')
    payload=meter('flow','流量','volume_flow',['D.main.mass_flow_kg_s','D.in0.density_kg_m3'],'volume_flow','m3/s').model_dump()
    payload.update(invalid)
    p.measurements=[MeasurementSpec.model_validate(payload)]
    with pytest.raises(CompilationError) as error:compile_project(p)
    assert error.value.diagnostic.code=='MEASUREMENT_INVALID'


@pytest.mark.parametrize('inputs',[[None,1000.],[1.,0.],[float('nan'),1000.],[1e308,1e-308]])
def test_unavailable_meter_is_null_with_a_diagnostic(inputs):
    p=two_boundary('water_balancing_valve')
    p.measurements=[meter('flow','流量','volume_flow',['D.main.mass_flow_kg_s','D.in0.density_kg_m3'],'volume_flow','m3/s')]
    # model_construct：NaN 帧不可能通过 RunFrame 校验，这里直接构造以覆盖 apply_measurements 的非有限值保护。
    f=RunFrame.model_construct(status='completed',valid=True,time_s=0.,diagnostics=[],
        variables=dict(zip(p.measurements[0].sources,inputs)))
    apply_measurements(p,f)
    assert f.variables['measurement.flow'] is None
    assert [d.code for d in f.diagnostics]==['MEASUREMENT_UNAVAILABLE']
    apply_measurements(p,f)
    assert len(f.diagnostics)==1


def test_public_composite_meter_catalog_recompile_and_pid_feedback():
    p=hvac_example('hvac-water-balance')
    p.controllers=[PIDController(id='dp',measurement='measurement.supply-dp',instance_id='Balance1',
        parameter_id='opening_ratio',setpoint=20000.,kp=1e-6,sample_s=.1,minimum=.1,maximum=1.,mode='manual',manual_output=.8)]
    network=compile_project(p)
    # A compiled Project retains the public alias map during revalidation.
    compile_project(network.project)
    descriptors={v.key:v for v in collect_air_variables(p)}
    assert descriptors['measurement.supply-dp'].unit.display_unit=='kPa'
    assert descriptors['controller.dp.measurement'].unit.canonical_unit=='Pa'
    session=SimulationSession(network,.2,.1)
    try:
        session.initialize()
        frame=session.advance()
        assert frame.variables['controller.dp.measurement']==pytest.approx(frame.variables['measurement.supply-dp'],rel=1e-5)
    finally:session.close()


@pytest.mark.parametrize('name',HVAC_EXAMPLES)
def test_portable_examples_are_current(name):
    import json
    expected=hvac_example(name).model_dump(mode='json')
    for definition in expected['modules']:definition['package_path']=None
    assert json.loads((ROOT/'examples/hvac-basic'/(name+'.project.json')).read_text(encoding='utf-8'))==expected
