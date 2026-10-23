"""A2/A3/A4: station no-commit trials, error acceptance, gate vs a finer reference, and reporting.

Fast gates use shortened station scenarios; the full-length numbers are recorded in
docs/numerics/results/A3.md. The fixed-step path is compared against the v0.5.0 a986ca3 baseline
so that every variable and ledger counter must stay bit-identical.
"""
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import apply_scenario, create_app
from fn_engine.compiler import compile_project
from fn_engine.models import Project, Scenario, ScheduleEvent, TimeStepOptions
from fn_engine.refrigeration import devices
from fn_engine.refrigeration.examples import station_case, station_example
from fn_engine.refrigeration.report import station_report
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed
from fn_engine.timestep import ErrorEstimate
from test_continuous import wait

# sha256 of {'variables', 'counters'} produced by the fixed-step path at v0.5.0 a986ca3.
BASELINE_HASH = {
    'example': 'a44a3f35d61849d4613b37c43a589aa05625d4c4402cb63f28f807b61fc98ba9',
    'case01': '991affb4f7c8c1e16b2418d62f6e1b46f15e269b50656a79120ffee1c06986ca',
}


def open_session(project, duration=600., dt_s=60., keep=100000):
    session = create_session(compile_project(project), duration, dt_s, keep=keep)
    session.initialize()
    return session


def run(project, duration=600., dt_s=60., keep=100000):
    session = open_session(project, duration, dt_s, keep)
    try:
        while not session.done:
            session.advance()
    finally:
        session.close()
    return session


def fixed_hash(session):
    frame = session.frames[-1]
    payload = {'variables': {k: frame.variables[k] for k in sorted(frame.variables)},
               'counters': {f'{a}.{b}': round(c, 12) for (a, b), c in sorted(session.counters.items())}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def adaptive_options(**changes):
    values = {'enabled': True}
    values.update(changes)
    return TimeStepOptions(**values)


def station_project(scenario='B-S01', duration=600., dynamic_step_s=10., time_step=None):
    project = apply_scenario(station_case(), scenario)
    project.solver.dynamic_step_s = dynamic_step_s
    if time_step is not None:
        project.solver.time_step = time_step
    return project


# --- A2: fixed path unchanged and trials start from any accepted vector --------------------------
def test_old_fixed_step_path_is_bit_identical_to_v050():
    session = run(station_example(), 600.)
    assert session.frames[-1].metrics['timestep_adaptive'] == 0
    assert fixed_hash(session) == BASELINE_HASH['example']
    case = run(station_project('B-S01', 1200.), 1200.)
    assert fixed_hash(case) == BASELINE_HASH['case01']


def test_trial_runs_from_any_accepted_vector_and_second_half_from_the_first():
    session = open_session(station_project('B-S01', 600., time_step=adaptive_options()))
    try:
        x = session._vector(session.masses, session.energies, session.temperatures)
        payload, error = session._trial_doubling(x, 10.)
        assert error.norm <= 1.
        state = session.last_trial
        assert state['h'] == 10. and state['x_mid'].shape == x.shape
        # 第二个半步确实从第一个半步的 accepted 中间态出发。
        manual_mid, _ = session._solve(x, 5.)
        manual_fine, _ = session._solve(manual_mid, 5.)
        assert state['x_mid'] == pytest.approx(manual_mid, rel=0, abs=1e-10)
        assert state['x_fine'] == pytest.approx(manual_fine, rel=0, abs=1e-10)
        assert not (state['x_mid'] == x).all()
        # 试算不触碰 accepted 状态与账本。
        assert session._vector(session.masses, session.energies, session.temperatures) == pytest.approx(x, rel=0, abs=0)
        assert session.counters == {}
        assert session.energy_residual_j == 0.
    finally:
        session.close()


def test_rejected_trial_restores_state_counters_and_caches():
    session = open_session(station_project('B-S01', 600., time_step=adaptive_options()))
    try:
        x = session._vector(session.masses, session.energies, session.temperatures)
        jacobian, cache = session._jacobian, session._cache
        masses, energies = dict(session.masses), dict(session.energies)
        temperatures, counters = dict(session.temperatures), dict(session.counters)
        residual = session.energy_residual_j
        session._error_estimate = lambda *args: ErrorEstimate(norm=5.)
        payload, error = session._trial_doubling(x, 10.)
        assert payload is None and error.norm == 5.
        assert session.masses == masses and session.energies == energies
        assert session.temperatures == temperatures and session.counters == counters
        assert session.energy_residual_j == residual
        assert session._jacobian is jacobian and session._cache is cache
        # 求解失败同样恢复缓存并抛出 TrialFailure，由接受循环缩步。
        def failing_solve(*args, **kwargs):
            raise devices.DeviceRangeError('REFRIGERATION_NOT_CONVERGED', '注入失败')

        session._solve = failing_solve
        with pytest.raises(Exception) as error_info:
            session._trial_doubling(x, 10.)
        assert error_info.type.__name__ == 'TrialFailure'
        assert session._jacobian is jacobian and session._cache is cache
        assert session.masses == masses and session.energies == energies
    finally:
        session.close()


def test_adaptive_integration_recovers_from_a_forced_rejection_and_solver_failure():
    session = open_session(station_project('B-S01', 600., time_step=adaptive_options()))
    try:
        calls = {'error': 0, 'solve': 0}
        original_error, original_solve = session._error_estimate, session._solve

        def reject_once(*args):
            calls['error'] += 1
            return ErrorEstimate(norm=3.) if calls['error'] == 1 else original_error(*args)

        def fail_once(*args, **kwargs):
            calls['solve'] += 1
            if calls['solve'] == 1:
                raise devices.DeviceRangeError('REFRIGERATION_NOT_CONVERGED', '注入失败')
            return original_solve(*args, **kwargs)

        session._error_estimate = reject_once
        session._solve = fail_once
        before = session._vector(session.masses, session.energies, session.temperatures)
        session._integrate_adaptive(10.)
        after = session._vector(session.masses, session.energies, session.temperatures)
        assert calls['error'] > 1 and calls['solve'] > 1
        assert session.step_stats.rejected >= 1 and session.step_stats.solver_failures >= 1
        assert not (after == before).all()
        assert abs(session.frame_residual_j) < 1e-6 * max(1., sum(abs(v) for v in session.energies.values()))
    finally:
        session.close()


def test_minimum_step_exhaustion_keeps_accepted_history():
    project = station_project('B-S01', 600., time_step=adaptive_options(
        min_internal_step_s=9.9, max_internal_step_s=10., rtol=1e-12, temperature_atol_k=1e-12,
        energy_atol_j=1e-12, mass_atol_kg=1e-15))
    session = open_session(project, 600.)
    try:
        with pytest.raises(SolveFailed) as error:
            session.advance()
        assert error.value.diagnostic.code == 'TIME_STEP_MIN_EXCEEDED'
        assert error.value.frames and all(frame.time_s < 60. for frame in error.value.frames)
        assert session.step_stats.min_step_hits >= 1
    finally:
        session.close()


def test_boundary_truncated_step_exhaustion_is_diagnosed_separately():
    project = station_project('B-S01', 600., time_step=adaptive_options(
        min_internal_step_s=5., max_internal_step_s=10., rtol=1e-12, temperature_atol_k=1e-12,
        energy_atol_j=1e-12, mass_atol_kg=1e-15), dynamic_step_s=10.)
    session = create_session(compile_project(project), 1., 1., keep=100)
    session.initialize()
    try:
        with pytest.raises(SolveFailed) as error:
            session.advance()
        assert error.value.diagnostic.code == 'TIME_STEP_BOUNDARY_EXCEEDED'
    finally:
        session.close()


# --- A3: four scenarios against a finer fixed-step reference ------------------------------------
def _set(event_id, at, key, value):
    return ScheduleEvent(id=event_id, type='set_variable', time_s=at, key=key, value=value)


SHORT_SCENARIOS = {
    'rated': [],
    'load-step': [_set('up', 450., 'ROOM1.param.heat_input_w', 40000.),
                  _set('down', 1350., 'ROOM1.param.heat_input_w', 0.)],
    'target-pressure': [_set('evap-0', 450., 'controller.suction.setpoint', 115000.),
                        _set('evap-1', 675., 'controller.suction.setpoint', 120000.),
                        _set('wb-down', 900., 'EC1.param.wet_bulb_temperature_k', 293.15),
                        _set('cond-0', 900., 'controller.head.setpoint', 1300000.),
                        _set('cond-1', 1125., 'controller.head.setpoint', 1250000.)],
    'wet-bulb': [_set('wb-0', 450., 'EC1.param.wet_bulb_temperature_k', 299.15),
                 _set('wb-1', 675., 'EC1.param.wet_bulb_temperature_k', 298.15),
                 _set('wb-2', 900., 'EC1.param.wet_bulb_temperature_k', 297.15),
                 _set('wb-3', 1350., 'EC1.param.wet_bulb_temperature_k', 294.15),
                 _set('wb-4', 1575., 'EC1.param.wet_bulb_temperature_k', 295.15)],
}


def short_station_project(events):
    project = station_case()
    project.scenarios = [Scenario(id='short', name='short', events=events)]
    return apply_scenario(project, 'short')


@pytest.mark.parametrize('name', list(SHORT_SCENARIOS))
def test_error_acceptance_matches_a_finer_fixed_step_reference(name):
    events = SHORT_SCENARIOS[name]
    reference = short_station_project(events)
    reference.solver.dynamic_step_s = 1.
    reference_run = run(reference, 1800.)
    adaptive = short_station_project(events)
    adaptive.solver.time_step = TimeStepOptions(enabled=True)
    adaptive_run = run(adaptive, 1800.)
    assert adaptive_run.step_stats.sequence
    assert adaptive_run.frames[-1].metrics['timestep_adaptive'] == 1
    ref, got = reference_run.frames[-1].variables, adaptive_run.frames[-1].variables
    for room in adaptive_run.network.room_coolers:
        assert abs(got[f'{room}.state.temperature_k'] - ref[f'{room}.state.temperature_k']) <= 1e-3
    for vessel in adaptive_run.network.vessels:
        pressure = ref[f'{vessel}.state.pressure_pa']
        assert abs(got[f'{vessel}.state.pressure_pa'] - pressure) <= 1e-3 * abs(pressure)
    electric_ref = sum(ref[f'{k}.state.electric_energy_j'] for k in adaptive_run.network.kinds
                       if adaptive_run.network.kinds[k] == 'refrigerant_compressor')
    electric_got = sum(got[f'{k}.state.electric_energy_j'] for k in adaptive_run.network.kinds
                       if adaptive_run.network.kinds[k] == 'refrigerant_compressor')
    assert abs(electric_got - electric_ref) <= 1e-3 * abs(electric_ref)
    # 事件顺序、控制次数与批量路径一致（脚本统计整机启动/风机切换次数）。
    assert adaptive_run.events_applied == reference_run.events_applied == len(events)
    assert got['script.control.state.starts'] == ref['script.control.state.starts']
    assert got['script.control.state.fan_changes'] == ref['script.control.state.fan_changes']


def test_manual_single_stepping_matches_the_batch_runner():
    project = station_project('B-S01', 600., time_step=adaptive_options())
    session = open_session(project, 240.)
    manual = [session.frames[-1]]
    while not session.done:
        manual.append(session.advance())
    session.close()
    batch = [frame.time_s for frame in run(project, 240.).frames]
    assert [frame.time_s for frame in manual] == batch


def test_api_single_step_runs_with_error_acceptance(tmp_path):
    project = station_example()
    project.solver.time_step = adaptive_options()
    body = {'project': project.model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': 120., 'dt_s': 60.,
            'start_paused': True}
    with TestClient(create_app(data_root=tmp_path)) as client:
        run_id = client.post('/api/v1/runs?background=true', json=body).json()['run_id']
        wait(client, run_id, lambda record: record['status'] == 'paused')
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'step'}).raise_for_status()
        record = wait(client, run_id, lambda record: record['status'] == 'paused' and record['frame']['time_s'] == 60.)
        assert record['frame']['metrics']['timestep_adaptive'] == 1
        assert record['frame']['metrics']['internal_steps_total'] >= 6


def test_saved_project_recomputes_after_app_restart(tmp_path):
    project = station_example()
    project.solver.time_step = adaptive_options()
    body = {'project': project.model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': 120., 'dt_s': 60.}
    with TestClient(create_app(data_root=tmp_path)) as client:
        first = client.post('/api/v1/runs', json=body).json()
    with TestClient(create_app(data_root=tmp_path)) as client:
        second = client.post('/api/v1/runs', json=body).json()
    assert first['status'] == second['status'] == 'completed'
    assert first['frame']['variables'] == second['frame']['variables']
    for key in ('timestep_adaptive', 'internal_step_s', 'internal_steps_total', 'local_error_norm_max'):
        assert first['frame']['metrics'][key] == second['frame']['metrics'][key]


# --- A4: reproducibility, save/restore and report wording ---------------------------------------
def test_same_settings_reproduce_the_same_accepted_step_sequence():
    project = station_project('B-S01', 600., time_step=adaptive_options())
    first = run(project, 600.)
    second = run(project, 600.)
    assert first.step_stats.sequence == second.step_stats.sequence
    assert first.frames[-1].variables == second.frames[-1].variables
    assert first.frames[-1].metrics == second.frames[-1].metrics
    restored = Project.model_validate(json.loads(project.model_dump_json()))
    third = run(restored, 600.)
    assert third.step_stats.sequence == first.step_stats.sequence
    assert third.frames[-1].variables == first.frames[-1].variables


def test_report_shows_local_error_metrics_without_calling_them_global():
    project = short_station_project(SHORT_SCENARIOS['rated'])
    project.solver.time_step = TimeStepOptions(enabled=True)
    session = run(project, 900.)
    network = session.network
    rows = [{'time_s': frame.time_s, 'variables': frame.variables, 'metrics': frame.metrics}
            for frame in session.frames]
    record = {'id': 'timestep-report', 'status': 'completed',
              'request': {'project': project.model_dump(mode='json'), 'dt_s': 60., 'duration_s': 900.,
                          'scenario_id': 'short'},
              'frame': session.frames[-1].model_dump(mode='json')}
    html = station_report(record, rows, network)
    assert '时间误差控制设置' in html and '开启（step-doubling 接受/拒绝）' in html
    assert '局部时间离散误差范数最大值' in html and '不是全程误差' in html
    assert '全局误差' not in html
