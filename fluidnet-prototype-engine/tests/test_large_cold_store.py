"""The warehouse is ordinary editable topology, with independently checked inventories."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import apply_scenario, create_app
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.model_types.domain import Project
from fn_engine.refrigeration.large_cold_store_example import ROOMS, assembly_recipe, build_large_cold_store
from fn_engine.solver import solve_dynamic

ROOT = Path(__file__).resolve().parents[1]


def test_saved_project_and_recipe_rebuild_without_case_specific_dispatch():
    project, design = build_large_cold_store()
    saved = Project.model_validate_json((ROOT / 'examples/large-cold-store/six-room.project.json').read_text(encoding='utf-8'))
    assert saved == project
    recipe = assembly_recipe()
    assert json.loads((ROOT / 'examples/large-cold-store/six-room.recipe.json').read_text(encoding='utf-8')) == recipe
    catalog = catalog_map()
    rebuilt = Project(id='customer-warehouse', name=recipe['name'], fluid=recipe['fluid'], solver=recipe['solver'],
        modules=[catalog[key] for key in sorted({node['module_id'] for node in recipe['instances']})],
        instances=recipe['instances'], connections=recipe['connections'])
    network = compile_project(rebuilt)
    assert network.execution_domain == 'refrigeration'
    assert len(rebuilt.instances) == 51 and len(rebuilt.connections) == 72
    assert len({node.page_id for node in rebuilt.instances}) == 4
    assert len(network.vessels) == 3 and len(network.room_cooler_groups) == 6
    assert all(len(coolers) == 2 for coolers in network.room_cooler_groups.values())
    assert design['net_room_load_w'] == 1300000 and design['total_volume_m3'] == 75600
    assert network.vessel('LT_K1', 'discharge') == 'IP'
    assert network.vessel('HT_K1', 'suction') == 'IP'
    assert network.vessel('C01_AC1', 'in0') == 'IP'
    assert network.vessel('F01_AC1', 'in0') == 'LP'
    assert not project.control_scripts and not project.controllers


@pytest.mark.parametrize('scenario', ['baseline', 'f01-extra-load', 'f01-cooler-off'])
def test_ten_minute_run_closes_the_external_mass_and_energy_ledger(scenario):
    project, _ = build_large_cold_store()
    selected = apply_scenario(project, scenario)
    frames = solve_dynamic(compile_project(selected), 600., 10.)
    assert len(frames) == 61 and frames[-1].time_s == 600.
    assert all(frame.valid and not any(d.severity == 'error' for d in frame.diagnostics) for frame in frames)
    first, last = frames[0].variables, frames[-1].variables
    vessels = ('HP', 'IP', 'LP')
    inventory = lambda v: sum(v[iid + '.state.internal_energy_j'] for iid in vessels) + sum(
        v[room[0] + '.param.heat_capacity_j_k'] * v[room[0] + '.state.temperature_k'] for room in ROOMS)
    boundary = sum(last[iid + '.state.electric_energy_j'] * last[iid + '.param.motor_efficiency']
                   for iid in ('LT_K1', 'LT_K2', 'HT_K1', 'HT_K2'))
    boundary += sum(last[iid + '.state.electric_energy_j'] for iid in ('LT_PUMP', 'MT_PUMP'))
    boundary += sum(last[room[0] + f'_AC{index}.state.fan_energy_j'] for room in ROOMS for index in (1, 2))
    boundary += sum(last[room[0] + '.state.external_energy_j'] for room in ROOMS)
    boundary -= last['COND.state.heat_rejected_j']
    assert inventory(last) - inventory(first) == pytest.approx(boundary, abs=1.)
    assert max(abs(frame.metrics['mass_residual_kg_circuit0']) for frame in frames) < 1e-7
    assert max(abs(frame.metrics['energy_residual_j']) for frame in frames) < 1.
    assert last['LP.state.pressure_pa'] < last['IP.state.pressure_pa'] < last['HP.state.pressure_pa']
    if scenario == 'baseline':
        for room in ROOMS:
            assert last[room[0] + '.state.temperature_k'] == pytest.approx(room[2] + 273.15, abs=1e-4)
        assert sum(last[room[0] + f'_AC{i}.room_cooling_w'] for room in ROOMS for i in (1, 2)) == pytest.approx(1.3e6, abs=.001)
    else:
        assert last['F01.state.temperature_k'] > first['F01.state.temperature_k'] + .05
        assert abs(last['F02.state.temperature_k'] - first['F02.state.temperature_k']) < .02
        if scenario == 'f01-cooler-off':
            assert last['F01_AC1.supply_mass_flow_kg_s'] == 0.
            assert last['F01_AC1.state.fan_energy_j'] == 0.


def test_renaming_instances_and_reordering_devices_preserves_the_solution():
    project, _ = build_large_cold_store()
    raw = project.model_dump(mode='json')
    ids = {node['id']: f'CUSTOM_{index + 27}' for index, node in enumerate(raw['instances'])}
    for node in raw['instances']:
        node['id'] = ids[node['id']]
    for edge in raw['connections']:
        for side in ('source', 'target'):
            edge[side]['instance_id'] = ids[edge[side]['instance_id']]
    for scenario in raw['scenarios']:
        scenario['overrides'] = {ids[key]: value for key, value in scenario['overrides'].items()}
    raw['selected_variables'] = [ids[key.split('.', 1)[0]] + '.' + key.split('.', 1)[1] for key in raw['selected_variables']]
    raw['instances'].reverse(); raw['connections'].reverse()
    original = solve_dynamic(compile_project(project), 10., 10.)[-1]
    changed = solve_dynamic(compile_project(Project.model_validate(raw)), 10., 10.)[-1]
    for key, value in original.variables.items():
        iid, dot, suffix = key.partition('.')
        if iid in ids and isinstance(value, (int, float)) and not isinstance(value, bool):
            assert changed.variables[ids[iid] + dot + suffix] == pytest.approx(value, rel=1e-8, abs=1e-5), key


def test_trend_report_uses_available_samples_and_does_not_invent_room_setpoints(tmp_path):
    from fn_engine.refrigeration.report import station_metrics
    project, _ = build_large_cold_store()
    with TestClient(create_app(data_root=tmp_path / 'data', module_storage_root=tmp_path / 'modules')) as client:
        response = client.post('/api/v1/runs', json={'project': project.model_dump(mode='json'),
            'mode': 'dynamic', 'duration_s': 600., 'dt_s': 10., 'history': 'trend',
            'selected_variables': ['F01.state.temperature_k', 'C02.state.temperature_k', 'LT_K1.state.electric_energy_j'],
            'trend_variables': ['F01.state.temperature_k']})
        assert response.status_code == 201 and response.json()['status'] == 'completed'
        rid = response.json()['run_id']
        rows = client.get(f'/api/v1/runs/{rid}/history').json()['rows']
        assert any('HP.state.level_ratio' not in row['variables'] for row in rows)
        metrics = station_metrics(rows, compile_project(project))
        assert all(room['max_deviation_k'] is None for room in metrics['rooms'].values())
        assert metrics['levels']['HP']['min'] is None
        assert metrics['electric_energy_j'] is None and metrics['mean_electric_power_w'] is None
        report = client.get(f'/api/v1/runs/{rid}/report.html')
        assert report.status_code == 200
        assert 'F01 未配置温控目标' in report.text and 'C02 未配置温控目标' in report.text
        assert '液位范围（已记录采样）' in report.text
        csv = client.get(f'/api/v1/runs/{rid}/report.csv')
        assert csv.status_code == 200 and 'F01.state.temperature_k' in csv.text
