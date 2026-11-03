"""Canvas partitioning preserves one network and its physical balances."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from fn_engine.bridge import normalize_prototype_export
from fn_engine.compiler import compile_project
from fn_engine.hvac_examples import hvac_example
from fn_engine.models import Project
from fn_engine.solver import solve_steady

ROOT = Path(__file__).resolve().parents[1]


def test_prototype_cross_page_edges_solve_like_the_single_canvas_network():
    raw = json.loads((ROOT/'tests/fixtures/prototype.json').read_text(encoding='utf-8'))
    raw['activeProject'] = 'water-net'
    baseline = solve_steady(compile_project(normalize_prototype_export(raw)))
    owner = next(project for project in raw['projects'] if project['id'] == 'water-net')
    original = deepcopy(owner['pages'][0])
    owner['pages'] = [dict(original, nodes=[], edges=[]),
        {'id':'terminal1','name':'末端 1','nodes':[],'edges':[]},
        {'id':'terminal2','name':'末端 2','nodes':[],'edges':[]}]
    destination = {}
    for node in original['nodes']:
        index = 1 if node['id'] in ('V1','L1') else 2 if node['id'] in ('V2','L2') else 0
        owner['pages'][index]['nodes'].append(node)
        destination[node['id']] = owner['pages'][index]
    for edge in original['edges']:
        destination[edge[1]]['edges'].append(edge)
    project = normalize_prototype_export(raw)
    assert {node.page_id for node in project.instances} == {'main','terminal1','terminal2'}
    restored = Project.model_validate_json(project.model_dump_json())
    result = solve_steady(compile_project(restored))
    assert baseline.valid and result.valid
    assert result.variables == pytest.approx(baseline.variables, rel=1e-7, abs=1e-6)
    assert result.metrics['mass_residual_kg_s'] < 1e-7


def test_standard_plant_three_canvas_partition_preserves_water_and_heat_balances():
    project = hvac_example('hvac-basic-plant')
    baseline = solve_steady(compile_project(project))
    for node in project.instances:
        node.page_id = 'terminals' if node.id in ('Coil','Coil2','Balance1','Balance2','Header','Collector') \
            else 'plant' if node.id in ('Chiller','ChilledPump','CoolingPump','Tower','ChilledRef','CoolingRef',
                                        'ChilledJoin','CoolingJoin','Strainer','Reducer','Isolation') else 'air'
    result = solve_steady(compile_project(Project.model_validate_json(project.model_dump_json())))
    assert baseline.valid and result.valid
    assert result.variables == pytest.approx(baseline.variables, rel=1e-8, abs=1e-6)
    values = result.variables
    assert values['Header.common.mass_flow_kg_s'] == pytest.approx(
        values['Coil.ch1.mass_flow_kg_s'] + values['Coil2.ch1.mass_flow_kg_s'], abs=1e-7)
    assert values['Chiller.cooling_power_w'] == pytest.approx(
        values['Coil.water_heat_w'] + values['Coil2.water_heat_w'] + values['ChilledPump.shaft_power_w'], abs=.02)
    assert values['Tower.heat_rejected_w'] == pytest.approx(
        values['Chiller.condenser_heat_w'] + values['CoolingPump.shaft_power_w'], abs=.02)
