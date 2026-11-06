"""Open intercooling is a three-vessel network, with independently audited stream balances."""
import json
from pathlib import Path

import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import Project
from fn_engine.refrigeration.station import StationSession, evaluate
from fn_engine.refrigeration.two_stage_example import modular_two_stage_example, two_stage_recipe
from fn_engine.solver import solve_dynamic

ROOT = Path(__file__).resolve().parents[1] / 'examples/refrigeration-modular'
VESSELS = ('Low', 'Intermediate', 'High')


def stream_balances(result):
    """Write each vessel's mass and enthalpy balance without using the station's derivatives."""
    d, v = result['devices'], result['vessels']
    ml, mh = (d[key]['mass_flow_kg_s'] for key in ('Compressor', 'HighCompressor'))
    vl, vh = (d[key]['mass_flow_kg_s'] for key in ('Valve', 'HighValve'))
    hgl, hgm = v['Low'].vapor_enthalpy_j_kg, v['Intermediate'].vapor_enthalpy_j_kg
    hfm, hfh = v['Intermediate'].liquid_enthalpy_j_kg, v['High'].liquid_enthalpy_j_kg
    wl, wh = (d[key]['shaft_power_w'] for key in ('Compressor', 'HighCompressor'))
    cooling = d['Cooler']['refrigerant_heat_w'] + d['Pump']['heat_to_fluid_w']
    mass = {'Low': vl - ml, 'Intermediate': ml + vh - mh - vl, 'High': mh - vh}
    energy = {'Low': vl * hfm - ml * hgl + cooling,
              'Intermediate': ml * hgl + wl + vh * hfh - mh * hgm - vl * hfm,
              'High': mh * hgm + wh - vh * hfh - d['Condenser']['heat_rejection_w']}
    return mass, energy


def current_result(session):
    return evaluate(session.network, session.services, session.masses, session.energies, session.temperatures)


def test_recipe_rebuilds_three_pressure_levels_using_public_modules():
    recipe = json.loads((ROOT / 'two-stage.recipe.json').read_text(encoding='utf-8'))
    assert recipe == two_stage_recipe()
    original = modular_two_stage_example()
    assert Project.model_validate_json((ROOT / 'two-stage.project.json').read_text(encoding='utf-8')) == original
    used = {instance['module_id'] for instance in recipe['instances']}
    catalog = catalog_map()
    rebuilt = Project(id='from-empty-two-stage', name=recipe['name'], fluid=recipe['fluid'],
        solver=recipe['solver'], instances=recipe['instances'], connections=recipe['connections'],
        modules=[catalog[key] for key in sorted(used)])
    network = compile_project(rebuilt)
    assert len(rebuilt.instances) == 11 and len(rebuilt.connections) == 13
    assert len(network.vessels) == 3 and len(network.circuit_fluids) == 1
    assert network.vessel('Compressor', 'suction') == 'Low'
    assert network.vessel('Compressor', 'discharge') == 'Intermediate'
    assert network.vessel('HighCompressor', 'suction') == 'Intermediate'
    assert network.vessel('HighCompressor', 'discharge') == 'High'
    assert network.vessel('HighValve', 'out0') == 'Intermediate'
    assert network.vessel('Valve', 'in0') == 'Intermediate'
    assert not rebuilt.controllers and not rebuilt.control_scripts


def test_design_point_closes_each_vessel_and_requires_different_stage_mass_flows():
    session = StationSession(compile_project(modular_two_stage_example()), 60., 60.)
    try:
        initial = session.initialize()
        result = current_result(session)
        mass, energy = stream_balances(result)
        for vessel in VESSELS:
            assert result['dm'][vessel] == pytest.approx(mass[vessel], abs=1e-12)
            assert result['du'][vessel] == pytest.approx(energy[vessel], abs=1e-8)
            assert abs(mass[vessel]) < 1e-10
            assert abs(energy[vessel]) < 1e-4
        d, v = result['devices'], result['vessels']
        assert v['Low'].pressure_pa < v['Intermediate'].pressure_pa < v['High'].pressure_pa
        expected_ratio = (d['Compressor']['discharge_enthalpy_j_kg'] - v['Intermediate'].liquid_enthalpy_j_kg) / (
            v['Intermediate'].vapor_enthalpy_j_kg - v['High'].liquid_enthalpy_j_kg)
        assert expected_ratio > 1.
        assert d['HighCompressor']['mass_flow_kg_s'] / d['Compressor']['mass_flow_kg_s'] == pytest.approx(
            expected_ratio, rel=1e-8)
        assert d['HighCompressor']['suction_enthalpy_j_kg'] == pytest.approx(v['Intermediate'].vapor_enthalpy_j_kg)
        assert d['Compressor']['discharge_temperature_k'] > v['Intermediate'].temperature_k
        session.advance()
        final = session.snapshot()
        assert final.valid and final.variables['Room.state.temperature_k'] == pytest.approx(255.15, abs=1e-6)
        for vessel in VESSELS:
            assert final.variables[f'{vessel}.state.temperature_k'] == pytest.approx(
                initial.variables[f'{vessel}.state.temperature_k'], abs=1e-6)
        assert abs(final.metrics['mass_residual_kg_circuit0']) < 1e-8
        assert abs(final.metrics['energy_residual_j']) < .05
    finally:
        session.close()


def test_arbitrary_ids_and_order_keep_the_same_two_stage_results():
    original = modular_two_stage_example()
    raw = original.model_dump(mode='json')
    ids = {instance['id']: f'CUSTOM_{index + 37}' for index, instance in enumerate(raw['instances'])}
    for instance in raw['instances']:
        instance['id'] = ids[instance['id']]
    for connection in raw['connections']:
        for endpoint in ('source', 'target'):
            connection[endpoint]['instance_id'] = ids[connection[endpoint]['instance_id']]
    raw['instances'].reverse()
    raw['connections'].reverse()
    raw['id'] = 'arbitrary-two-stage'
    edited = Project.model_validate(raw)
    a = solve_dynamic(compile_project(original), 10., 10.)[-1]
    b = solve_dynamic(compile_project(edited), 10., 10.)[-1]
    for key, value in a.variables.items():
        iid, separator, suffix = key.partition('.')
        if iid in ids:
            other = b.variables[ids[iid] + separator + suffix]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                assert other == pytest.approx(value, rel=1e-8, abs=1e-6), key
            else:
                assert other == value, key


@pytest.mark.parametrize('stopped', ['Compressor', 'HighCompressor'])
def test_stopping_one_stage_changes_stored_mass_and_energy_without_inventing_an_interlock(stopped):
    session = StationSession(compile_project(modular_two_stage_example()), 1., 1.)
    try:
        session.initialize()
        session.set_parameter(stopped, 'running', 0.)
        initial = session.snapshot()
        first = current_result(session)
        assert first['devices'][stopped]['mass_flow_kg_s'] == 0.
        assert first['devices'][stopped]['shaft_power_w'] == 0.
        assert first['dm']['Intermediate'] < 0. if stopped == 'Compressor' else first['dm']['Intermediate'] > 0.
        masses, energies = dict(session.masses), dict(session.energies)
        session.advance()
        final = session.snapshot()
        result = current_result(session)
        mass, energy = stream_balances(result)
        for vessel in VESSELS:
            assert session.masses[vessel] - masses[vessel] == pytest.approx(mass[vessel], abs=1e-7)
            assert session.energies[vessel] - energies[vessel] == pytest.approx(energy[vessel], abs=.03)
        total = lambda frame: sum(frame.variables[f'{iid}.state.internal_energy_j'] for iid in VESSELS) + (
            frame.variables['Room.param.heat_capacity_j_k'] * frame.variables['Room.state.temperature_k'])
        values = final.variables
        boundary = sum(values[f'{iid}.state.electric_energy_j'] * values[f'{iid}.param.motor_efficiency']
                       for iid in ('Compressor', 'HighCompressor'))
        boundary += values['Pump.state.electric_energy_j'] - values['Condenser.state.heat_rejected_j']
        boundary += values['Cooler.state.fan_energy_j'] + values['Room.state.external_energy_j']
        assert total(final) - total(initial) == pytest.approx(boundary, abs=.05)
        assert final.valid and abs(final.metrics['mass_residual_kg_circuit0']) < 1e-8
        assert abs(final.metrics['energy_residual_j']) < .05
        assert final.variables[f'{stopped}.state.electric_energy_j'] == 0.
    finally:
        session.close()
