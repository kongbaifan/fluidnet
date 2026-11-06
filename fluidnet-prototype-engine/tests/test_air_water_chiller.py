"""Air-cooled chiller: independent cycle balance and one-liquid-loop integration."""
import math

import pytest
from scipy.optimize import least_squares

from fn_engine.air_catalog import air_cooled_chiller
from fn_engine.air_water_chiller import evaluate_air_chiller
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project, CompilationError
from fn_engine.models import FluidConfig, Project
from fn_engine.properties import property_service
from fn_engine.refrigeration.cycle import cycle_rates, rated_displacement, DeviceRangeError
from fn_engine.water_chiller import refrigerant_service
from fn_engine.solver import solve_steady
from fn_engine.simulation import SimulationSession

P={p.id:p.default for p in air_cooled_chiller().parameters}
WATER=property_service(FluidConfig(fluid='Water',phase_policy='liquid'))


def point(t=285.15,mass=1.,**updates):
    inlet=WATER.state_pt(250000.,t)
    return inlet,evaluate_air_chiller(inlet,mass,P|updates,WATER,240000.,check=True)


def project(**parameters):
    catalog=catalog_map()
    return Project(id='air-chiller-open',name='风冷冷水机组单水回路',fluid=FluidConfig(fluid='Water',phase_policy='liquid'),
        modules=[catalog['source'],catalog['air_cooled_chiller']],instances=[
            {'id':'Return','module_id':'source','name':'回水','parameters':{'pressure_pa':250000.,'temperature_k':285.15}},
            {'id':'AC-Chiller','module_id':'air_cooled_chiller','name':'风冷机组','parameters':parameters},
            {'id':'Supply','module_id':'source','name':'供水出口','parameters':{'pressure_pa':249000.,'temperature_k':280.15}}],
        connections=[{'id':'a','source':{'instance_id':'Return','port_id':'out0'},'target':{'instance_id':'AC-Chiller','port_id':'in0'}},
            {'id':'b','source':{'instance_id':'AC-Chiller','port_id':'out0'},'target':{'instance_id':'Supply','port_id':'out0'}}],
        solver={'thermal':True,'property_coupling':'node'})


def test_reference_three_equations_and_air_water_energy():
    inlet,result=point();v=result['outputs']
    service=refrigerant_service(P);displacement=rated_displacement(service,P)
    ce=inlet.specific_heat_j_kg_k;ca=8.*1006.
    ge=ce*(1-math.exp(-8000./ce));ga=ca*(1-math.exp(-6000./ca))
    target=inlet.enthalpy_j_kg-WATER.state_pt(240000.,280.15).enthalpy_j_kg
    def residual(x):
        te,tc,load=x;rates=cycle_rates(service,P,displacement,te,tc,load)
        return [(ge*(285.15-te)-rates['cooling_w'])/1000.,(ga*(tc-303.15)-rates['rejection_w'])/1000.,(rates['cooling_w']-target)/1000.]
    reference=least_squares(residual,[278.,308.,.6],xtol=1e-13,ftol=1e-13,gtol=1e-13)
    assert max(abs(value) for value in reference.fun)<1e-8
    assert [v['evaporating_temperature_k'],v['condensing_temperature_k'],v['load_ratio']]==pytest.approx(reference.x,abs=1e-6)
    assert inlet.enthalpy_j_kg-result['outlet_h']==pytest.approx(v['cooling_power_w'])
    assert v['air_mass_flow_kg_s']*1006.*(v['air_outlet_temperature_k']-303.15)==pytest.approx(v['condenser_heat_w'],abs=1e-6)
    assert v['electric_power_w']==pytest.approx(v['compressor_electric_power_w']+1000.)
    assert v['condenser_heat_w']==pytest.approx(v['cooling_power_w']+v['shaft_power_w'])


def test_ambient_fan_and_low_load_average_are_explicit():
    cold=point(air_inlet_temperature_k=298.15)[1]['outputs'];hot=point(air_inlet_temperature_k=308.15)[1]['outputs']
    assert cold['system_cop']>hot['system_cop']
    v=point(t=281.15,minimum_load_ratio=.4,fan_ratio=.7)[1]['outputs']
    assert v['low_load_cycling'] and 0<v['cycling_ratio']<1
    assert v['fan_power_w']==pytest.approx(v['cycling_ratio']*1000.*.7**3)
    assert v['air_mass_flow_kg_s']*1006.*(v['air_outlet_temperature_k']-303.15)==pytest.approx(v['air_heat_rejection_w'],abs=1e-5)
    assert abs(v['air_equation_residual_w'])<1e-5


def test_stop_zero_water_and_no_air_have_defined_behavior():
    inlet,result=point(running=0.,fan_ratio=0.)
    assert result['outlet_h']==inlet.enthalpy_j_kg
    assert result['outputs']['electric_power_w']==0 and result['outputs']['air_outlet_temperature_k'] is None
    assert point(mass=0.)[1]['outputs']['cooling_power_w']==0
    with pytest.raises(DeviceRangeError,match='风机停转'):point(fan_ratio=0.)


def test_single_water_loop_and_final_minimum_flow_protection():
    p=project();f=solve_steady(compile_project(p));v=f.variables
    assert f.valid and v['AC-Chiller.cooling_power_w']>0
    flow=v['AC-Chiller.mass_flow_kg_s']
    assert solve_steady(compile_project(project(evaporator_min_flow_kg_s=flow*.99))).valid
    with pytest.raises(CompilationError,match='最小值'):solve_steady(compile_project(project(evaporator_min_flow_kg_s=flow*1.01)))
    stopped=solve_steady(compile_project(project(running=0.,evaporator_min_flow_kg_s=flow*2))).variables
    assert stopped['AC-Chiller.mass_flow_kg_s']>0 and stopped['AC-Chiller.cooling_power_w']==0


def test_counters_accumulate_total_electricity_and_fan_once():
    session=SimulationSession(compile_project(project()),2.,1.)
    try:
        session.initialize();frames=[session.advance(),session.advance()]
        for field,power in [('electric_energy_j','electric_power_w'),('fan_energy_j','fan_power_w')]:
            assert frames[-1].variables['AC-Chiller.state.'+field]==pytest.approx(sum(f.variables['AC-Chiller.'+power] for f in frames))
    finally:session.close()


def test_chiller_in_moist_air_project_keeps_air_and_liquid_circuits_separate():
    p=project();p.fluid=FluidConfig(fluid='Air',phase_policy='gas')
    from fn_engine.models import CircuitFluid, ModuleInstance, Connection, MoistAirOptions
    p.circuit_fluids=[CircuitFluid(id='water',anchor={'instance_id':'Return','port_id':'out0'},fluid={'fluid':'Water','phase_policy':'liquid'})]
    p.modules.append(catalog_map()['duct'])
    p.instances.extend([ModuleInstance(id='Fresh',name='风入口',module_id='source',parameters={'pressure_pa':101425.,'temperature_k':298.15,'humidity_ratio_kg_kg':.008}),
        ModuleInstance(id='Duct',name='风管',module_id='duct'),
        ModuleInstance(id='Exhaust',name='风出口',module_id='source',parameters={'pressure_pa':101325.,'temperature_k':298.15,'humidity_ratio_kg_kg':.008})])
    p.connections.extend([Connection(id='air1',source={'instance_id':'Fresh','port_id':'out0'},target={'instance_id':'Duct','port_id':'in0'}),
        Connection(id='air2',source={'instance_id':'Duct','port_id':'out0'},target={'instance_id':'Exhaust','port_id':'out0'})])
    p.solver.moist_air=True;p.solver.moist_air_options=MoistAirOptions(contract_version=1)
    p.solver.module_mixed_jacobian=False
    f=solve_steady(compile_project(p))
    assert f.valid and f.variables['AC-Chiller.cooling_power_w']>0
    assert f.variables['Duct.in0.humidity_ratio_kg_kg']==pytest.approx(f.variables['Duct.out0.humidity_ratio_kg_kg'])
