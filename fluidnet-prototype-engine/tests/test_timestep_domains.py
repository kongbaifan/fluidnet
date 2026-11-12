"""New domains: independent solutions, physical units and atomic failed segments."""
from copy import deepcopy

import numpy as np
import pytest
from scipy.linalg import expm

from fn_engine.compiler import compile_project
from fn_engine.examples import pid_example
from fn_engine.models import TimeStepOptions
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed
from fn_engine.refrigeration.examples import room_example
from fn_engine.refrigeration.forward_examples import coupled_buffer_example
from fn_engine.timestep import ErrorEstimate
from fn_engine.buffer_example import buffer_example
from test_air_room import room_project


def options(**changes):
    return TimeStepOptions(enabled=True, max_internal_step_s=20., rtol=1e-8,
                           energy_atol_j=.1, mass_atol_kg=1e-7, temperature_atol_k=1e-6,
                           **changes)


def heated_tank():
    project = pid_example('temperature')
    project.controllers = []
    tank = next(i for i in project.instances if i.id == 'T1')
    tank.parameters.update(heat_input_w=2000., heat_loss_ua_w_k=100.)
    return project


def final(project, duration=20., dt=20.):
    session = create_session(compile_project(project), duration, dt, keep=100)
    try:
        session.initialize()
        while not session.done:
            frame = session.advance()
        return frame
    finally:
        session.close()


def test_fluid_native_error_control_improves_against_fine_reference():
    project = heated_tank()
    coarse = final(project)
    reference = final(project, dt=.1)
    project.solver.time_step = options()
    adaptive = final(project)
    key = 'T1.state.temperature_k'
    assert abs(adaptive.variables[key] - reference.variables[key]) < abs(coarse.variables[key] - reference.variables[key]) / 10.
    assert adaptive.metrics['internal_rejections_total'] > 0
    assert adaptive.metrics['timestep_adaptive'] == 1


def test_closed_buffer_and_pipe_cells_have_energy_error_coordinates():
    from test_thermal import line
    projects = [buffer_example(), line('pipe', {'length_m': 5., 'diameter_m': .02,
        'thermal_cells': 3, 'heat_loss_ua_w_k': 10., 'wall_heat_capacity_j_k': 1000.})]
    for project in projects:
        project.solver.time_step = TimeStepOptions(enabled=True, max_internal_step_s=.1,
                                                   min_internal_step_s=1e-5, energy_atol_j=.1)
        session = create_session(compile_project(project), .1, .1)
        try:
            session.initialize()
            assert session._adaptive_cell_scales
            frame = session.advance()
            assert frame.metrics['timestep_adaptive'] == 1
            assert frame.metrics['local_error_norm_max'] <= 1.
        finally:
            session.close()


def test_air_moisture_exact_integration_and_accepted_ledgers():
    project = room_project()
    next(i for i in project.instances if i.id == 'B1').parameters['pressure_pa'] = 101325.
    project.solver.time_step = options()
    session = create_session(compile_project(project), 10., 10.)
    try:
        before = session.initialize()
        after = session.advance()
        assert after.variables['Room.state.water_vapor_mass_kg'] - before.variables['Room.state.water_vapor_mass_kg'] == pytest.approx(.001, abs=1e-9)
        assert after.variables['Room.state.moisture_added_kg'] == pytest.approx(.001, abs=1e-10)
        assert abs(after.metrics['moisture_residual_kg_s']) < 1e-9
        assert after.metrics['timestep_adaptive'] == 1
    finally:
        session.close()


def test_cold_store_room_goods_match_independent_linear_system():
    project = room_example()
    project.control_scripts = []; project.events = []
    project.solver.time_step = options()
    network = compile_project(project)
    unit, cooler, room = network.chains[0]
    network.parameters[unit]['run_request'] = 0.
    network.parameters[cooler]['fan_continuous'] = 0.
    p = network.parameters[room]
    c, g = p['heat_capacity_j_k'], p['goods_mass_kg'] * p['goods_specific_heat_j_kg_k']
    ua, ug = p['wall_ua_w_k'] + p['roof_ua_w_k'] + p['floor_ua_w_k'], p['goods_ua_w_k']
    source = ((p['wall_ua_w_k'] + p['roof_ua_w_k']) * p['ambient_temperature_k'] +
              p['floor_ua_w_k'] * p['ground_temperature_k'] + p['heat_input_w'] +
              (p['lighting_power_w'] if p['lighting_on'] >= .5 else 0.))
    a = np.array([[-(ua+ug)/c, ug/c], [ug/g, -ug/g]])
    equilibrium = np.linalg.solve(a, -np.array([source/c, 0.]))
    expected = equilibrium + expm(a * 20.) @ (np.array([p['temperature_k'], p['goods_temperature_k']]) - equilibrium)
    session = create_session(network, 20., 20.)
    try:
        session.initialize(); frame = session.advance()
        assert session.temperatures[room] == pytest.approx(expected[0], abs=2e-5)
        assert session.goods[room] == pytest.approx(expected[1], abs=2e-5)
        assert abs(frame.metrics['energy_residual_j']) < .01
        assert frame.metrics['timestep_adaptive'] == 1
    finally:
        session.close()


@pytest.mark.parametrize('factory,module', [(heated_tank, 'fn_engine.simulation_adaptive'),
                                          (room_example, 'fn_engine.refrigeration.cold_store')])
def test_minimum_step_rolls_back_whole_segment_and_control(factory, module, monkeypatch):
    project = factory(); project.solver.time_step = options(min_internal_step_s=.1)
    session = create_session(compile_project(project), 20., 20.)
    try:
        session.initialize()
        fields = ('tanks', 'cells', 'air_rooms') if module.endswith('simulation_adaptive') else ('temperatures', 'goods', 'counters', 'units', 'coolers', 'event_index')
        before = deepcopy({key: getattr(session, key) for key in fields})
        controls = deepcopy({key: (value.state, value.next_s, value.samples) for key, value in session.scripts.items()})
        monkeypatch.setattr(module + '.normalized_error', lambda *a, **k: ErrorEstimate(2.))
        with pytest.raises(SolveFailed, match='最小步长'):
            session.advance()
        assert session.time == 0.
        for key, value in before.items():
            assert getattr(session, key) == value
        assert {key: (value.state, value.next_s, value.samples) for key, value in session.scripts.items()} == controls
        assert session.step_stats.accepted == 0
    finally:
        session.close()


def test_coupled_buffer_error_uses_joules_and_real_accepted_energy():
    project = coupled_buffer_example()
    project.solver.time_step = TimeStepOptions(enabled=True, max_internal_step_s=.1,
                                               energy_atol_j=.1, rtol=1e-7)
    session = create_session(compile_project(project), .1, .1)
    try:
        session.initialize()
        x = session._vector(session.masses, session.energies, session.temperatures)
        fine = x.copy()
        index = len(x) - 1
        # 1 J/kg in a 100 kg tank is 100 J, independent of solver vector normalization.
        fine[index] += 1. / session.scale[index]
        result = session._current()
        estimate = session._error_estimate(x, x, fine, result, result)
        assert estimate.by_category['energy'] == pytest.approx(100. / (.1 + 1e-7 * 100.))
        frame = session.advance()
        assert frame.metrics['timestep_adaptive'] == 1
        assert abs(frame.metrics['energy_residual_j']) < .01
    finally:
        session.close()


def test_schema5_author_compressor_in_coupled_storage_commits_once():
    from fn_engine.refrigeration.author_examples import definition
    project = coupled_buffer_example()
    module = definition('compressor')
    project.modules.append(module)
    for instance in project.instances:
        if instance.module_id == 'refrigerant_compressor':
            instance.module_id = module.id
            compressor_id = instance.id
    project.solver.time_step = TimeStepOptions(enabled=True, max_internal_step_s=.1)
    session = create_session(compile_project(project), .2, .1)
    try:
        session.initialize(); frame = session.advance()
        assert session.runners[compressor_id].state['accepted_seconds'] == pytest.approx(.1)
        assert abs(frame.metrics['energy_residual_j']) < .01
        before = deepcopy((session.masses, session.energies, session.temperatures,
                           session.runners[compressor_id].state))
        session.network.parameters['Buffer']['maximum_temperature_k'] = 280.
        session._cache = None
        with pytest.raises(SolveFailed):
            session.advance()
        assert (session.masses, session.energies, session.temperatures,
                session.runners[compressor_id].state) == before
        assert session.time == .1
    finally:
        session.close()


@pytest.mark.parametrize('factory', [heated_tank, room_example, room_project])
def test_adaptive_checkpoint_resumes_same_states_and_step_sequence(factory):
    from fn_engine.checkpoints import capture, restore
    project = factory(); project.solver.time_step = options()
    original = create_session(compile_project(project), 2., .5, keep=8)
    resumed = None
    try:
        original.initialize(); original.advance()
        resumed = restore(capture(original))
        a, b = original.advance(), resumed.advance()
        assert a.time_s == b.time_s
        for key, value in a.variables.items():
            if '.state.' in key and isinstance(value, (int, float)):
                assert b.variables[key] == pytest.approx(value, rel=1e-9, abs=1e-7), key
        assert original.step_stats.sequence == resumed.step_stats.sequence
        assert original.step_stats.accepted == resumed.step_stats.accepted
        assert a.metrics['local_error_norm_max'] <= 1.
    finally:
        original.close()
        if resumed:
            resumed.close()
