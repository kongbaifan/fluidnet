"""Behavior at shared command/lifecycle boundaries, using real compiled projects."""
from copy import deepcopy

import pytest

from fn_engine.compiler import compile_project
from fn_engine.simulation import SimulationSession
from fn_engine.refrigeration.examples import ideal_room_example
from fn_engine.sessions import create_session
from test_engine import reference_project
from test_module_composites import group


def test_public_parameter_batch_validates_every_target_before_changing_any_value():
    _, _, project = group()
    session = SimulationSession(compile_project(project), .2, .1)
    try:
        session.initialize()
        before = deepcopy(session.network.parameters)
        revision = session.revision
        with pytest.raises(ValueError):
            session.write_variables({'C1.param.D1_opening_ratio': .4, 'C1.param.D2_opening_ratio': -1.})
        assert session.network.parameters == before
        assert session.revision == revision
    finally:
        session.close()


def test_public_parameter_batch_updates_all_workers_and_counts_one_revision():
    _, _, project = group()
    session = SimulationSession(compile_project(project), .2, .1)
    try:
        initial = session.initialize()
        revision = session.revision
        session.write_variables({'C1.param.D1_opening_ratio': .4, 'C1.param.D2_opening_ratio': .3})
        assert session.network.parameters['C1__D1']['opening_ratio'] == .4
        assert session.network.parameters['C1__D2']['opening_ratio'] == .3
        assert session.revision == revision + 1
        frame = session.advance()
        assert frame.valid
        assert frame.variables['C1.main.mass_flow_kg_s'] < initial.variables['C1.main.mass_flow_kg_s']
        assert frame.variables['C1.state.D1.commit_count'] == 1
        assert frame.variables['C1.state.D2.commit_count'] == 1
    finally:
        session.close()


def test_failed_device_cleanup_still_closes_controls_once():
    session = SimulationSession(compile_project(reference_project()), .2, .1)
    calls = []

    class FailingGroup:
        def close(self):
            calls.append('device')
            raise RuntimeError('close failure')

    class Control:
        def close(self):
            calls.append('control')

    session.runners = FailingGroup()
    session.scripts = {'control': Control()}
    with pytest.raises(RuntimeError, match='close failure'):
        session.close()
    session.close()
    assert calls == ['device', 'control']


def test_thermal_control_runs_without_placeholder_fluid_storage_or_branches():
    network = compile_project(ideal_room_example())
    for name in ('branches', 'storage'):
        if hasattr(network, name):
            delattr(network, name)
    session = create_session(network, 10., 5.)
    try:
        initial = session.initialize()
        session.update_controller('room_temperature', 'setpoint', 260.)
        frame = session.advance()
        assert frame.valid and frame.time_s > initial.time_s
        assert frame.variables['controller.room_temperature.setpoint'] == 260.
        assert not hasattr(network, 'trapped')
    finally:
        session.close()
