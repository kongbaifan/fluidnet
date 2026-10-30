"""Failed thermal segments keep physics, controls, timestamps and archived frames together."""
from copy import deepcopy

import pytest

from fn_engine.compiler import compile_project
from fn_engine.models import ControlScript, PIDController, ScheduleEvent, TimeStepOptions
from fn_engine.refrigeration.examples import ideal_room_example, station_example
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed
from fn_engine.timestep import ErrorEstimate, TrialFailure


def options(max_step=10.):
    return TimeStepOptions(enabled=True, min_internal_step_s=.1, max_internal_step_s=max_step,
                           rtol=.01, temperature_atol_k=1.)


def open_session(project, duration=10., dt=10.):
    session = create_session(compile_project(project), duration, dt)
    session.initialize()
    return session


def counting_script(id='control', target='ROOM1.param.heat_input_w'):
    return ControlScript(id=id, enabled=True, sample_s=2., inputs=[], outputs=[target], source=f'''
def initialize(ctx):
    ctx.state["count"] = 0
def step(ctx, dt_s):
    ctx.state["count"] += 1
    ctx.write({target!r}, 100. * ctx.state["count"])
def finalize(ctx):
    pass
''')


@pytest.mark.parametrize('max_step, accepted_time', [(10., 0.), (2., 2.)])
def test_real_thermal_range_failure_discards_partial_segment_and_keeps_completed_segments(max_step, accepted_time):
    # Contract-valid stress input: the ideal source reaches the absolute-temperature boundary.
    # This follows the real range-check/retry path, with no mocked solver or error estimate.
    project = ideal_room_example()
    project.controllers = []
    project.instances[0].parameters.update(heat_capacity_j_k=100., wall_ua_w_k=0., roof_ua_w_k=0.,
                                           floor_ua_w_k=0., heat_input_w=0.)
    project.solver.time_step = options(max_step)
    session = open_session(project)
    try:
        with pytest.raises(SolveFailed) as caught:
            session.advance()
        assert caught.value.diagnostic.code == 'TIME_STEP_MIN_EXCEEDED'
        assert session.time == accepted_time
        assert session.temperatures['ROOM1'] == pytest.approx(263.15 - 100. * accepted_time)
        assert session.cooling_energy['COLD1'] == pytest.approx(10000. * accepted_time)
        assert session.external_energy['ROOM1'] == 0.
        assert session.step_stats.accepted == (1 if accepted_time else 0)
        assert sum(session.step_stats.sequence) == accepted_time
        assert session.step_stats.min_step_hits == 1
        assert session.step_stats.solver_failures > 0
        assert caught.value.frames == list(session.frames)
        frame = caught.value.frames[-1]
        assert frame.time_s == accepted_time
        assert frame.variables == session.snapshot().variables
        assert frame.variables['COLD1.state.cooling_energy_j'] == 10000. * accepted_time
    finally:
        session.close()


def test_station_failure_rolls_back_partial_candidates_pid_scripts_schedule_and_cache():
    project = station_example()
    project.solver.time_step = options()
    project.controllers = [PIDController(id='suction', measurement='LP1.state.pressure_pa', instance_id='K1',
        parameter_id='load_ratio', setpoint=125000., kp=-2e-4, ki=-2e-6, sample_s=2., minimum=0., maximum=1.)]
    project.control_scripts = [counting_script()]
    project.events = [ScheduleEvent(id='wet-bulb', type='set_variable', time_s=2.,
                                   key='EC1.param.wet_bulb_temperature_k', value=300.)]
    reference = open_session(project, 2., 2.)
    session = open_session(project)
    try:
        expected = reference.advance()
        original = session._trial_doubling
        accepted_candidate = False

        def fail_after_candidate(x, h):
            nonlocal accepted_candidate
            if session.time < 2.:
                return original(x, h)
            if accepted_candidate:
                raise TrialFailure('forced failure after one successful station candidate')
            if h > 1.:
                return None, ErrorEstimate(norm=4.)
            payload, error = original(x, h)
            accepted_candidate = error.norm <= 1.
            return payload, error

        session._trial_doubling = fail_after_candidate
        with pytest.raises(SolveFailed) as caught:
            session.advance()
        assert accepted_candidate
        assert caught.value.diagnostic.code == 'TIME_STEP_MIN_EXCEEDED'
        assert session.time == 2.
        assert caught.value.frames[-1].time_s == 2.
        assert caught.value.frames[-1].variables == expected.variables
        assert session.snapshot().variables == expected.variables
        assert session.network.parameters == reference.network.parameters
        assert session.revision == reference.revision
        assert session.controllers == reference.controllers
        assert session.scripts['control'].state == {'count': 1}
        assert session.scripts['control'].samples == 1
        assert session.scripts['control'].pending is None
        assert session.scripts['control'].next_s == 2.
        assert session.event_index == session.events_applied == 0
        assert session.counters == reference.counters
        assert session.step_stats.sequence == reference.step_stats.sequence
        assert session.step_stats.accepted == reference.step_stats.accepted
        assert session.march._next_h == reference.march._next_h
        assert session._jacobian == pytest.approx(reference._jacobian, rel=0, abs=0)
        # Remove the transient fault and resume from the same accepted boundary. The event and
        # control sample must be applied exactly once, matching an uninterrupted run.
        session._trial_doubling = original
        continuous = open_session(project)
        try:
            final = continuous.advance()
            resumed = session.advance()
            assert resumed.time_s == final.time_s == 10.
            assert resumed.variables == final.variables
            assert session.events_applied == continuous.events_applied == 1
        finally:
            continuous.close()
    finally:
        reference.close()
        session.close()


def test_script_accept_failure_rolls_back_physics_and_all_preceding_script_accepts():
    project = ideal_room_example()
    project.controllers = []
    project.control_scripts = [counting_script('first'), counting_script('second', 'COLD1.param.cooling_power_w')]
    project.solver.time_step = options()
    session = open_session(project)
    try:
        before = session.snapshot()
        parameters = deepcopy(session.network.parameters)
        runner = session.scripts['second']
        original = runner.accept

        def fail_after_accept():
            original()
            raise ValueError('acceptance fault after both managed script states changed')

        runner.accept = fail_after_accept
        with pytest.raises(SolveFailed, match='acceptance fault') as caught:
            session.advance()
        assert session.time == 0.
        assert session.snapshot().variables == before.variables
        assert session.network.parameters == parameters
        assert session.revision == before.parameter_revision
        assert session.cooling_energy == {'COLD1': 0.}
        assert session.external_energy == {'ROOM1': 0.}
        assert session.step_stats.accepted == 0
        for script in session.scripts.values():
            assert script.state == {'count': 0}
            assert script.pending is None and script.samples == 0
            assert script.next_s == 0. and script.last_s is None
        assert caught.value.frames == [session.frames[0]]
    finally:
        session.close()
