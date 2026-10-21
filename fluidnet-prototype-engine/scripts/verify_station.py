"""B acceptance: run the NH3/CO2 station scenarios B-S01…B-S04 at full length through the product API in a fresh
workspace and write a case package (reports, CSV, metrics, checks). EXECUTION_PLAN.md section 4.

    python scripts/verify_station.py --output artifacts/cold-storage-b-<date>
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
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
from fn_engine.refrigeration.examples import STATION_SCENARIO_DURATIONS, station_case
from fn_engine.refrigeration.report import station_metrics
from verify_cold_storage import rows_of, wait

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'cases' / 'cold-storage' / 'nh3-co2' / 'station'
DESIGN = json.loads((CASE / 'references' / 'design_point.json').read_text(encoding='utf-8'))['design']
STOP_CODES = {'VESSEL_LEVEL_RANGE', 'VESSEL_PHASE_RANGE', 'COMPRESSOR_PRESSURE_RATIO', 'REFRIGERATION_NOT_CONVERGED'}


def checks_for(sid, m, rows, record):
    last = rows[-1]['variables']
    codes = {d['code'] for r in rows for d in r.get('diagnostics', [])}
    exchanged = sum(abs(last[k]) for k in last if k.endswith(('.state.electric_energy_j', '.state.fan_energy_j',
                                                                '.state.heat_rejected_j', '.state.external_energy_j')))
    out = [('运行完成', record['status'] == 'completed', record['status']),
           ('两库库温在设定 ±1 K', all(r['max_deviation_k'] < 1. for r in m['rooms'].values()),
            '，'.join(f'{k} {v["max_deviation_k"]:.3f} K' for k, v in m['rooms'].items())),
           ('贮液器液位在 0.6–0.667', .6 <= m['levels']['HP1']['min'] and m['levels']['HP1']['max'] <= .667,
            f'{m["levels"]["HP1"]["min"]:.4f} … {m["levels"]["HP1"]["max"]:.4f}'),
           ('其余容器在模型液位带内', all(.05 < v['min'] and v['max'] < .95 for v in m['levels'].values()), str(m['levels'])),
           ('NH₃/CO₂ 存量守恒', all(abs(v) < 1e-6 for v in m['mass_residual_kg'].values()), str(m['mass_residual_kg'])),
           ('能量账本 ≤ 0.1%', abs(m['energy_residual_j']) <= 1e-3 * exchanged, f'{m["energy_residual_j"]:.3g} J / {exchanged / 3.6e6:.0f} kWh'),
           ('无越界停止诊断', not codes & STOP_CODES and 'COMPRESSOR_ENVELOPE' not in codes, ''),
           ('需求满足度 100%', m['satisfaction'] == 1., f'{m["satisfaction"]}')]
    tail = [r['variables'] for r in rows if r['time_s'] >= rows[-1]['time_s'] - 3 * 3600]
    for cid, key in (('suction', 'LP1.state.pressure_pa'), ('head', 'HP1.state.pressure_pa')):
        error = max(abs(v[key] - v[f'controller.{cid}.setpoint']) for v in tail)
        out.append((f'末 3 h {cid} 压力跟踪目标（≤ 0.5%）', error <= 5e-3 * tail[-1][f'controller.{cid}.setpoint'], f'{error / 1000:.2f} kPa'))
    if sid == 'B-S01':
        out.append(('稳态与 B0 独立设计点一致', abs(last['K1.param.load_ratio'] - DESIGN['compressors']['load_each']) < 1e-3
                    and abs(rows[-1]['metrics']['electric_power_w'] / DESIGN['balance']['electric_power_w'] - 1) < 1e-4,
                    f'载量 {last["K1.param.load_ratio"]:.4f}（参考 {DESIGN["compressors"]["load_each"]:.4f}），电功率 '
                    f'{rows[-1]["metrics"]["electric_power_w"] / 1000:.3f} kW（参考 {DESIGN["balance"]["electric_power_w"] / 1000:.3f}）'))
    if sid == 'B-S02':
        peak = max(r['variables'].get('script.control.state.running', 0) for r in rows)
        out.append(('负荷升高增开、降低后减停', m['compressor_starts'] == 1 and m['compressor_stops'] == 1 and peak == 4,
                    f'启动 {m["compressor_starts"]:.0f}、停止 {m["compressor_stops"]:.0f}，最多 {peak:.0f} 台'))
    if sid == 'B-S03':
        before = next(r for r in rows if r['time_s'] == 21600.)['metrics']['electric_power_w']
        out.append(('提高蒸发、降低冷凝目标后电功率下降', rows[-1]['metrics']['electric_power_w'] < before - 5000.,
                    f'{before / 1000:.2f} → {rows[-1]["metrics"]["electric_power_w"] / 1000:.2f} kW'))
    if sid == 'B-S04':
        low = [r['variables']['EC1.param.fan_ratio'] for r in rows if 33000 <= r['time_s'] <= 50400]
        out.append(('湿球降低时冷凝器风机减组、回升后恢复', set(low) == {.5} and last['EC1.param.fan_ratio'] == 1.
                    and m['condenser_fan_changes'] == 2, f'风机组切换 {m["condenser_fan_changes"]:.0f} 次'))
    return [{'name': n, 'passed': bool(ok), 'detail': str(d)} for n, ok, d in out]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started, process = time.perf_counter(), psutil.Process()
    summary = {'case_id': 'nh3co2-two-room-v1', 'generated_at': datetime.now(timezone.utc).isoformat(),
               'environment': {'engine': __version__, 'python': platform.python_version(), 'coolprop': CoolProp.__version__,
                               'platform': platform.platform(), 'cpu_count': psutil.cpu_count()},
               'input_sha256': {'parameters.json': hashlib.sha256((CASE / 'parameters.json').read_bytes()).hexdigest()},
               'scenarios': []}
    project = station_case()
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / 'workspace'
        with TestClient(create_app(data_root=data, module_storage_root=Path(tmp) / 'modules')) as client:
            for scenario in project.scenarios:
                sid, duration = scenario.id, STATION_SCENARIO_DURATIONS[scenario.id]
                begin = time.perf_counter()
                run_id = client.post('/api/v1/runs?background=true', json={'project': project.model_dump(mode='json'), 'mode': 'dynamic',
                    'scenario_id': sid, 'duration_s': duration, 'dt_s': 30., 'history': 'trend', 'history_window': 20001}).json()['run_id']
                record = wait(client, run_id)
                wall = time.perf_counter() - begin
                rows = rows_of(client, run_id)
                metrics = station_metrics(rows, compile_project(apply_scenario(project, sid)))
                folder = args.output / sid
                folder.mkdir()
                (folder / 'report.html').write_text(client.get(f'/api/v1/runs/{run_id}/report.html').text, encoding='utf-8')
                (folder / 'data.csv').write_bytes(client.get(f'/api/v1/runs/{run_id}/report.csv').content)
                (folder / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
                checks = checks_for(sid, metrics, rows, record)
                summary['scenarios'].append({'id': sid, 'name': scenario.name, 'run_id': run_id, 'simulated_s': duration, 'wall_s': wall,
                                             'frames': len(rows), 'checks': checks, 'metrics': metrics})
                print(f'{sid}: {record["status"]} {wall:.1f} s，' + '，'.join(f'{c["name"]}={"通过" if c["passed"] else "失败"}' for c in checks))
            first = summary['scenarios'][0]
        with TestClient(create_app(data_root=data, module_storage_root=Path(tmp) / 'modules')) as client:
            archived = client.get(f'/api/v1/runs/{first["run_id"]}').json()
            replay = client.post('/api/v1/runs?background=true', json={'project': project.model_dump(mode='json'), 'mode': 'dynamic',
                'scenario_id': first['id'], 'duration_s': first['simulated_s'], 'dt_s': 30.}).json()['run_id']
            again = wait(client, replay)
            summary['restart'] = {'archived_status': archived['status'],
                                  'replay_identical': again['frame']['variables'] == archived['frame']['variables']}
    summary['workers_after_stop'] = len(process.children(recursive=True))
    summary['total_wall_s'] = time.perf_counter() - started
    summary['passed'] = (all(c['passed'] for s in summary['scenarios'] for c in s['checks']) and summary['restart']['replay_identical']
                         and summary['workers_after_stop'] == 0)
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{"全部通过" if summary["passed"] else "存在失败"}；总墙钟 {summary["total_wall_s"]:.0f} s；输出 {args.output}')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
