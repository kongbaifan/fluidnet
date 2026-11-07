"""Registration must preserve executable identity and expose only separate UI metadata."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.catalog import builtin_catalog
from fn_engine.device_registry import STORAGE_DEVICES, registered_definitions
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
        assert [d['module_id'] for d in data['devices']] == list(BASELINE_HASHES)
        assert all(d['runtime'] == 'builtin' and d['canvas_family'] == 'tank' for d in data['devices'])
        catalog = client.get('/api/v1/catalog').json()
        assert set(catalog) == {'modules', 'prototype_parameter_bindings'}
        assert all('presentation' not in m and 'icon' not in m for m in catalog['modules'])
        assert all('factory' not in d for d in data['devices'])
