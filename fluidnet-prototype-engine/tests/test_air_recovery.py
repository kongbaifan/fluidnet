"""Two independent air streams: no moisture transfer and equal/opposite sensible heat."""
import math

import pytest

from fn_engine.compiler import compile_project
from fn_engine.hvac_expansion_examples import air_recovery_example
from fn_engine.moist_air import MoistAirService
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady


@pytest.mark.parametrize('bypass',[0.,.5,1.])
@pytest.mark.parametrize('reverse',[False,True])
def test_two_streams_conserve_dry_air_water_and_heat_against_ntu(bypass,reverse):
    p=air_recovery_example();p.instances[0].parameters['bypass_ratio']=bypass
    if reverse:
        for n in p.instances:
            if n.id=='supply_in':n.parameters['pressure_pa']=101325.
            if n.id=='supply_out':n.parameters['pressure_pa']=101425.
    f=solve_steady(compile_project(p));v=f.variables
    heat=v['Recovery.recovered_heat_w'];capacity={}
    service=MoistAirService()
    for side in ('exhaust','supply'):
        a,b='Recovery.'+side+'_in','Recovery.'+side+'_out'
        assert v[a+'.dry_air_mass_flow_kg_s']+v[b+'.dry_air_mass_flow_kg_s']==pytest.approx(0.,abs=1e-8)
        assert v[a+'.humidity_ratio_kg_kg']==pytest.approx(v[b+'.humidity_ratio_kg_kg'],abs=1e-10)
        energy=sum(v[k+'.mass_flow_kg_s']*v[k+'.enthalpy_j_kg'] for k in (a,b))
        assert energy==pytest.approx(heat if side=='exhaust' else -heat,abs=.05)
        inlet=b if side=='supply' and reverse else a
        state=service.state_ptw(v[inlet+'.pressure_pa'],v[inlet+'.temperature_k'],v[inlet+'.humidity_ratio_kg_kg'])
        capacity[side]=abs(v[inlet+'.dry_air_mass_flow_kg_s'])*state.specific_heat_j_kg_dry_air_k
    small,large=min(capacity.values()),max(capacity.values());r=small/large;ntu=1000*(1-bypass)/small
    eps=(1-math.exp(-ntu*(1+r)))/(1+r) if reverse else (1-math.exp(-ntu*(1-r)))/(1-r*math.exp(-ntu*(1-r)))
    assert heat==pytest.approx(eps*small*20.,rel=3e-5,abs=.01)
    if bypass==1.:assert heat==0.


def test_recovery_accepted_energy_and_runtime_bypass():
    session=SimulationSession(compile_project(air_recovery_example()),2.,1.)
    try:
        session.initialize();first=session.advance()
        session.set_parameter('Recovery','bypass_ratio',1.)
        second=session.advance()
        assert second.variables['Recovery.recovered_heat_w']==0.
        assert second.variables['Recovery.state.recovered_energy_j']==pytest.approx(first.variables['Recovery.recovered_heat_w'])
    finally:session.close()


def test_condensation_or_frost_is_rejected_not_silently_dried():
    p=air_recovery_example()
    for n in p.instances:
        if n.id.startswith('exhaust'):n.parameters['humidity_ratio_kg_kg']=.025
        if n.id.startswith('supply'):n.parameters['temperature_k']=274.15
    p.instances[0].parameters['ua_w_k']=10000.
    with pytest.raises(Exception,match='饱和|凝|相对湿度|SUPERSATURATION|湿度'):
        solve_steady(compile_project(p))
