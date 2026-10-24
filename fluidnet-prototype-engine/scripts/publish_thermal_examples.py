"""Create explicit v2 seeds using the new heat/observation API; legacy seeds stay frozen."""
import json
from pathlib import Path

from fn_engine.models import ModuleDefinition
from fn_engine.module_contracts import contract_model
from fn_engine.runtime import module_content_hash, module_definition_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    for identifier, example, thermal in [('fan_coil_unit', 'fan_coil', True), ('cooling_tower', 'cooling_tower', True),
                                         ('capillary_tube', 'capillary', False)]:
        payload = json.loads((ROOT / 'modules' / identifier / 'manifest.json').read_text(encoding='utf-8'))
        payload.update(schema_version=2, version=2, runtime='python', content_hash=None, definition_hash=None,
            source={'runtime':(ROOT / f'examples/module_sdk/{example}.py').read_text(encoding='utf-8')},
            sdk={'api_version':'0.4.0', 'capabilities':['net.pipe', 'observe.v1', 'state.transactions.v1'] + (['thermal.v1'] if thermal else [])})
        module = ModuleDefinition.model_validate(payload)
        module.content_hash, module.definition_hash = module_content_hash(module), module_definition_hash(module)
        target = ROOT / 'modules' / f'{identifier}_sdk'
        target.mkdir(exist_ok=True)
        (target / 'manifest.json').write_text(json.dumps(contract_model(module).model_dump(mode='json',
            exclude={'source', 'package_path'}), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (target / 'module.py').write_text(module.source['runtime'], encoding='utf-8', newline='')


if __name__ == '__main__':
    main()
