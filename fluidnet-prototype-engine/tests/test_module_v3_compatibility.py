import json
from pathlib import Path
import pytest
from fn_engine.models import ModuleDefinition
from fn_engine.module_contracts import canonical_contract_bytes,definition_hash
from fn_engine.runtime import module_content_hash

FROZEN=json.loads((Path(__file__).parent/'fixtures/module-system/v3-snapshots.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('sample',FROZEN['modules'],ids=lambda sample:sample['id'])
def test_schema3_author_contracts_export_reload_preserve_frozen_bytes_and_hashes(sample):
    module=ModuleDefinition.model_validate(sample['definition'])
    for _ in range(3):
        assert canonical_contract_bytes(module).decode()==sample['canonical_json']
        assert definition_hash(module)==sample['definition_hash']
        assert module_content_hash(module)==sample['content_hash']
        module=ModuleDefinition.model_validate_json(module.model_dump_json())
