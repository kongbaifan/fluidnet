"""Portable foundation acceptance cases; --check never modifies saved artifacts."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from fn_engine.refrigeration.author_examples import author_station_example  # noqa: E402
from fn_engine.refrigeration.network_examples import network_example  # noqa: E402
from fn_engine.refrigeration.process_examples import process_example  # noqa: E402
from fn_engine.refrigeration.standby_example import standby_example  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    projects = {'parallel-network': network_example(), 'inventory-network': network_example(True),
                'cold-store-processes': process_example(True, True),
                'standby': standby_example(), 'author-constitutive': author_station_example()}
    for name, project in projects.items():
        path = ROOT / 'examples/foundation' / (name + '.project.json')
        payload = project.model_dump(mode='json')
        if args.check:
            if not path.exists() or json.loads(path.read_text(encoding='utf-8')) != payload:
                raise SystemExit(str(path) + ' mismatch')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Foundation examples consistent: ' + str(len(projects)))


if __name__ == '__main__':
    main()
