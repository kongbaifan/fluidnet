"""Registration must preserve executable identity and expose only separate UI metadata."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.catalog import builtin_catalog
from fn_engine.device_registry import BUILTIN_FAMILIES, STORAGE_DEVICES, registered_definitions
from fn_engine.runtime import module_definition_hash


# Measured before replacing catalog's five direct factory calls.
BASELINE_HASHES = {
    'closed_buffer_tank': '2d659f13ac3b0175659315e02f344ddc254a890fe33ce44d2d5af4fa15887560',
    'hydronic_buffer_tank': '4e9590f446bc04bcc07038ab46449085a82f2774773da9633e1244e11e7f593f',
    'gas_expansion_tank': 'b9b39e6d66a95c955c4c63b194676579ad81e7d6e1648ca5b220a4f85669008a',
    'tower_pool': '9b1e8f7c595c0cbd44330bd58ecb468fcc491d533d32793ce7770c201ac6d09a',
    'coupled_tower_pool': 'dafbb478e12969b88a19093c2e6af5fc1445a81be4cddadf2a569c9648df9406',
}


def test_registered_catalog_preserves_definition_hashes_order_and_fresh_instances():
    catalog = builtin_catalog()
    assert len({d.id for d in catalog}) == len(catalog)
    assert {d.id: module_definition_hash(d) for d in catalog if d.id in BASELINE_HASHES} == BASELINE_HASHES
    assert [d.id for d in catalog if d.id in BASELINE_HASHES] == list(BASELINE_HASHES)
    first, second = registered_definitions(), registered_definitions()
    first[0].parameters[0].default = 123456
    assert module_definition_hash(second[0]) == BASELINE_HASHES[second[0].id]


def test_invalid_registration_fails_before_exposing_a_catalog():
    descriptor = STORAGE_DEVICES[0]
    with pytest.raises(ValueError, match='Duplicate'):
        registered_definitions([descriptor, descriptor])
    with pytest.raises(ValueError, match='identity mismatch'):
        registered_definitions([replace(descriptor, module_id='wrong')])
    with pytest.raises(ValueError, match='domains mismatch'):
        registered_definitions([replace(descriptor, domains=('thermal',))])


def test_http_presentation_is_separate_from_the_executable_catalog(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        response = client.get('/api/v1/catalog/presentation')
        assert response.status_code == 200
        data = response.json()
        assert data['version'] == 1
        assert [d['module_id'] for d in data['devices']] == [d.id for d in builtin_catalog()]
        assert all(d['runtime'] == 'builtin' for d in data['devices'])
        catalog = client.get('/api/v1/catalog').json()
        assert set(catalog) == {'modules', 'prototype_parameter_bindings'}
        assert all('presentation' not in m and 'icon' not in m for m in catalog['modules'])
        assert all('factory' not in d for d in data['devices'])


def test_every_builtin_retains_full_definition_hash_and_order_after_family_registration():
    baseline = json.loads((Path(__file__).parent/'fixtures/catalog-registry.json').read_text(encoding='utf-8'))
    actual = [{'id': d.id, 'definition_hash': module_definition_hash(d), 'json_sha256': hashlib.sha256(
        json.dumps(d.model_dump(mode='json'), sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()}
        for d in builtin_catalog()]
    assert actual == baseline['devices']
    assert [len(f.members) for f in BUILTIN_FAMILIES] == [12, 9, 5, 2, 3, 29]
    first, second = builtin_catalog(), builtin_catalog()
    for left, right in zip(first, second):
        assert left is not right and left.parameters is not right.parameters and left.ports is not right.ports


def test_family_registration_rejects_missing_reordered_and_duplicate_definitions(monkeypatch):
    from fn_engine import device_registry as registry
    family = BUILTIN_FAMILIES[0]
    with pytest.raises(ValueError, match='membership or order'):
        replace(family, factory=lambda: list(reversed(family.factory()))).definitions()
    with pytest.raises(ValueError, match='membership or order'):
        replace(family, members=family.members[:-1]).definitions()
    with pytest.raises(ValueError, match='Duplicate'):
        replace(family, members=family.members+family.members[:1]).definitions()
    with pytest.raises(ValueError, match='Unknown'):
        registry.family_definitions('missing')
    monkeypatch.setattr(registry, 'BUILTIN_FAMILIES', (family, family))
    with pytest.raises(ValueError, match='Duplicate'):
        registry.presentation_catalog()


def test_presentation_reads_metadata_without_building_definitions(monkeypatch):
    from fn_engine import device_registry as registry
    def forbidden():
        pytest.fail('presentation must not call physical factories')
    monkeypatch.setattr(registry, 'BUILTIN_FAMILIES', tuple(replace(family, factory=forbidden) for family in BUILTIN_FAMILIES))
    assert len(registry.presentation_catalog()['devices']) == 60


def test_all_builtins_have_parameter_bindings_and_new_closed_volume_normalizes_and_compiles():
    from fn_engine.bridge import PARAMETER_BINDINGS, normalize_prototype_export
    from fn_engine.compiler import compile_project
    from test_trapped_volume import trapped_project
    project = trapped_project()
    baseline = json.loads((Path(__file__).parent/'fixtures/catalog-registry.json').read_text(encoding='utf-8'))
    before = baseline['prototype_parameter_bindings']
    assert {key: PARAMETER_BINDINGS[key] for key in before} == before
    assert PARAMETER_BINDINGS.keys() - before.keys() == {'closed_volume'}
    assert {d.id for d in builtin_catalog()} <= PARAMETER_BINDINGS.keys()
    assert PARAMETER_BINDINGS['source']['pressure'] == 'pressure_pa'
    assert PARAMETER_BINDINGS['valve']['opening'] == 'opening_ratio'
    assert PARAMETER_BINDINGS['pump']['speed'] == 'speed_ratio'
    definitions = {d.id: d for d in project.modules}
    nodes = []
    for instance in project.instances:
        specs = {p.id: p for p in definitions[instance.module_id].parameters}
        nodes.append({'id': instance.id, 'moduleId': instance.module_id, 'params': {
            key: specs[key].unit.from_canonical(value) if specs[key].unit else value
            for key, value in instance.parameters.items()}})
    raw = {'format': 'fluidnet-studio-prototype', 'activeProject': project.id,
           'modules': [{'id': d.id, 'kind': d.id} for d in project.modules],
           'projects': [{'id': project.id, 'name': project.name, 'medium': 'water', 'pages': [{
               'id': 'main', 'nodes': nodes, 'edges': [[edge.id, edge.source.instance_id, edge.source.port_id,
                                                     edge.target.instance_id, edge.target.port_id] for edge in project.connections]}]}]}
    restored = normalize_prototype_export(raw)
    assert restored.instances[3].module_id == 'closed_volume'
    assert restored.instances[3].parameters == project.instances[3].parameters
    compile_project(restored)
