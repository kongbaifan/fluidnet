"""Generate new boiler/bend seeds and examples; --check only compares."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fn_engine.hydronic_boiler import definition as boiler  # noqa: E402
from fn_engine.geometry_bend import definition as bend  # noqa: E402
from fn_engine.regulating_valves import example  # noqa: E402
from fn_engine.hvac_expansion_examples import recipe  # noqa: E402

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for m in (boiler(),bend()):
        p=example();p.modules=[p.modules[0],m];p.instances[1].module_id=m.id;p.instances[1].name=m.name
        p.instances[2].parameters['pressure_pa']=249900.;p.id=m.id+'-case';p.name=m.name
        files={ROOT/'modules'/m.id/'module.py':m.source['runtime'],
               ROOT/'modules'/m.id/'manifest.json':json.dumps(m.model_dump(mode='json',exclude={'source','content_hash','definition_hash','package_path'}),ensure_ascii=False,indent=2)+'\n',
               ROOT/'examples/hvac-expansion'/(m.id+'.project.json'):p.model_dump_json(indent=2)+'\n',
               ROOT/'examples/hvac-expansion'/(m.id+'.recipe.json'):json.dumps(recipe(p),ensure_ascii=False,indent=2)+'\n'}
        for path,text in files.items():
            if args.check:
                if not path.exists() or path.read_text(encoding='utf-8')!=text:raise SystemExit('Mismatch: '+str(path))
            else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    print('Simple equipment consistent')
if __name__=='__main__':main()
