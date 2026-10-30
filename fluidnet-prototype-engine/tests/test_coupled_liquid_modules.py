"""Hydraulic authors share the enclosing station's candidate and acceptance boundary."""
from copy import deepcopy

import pytest

from fn_engine.compiler import CompilationError, compile_project
from fn_engine.module_templates import create_template
from fn_engine.models import Connection, Endpoint
from fn_engine.refrigeration.coupling import CoupledStationSession
from fn_engine.refrigeration.coupling_examples import thermal_coupling_example
from fn_engine.refrigeration.devices import DeviceRangeError
from fn_engine.solver import SolveFailed


def author_project():
    project = thermal_coupling_example('Water')
    definition = create_template('managed_state', 'custom_liquid_valve', '作者水阀')
    for parameter in definition.parameters:
        if parameter.id == 'opening_ratio':
            parameter.runtime = True
    project.modules.append(definition)
    next(instance for instance in project.instances if instance.id == 'WV1').module_id = definition.id
    return project


def test_liquid_author_matches_builtin_and_snapshots_do_not_execute_source():
    projects = [thermal_coupling_example('Water'), author_project()]
    sessions = [CoupledStationSession(compile_project(project), .2, .1) for project in projects]
    try:
        frames = [session.initialize() for session in sessions]
        assert frames[1].variables['WV1.state.commit_count'] == 0
        for _ in range(2):
            frames = [session.advance() for session in sessions]
            for key in ['WV1.mass_flow_kg_s', 'coupling.HX1.heat_w', 'LP1.state.temperature_k']:
                assert frames[1].variables[key] == pytest.approx(frames[0].variables[key], rel=1e-8, abs=1e-7)
        session = sessions[1]
        runner = session.runners['WV1']
        calls = runner.request_count
        session.snapshot()
        session.snapshot()
        assert runner.request_count == calls
        assert runner.state['commit_count'] == 2
        assert runner.state_revision == 2
        assert frames[1].variables['WV1.state.commit_count'] == 2
        assert frames[1].variables['WV1.state.throughput_kg'] == runner.state['throughput_kg']
        assert abs(frames[1].metrics['reference_heat_w']) < 1e-7
        assert abs(frames[1].metrics['energy_residual_j']) < .002
        assert frames[1].variables['WV1.state.transferred_mass_kg'] > 0
    finally:
        for session in sessions:
            session.close()
    assert runner.process is None or runner.process.poll() is not None


def test_runtime_liquid_author_parameter_updates_reach_nested_network():
    session = CoupledStationSession(compile_project(author_project()), .2, .1)
    try:
        first = session.initialize()
        session.write_variables({'WV1.param.opening_ratio': .4})
        reduced = session.advance()
        assert reduced.variables['WV1.param.opening_ratio'] == .4
        assert reduced.variables['WV1.opening_ratio'] == .4
        assert reduced.variables['WV1.mass_flow_kg_s'] < first.variables['WV1.mass_flow_kg_s']
        session.write_variables({'WV1.param.opening_ratio': .8})
        restored = session.advance()
        assert restored.variables['WV1.mass_flow_kg_s'] == pytest.approx(first.variables['WV1.mass_flow_kg_s'], rel=1e-6)
    finally:
        session.close()


@pytest.mark.parametrize('adaptive', [False, True])
def test_accept_failure_rolls_back_water_station_and_author(adaptive):
    project = author_project()
    project.solver.time_step.enabled = adaptive
    module = project.modules[-1]
    module.source['runtime'] = module.source['runtime'].replace("ctx.state['commit_count'] = count + 1",
        "ctx.state['commit_count'] = count + 1\n        if ctx.time_s > .15: raise ValueError('author rejected')")
    session = CoupledStationSession(compile_project(project), .2, .1)
    try:
        session.initialize()
        session.advance()
        before = deepcopy((session.masses, session.energies, session.counters, session.runners['WV1'].state))
        with pytest.raises(SolveFailed, match='author rejected'):
            session.advance()
        assert (session.masses, session.energies, session.counters, session.runners['WV1'].state) == before
        assert session.time == .1
        assert session.frames[-1].time_s == .1
        assert session.runners['WV1'].state_revision == 1
    finally:
        session.close()


def test_retried_inner_steps_have_real_times_and_one_author_accept(monkeypatch):
    session = CoupledStationSession(compile_project(author_project()), .1, .1)
    try:
        session.initialize()
        runner = session.runners['WV1']
        evaluate, solve = runner.evaluate, session._solve
        times, accepted = [], []
        def record(request):
            times.append(request.time_s)
            return evaluate(request)
        def reject_large(x, h):
            result = solve(x, h)
            if h > .075:
                raise DeviceRangeError('REFRIGERATION_NOT_CONVERGED', 'retry')
            index = next(i for i, branch in enumerate(session.network.fluid_network.branches) if branch.instance_id == 'WV1')
            accepted.append(h * abs(result[1]['fluid_result'].hydraulic.flows[index]))
            return result
        monkeypatch.setattr(runner, 'evaluate', record)
        monkeypatch.setattr(session, '_solve', reject_large)
        frame = session.advance()
        assert .05 in times and .1 in times
        assert len(accepted) == 2
        assert frame.variables['WV1.state.transferred_mass_kg'] == pytest.approx(sum(accepted))
        assert runner.state['commit_count'] == 1
        assert runner.execution.accepted_time_s == .1
    finally:
        session.close()


@pytest.mark.parametrize('alter', ['thermal', 'no-transactions', 'pump'])
def test_compile_rejects_unopened_liquid_roles(alter):
    project = author_project()
    module = project.modules[-1]
    if alter == 'thermal':
        module.sdk.capabilities.append('thermal.v1')
    elif alter == 'no-transactions':
        module.sdk.capabilities.remove('state.transactions.v1')
    else:
        module.sdk.capabilities.append('net.pump')
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'COUPLED_LIQUID_MODULE_UNSUPPORTED'


def test_actual_heat_relation_is_rejected_even_without_declared_thermal_capability():
    project = author_project()
    module = project.modules[-1]
    module.source['runtime'] = module.source['runtime'].replace('density_kg_m3=rho)', 'density_kg_m3=rho, heat_w=123.)')
    session = CoupledStationSession(compile_project(project), .1, .1)
    try:
        with pytest.raises(ValueError, match='无附加热流'):
            session.initialize()
        assert session.closed
        assert all(runner.process is None or runner.process.poll() is not None for runner in session.runners.values())
    finally:
        session.close()


def test_adaptive_rejection_uses_only_accepted_half_step_mass(monkeypatch):
    from fn_engine.timestep import ErrorEstimate
    project = author_project()
    project.solver.time_step.enabled = True
    session = CoupledStationSession(compile_project(project), .1, .1)
    try:
        session.initialize()
        estimate, trial = session._error_estimate, session._trial_doubling
        calls, accepted = 0, []
        def reject_first(*args):
            nonlocal calls
            calls += 1
            return ErrorEstimate(4.) if calls == 1 else estimate(*args)
        def collect(x, h):
            payload, error = trial(x, h)
            if payload is not None:
                accepted.append(payload['counters'][('WV1', 'transferred_mass_kg')])
            return payload, error
        monkeypatch.setattr(session, '_error_estimate', reject_first)
        monkeypatch.setattr(session, '_trial_doubling', collect)
        frame = session.advance()
        assert session.step_stats.rejected == 1
        assert len(accepted) >= 2
        assert frame.variables['WV1.state.transferred_mass_kg'] == pytest.approx(sum(accepted))
        assert frame.variables['WV1.state.commit_count'] == 1
    finally:
        session.close()


def test_second_author_prepare_failure_keeps_both_modules_and_station_unaccepted():
    project = author_project()
    first = next(instance for instance in project.instances if instance.id == 'WV1')
    second = first.model_copy(deep=True, update={'id': 'WV2'})
    project.instances.append(second)
    edge = next(edge for edge in project.connections if edge.id == 'w4')
    edge.source.instance_id = 'WV2'
    project.connections.append(Connection(id='two_valves', source=Endpoint(instance_id='WV1', port_id='out0'),
                                          target=Endpoint(instance_id='WV2', port_id='in0')))
    module = project.modules[-1]
    module.source['runtime'] = module.source['runtime'].replace("ctx.state['commit_count'] = count + 1",
        "ctx.state['commit_count'] = count + 1\n        if ctx.execution.instance_id == 'WV2': raise ValueError('second author')")
    session = CoupledStationSession(compile_project(project), .1, .1)
    try:
        first = session.initialize()
        state = deepcopy((session.masses, session.energies, session.counters))
        with pytest.raises(SolveFailed, match='second author'):
            session.advance()
        assert (session.masses, session.energies, session.counters) == state
        assert session.time == 0
        assert all(runner.state_revision == 0 and runner.state['commit_count'] == 0 for runner in session.runners.values())
        assert session.frames[-1].variables == first.variables
    finally:
        session.close()


def test_sync_failure_retains_accepted_liquid_and_station_frame(monkeypatch):
    from fn_engine.runtime import RuntimeErrorBase
    session = CoupledStationSession(compile_project(author_project()), .2, .1)
    try:
        session.initialize()
        runner = session.runners['WV1']
        def fail_sync(candidate):
            raise RuntimeErrorBase('injected synchronization failure')
        monkeypatch.setattr(runner, 'synchronize_state', fail_sync)
        with pytest.raises(SolveFailed) as error:
            session.advance()
        assert error.value.diagnostic.code == 'MODULE_SYNC_FAILED'
        assert session.time == .1
        assert session.frames[-1].time_s == .1
        assert session.frames[-1].variables['WV1.state.commit_count'] == 1
        assert session.frames[-1].variables['WV1.state.transferred_mass_kg'] > 0
        assert runner.state_revision == 1
        with pytest.raises(StopIteration):
            session.advance()
        assert runner.state_revision == 1
    finally:
        session.close()


def test_steady_liquid_author_matches_equilibrium_without_committing(monkeypatch):
    from fn_engine.refrigeration import liquid_modules
    from fn_engine.solver import solve_steady
    created, worker = [], liquid_modules.LiquidWorker
    class TracedWorker(worker):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)
    monkeypatch.setattr(liquid_modules, 'LiquidWorker', TracedWorker)
    builtin = solve_steady(compile_project(thermal_coupling_example('Water')))
    custom = solve_steady(compile_project(author_project()))
    assert custom.variables['WV1.mass_flow_kg_s'] == pytest.approx(builtin.variables['WV1.mass_flow_kg_s'], rel=1e-7)
    assert abs(custom.metrics['steady_energy_residual_w']) < .01
    assert custom.variables['WV1.state.commit_count'] == 0
    assert custom.variables['WV1.state.transferred_mass_kg'] == 0
    assert len(created) == 1
    assert created[0].request_count > 1
    assert created[0].state_revision == 0
    assert created[0].process is None or created[0].process.poll() is not None


def test_zero_flow_stops_both_liquid_heat_and_platform_mass_accumulation():
    session = CoupledStationSession(compile_project(author_project()), .2, .1)
    try:
        session.initialize()
        open_frame = session.advance()
        session.write_variables({'WV1.param.opening_ratio': 0.})
        closed = session.advance()
        assert closed.variables['WV1.mass_flow_kg_s'] == pytest.approx(0., abs=1e-10)
        assert closed.variables['coupling.HX1.heat_w'] == 0
        assert closed.variables['WV1.state.transferred_mass_kg'] == pytest.approx(open_frame.variables['WV1.state.transferred_mass_kg'])
    finally:
        session.close()


@pytest.mark.parametrize('phase', ['evaluate', 'observe', 'commit'])
def test_all_author_phases_cannot_spoof_host_mass_ledger(phase):
    project = author_project()
    module = project.modules[-1]
    injection = "ctx.var('state.transferred_mass_kg', 1234.)"
    if phase == 'evaluate':
        module.source['runtime'] = module.source['runtime'].replace("ctx.var('opening_ratio', opening)", injection)
    elif phase == 'observe':
        module.sdk.capabilities.append('observe.v1')
        module.source['runtime'] = module.source['runtime'].replace('    def finalize(',
            f'    def observe(self, ctx):\n        {injection}\n\n    def finalize(')
    else:
        module.source['runtime'] = module.source['runtime'].replace("ctx.state['commit_count'] = count + 1", injection)
    session = CoupledStationSession(compile_project(project), .1, .1)
    try:
        if phase == 'commit':
            session.initialize()
            with pytest.raises(SolveFailed):
                session.advance()
            assert session.time == 0
            assert session.frames[-1].variables['WV1.state.transferred_mass_kg'] == 0
        else:
            with pytest.raises(ValueError):
                session.initialize()
        assert session.runners['WV1'].state_revision == 0
    finally:
        session.close()
