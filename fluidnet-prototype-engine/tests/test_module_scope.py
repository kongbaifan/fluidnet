"""Applicability, immutable validation evidence and cross-schema compatibility."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from fn_engine.models import ModuleDefinition, ModuleSaveRequest, ModuleValidationEvidence
from fn_engine.module_templates import create_template
from fn_engine.packages import ModuleStore
from fn_engine.runtime import module_definition_hash
from fn_engine.solver import solve_steady
from test_module_execution_network import network_for

ROOT = Path(__file__).resolve().parents[1]


def scoped(kind='hard'):
    payload = create_template('resistance', 'scope_probe', 'Scope probe').model_dump(mode='json')
    payload.update(schema_version=3, applicability={'limits':[{'id':'in0', 'target':'port',
        'quantity':'pressure_pa', 'maximum':200000, 'kind':kind}]})
    return ModuleDefinition.model_validate(payload)


def test_hard_limit_rejects_final_solution_and_envelope_warns():
    with pytest.raises(ValueError, match='超出 hard 范围'):
        solve_steady(network_for(scoped()))
    frame = solve_steady(network_for(scoped('envelope')))
    assert frame.valid
    assert any(d.code == 'MODULE_SCOPE_LIMIT' and d.severity == 'warning' for d in frame.diagnostics)


def test_unsupported_fluid_is_rejected_before_worker_start():
    payload = scoped().model_dump(mode='json')
    payload['applicability']['fluids'] = ['Air']
    with pytest.raises(ValueError, match='不支持工质 Water'):
        network_for(ModuleDefinition.model_validate(payload))


def test_schema3_reload_canonical_numbers_and_old_schema_bytes_remain_frozen():
    module = scoped()
    restored = ModuleDefinition.model_validate_json(module.model_dump_json())
    assert module_definition_hash(module) == module_definition_hash(restored)
    for filename in ['v1-snapshots.json', 'v2-snapshots.json']:
        frozen = json.loads((ROOT / 'tests/fixtures/module-system' / filename).read_text(encoding='utf-8'))
        for sample in frozen['modules']:
            assert module_definition_hash(ModuleDefinition.model_validate(sample['definition'])) == sample['definition_hash']


def test_added_evidence_never_rewrites_release_or_definition(tmp_path):
    store = ModuleStore(ROOT / 'modules', tmp_path)
    release = store.save(ModuleSaveRequest(module=create_template('resistance', 'evidence_probe', 'Evidence'), expected_latest_version=0))
    receipt = tmp_path / 'module-evidence_probe/v1/release.json'
    original = receipt.read_bytes()
    evidence = ModuleValidationEvidence(level='external', status='pending', source='manufacturer data not yet supplied',
        content_hash=release.package.content_hash, definition_hash=release.package.definition_hash,
        input_hash='0'*64, engine_version='0.5.0', sdk_version='0.4.0')
    updated = store.add_evidence('evidence_probe', 1, evidence)
    assert len(updated.validation_evidence) == 2
    assert receipt.read_bytes() == original
    assert updated.package == release.package
    bad = deepcopy(evidence)
    bad.definition_hash = '0'*64
    with pytest.raises(ValueError, match='双哈希'): store.add_evidence('evidence_probe', 1, bad)
