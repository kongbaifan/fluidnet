"""Engineering A/B acceptance: optional module cache / mixed Jacobian on vs off on repository cases.

Each run is a fresh process (cold start, own Workers). Results are checked against independent
equations (engineering_checks) and compared frame by frame with the baseline run.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'

MODES = {'baseline': (False, False), 'cache': (True, False), 'jacobian': (False, True), 'both': (True, True)}
COUNTER_KEYS = ('residual_calls', 'perturbation_calls', 'nfev', 'njev', 'rpc_batches', 'rpc_instances',
                'parent_cache_hits', 'module_evaluations')


def worker_processes(*groups):
    """Live Popen handles of module and control-script Workers (BatchRunners or per-instance dicts)."""
    handles = []
    for group in groups:
        workers = getattr(group, 'workers', None) or list(group.values())
        handles += [w.process for w in workers if getattr(w, 'process', None) is not None]
    return handles


def run_case(identifier, mode, project_path=None, duration_s=0., dt_s=1.):
    from engineering_cases import build_case, imported_case
    from engineering_checks import AcceptedLedger, Checks, check_frame
    from profile_module_system import rss
    from fn_engine import solver as s
    from fn_engine.compiler import compile_project
    from fn_engine.sessions import create_session

    started = time.perf_counter()
    case = imported_case(Path(project_path), duration_s, dt_s) if project_path else build_case(identifier)
    case.project.solver.module_cache, case.project.solver.module_mixed_jacobian = MODES[mode]
    at = time.perf_counter(); network = compile_project(case.project); compile_s = time.perf_counter() - at
    checks, totals, solve = Checks(), dict.fromkeys(COUNTER_KEYS, 0), s.solve_network
    solves = [0]

    def counted(*args, **kwargs):
        result = solve(*args, **kwargs)
        solves[0] += 1
        for key, value in ((getattr(result.hydraulic, 'counters', None) or {}).items()):
            if key in totals:
                totals[key] += value
        return result
    s.solve_network = counted
    groups, processes, peak, stop = [], [], [rss(os.getpid())], threading.Event()

    def memory():
        while not stop.wait(.025):
            live = [p for p in processes if p.poll() is None]
            peak[0] = max(peak[0], rss(os.getpid()) + sum(rss(p.pid) for p in live))
    sampler = threading.Thread(target=memory, daemon=True); sampler.start()
    ledger, frames = None, []
    try:
        at = time.perf_counter()
        if case.kind == 'steady':
            runners = s._python_runners(network); groups.append(runners)
            processes += worker_processes(runners)
            initialize_s = time.perf_counter() - at; at = time.perf_counter()
            frames.append(s.snapshot(network, s.solve_network(network, runners)))
        else:
            session = create_session(network, case.duration_s, case.dt_s)
            if getattr(network, 'execution_domain', 'fluid') == 'fluid':
                ledger, accept = AcceptedLedger(checks), session._accept

                def observed(h, *trial):
                    tanks = {node: state.mass_kg for node, state in session.tanks.items()}
                    states = {key: dict(getattr(runner, 'state', {}) or {}) for key, runner in session.runners.items()}
                    accept(h, *trial)
                    ledger.observe(session, h, tanks, states)
                session._accept = observed
            frames.append(session.advance())
            groups += [session.runners, session.scripts]
            processes += worker_processes(session.runners, session.scripts)
            initialize_s = time.perf_counter() - at; at = time.perf_counter()
            events = sorted(case.events, key=lambda event: event['time_s'])
            while not session.done:
                while events and events[0]['time_s'] <= session.time + 1e-9:
                    event = events.pop(0)
                    session.set_parameter(event['instance_id'], event['parameter_id'], event['value'])
                frames.append(session.advance())
        run_s = time.perf_counter() - at
        for frame in frames:
            check_frame(case, network, frame, checks)
    finally:
        s.solve_network = solve
        if case.kind == 'steady':
            for group in groups:
                s._close_runners(group)
        elif 'session' in locals():
            session.close()
        stop.set(); sampler.join(timeout=1)
    time.sleep(.2)
    leaked = sum(p.poll() is None for p in processes)
    python_modules = [m for m in network.modules.values() if m.runtime == 'python']
    return {'case': case.id, 'name': case.name, 'mode': mode, 'kind': case.kind, 'origin': case.origin,
            'domain': getattr(network, 'execution_domain', 'fluid'), 'sources': case.sources,
            'assumptions': case.assumptions, 'cache_enabled': MODES[mode][0], 'mixed_jacobian_enabled': MODES[mode][1],
            'pure_evaluate_modules': sorted(m.id for m in python_modules if m.pure_evaluate),
            'python_modules': sorted(m.id for m in python_modules),
            'compile_s': compile_s, 'initialize_s': initialize_s, 'run_s': run_s,
            'in_process_wall_s': time.perf_counter() - started, 'peak_tree_rss_bytes': peak[0],
            'workers_started': len(processes), 'workers_alive_after_close': leaked,
            'solves': solves[0], 'counters': totals, 'accepted_substeps': ledger.steps if ledger else None,
            'checks': checks.report(),
            'frames': [frame.model_dump(mode='json', include={'time_s', 'sequence', 'parameter_revision', 'valid',
                                                               'status', 'variables'}) for frame in frames]}


def summarize(rows):
    from engineering_checks import compare_frames
    summary = []
    for case in dict.fromkeys(row['case'] for row in rows):
        reference = next(r for r in rows if r['case'] == case and r['mode'] == 'baseline')
        base_run = statistics.median(r['run_s'] for r in rows if r['case'] == case and r['mode'] == 'baseline')
        for mode in dict.fromkeys(r['mode'] for r in rows if r['case'] == case):
            group = [r for r in rows if r['case'] == case and r['mode'] == mode]
            comparisons = [compare_frames(reference['frames'], r['frames']) for r in group if r is not reference]
            counters = group[0]['counters']
            run_s = statistics.median(r['run_s'] for r in group)
            summary.append({
                'case': case, 'mode': mode, 'repeats': len(group),
                'checks_passed': all(r['checks']['passed'] for r in group),
                'matches_baseline': all(c['passed'] for c in comparisons),
                'max_baseline_differences': {k: max(c['max_absolute_errors'].get(k, 0.) for c in comparisons)
                                             for k in ('variable_values',)} if comparisons else {},
                'median_process_wall_s': statistics.median(r['process_wall_s'] for r in group),
                'median_run_s': run_s, 'run_change_vs_baseline': run_s / base_run - 1 if base_run else None,
                'median_peak_tree_rss_mb': statistics.median(r['peak_tree_rss_bytes'] for r in group) / 2 ** 20,
                'workers_started': group[0]['workers_started'],
                'workers_alive_after_close': max(r['workers_alive_after_close'] for r in group),
                'solves': group[0]['solves'], 'rpc_batches': counters['rpc_batches'],
                'parent_cache_hits': counters['parent_cache_hits'], 'residual_calls': counters['residual_calls'],
                'cache_effective': counters['parent_cache_hits'] > 0,
                'pure_evaluate_modules': group[0]['pure_evaluate_modules']})
    return summary


def main():
    from engineering_cases import CASE_IDS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='新的 artifacts/engineering 子目录')
    parser.add_argument('--cases', nargs='+', default=list(CASE_IDS))
    parser.add_argument('--modes', nargs='+', choices=MODES, default=list(MODES))
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--project', help='导入的项目 JSON（替代内置案例）')
    parser.add_argument('--duration', type=float, default=0.)
    parser.add_argument('--dt', type=float, default=1.)
    parser.add_argument('--worker', nargs=2, metavar=('CASE', 'MODE'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(run_case(*args.worker, args.project, args.duration, args.dt), ensure_ascii=False, allow_nan=False))
        return
    target = Path(args.output or f'artifacts/engineering/{time.strftime("%Y%m%d-%H%M%S")}').resolve()
    if not target.is_relative_to((ROOT / 'artifacts/engineering').resolve()) or target.exists():
        raise ValueError('验收证据必须写入新的 artifacts/engineering 目录')
    target.mkdir(parents=True)
    cases = ['imported-project'] if args.project else args.cases
    modes = ['baseline'] + [m for m in args.modes if m != 'baseline']
    rows = []
    for case in cases:
        for repeat in range(args.repeats):
            for mode in modes:  # interleaved so drift affects every mode alike
                command = [sys.executable, __file__, '--worker', case, mode, '--duration', str(args.duration), '--dt', str(args.dt)]
                if args.project:
                    command += ['--project', str(Path(args.project).resolve())]
                at = time.perf_counter()
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                if result.returncode:
                    raise RuntimeError(f'{case}/{mode} 失败：\n{result.stderr}')
                row = json.loads(result.stdout); row['process_wall_s'] = time.perf_counter() - at; row['repeat'] = repeat
                (target / f'{case}-{mode}-{repeat}.json').write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding='utf-8')
                rows.append(row)
                print(json.dumps({'case': case, 'mode': mode, 'repeat': repeat, 'run_s': round(row['run_s'], 3),
                                  'checks': row['checks']['passed'], 'leaked': row['workers_alive_after_close']}), flush=True)
    summary = summarize(rows)
    report = {'environment': {'python': sys.version, 'platform': platform.platform(), 'blas_threads': 1},
              'protocol': {'repeats': args.repeats, 'modes': modes, 'fresh_process_per_run': True,
                           'reference': 'baseline repeat 0', 'origin': rows[0]['origin']},
              'summary': summary, 'passed': all(r['checks_passed'] and r['matches_baseline'] and
                                                not r['workers_alive_after_close'] for r in summary)}
    (target / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in summary:
        print(json.dumps({k: row[k] for k in ('case', 'mode', 'checks_passed', 'matches_baseline', 'median_run_s',
                                              'run_change_vs_baseline', 'cache_effective', 'workers_alive_after_close')},
                         ensure_ascii=False))
    print('PASSED' if report['passed'] else 'FAILED', target)


if __name__ == '__main__':
    main()
