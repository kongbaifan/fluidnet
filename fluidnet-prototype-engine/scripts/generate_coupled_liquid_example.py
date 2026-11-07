"""Regenerate the portable coupled-liquid author example from its public package."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from fn_engine.refrigeration.liquid_module_examples import coupled_liquid_module_example  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    expected = coupled_liquid_module_example().model_dump(mode='json')
    path = ROOT / 'examples/coupled_liquid_modules/author_loop.json'
    if args.check:
        if json.loads(path.read_text(encoding='utf-8')) != expected:
            raise SystemExit(f'Example out of date: {path}')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Coupled liquid author example verified.' if args.check else 'Coupled liquid author example generated.')


if __name__ == '__main__':
    main()
