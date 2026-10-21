"""Case B2: five loops + upper start/stop on the lumped NH3/CO2 station; acceptance scenarios 1–4.

Steady values are checked against the B0 independent design point (PropsSI only, no engine imports):
cases/cold-storage/nh3-co2/station/references/design_point.json. Full-length runs are in
scripts/verify_station.py; here each scenario is shortened but keeps all of its events.
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import apply_scenario, create_app
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import ScheduleEvent
from fn_engine.refrigeration.examples import STATION_SCENARIO_DURATIONS, station_case, station_example
from fn_engine.sessions import create_session
from test_continuous import wait

ROOT = Path(__file__).resolve().parents[1] / 'cases' / 'cold-storage' / 'nh3-co2' / 'station'
PARAMETERS = json.loads((ROOT / 'parameters.json').read_text(encoding='utf-8'))
DESIGN = json.loads((ROOT / 'references' / 'design_point.json').read_text(encoding='utf-8'))['design']
RUNS = {}


def run(sid, duration):
    if (sid, duration) not in RUNS:
        session = create_session(compile_project(apply_scenario(station_case(), sid)), duration, 60., keep=10000)
        frames = [session.initialize()]
        try:
            while not session.done:
                frames.append(session.advance())
        finally:
            session.close()
        RUNS[(sid, duration)] = [f.variables | {'_t': f.time_s, '_m': f.metrics} for f in frames]
    return RUNS[(sid, duration)]


def after(frames, t0, t1=1e12):
    return [f for f in frames if t0 <= f['_t'] <= t1]


def test_case_parameters_match_the_b0_files():
    p = compile_project(station_case()).parameters
    room, cooler, pump, comp, cond = (PARAMETERS[k] for k in ('rooms', 'air_cooler', 'pump', 'compressors', 'condenser'))
    for r in ('ROOM1', 'ROOM2'):
        for key in ('heat_capacity_j_k', 'wall_ua_w_k', 'roof_ua_w_k', 'floor_ua_w_k', 'ambient_temperature_k', 'ground_temperature_k'):
            assert p[r][key] == room[key], (r, key)
        assert p[r]['heat_input_w'] == room['rated_heat_input_w'] and p[r]['temperature_k'] == room['setpoint_temperature_k']
    for a in ('AC1', 'AC2'):
        for key in ('ua_w_k', 'natural_ua_ratio', 'fan_power_w', 'max_outlet_quality', 'supply_valve_ratio'):
            assert p[a][key] == cooler[key], (a, key)
    for key in ('rated_mass_flow_kg_s', 'rated_pressure_rise_pa', 'efficiency_ratio'):
        assert p['PU1'][key] == pump[key]
    for k in ('K1', 'K2', 'K3', 'K4'):
        for key in ('displacement_m3_s', 'volumetric_efficiency', 'isentropic_efficiency', 'motor_efficiency', 'max_pressure_ratio'):
            assert p[k][key] == pytest.approx(comp[key], rel=1e-12), (k, key)
    for key in ('ua_w_k', 'natural_ua_ratio', 'flooded_ua_ratio', 'fan_power_w', 'wet_bulb_temperature_k'):
        assert p['EC1'][key] == cond[key]
    assert p['HX1']['ua_w_k'] == PARAMETERS['cascade']['ua_w_k'] and p['EV1']['kv_m3_h'] == PARAMETERS['expansion_valve']['kv_m3_h']
    for vessel, key in (('HP1', 'hp_receiver'), ('LP1', 'lp_drum'), ('CD1', 'pumped_drum')):
        for field in ('volume_m3', 'height_m', 'level_ratio'):
            assert p[vessel][field] == PARAMETERS['vessels'][key][field], (vessel, field)
    assert p['LP1']['temperature_k'] == pytest.approx(DESIGN['nh3_low']['saturation_temperature_k'], abs=1e-6)
    assert p['HP1']['temperature_k'] == pytest.approx(DESIGN['condenser']['condensing_temperature_k'], abs=1e-6)
    assert p['CD1']['temperature_k'] == pytest.approx(DESIGN['co2']['saturation_temperature_k'], abs=1e-6)
    controllers = {c.id: c for c in station_case().controllers}
    assert controllers['suction'].setpoint == PARAMETERS['targets']['evaporating_pressure_pa']
    assert controllers['head'].setpoint == PARAMETERS['targets']['condensing_pressure_pa']
    assert controllers['level'].setpoint == PARAMETERS['targets']['hp_level_setpoint']
    assert set(STATION_SCENARIO_DURATIONS) == {s.id for s in station_case().scenarios}


def test_scenario_1_rated_load_settles_on_the_independent_design_point():
    frames = run('B-S01', 21600.)
    v = frames[-1]
    assert v['LP1.state.pressure_pa'] == pytest.approx(DESIGN['nh3_low']['pressure_pa'], rel=1e-5)
    assert v['HP1.state.pressure_pa'] == pytest.approx(DESIGN['condenser']['pressure_pa'], rel=1e-5)
    assert v['CD1.state.temperature_k'] == pytest.approx(DESIGN['co2']['saturation_temperature_k'], abs=1e-3)
    assert v['AC1.param.fan_ratio'] == pytest.approx(DESIGN['cooler']['fan_ratio'], abs=1e-3)
    assert v['PU1.param.speed_ratio'] == pytest.approx(DESIGN['co2']['pump_speed_ratio'], abs=1e-3)
    assert v['EC1.param.return_gas_ratio'] == pytest.approx(DESIGN['condenser']['return_gas_ratio'], abs=1e-3)
    assert v['EV1.param.opening_ratio'] == pytest.approx(DESIGN['expansion_valve']['opening_ratio'], abs=1e-3)
    assert v['script.control.state.running'] == DESIGN['compressors']['running']
    assert v['K1.param.load_ratio'] == pytest.approx(DESIGN['compressors']['load_each'], abs=1e-3)
    assert v['HX1.heat_w'] == pytest.approx(DESIGN['cascade']['heat_w'], rel=1e-4)
    assert v['_m']['electric_power_w'] == pytest.approx(DESIGN['balance']['electric_power_w'], rel=1e-4)
    for f in frames:
        assert abs(f['ROOM1.state.temperature_k'] - 255.15) < 1. and abs(f['ROOM2.state.temperature_k'] - 255.15) < 1.
        assert .6 <= f['HP1.state.level_ratio'] <= .667
    tail = after(frames, 3600.)
    assert max(f['LP1.state.pressure_pa'] for f in tail) - min(f['LP1.state.pressure_pa'] for f in tail) < 100.   # no oscillation
    assert v['script.control.state.satisfaction'] == 1. and v['script.control.state.starts'] == 0
    assert abs(v['_m']['energy_residual_j']) < 10. and all(abs(x) < 1e-9 for k, x in v['_m'].items() if k.startswith('mass_residual'))


def test_scenario_2_load_step_adds_then_removes_a_compressor_and_rooms_recover():
    frames = run('B-S02', 61200.)
    v = frames[-1]
    assert v['script.control.state.starts'] == 1 and v['script.control.state.stops'] == 1
    peak = max(f['script.control.state.running'] for f in after(frames, 21600., 50400.) if 'script.control.state.running' in f)
    assert peak == 4 and v['script.control.state.running'] == 3
    for f in frames:
        assert abs(f['ROOM1.state.temperature_k'] - 255.15) < 1. and abs(f['ROOM2.state.temperature_k'] - 255.15) < 1.
        assert .6 <= f['HP1.state.level_ratio'] <= .667
    assert abs(v['ROOM1.state.temperature_k'] - 255.15) < .05 and v['script.control.state.satisfaction'] == 1.
    # Each running unit stays on at least the minimum on time: one start, one stop, 600 s apart or more.
    on = [f['_t'] for f in frames if f.get('K4.param.running') == 1.]
    assert on and on[-1] - on[0] >= 600.
    assert abs(v['_m']['energy_residual_j']) < 10.


def test_scenario_3_new_targets_are_tracked_and_cost_less_electricity():
    frames = run('B-S03', 54000.)
    before = [f for f in frames if 18000. <= f['_t'] <= 21600.]
    late = after(frames, 50000.)
    assert all(f['LP1.state.pressure_pa'] == pytest.approx(125000., rel=2e-3) for f in late)
    assert all(f['HP1.state.pressure_pa'] == pytest.approx(1200000., rel=2e-3) for f in late)
    assert late[-1]['_m']['electric_power_w'] < before[-1]['_m']['electric_power_w'] - 5000.
    for f in frames:
        assert abs(f['ROOM1.state.temperature_k'] - 255.15) < 1.
    v = frames[-1]
    assert v['script.control.state.starts'] == 0 and v['script.control.state.stops'] == 0
    assert v['_m']['events_applied'] == 7 and v['script.control.state.infeasible'] == 0.


def test_scenario_4_wet_bulb_change_switches_condenser_fans_and_holds_pressure():
    frames = run('B-S04', 61200.)
    low = after(frames, 33000., 50400.)
    assert all(f['EC1.param.fan_ratio'] == .5 for f in low)
    steady = low + after(frames, 59400.)   # after the ramps (last step at 57.6 ks) and fan-group changes have settled
    assert all(f['HP1.state.pressure_pa'] == pytest.approx(1350000., rel=5e-3) for f in steady)
    assert max(abs(f['HP1.state.pressure_pa'] - 1350000.) for f in frames) < 60000.   # transients stay bounded (measured ≈ 46 kPa)
    assert frames[-1]['_m']['events_applied'] == 14
    assert frames[-1]['EC1.param.fan_ratio'] == 1. and frames[-1]['script.control.state.fan_changes'] == 2
    assert frames[-1]['_m']['electric_power_w'] == pytest.approx(DESIGN['balance']['electric_power_w'], rel=1e-3)


def test_unreachable_condensing_target_is_reported():
    project = station_case()
    project.events = [ScheduleEvent(id='low', type='set_variable', time_s=600., key='controller.head.setpoint', value=1150000.)]
    session = create_session(compile_project(project), 3 * 3600., 60., keep=1000)
    logs = []
    try:
        session.initialize()
        while not session.done:
            logs += [d.message for d in session.advance().diagnostics if d.code == 'CONTROL_LOG']
    finally:
        session.close()
    assert any('目标冷凝压力不可达' in m for m in logs)


def test_station_schedule_contract():
    project = station_case()
    project.events = [ScheduleEvent(id='x', type='set_variable', time_s=1., key='K1.param.load_ratio', value=.5)]
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'SCHEDULE_EVENT_CONFLICT'
    for key, value, code in [('HP1.param.volume_m3', 2., 'PARAMETER_NOT_RUNTIME'), ('EC1.param.fan_ratio', 1., 'SCHEDULE_EVENT_CONFLICT'),
                             ('ROOM1.param.heat_input_w', -1., 'SCHEDULE_EVENT_INVALID'), ('nothing.here', 1., 'SCHEDULE_EVENT_TARGET')]:
        project.events = [ScheduleEvent(id='x', type='set_variable', time_s=1., key=key, value=value)]
        with pytest.raises(CompilationError) as error:
            compile_project(project)
        assert error.value.diagnostic.code == code, key
    project = station_example()
    project.events = [ScheduleEvent(id='d', type='electric_defrost', time_s=1.)]
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'SCHEDULE_UNSUPPORTED'
    with pytest.raises(ValueError):
        ScheduleEvent(id='x', type='set_variable', time_s=1., key='a.param.b')


def test_api_report_csv_and_live_target_change(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        project = client.get('/api/v1/examples/cold-storage-nh3co2').json()
        body = {'project': project, 'mode': 'dynamic', 'duration_s': 3600., 'dt_s': 30., 'history': 'trend', 'trend_variables': []}
        run_id = client.post('/api/v1/runs?background=true', json=body | {'start_paused': True}).json()['run_id']
        wait(client, run_id, lambda r: r['status'] == 'paused')
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'controller', 'controller_id': 'suction',
                                                           'parameter_id': 'setpoint', 'value': 115000.}).raise_for_status()
        client.post(f'/api/v1/runs/{run_id}/command', json={'action': 'resume'}).raise_for_status()
        record = wait(client, run_id, lambda r: r['status'] == 'completed', timeout=180)
        assert record['frame']['variables']['controller.suction.setpoint'] == 115000.
        assert record['frame']['variables']['LP1.state.pressure_pa'] == pytest.approx(115000., rel=5e-3)
        report = client.get(f'/api/v1/runs/{run_id}/report.html')
        assert report.status_code == 200 and '制冷站运行报告' in report.text and '需求满足度' in report.text
        lines = client.get(f'/api/v1/runs/{run_id}/report.csv').text.strip().splitlines()
        assert len(lines) == 122 and 'LP1.state.pressure_pa [Pa]' in lines[0]
        assert all(cell != '' for cell in lines[60].split(','))   # slim trend frames keep the report curves
