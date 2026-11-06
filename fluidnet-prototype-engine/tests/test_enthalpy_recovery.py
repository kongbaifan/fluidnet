"""Typed two-stream vapor/enthalpy transport with independent boundary balances."""
import pytest

from fn_engine.enthalpy_recovery import definition,evaluate
from fn_engine.moist_air import MoistAirService,AirPropertyError,vapor_enthalpy
from fn_engine.compiler import compile_project,CompilationError
from fn_engine.hvac_expansion_examples import enthalpy_recovery_example
from fn_engine.solver import solve_steady
from fn_engine.simulation import SimulationSession

P={p.id:p.default for p in definition().parameters}
AIR=MoistAirService()


@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('flows',[(1.,1.),(.6,1.4),(0.,1.)])
def test_independent_dry_air_water_and_energy_accounts(reverse,flows):
    a=AIR.state_ptw(101425.,303.15,.007);b=AIR.state_ptw(101425.,283.15,.003)
    if reverse:a,b=b,a
    ma,mb=flows;r=evaluate(a,b,ma,mb,P,101325.,101325.)
    ao,bo=r.exhaust.outlet_state,r.supply.outlet_state
    vapor=.5*min(ma,mb)*(a.humidity_ratio_kg_kg-b.humidity_ratio_kg_kg)
    sensible=.65*min(ma*a.specific_heat_j_kg_dry_air_k,mb*b.specific_heat_j_kg_dry_air_k)*(a.temperature_k-b.temperature_k)
    heat=sensible+vapor*vapor_enthalpy(a.temperature_k if vapor>=0 else b.temperature_k)
    assert ma*(a.humidity_ratio_kg_kg-ao.humidity_ratio_kg_kg)==pytest.approx(vapor,abs=1e-12)
    assert mb*(bo.humidity_ratio_kg_kg-b.humidity_ratio_kg_kg)==pytest.approx(vapor,abs=1e-12)
    assert ma*(a.enthalpy_j_kg_dry_air-ao.enthalpy_j_kg_dry_air)==pytest.approx(heat,abs=1e-6)
    assert mb*(bo.enthalpy_j_kg_dry_air-b.enthalpy_j_kg_dry_air)==pytest.approx(heat,abs=1e-6)
    assert r.exhaust.water_added_kg_s+r.supply.water_added_kg_s==0
    assert r.exhaust.heat_to_air_w+r.supply.heat_to_air_w==0


def test_full_bypass_has_no_heat_or_moisture_exchange():
    a=AIR.state_ptw(101325.,303.15,.007);b=AIR.state_ptw(101325.,283.15,.003)
    r=evaluate(a,b,1.,1.,P|{'bypass_ratio':1.},101325.,101325.)
    assert r.exhaust.outputs['total_heat_w']==r.exhaust.outputs['moisture_transfer_kg_s']==0


def test_saturation_frost_and_nonmoist_domains_are_rejected():
    a=AIR.state_ptw(101325.,303.15,.025);b=AIR.state_ptw(101325.,274.15,.001)
    with pytest.raises(AirPropertyError):evaluate(a,b,1.,1.,P|{'sensible_effectiveness':.95,'moisture_effectiveness':0.},101325.,101325.)
    cold=AIR.state_ptw(101325.,268.15,.001)
    with pytest.raises(AirPropertyError,match='低于0'):evaluate(cold,b,1.,1.,P,101325.,101325.)
    p=enthalpy_recovery_example();p.solver.moist_air=False;p.solver.moist_air_options=None
    with pytest.raises(CompilationError,match='moist_air'):compile_project(p)


@pytest.mark.parametrize('reverse',[False,True])
def test_real_network_conserves_each_dry_stream_and_total_vapor_enthalpy(reverse):
    p=enthalpy_recovery_example()
    if reverse:
        for n in p.instances:
            if n.id=='supply_in':n.parameters['pressure_pa']=101325.
            if n.id=='supply_out':n.parameters['pressure_pa']=101425.
    f=solve_steady(compile_project(p));v=f.variables
    energy=water=0.
    for side in ('exhaust','supply'):
        ports=['Recovery.'+side+'_'+end for end in ('in','out')]
        assert sum(v[k+'.dry_air_mass_flow_kg_s'] for k in ports)==pytest.approx(0.,abs=1e-8)
        energy+=sum(v[k+'.mass_flow_kg_s']*v[k+'.enthalpy_j_kg'] for k in ports)
        water+=sum(v[k+'.dry_air_mass_flow_kg_s']*v[k+'.humidity_ratio_kg_kg'] for k in ports)
    assert energy==pytest.approx(0.,abs=.05);assert water==pytest.approx(0.,abs=1e-8)
    assert v['Recovery.supply_out.humidity_ratio_kg_kg'] != pytest.approx(v['Recovery.supply_in.humidity_ratio_kg_kg'])
    assert abs(f.metrics['moisture_residual_kg_s'])<1e-8


def test_water_and_energy_commit_once_after_runtime_bypass():
    session=SimulationSession(compile_project(enthalpy_recovery_example()),2.,1.)
    try:
        session.initialize();first=session.advance();session.set_parameter('Recovery','bypass_ratio',1.);second=session.advance()
        for counter,rate in [('transferred_water_kg','moisture_transfer_kg_s'),('transferred_energy_j','total_heat_w')]:
            assert second.variables['Recovery.state.'+counter]==pytest.approx(first.variables['Recovery.'+rate])
    finally:session.close()
