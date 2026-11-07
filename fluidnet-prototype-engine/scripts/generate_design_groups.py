"""Generate only new design/group seeds; --check never writes."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fn_engine.equipment_design import definitions as design_definitions  # noqa: E402
from fn_engine.equipment_groups import definitions as group_definitions  # noqa: E402

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    count=0
    for m in [*design_definitions(),*group_definitions()]:
        folder=ROOT/'modules'/m.id
        contents={'manifest.json':json.dumps(m.model_dump(mode='json',exclude={'source','content_hash','definition_hash','package_path'}),ensure_ascii=False,indent=2)+'\n','module.py':m.source['runtime']}
        if m.source.get('design'):contents['design.py']=m.source['design']
        for name,source in contents.items():
            path=folder/name
            if args.check:
                if not path.exists() or path.read_text(encoding='utf-8')!=source:raise SystemExit('Mismatch: '+str(path))
            else:folder.mkdir(parents=True,exist_ok=True);path.write_text(source,encoding='utf-8')
            count+=1
    from fn_engine.equipment_library import catalog, build, LibraryRequest
    from fn_engine.hvac_expansion_examples import recipe
    for item in catalog().items:
        project=build(LibraryRequest(name=item.id))
        for suffix,data in [('project',project.model_dump(mode='json')),('recipe',recipe(project))]:
            path=ROOT/'examples/equipment-library'/f'{item.id}.{suffix}.json'
            source=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
            if args.check:
                if not path.exists() or path.read_text(encoding='utf-8')!=source:raise SystemExit('Mismatch: '+str(path))
            else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source,encoding='utf-8')
            count+=1
    print('Design/group seeds and examples consistent:',count)
if __name__=='__main__':main()
