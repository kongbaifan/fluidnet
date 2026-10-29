"""T01–T04：外部流股对账、浓缩倍数、不可行工况与累计量。"""
import pytest
from CoolProp.CoolProp import HAPropsSI, PropsSI

from fn_engine.air_examples import air_example
from fn_engine.compiler import compile_project
from fn_engine.cooling_tower_moist import evaluate_tower
from fn_engine.models import FluidConfig
from fn_engine.moist_air import AirPropertyError
from fn_engine.properties import property_service
from fn_engine.simulation import SimulationSession


def setup_tower(**updates):
    network=compile_project(air_example('cooling-tower-moist'))
    service=property_service(FluidConfig(fluid='Water',phase_policy='liquid'))
    return service,service.state_pt(103325.,310.15),network.parameters['Tower']|updates


@pytest.mark.parametrize('drift,coc',[(.0002,3.),(.01,10.)])
def test_water_and_energy_from_independent_streams(drift,coc):
    service,inlet,p=setup_tower(drift_fraction=drift,cycles_of_concentration=coc)
    result=evaluate_tower(inlet,3.,p,service,101325.)
    o=result.outputs
    assert o['makeup_kg_s']==pytest.approx(o['evaporation_kg_s']+o['drift_kg_s']+o['blowdown_kg_s'])
    air_args=('P',101325.,'T',303.15,'W',.014)
    md=3./HAPropsSI('V',*air_args)
    h_air_in=HAPropsSI('H',*air_args)
    h_air_out=HAPropsSI('H','P',101325.,'T',o['air_outlet_temperature_k'],'W',o['air_outlet_humidity_ratio_kg_kg'])
    reference=PropsSI('H','P',101325.,'T',273.16,'Water')-4180*.01
    drain_h=PropsSI('H','P',101325.,'T',o['water_outlet_temperature_k'],'Water')-reference
    residual=o['heat_rejected_w']+o['makeup_kg_s']*4180*20-(o['drift_kg_s']+o['blowdown_kg_s'])*drain_h-md*(h_air_out-h_air_in)
    assert residual==pytest.approx(0,abs=1e-3)
    assert o['evaporation_kg_s']==pytest.approx(md*(o['air_outlet_humidity_ratio_kg_kg']-.014),abs=1e-10)
    assert result.concentration_limited == (drift==.01)
    assert o['approach_k']>0


def test_bypass_and_infeasible_states():
    service,inlet,p=setup_tower()
    assert evaluate_tower(inlet,0.,p,service).outputs['makeup_kg_s']==0
    assert evaluate_tower(inlet,3.,p|{'air_volume_flow_m3_s':0.},service).outputs['heat_rejected_w']==0
    bypass=evaluate_tower(inlet,3.,p|{'air_volume_flow_m3_s':0.},service,101325.)
    assert bypass.outputs['water_outlet_temperature_k']==pytest.approx(bypass.outlet_state.temperature_k,abs=1e-9)
    with pytest.raises(AirPropertyError):
        evaluate_tower(service.state_pt(101325.,290.15),3.,p,service)
    with pytest.raises(AirPropertyError):
        evaluate_tower(inlet,-1.,p,service)


def test_tower_rejects_disabled_thermal_before_starting():
    from fn_engine.compiler import CompilationError
    project=air_example('cooling-tower-moist')
    project.solver.thermal=False
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code=='TOWER_THERMAL_REQUIRED'


def test_network_tower_accumulates_only_accepted_steps():
    session=SimulationSession(compile_project(air_example('cooling-tower-moist')),2.,1.)
    try:
        session.initialize();a=session.advance();b=session.advance()
        assert b.variables['Tower.state.makeup_kg']==pytest.approx(a.variables['Tower.makeup_kg_s']+b.variables['Tower.makeup_kg_s'])
        assert b.variables['Tower.state.heat_rejected_j']==pytest.approx(a.variables['Tower.heat_rejected_w']+b.variables['Tower.heat_rejected_w'])
    finally:
        session.close()
