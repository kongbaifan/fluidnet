"""Case A (A2–A4): single-stage cycle, room + goods + cooler coupling, schedule events and thermostat control.

Expected values come from the A0 independent reference (cases/cold-storage/tools/verify_reference.py, which
calls CoolProp PropsSI directly and imports no engine code) or from closed-form solutions.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from fn_engine.api import apply_scenario, create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.catalog import catalog_map, cold_store_catalog
from fn_engine.compiler import CompilationError, compile_project, validate_project_details
from fn_engine.models import ControlScript, FluidConfig, ModuleInstance, ScheduleEvent
from fn_engine.properties import property_service
from fn_engine.refrigeration import cold_store
from fn_engine.refrigeration.cycle import DeviceRangeError, check_envelope, cycle_point, rated_design
from fn_engine.refrigeration.examples import ROOM_SCENARIO_DURATIONS, room_example
from fn_engine.refrigeration.report import series_keys
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed, solve_steady
from test_continuous import wait

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'cases' / 'cold-storage' / 'single-room-minus18'
PARAMETERS = json.loads((CASE / 'parameters.json').read_text(encoding='utf-8'))
REFERENCE = json.loads((CASE / 'references' / 'workpoints.json').read_text(encoding='utf-8'))


def independent_reference():
    spec = importlib.util.spec_from_file_location('verify_reference', ROOT / 'cases' / 'cold-storage' / 'tools' / 'verify_reference.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unit_parameters():
    unit = next(m for m in cold_store_catalog() if m.id == 'condensing_unit')
    return {p.id: p.default for p in unit.parameters}


def service():
    return property_service(FluidConfig(fluid='HEOS::R290', phase_policy='any'))


def run(project, duration, dt=30., scenario=None):
    network = compile_project(apply_scenario(project, scenario))
    session = create_session(network, duration, dt, keep=100000)
    frames = []
    try:
        frames.append(session.initialize())
        while not session.done:
            frames.append(session.advance())
    finally:
        session.close()
    return network, frames


def without_control(**instance_parameters):
    project = room_example()
    project.control_scripts = []
    for instance in project.instances:
        instance.parameters.update(instance_parameters.get(instance.id, {}))
    return project


# --- A2: cycle and workpoint bench -------------------------------------------------------------

@pytest.mark.parametrize('name, te, tc, capacity', [('rated', 245.15, 313.15, 1.), ('lower_evaporation', 241.15, 313.15, 1.),
                                                    ('high_condensation', 245.15, 319.15, 1.), ('half_capacity', 245.15, 313.15, .5)])
def test_cycle_matches_independent_reference_workpoints(name, te, tc, capacity):
    p = unit_parameters()
    design = rated_design(service(), p)
    assert design['displacement_m3_s'] == pytest.approx(REFERENCE['design']['fixed_displacement_m3_s'], rel=1e-12)
    assert design['condenser_ua_w_k'] == pytest.approx(REFERENCE['design']['condenser_ua_w_k'], rel=1e-12)
    point, ref = cycle_point(service(), p, design['displacement_m3_s'], te, tc, capacity), REFERENCE['workpoints'][name]
    for key, expected in [('mass_flow_kg_s', 'mass_flow_kg_s'), ('cooling_power_w', 'cooling_power_w'),
                          ('shaft_power_w', 'shaft_power_w'), ('electric_power_w', 'compressor_electric_power_w'),
                          ('condenser_heat_w', 'condenser_rejection_power_w'), ('pressure_ratio', 'pressure_ratio'),
                          ('cop', 'cop_compressor_electric'), ('isentropic_enthalpy_j_kg', 'isentropic_discharge_enthalpy_j_kg')]:
        assert point[key] == pytest.approx(ref[expected], rel=1e-9), key
    for i in range(1, 5):
        for key in ('pressure_pa', 'enthalpy_j_kg', 'temperature_k', 'entropy_j_kg_k'):
            assert point[f'state{i}.{key}'] == pytest.approx(ref['states'][str(i)][key], rel=1e-9), (i, key)
    assert point['state4.quality'] == pytest.approx(ref['states']['4']['quality'], rel=1e-9)
    assert point['state1.quality'] is None and point['state3.quality'] is None
    scale = max(point['condenser_heat_w'], point['cooling_power_w'], point['shaft_power_w'])
    assert abs(point['cycle_residual_w']) <= max(1., 1e-6 * scale)
    # Carnot bound on the saturation temperatures (shaft COP).
    assert point['cooling_power_w'] / point['shaft_power_w'] < te / (tc - te)


@pytest.mark.parametrize('te, tc, field', [(230.15, 313.15, 'min_evaporating_temperature_k'),
                                           (265.15, 313.15, 'max_evaporating_temperature_k'),
                                           (245.15, 295.15, 'min_condensing_temperature_k'),
                                           (245.15, 325.15, 'max_condensing_temperature_k')])
def test_envelope_is_checked_field_by_field(te, tc, field):
    p = unit_parameters()
    point = cycle_point(service(), p, rated_design(service(), p)['displacement_m3_s'], te, tc, 1.)
    with pytest.raises(DeviceRangeError) as error:
        check_envelope(p, point)
    assert error.value.code == 'REFRIGERATION_ENVELOPE' and error.value.field == field


def test_discharge_and_pressure_ratio_limits_and_impossible_points():
    p = unit_parameters() | {'max_discharge_temperature_k': 340.15}
    design = rated_design(service(), p)
    with pytest.raises(DeviceRangeError) as error:
        check_envelope(p, cycle_point(service(), p, design['displacement_m3_s'], 245.15, 313.15, 1.))
    assert error.value.field == 'max_discharge_temperature_k'
    p = unit_parameters() | {'max_pressure_ratio': 5.}
    with pytest.raises(DeviceRangeError) as error:
        check_envelope(p, cycle_point(service(), p, design['displacement_m3_s'], 245.15, 313.15, 1.))
    assert error.value.field == 'max_pressure_ratio'
    with pytest.raises(DeviceRangeError) as error:
        cycle_point(service(), unit_parameters(), design['displacement_m3_s'], 300., 290., 1.)
    assert error.value.code == 'CYCLE_PRESSURE_RATIO'


def test_workpoint_bench_api_uses_the_same_cycle():
    with TestClient(create_app()) as client:
        ok = client.post('/api/v1/cold-store/workpoint', json={'evaporating_temperature_k': 245.15, 'condensing_temperature_k': 313.15})
        assert ok.status_code == 200, ok.text
        body, ref = ok.json(), REFERENCE['workpoints']['rated']
        assert body['point']['cooling_power_w'] == pytest.approx(ref['cooling_power_w'], rel=1e-9)
        assert body['unit_electric_power_w'] == pytest.approx(ref['compressor_electric_power_w'] + 200., rel=1e-9)
        assert body['diagnostics'] == []
        outside = client.post('/api/v1/cold-store/workpoint', json={'evaporating_temperature_k': 245.15, 'condensing_temperature_k': 325.15})
        assert outside.status_code == 200 and outside.json()['diagnostics'][0]['code'] == 'REFRIGERATION_ENVELOPE'
        bad = client.post('/api/v1/cold-store/workpoint', json={'evaporating_temperature_k': 245.15, 'condensing_temperature_k': 313.15,
                                                                 'parameters': {'isentropic_efficiency': 1.5}})
        assert bad.status_code == 422 and bad.json()['detail']['code'] == 'PARAMETER_RANGE'
        water = client.post('/api/v1/cold-store/workpoint', json={'evaporating_temperature_k': 245.15, 'condensing_temperature_k': 313.15,
                                                                   'fluid': {'fluid': 'Water'}})
        assert water.status_code == 422


def test_cold_store_project_needs_a_refrigerant_and_a_valid_topology():
    project = room_example()
    project.fluid = FluidConfig(fluid='Water')
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'CYCLE_DESIGN_INVALID' and error.value.diagnostic.instance_id == 'CU1'
    project = room_example()
    project.connections = project.connections[:1]
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'COLD_STORE_CONNECTION_MISSING'
    project = room_example()
    project.connections[1].target.instance_id, project.connections[1].target.port_id = 'AC1', 'supply'
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'COLD_STORE_CONNECTION_INVALID'
    project = room_example()
    project.modules.append(catalog_map()['ideal_cold_source'])
    project.instances.append(ModuleInstance(id='COLD1', module_id='ideal_cold_source', name='x'))
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'COLD_STORE_MODEL_UNSUPPORTED'
    with pytest.raises(CompilationError) as error:
        solve_steady(compile_project(room_example()))
    assert error.value.diagnostic.code == 'COLD_STORE_DYNAMIC_REQUIRED'


def test_room_must_be_fed_through_a_cooler():
    project = room_example()
    project.instances.append(ModuleInstance(id='AC2', module_id='unit_cooler', name='第二台冷风机'))
    links = {'cold1': ('CU1', 'cold', 'ROOM1', 'heat'), 'heat1': ('AC1', 'heat', 'AC2', 'supply')}
    for connection in project.connections:
        a, pa, b, pb = links[connection.id]
        connection.source.instance_id, connection.source.port_id = a, pa
        connection.target.instance_id, connection.target.port_id = b, pb
    extra = project.connections[1].model_copy(deep=True)
    extra.id, extra.source.instance_id, extra.target.instance_id, extra.target.port_id = 'heat2', 'AC2', 'AC1', 'supply'
    project.connections.append(extra)
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'COLD_STORE_TOPOLOGY'


# --- A3: room, goods and cooler coupling ------------------------------------------------------

def test_closed_room_and_goods_conserve_energy_and_reach_the_capacity_weighted_temperature():
    project = without_control(ROOM1={'wall_ua_w_k': 0., 'roof_ua_w_k': 0., 'floor_ua_w_k': 0.},
                              CU1={'run_request': 0.})
    network, frames = run(project, 21600.)
    p = network.parameters['ROOM1']
    c_room, c_goods = p['heat_capacity_j_k'], p['goods_mass_kg'] * p['goods_specific_heat_j_kg_k']
    expected = (c_room * p['temperature_k'] + c_goods * p['goods_temperature_k']) / (c_room + c_goods)
    last = frames[-1].variables
    # Coupling time constant ≈ 1/(UA_g·(1/C_r + 1/C_g)) ≈ 1.8 ks: after 6 h the initial 5 K gap is ~1e-5 K.
    assert last['ROOM1.state.temperature_k'] == pytest.approx(expected, abs=1e-4)
    assert last['ROOM1.state.goods_temperature_k'] == pytest.approx(expected, abs=1e-4)
    assert abs(last['ROOM1.state.temperature_k'] - last['ROOM1.state.goods_temperature_k']) < 1e-4
    stored = [f.variables['ROOM1.stored_energy_j'] for f in frames]
    assert max(stored) - min(stored) < 1e-3
    assert last['CU1.state.starts'] == 0 and last['CU1.state.electric_energy_j'] == 0
    # Goods respond more slowly than the room: the room has moved further from its start after 10 min.
    early = frames[20].variables
    assert abs(early['ROOM1.state.temperature_k'] - p['temperature_k']) > abs(early['ROOM1.state.goods_temperature_k'] - p['goods_temperature_k'])


def test_coupled_frames_satisfy_coil_condenser_and_cycle_relations_independently():
    reference = independent_reference()
    machine = deepcopy(PARAMETERS['refrigeration'])
    network, frames = run(room_example(), 7200., scenario='A-S02')
    design = network.designs['CU1']
    running = [f for f in frames if f.variables['CU1.state.running'] == 1.]
    assert len(running) > 50
    for frame in running[::10]:
        v = frame.variables
        te, tc = v['CU1.evaporating_temperature_k'], v['CU1.condensing_temperature_k']
        ref = reference.cycle_point(machine, te, tc, v['CU1.actual_capacity_ratio'], design['displacement_m3_s'])
        assert v['CU1.cooling_power_w'] == pytest.approx(ref['cooling_power_w'], rel=1e-9)
        assert v['CU1.electric_power_w'] == pytest.approx(ref['compressor_electric_power_w'], rel=1e-9)
        assert v['CU1.discharge_temperature_k'] == pytest.approx(ref['states']['2']['temperature_k'], rel=1e-9)
        # Coil: UA_e·(T_room − T_evap) = Q_evap; condenser: UA_c·(T_cond − T_amb) = Q_cond (Newton tolerance 1e-8 · 10 kW).
        assert 1000. * (v['ROOM1.state.temperature_k'] - te) == pytest.approx(v['CU1.cooling_power_w'], abs=1e-3)
        assert design['condenser_ua_w_k'] * (tc - v['CU1.param.ambient_temperature_k']) == pytest.approx(v['CU1.condenser_heat_w'], abs=1e-3)
        assert v['ROOM1.cooling_power_w'] == pytest.approx(v['CU1.cooling_power_w'], abs=1e-3)
        assert te < v['ROOM1.state.temperature_k'] and tc > v['CU1.param.ambient_temperature_k']
    assert max(abs(f.metrics['coupling_residual_w']) for f in frames) < 1e-3


def test_independent_energy_ledger_from_published_counters():
    network, frames = run(room_example(), 10800., scenario='A-S03')
    first, last = frames[0].variables, frames[-1].variables
    inflow = (last['ROOM1.state.external_energy_j'] + last['ROOM1.state.goods_energy_j'] + last['AC1.state.fan_energy_j']
              + network.parameters['AC1']['defrost_room_fraction'] * last['AC1.state.heater_energy_j'])
    stored = last['ROOM1.stored_energy_j'] - first['ROOM1.stored_energy_j']
    residual = stored - (inflow - last['ROOM1.state.cooling_energy_j'])
    scale = inflow + last['ROOM1.state.cooling_energy_j']
    assert abs(residual) < max(100., 1e-3 * scale) and abs(residual) < 1.
    assert abs(frames[-1].metrics['energy_residual_j']) < 1e-2
    # Room-side coil energy and cycle cooling energy agree; Q_cond = Q_evap + P_shaft in the counters.
    assert last['ROOM1.state.cooling_energy_j'] == pytest.approx(last['CU1.state.cooling_energy_j'], abs=1.)
    shaft = last['CU1.state.electric_energy_j'] * network.parameters['CU1']['motor_efficiency']
    assert last['CU1.state.condenser_heat_j'] == pytest.approx(last['CU1.state.cooling_energy_j'] + shaft, rel=1e-9)


def test_step_sensitivity_default_half_quarter():
    """PLAN 5.1. Substeps are already cut at the 5 s control samples, so the effective default step is 5 s.

    Thermostat switching happens at sample instants; a smaller step can move one switch by a sample and shift
    the on/off phase, so the comparison uses the key indicators, not frame-by-frame values."""
    results = {}
    for step in (5., 2.5, 1.25):
        project = room_example()
        project.solver.dynamic_step_s = step
        _, frames = run(project, 14400., scenario='A-S02')
        temperatures = [f.variables['ROOM1.state.temperature_k'] for f in frames if f.time_s >= 1200.]
        v = frames[-1].variables
        results[step] = {'mean': sum(temperatures) / len(temperatures), 'max': v['ROOM1.state.max_service_temperature_k'],
                         'min': v['ROOM1.state.min_service_temperature_k'], 'goods': v['ROOM1.state.goods_temperature_k'],
                         'electric': v['CU1.state.electric_energy_j'], 'pulldown': v['ROOM1.state.pulldown_time_s']}
    for coarse, fine in ((5., 1.25), (2.5, 1.25)):
        a, b = results[coarse], results[fine]
        for key in ('mean', 'max', 'min', 'goods'):
            assert abs(a[key] - b[key]) <= .1, (coarse, key)
        assert a['electric'] == pytest.approx(b['electric'], rel=.01), coarse
        assert abs(a['pulldown'] - b['pulldown']) <= 30., coarse
    assert all(r['max'] < 256.15 for r in results.values())


def test_envelope_violation_stops_with_the_accepted_frames():
    project = room_example()
    project.events = [ScheduleEvent(id='heatwave', type='ambient_temperature', time_s=3600., temperature_k=323.15)]
    with pytest.raises(SolveFailed) as error:
        run(project, 7200.)
    diagnostic = error.value.diagnostic
    assert diagnostic.code == 'REFRIGERATION_ENVELOPE' and diagnostic.instance_id == 'CU1'
    assert diagnostic.field == 'max_condensing_temperature_k'
    assert error.value.frames and 3600. <= error.value.frames[-1].time_s < 7200.


def test_goods_leaving_the_frozen_model_range_stops_the_run():
    project = without_control(ROOM1={'heat_input_w': 20000., 'goods_ua_w_k': 5000.}, CU1={'run_request': 0.})
    with pytest.raises(SolveFailed) as error:
        run(project, 7200.)
    assert error.value.diagnostic.code == 'GOODS_TEMPERATURE_RANGE' and error.value.diagnostic.instance_id == 'ROOM1'


# --- A4: switching, control and schedule --------------------------------------------------------

TOGGLE = '''def initialize(ctx):
    pass
def step(ctx, dt_s):
    ctx.write("CU1.param.run_request", 0.0 if ctx.read("CU1.state.running") >= 0.5 else 1.0)
def finalize(ctx):
    pass
'''


def toggling(**instance_parameters):
    project = without_control(**instance_parameters)
    project.control_scripts = [ControlScript(id='control', enabled=True, source=TOGGLE, sample_s=5.,
                                             inputs=['CU1.state.running'], outputs=['CU1.param.run_request'])]
    return project


def test_minimum_on_and_off_times_are_never_shortened():
    # A request opposite to the current state every 5 s: the unit runs exactly minimum_on, then rests minimum_off.
    _, frames = run(toggling(ROOM1={'temperature_k': 258.15}), 3600., dt=5.)
    last = frames[-1].variables
    assert last['CU1.state.starts'] == 12
    assert last['CU1.state.run_time_s'] == pytest.approx(12 * 120., abs=1e-6)
    changes = [f.time_s for a, f in zip(frames, frames[1:]) if a.variables['CU1.state.running'] != f.variables['CU1.state.running']]
    # A frame shows the substep that ended at its time: switching at 0/120/300/420 s appears 5 s later.
    assert changes[:4] == pytest.approx([5., 125., 305., 425.])
    assert any(f.variables['CU1.state.switch_blocked'] == 1. for f in frames)
    # The initial off time counts: with 0 s already off, the first start waits the full 180 s.
    _, frames = run(toggling(ROOM1={'temperature_k': 258.15}, CU1={'initial_off_elapsed_s': 0.}), 600., dt=5.)
    first = next(f.time_s for f in frames if f.variables['CU1.state.running'] == 1.)
    assert first == pytest.approx(185.)


def test_thermostat_direction_and_variable_capacity_request():
    network, frames = run(room_example(), 10800.)
    for a, b in zip(frames, frames[1:]):
        t = a.variables['ROOM1.state.temperature_k']
        if t >= 255.65 + .05 and a.variables['CU1.state.state_elapsed_s'] >= 180.:
            assert b.variables['CU1.state.running'] == 1.
        if t <= 254.65 - .05 and a.variables['CU1.state.state_elapsed_s'] >= 120.:
            assert b.variables['CU1.state.running'] == 0.
    _, frames = run(room_example(), 10800., scenario='A-S05-variable')
    running = [f.variables for f in frames if f.variables['CU1.state.running'] == 1.]
    pulldown = [v['CU1.actual_capacity_ratio'] for v in running if v['ROOM1.state.temperature_k'] > 258.15]
    holding = [v['CU1.actual_capacity_ratio'] for v in running if abs(v['ROOM1.state.temperature_k'] - 255.15) < .3]
    assert pulldown and min(pulldown) == 1.
    assert holding and max(holding) < 1. and min(holding) >= .35
    assert frames[-1].variables['CU1.state.starts'] < 10


def test_schedule_door_goods_and_ambient_apply_once_at_their_time():
    network, frames = run(room_example(), 10800., scenario='A-S02')
    door = {f.time_s: f.variables['ROOM1.door_heat_w'] for f in frames}
    assert door[7200.] == 0 and door[7230.] == 5000. and door[7800.] == 5000. and door[7830.] == 0.
    assert sum(1 for f in frames for d in f.diagnostics if d.code == 'SCHEDULE_EVENT') == 1
    assert frames[-1].metrics['events_applied'] == 1
    _, frames = run(room_example(), 9000., scenario='A-S03')
    before = next(f for f in frames if f.time_s == 7200.).variables
    after = next(f for f in frames if f.time_s == 7230.).variables
    assert after['ROOM1.state.goods_mass_kg'] == 2500.
    assert after['ROOM1.state.goods_energy_j'] == pytest.approx(500 * 1800. * (261.15 - 253.15))
    assert after['ROOM1.goods_ua_w_k'] == pytest.approx(500. * 2500 / 2000)
    mixed = (2000 * before['ROOM1.state.goods_temperature_k'] + 500 * 261.15) / 2500
    assert after['ROOM1.state.goods_temperature_k'] == pytest.approx(mixed, abs=.05)
    _, frames = run(room_example(), 9000., scenario='A-S04')
    at = {f.time_s: f.variables for f in frames}
    assert at[7200.]['CU1.param.ambient_temperature_k'] == 305.15
    assert at[7230.]['CU1.param.ambient_temperature_k'] == at[7230.]['ROOM1.param.ambient_temperature_k'] == 311.15
    hot = [v['CU1.condensing_temperature_k'] for t, v in at.items() if t > 7300 and v['CU1.state.running'] == 1.]
    cool = [v['CU1.condensing_temperature_k'] for t, v in at.items() if 3600 < t < 7200 and v['CU1.state.running'] == 1.]
    assert min(hot) > max(cool) + 4.


def test_defrost_waits_for_minimum_on_then_heats_drips_and_recovers():
    project = room_example()
    project.events = [ScheduleEvent(id='d1', type='electric_defrost', time_s=60.),
                      ScheduleEvent(id='d2', type='electric_defrost', time_s=600.)]
    network, frames = run(project, 2400., dt=5.)
    mode = {f.time_s: f.variables['AC1.state.mode'] for f in frames}
    pending = {f.time_s: f.variables['AC1.state.defrost_pending'] for f in frames}
    # Started at t=0 (5 s sample), the unit must run 120 s before defrost may stop it.
    assert pending[65.] == 1. and mode[115.] == 0. and mode[125.] == 1.
    assert mode[120. + 900. - 5] == 1. and mode[120. + 900. + 5] == 2.
    assert mode[120. + 1200. - 5] == 2. and mode[120. + 1200. + 5] == 0.
    during = [f.variables for f in frames if 125. <= f.time_s <= 1315.]
    assert all(v['CU1.state.running'] == 0. and v['AC1.state.fan_running'] == 0. for v in during)
    last = frames[-1].variables
    assert last['AC1.state.heater_energy_j'] == pytest.approx(900 * 1500.)
    assert last['AC1.state.defrost_count'] == 1.
    assert any(d.code == 'DEFROST_REQUEST_IGNORED' for f in frames for d in f.diagnostics)


def test_retried_substeps_do_not_double_count(monkeypatch):
    _, reference = run(room_example(), 1800., scenario='A-S02')
    original, failures = cold_store.ColdStoreSession._trial, {'left': 3}

    def flaky(self, chain, h):
        if h > 1. and self.units[chain[0]]['running'] and failures['left']:
            failures['left'] -= 1
            raise DeviceRangeError('COLD_STORE_NOT_CONVERGED', 'forced', chain[0])
        return original(self, chain, h)

    monkeypatch.setattr(cold_store.ColdStoreSession, '_trial', flaky)
    _, retried = run(room_example(), 1800., scenario='A-S02')
    assert failures['left'] == 0
    a, b = reference[-1].variables, retried[-1].variables
    # Halved substeps change the integration slightly; counters are not added twice.
    assert b['CU1.state.run_time_s'] == pytest.approx(a['CU1.state.run_time_s'], abs=5.)
    assert b['CU1.state.electric_energy_j'] == pytest.approx(a['CU1.state.electric_energy_j'], rel=.01)
    assert abs(retried[-1].metrics['energy_residual_j']) < 1e-2


def test_example_reproduces_the_case_scenarios_and_parameters():
    data = json.loads((CASE / 'scenarios.json').read_text(encoding='utf-8'))
    project = room_example()
    scenarios = {s.id: s for s in project.scenarios}
    for item in data['scenarios']:
        ids = [f'{item["id"]}-onoff', f'{item["id"]}-variable'] if len(item['control_modes']) > 1 else [item['id']]
        for sid in ids:
            scenario = scenarios[sid]
            assert ROOM_SCENARIO_DURATIONS[sid] == item['duration_s']
            events = [{k: v for k, v in e.model_dump().items() if v is not None} for e in scenario.events]
            assert events == item['events']
            overrides = {('refrigeration.rated_cooling_power_w' if k == 'rated_cooling_power_w' else k): v
                         for k, v in scenario.overrides.get('CU1', {}).items() if k != 'variable_capacity'}
            assert overrides == item['overrides']
    network = compile_project(project)
    room, unit, cooler = (network.parameters[i] for i in ('ROOM1', 'CU1', 'AC1'))
    r, g, m, c, d = (PARAMETERS[k] for k in ('room', 'goods', 'refrigeration', 'control', 'defrost'))
    assert room['wall_ua_w_k'] == pytest.approx(2 * (r['length_m'] + r['width_m']) * r['height_m'] * r['wall_u_w_m2_k'])
    assert room['roof_ua_w_k'] == pytest.approx(r['length_m'] * r['width_m'] * r['roof_u_w_m2_k'])
    assert room['floor_ua_w_k'] == pytest.approx(r['length_m'] * r['width_m'] * r['floor_u_w_m2_k'])
    for key, value in [('temperature_k', r['initial_temperature_k']), ('setpoint_temperature_k', r['setpoint_temperature_k']),
                       ('heat_capacity_j_k', r['effective_heat_capacity_j_k']), ('ambient_temperature_k', r['ambient_temperature_k']),
                       ('ground_temperature_k', r['ground_temperature_k']), ('lighting_power_w', r['lighting_power_w']),
                       ('goods_mass_kg', g['mass_kg']), ('goods_specific_heat_j_kg_k', g['specific_heat_j_kg_k']),
                       ('goods_temperature_k', g['initial_temperature_k']), ('goods_ua_w_k', g['room_ua_w_k']),
                       ('goods_min_temperature_k', g['valid_temperature_range_k'][0]),
                       ('goods_max_temperature_k', g['valid_temperature_range_k'][1]),
                       ('energy_reference_temperature_k', g['energy_reference_temperature_k']),
                       ('hysteresis_k', c['start_temperature_k'] - r['setpoint_temperature_k'])]:
        assert room[key] == pytest.approx(value), key
    assert r['setpoint_temperature_k'] - c['stop_temperature_k'] == pytest.approx(room['hysteresis_k'])
    for key, value in [('rated_cooling_power_w', m['rated_cooling_power_w']), ('superheat_k', m['superheat_k']),
                       ('rated_evaporating_temperature_k', m['rated_evaporating_temperature_k']),
                       ('rated_condensing_temperature_k', m['rated_condensing_temperature_k']),
                       ('subcooling_k', m['subcooling_k']), ('isentropic_efficiency', m['isentropic_efficiency']),
                       ('volumetric_efficiency', m['volumetric_efficiency']), ('motor_efficiency', m['motor_efficiency']),
                       ('min_capacity_ratio', m['capacity_ratio_minimum']), ('condenser_fan_power_w', m['condenser_fan_power_w']),
                       ('minimum_on_s', c['minimum_on_s']), ('minimum_off_s', c['minimum_off_s']),
                       ('initial_off_elapsed_s', c['initial_off_elapsed_s']),
                       ('max_discharge_temperature_k', m['model_limits']['discharge_temperature_maximum_k']),
                       ('max_pressure_ratio', m['model_limits']['pressure_ratio_maximum'])]:
        assert unit[key] == pytest.approx(value), key
    assert [unit['min_evaporating_temperature_k'], unit['max_evaporating_temperature_k']] == m['model_limits']['evaporating_temperature_k']
    assert [unit['min_condensing_temperature_k'], unit['max_condensing_temperature_k']] == m['model_limits']['condensing_temperature_k']
    for key, value in [('ua_w_k', m['evaporator_ua_w_k']), ('fan_power_w', m['evaporator_fan_power_w']),
                       ('defrost_heater_power_w', d['heater_power_w']), ('defrost_duration_s', d['heating_duration_s']),
                       ('drip_duration_s', d['drip_wait_s']), ('defrost_room_fraction', d['room_heat_fraction'])]:
        assert cooler[key] == pytest.approx(value), key
    assert project.fluid.fluid == m['fluid'] and project.control_scripts[0].sample_s == c['sample_s']
    assert project.solver.dynamic_step_s == PARAMETERS['numerics']['internal_step_maximum_s']


def test_schedule_contract_and_validation():
    with pytest.raises(ValidationError):
        ScheduleEvent(id='x', type='door_heat', time_s=0., heat_w=1.)
    with pytest.raises(ValidationError):
        ScheduleEvent(id='x', type='electric_defrost', time_s=0., heat_w=1.)
    door = ScheduleEvent(id='a', type='door_heat', time_s=1., duration_s=1., heat_w=1.)
    for events, code in [([ScheduleEvent(id='g', type='goods_addition', time_s=10., mass_kg=10., temperature_k=270.)], 'SCHEDULE_EVENT_INVALID'),
                         ([door, door], 'SCHEDULE_EVENT_INVALID'),
                         ([ScheduleEvent(id='d', type='electric_defrost', time_s=1., instance_id='ROOM1')], 'SCHEDULE_EVENT_TARGET')]:
        project = room_example()
        project.events = events
        with pytest.raises(CompilationError) as error:
            compile_project(project)
        assert error.value.diagnostic.code == code
    project = room_example()
    project.control_scripts[0].outputs.append('CU1.param.ambient_temperature_k')
    project.events = [ScheduleEvent(id='hot', type='ambient_temperature', time_s=1., temperature_k=310.)]
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'SCHEDULE_EVENT_CONFLICT'
    from fn_engine.refrigeration.examples import ideal_room_example
    project = ideal_room_example()
    project.events = [door]
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'SCHEDULE_UNSUPPORTED'
    project = room_example()
    project.scenarios[1].events = [ScheduleEvent(id='g', type='goods_addition', time_s=10., mass_kg=10., temperature_k=270.)]
    diagnostics, _ = validate_project_details(project)
    assert any(d.code == 'SCHEDULE_EVENT_INVALID' and 'A-S02' in d.message for d in diagnostics)
    project = room_example()
    project.events = [ScheduleEvent(id='late', type='door_heat', time_s=999., duration_s=1., heat_w=1.)]
    _, frames = run(project, 60.)
    assert any(d.code == 'SCHEDULE_EVENT_AFTER_RUN' for d in frames[0].diagnostics)


def prototype_room():
    """The prototype export the Studio sends for the case (parameters in display units, events canonical)."""
    project = room_example()
    definitions, instances = {m.id: m for m in project.modules}, {i.id: i for i in project.instances}

    def display(iid, values):
        specs = {p.id: p for p in definitions[instances[iid].module_id].parameters}
        return {k: specs[k].unit.from_canonical(v) for k, v in values.items()}
    nodes = [{'id': i.id, 'moduleId': i.module_id, 'name': i.name,
              'params': display(i.id, {p.id: i.parameters.get(p.id, p.default) for p in definitions[i.module_id].parameters})}
             for i in project.instances]
    scenarios = [{'id': s.id, 'name': s.name, 'overrides': {iid: display(iid, v) for iid, v in s.overrides.items()},
                  'events': [e.model_dump(mode='json', exclude_none=True) for e in s.events] if s.events is not None else None}
                 for s in project.scenarios]
    return {'format': 'fluidnet-studio-prototype', 'schema': 1, 'activeProject': project.id,
            'modules': [{'id': m.id, 'kind': m.id, 'runtime': 'builtin', 'name': m.name, 'version': 1,
                         'ports': [p.model_dump(mode='json') for p in m.ports], 'channels': []} for m in project.modules],
            'models': [], 'charts': {'extra': []},
            'projects': [{'id': project.id, 'name': project.name, 'fluid': 'HEOS::R290', 'solver': {'dt': 30},
                          'controlScripts': [s.model_dump(mode='json') for s in project.control_scripts], 'scenarios': scenarios,
                          'pages': [{'id': 'main', 'nodes': nodes, 'edges': [[c.id, c.source.instance_id, c.source.port_id,
                                     c.target.instance_id, c.target.port_id] for c in project.connections]}]}]}


def test_prototype_normalization_keeps_parameters_events_and_scenarios():
    data = prototype_room()
    data['projects'][0]['events'] = [{'id': 'door-x', 'type': 'door_heat', 'time_s': 60., 'duration_s': 60., 'heat_w': 1000.}]
    project = normalize_prototype_export(data)
    assert project.events[0].heat_w == 1000. and project.fluid.fluid == 'HEOS::R290'
    assert [s.events for s in project.scenarios] == [s.events for s in room_example().scenarios]
    expected, actual = compile_project(room_example()).parameters, compile_project(project).parameters
    for iid, values in expected.items():
        for key, value in values.items():
            assert actual[iid][key] == pytest.approx(value, rel=1e-12, abs=1e-9), (iid, key)
    s07 = apply_scenario(project, 'A-S07')
    assert next(i for i in s07.instances if i.id == 'CU1').parameters['rated_cooling_power_w'] == pytest.approx(2000.)


def test_api_background_run_reports_comparison_and_restart(tmp_path):
    root = tmp_path / 'data'
    keys = [k for k, _ in series_keys([('CU1', 'AC1', 'ROOM1')])]
    with TestClient(create_app(data_root=root)) as client:
        assert client.get('/api/v1/health').json()['capabilities']['cold_store_cycle']
        project = client.get('/api/v1/examples/cold-storage-room').json()
        body = {'project': project, 'mode': 'dynamic', 'duration_s': 3600., 'dt_s': 30., 'history': 'trend', 'trend_variables': keys}
        a = client.post('/api/v1/runs?background=true', json=body | {'scenario_id': 'A-S05-onoff', 'start_paused': True}).json()['run_id']
        wait(client, a, lambda r: r['status'] == 'paused')
        client.post(f'/api/v1/runs/{a}/command', json={'action': 'step'}).raise_for_status()
        wait(client, a, lambda r: r['status'] == 'paused' and r['frame']['time_s'] == 30.)
        client.post(f'/api/v1/runs/{a}/command', json={'action': 'resume'}).raise_for_status()
        record = wait(client, a, lambda r: r['status'] == 'completed', timeout=180)
        sync = client.post('/api/v1/runs', json=body | {'scenario_id': 'A-S05-onoff'}).json()
        # Pausing and single-stepping do not change the physics or the cumulative counters.
        assert sync['frame']['variables'] == record['frame']['variables']
        b = client.post('/api/v1/runs?background=true', json=body | {'scenario_id': 'A-S05-variable'}).json()['run_id']
        wait(client, b, lambda r: r['status'] == 'completed', timeout=180)
        report = client.get(f'/api/v1/runs/{a}/report.html')
        assert report.status_code == 200 and report.headers['content-type'].startswith('text/html')
        assert '冷库运行报告' in report.text and 'A-S05' in report.text and 'REFRIGERATION_ENVELOPE' in report.text
        csv_text = client.get(f'/api/v1/runs/{a}/report.csv').text
        lines = csv_text.lstrip(chr(0xFEFF)).splitlines()
        assert len(lines) == 1 + 121 and lines[0].startswith('time_s,ROOM1.state.temperature_k [K]')
        assert all(cell != '' for cell in lines[-1].split(',')[:3])
        fair = client.get(f'/api/v1/runs/compare/report.html?a={a}&b={b}')
        assert fair.status_code == 200 and '公平性' in fair.text and '不一致' not in fair.text
        other = client.post('/api/v1/runs', json=body | {'scenario_id': 'A-S02'}).json()['run_id']
        unfair = client.get(f'/api/v1/runs/compare/report.html?a={a}&b={other}').text
        assert '不一致' in unfair and '不计算节电率' in unfair
        ideal = client.post('/api/v1/runs', json={'project': client.get('/api/v1/examples/cold-storage').json(), 'mode': 'dynamic',
                                                  'duration_s': 60., 'dt_s': 30.}).json()['run_id']
        assert client.get(f'/api/v1/runs/{ideal}/report.html').json()['detail']['code'] == 'REPORT_UNSUPPORTED'
    with TestClient(create_app(data_root=root)) as client:
        assert client.get(f'/api/v1/runs/{a}/report.csv').text == csv_text
        replay = client.post('/api/v1/runs', json=body | {'scenario_id': 'A-S05-onoff'}).json()
        assert replay['frame']['variables'] == record['frame']['variables']
