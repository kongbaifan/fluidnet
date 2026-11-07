"""Behavior at shared command/lifecycle boundaries, using real compiled projects."""
from copy import deepcopy

import pytest

from fn_engine.compiler import compile_project
from fn_engine.models import ControlScript
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


def test_public_control_preview_returns_an_unaccepted_detached_proposal():
    project = ideal_room_example()
    project.controllers = []
    project.control_scripts = [ControlScript(id='preview', enabled=True, sample_s=5., inputs=[],
        outputs=['ROOM1.param.heat_input_w'], source='''
def initialize(ctx):
    ctx.state['count'] = 0
def step(ctx, dt_s):
    ctx.state['count'] += 1
    ctx.write('ROOM1.param.heat_input_w', 1234.)
def finalize(ctx):
    pass
''')]
    session = create_session(compile_project(project), 10., 5.)
    try:
        session.initialize()
        proposal = session.preview_control('preview')
        assert proposal['writes']['ROOM1.param.heat_input_w'] == 1234.
        assert proposal['state']['count'] == 1
        assert session.snapshot().variables['script.preview.state.count'] == 0
        proposal['state']['count'] = 999
        assert session.advance().variables['script.preview.state.count'] == 1
    finally:
        session.close()


def test_unknown_control_preview_does_not_change_an_initialized_session():
    session = create_session(compile_project(ideal_room_example()), 10., 5.)
    try:
        before = session.initialize()
        with pytest.raises(ValueError, match='控制脚本不存在'):
            session.preview_control('missing')
        assert session.snapshot().variables == before.variables
        assert session.revision == 0
    finally:
        session.close()
