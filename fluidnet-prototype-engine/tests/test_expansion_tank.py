"""H08 independently audits gas pV, liquid EOS, mass exchange and compression energy."""
from copy import deepcopy

import pytest

from fn_engine.compiler import CompilationError, compile_project
from fn_engine.expansion_example import expansion_example
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_dynamic, solve_steady


def test_mass_pressure_and_full_liquid_gas_energy_balance():
    frames=solve_dynamic(compile_project(expansion_example()),3.,1.)
    first=frames[0].variables
    for a,b in zip(frames,frames[1:]):
        old,v=a.variables,b.variables
        mass=v['Expansion.state.mass_kg']
        assert mass>old['Expansion.state.mass_kg']
        assert v['Expansion.state.pressure_pa']>old['Expansion.state.pressure_pa']
        assert mass-old['Expansion.state.mass_kg']==pytest.approx(v['Expansion.state.net_inflow_kg_s'],abs=1e-8)
        assert v['Expansion.state.pressure_pa']*v['Expansion.state.gas_volume_m3']==pytest.approx(15000.,abs=1e-6)
        assert v['Expansion.state.gas_volume_m3']+v['Expansion.state.volume_m3']==pytest.approx(.1,abs=1e-10)
        incoming=v['InPipe.mass_flow_kg_s']*v['InPipe.out0.enthalpy_j_kg']
        outgoing=v['OutPipe.mass_flow_kg_s']*v['Expansion.out0.enthalpy_j_kg']
        gas_work=v['Expansion.state.gas_work_j']-old['Expansion.state.gas_work_j']
        assert gas_work<0.
        assert v['Expansion.state.internal_energy_j']-old['Expansion.state.internal_energy_j']==pytest.approx(
            incoming-outgoing+gas_work,abs=.02)
    assert frames[-1].variables['Expansion.state.temperature_k']>first['Expansion.state.temperature_k']


def test_pressure_changes_with_liquid_temperature_at_fixed_mass():
    network=compile_project(expansion_example())
    spec=next(iter(network.storage.values()))
    hot=spec.service.state_pt(spec.initial_pressure_pa,313.15)
    p,fluid,liquid,gas=spec.state(spec.initial_mass_kg,hot.enthalpy_j_kg)
    assert p>spec.initial_pressure_pa
    assert liquid+gas==pytest.approx(spec.total_volume_m3,abs=1e-10)
    assert spec.initial_mass_kg/fluid.density_kg_m3==pytest.approx(liquid)
    delta=.001
    independent=(spec.pressure(spec.initial_mass_kg+delta,hot.enthalpy_j_kg)-
                 spec.pressure(spec.initial_mass_kg-delta,hot.enthalpy_j_kg))/(2*delta)
    assert spec.pressure_slope(spec.initial_mass_kg,hot.enthalpy_j_kg)==pytest.approx(independent,rel=1e-6)


def test_draining_decompresses_gas_and_rollback_preserves_accepted_mass_and_energy(monkeypatch):
    project=expansion_example()
    project.instances[0].parameters['pressure_pa']=230000.
    session=SimulationSession(compile_project(project),1.,1.)
    try:
        initial=session.initialize()
        accepted=deepcopy(session.tanks)
        trial=session._trial(1.)
        node=next(iter(accepted))
        assert trial[2][node].mass_kg<accepted[node].mass_kg
        assert session.tanks==accepted
        original=SimulationSession.snapshot
        def invalid(self):
            frame=original(self)
            frame.valid=False
            return frame
        with monkeypatch.context() as patch:
            patch.setattr(SimulationSession,'snapshot',invalid)
            with pytest.raises(CompilationError):
                session._accept(1.,*trial)
        assert session.time==0. and session.tanks==accepted
        session._accept(1.,*session._trial(1.))
        last=session.snapshot()
        assert last.variables['Expansion.state.pressure_pa']<initial.variables['Expansion.state.pressure_pa']
        assert last.variables['Expansion.state.gas_work_j']>0.
    finally:
        session.close()


def test_storage_is_not_a_steady_pressure_source_and_rejects_full_liquid_volume():
    network=compile_project(expansion_example())
    with pytest.raises(CompilationError) as error:
        solve_steady(network)
    assert error.value.diagnostic.code=='EXPANSION_DYNAMIC_REQUIRED'
    spec=next(iter(network.storage.values()))
    with pytest.raises(CompilationError) as error:
        spec.state(spec.initial_mass_kg*.0001,spec.initial_enthalpy_j_kg)
    assert error.value.diagnostic.code=='EXPANSION_VOLUME_RANGE'
    project=expansion_example()
    project.solver.property_coupling='reference'
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code=='EXPANSION_DOMAIN_UNSUPPORTED'
