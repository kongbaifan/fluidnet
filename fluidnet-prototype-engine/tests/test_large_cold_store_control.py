"""Practical room response, capacity limits and independent energy conservation."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import apply_scenario, create_app
from fn_engine.compiler import compile_project
from fn_engine.refrigeration.large_cold_store_control import controlled_large_cold_store
from fn_engine.refrigeration.large_cold_store_example import ROOMS
from fn_engine.solver import solve_dynamic


@pytest.mark.parametrize('scenario', ['baseline', 'load-step', 'cooler-off', 'lower-load'])
def test_controlled_room_responses_and_independent_inventory(scenario):
    project = apply_scenario(controlled_large_cold_store(), scenario)
    frames = solve_dynamic(compile_project(project), 10800., 30.)
    assert all(frame.valid for frame in frames)
    first, last = frames[0].variables, frames[-1].variables
    inventory = lambda v: (sum(v[i + '.state.internal_energy_j'] for i in ('HP', 'IP', 'LP'))
                           + sum(v[r[0] + '.state.temperature_k'] * r[8] for r in ROOMS))
    energy = sum(last[i + '.state.electric_energy_j'] * last[i + '.param.motor_efficiency']
                 for i in ('LT_K1', 'LT_K2', 'HT_K1', 'HT_K2'))
    energy += sum(last[i + '.state.electric_energy_j'] for i in ('LT_PUMP', 'MT_PUMP'))
    energy += sum(last[r[0] + f'_AC{i}.state.fan_energy_j'] for r in ROOMS for i in (1, 2))
    energy += sum(last[r[0] + '.state.external_energy_j'] for r in ROOMS)
    energy -= last['COND.state.heat_rejected_j']
    assert inventory(last) - inventory(first) == pytest.approx(energy, abs=10.)
    assert max(abs(f.metrics['mass_residual_kg_circuit0']) for f in frames) < 1e-7
    assert max(abs(f.metrics['energy_residual_j']) for f in frames) < 10.
    target = 249.15
    if scenario == 'baseline':
        for room in ROOMS:
            assert last[room[0] + '.state.temperature_k'] == pytest.approx(room[2] + 273.15, abs=1e-4)
        assert last['F01_AC2.param.fan_ratio'] == pytest.approx(.65, abs=1e-5)
    elif scenario == 'load-step':
        assert max(f.variables['F01_AC2.param.fan_ratio'] for f in frames) > .95
        assert last['F01.state.temperature_k'] == pytest.approx(target, abs=.03)
        assert last['F01_AC2.param.fan_ratio'] < .65
        assert frames[-1].metrics['events_applied'] == 2
    elif scenario == 'lower-load':
        assert last['F01_AC2.param.fan_ratio'] < .5
        assert last['F01.state.temperature_k'] == pytest.approx(target, abs=.03)
        assert frames[-1].metrics['electric_power_w'] < frames[0].metrics['electric_power_w']
    else:
        assert last['F01_AC1.supply_mass_flow_kg_s'] == 0.
        assert last['F01_AC1.state.fan_energy_j'] == 0.
        assert last['F01_AC2.param.fan_ratio'] == 1.
        assert last['F01.state.temperature_k'] > target + .5


def test_saved_example_and_api_and_report(tmp_path):
    project = controlled_large_cold_store()
    path = Path(__file__).resolve().parents[1] / 'examples/large-cold-store/six-room-controlled.project.json'
    assert json.loads(path.read_text(encoding='utf-8')) == project.model_dump(mode='json')
    assert len({(c.instance_id, c.parameter_id) for c in project.controllers}) == len(project.controllers)
    with TestClient(create_app(data_root=tmp_path / 'data', module_storage_root=tmp_path / 'modules')) as client:
        assert client.get('/api/v1/examples/large-cold-store-controlled').json() == project.model_dump(mode='json')
        result = client.post('/api/v1/runs', json={'project': project.model_dump(mode='json'),
                            'mode': 'dynamic', 'duration_s': 60., 'dt_s': 30.})
        assert result.status_code == 201 and result.json()['status'] == 'completed'
        html = client.get('/api/v1/runs/' + result.json()['run_id'] + '/report.html')
        assert html.status_code == 200
        assert 'F01 最大偏离设定' in html.text and 'F01 未配置温控目标' not in html.text


def test_smaller_steps_preserve_control_response():
    project = apply_scenario(controlled_large_cold_store(), 'load-step')
    coarse = solve_dynamic(compile_project(project), 3600., 30.)[-1]
    project.solver.dynamic_step_s = 15.
    fine = solve_dynamic(compile_project(project), 3600., 30.)[-1]
    assert fine.variables['F01.state.temperature_k'] == pytest.approx(coarse.variables['F01.state.temperature_k'], abs=.01)
