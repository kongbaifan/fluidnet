"""H07 conservation, mixed-volume response and transactional acceptance."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from fn_engine.buffer_example import buffer_example
from fn_engine.buffer_tank import candidate, definition
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_dynamic, solve_steady


def test_constant_cp_implicit_mixing_matches_independent_analytic_solution():
    cp = 4000.
    class Liquid:
        def state_pt(self, pressure, temperature):
            return SimpleNamespace(temperature_k=temperature, enthalpy_j_kg=cp*temperature, phase='liquid', quality=None)
    params = {p.id:p.default for p in definition().parameters}
    params.update(mass_kg=20., heat_loss_ua_w_k=25., ambient_temperature_k=290., heat_input_w=150.)
    flow, dt, old, inlet = .3, 12., 300., 330.
    expected = (20.*cp*old/dt + flow*cp*inlet + 25.*290. + 150.) / (20.*cp/dt + flow*cp + 25.)
    _, output = candidate(params,Liquid(),200000.,cp*inlet,flow,cp*old,dt)
    assert output['state.temperature_k'] == pytest.approx(expected,abs=1e-10)
    assert abs(output['energy_residual_w']) < 1e-6
    # A mixed tank's outlet remains its bulk temperature, not a plug-flow exponential profile.
    assert old < expected < inlet


@pytest.mark.parametrize('reverse',[False,True])
def test_real_liquid_flow_heats_stored_mass_and_closes_independent_balance(reverse):
    project = buffer_example()
    if reverse:
        project.instances[0].parameters['pressure_pa'] = 200000.
        project.instances[2].parameters.update(pressure_pa=201000.,temperature_k=333.15)
    session = SimulationSession(compile_project(project),10.,10.)
    try:
        first = session.initialize()
        assert first.variables['Buffer.state.temperature_k'] == pytest.approx(293.15)
        assert first.variables['Buffer.state.stored_power_w'] == 0.
        session.advance()
        last = session.snapshot()
        v = last.variables
        assert v['Buffer.mass_flow_kg_s'] < 0 if reverse else v['Buffer.mass_flow_kg_s'] > 0
        inlet, outlet = ('out0','in0') if reverse else ('in0','out0')
        power = abs(v['Buffer.mass_flow_kg_s'])*(v[f'Buffer.{inlet}.enthalpy_j_kg']-v[f'Buffer.{outlet}.enthalpy_j_kg'])
        change = v['Buffer.state.stored_energy_j']-first.variables['Buffer.state.stored_energy_j']
        assert change == pytest.approx(10.*(power-v['Buffer.ambient_heat_loss_w']),abs=.05)
        assert change/10. == pytest.approx(v['Buffer.state.stored_power_w'],abs=1e-8)
        assert v[f'Buffer.{outlet}.temperature_k'] == pytest.approx(v['Buffer.state.temperature_k'],abs=1e-7)
        assert 293.15 < v['Buffer.state.temperature_k'] < 333.15
        assert v['Buffer.state.mass_kg'] == 100.
        assert last.metrics['reference_heat_w'] == 0.
        assert abs(v['Buffer.energy_residual_w']) < 1e-5
    finally:
        session.close()


def test_zero_flow_loses_stored_energy_without_a_fictitious_boundary_flow():
    frames = solve_dynamic(compile_project(buffer_example(True)),20.,10.)
    for a,b in zip(frames,frames[1:]):
        v=b.variables
        assert abs(v['Buffer.mass_flow_kg_s']) < 1e-10
        assert v['Buffer.state.temperature_k'] < a.variables['Buffer.state.temperature_k']
        assert v['Buffer.state.stored_energy_j']-a.variables['Buffer.state.stored_energy_j'] == pytest.approx(
            -10.*v['Buffer.ambient_heat_loss_w'], abs=.01)
        assert abs(v['Supply.out0.mass_flow_kg_s']) < 1e-10
        assert abs(v['Return.out0.mass_flow_kg_s']) < 1e-10


def test_closed_loop_stores_pump_heat_without_an_invented_cold_reference():
    from test_thermal import project
    model=project([('Reference','source',{'pressure_pa':200000.,'temperature_k':293.15}),
                   ('Join','junction',{}),('Pump','pump',{}),('Buffer','closed_buffer_tank',{'mass_kg':100.})],
                  [('Reference:out0','Join:in0'),('Join:out0','Pump:in0'),('Pump:out0','Buffer:in0'),
                   ('Buffer:out0','Join:out1')],dynamic_step_s=10.,thermal_tolerance_k=1e-9)
    frames=solve_dynamic(compile_project(model),10.,10.)
    first,last=frames
    v=last.variables
    assert v['Buffer.state.temperature_k'] > first.variables['Buffer.state.temperature_k']
    assert abs(v['Reference.out0.mass_flow_kg_s']) < 1e-8
    assert last.metrics['reference_heat_w'] == 0.
    assert v['Buffer.state.stored_energy_j']-first.variables['Buffer.state.stored_energy_j'] == pytest.approx(
        10.*v['Pump.shaft_power_w'],abs=.05)


def test_trial_and_rejected_frame_do_not_modify_accepted_buffer_state(monkeypatch):
    session = SimulationSession(compile_project(buffer_example(True)),10.,10.)
    try:
        first=session.initialize()
        cells=deepcopy(session.cells)
        trial=session._trial(10.)
        assert not np.array_equal(trial[3][0],cells[0])
        assert np.array_equal(session.cells[0],cells[0]) and session.time == 0.
        original=SimulationSession.snapshot
        def invalid(self):
            frame=original(self)
            frame.valid=False
            return frame
        with monkeypatch.context() as patch:
            patch.setattr(SimulationSession,'snapshot',invalid)
            with pytest.raises(CompilationError,match='候选帧'):
                session._accept(10.,*trial)
        assert session.time == 0. and np.array_equal(session.cells[0],cells[0])
        assert session.snapshot().variables['Buffer.state.stored_energy_j'] == first.variables['Buffer.state.stored_energy_j']
        session._accept(10.,*session._trial(10.))
        assert session.time == 10. and not np.array_equal(session.cells[0],cells[0])
    finally:
        session.close()


def test_temperature_limit_rejects_candidate_without_losing_the_last_accepted_value():
    session=SimulationSession(compile_project(buffer_example(True)),10.,10.)
    try:
        session.initialize()
        accepted=deepcopy(session.cells)
        session.set_parameter('Buffer','heat_input_w',1e10)
        with pytest.raises(CompilationError) as error:
            session._trial(10.)
        assert error.value.diagnostic.code == 'BUFFER_TEMPERATURE_RANGE'
        assert session.time == 0. and np.array_equal(session.cells[0],accepted[0])
    finally:
        session.close()


def test_steady_thermal_off_gas_and_moist_domains_are_explicitly_rejected():
    project=buffer_example()
    with pytest.raises(CompilationError) as error:
        solve_steady(compile_project(project))
    assert error.value.diagnostic.code == 'BUFFER_DYNAMIC_REQUIRED'
    for thermal,moist in ((False,False),(True,True)):
        edited=project.model_copy(deep=True)
        edited.solver.thermal=thermal
        if moist:
            from fn_engine.air_models import MoistAirOptions
            edited.fluid.fluid,edited.fluid.phase_policy='Air','gas'
            edited.solver.moist_air=True
            edited.solver.moist_air_options=MoistAirOptions(contract_version=1)
        with pytest.raises(CompilationError) as error:
            compile_project(edited)
        assert error.value.diagnostic.code == 'BUFFER_DOMAIN_UNSUPPORTED'
    project.fluid.fluid,project.fluid.phase_policy='Air','gas'
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'BUFFER_LIQUID_REQUIRED'
