import json
from pathlib import Path

import pytest
from fn_engine.compiler import compile_project
from fn_engine.hydronic_boiler import definition as boiler
from fn_engine.geometry_bend import definition as bend
from fn_engine.regulating_valves import example
from fn_engine.solver import solve_steady
from fn_engine.simulation import SimulationSession


def project(module,params=None):
    p=example();p.modules=[p.modules[0],module];p.instances[1].module_id=module.id;p.instances[1].parameters=params or {}
    p.instances[2].parameters['pressure_pa']=249900.
    return p


@pytest.mark.parametrize('ratio',[0.,.25,1.])
def test_boiler_fluid_fuel_and_flue_balance(ratio):
    p=project(boiler(),{'capacity_ratio':ratio})
    v=solve_steady(compile_project(p)).variables
    q=v['Regulator.main.mass_flow_kg_s']*(v['Regulator.out0.enthalpy_j_kg']-v['Regulator.in0.enthalpy_j_kg'])
    assert q==pytest.approx(20000.*ratio,abs=1e-5)
    assert v['Regulator.fuel_power_w']==pytest.approx(q/.9,abs=1e-5)
    assert v['Regulator.flue_loss_w']+q==pytest.approx(v['Regulator.fuel_power_w'],abs=1e-5)


def test_boiler_low_flow_rejected_and_stopped_passes():
    p=project(boiler(),{'minimum_mass_flow_kg_s':100.})
    with pytest.raises(Exception,match='流量不足'):solve_steady(compile_project(p))
    p.instances[1].parameters['running']=0.
    v=solve_steady(compile_project(p)).variables
    assert v['Regulator.delivered_heat_w']==v['Regulator.fuel_power_w']==0.
    assert v['Regulator.main.mass_flow_kg_s']>0.


def test_boiler_accepted_fuel_energy():
    session=SimulationSession(compile_project(project(boiler())),.2,.1)
    try:
        session.initialize();session.advance();frame=session.advance()
        assert frame.variables['Regulator.state.heat_energy_j']==pytest.approx(4000.)
        assert frame.variables['Regulator.state.fuel_energy_j']==pytest.approx(4000./.9)
    finally:session.close()


def test_boiler_active_heat_cannot_be_silently_disabled():
    p=project(boiler())
    p.solver.thermal=False
    with pytest.raises(Exception,match='热联算'):solve_steady(compile_project(p))


@pytest.mark.parametrize('idle', [{'running':0.}, {'capacity_ratio':0.}])
def test_boiler_idle_allows_hydraulics_without_thermal(idle):
    p=project(boiler(),idle)
    p.solver.thermal=False
    v=solve_steady(compile_project(p)).variables
    assert v['Regulator.main.mass_flow_kg_s']>0.
    assert v['Regulator.delivered_heat_w']==v['Regulator.fuel_power_w']==0.


def test_boiler_overtemperature_rejects_without_advancing_energy():
    session=SimulationSession(compile_project(project(boiler())),.3,.1)
    try:
        session.initialize();accepted=session.advance()
        assert accepted.variables['Regulator.state.heat_energy_j']==pytest.approx(2000.)
        session.set_parameter('Supply','temperature_k',355.)
        with pytest.raises(Exception,match='温度上限'):session.advance()
        assert session.time==.1 and session.last_accepted_frame==accepted
        assert session.last_accepted_frame.variables['Regulator.state.fuel_energy_j']==pytest.approx(2000./.9)
    finally:session.close()


@pytest.mark.parametrize('angle,radius,k',[(45.,1.5,.15),(90.,1.,.5),(90.,1.25,.4),(180.,3.,.3)])
def test_geometry_tables_and_independent_local_pressure_law(angle,radius,k):
    p=project(bend(),{'angle_deg':angle,'radius_diameter_ratio':radius})
    v=solve_steady(compile_project(p)).variables
    rho=v['Regulator.in0.density_kg_m3'];speed=v['Regulator.velocity_m_s']
    assert v['Regulator.loss_coefficient']==pytest.approx(k)
    assert k*rho*speed*speed/2==pytest.approx(100.,rel=1e-6)


def test_new_seed_definitions_match_sources():
    root=Path(__file__).resolve().parents[1]/'modules'
    for m in (boiler(),bend()):
        p=root/m.id
        assert json.loads((p/'manifest.json').read_text(encoding='utf-8'))==m.model_dump(mode='json',exclude={'source','content_hash','definition_hash','package_path'})
        assert (p/'module.py').read_text(encoding='utf-8')==m.source['runtime']


@pytest.mark.parametrize('moist',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_bend_air_paths_keep_signed_pressure_and_moisture(moist,reverse):
    p=project(bend(),{'maximum_velocity_m_s':30.})
    p.fluid=p.fluid.model_copy(update={'fluid':'Air','phase_policy':'gas'})
    p.solver.moist_air=moist
    if moist:
        from fn_engine.air_models import MoistAirOptions
        p.solver.moist_air_options=MoistAirOptions()
    p.instances[0].parameters.update(pressure_pa=101325. if reverse else 101425.,humidity_ratio_kg_kg=.006)
    p.instances[2].parameters.update(pressure_pa=101425. if reverse else 101325.,humidity_ratio_kg_kg=.006)
    v=solve_steady(compile_project(p)).variables
    q=v['Regulator.main.mass_flow_kg_s']
    assert q<0 if reverse else q>0
    assert v['Regulator.actual_pressure_drop_pa']==pytest.approx(-100. if reverse else 100.,abs=1e-7)
    if moist:
        assert v['Regulator.in0.humidity_ratio_kg_kg']==pytest.approx(.006)
        assert v['Regulator.out0.humidity_ratio_kg_kg']==pytest.approx(.006)


def test_geometry_data_domain_is_not_silently_extrapolated():
    p=project(bend(),{'radius_diameter_ratio':.6,'radius_coefficient_curve':[[1,.5],[2,.3]]})
    with pytest.raises(Exception,match='禁止外推'):solve_steady(compile_project(p))
