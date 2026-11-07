"""Publish portable basic HVAC cases, with optional reproducibility verification."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

from fn_engine.compiler import compile_project  # noqa: E402
from fn_engine.hvac_examples import HVAC_EXAMPLES,hvac_example  # noqa: E402


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    for name in HVAC_EXAMPLES:
        project=hvac_example(name)
        for definition in project.modules:definition.package_path=None
        compile_project(project)
        expected=project.model_dump(mode='json')
        path=ROOT/'examples/hvac-basic'/(name+'.project.json')
        if args.check:
            if not path.exists() or json.loads(path.read_text(encoding='utf-8'))!=expected:
                raise SystemExit('HVAC example out of date: '+str(path))
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(HVAC_EXAMPLES)} HVAC examples '+('verified.' if args.check else 'generated.'))


if __name__=='__main__':main()
