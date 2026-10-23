"""A0/A1: time-step error-control configuration, normalisation and the ideal-room analytic check.

No full-suite run here: these tests only cover ``backend/fn_engine/timestep.py`` and the
``thermal`` execution domain in ``refrigeration/session.py``.
"""
import json
import math

import pytest
from pydantic import ValidationError

from fn_engine.compiler import CompilationError, compile_project
from fn_engine.examples import pid_example
from fn_engine.models import Project, SolverOptions, TimeStepOptions
from fn_engine.refrigeration.examples import ideal_room_example, room_example
from fn_engine.refrigeration.session import ideal_room_analytic
from fn_engine.sessions import create_session
from fn_engine.timestep import (AdaptiveMarch, ErrorEstimate, StepController, TimeStepConfig,
                                TimeStepExhausted, TrialFailure, ensure_supported, normalized_error)


def constant_room_project(dynamic_step_s=10., time_step=None):
    """Ideal-room model with the constant-capacity source: the analytic solution is exact here."""
    project = ideal_room_example()
    project.controllers = []
    for instance in project.instances:
        if instance.id == 'COLD1':
            instance.parameters['capacity_ratio'] = 1.
    project.solver.dynamic_step_s = dynamic_step_s
    if time_step is not None:
        project.solver.time_step = time_step
    return project


def run(project, duration_s, dt_s):
    session = create_session(compile_project(project), duration_s, dt_s, keep=100000)
    frames = [session.initialize()]
    try:
        while not session.done:
            frames.append(session.advance())
    finally:
        session.close()
    return session, frames


def small_config(**changes):
    """Unit-scale configuration for the pure controller/march tests."""
    values = dict(enabled=True, mass_atol_kg=1e-9, energy_atol_j=1e-3, temperature_atol_k=1e-5,
                  rtol=1e-6, min_step_s=0.5, max_step_s=10., safety=.9, growth=2., shrink=.5)
    values.update(changes)
    return TimeStepConfig(**values)


# --- A0: configuration and validation -------------------------------------------------------------
def test_defaults_keep_the_old_fixed_step_mode():
    options = SolverOptions()
    assert options.time_step == TimeStepOptions()
    assert options.time_step.enabled is False
    # A project saved before this field existed still loads and keeps the old behaviour.
    legacy = ideal_room_example().model_dump(mode='json')
    legacy['solver'].pop('time_step')
    restored = Project.model_validate(legacy)
    assert restored.solver.time_step.enabled is False
    assert restored.solver.dynamic_step_s == ideal_room_example().solver.dynamic_step_s


def test_snapshot_keeps_every_time_step_setting():
    project = constant_room_project()
    project.solver.time_step = TimeStepOptions(enabled=True, mass_atol_kg=2e-9, energy_atol_j=2e-3,
                                               temperature_atol_k=2e-5, rtol=2e-6, min_internal_step_s=.01,
                                               max_internal_step_s=30., safety=.8, growth_factor=1.5,
                                               shrink_factor=.4)
    restored = Project.model_validate(json.loads(project.model_dump_json()))
    assert restored.solver.time_step == project.solver.time_step
    config = TimeStepConfig.from_solver(restored.solver)
    assert (config.max_step_s, config.min_step_s, config.safety, config.growth, config.shrink) == (30., .01, .8, 1.5, .4)
    # `None` follows the legacy internal step cap.
    follow = TimeStepConfig.from_solver(SolverOptions(time_step=TimeStepOptions(enabled=True)))
    assert follow.max_step_s == SolverOptions().dynamic_step_s


@pytest.mark.parametrize('field', ['mass_atol', 'energy_atol', 'temperature_atol', 'atol', 'mass_atol_j',
                                   'energy_atol_kg', 'temperature_atol_c'])
def test_tolerances_must_name_their_unit(field):
    with pytest.raises(ValueError) as error:
        TimeStepOptions(**{field: 1e-3})
    assert '单位' in str(error.value)


@pytest.mark.parametrize('field', ['mass_atol_kg', 'energy_atol_j', 'temperature_atol_k', 'rtol',
                                   'min_internal_step_s', 'max_internal_step_s', 'safety'])
@pytest.mark.parametrize('value', [0., -1.])
def test_non_positive_tolerances_are_rejected(field, value):
    with pytest.raises(ValidationError):
        TimeStepOptions(**{field: value})


def test_minimum_step_must_be_below_maximum_step():
    with pytest.raises(ValidationError) as error:
        TimeStepOptions(min_internal_step_s=2., max_internal_step_s=1.)
    assert '最小步长' in str(error.value)


@pytest.mark.parametrize('domain', ['fluid', 'cold_store'])
def test_unsupported_execution_domains_are_rejected(domain):
    with pytest.raises(CompilationError) as error:
        ensure_supported(domain)
    assert error.value.diagnostic.code == 'TIMESTEP_DOMAIN_UNSUPPORTED'
    if domain == 'fluid':
        project = pid_example('level')
        project.solver.time_step = TimeStepOptions(enabled=True)
        with pytest.raises(CompilationError) as error:
            create_session(compile_project(project), 10., 1.)
        assert error.value.diagnostic.code == 'TIMESTEP_DOMAIN_UNSUPPORTED'
    else:
        project = room_example()
        project.solver.time_step = TimeStepOptions(enabled=True)
        with pytest.raises(CompilationError) as error:
            create_session(compile_project(project), 10., 1.)
        assert error.value.diagnostic.code == 'TIMESTEP_DOMAIN_UNSUPPORTED'


def test_effective_minimum_above_dynamic_step_is_rejected():
    with pytest.raises(ValueError) as error:
        TimeStepConfig.from_solver(SolverOptions(dynamic_step_s=.001,
                                                 time_step=TimeStepOptions(enabled=True, min_internal_step_s=.01)))
    assert '最小步长' in str(error.value)


# --- A1: normalisation, step proposal and the accept loop ----------------------------------------
def test_normalized_error_is_per_category_and_centered_on_the_reference():
    old = [10., 1000., 250.]
    full = [10.1, 1100., 250.1]
    fine = [10.2, 1200., 250.2]
    estimate = normalized_error(old, full, fine, categories=['mass', 'energy', 'temperature'],
                                atol={'mass': 1e-3, 'energy': 1e-2, 'temperature': 1e-3}, rtol=1e-6,
                                references=[0., 1000., 0.])
    assert estimate.by_category == {'mass': pytest.approx(0.1 / (1e-3 + 1e-6 * 10.2)),
                                    'energy': pytest.approx(100. / (1e-2 + 1e-6 * 200.)),
                                    'temperature': pytest.approx(0.1 / (1e-3 + 1e-6 * 250.2))}
    assert estimate.norm == max(estimate.by_category.values())
    # Shifting the internal-energy zero and its frozen reference together changes nothing.
    shifted = normalized_error([10., 5000., 250.], [10.1, 5100., 250.1], [10.2, 5200., 250.2],
                               categories=['mass', 'energy', 'temperature'],
                               atol={'mass': 1e-3, 'energy': 1e-2, 'temperature': 1e-3}, rtol=1e-6,
                               references=[0., 5000., 0.])
    assert shifted.norm == pytest.approx(estimate.norm)
    with pytest.raises(ValueError):
        normalized_error(old, full, fine, categories=['mass'], atol={'mass': 1e-3}, rtol=1e-6)


def test_derived_pressure_check_participates_in_the_norm():
    estimate = normalized_error([1.], [1.], [1.], categories=['mass'], atol={'mass': 1e-3}, rtol=1e-6,
                                extra={'pressure': (1e6, 1e6 + 3., 1.)})
    assert estimate.extra['pressure'] == pytest.approx(3. / (1. + 1e-6 * (1e6 + 3.)))


def test_step_proposal_is_the_frozen_formula_and_bounded():
    controller = StepController(small_config())
    assert controller.next(4., .25) == pytest.approx(4. * .9 * .25 ** -.5)
    assert controller.next(4., 0.) == pytest.approx(8.)              # zero error -> bounded growth
    assert controller.next(4., 1e-8) == pytest.approx(8.)            # growth cap
    assert controller.next(4., 1e6) == pytest.approx(2.)             # shrink floor .5
    assert controller.next(20., .25) == pytest.approx(10.)           # max step
    assert controller.shrink(8.) == pytest.approx(4.)


def test_march_accepts_only_within_tolerance_and_counts_boundaries():
    controller = AdaptiveMarch(small_config())
    accepted = []
    trial_calls = []

    def trial(h):
        trial_calls.append(h)
        return {'h': h}, ErrorEstimate(norm=0.2 if h <= 2. else 5.)

    controller.march(10., trial, lambda payload, h, error: accepted.append(h), time=0.)
    assert accepted and all(h <= 2. for h in accepted)
    assert sum(accepted) == pytest.approx(10.)
    assert controller.stats.rejected > 0 and controller.stats.accepted == len(accepted)
    assert controller.stats.sequence == pytest.approx(accepted)


def test_march_rejects_do_not_touch_any_accepted_state():
    """The loop only ever calls `accept` for error_norm <= 1 (transaction rule §12.1)."""
    march = AdaptiveMarch(small_config())
    state = {'committed': 0., 'attempts': 0}

    def trial(h):
        state['attempts'] += 1
        return h, ErrorEstimate(norm=2. if state['attempts'] < 3 else .5)

    march.march(2., trial, lambda payload, h, error: state.__setitem__('committed', state['committed'] + h), time=0.)
    assert state['committed'] == pytest.approx(2.)
    assert march.stats.rejected == 2 and march.stats.accepted > 0


def test_minimum_step_stop_is_explicit_and_keeps_the_accepted_history():
    march = AdaptiveMarch(small_config(min_step_s=1., max_step_s=10.))
    with pytest.raises(TimeStepExhausted) as error:
        march.march(10., lambda h: (h, ErrorEstimate(norm=5.)), lambda payload, h, error: None, time=100.)
    assert error.value.code == TimeStepExhausted.MINIMUM
    assert '不放宽' in str(error.value)


def test_boundary_truncated_small_step_has_its_own_diagnostic():
    march = AdaptiveMarch(small_config(min_step_s=1., max_step_s=10.))
    with pytest.raises(TimeStepExhausted) as error:
        march.march(.5, lambda h: (h, ErrorEstimate(norm=5.)), lambda payload, h, error: None, time=0.)
    assert error.value.code == TimeStepExhausted.BOUNDARY


def test_solver_failure_retries_by_shrinking_and_stops_at_the_minimum():
    march = AdaptiveMarch(small_config(min_step_s=1., max_step_s=10.))
    with pytest.raises(TimeStepExhausted) as error:
        march.march(10., lambda h: (_ for _ in ()).throw(TrialFailure('not converged')),
                    lambda payload, h, err: None, time=0.)
    assert error.value.code == TimeStepExhausted.MINIMUM
    assert march.stats.solver_failures > 0


# --- A1: ideal-room adaptive results against the analytic solution --------------------------------
def test_analytic_ideal_room_reference():
    project = constant_room_project(1.)
    session, frames = run(project, 3600., 600.)
    network = session.network
    analytic = ideal_room_analytic(network, 3600.)
    room, source = next(iter(network.room_sources.items()))
    p = network.parameters[room]
    power = network.parameters[source]['cooling_power_w']
    assert analytic[room]['cooling_energy_j'] == pytest.approx(3600. * power)
    assert analytic[room]['external_energy_j'] == pytest.approx(
        frames[-1].variables[f'{room}.state.external_energy_j'], rel=2e-4)
    assert frames[-1].variables[f'{room}.stored_energy_j'] == pytest.approx(
        p['heat_capacity_j_k'] * (analytic[room]['temperature_k'] - 273.15), rel=1e-4)
    # Analytic trajectory is an exponential from the initial state to the equilibrium.
    ua = p['wall_ua_w_k'] + p['roof_ua_w_k'] + p['floor_ua_w_k']
    equilibrium = ((p['wall_ua_w_k'] + p['roof_ua_w_k']) * p['ambient_temperature_k']
                   + p['floor_ua_w_k'] * p['ground_temperature_k'] + p['heat_input_w'] - power) / ua
    expected = equilibrium + (p['temperature_k'] - equilibrium) * math.exp(-ua / p['heat_capacity_j_k'] * 3600.)
    assert analytic[room]['temperature_k'] == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize('time_step, limit', [
    (TimeStepOptions(enabled=True, max_internal_step_s=600., rtol=1e-4, temperature_atol_k=1e-3,
                     energy_atol_j=1e-1, mass_atol_kg=1e-7), 0.2),
    (TimeStepOptions(enabled=True, max_internal_step_s=600., rtol=1e-6, temperature_atol_k=1e-5,
                     energy_atol_j=1e-3, mass_atol_kg=1e-9), 2e-2),
    (TimeStepOptions(enabled=True, max_internal_step_s=600., rtol=1e-8, temperature_atol_k=1e-7,
                     energy_atol_j=1e-5, mass_atol_kg=1e-11), 3e-3)])
def test_tightening_tolerances_lowers_the_temperature_error_monotonically(time_step, limit):
    project = constant_room_project(60., time_step)
    session, frames = run(project, 3600., 600.)
    room = next(iter(session.network.room_sources))
    analytic = ideal_room_analytic(session.network, 3600.)
    error = frames[-1].variables[f'{room}.state.temperature_k'] - analytic[room]['temperature_k']
    assert abs(error) < limit
    # Output times stay exactly on the publish grid.
    assert [frame.time_s for frame in frames] == pytest.approx([600. * i for i in range(7)])


def test_rejected_trials_are_not_written_to_the_energy_ledger():
    time_step = TimeStepOptions(enabled=True, max_internal_step_s=600., rtol=1e-8, temperature_atol_k=1e-7,
                                energy_atol_j=1e-5, mass_atol_kg=1e-11)
    project = constant_room_project(60., time_step)
    session, frames = run(project, 3600., 600.)
    assert session.step_stats.rejected > 0
    room, source = next(iter(session.network.room_sources.items()))
    power = session.network.parameters[source]['cooling_power_w']
    # Constant capacity: accepted half-steps must sum to exactly the 3600 s run.
    assert frames[-1].variables[f'{source}.state.cooling_energy_j'] == pytest.approx(power * 3600., rel=1e-12)
    analytic = ideal_room_analytic(session.network, 3600.)
    assert frames[-1].variables[f'{room}.state.external_energy_j'] == pytest.approx(
        analytic[room]['external_energy_j'], rel=2e-3)


def test_adaptive_is_more_accurate_than_fixed_at_a_comparable_step_count():
    adaptive = constant_room_project(60., TimeStepOptions(enabled=True, max_internal_step_s=600., rtol=1e-6,
                                                         temperature_atol_k=1e-5, energy_atol_j=1e-3, mass_atol_kg=1e-9))
    fixed = constant_room_project(60.)
    adaptive_session, adaptive_frames = run(adaptive, 3600., 600.)
    fixed_session, fixed_frames = run(fixed, 3600., 600.)
    room = next(iter(adaptive_session.network.room_sources))
    analytic = ideal_room_analytic(adaptive_session.network, 3600.)
    adaptive_error = abs(adaptive_frames[-1].variables[f'{room}.state.temperature_k'] - analytic[room]['temperature_k'])
    fixed_error = abs(fixed_frames[-1].variables[f'{room}.state.temperature_k'] - analytic[room]['temperature_k'])
    assert adaptive_session.step_stats.accepted < 2 * fixed_session.step_stats.accepted
    assert adaptive_error < fixed_error


def test_fixed_mode_frames_report_the_legacy_step_without_adaptive_keys_enabled():
    session, frames = run(constant_room_project(10.), 60., 60.)
    metrics = frames[-1].metrics
    assert metrics['timestep_adaptive'] == 0
    assert metrics['internal_step_s'] == pytest.approx(10.)
    assert metrics['internal_steps'] == 6
    assert metrics['local_error_norm_max'] == 0.
    assert session.step_stats.accepted == 6
