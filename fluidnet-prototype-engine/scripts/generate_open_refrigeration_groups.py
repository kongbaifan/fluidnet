"""Generate portable open-group hosts and test-context recipes; --check is read-only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from fn_engine.refrigeration.group_examples import GROUPS, open_group_example, grouped_station_example  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    payloads = {'source.project':open_group_example('compressors')[0].model_dump(mode='json'),
                'grouped-station.project':grouped_station_example().model_dump(mode='json')}
    for kind, (_, selected) in GROUPS.items():
        source, module, host = open_group_example(kind)
        payloads[kind+'.project'] = host.model_dump(mode='json')
        payloads[kind+'.recipe'] = {'source_project':'source.project.json', 'instance_ids':selected,
            'module_id':module.id, 'module_name':module.name, 'host_project':kind+'.project.json',
            'host_instance_id':'D1', 'duration_s':.2, 'dt_s':.1,
            'public_ports':[port.model_dump(mode='json') for port in module.ports]}
    for key, payload in payloads.items():
        path = ROOT/'examples/open-refrigeration-groups'/f'{key}.json'
        content = json.dumps(payload, ensure_ascii=False, indent=2)+'\n'
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != content:
                raise SystemExit(str(path)+' mismatch')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
    print('Open refrigeration group examples consistent')


if __name__ == '__main__':
    main()
