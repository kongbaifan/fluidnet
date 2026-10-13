import math

import pytest
from scipy.optimize import brentq

from fn_engine.compiler import CompilationError, compile_project, validate_project
from fn_engine.controllers import PID
from fn_engine.examples import pid_example
from fn_engine.models import PIDController
from fn_engine.simulation import SimulationSession
from fn_engine.solver import HydraulicNotConverged, solve_dynamic

G = 9.80665


def controller(**changes):
    values = dict(id='c', measurement='x', instance_id='V1', parameter_id='opening_ratio', setpoint=10., kp=1., ki=1.,
                  sample_s=1., minimum=0., maximum=1.)
    return PIDController(**(values | changes))


def run(pid, measurements, start=0):
    return [pid.sample(float(start + t), {'x': x}) for t, x in enumerate(measurements)]


def test_integral_stops_exactly_at_saturation_and_unwinds_at_once():
    pid = PID(controller(kp=.1, ki=.3, setpoint=.6), 0.)
    outputs = run(pid, [0.] * 12)
    assert outputs[-1] == pytest.approx(1.)
    assert pid.integral == pytest.approx(1. - .1 * .6)
    # A windup-free integral leaves saturation on the first sample after the error reverses.
    assert run(pid, [1.], start=12)[0] < 1.


def test_proportional_saturation_does_not_freeze_the_integral():
    pid = PID(controller(), .5)
    # The first sample is bumpless (holds the initial output); kp·e alone already saturates afterwards.
    assert run(pid, [0.] * 3) == pytest.approx([.5, 1., 1.])
    assert run(pid, [20.], start=3)[0] == 0.


def test_proportional_level_control_keeps_the_analytic_offset():
    model = pid_example('level')
    model.controllers[0].ki = 0.
    frames = solve_dynamic(compile_project(model), 900, 1.)
    level = frames[-1].variables['T1.state.level_m']
    c = model.controllers[0]
    bias = .5 - c.kp * (c.setpoint - 1.)
    rho = frames[-1].variables['T1.state.mass_kg'] / frames[-1].variables['T1.state.volume_m3']
    # Equal Kv valves: opening·√Δp_in = 0.5·√Δp_out, with u = kp·(sp − L) + bias.
    balance = lambda L: (c.kp * (c.setpoint - L) + bias) * math.sqrt(150000 - 101325 - rho * G * L) - .5 * math.sqrt(rho * G * L)
    assert level == pytest.approx(brentq(balance, .5, 1.5), abs=2e-3)
    assert c.setpoint - level > .4
    assert frames[-1].variables['controller.level.output'] == pytest.approx(c.kp * (c.setpoint - level) + bias)


def test_integral_action_removes_the_offset():
    frames = solve_dynamic(compile_project(pid_example('level')), 900, 1.)
    assert frames[-1].variables['T1.state.level_m'] == pytest.approx(1.5, abs=5e-3)


def test_target_must_be_a_runtime_parameter():
    model = pid_example('level')
    model.controllers[0].parameter_id = 'kv_m3_h'
    with pytest.raises(CompilationError) as error:
        solve_dynamic(compile_project(model), 1., .5)
    assert error.value.diagnostic.code == 'PARAMETER_NOT_RUNTIME'


def test_limits_must_fit_the_target_range():
    model = pid_example('level')
    model.controllers[0].maximum = 2.
    with pytest.raises(CompilationError) as error:
        solve_dynamic(compile_project(model), 1., .5)
    assert error.value.diagnostic.code == 'PID_TARGET_INVALID'


@pytest.mark.parametrize('change, code', [
    ({'parameter_id': 'kv_m3_h'}, 'PARAMETER_NOT_RUNTIME'),
    ({'maximum': 2.}, 'PID_TARGET_INVALID'),
    ({'measurement': 'T1.state.no_such_value'}, 'PID_MEASUREMENT_UNKNOWN'),
    ({'measurement': 'X9.state.level_m'}, 'PID_MEASUREMENT_UNKNOWN'),
    ({'measurement': 'T1.param.level_m'}, 'PID_MEASUREMENT_UNKNOWN'),
])
def test_project_validation_reports_controller_errors(change, code):
    model = pid_example('level')
    model.controllers[0] = model.controllers[0].model_copy(update=change)
    diagnostics = validate_project(model)
    assert [d.code for d in diagnostics if d.severity == 'error'] == [code]


def test_valid_controllers_pass_project_validation():
    for kind in ('level', 'temperature'):
        assert not [d for d in validate_project(pid_example(kind)) if d.severity == 'error']


def test_controlled_parameter_rejects_manual_writes_until_manual_mode():
    session = SimulationSession(compile_project(pid_example('level')), 2., .5)
    try:
        session.advance()
        with pytest.raises(CompilationError) as error:
            session.set_parameter('V1', 'opening_ratio', .3)
        assert error.value.diagnostic.code == 'PARAMETER_CONTROLLED'
        session.update_controller('level', 'mode', 'manual')
        session.update_controller('level', 'manual_output', .3)
        frame = session.advance()
        assert frame.variables['controller.level.output'] == .3
        assert session.network.parameters['V1']['opening_ratio'] == .3
    finally:
        session.close()


def test_failed_substep_does_not_advance_the_controller(monkeypatch):
    original_sample, original_trial = PID.sample, SimulationSession._trial

    def sample_times(fail):
        times, failures = [], [fail]

        def sample(self, time_s, variables):
            times.append(time_s)
            return original_sample(self, time_s, variables)

        def trial(self, h):
            if failures[0] and self.time > 0:
                failures[0] = False
                raise HydraulicNotConverged('injected')
            return original_trial(self, h)

        monkeypatch.setattr(PID, 'sample', sample)
        monkeypatch.setattr(SimulationSession, '_trial', trial)
        frames = solve_dynamic(compile_project(pid_example('level')), 2., .5)
        assert not failures[0], 'the injected failure must have fired'
        return times, frames

    reference, _ = sample_times(False)
    retried, frames = sample_times(True)
    # t=0 is sampled once at initialisation; the halved retry of the 0.5 s step adds no sample.
    assert retried == reference == pytest.approx([0., .5, 1., 1.5])
    assert all(f.valid for f in frames)
