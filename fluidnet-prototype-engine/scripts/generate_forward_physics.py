"""Generate S5/S6 portable cases without overwriting old published modules."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fn_engine.refrigeration.forward_examples import headed_example,manifold_example,tube_bundle_example,coil_intercooler_example,coupled_buffer_example  # noqa: E402


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for factory in (headed_example,manifold_example,tube_bundle_example,coil_intercooler_example,coupled_buffer_example):
        project=factory();data=project.model_dump(mode='json');recipe={key:data[key] for key in ('name','fluid','solver','instances','connections','circuit_fluids')}
        recipe.update(duration_s=1.,dt_s=.1,thermal_couplings=data.get('thermal_couplings',[]),coupling_mode=data.get('coupling_mode','legacy'))
        for kind,payload in [('project',data),('recipe',recipe)]:
            path=ROOT/'examples/forward-physics'/f'{project.id}.{kind}.json';contents=json.dumps(payload,ensure_ascii=False,indent=2)+'\n'
            if args.check:
                if not path.exists() or path.read_text(encoding='utf-8')!=contents:raise SystemExit(str(path)+' mismatch')
            else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(contents,encoding='utf-8')
    print('Forward physics examples consistent')
if __name__=='__main__':main()
