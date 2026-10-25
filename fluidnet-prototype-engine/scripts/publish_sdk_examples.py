"""Build checked-in SDK seed packages without modifying any legacy release."""
import json
from pathlib import Path

from fn_engine.models import ModuleDefinition
from fn_engine.module_contracts import contract_model
from fn_engine.runtime import module_content_hash, module_definition_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    samples = json.loads((ROOT / 'tests/fixtures/module-system/v2-snapshots.json').read_text(encoding='utf-8'))['modules']
    for sample, directory, identifier, version, name, example in [
        (samples[0], 'programmable_valve_sdk', 'programmable_valve', 2, '可编程阀门（SDK）', 'valve'),
        (samples[1], 'sdk_resistance', 'sdk_resistance', 1, 'SDK 局部阻力', 'resistance'),
    ]:
        payload = dict(sample['definition'])
        source = (ROOT / f'examples/module_sdk/{example}.py').read_text(encoding='utf-8')
        payload.update(id=identifier, version=version, name=name, source={'runtime': source},
                       content_hash=None, definition_hash=None, package_path=None)
        payload['sdk'] = {'api_version': '0.5.0', 'capabilities': [
            'lifecycle.v1', 'state.json.v1', 'context.execution.v1','hydraulic.signed_start.v1',
            f'net.{"valve" if example == "valve" else "resistance"}']}
        module = ModuleDefinition.model_validate(payload)
        module.content_hash = module_content_hash(module)
        module.definition_hash = module_definition_hash(module)
        target = ROOT / 'modules' / directory
        target.mkdir(exist_ok=True)
        manifest = contract_model(module).model_dump(mode='json', exclude={'source', 'package_path'})
        (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (target / 'module.py').write_text(source, encoding='utf-8', newline='')


if __name__ == '__main__':
    main()
