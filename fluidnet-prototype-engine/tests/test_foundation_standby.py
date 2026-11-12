import pytest

from fn_engine.checkpoints import capture, restore
from fn_engine.compiler import compile_project
from fn_engine.control import ControlRunner
from fn_engine.refrigeration.standby_example import standby_example
from fn_engine.sessions import create_session


def test_actual_duty_failure_switches_both_pairs_and_resume_keeps_control_clock():
    project = standby_example()
    project.events = project.scenarios[0].events
    session = create_session(compile_project(project), .8, .1)
    resumed = None
    try:
        session.initialize()
        for _ in range(3): session.advance()
        resumed = restore(capture(session))
        for _ in range(4):
            a, b = session.advance(), resumed.advance()
            for key in ('script.standby.samples', 'script.standby.last_time_s',
                        'script.standby.state.pump_active', 'script.standby.state.compressor_active',
                        'BackupPump.mass_flow_kg_s', 'Compressor-2.mass_flow_kg_s'):
                assert b.variables[key] == pytest.approx(a.variables[key]), key
        assert a.variables['BackupPump.mass_flow_kg_s'] > .1
        assert a.variables['Pump.mass_flow_kg_s'] == 0.
        assert a.variables['Compressor-2.mass_flow_kg_s'] > .01
        assert a.variables['Compressor-1.mass_flow_kg_s'] == 0.
        assert abs(a.metrics['energy_residual_j']) < .05
    finally:
        session.close()
        if resumed is not None: resumed.close()


def test_failed_standby_latches_all_machines_off():
    script = standby_example().control_scripts[0]
    runner = ControlRunner(script.model_dump(mode='json'))
    state = runner.call('initialize', {'state': {}, 'values': {}})['state']
    values = {key: 1. for key in script.inputs}
    values['High.state.pressure_pa'] = 1e6
    values['Low.state.level_ratio'] = .4
    values['Pump.param.running'] = 0.
    result = runner.call('step', {'state': state, 'values': values, 'time_s': .3, 'dt_s': .1})
    assert result['state']['pump_active'] == 1
    values['BackupPump.mass_flow_kg_s'] = 0.
    result = runner.call('step', {'state': result['state'], 'values': values, 'time_s': .6, 'dt_s': .1})
    assert result['state']['tripped']
    assert set(result['writes'].values()) == {0.}
