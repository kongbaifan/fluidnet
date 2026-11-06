import math
import pytest
from CoolProp.CoolProp import PropsSI

from fn_engine.compiler import compile_project,CompilationError
from fn_engine.models import FluidConfig
from fn_engine.properties import property_service
from fn_engine.refrigeration.cycle import DeviceRangeError
from fn_engine.refrigeration.stream_devices import line_point,counterflow_heat
from fn_engine.refrigeration.stream_example import stream_example,recuperator_example
from fn_engine.solver import solve_dynamic


def test_adiabatic_laminar_pressure_drop_matches_independent_formula():
    service=property_service(FluidConfig(fluid='R134a',phase_policy='any'))
    inlet=service.state_pt(200000.,300.)
    p={'length_m':1.,'diameter_m':.05,'roughness_m':0.,'heat_loss_ua_w_k':0.,'ambient_temperature_k':300.,'segments':1}
    m=.0001
    pressure,h,row=line_point(service,p,200000.,inlet.enthalpy_j_kg,m)
    drop=128*inlet.viscosity_pa_s*p['length_m']*m/(math.pi*inlet.density_kg_m3*p['diameter_m']**4)
    assert 200000.-pressure==pytest.approx(drop,rel=1e-7)
    assert h==inlet.enthalpy_j_kg and row['heat_w']==0.


def test_counterflow_equal_capacity_limit_and_zero_flow():
    assert counterflow_heat(100.,200.,200.,310.,280.)==pytest.approx(200.*(1./3.)*30.)
    assert counterflow_heat(100.,0.,200.,310.,280.)==0.


def test_real_suction_enthalpy_changes_compressor_work_and_enters_the_energy_ledger():
    project=stream_example();network=compile_project(project)
    frames=solve_dynamic(network,30.,10.);v=frames[-1].variables
    assert v['Compressor.inlet_enthalpy_j_kg']==v['SuctionLine.outlet_enthalpy_j_kg']
    assert v['Compressor.inlet_enthalpy_j_kg']>v['Low.vapor_enthalpy_j_kg']
    assert v['Compressor.inlet_pressure_pa']<v['Low.state.pressure_pa']
    ps,h,pd=v['Compressor.inlet_pressure_pa'],v['Compressor.inlet_enthalpy_j_kg'],v['Compressor.outlet_pressure_pa']
    entropy=PropsSI('S','P',ps,'H',h,'R134a');his=PropsSI('H','P',pd,'S',entropy,'R134a')
    expected=v['Compressor.mass_flow_kg_s']*(his-h)/v['Compressor.param.isentropic_efficiency']
    assert v['Compressor.shaft_power_w']==pytest.approx(expected,rel=1e-7)
    assert abs(frames[-1].metrics['energy_residual_j'])<.05
    assert abs(frames[-1].metrics['mass_residual_kg_circuit0'])<1e-8


def test_external_subcooler_enthalpy_reaches_the_throttled_outlet():
    v=solve_dynamic(compile_project(stream_example(True)),10.,10.)[-1].variables
    assert v['Valve.inlet_enthalpy_j_kg']==v['Subcooler.outlet_enthalpy_j_kg']
    assert v['Valve.outlet_enthalpy_j_kg']==v['Valve.inlet_enthalpy_j_kg']
    assert v['Valve.inlet_enthalpy_j_kg']<v['High.liquid_enthalpy_j_kg']


def test_recuperator_exchanges_equal_heat_between_real_streams():
    frames=solve_dynamic(compile_project(recuperator_example()),10.,10.);v=frames[-1].variables
    q=v['Recuperator.heat_w'];assert q>0.
    for side,sign in [('hot',-1.),('cold',1.)]:
        prefix='Recuperator.'+side+'_'
        assert v[prefix+'mass_flow_kg_s']*(v[prefix+'outlet_enthalpy_j_kg']-v[prefix+'inlet_enthalpy_j_kg'])==pytest.approx(sign*q,abs=1e-7)
    assert v['Compressor.inlet_enthalpy_j_kg']==v['Recuperator.cold_outlet_enthalpy_j_kg']
    assert v['Valve.inlet_enthalpy_j_kg']==v['Recuperator.hot_outlet_enthalpy_j_kg']
    assert abs(frames[-1].metrics['energy_residual_j'])<.05


def test_saturated_liquid_with_unheated_pressure_drop_cannot_be_a_single_phase_line():
    service=property_service(FluidConfig(fluid='R134a',phase_policy='any'))
    inlet=service.state_tq(308.15,0.)
    p={'length_m':10.,'diameter_m':.01,'roughness_m':1e-5,'heat_loss_ua_w_k':0.,'ambient_temperature_k':308.15,'segments':4}
    with pytest.raises(DeviceRangeError) as exc:line_point(service,p,inlet.pressure_pa,inlet.enthalpy_j_kg,.03)
    assert exc.value.code=='REFRIGERANT_LINE_PHASE'


def test_legacy_compressor_cannot_silently_ignore_a_stream_pipe():
    from fn_engine.catalog import catalog_map
    p=stream_example();c=next(i for i in p.instances if i.id=='Compressor');c.module_id='refrigerant_compressor'
    p.modules=[m for key,m in catalog_map().items() if key in {i.module_id for i in p.instances}]
    with pytest.raises(CompilationError):compile_project(p)


def test_arbitrary_ids_keep_heat_and_pressure_routing():
    project=recuperator_example();mapping={i.id:'Custom-'+i.id for i in project.instances}
    for i in project.instances:i.id=mapping[i.id]
    for c in project.connections:
        c.source.instance_id=mapping[c.source.instance_id];c.target.instance_id=mapping[c.target.instance_id]
    project.instances.reverse();project.connections.reverse()
    f=solve_dynamic(compile_project(project),5.,5.)[-1]
    assert f.valid and f.variables['Custom-Valve.inlet_enthalpy_j_kg']==f.variables['Custom-Recuperator.hot_outlet_enthalpy_j_kg']
    assert abs(f.metrics['energy_residual_j'])<.05


def test_large_suction_drop_reduces_flow_instead_of_rejecting_an_invalid_initial_guess():
    from scipy.optimize import brentq
    from fn_engine.refrigeration.devices import vessel_initial,vessel_state
    from fn_engine.refrigeration.stream_devices import compressor_point
    project=stream_example()
    next(i for i in project.instances if i.id=='SuctionLine').parameters.update(length_m=100.,diameter_m=.01,heat_loss_ua_w_k=0.)
    network=compile_project(project);p=network.parameters;service=property_service(project.fluid)
    low=vessel_state(service,p['Low'],*vessel_initial(service,p['Low']))
    high=vessel_state(service,p['High'],*vessel_initial(service,p['High']))
    def independent(mass):
        pressure,enthalpy,_=line_point(service,p['SuctionLine'],low.pressure_pa,low.vapor_enthalpy_j_kg,mass)
        expected,*_=compressor_point(service,p['Compressor'],pressure,enthalpy,high.pressure_pa)
        return mass-expected
    reference=brentq(independent,.004,.0042,xtol=1e-13)
    frames=solve_dynamic(network,.1,.1)
    assert frames[0].variables['Compressor.mass_flow_kg_s']==pytest.approx(reference,rel=1e-8)
    assert frames[-1].valid and abs(frames[-1].metrics['energy_residual_j'])<.05
    assert frames[0].variables['SuctionLine.outlet_pressure_pa']>0.
