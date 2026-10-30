"""Full room dynamics, sampled controls, and frozen API reports for the three-loop example."""
import csv
from io import StringIO
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine.air_examples import air_example
from fn_engine.api import create_app
from fn_engine.chiller_examples import ROOM_CONTROL_DURATION_S, ROOM_CONTROL_EXAMPLES, ROOM_CONTROL_STEP_S
from fn_engine.compiler import compile_project
from fn_engine.models import Project
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_dynamic


@pytest.fixture(scope='module')
def trajectories():
    results = {}
    for name in ROOM_CONTROL_EXAMPLES:
        project = air_example(name)
        frames = solve_dynamic(compile_project(project), ROOM_CONTROL_DURATION_S, ROOM_CONTROL_STEP_S)
        results[name] = frames
        print(json.dumps({'case':name, 'temperature_c':frames[-1].variables['Room.state.temperature_k']-273.15,
            'target_c':frames[-1].variables['controller.room-temperature.setpoint']-273.15,
            'valve':frames[-1].variables['controller.room-temperature.output'],
            'energy_kwh':frames[-1].variables['Chiller.state.electric_energy_j']/3600000,
            'minimum_water_flow_kg_s':min(f.variables['Coil.in1.mass_flow_kg_s'] for f in frames)},ensure_ascii=False))
    return results


def test_cooldown_and_disturbances_reach_their_targets_with_real_room_storage(trajectories):
    for name, frames in trajectories.items():
        assert len(frames) == 81 and all(f.valid for f in frames)
        assert frames[0].variables['Room.state.temperature_k'] == pytest.approx(303.15)
        target = frames[-1].variables['controller.room-temperature.setpoint']
        # A 0.25 K band is the declared 40-minute teaching-case acceptance, not an exact thermostat.
        assert frames[-1].variables['Room.state.temperature_k'] == pytest.approx(target, abs=.25), name
        assert max(abs(f.variables['Room.state.temperature_k']-target) for f in frames[-6:]) < .3
        assert min(f.variables['Room.state.temperature_k'] for f in frames) > target-.4
        assert frames[-1].variables['Room.state.stored_energy_j'] != frames[0].variables['Room.state.stored_energy_j']


def test_controls_use_accepted_samples_and_preserve_both_closed_water_loops(trajectories):
    for frames in trajectories.values():
        energy = 0.
        for previous, frame in zip(frames, frames[1:]):
            v = frame.variables
            assert .02 <= v['controller.room-temperature.output'] <= 1.
            assert v['Coil.in1.mass_flow_kg_s'] > .03
            assert v['Chiller.param.running'] == 1.
            assert abs(v['ChilledRef.out0.mass_flow_kg_s']) < 1e-10
            assert abs(v['CoolingRef.out0.mass_flow_kg_s']) < 1e-10
            assert v['Chiller.cooling_power_w'] == pytest.approx(v['Coil.water_heat_w']+v['ChilledPump.shaft_power_w'],abs=.04)
            assert v['Tower.heat_rejected_w'] == pytest.approx(v['Chiller.condenser_heat_w']+v['CoolingPump.shaft_power_w'],abs=.04)
            energy += v['Chiller.electric_power_w']*(frame.time_s-previous.time_s)
        assert frames[-1].variables['Chiller.state.electric_energy_j'] == pytest.approx(energy,rel=1e-9)


def test_step_scripts_change_the_physical_load_and_the_pid_target(trajectories):
    load = trajectories['room-control-load-step']
    setpoint = trajectories['room-control-setpoint-step']
    for frames, key, before, after in ((load,'Room.sensible_load_w',5000.,8000.),
        (setpoint,'controller.room-temperature.setpoint',299.15,298.15)):
        assert next(f for f in frames if f.time_s == 600).variables[key] == before
        assert next(f for f in frames if f.time_s == 630).variables[key] == after
        assert frames[-1].variables['script.room-scenario.state.applied'] is True
    assert load[-1].variables['controller.room-temperature.output'] > trajectories['room-temperature-control'][-1].variables['controller.room-temperature.output']
    assert setpoint[-1].variables['Room.state.temperature_k'] < trajectories['room-temperature-control'][-1].variables['Room.state.temperature_k']-.8


@pytest.mark.parametrize('opening', [.02, 1.])
def test_declared_valve_limits_remain_solvable_without_water_storage(opening):
    project = air_example('room-temperature-control')
    project.controllers[0].mode = 'manual'
    project.controllers[0].manual_output = opening
    next(i for i in project.instances if i.id=='WaterValve').parameters['opening_ratio'] = opening
    frames = solve_dynamic(compile_project(project),60.,30.)
    assert all(f.valid and f.variables['Coil.in1.mass_flow_kg_s'] > .03 for f in frames)


def test_api_frozen_setpoint_reports_and_restart_use_the_saved_controller(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        project = client.get('/api/v1/examples/room-temperature-control').json()
        assert len(project['controllers']) == 1
        created = client.post('/api/v1/runs',json={'project':project,'mode':'dynamic','duration_s':60.,'dt_s':30.})
        assert created.status_code == 201, created.text
        assert created.json()['status'] == 'completed', created.text
        rid = created.json()['run_id']
        record = client.get('/api/v1/runs/'+rid).json()
        assert record['frame']['variables']['Chiller.out0.temperature_k'] > 273.15
        assert record['frame']['variables']['controller.room-temperature.mode'] == 'auto'
        catalog = {v['key']:v for v in record['air_metadata']['variable_catalog']}
        assert catalog['controller.room-temperature.setpoint']['unit']['display_unit'] == '°C'
        rows = list(csv.DictReader(StringIO(client.get(f'/api/v1/runs/{rid}/report.csv').content.decode('utf-8-sig'))))
        row = next(row for row in rows if row['变量键']=='controller.room-temperature.setpoint' and float(row['时间(s)'])==60)
        assert float(row['规范数值']) == pytest.approx(299.15)
        assert float(row['显示数值']) == pytest.approx(26.)
        assert 'controller.room-temperature.output' in client.get(f'/api/v1/runs/{rid}/report.html').text
        # Changing a separate project object cannot relabel or overwrite the historical target.
        project['controllers'][0]['setpoint'] = 297.15
    with TestClient(create_app(data_root=tmp_path)) as client:
        old = client.get('/api/v1/runs/'+rid).json()
        assert old['request']['project']['controllers'][0]['setpoint'] == 299.15
        assert old['air_metadata'] == record['air_metadata']


def test_live_target_and_manual_control_use_real_session_bindings():
    session = SimulationSession(compile_project(air_example('room-temperature-control')),90.,30.)
    try:
        session.initialize()
        session.advance()
        session.update_controller('room-temperature','setpoint',298.15)
        changed = session.advance()
        assert changed.variables['controller.room-temperature.setpoint'] == 298.15
        session.update_controller('room-temperature','mode','manual')
        session.update_controller('room-temperature','manual_output',.2)
        manual = session.advance()
        assert manual.variables['controller.room-temperature.output'] == .2
    finally:
        session.close()


def test_insufficient_capacity_reports_full_load_and_actual_temperature():
    project = air_example('room-temperature-control')
    for instance in project.instances:
        if instance.id == 'Room':
            instance.parameters.update(initial_temperature_k=299.15, sensible_load_w=15000.)
        elif instance.id == 'Chiller':
            instance.parameters['rated_cooling_power_w'] = 8000.
        elif instance.id == 'WaterValve':
            instance.parameters['opening_ratio'] = 1.
    project.controllers[0].mode = 'manual'
    project.controllers[0].manual_output = 1.
    frames = solve_dynamic(compile_project(project),120.,30.)
    v = frames[-1].variables
    assert v['Chiller.capacity_limited'] is True
    assert v['Chiller.load_ratio'] == pytest.approx(1.)
    assert v['Chiller.out0.temperature_k'] > v['Chiller.param.chilled_water_setpoint_k']
    assert v['Room.state.temperature_k'] > v['controller.room-temperature.setpoint']+.3


def test_portable_projects_preserve_control_sources_and_compile_without_local_module_paths():
    root = Path(__file__).resolve().parents[1]/'examples/room-control'
    for name in ROOM_CONTROL_EXAMPLES:
        project = Project.model_validate_json((root/(name+'.project.json')).read_text(encoding='utf-8'))
        reference = air_example(name)
        assert project.controllers == reference.controllers
        assert project.control_scripts == reference.control_scripts
        assert project.scenarios == reference.scenarios
        assert all(module.package_path is None for module in project.modules)
        assert project.selected_variables == []
        compile_project(project)
