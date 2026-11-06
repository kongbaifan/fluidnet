"""Portable hydronic storage projects; --check never writes."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fn_engine.hydronic_buffer_example import example  # noqa: E402
from fn_engine.hvac_expansion_examples import recipe  # noqa: E402


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for name,options in [('hydronic-buffer',{}),('hydronic-buffer-stagnant',{'stagnant':True})]:
        p=example(**options)
        for suffix,data in [('project',p.model_dump(mode='json')),('recipe',recipe(p))]:
            dest=ROOT/'examples/forward'/f'{name}.{suffix}.json';text=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
            if args.check:
                if not dest.exists() or dest.read_text(encoding='utf-8')!=text:raise SystemExit('Mismatch: '+str(dest))
            else:dest.parent.mkdir(exist_ok=True,parents=True);dest.write_text(text,encoding='utf-8')
    print('Hydronic buffer examples consistent')
if __name__=='__main__':main()
