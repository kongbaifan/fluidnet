"""Generate only new HVAC seed IDs and portable reference projects; never rewrite old versions."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fn_engine.hvac_expansion import definitions  # noqa: E402


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for m in definitions():
        payload=m.model_dump(mode='json',exclude={'source','content_hash','definition_hash','package_path'})
        files={'manifest.json':json.dumps(payload,ensure_ascii=False,indent=2)+'\n','module.py':m.source['runtime']}
        for name,text in files.items():
            path=ROOT/'modules'/m.id/name
            if args.check:
                if not path.exists() or path.read_text(encoding='utf-8')!=text:raise SystemExit(f'不一致：{path}')
            else:
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    from fn_engine.hvac_expansion_examples import HVAC_EXPANSION_EXAMPLES, example, recipe
    for name in HVAC_EXPANSION_EXAMPLES:
        p=example(name)
        for suffix,data in [('project',p.model_dump(mode='json')),('recipe',recipe(p))]:
            path=ROOT/'examples/hvac-expansion'/f'{name}.{suffix}.json'
            text=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
            if args.check:
                if not path.exists() or path.read_text(encoding='utf-8')!=text:raise SystemExit(f'不一致：{path}')
            else:
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    print('HVAC expansion packages and examples consistent' if args.check else 'HVAC expansion generated')


if __name__=='__main__':main()
