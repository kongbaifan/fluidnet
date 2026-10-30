"""Build an importable full station using the public author throttle package."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

from fn_engine.compiler import compile_project  # noqa: E402
from fn_engine.models import Project, Position, Scenario  # noqa: E402
from fn_engine.packages import load_module_package, package_ref  # noqa: E402
from fn_engine.runtime import module_content_hash, module_definition_hash  # noqa: E402
from fn_engine.refrigeration.examples import station_case, station_example  # noqa: E402

VALVE='Expansion-Custom'
CONDENSER='Condenser-Custom'
LAYOUT={'LP1':(190,220),'SH1':(330,150),'K1':(470,80),'K2':(470,160),'K3':(470,240),'K4':(470,320),
    'DH1':(610,150),'EC1':(750,150),'HP1':(890,330),'EV1':(890,470),'RH1':(610,520),'HX1':(330,560),
    'CD1':(190,640),'PU1':(330,720),'FH1':(470,720),'AC1':(610,640),'AC2':(610,800),
    'BH1':(190,800),'ROOM1':(790,640),'ROOM2':(790,800)}


def author_station(module=None,compact=False):
    module=(module or load_module_package(ROOT/'modules/isenthalpic_throttle')).model_copy(deep=True)
    module.package_path=None
    module.content_hash=module_content_hash(module)
    module.definition_hash=module_definition_hash(module)
    project=station_example() if compact else station_case()
    for node in project.instances:
        x,y=LAYOUT.get(node.id,(100,100))
        node.position=Position(x=x,y=y)
    payload=project.model_dump_json().replace('"EV1"',f'"{VALVE}"').replace('EV1.',VALVE+'.')
    payload=payload.replace('"EC1"',f'"{CONDENSER}"').replace('EC1.',CONDENSER+'.')
    data=json.loads(payload)
    for script in data['control_scripts']:script['content_hash']=None
    project=Project.model_validate(data)
    valve=next(n for n in project.instances if n.id==VALVE)
    valve.module_id=module.id;valve.package=package_ref(module)
    project.modules.append(module)
    used={n.module_id for n in project.instances}
    project.modules=[m for m in project.modules if m.id in used]
    project.id='author-station-small' if compact else 'author-station-nh3co2'
    project.name='作者节流模块 · '+('单回路制冷站' if compact else 'NH₃/CO₂ 完整制冷站')
    project.description='公共 SDK 等焓节流设备，项目与运行固定模块版本；含原有控制及自定义实例编号。'
    project.scenarios=[Scenario(id='half-opening',name='初始半开度',overrides={VALVE:{'opening_ratio':.5}}),
        Scenario(id='equal-percentage',name='等百分比特性',overrides={VALVE:{'characteristic':'equal_percentage'}})]
    compile_project(project)
    return project


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    for compact,name in [(False,'author_station.json'),(True,'author_station_small.json')]:
        expected=author_station(compact=compact).model_dump(mode='json')
        path=ROOT/'examples/refrigeration_extensions'/name
        if args.check:
            if json.loads(path.read_text(encoding='utf-8'))!=expected:raise SystemExit(f'Example out of date: {path}')
        else:path.write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Two author station examples verified.' if args.check else 'Two author station examples generated.')


if __name__=='__main__':main()
