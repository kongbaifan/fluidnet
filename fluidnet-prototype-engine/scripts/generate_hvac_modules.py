"""Publish reproducible basic HVAC seed packages; --check only compares generated contracts."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

from fn_engine.hvac_basic import equipment_definitions  # noqa: E402


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    for module in equipment_definitions():
        folder=ROOT/'modules'/module.id
        payload=module.model_dump(mode='json',exclude={'source','content_hash','definition_hash','package_path'})
        files={'manifest.json':json.dumps(payload,ensure_ascii=False,indent=2)+'\n', 'module.py':module.source['runtime']}
        for name,content in files.items():
            target=folder/name
            if args.check:
                if not target.exists() or target.read_text(encoding='utf-8')!=content:
                    raise SystemExit('生成物不一致：'+str(target))
            else:
                folder.mkdir(parents=True,exist_ok=True)
                target.write_text(content,encoding='utf-8')
    print('HVAC equipment packages consistent' if args.check else 'HVAC equipment packages generated')


if __name__=='__main__': main()
