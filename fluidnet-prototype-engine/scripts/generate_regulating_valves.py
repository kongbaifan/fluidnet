"""Generate only the two new v1 valve seeds and portable examples; --check never writes."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fn_engine.regulating_valves import definitions, example  # noqa: E402
from fn_engine.hvac_expansion_examples import recipe  # noqa: E402


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    files={}
    for module in definitions():
        payload=module.model_dump(mode='json',exclude={'source','content_hash','definition_hash','package_path'})
        folder=ROOT/'modules'/module.id
        files[folder/'manifest.json']=json.dumps(payload,ensure_ascii=False,indent=2)+'\n'
        files[folder/'module.py']=module.source['runtime']
        files[ROOT/'examples/regulating-valves'/(module.id+'.project.json')]=example(module.id).model_dump_json(indent=2)+'\n'
        files[ROOT/'examples/regulating-valves'/(module.id+'.recipe.json')]=json.dumps(recipe(example(module.id)),ensure_ascii=False,indent=2)+'\n'
    for path,contents in files.items():
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8')!=contents:
                raise SystemExit('Generation mismatch: '+str(path))
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(contents,encoding='utf-8')
    print(f'Regulating valves consistent: {len(files)} files')


if __name__=='__main__':
    main()
