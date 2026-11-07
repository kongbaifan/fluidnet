"""Device contracts compose without a fixed station-case identity or hidden connections."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Project
from fn_engine.refrigeration.modular_examples import assembly_recipe, modular_cascade_example, modular_room_example
from fn_engine.solver import solve_dynamic

ROOT = Path(__file__).resolve().parents[1]/'examples/refrigeration-modular'


def run(project, duration=120.):
    return solve_dynamic(compile_project(project), duration, 60.)


@pytest.mark.parametrize('name,rooms,compressors', [('single-room', 1, 1), ('two-room', 2, 2)])
def test_recipe_rebuilds_from_catalog_without_importing_a_case(name, rooms, compressors):
    recipe = json.loads((ROOT/f'{name}.recipe.json').read_text(encoding='utf-8'))
    assert recipe == assembly_recipe(rooms, compressors)
    expected = modular_room_example(rooms, compressors)
    assert Project.model_validate_json((ROOT/f'{name}.project.json').read_text(encoding='utf-8')) == expected
    catalog = catalog_map()
    used = {i['module_id'] for i in recipe['instances']}
    rebuilt = Project(id='from-empty-canvas', name='逐个模块组装', fluid=recipe['fluid'], solver=recipe['solver'],
        instances=recipe['instances'], connections=recipe['connections'], modules=[catalog[k] for k in sorted(used)])
    network = compile_project(rebuilt)
    assert len(network.room_coolers) == rooms and len(network.vessels) == 2
    assert network.execution_domain == 'refrigeration'
    frames = run(rebuilt, recipe['duration_s'])
    assert all(frame.valid for frame in frames)
    for room in network.room_coolers:
        assert frames[-1].variables[f'{room}.state.temperature_k'] == pytest.approx(255.15, abs=1e-6)
    assert abs(frames[-1].metrics['mass_residual_kg_circuit0']) < 1e-8
    assert abs(frames[-1].metrics['energy_residual_j']) < .05


def renamed(project, prefix):
    raw = project.model_dump(mode='json')
    ids = {i['id']:f'{prefix}_{n+11}' for n,i in enumerate(raw['instances'])}
    for instance in raw['instances']:
        instance['id'] = ids[instance['id']]
    for connection in raw['connections']:
        connection['id'] = prefix+'_'+connection['id']
        for end in ('source', 'target'):
            connection[end]['instance_id'] = ids[connection[end]['instance_id']]
    for circuit in raw['circuit_fluids']:
        circuit['anchor']['instance_id'] = ids[circuit['anchor']['instance_id']]
    raw['id'] = prefix
    return Project.model_validate(raw), ids


def test_arbitrary_ids_and_instance_order_do_not_change_results():
    original = modular_room_example(2, 2)
    edited, ids = renamed(original, 'CUSTOM')
    edited.instances.reverse()
    edited.connections.reverse()
    a, b = run(original)[-1], run(edited)[-1]
    for key, value in a.variables.items():
        iid, separator, rest = key.partition('.')
        if iid in ids:
            other = b.variables[ids[iid]+separator+rest]
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                assert other == pytest.approx(value, rel=1e-7, abs=1e-6), key
            else:
                assert other == value, key


@pytest.mark.parametrize('rooms,compressors', [(1, 2), (2, 1)])
def test_rooms_and_parallel_compressors_are_independently_composable(rooms, compressors):
    project = modular_room_example(rooms, compressors)
    network = compile_project(project)
    assert len(network.room_coolers) == rooms
    assert sum(kind == 'refrigerant_compressor' for kind in network.kinds.values()) == compressors
    final = run(project, 60.)[-1]
    assert final.valid and abs(final.metrics['energy_residual_j']) < .05
    for room in network.room_coolers:
        assert final.variables[room+'.state.temperature_k'] == pytest.approx(255.15, abs=1e-6)


def test_copied_independent_loops_preserve_their_own_charge_and_room():
    first, first_ids = renamed(modular_room_example(), 'A')
    second, second_ids = renamed(modular_room_example(), 'B')
    copied = first.model_copy(deep=True)
    copied.instances.extend(second.instances)
    copied.connections.extend(second.connections)
    network = compile_project(copied)
    assert len(network.circuit_fluids) == 2 and len(network.vessels) == 4
    assert network.room_coolers[first_ids['Room']] == first_ids['Cooler']
    assert network.room_coolers[second_ids['Room']] == second_ids['Cooler']
    frames = run(copied)
    for index in range(2):
        assert abs(frames[-1].metrics[f'mass_residual_kg_circuit{index}']) < 1e-8
    assert frames[-1].variables[f'{first_ids["Room"]}.state.temperature_k'] == pytest.approx(
        frames[-1].variables[f'{second_ids["Room"]}.state.temperature_k'], abs=1e-8)


def test_device_response_and_energy_ledger_are_physical():
    project = modular_room_example(2, 2)
    next(i for i in project.instances if i.id == 'Room-1').parameters['heat_input_w'] += 1000.
    frames = run(project, 300.)
    first, last = frames[0].variables, frames[-1].variables
    assert last['Room-1.state.temperature_k'] > first['Room-1.state.temperature_k']
    assert last['Room-1.state.temperature_k'] > last['Room-2.state.temperature_k']
    assert last['Cooler-1.supply_mass_flow_kg_s'] == pytest.approx(last['Pump.mass_flow_kg_s']/2.)
    assert last['Low.state.pressure_pa'] != pytest.approx(first['Low.state.pressure_pa'], abs=.1)
    stored = lambda v: sum(v[f'{iid}.state.internal_energy_j'] for iid in ('Low','High')) + sum(
        v[f'Room-{i}.param.heat_capacity_j_k']*v[f'Room-{i}.state.temperature_k'] for i in (1,2))
    boundary = sum(last[f'Compressor-{i}.state.electric_energy_j']*last[f'Compressor-{i}.param.motor_efficiency'] for i in (1,2))
    boundary += last['Pump.state.electric_energy_j']-last['Condenser.state.heat_rejected_j']
    boundary += sum(last[f'Cooler-{i}.state.fan_energy_j']+last[f'Room-{i}.state.external_energy_j'] for i in (1,2))
    assert stored(last)-stored(first) == pytest.approx(boundary, abs=.05)


def test_invalid_thermal_device_pair_is_a_compilation_diagnostic():
    project = modular_room_example(2, 1)
    links = [c for c in project.connections if c.source.port_id == 'heat']
    project.connections.remove(links[1])
    links[0].target.instance_id = 'Cooler-2'
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code == 'REFRIGERATION_THERMAL_CONNECTION'


def test_optional_port_edit_cannot_leave_a_room_without_a_cooler():
    project = modular_room_example()
    project.connections = [c for c in project.connections if c.source.port_id != 'heat']
    for module in project.modules:
        for port in module.ports:
            if port.id == 'heat':
                port.required = False
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code == 'REFRIGERATION_THERMAL_CONNECTION_MISSING'


def test_modular_api_run_and_frozen_report(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.get('/api/v1/examples/refrigeration-modular-room')
        assert response.status_code == 200
        project, ids = renamed(Project.model_validate(response.json()), 'UI')
        created = client.post('/api/v1/runs', json={'project':project.model_dump(mode='json'),
            'mode':'dynamic','duration_s':60.,'dt_s':60.})
        assert created.status_code == 201 and created.json()['status'] == 'completed', created.text
        rid = created.json()['run_id']
        report = client.get(f'/api/v1/runs/{rid}/report.html')
        assert report.status_code == 200 and ids['Room'] in report.text
        record = client.get(f'/api/v1/runs/{rid}').json()
        assert record['frame']['variables'][ids['Room']+'.state.temperature_k'] == pytest.approx(255.15, abs=1e-6)


def test_cascade_recipe_builds_two_conservative_circuits_from_public_modules():
    recipe = json.loads((ROOT/'cascade.recipe.json').read_text(encoding='utf-8'))
    assert recipe == assembly_recipe(cascade=True)
    canonical = Project.model_validate_json((ROOT/'cascade.project.json').read_text(encoding='utf-8'))
    assert canonical == modular_cascade_example()
    catalog = catalog_map()
    used = {i['module_id'] for i in recipe['instances']}
    project = Project(id='canvas-cascade', name='独立模块搭建复叠', fluid=recipe['fluid'],
        circuit_fluids=recipe['circuit_fluids'], solver=recipe['solver'], instances=recipe['instances'],
        connections=recipe['connections'], modules=[catalog[key] for key in sorted(used)])
    network = compile_project(project)
    assert len(project.instances) == 10 and len(project.connections) == 13
    assert [fluid.fluid for fluid in network.circuit_fluids] == ['Ammonia', 'CarbonDioxide']
    assert network.vessel('Cascade', 'evap_in') == 'Low'
    assert network.vessel('Cascade', 'cond_in') == 'Secondary'
    frames = run(project, 600.)
    first, last = frames[0].variables, frames[-1].variables
    assert all(frame.valid for frame in frames)
    assert last['Room.state.temperature_k'] == pytest.approx(255.15, abs=1e-6)
    assert last['Low.state.mass_kg']+last['High.state.mass_kg'] == pytest.approx(
        first['Low.state.mass_kg']+first['High.state.mass_kg'], abs=1e-8)
    assert last['Secondary.state.mass_kg'] == pytest.approx(first['Secondary.state.mass_kg'], abs=1e-8)
    assert last['Cascade.heat_w'] == pytest.approx(last['Cooler.refrigerant_heat_w']+last['Pump.electric_power_w'], abs=.001)
    assert last['Condenser.heat_rejection_w'] == pytest.approx(last['Cascade.heat_w']+last['Compressor.shaft_power_w'], abs=.001)
    for index in (0, 1):
        assert abs(frames[-1].metrics[f'mass_residual_kg_circuit{index}']) < 1e-8
    assert abs(frames[-1].metrics['energy_residual_j']) < .05


def test_cascade_arbitrary_ids_keep_circuit_anchors_and_heat_transfer():
    project, ids = renamed(modular_cascade_example(), 'FREE')
    project.instances.reverse()
    project.connections.reverse()
    frame = run(project)[-1]
    assert frame.valid and frame.variables[ids['Room']+'.state.temperature_k'] == pytest.approx(255.15, abs=1e-6)
    assert frame.variables[ids['Cascade']+'.heat_w'] == pytest.approx(5420.236825, abs=.001)
    for index in (0, 1):
        assert abs(frame.metrics[f'mass_residual_kg_circuit{index}']) < 1e-8


def test_cascade_api_returns_the_modular_project(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.get('/api/v1/examples/refrigeration-modular-cascade')
        assert response.status_code == 200
        project = Project.model_validate(response.json())
        assert project == modular_cascade_example()
        assert not project.controllers and not project.control_scripts
        assert compile_project(project).execution_domain == 'refrigeration'
