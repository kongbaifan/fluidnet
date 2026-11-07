"""Independent inventory and vapor/drop enthalpy books for a real pool."""
from copy import deepcopy

import pytest

from fn_engine.compiler import compile_project, CompilationError
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_dynamic, solve_steady
from fn_engine.tower_pool_example import tower_pool_example


@pytest.mark.parametrize('makeup',[False,True])
def test_real_makeup_evaporation_drift_and_pool_enthalpy_are_conserved(makeup):
    frames=solve_dynamic(compile_project(tower_pool_example(makeup)),20.,10.)
    for a,b in zip(frames,frames[1:]):
        old,v=a.variables,b.variables
        mass_net=sum(v[f'Pool.{port}.mass_flow_kg_s'] for port in ('in0','in1','out0','out1'))
        assert v['Pool.state.mass_kg']-old['Pool.state.mass_kg']==pytest.approx(10.*(mass_net-.0011),abs=1e-7)
        old_h=old['Pool.out0.enthalpy_j_kg']
        new_h=v['Pool.out0.enthalpy_j_kg']
        streams=sum(v[f'Pool.{port}.mass_flow_kg_s']*v[f'Pool.{port}.enthalpy_j_kg'] for port in ('in0','in1','out0','out1'))
        # For incoming ports use the upstream boundary liquid enthalpy, not the well-mixed pool node.
        if makeup:
            streams=v['Valve1.mass_flow_kg_s']*v['Valve1.out0.enthalpy_j_kg']+v['Valve3.mass_flow_kg_s']*new_h
        energy=v['Pool.state.mass_kg']*new_h-old['Pool.state.mass_kg']*old_h
        assert energy==pytest.approx(10.*(streams-v['Pool.evaporation_enthalpy_w']-v['Pool.drift_enthalpy_w']),abs=.02)
        assert v['Pool.state.evaporated_kg']==pytest.approx(.001*b.time_s)
        assert v['Pool.state.drift_kg']==pytest.approx(.0001*b.time_s)
        if makeup:
            assert mass_net>.0011 and v['Pool.state.mass_kg']>old['Pool.state.mass_kg']
        else:
            assert abs(mass_net)<1e-10 and v['Pool.state.level_m']<old['Pool.state.level_m']
            assert v['Pool.state.temperature_k']<old['Pool.state.temperature_k']


def test_failed_frame_keeps_inventory_and_evaporation_counters(monkeypatch):
    session=SimulationSession(compile_project(tower_pool_example()),10.,10.)
    try:
        session.initialize()
        accepted=deepcopy(session.tanks)
        trial=session._trial(10.)
        original=SimulationSession.snapshot
        def invalid(self):
            f=original(self);f.valid=False;return f
        with monkeypatch.context() as patch:
            patch.setattr(SimulationSession,'snapshot',invalid)
            with pytest.raises(CompilationError):session._accept(10.,*trial)
        assert session.time==0. and session.tanks==accepted
        assert session.snapshot().variables['Pool.state.evaporated_kg']==0.
    finally:session.close()


def test_pool_rejects_steady_instead_of_maintaining_inventory_with_a_hidden_source():
    with pytest.raises(CompilationError) as error:solve_steady(compile_project(tower_pool_example()))
    assert error.value.diagnostic.code=='POOL_DYNAMIC_REQUIRED'
