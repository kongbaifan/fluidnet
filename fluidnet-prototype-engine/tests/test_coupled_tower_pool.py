"""Humidity-driven pool inventory, water/air reference alignment and accepted ledgers."""
from copy import deepcopy

from CoolProp.CoolProp import HAPropsSI, PropsSI
import pytest

from fn_engine.compiler import CompilationError, compile_project
from fn_engine.coupled_tower_pool_example import coupled_tower_pool_example
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_dynamic


@pytest.mark.parametrize('makeup',[False,True])
def test_independent_actual_air_water_and_pool_energy_books(makeup):
    project=coupled_tower_pool_example(makeup)
    frames=solve_dynamic(compile_project(project),20.,10.)
    for a,b in zip(frames,frames[1:]):
        old,v=a.variables,b.variables
        p=101325.
        tin,w_in=298.15,.01
        md=.3/HAPropsSI('V','P',p,'T',tin,'W',w_in)
        h_in=HAPropsSI('H','P',p,'T',tin,'W',w_in)
        h_out=HAPropsSI('H','P',p,'T',v['Pool.air_outlet_temperature_k'],'W',v['Pool.air_outlet_humidity_ratio_kg_kg'])
        evaporated=md*(v['Pool.air_outlet_humidity_ratio_kg_kg']-w_in)
        assert v['Pool.evaporation_kg_s']==pytest.approx(evaporated,abs=1e-10)
        assert v['Pool.drift_kg_s']==pytest.approx(.0002*v['Pipe.mass_flow_kg_s'],abs=1e-10)
        assert v['Pool.makeup_kg_s']==pytest.approx(v['MakeupValve.mass_flow_kg_s'],abs=1e-10)
        assert v['Pool.blowdown_kg_s']==pytest.approx(v['DrainValve.mass_flow_kg_s'],abs=1e-10)
        water_net=v['Pool.makeup_kg_s']-v['Pool.blowdown_kg_s']-evaporated-v['Pool.drift_kg_s']
        assert v['Pool.state.mass_kg']-old['Pool.state.mass_kg']==pytest.approx(10.*water_net,abs=1e-7)
        if not makeup:
            assert abs(v['Pool.makeup_kg_s'])<1e-10 and v['Pool.state.mass_kg']<old['Pool.state.mass_kg']
        reference=PropsSI('H','P',101325.,'T',273.16,'Water')-4180.*.01
        water_h=v['Pool.out0.enthalpy_j_kg']
        sink=md*(h_out-h_in)+evaporated*reference+v['Pool.drift_kg_s']*water_h
        assert v['Pool.heat_rejected_w']==pytest.approx(sink,abs=2e-5)
        incoming=v['Pipe.mass_flow_kg_s']*v['Pipe.out0.enthalpy_j_kg']+v['MakeupValve.mass_flow_kg_s']*v['MakeupValve.out0.enthalpy_j_kg']
        outgoing=(v['Pump.mass_flow_kg_s']+v['DrainValve.mass_flow_kg_s'])*water_h
        energy=v['Pool.state.mass_kg']*water_h-old['Pool.state.mass_kg']*old['Pool.out0.enthalpy_j_kg']
        assert energy==pytest.approx(10.*(incoming-outgoing-sink),abs=.03)
        for state,rate in [('evaporated_kg','evaporation_kg_s'),('drift_kg','drift_kg_s'),
            ('makeup_kg','makeup_kg_s'),('blowdown_kg','blowdown_kg_s'),('heat_rejected_j','heat_rejected_w')]:
            assert v['Pool.state.'+state]-old['Pool.state.'+state]==pytest.approx(10.*v['Pool.'+rate],abs=1e-7)


def test_repeated_trial_and_rejected_frame_do_not_charge_water_or_energy_twice(monkeypatch):
    session=SimulationSession(compile_project(coupled_tower_pool_example()),10.,10.)
    try:
        initial=session.initialize()
        accepted=deepcopy(session.tanks)
        specs=deepcopy(session.network.storage)
        trial=session._trial(10.)
        session._trial(10.)
        assert session.tanks==accepted and session.network.storage==specs
        assert session.air_accumulators['Pool']['evaporated_kg']==0.
        original=SimulationSession.snapshot
        def invalid(self):
            f=original(self);f.valid=False;return f
        with monkeypatch.context() as patch:
            patch.setattr(SimulationSession,'snapshot',invalid)
            with pytest.raises(CompilationError):session._accept(10.,*trial)
        assert session.tanks==accepted and session.time==0.
        session._accept(10.,*session._trial(10.))
        last=session.snapshot()
        assert last.variables['Pool.state.evaporated_kg']==pytest.approx(10.*last.variables['Pool.evaporation_kg_s'])
        assert last.variables['Pool.state.mass_kg']!=initial.variables['Pool.state.mass_kg']
    finally:session.close()


def test_fan_stop_removes_contact_losses_and_restarts_from_the_last_pool_state():
    session=SimulationSession(compile_project(coupled_tower_pool_example(False)),20.,10.)
    try:
        session.initialize()
        session.set_parameter('Pool','fan_ratio',0.)
        first=session.advance()
        assert first.variables['Pool.evaporation_kg_s']==first.variables['Pool.drift_kg_s']==0.
        assert first.variables['Pool.heat_rejected_w']==first.variables['Pool.fan_electric_power_w']==0.
        session.set_parameter('Pool','fan_ratio',1.)
        last=session.advance()
        assert last.variables['Pool.evaporation_kg_s']>0.
        assert last.variables['Pool.state.mass_kg']<first.variables['Pool.state.mass_kg']
    finally:session.close()


def test_air_humidity_and_fan_power_change_true_water_losses_without_fixed_makeup():
    from fn_engine.coupled_tower_pool import exchange
    from fn_engine.properties import property_service
    from fn_engine.models import FluidConfig
    network=compile_project(coupled_tower_pool_example(False))
    p=network.parameters['Pool']
    water=property_service(FluidConfig(fluid='Water',phase_policy='liquid'))
    liquid=water.state_pt(111000.,303.15)
    dry=exchange(p,liquid,water,2.)
    humid=exchange(p|{'air_humidity_ratio_kg_kg':.015},liquid,water,2.)
    half=exchange(p|{'fan_ratio':.5},liquid,water,2.)
    assert dry['evaporation_kg_s']>humid['evaporation_kg_s']>0.
    assert half['evaporation_kg_s']==pytest.approx(.5*dry['evaporation_kg_s'])
    assert half['fan_electric_power_w']==pytest.approx(.125*dry['fan_electric_power_w'])
    assert 'makeup_kg_s' not in dry and 'blowdown_kg_s' not in dry
    stopped=exchange(p|{'fan_ratio':0.},liquid,water,2.)
    assert stopped['air_outlet_temperature_k']==pytest.approx(p['air_temperature_k'],abs=1e-8)
    assert stopped['air_outlet_humidity_ratio_kg_kg']==p['air_humidity_ratio_kg_kg']


def test_invalid_ambient_command_does_not_replace_parameters_or_accepted_water_inventory():
    session=SimulationSession(compile_project(coupled_tower_pool_example()),10.,10.)
    try:
        session.initialize()
        accepted=deepcopy(session.tanks)
        p=dict(session.network.parameters['Pool'])
        with pytest.raises(CompilationError):
            session.set_parameter('Pool','air_humidity_ratio_kg_kg',.05)
        assert session.network.parameters['Pool']==p and session.tanks==accepted
    finally:session.close()
