"""Frozen schema parsing/hashes and declarative compatibility, no scientific stack."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fn_engine.models import ModuleCatalogItem, ModuleDefinition, ModuleManifest, Project
from fn_engine._module_schema_v1 import ModuleDefinitionV1
from fn_engine.module_contracts import (
    ModuleCompatibilityError, canonical_contract_bytes, check_module_compatibility, definition_hash,
)

ROOT = Path(__file__).resolve().parents[1]
V1 = json.loads((ROOT / 'tests/fixtures/module-system/v1-snapshots.json').read_text(encoding='utf-8'))
V2 = json.loads((ROOT / 'tests/fixtures/module-system/v2-snapshots.json').read_text(encoding='utf-8'))


def schema2_payload():
    return deepcopy(V2['modules'][1]['definition'])


def test_frozen_schema1_matches_pre_extension_schema_including_nested_defaults():
    expected = json.loads((ROOT / 'tests/fixtures/module-system/module-v1.schema.json').read_text(encoding='utf-8'))
    expected.pop('$schema')
    actual = ModuleDefinitionV1.model_json_schema()
    # The frozen implementation class has its own name; the wire contract is unchanged.
    actual['title'] = expected['title']
    assert actual == expected


@pytest.mark.parametrize('sample', V2['modules'], ids=lambda sample: sample['id'])
def test_schema2_frozen_export_reload_and_canonical_bytes(sample):
    module = ModuleDefinition.model_validate(sample['definition'])
    for _ in range(2):
        check_module_compatibility(module)
        assert canonical_contract_bytes(module).decode() == sample['canonical_json']
        assert definition_hash(module) == sample['definition_hash']
        module = ModuleDefinition.model_validate_json(module.model_dump_json())
    assert module.model_dump(mode='json') == sample['definition']


@pytest.mark.parametrize('sample', V1['modules'], ids=lambda sample: sample['id'])
def test_schema1_export_does_not_gain_sdk_defaults(sample):
    module = ModuleDefinition.model_validate(sample['definition'])
    assert module.sdk is None
    assert 'sdk' not in module.model_dump(mode='json')
    assert definition_hash(module) == sample['definition_hash']
    check_module_compatibility(module)


def test_nested_schema1_defaults_stay_frozen_when_omitted():
    payload = deepcopy(V1['modules'][0]['definition'])
    for port in payload['ports']:
        for key in ['domain', 'direction', 'required', 'circuit']:
            if port[key] == {'domain':'fluid', 'direction':'bidirectional', 'required':True, 'circuit':'fluid'}[key]:
                port.pop(key)
    for parameter in payload['parameters']:
        for key, default in {'value_type':'number', 'unit':None, 'minimum':None, 'maximum':None,
                             'runtime':False, 'writable':True}.items():
            if parameter.get(key) == default:
                parameter.pop(key, None)
        if parameter.get('unit'):
            if parameter['unit']['display_scale'] == 1.0:
                parameter['unit'].pop('display_scale')
            if parameter['unit']['display_offset'] == 0.0:
                parameter['unit'].pop('display_offset')
    module = ModuleDefinition.model_validate(payload)
    assert definition_hash(module) == V1['modules'][0]['definition_hash']


@pytest.mark.parametrize('sdk', [None, {}, {'api_version':'0.2.0'}])
def test_schema1_rejects_explicit_sdk_even_null(sdk):
    payload = deepcopy(V1['modules'][0]['definition'])
    payload['sdk'] = sdk
    with pytest.raises(ValidationError):
        ModuleDefinition.model_validate(payload)


@pytest.mark.parametrize('change', ['missing_sdk', 'null_sdk', 'missing_api', 'range', 'prerelease', 'leading_zero',
    'unknown_sdk_field', 'duplicate_capability', 'invalid_capability', 'empty_capability',
    'boolean_state_version', 'float_state_version', 'zero_state_version', 'builtin', 'missing_runtime',
    'unknown_schema', 'unknown_top', 'unknown_nested'])
def test_invalid_schema2_contracts_are_rejected(change):
    payload = schema2_payload()
    if change == 'missing_sdk': payload.pop('sdk')
    elif change == 'null_sdk': payload['sdk'] = None
    elif change == 'missing_api': payload['sdk'].pop('api_version')
    elif change in {'range', 'prerelease', 'leading_zero'}:
        payload['sdk']['api_version'] = {'range':'>=0.2.0', 'prerelease':'0.2.0-beta', 'leading_zero':'0.02.0'}[change]
    elif change == 'unknown_sdk_field': payload['sdk']['unknown'] = True
    elif change == 'duplicate_capability': payload['sdk']['capabilities'] = ['net.valve', 'net.valve']
    elif change == 'invalid_capability': payload['sdk']['capabilities'] = ['Net valve']
    elif change == 'empty_capability': payload['sdk']['capabilities'] = ['']
    elif change == 'boolean_state_version': payload['sdk']['state_contract_version'] = True
    elif change == 'float_state_version': payload['sdk']['state_contract_version'] = 1.0
    elif change == 'zero_state_version': payload['sdk']['state_contract_version'] = 0
    elif change == 'builtin': payload['runtime'] = 'builtin'
    elif change == 'missing_runtime': payload.pop('runtime')
    elif change == 'unknown_schema': payload['schema_version'] = 99
    elif change == 'unknown_top': payload['unknown'] = True
    elif change == 'unknown_nested': payload['parameters'][0]['unknown'] = True
    with pytest.raises(ValidationError):
        ModuleDefinition.model_validate(payload)


def test_capability_order_browser_numbers_and_missing_sdk_defaults_are_canonical():
    payload = schema2_payload()
    payload['sdk']['capabilities'].reverse()
    payload['sdk'].pop('state_contract_version')
    payload['parameters'][1]['default'] = 8
    payload['parameters'][1]['minimum'] = 0
    assert definition_hash(ModuleDefinition.model_validate(payload)) == V2['modules'][1]['definition_hash']
    module = ModuleDefinition.model_validate(payload)
    assert module.sdk.capabilities == sorted(module.sdk.capabilities)
    explicit = schema2_payload()
    explicit['sdk']['capabilities'] = []
    omitted = deepcopy(explicit)
    omitted['sdk'].pop('capabilities')
    assert definition_hash(ModuleDefinition.model_validate(explicit)) == definition_hash(ModuleDefinition.model_validate(omitted))


@pytest.mark.parametrize('field,value', [('api_version', '0.3.0'), ('capabilities', ['future.thermal']),
                                       ('state_contract_version', 2)])
def test_sdk_declarations_participate_in_definition_hash(field, value):
    payload = schema2_payload()
    payload['sdk'][field] = value
    assert definition_hash(ModuleDefinition.model_validate(payload)) != V2['modules'][1]['definition_hash']


@pytest.mark.parametrize('sdk,code,field', [
    ({'api_version':'9.0.0'}, 'MODULE_SDK_UNSUPPORTED', 'sdk.api_version'),
    ({'api_version':'1.0.0'}, 'MODULE_SDK_UNSUPPORTED', 'sdk.api_version'),
    ({'api_version':'0.2.1'}, 'MODULE_SDK_UNSUPPORTED', 'sdk.api_version'),
    ({'api_version':'0.2.0', 'capabilities':['thermal.future']}, 'MODULE_CAPABILITY_UNSUPPORTED', 'sdk.capabilities'),
    ({'api_version':'0.1.0', 'capabilities':['net.resistance']}, 'MODULE_CAPABILITY_UNSUPPORTED', 'sdk.capabilities'),
    ({'api_version':'0.2.0', 'state_contract_version':2}, 'MODULE_STATE_CONTRACT_UNSUPPORTED', 'sdk.state_contract_version'),
])
def test_well_formed_but_unsupported_contract_is_readable_and_cannot_execute(sdk, code, field):
    payload = schema2_payload()
    payload['sdk'] = sdk
    module = ModuleDefinition.model_validate(payload)
    assert ModuleDefinition.model_validate_json(module.model_dump_json()).sdk == module.sdk
    with pytest.raises(ModuleCompatibilityError) as caught:
        check_module_compatibility(module)
    assert caught.value.code == code
    assert caught.value.field == field


def test_legacy_nested_project_and_catalog_serialization_preserve_contract_shape():
    project = Project.model_validate(V1['projects'][0]['project'])
    assert all('sdk' not in module for module in project.model_dump(mode='json')['modules'])
    definition = V1['modules'][0]['definition']
    item = ModuleCatalogItem.model_validate({**definition, 'package':None})
    assert item.package is None
    assert definition_hash(item) == definition['definition_hash']
    manifest = ModuleManifest(id='legacy', name='Legacy')
    assert manifest.runtime == 'python'
    assert 'sdk' not in manifest.model_dump()


def test_mutated_objects_are_revalidated_before_hashing_or_negotiation():
    module = ModuleDefinition.model_validate(schema2_payload())
    module.sdk = None
    for operation in [definition_hash, check_module_compatibility]:
        with pytest.raises(ValidationError):
            operation(module)


@pytest.mark.parametrize('sample', [V1['modules'][0], V2['modules'][1]], ids=lambda sample: sample['id'])
def test_draft_hash_allows_upgrade_preview_but_execution_rejects_broken_references(sample):
    module = ModuleDefinition.model_validate(sample['definition'])
    module.ports[0].id = 'renamed_inlet'
    assert len(definition_hash(module)) == 64
    assert definition_hash(module) != sample['definition_hash']
    with pytest.raises(ValidationError, match='不存在的端口'):
        check_module_compatibility(module)
