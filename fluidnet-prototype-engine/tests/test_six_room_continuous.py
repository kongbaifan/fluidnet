"""Acceptance of the integrated six-room topology and its sampled supervision."""
import pytest

from fn_engine.checkpoints import capture, restore
from fn_engine.compiler import compile_project
from fn_engine.control import ControlRunner
from fn_engine.model_types.domain import Project, ScheduleEvent
from fn_engine.refrigeration.six_room_continuous import continuous_large_cold_store
from fn_engine.sessions import create_session


def test_topology_inventory_capacity_and_serialized_project():
    project, assumptions = continuous_large_cold_store()
    restored = Project.model_validate_json(project.model_dump_json())
    network = compile_project(restored)
    assert len(project.instances) == 126
    assert len(project.connections) == 175
    assert len(project.controllers) == 21
    assert len(project.control_scripts) == 2
    assert len(network.vessels) == 3
    assert network.vessel('COND', 'in0') == 'HP'
    assert network.vessel('COND', 'out0') == 'HP'
    assert len(network.room_cooler_groups) == 6
    assert all(len(coolers) == 2 for coolers in network.room_cooler_groups.values())
    nodes = {n.id: n for n in restored.instances}
    for zone in ('LT', 'HT'):
        assert nodes[zone + '_K3'].parameters['displacement_m3_s'] == nodes[zone + '_K1'].parameters['displacement_m3_s']
        assert nodes[zone + '_K3'].parameters['running'] == 0.
        assert nodes[zone + '_K1'].parameters.get('running', 1.) == 1.
        assert nodes[zone + '_K2'].parameters.get('running', 1.) == 1.
    assert len(assumptions['operation']['defrost_order']) == 12
    assert max(sum(n.page_id == page for n in project.instances) for page in {n.page_id for n in project.instances}) <= 64


def supervisor():
    project, _ = continuous_large_cold_store()
    script = project.control_scripts[0]
    runner = ControlRunner(script.model_dump(mode='json'))
    state = runner.call('initialize', {'state': {}, 'values': {}})['state']
    values = {key: 1. for key in script.inputs}
    values.update({'HP.state.pressure_pa': 1e6, 'LP.state.level_ratio': .4, 'IP.state.level_ratio': .4})
    return runner, state, values


def sample(runner, state, values, time):
    return runner.call('step', {'state': state, 'values': values, 'time_s': time, 'dt_s': 30.})


def test_standby_confirmation_minimum_runtime_and_failed_start_latch():
    runner, state, values = supervisor()
    values['LT_PUMP.param.running'] = 0.
    first = sample(runner, state, values, 300.)
    assert first['writes']['LT_PUMP2.param.running'] == 0.
    started = sample(runner, first['state'], values, 330.)
    assert started['writes']['LT_PUMP2.param.running'] == 1.
    values['LT_PUMP.param.running'] = 1.
    early = sample(runner, started['state'], values, 360.)
    assert early['writes']['LT_PUMP2.param.running'] == 1.
    stopped = sample(runner, early['state'], values, 450.)
    assert stopped['writes']['LT_PUMP2.param.running'] == 0.
    values['LT_PUMP.param.running'] = 0.
    fault = sample(runner, stopped['state'], values, 600.)
    restarted = sample(runner, fault['state'], values, 630.)
    values['LT_PUMP2.mass_flow_kg_s'] = 0.
    failed = sample(runner, restarted['state'], values, 660.)
    assert failed['state']['low_pumps_failed_start']
    assert failed['writes']['LT_PUMP2.param.running'] == 0.
    inhibited = sample(runner, failed['state'], values, 900.)
    assert inhibited['writes']['LT_PUMP2.param.running'] == 0.
    assert inhibited['state']['low_pumps_starts'] == 2


def test_supervisor_blocks_start_at_low_inventory_and_staggers_every_day():
    runner, state, values = supervisor()
    values['LT_K1.param.running'] = 0.
    values['LP.state.level_ratio'] = .01
    state = sample(runner, state, values, 0.)['state']
    result = sample(runner, state, values, 60.)
    assert result['writes']['LT_K3.param.running'] == 0.
    state = result['state']
    for day in (0., 86400.):
        requested = []
        for slot in range(12):
            result = sample(runner, state, values, day + 14400. + slot * 1200.)
            state = result['state']
            active = [k for k, v in result['writes'].items() if k.endswith('.defrost_request') and v == 1.]
            assert len(active) == 1
            requested.extend(active)
        assert len(set(requested)) == 12
        assert all('_AC1.' in k for k in requested[:6])
        assert all('_AC2.' in k for k in requested[6:])


def test_integrated_steps_and_checkpoint_retain_all_inventories():
    project, _ = continuous_large_cold_store()
    session = create_session(compile_project(project), None, 30., keep=8)
    branch = None
    try:
        initial = session.initialize()
        first = session.advance()
        assert first.time_s == 30.
        assert first.variables['F01_AC1.in0.mass_flow_kg_s'] == pytest.approx(-first.variables['F01_AC1.out0.mass_flow_kg_s'])
        assert first.variables['F01_AC1.hot_in.mass_flow_kg_s'] == 0.
        assert first.variables['LT_PUMP.out0.mass_flow_kg_s'] < 0.
        assert first.variables['COND.in0.pressure_pa'] > first.variables['LP.state.pressure_pa']
        assert first.variables['F01_AC1.frost_mass_kg'] != initial.variables['F01_AC1.frost_mass_kg']
        for pump in ('LT_PUMP2', 'MT_PUMP2'):
            assert abs(first.variables[pump + '.mass_flow_kg_s']) < 1e-10
        branch = restore(capture(session))
        a, b = session.advance(), branch.advance()
        for key, value in a.variables.items():
            if isinstance(value, (int, float)):
                assert b.variables[key] == pytest.approx(value, rel=1e-10, abs=1e-6), key
        assert abs(a.metrics['energy_residual_j']) < .05
        assert abs(a.metrics['mass_residual_kg_circuit0']) < 1e-7
        assert abs(a.metrics['water_mass_residual_kg']) < 1e-8
        assert all(abs(a.variables[oil + '.oil_mass_residual_kg']) < 1e-8 for oil in ('LT_OIL', 'HT_OIL'))
    finally:
        session.close()
        if branch: branch.close()


def test_second_temperature_zone_switches_real_pump_and_compressor_capacity():
    project, _ = continuous_large_cold_store()
    project.events = [ScheduleEvent(id=f'{iid}-{t}', type='set_variable', time_s=t,
        key=iid + '.param.running', value=value) for t, value in ((60, 0.), (240, 1.))
        for iid in ('HT_K1', 'MT_PUMP')]
    session = create_session(compile_project(project), 300., 30., keep=8)
    switched = False
    try:
        session.initialize()
        while session.time < 300.:
            frame = session.advance()
            v = frame.variables
            switched |= v['HT_K3.param.running'] == v['MT_PUMP2.param.running'] == 1. and (
                v['HT_K3.mass_flow_kg_s'] > .01 and v['MT_PUMP2.mass_flow_kg_s'] > .1)
        assert switched
        assert v['HT_K3.param.running'] == v['MT_PUMP2.param.running'] == 0.
        assert v['HT_K1.mass_flow_kg_s'] > .01 and v['MT_PUMP.mass_flow_kg_s'] > .1
        assert abs(frame.metrics['energy_residual_j']) < .05
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-7
    finally: session.close()
