"""Run the complete six-room plant on one timeline and save compact acceptance evidence."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from fn_engine.checkpoints import capture, restore
from fn_engine.compiler import compile_project
from fn_engine.model_types.domain import ScheduleEvent
from fn_engine.refrigeration.six_room_continuous import continuous_large_cold_store
from fn_engine.sessions import create_session


def validate(duration=86520., out=None, checkpoint=True):
    out = out or ROOT / 'artifacts/six-room-continuous'
    out.mkdir(parents=True, exist_ok=True)
    project, assumptions = continuous_large_cold_store()
    session = create_session(compile_project(project), None, 30., keep=8)
    room_ids = list(assumptions['rooms'])
    cooler_ids = assumptions['operation']['defrost_order']
    selected = [r + suffix for r in room_ids for suffix in (
        '.state.temperature_k', '.goods_temperature_k', '.goods_frozen_ratio', '.humidity_ratio_kg_kg',
        '.infiltration_heat_w', '.param.heat_input_w')]
    selected += [c + suffix for c in cooler_ids for suffix in (
        '.defrost_mode', '.frost_mass_kg', '.hot_gas_heat_w', '.hot_mass_flow_kg_s', '.mass_flow_kg_s',
        '.state.defrost_count')]
    selected += [i + suffix for i in ('LT_PUMP', 'LT_PUMP2', 'MT_PUMP', 'MT_PUMP2',
        'LT_K1', 'LT_K2', 'LT_K3', 'HT_K1', 'HT_K2', 'HT_K3') for suffix in ('.mass_flow_kg_s', '.param.running')]
    selected += [v + suffix for v in ('HP', 'IP', 'LP') for suffix in ('.state.pressure_pa', '.state.level_ratio')]
    selected += [i + '.oil_mass_residual_kg' for i in ('LT_OIL', 'HT_OIL')]
    selected += ['script.operating_day.state.day', 'script.operating_day.state.phase']
    rows, transitions, maxima = [], [], {}
    evidence = {'load': False, 'cooler_stop': False, 'pump_backup': False, 'pump_recovered': False,
                'compressor_backup': False, 'compressor_recovered': False, 'doors': [],
                'hotgas_coolers': [], 'defrost_modes': {}, 'checkpoint_max_difference': None,
                'next_day': False}
    started = time.perf_counter()
    last_status = None
    passed = False
    try:
        frame = session.initialize()
        while frame.time_s <= duration:
            v = frame.variables
            for key, value in frame.metrics.items():
                if 'residual' in key: maxima[key] = max(maxima.get(key, 0.), abs(value))
            for oil in ('LT_OIL', 'HT_OIL'):
                key = oil + '.oil_mass_residual_kg'
                maxima[key] = max(maxima.get(key, 0.), abs(v[key]))
            assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-6
            assert abs(frame.metrics['energy_residual_j']) < 10.
            assert abs(frame.metrics['water_mass_residual_kg']) < 1e-6
            assert all(maxima[i + '.oil_mass_residual_kg'] < 1e-7 for i in ('LT_OIL', 'HT_OIL'))
            for room in room_ids:
                if v[room + '.infiltration_heat_w'] > 0. and room not in evidence['doors']:
                    evidence['doors'].append(room)
            for cooler in cooler_ids:
                mode = int(v[cooler + '.defrost_mode'])
                modes = evidence['defrost_modes'].setdefault(cooler, [])
                if mode not in modes: modes.append(mode)
                if v[cooler + '.hot_gas_heat_w'] > 0. and cooler not in evidence['hotgas_coolers']:
                    evidence['hotgas_coolers'].append(cooler)
            for room in room_ids:
                assert not (v[room + '_AC1.defrost_mode'] and v[room + '_AC2.defrost_mode'])
            phase = v.get('script.operating_day.state.phase', '')
            evidence['load'] |= phase == 'load' and v['F01.param.heat_input_w'] > assumptions['rooms']['F01']['base_heat_input_w']
            evidence['cooler_stop'] |= phase == 'cooler-stop' and abs(v['F01_AC1.mass_flow_kg_s']) < 1e-8
            evidence['pump_backup'] |= phase == 'pump-fault' and v['LT_PUMP2.mass_flow_kg_s'] > .1
            evidence['pump_recovered'] |= frame.time_s > 36750 and v['LT_PUMP.param.running'] == 1. and v['LT_PUMP2.param.running'] == 0.
            evidence['compressor_backup'] |= phase == 'compressor-fault' and v['LT_K3.mass_flow_kg_s'] > .001
            evidence['compressor_recovered'] |= frame.time_s > 43950 and v['LT_K1.param.running'] == 1. and v['LT_K3.param.running'] == 0.
            evidence['next_day'] |= v.get('script.operating_day.state.day', 0) >= 1
            status = (phase, *(int(v[c + '.defrost_mode']) for c in cooler_ids),
                      v['LT_PUMP2.param.running'], v['LT_K3.param.running'])
            if status != last_status:
                transitions.append({'time_s': frame.time_s, 'status': status})
            if frame.time_s % 300 == 0 or status != last_status:
                row = {'time_s': frame.time_s, 'variables': {k: v.get(k) for k in selected}, 'metrics': frame.metrics}
                rows.append(row)
                (out / 'latest.json').write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
            if frame.time_s % 600 == 0:
                print(json.dumps({'time_s': frame.time_s, 'wall_s': round(time.perf_counter() - started, 2),
                    'room_c': [round(v[r + '.state.temperature_k'] - 273.15, 3) for r in room_ids],
                    'energy_residual_j': frame.metrics['energy_residual_j']}, ensure_ascii=False), flush=True)
            last_status = status
            if frame.time_s >= duration: break
            if checkpoint and frame.time_s >= min(900., duration / 2.) and evidence['checkpoint_max_difference'] is None:
                saved = capture(session)
                (out / 'checkpoint.json').write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
                branch = restore(saved)
                try:
                    frame, twin = session.advance(), branch.advance()
                    diffs = [abs(value - twin.variables[key]) for key, value in frame.variables.items()
                             if isinstance(value, (float, int)) and isinstance(twin.variables.get(key), (float, int))]
                    evidence['checkpoint_max_difference'] = max(diffs, default=0.)
                    assert evidence['checkpoint_max_difference'] < 1e-6
                finally: branch.close()
            else:
                frame = session.advance()
        if duration >= 86520:
            assert all(evidence[k] for k in ('load', 'cooler_stop', 'pump_backup', 'pump_recovered',
                'compressor_backup', 'compressor_recovered', 'next_day'))
            assert set(evidence['doors']) == set(room_ids)
            assert set(evidence['hotgas_coolers']) == set(cooler_ids)
            assert all(set(modes) == {0, 1, 2, 3, 4} for modes in evidence['defrost_modes'].values())
        passed = True
    finally:
        summary = {'passed': passed, 'time_s': session.time, 'wall_s': time.perf_counter() - started,
            'devices': len(project.instances), 'connections': len(project.connections),
            'max_residuals': maxima, 'evidence': evidence, 'transitions': transitions}
        (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        if duration >= 86400.:
            (ROOT / 'examples/large-cold-store/continuous-validation-summary.json').write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (out / 'trajectory.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        session.close()
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def validate_auxiliary(out):
    """Separate initial-goods and second-zone backup checks; not a substitute for the operating day."""
    out.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for case, duration in (('warm-goods', 2400.), ('high-middle-standby', 480.)):
        project, _ = continuous_large_cold_store()
        if case == 'warm-goods':
            scenario = next(s for s in project.scenarios if s.id == case)
            for node in project.instances: node.parameters.update(scenario.overrides.get(node.id, {}))
        else:
            project.events = [ScheduleEvent(id=f'{iid}-{int(t)}', type='set_variable', time_s=t,
                key=iid + '.param.running', value=state) for t, state in ((60., 0.), (300., 1.)) for iid in ('HT_K1', 'MT_PUMP')]
        session = create_session(compile_project(project), duration, 30., keep=8)
        keys = ['F01.goods_temperature_k', 'F01.goods_frozen_ratio', 'F01.state.goods_energy_j'] + [
            iid + suffix for iid in ('HT_K1', 'HT_K3', 'MT_PUMP', 'MT_PUMP2')
            for suffix in ('.mass_flow_kg_s', '.param.running')]
        started, rows = time.perf_counter(), []
        try:
            frame = session.initialize()
            while True:
                rows.append({'time_s': frame.time_s, **{key: frame.variables[key] for key in keys}})
                assert abs(frame.metrics['energy_residual_j']) < .1
                assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-6
                if frame.time_s % 600 == 0: print(case, frame.time_s, flush=True)
                if frame.time_s >= duration: break
                frame = session.advance()
            if case == 'warm-goods':
                assert rows[-1]['F01.state.goods_energy_j'] < rows[0]['F01.state.goods_energy_j']
                assert 0. < rows[-1]['F01.goods_frozen_ratio'] < 1.
            else:
                assert any(r['HT_K3.mass_flow_kg_s'] > .01 and r['MT_PUMP2.mass_flow_kg_s'] > .1
                    and r['HT_K3.param.running'] == r['MT_PUMP2.param.running'] == 1. for r in rows)
                assert rows[-1]['HT_K3.param.running'] == rows[-1]['MT_PUMP2.param.running'] == 0.
            result = {'passed': True, 'time_s': frame.time_s, 'wall_s': time.perf_counter() - started,
                      'metrics': frame.metrics, 'rows': rows}
            (out / (case + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            summaries[case] = {k: v for k, v in result.items() if k != 'rows'}
        finally: session.close()
    print(json.dumps(summaries, ensure_ascii=False), flush=True)
    return summaries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=86520.)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--no-checkpoint', action='store_true')
    parser.add_argument('--auxiliary', action='store_true', help='run the separate warm-goods and high/middle backup cases')
    args = parser.parse_args()
    if args.auxiliary:
        validate_auxiliary(args.out or ROOT / 'artifacts/six-room-continuous')
    else:
        validate(args.duration, args.out, not args.no_checkpoint)
