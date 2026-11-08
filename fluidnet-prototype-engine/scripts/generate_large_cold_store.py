"""Generate the explicitly declared six-room example; --check is read-only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from fn_engine.refrigeration.large_cold_store_example import assembly_recipe, build_large_cold_store  # noqa: E402
from fn_engine.refrigeration.large_cold_store_control import controlled_large_cold_store  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    project, metadata = build_large_cold_store()
    for definition in project.modules:
        definition.package_path = None
    documents = {'six-room.project.json': project.model_dump(mode='json'),
                 'six-room.recipe.json': assembly_recipe(), 'design-assumptions.json': metadata}
    controlled = controlled_large_cold_store()
    for definition in controlled.modules:
        definition.package_path = None
    documents['six-room-controlled.project.json'] = controlled.model_dump(mode='json')
    for name, data in documents.items():
        path = ROOT / 'examples' / 'large-cold-store' / name
        text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        if args.check:
            if not path.exists() or json.loads(path.read_text(encoding='utf-8')) != data:
                raise SystemExit('Large cold store example differs: ' + str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
    print(f'Large cold store: {len(project.instances)} devices, {len(project.connections)} connections; ' +
          ('verified' if args.check else 'generated'))


if __name__ == '__main__':
    main()
