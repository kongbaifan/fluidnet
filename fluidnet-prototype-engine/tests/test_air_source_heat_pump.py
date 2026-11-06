"""Heating is solved from a real refrigerant cycle and both finite-capacity heat exchangers."""
import math

import pytest
from scipy.optimize import least_squares

from fn_engine.air_source_heat_pump import definition, evaluate_heat_pump
from fn_engine.models import FluidConfig
from fn_engine.properties import property_service
from fn_engine.refrigeration.cycle import cycle_rates, rated_displacement, DeviceRangeError
from fn_engine.water_chiller import refrigerant_service
from fn_engine.compiler import compile_project, CompilationError
from fn_engine.solver import solve_steady
from fn_engine.simulation import SimulationSession
from test_air_water_chiller import project as chilled_project

P={p.id:p.default for p in definition().parameters}
WATER=property_service(FluidConfig(fluid='Water',phase_policy='liquid'))


def run(t=308.15,flow=.4,**params):
    inlet=WATER.state_pt(250000.,t)
    return inlet,evaluate_heat_pump(inlet,flow,P|params,WATER,249000.,check=True)


def project(**params):
    p=chilled_project();p.modules[-1]=definition()
    next(n for n in p.instances if n.id=='Return').parameters['temperature_k']=308.15
    next(n for n in p.instances if n.id=='Supply').parameters['temperature_k']=313.15
    machine=next(n for n in p.instances if n.id=='AC-Chiller');machine.module_id='air_source_heat_pump'
    machine.parameters={'diameter_m':.025,'loss_coefficient':20.,**params}
    return p


def test_independent_three_equation_heating_solution_and_energy():
    inlet,r=run();v=r['outputs'];service=refrigerant_service(P);displacement=rated_displacement(service,P)
    cw=.4*inlet.specific_heat_j_kg_k;ca=8.*1006.;gw=cw*(1-math.exp(-6000./cw));ga=ca*(1-math.exp(-6000./ca))
    target=.4*(WATER.state_pt(249000.,313.15).enthalpy_j_kg-inlet.enthalpy_j_kg)
    def balance(x):
        te,tc,load=x;rates=cycle_rates(service,P,displacement,te,tc,load)
        return [(ga*(293.15-te)-rates['cooling_w'])/1000.,(gw*(tc-308.15)-rates['rejection_w'])/1000.,(rates['rejection_w']-target)/1000.]
    ref=least_squares(balance,[290.,315.,.5],xtol=1e-13,ftol=1e-13,gtol=1e-13)
    assert max(abs(x) for x in ref.fun)<1e-8
    assert [v['evaporating_temperature_k'],v['condensing_temperature_k'],v['load_ratio']]==pytest.approx(ref.x,abs=1e-6)
    assert v['heating_power_w']==pytest.approx(v['air_heat_extracted_w']+v['shaft_power_w'])
    assert v['electric_power_w']==pytest.approx(v['compressor_electric_power_w']+v['fan_power_w'])
    assert .4*(r['outlet_h']-inlet.enthalpy_j_kg)==pytest.approx(v['heating_power_w'])


def test_capacity_limit_and_weather_change_are_cycle_results():
    inlet,result=run(t=303.15,flow=1.);v=result['outputs']
    assert v['capacity_limited'] and v['load_ratio']==1.
    assert WATER.state_ph(249000.,result['outlet_h']).temperature_k < 313.15
    colder=run(air_inlet_temperature_k=288.15)[1]['outputs']
    warmer=run(air_inlet_temperature_k=298.15)[1]['outputs']
    assert warmer['cop']>colder['cop']


def test_frost_condensation_zero_air_and_idle_are_explicit():
    for updates,pattern in [({'air_inlet_temperature_k':270.15},'低于|包络'),({'air_dew_point_k':292.15},'露点'),({'fan_ratio':0.},'空气流量')]:
        with pytest.raises(DeviceRangeError,match=pattern):run(**updates)
    inlet,result=run(running=0.,fan_ratio=0.)
    assert result['outlet_h']==inlet.enthalpy_j_kg and result['outputs']['electric_power_w']==0.


def test_real_liquid_network_and_final_flow_protection():
    f=solve_steady(compile_project(project()));v=f.variables
    assert f.valid and v['AC-Chiller.heating_power_w']>0
    assert v['AC-Chiller.out0.temperature_k']>v['AC-Chiller.in0.temperature_k']
    with pytest.raises(CompilationError,match='最小运行值'):
        solve_steady(compile_project(project(water_min_flow_kg_s=v['AC-Chiller.mass_flow_kg_s']*1.01)))


def test_heating_and_electric_ledgers_accept_once():
    session=SimulationSession(compile_project(project()),2.,1.)
    try:
        session.initialize();frames=[session.advance(),session.advance()]
        for field,power in [('heating_energy_j','heating_power_w'),('electric_energy_j','electric_power_w')]:
            assert frames[-1].variables['AC-Chiller.state.'+field]==pytest.approx(sum(f.variables['AC-Chiller.'+power] for f in frames))
    finally:session.close()


def test_dew_point_guard_uses_the_final_density_coupled_point():
    # The first inner solve has Te=292.46080276 K, but final Te=292.46255358 K.
    # This dew point lies between them; only the actual converged point is admissible evidence.
    frame=solve_steady(compile_project(project(air_dew_point_k=292.4615)))
    assert frame.valid
    assert frame.variables['AC-Chiller.evaporating_temperature_k']>292.4615
    with pytest.raises(CompilationError,match='露点'):
        solve_steady(compile_project(project(air_dew_point_k=292.463)))


def test_idle_heat_pump_does_not_query_an_unused_heating_setpoint():
    inlet=WATER.state_pt(250000.,308.15)
    class NoQuery:
        def state_pt(self,*args):raise AssertionError('idle setpoint must not invoke properties')
    for updates,flow in [({'running':0.},.4),({},0.)]:
        result=evaluate_heat_pump(inlet,flow,P|updates,NoQuery(),249000.,check=True)
        assert result['outlet_h']==inlet.enthalpy_j_kg and result['outputs']['electric_power_w']==0.
