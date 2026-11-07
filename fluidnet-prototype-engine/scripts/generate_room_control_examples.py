"""Publish portable room-control Project files; the browser can also create them via the example API."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

from fn_engine.chiller_examples import ROOM_CONTROL_EXAMPLES, room_temperature_example  # noqa: E402
from fn_engine.compiler import compile_project  # noqa: E402
from fn_engine.models import Position  # noqa: E402


def portable_example(name):
    project = room_temperature_example(name)
    for index, instance in enumerate(project.instances):
        instance.position = Position(x=100+(index%6)*170,y=120+(index//6)*130)
    for definition in project.modules:
        definition.package_path = None
    compile_project(project)
    return project


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    target = ROOT/'examples/room-control'
    if not args.check:
        target.mkdir(parents=True,exist_ok=True)
    for name in ROOM_CONTROL_EXAMPLES:
        expected = portable_example(name).model_dump(mode='json')
        path = target/(name+'.project.json')
        if args.check:
            if json.loads(path.read_text(encoding='utf-8')) != expected:
                raise SystemExit(f'Example out of date: {path}')
        else:
            path.write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Three room-control examples verified.' if args.check else 'Three room-control examples generated.')


if __name__ == '__main__':
    main()
