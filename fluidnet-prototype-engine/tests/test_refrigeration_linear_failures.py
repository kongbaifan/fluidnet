"""Singular Newton systems recover or fail with accepted physics and history intact."""
from copy import deepcopy
import inspect

import numpy as np
import pytest

from fn_engine.compiler import compile_project
from fn_engine.models import TimeStepOptions
from fn_engine.refrigeration import cold_store, station
from fn_engine.refrigeration.examples import room_example, station_example
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed


def open_session(domain, adaptive=False, duration=30.):
    project = station_example() if domain == 'station' else room_example()
    if adaptive:
        project.solver.time_step = TimeStepOptions(enabled=True, min_internal_step_s=.1,
            max_internal_step_s=10., temperature_atol_k=1., rtol=.01)
    session = create_session(compile_project(project), duration, 30., keep=20)
    session.initialize()
    return session


def inject_singular_matrices(monkeypatch, domain, failures):
    target = station.StationSession._solve if domain == 'station' else cold_store.ColdStoreSession._newton
    original = np.linalg.solve
    calls = []

    def solve(matrix, rhs):
        if inspect.currentframe().f_back.f_code is target.__code__:
            calls.append(matrix.shape)
            if failures is None or len(calls) <= failures:
                # Let NumPy raise from an actual singular system in the real Newton path.
                return original(np.zeros_like(matrix), rhs)
        return original(matrix, rhs)

    monkeypatch.setattr(np.linalg, 'solve', solve)
    return calls


@pytest.mark.parametrize('domain', ['station', 'cold_store'])
@pytest.mark.parametrize('adaptive', [False, True], ids=['fixed', 'adaptive'])
@pytest.mark.parametrize('failures', [1, 2], ids=['rebuild', 'fallback'])
def test_singular_newton_system_recovers(domain, adaptive, failures, monkeypatch):
    reference = open_session(domain, adaptive)
    session = open_session(domain, adaptive)
    try:
        expected = reference.advance()
        calls = inject_singular_matrices(monkeypatch, domain, failures)
        frame = session.advance()
        assert len(calls) > failures
        assert frame.time_s == expected.time_s == 30.
        assert abs(frame.metrics['energy_residual_j']) < .05
        if failures == 1:
            # Refreshing at the same state must retain the ordinary solution and step sequence.
            assert frame.variables == expected.variables
            assert session.step_stats.accepted == reference.step_stats.accepted
            assert session.step_stats.sequence == reference.step_stats.sequence
            assert session.step_stats.solver_failures == 0
        elif adaptive:
            assert session.step_stats.solver_failures > 0
        else:
            assert session.step_stats.accepted > reference.step_stats.accepted
    finally:
        reference.close()
        session.close()


@pytest.mark.parametrize('domain', ['station', 'cold_store'])
@pytest.mark.parametrize('adaptive', [False, True], ids=['fixed', 'adaptive'])
@pytest.mark.parametrize('accepted_time', [0., 30.], ids=['initial', 'after-accepted-frame'])
def test_persistent_singularity_preserves_accepted_state_and_reports_exhaustion(
        domain, adaptive, accepted_time, monkeypatch):
    session = open_session(domain, adaptive, duration=60.)
    try:
        if accepted_time:
            session.advance()
        before = session.snapshot().variables
        parameters = deepcopy(session.network.parameters)
        frames = list(session.frames)
        accepted_steps = session.step_stats.accepted
        sequence = list(session.step_stats.sequence)
        scripts = {key: (deepcopy(runner.state), runner.samples, runner.next_s, runner.last_s)
                   for key, runner in session.scripts.items()}
        calls = inject_singular_matrices(monkeypatch, domain, None)
        with pytest.raises(SolveFailed) as caught:
            session.advance()
        code = ('REFRIGERATION_JACOBIAN_SINGULAR' if domain == 'station'
                else 'COLD_STORE_JACOBIAN_SINGULAR')
        assert caught.value.diagnostic.code == ('TIME_STEP_MIN_EXCEEDED' if adaptive else code)
        assert '奇异' in str(caught.value)
        assert len(calls) > 2
        assert session.time == accepted_time
        assert session.snapshot().variables == before
        assert session.network.parameters == parameters
        assert session.step_stats.accepted == accepted_steps
        assert session.step_stats.sequence == sequence
        assert list(session.frames) == caught.value.frames == frames
        for key, runner in session.scripts.items():
            assert (runner.state, runner.samples, runner.next_s, runner.last_s) == scripts[key]
            assert runner.pending is None
        if adaptive:
            assert session.step_stats.solver_failures > 0
            assert session.step_stats.min_step_hits == 1
    finally:
        session.close()


@pytest.mark.parametrize('domain', ['station', 'cold_store'])
def test_real_singular_cached_jacobian_is_rebuilt(domain):
    session = open_session(domain)
    try:
        before = session.snapshot().variables
        if domain == 'station':
            x = session._vector(session.masses, session.energies, session.temperatures)
            session._jacobian = np.eye(len(x)) / 10.
            candidate, _ = session._solve(x, 10.)
            assert np.all(np.isfinite(candidate))
            assert not np.array_equal(candidate, x)
        else:
            chain = session.network.chains[0]
            session.units[chain[0]]['running'] = True
            before = session.snapshot().variables
            session.units[chain[0]]['jacobian'] = np.zeros((2, 2))
            candidate = session._trial(chain, 10.)
            assert candidate['point']['cooling_power_w'] > 0.
        # A Newton trial updates its cache, not the accepted inventory or control clocks.
        assert session.snapshot().variables == before
    finally:
        session.close()
