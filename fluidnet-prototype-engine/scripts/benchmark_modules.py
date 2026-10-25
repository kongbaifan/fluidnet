"""MOD-B1: isolated module replay with exact RPC traces and accepted-state ledgers.

This is a correctness baseline, not the MOD-P0 cold-5/hot-7 performance protocol.
Each case exports the complete Project, frames, worker request/response trace and hashes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

if __name__ == '__main__':
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = '1'

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

from module_baseline import digest, environment, git, json_bytes, now, output_directory
from module_cases import CASES, build_case
from fn_engine.compiler import compile_project
from fn_engine.runtime import WorkerProcess, module_content_hash, module_definition_hash
from fn_engine.simulation import SimulationSession


def check(name, passed, **evidence):
    return {'id': name, 'passed': bool(passed), **evidence}


def verify_frames(project, frames):
    checks = [check('accepted_frames', len(frames) == 3, count=len(frames))]
    if not frames:
        return checks
    checks.extend([
        check('pressure_residual', all(f.metrics['pressure_residual_pa'] <= project.solver.pressure_tolerance_pa
                                       for f in frames)),
        check('mass_residual', all(f.metrics['mass_residual_kg_s'] <= project.solver.mass_tolerance_kg_s
                                   for f in frames)),
        check('valid_frames', all(f.valid and not any(d.severity == 'error' for d in f.diagnostics) for f in frames)),
        check('finite_variables', all(not isinstance(v, (int, float)) or math.isfinite(v)
                                     for f in frames for v in f.variables.values())),
    ])
    for instance in project.instances:
        definition = next(m for m in project.modules if m.id == instance.module_id)
        if definition.runtime != 'python':
            continue
        prefix = instance.id
        final = frames[-1].variables
        count = final.get(f'{prefix}.state.commit_count')
        if count is not None:
            checks.append(check(f'{prefix}.commit_count', count == 2, value=count, reference=2))
        mass = final.get(f'{prefix}.state.throughput_kg')
        if mass is not None:
            expected = sum((f.time_s - previous.time_s) * sum(
                abs(f.variables[f'{prefix}.{channel.id}.mass_flow_kg_s'])
                for channel in definition.channels if channel.enabled)
                for previous, f in zip(frames, frames[1:]))
            checks.append(check(f'{prefix}.throughput_ledger', math.isclose(mass, expected, abs_tol=1e-8, rel_tol=1e-8),
                                value=mass, reference=expected))
    return checks


def run_case(name, *, project=None, batch=True, workers=1):
    project = project if project is not None else build_case(name, batch=batch, workers=workers)
    inputs = project.model_dump(mode='json')
    trace, processes, worker_ids = [], {}, {}
    original = WorkerProcess._request
    original_start = WorkerProcess._ensure_process

    def start(worker):
        try:
            return original_start(worker)
        finally:
            if worker.process is not None:
                processes[worker.process.pid] = worker.process
                worker_ids[id(worker)] = worker.process.pid

    def request(worker, payload):
        begin = time.perf_counter()
        row = {'request': deepcopy(payload), 'status': 'running'}
        trace.append(row)
        try:
            response = original(worker, payload)
            row.update(status='passed', response=deepcopy(response))
            return response
        except Exception as error:
            row.update(status='failed', error=f'{type(error).__name__}: {error}'[:4000])
            raise
        finally:
            row['elapsed_s'] = time.perf_counter() - begin
            row['worker_pid'] = worker_ids.get(id(worker))

    session, failure, frames, checks, compile_s, cleanup_failure = None, None, [], [], None, None
    begin = time.perf_counter()
    with TemporaryDirectory(prefix='fluidnet-module-baseline-') as temp, patch.dict(os.environ, {
        'FLUIDNET_DATA_DIR': str(Path(temp) / 'workspace'),
        'FLUIDNET_MODULE_STORE': str(Path(temp) / 'modules'),
    }), patch.object(WorkerProcess, '_request', request), patch.object(WorkerProcess, '_ensure_process', start):
        try:
            compiled_at = time.perf_counter()
            network = compile_project(project)
            compile_s = time.perf_counter() - compiled_at
            session = SimulationSession(network, 1.0, .5)
            while not session.done:
                session.advance()
        except Exception as error:
            failure = f'{type(error).__name__}: {error}'[:4000]
        finally:
            if session is not None:
                frames = list(session.frames)
                try:
                    session.close()
                except Exception as error:
                    cleanup_failure = f'{type(error).__name__}: {error}'[:4000]
                    failure = f'{failure or ""}; cleanup: {type(error).__name__}: {error}'[:4000]
    if name == 'worker-failure':
        checks = [check('real_worker_failure', failure is not None and 'MOD_B1_INJECTED_FAILURE' in failure,
                        error=failure), check('no_accepted_failure_frame', not frames, count=len(frames))]
    elif failure is None:
        checks = verify_frames(project, frames)
        if name == 'single-valve':
            # Independent Kv equation; density is the module's recorded physical input, not a flow fit.
            params = network.parameters['D1']
            rho = frames[-1].variables['D1.density_kg_m3']
            delta_p = network.parameters['B1']['pressure_pa'] - network.parameters['B2']['pressure_pa']
            expected = rho / 3600 * params['kv_m3_h'] * params['opening_ratio'] * math.copysign(
                math.sqrt(abs(delta_p) / (1e5 * rho / 1000)), delta_p)
            actual = frames[-1].variables['D1.main.mass_flow_kg_s']
            checks.append(check('independent_kv', math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-8),
                                value=actual, reference=expected, density_kg_m3=rho))
    else:
        checks = [check('unexpected_failure', False, error=failure)]
    checks.append(check('lifecycle_cleanup', cleanup_failure is None, error=cleanup_failure))
    checks.append(check('worker_cleanup', all(p.poll() is not None for p in processes.values()),
                        workers_observed=len(processes)))
    actions = Counter(row['request']['action'] for row in trace)
    evaluations = sum(len(row['request']['items']) if row['request']['action'] == 'batch' else
                      int(row['request']['action'] == 'evaluate') for row in trace)
    modules = [{'id': m.id, 'version': m.version, 'content_hash': module_content_hash(m),
                'definition_hash': module_definition_hash(m)} for m in project.modules if m.runtime == 'python']
    return {'id': name, 'status': 'passed' if all(c['passed'] for c in checks) else 'failed',
            'project': inputs, 'input_sha256': digest(json_bytes(inputs)), 'modules': modules,
            'checks': checks, 'failure': failure,
            'timings': {'end_to_end_s': time.perf_counter() - begin, 'compile_s': compile_s,
                        'worker_rpc_sum_s': sum(row['elapsed_s'] for row in trace)},
            'counts': {'rpc_requests': len(trace), 'actions': dict(actions), 'module_evaluation_requests': evaluations,
                       'accepted_frames': len(frames)},
            'frames': [f.model_dump(mode='json') for f in frames], 'rpc_trace': trace}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'artifacts/module-system' /
        git('rev-parse', '--short', 'HEAD').decode().strip() / 'MOD-B1'))
    parser.add_argument('--cases', default=','.join(CASES))
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--no-batch', action='store_true')
    parser.add_argument('--replay', type=Path, help='project.json from a previous case; no catalog upgrade')
    args = parser.parse_args(argv)
    names = args.cases.split(',')
    if not args.replay and any(name not in CASES for name in names):
        parser.error('unknown case')
    if args.workers < 1:
        parser.error('--workers must be positive')
    output = output_directory(args.output)
    report = {'format_version': 1, 'work_package': 'MOD-B1', 'generated_at': now(),
              'commit': git('rev-parse', 'HEAD').decode().strip(), 'environment': environment(),
              'protocol': 'one correctness replay per case; no speedup or percentile claim',
              'timing_note': 'RPC sum overlaps solver time; close/finalize pipe writes are not _request RPCs',
              'cases': []}
    if args.replay:
        from fn_engine.models import Project
        payload = json.loads(args.replay.read_text(encoding='utf-8'))
        project = Project.model_validate(payload)
        names = [args.replay.parent.name]
    else:
        project = None
    for name in names:
        result = run_case(name, project=project, batch=not args.no_batch, workers=args.workers)
        directory = output / name
        directory.mkdir(parents=True, exist_ok=True)
        for filename, data in [('project.json', result['project']), ('result.json', result)]:
            (directory / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                                             encoding='utf-8')
        report['cases'].append({k: v for k, v in result.items() if k not in {'project', 'frames', 'rpc_trace'}})
        print(json.dumps({'id': name, 'status': result['status'], 'counts': result['counts']}, ensure_ascii=False), flush=True)
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                                       encoding='utf-8')
    return int(any(case['status'] != 'passed' for case in report['cases']))


if __name__ == '__main__':
    raise SystemExit(main())
