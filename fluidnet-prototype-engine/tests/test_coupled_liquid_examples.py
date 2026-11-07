"""Portable author example and its independently checked valve characteristic."""
import json
import math
from pathlib import Path

import pytest

from fn_engine.compiler import compile_project
from fn_engine.models import Project
from fn_engine.refrigeration.coupling import CoupledStationSession
from fn_engine.refrigeration.liquid_module_examples import coupled_liquid_module_example, VALVE

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('exponent', [1., 2.])
def test_example_valve_matches_independent_kv_relation(exponent):
    project = coupled_liquid_module_example()
    next(instance for instance in project.instances if instance.id == VALVE).parameters['characteristic_exponent'] = exponent
    session = CoupledStationSession(compile_project(project), .1, .1)
    try:
        frame = session.initialize()
        values = frame.variables
        effective_kv = values[f'{VALVE}.param.kv_m3_h'] * values[f'{VALVE}.param.opening_ratio'] ** exponent
        density = values[f'{VALVE}.density_kg_m3']
        drop = values[f'{VALVE}.pressure_drop_pa']
        # Kv is m³/h at 1 bar for reference water. Derive mass flow independently.
        expected = effective_kv / 3600. * math.sqrt(abs(drop) * density * 1000. / 100000.)
        assert values[f'{VALVE}.mass_flow_kg_s'] == pytest.approx(math.copysign(expected, drop), rel=1e-8)
        assert values[f'{VALVE}.effective_opening_ratio'] == .8 ** exponent
        assert abs(frame.metrics['fluid_energy_residual_w']) < 1e-4
    finally:
        session.close()


def test_portable_file_contains_frozen_source_and_roundtrips_without_path():
    source = json.loads((ROOT / 'examples/coupled_liquid_modules/author_loop.json').read_text(encoding='utf-8'))
    assert source == coupled_liquid_module_example().model_dump(mode='json')
    assert source['selected_variables'] == []
    project = Project.model_validate(source)
    valve = next(instance for instance in project.instances if instance.id == VALVE)
    module = next(module for module in project.modules if module.id == valve.module_id)
    assert module.package_path is None
    assert module.source['runtime']
    assert valve.package.content_hash == module.content_hash
    assert valve.package.definition_hash == module.definition_hash
    session = CoupledStationSession(compile_project(project), .1, .1)
    try:
        session.initialize()
        frame = session.advance()
        assert frame.variables[f'{VALVE}.state.commit_count'] == 1
        assert frame.variables[f'{VALVE}.state.transferred_mass_kg'] > 0
    finally:
        session.close()


def test_batch_choices_include_real_host_flow_and_mass_with_canonical_units():
    from fn_engine.batches import observation_choices
    from fn_engine.models import VariableSpec
    project = coupled_liquid_module_example()
    # Even an author label/unit declaration cannot redefine the host's ledger.
    module = next(module for module in project.modules if module.id == 'coupled_liquid_valve')
    module.variables.append(VariableSpec(id='state.transferred_mass_kg', label='misleading author label',
        quantity='temperature', source='state', unit={'quantity': 'temperature', 'canonical_unit': 'K', 'display_unit': 'K'}))
    choices = {variable.key: variable for variable in observation_choices(project)}
    assert choices[f'{VALVE}.mass_flow_kg_s'].unit.canonical_unit == 'kg/s'
    assert choices[f'{VALVE}.pressure_drop_pa'].unit.display_scale == 1000.
    assert choices[f'{VALVE}.state.transferred_mass_kg'].unit.canonical_unit == 'kg'
    assert '平台积分' in choices[f'{VALVE}.state.transferred_mass_kg'].label
    session = CoupledStationSession(compile_project(coupled_liquid_module_example()), .1, .1)
    try:
        session.initialize()
        frame = session.advance()
        for suffix in ('mass_flow_kg_s', 'pressure_drop_pa', 'state.transferred_mass_kg'):
            assert isinstance(frame.variables[f'{VALVE}.{suffix}'], float)
    finally:
        session.close()
    project = coupled_liquid_module_example()
    project.thermal_couplings = []
    assert f'{VALVE}.state.transferred_mass_kg' not in {variable.key for variable in observation_choices(project)}
