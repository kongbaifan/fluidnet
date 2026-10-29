"""MOD-B2: frozen v1 bytes/hashes, not expectations computed by the implementation under test."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from fn_engine.compiler import compile_project
from fn_engine.models import ModuleDefinition, Project
from fn_engine.packages import load_module_package
from fn_engine.runtime import module_content_hash, module_definition_hash

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = json.loads((ROOT / 'tests/fixtures/module-system/v1-snapshots.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('sample', SNAPSHOTS['modules'], ids=lambda row: row['id'])
def test_frozen_v1_module_load_export_reload_preserves_original_hashes(sample):
    module = ModuleDefinition.model_validate(sample['definition'])
    for _ in range(2):
        assert module_content_hash(module) == sample['content_hash']
        assert module_definition_hash(module) == sample['definition_hash']
        module = ModuleDefinition.model_validate_json(module.model_dump_json())
    assert module.source == sample['definition']['source']


@pytest.mark.parametrize('sample', SNAPSHOTS['modules'], ids=lambda row: row['id'])
def test_seed_packages_still_match_frozen_v1_versions(sample):
    directory = 'check_valve_v2' if sample['id'] == 'check_valve' and sample['definition']['version'] == 2 else sample['id']
    current = load_module_package(ROOT / 'modules' / directory / 'history' / 'v1' if directory == 'fan' else ROOT / 'modules' / directory)
    assert module_content_hash(current) == sample['content_hash']
    assert module_definition_hash(current) == sample['definition_hash']


@pytest.mark.parametrize('sample', SNAPSHOTS['projects'], ids=lambda row: row['id'])
def test_saved_v1_projects_keep_source_bindings_after_export_reload(sample):
    original = Project.model_validate(sample['project'])
    restored = Project.model_validate_json(original.model_dump_json())
    compile_project(restored)
    for before, after in zip(original.modules, restored.modules, strict=True):
        assert before.source == after.source
        assert module_definition_hash(after) == module_definition_hash(before)
        if before.runtime == 'python':
            assert module_content_hash(before) == module_content_hash(after)
    assert [i.package for i in original.instances] == [i.package for i in restored.instances]


def test_v1_hash_ignores_locations_and_hash_fields_but_detects_contract_or_source_changes():
    sample = next(row for row in SNAPSHOTS['modules'] if row['id'] == 'programmable_valve')
    original = ModuleDefinition.model_validate(sample['definition'])
    moved = original.model_copy(deep=True, update={'package_path': 'another-location',
                                                 'content_hash': '0' * 64, 'definition_hash': '1' * 64})
    assert module_definition_hash(moved) == sample['definition_hash']
    changed = original.model_copy(deep=True)
    changed.parameters[0].default = .4
    assert module_definition_hash(changed) != sample['definition_hash']
    changed.source['runtime'] += '\n# changed source\n'
    assert module_content_hash(changed) != sample['content_hash']


def test_v1_missing_defaults_and_browser_integer_roundtrip_preserve_hash():
    sample = next(row for row in SNAPSHOTS['modules'] if row['id'] == 'programmable_valve')
    payload = deepcopy(sample['definition'])
    for field in ('schema_version', 'source_format', 'state_model', 'thermal_model', 'bank_names'):
        payload.pop(field)
    payload['parameters'][1]['default'] = int(payload['parameters'][1]['default'])
    module = ModuleDefinition.model_validate(payload)
    assert module_definition_hash(module) == sample['definition_hash']


def test_v1_rejects_nonfinite_contract_numbers():
    payload = deepcopy(SNAPSHOTS['modules'][0]['definition'])
    payload['parameters'][0]['default'] = float('nan')
    with pytest.raises(ValueError):
        module_definition_hash(ModuleDefinition.model_validate(payload))
