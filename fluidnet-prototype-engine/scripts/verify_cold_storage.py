"""A6: run the −18 °C cold-store case A-S01…A-S07 through the product API in a fresh workspace and write
an inspectable case package (reports, CSV, metrics, acceptance checks, environment, timing).

    python scripts/verify_cold_storage.py --output artifacts/cold-storage-a6-<date>

The output directory must not exist (evidence is never overwritten). Exit code 0 only if every check passes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
import time

import CoolProp
import psutil
from fastapi.testclient import TestClient

from fn_engine import __version__
from fn_engine.api import apply_scenario, create_app
from fn_engine.compiler import compile_project
from fn_engine.models import ScheduleEvent
from fn_engine.refrigeration.examples import ROOM_SCENARIO_DURATIONS, room_example
from fn_engine.refrigeration.report import run_metrics

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'cases' / 'cold-storage' / 'single-room-minus18'


def wait(client, run_id, timeout=900.):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        record = client.get(f'/api/v1/runs/{run_id}').json()
        if record['status'] in ('completed', 'failed', 'cancelled'):
            return record
        time.sleep(.2)
    raise TimeoutError(run_id)


def rows_of(client, run_id):
    rows, offset = [], 0
    while True:
        page = client.get(f'/api/v1/runs/{run_id}/history', params={'offset': offset, 'limit': 2001}).json()
        rows += page['rows']
        offset = page['offset'] + len(page['rows'])
        if not page['rows'] or offset >= page['total_rows']:
            return rows


def series(rows, key, start=0., end=math.inf, running=None):
    values = [r['variables'].get(key) for r in rows if start <= r['time_s'] < end
              and (running is None or r['variables'].get(running) == 1.)]
    return [v for v in values if v is not None]


def checks_for(sid, metrics, rows, record, network):
    m, last = metrics[0], rows[-1]['variables']
    codes = {d['code'] for r in rows for d in r.get('diagnostics', [])}
    out = [('运行完成', record['status'] == 'completed', record['status']),
           ('独立能量账本 ≤ max(100 J, 0.1%)', abs(m['ledger_residual_j']) <= max(100., 1e-3 * m['ledger_scale_j']),
            f'{m["ledger_residual_j"]:.3g} J / {m["ledger_scale_j"] / 3.6e6:.2f} kWh'),
           ('事件执行次数', rows[-1]['metrics'].get('events_applied') == len(network.events),
            f'{rows[-1]["metrics"].get("events_applied")} / {len(network.events)}'),
           ('全部帧保留', len(rows) == record['total_rows'] == round(ROOM_SCENARIO_DURATIONS[sid] / 30) + 1, len(rows))]
    in_band = m['pulldown_time_s'] is not None and (m['service_time_above_alarm_s'] or 0) == 0
    if sid in ('A-S01', 'A-S02', 'A-S03', 'A-S04', 'A-S05-onoff', 'A-S05-variable'):
        out.append(('进入温控带后不超温', in_band, f'降温 {m["pulldown_time_s"]} s，保温期超温 {m["service_time_above_alarm_s"]} s'))
    if sid in ('A-S02', 'A-S03', 'A-S06'):
        out.append(('扰动后恢复', all(e['recovery_s'] is not None for e in m['events']),
                    '；'.join(f'{e["id"]} 峰值 {e["peak_k"] - 273.15:.2f} °C，恢复 {e["recovery_s"]} s' for e in m['events'])))
    if sid == 'A-S03':
        out.append(('入库后货物质量', last['ROOM1.state.goods_mass_kg'] == 2500., last['ROOM1.state.goods_mass_kg']))
    if sid == 'A-S04':
        before = series(rows, 'CU1.condensing_temperature_k', 3600., 7200., 'CU1.state.running')
        after = series(rows, 'CU1.condensing_temperature_k', 10800., math.inf, 'CU1.state.running')
        cop_before = series(rows, 'CU1.cop', 3600., 7200., 'CU1.state.running')
        cop_after = series(rows, 'CU1.cop', 10800., math.inf, 'CU1.state.running')
        mean = lambda v: sum(v) / len(v)
        out.append(('室外升温后冷凝温度升高、COP 降低', mean(after) > mean(before) + 4 and mean(cop_after) < mean(cop_before),
                    f'冷凝 {mean(before) - 273.15:.2f} → {mean(after) - 273.15:.2f} °C，COP {mean(cop_before):.3f} → {mean(cop_after):.3f}'))
    if sid == 'A-S06':
        out.append(('两次融霜完成、融霜电量', last['AC1.state.defrost_count'] == 2.
                    and abs(last['AC1.state.heater_energy_j'] - 2 * 900 * 1500.) < 1e-6,
                    f'{last["AC1.state.defrost_count"]} 次，{last["AC1.state.heater_energy_j"] / 3.6e6:.3f} kWh'))
    if sid == 'A-S07':
        out.append(('能力不足：未到设定值、持续超温并给出诊断',
                    m['pulldown_time_s'] is None and m['time_above_alarm_s'] == ROOM_SCENARIO_DURATIONS[sid]
                    and 'COLD_ROOM_CAPACITY_SHORTFALL' in codes, f'超温 {m["time_above_alarm_s"] / 3600:.2f} h'))
    return [{'name': n, 'passed': bool(ok), 'detail': str(d)} for n, ok, d in out]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    process, started = psutil.Process(), time.perf_counter()
    summary = {'case_id': 'single-room-minus18-v1', 'generated_at': datetime.now(timezone.utc).isoformat(),
               'environment': {'engine': __version__, 'python': platform.python_version(), 'coolprop': CoolProp.__version__,
                               'platform': platform.platform(), 'processor': platform.processor(),
                               'cpu_count': psutil.cpu_count(), 'memory_bytes': psutil.virtual_memory().total},
               'input_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (CASE / 'parameters.json', CASE / 'scenarios.json', CASE / 'sources.json')},
               'numerics': {'publish_s': 30., 'internal_step_max_s': 10., 'control_sample_s': 5., 'mode': 'background fast'},
               'scenarios': [], 'negative': [], 'comparison': None, 'restart': None}
    project = room_example()
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / 'workspace'
        with TestClient(create_app(data_root=data, module_storage_root=Path(tmp) / 'modules')) as client:
            body = project.model_dump(mode='json')
            for scenario in project.scenarios:
                sid, duration = scenario.id, ROOM_SCENARIO_DURATIONS[scenario.id]
                begin = time.perf_counter()
                run_id = client.post('/api/v1/runs?background=true', json={'project': body, 'mode': 'dynamic', 'scenario_id': sid,
                    'duration_s': duration, 'dt_s': 30., 'history': 'trend', 'history_window': 20001}).json()['run_id']
                record = wait(client, run_id)
                wall = time.perf_counter() - begin
                rows = rows_of(client, run_id)
                network = compile_project(apply_scenario(project, sid))
                metrics = run_metrics({**record, 'request': record['request']}, rows, network)
                folder = args.output / sid
                folder.mkdir()
                (folder / 'report.html').write_text(client.get(f'/api/v1/runs/{run_id}/report.html').text, encoding='utf-8')
                (folder / 'data.csv').write_bytes(client.get(f'/api/v1/runs/{run_id}/report.csv').content)
                (folder / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
                checks = checks_for(sid, metrics, rows, record, network)
                summary['scenarios'].append({'id': sid, 'name': scenario.name, 'run_id': run_id, 'simulated_s': duration,
                    'wall_s': wall, 'frames': len(rows), 'checks': checks, 'metrics': {k: v for k, v in metrics[0].items() if k != 'events'},
                    'events': metrics[0]['events']})
                print(f'{sid}: {record["status"]} {wall:.1f} s, ' + ', '.join(f'{c["name"]}={"通过" if c["passed"] else "失败"}' for c in checks))
            ids = {s['id']: s['run_id'] for s in summary['scenarios']}
            compare = client.get('/api/v1/runs/compare/report.html', params={'a': ids['A-S05-onoff'], 'b': ids['A-S05-variable']})
            (args.output / 'A-S05-comparison.html').write_text(compare.text, encoding='utf-8')
            verdict = compare.text.split('<h2>结论</h2><ul><li>')[1].split('</li>')[0]
            summary['comparison'] = {'a': ids['A-S05-onoff'], 'b': ids['A-S05-variable'], 'fair': '不一致' not in compare.text,
                                     'verdict': verdict}
            # Negative checks: outside the declared envelope, and goods leaving the frozen model range.
            for name, events, code in [
                    ('室外 50 °C：冷凝温度超出运行范围', [ScheduleEvent(id='heatwave', type='ambient_temperature', time_s=3600., temperature_k=323.15)],
                     'REFRIGERATION_ENVELOPE'),
                    ('入库货温超出冻结模型', [ScheduleEvent(id='warm', type='goods_addition', time_s=60., mass_kg=10., temperature_k=270.15)],
                     'SCHEDULE_EVENT_INVALID')]:
                negative = room_example()
                negative.events = events
                response = client.post('/api/v1/runs?background=true', json={'project': negative.model_dump(mode='json'), 'mode': 'dynamic',
                                                                            'duration_s': 7200., 'dt_s': 30.})
                if response.status_code == 202:
                    record = wait(client, response.json()['run_id'])
                    found = [d['code'] for d in record['frame']['diagnostics']] if record['frame'] else []
                    detail = f'{record["status"]} t={record["frame"]["time_s"] if record["frame"] else 0:g}s {found}'
                    ok = record['status'] == 'failed' and code in found
                else:
                    detail, ok = response.text[:300], code in response.text
                summary['negative'].append({'name': name, 'expected': code, 'passed': ok, 'detail': detail})
                print(f'负向：{name} {"通过" if ok else "失败"} {detail}')
        with TestClient(create_app(data_root=data, module_storage_root=Path(tmp) / 'modules')) as client:
            first = summary['scenarios'][0]
            archived = client.get(f'/api/v1/runs/{first["run_id"]}').json()
            replay = client.post('/api/v1/runs', json={'project': project.model_dump(mode='json'), 'mode': 'dynamic',
                                                       'scenario_id': first['id'], 'duration_s': first['simulated_s'], 'dt_s': 30.}).json()
            summary['restart'] = {'archived_status': archived['status'], 'report_after_restart':
                                  client.get(f'/api/v1/runs/{first["run_id"]}/report.html').status_code == 200,
                                  'replay_identical': replay['frame']['variables'] == archived['frame']['variables']}
    summary['workers_after_stop'] = len(process.children(recursive=True))
    summary['peak_rss_bytes'] = process.memory_info().peak_wset if hasattr(process.memory_info(), 'peak_wset') else process.memory_info().rss
    summary['total_wall_s'] = time.perf_counter() - started
    passed = (all(c['passed'] for s in summary['scenarios'] for c in s['checks']) and all(n['passed'] for n in summary['negative'])
              and summary['comparison']['fair'] and summary['restart']['replay_identical']
              and summary['restart']['report_after_restart'] and summary['workers_after_stop'] == 0)
    summary['passed'] = passed
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{"全部通过" if passed else "存在失败"}；总墙钟 {summary["total_wall_s"]:.0f} s；输出 {args.output}')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
