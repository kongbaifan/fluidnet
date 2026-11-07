"""Measure a fresh process per run, with or without an earlier readiness request.

This is an experiment, not a production pool. A worker is never leased twice.
Prestart time, request latency, repeated steps and resident memory are separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import psutil

from profile_worker_startup import ROOT, environment, probe_definition, probe_parameters, trial_port
from fn_engine.model_types.base import FluidConfig
from fn_engine.model_types.protocol import CommitStepRequest, EvaluateRequest
from fn_engine.runtime import WorkerProcess


def sample(kind: str, prestart: bool, index: int) -> dict:
    definition = probe_definition(kind)
    run_id = f'prestart-{kind}-{index}-{prestart}'
    worker = WorkerProcess(definition, probe_parameters(definition), FluidConfig(),
                           timeout_s=30, run_id=run_id, instance_id='probe')
    report: dict = {'kind': kind, 'prestart': prestart, 'index': index, 'prestart_s': 0.}
    try:
        if prestart:
            begin = time.perf_counter()
            ready = worker._request({'action': 'startup_report'})
            report['prestart_s'] = time.perf_counter() - begin
            report['ready'] = ready
            assert worker.state == {} and worker.state_revision == 0
        begin = time.perf_counter()
        worker.initialize()
        report['initialize_s'] = time.perf_counter() - begin
        assert worker.process is not None
        process = psutil.Process(worker.process.pid)
        report['pid'] = process.pid
        report['initialized_rss_bytes'] = process.memory_info().rss
        initial = json.loads(json.dumps(worker.state))
        report['initial_state'] = initial
        steps = []
        for step in range(3):
            begin = time.perf_counter()
            response = worker.evaluate(EvaluateRequest(run_id=run_id, instance_id='probe',
                time_s=step * .1, iteration_id=step, trial_ports=trial_port(definition),
                readonly_state=worker.state))
            evaluated = time.perf_counter()
            worker.commit_step(CommitStepRequest(run_id=run_id, instance_id='probe',
                                                time_s=(step + 1) * .1, dt_s=.1))
            steps.append({'evaluate_s': evaluated - begin, 'commit_s': time.perf_counter() - evaluated,
                          'rss_bytes': process.memory_info().rss,
                          'variables': response.variables, 'state': json.loads(json.dumps(worker.state))})
        report['steps'] = steps
        report['first_success_s'] = report['initialize_s'] + steps[0]['evaluate_s'] + steps[0]['commit_s']
        report['total_first_success_s'] = report['prestart_s'] + report['first_success_s']
        if kind == 'property':
            assert initial == {'calls': 0}
            assert [step['state']['calls'] for step in steps] == [1, 2, 3]
        report['rpc_count'] = worker.request_count
    finally:
        process = worker.process
        worker.close(force=True)
        report['exited'] = process is None or process.poll() is not None
    assert report['exited'], 'Worker did not exit'
    return report


def summarize(rows: list[dict]) -> list[dict]:
    summary = []
    for kind in ('module', 'property'):
        for prestart in (False, True):
            selected = [row for row in rows if row['kind'] == kind and row['prestart'] == prestart]
            item = {'kind': kind, 'prestart': prestart, 'samples': len(selected)}
            for key in ('prestart_s', 'initialize_s', 'first_success_s', 'total_first_success_s', 'initialized_rss_bytes'):
                item[key] = statistics.median(row[key] for row in selected)
            item['first_evaluate_s'] = statistics.median(row['steps'][0]['evaluate_s'] for row in selected)
            item['later_evaluate_s'] = statistics.median(step['evaluate_s'] for row in selected for step in row['steps'][1:])
            item['max_sampled_rss_bytes'] = max(step['rss_bytes'] for row in selected for step in row['steps'])
            summary.append(item)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', default='artifacts/architecture-completion/worker-prestart.json')
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    children = {p.pid for p in psutil.Process().children(recursive=True)}
    rows = []
    # Alternating order reduces simple warm-cache/order bias.
    for index in range(args.repeats):
        for kind in ('module', 'property'):
            for prestart in ((False, True) if index % 2 == 0 else (True, False)):
                row = sample(kind, prestart, index)
                rows.append(row)
                print(kind, prestart, round(row['first_success_s'], 4), flush=True)
    after = {p.pid for p in psutil.Process().children(recursive=True)}
    assert after <= children, f'Remaining child processes: {after - children}'
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [ROOT / 'backend/fn_engine/worker.py', ROOT / 'backend/fn_engine/runtime.py',
                        Path(__file__).resolve(), ROOT / 'scripts/profile_worker_startup.py']}
    for kind in ('module', 'property'):
        samples = [row for row in rows if row['kind'] == kind]
        expected = samples[0]
        for row in samples[1:]:
            assert row['initial_state'] == expected['initial_state']
            assert [(step['variables'], step['state']) for step in row['steps']] == [
                (step['variables'], step['state']) for step in expected['steps']]
    report = {'schema': 1, 'environment': environment(), 'source_hashes': hashes, 'rows': rows,
              'summary': summarize(rows), 'children_remaining': sorted(after - children),
              'scope': 'Fresh process for every run; prestart shifts imports earlier. No cross-run reuse, concurrent throughput or property-preload pool is implemented.'}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
