"""MOD-B0/B1: replay, physical references, real Worker failures and storage isolation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import module_baseline as baseline
import benchmark_modules as benchmark
from module_cases import CASES, build_case


def test_baseline_captures_replayable_supplement_without_user_storage(tmp_path, monkeypatch):
    user_data = tmp_path / 'user-data'
    user_data.mkdir()
    sentinel = user_data / 'sentinel.txt'
    sentinel.write_text('untouched', encoding='utf-8')
    monkeypatch.setenv('FLUIDNET_DATA_DIR', str(user_data))
    monkeypatch.setenv('FLUIDNET_MODULE_STORE', str(user_data))
    output = tmp_path / 'baseline'
    report = baseline.capture(output)
    assert report['commit'] == baseline.git('rev-parse', 'HEAD').decode().strip()
    assert len(report['modules']) >= 10
    assert any(row['id'] == 'programmable_valve' for row in report['modules'])
    assert report['environment']['http_api']['endpoints']
    assert 'valve' in report['environment']['legacy_runtime_api']['NetworkBuilder']
    assert hashlib.sha256((output / 'workspace.patch').read_bytes()).hexdigest() == report['tracked_patch_sha256']
    for overlay in report['untracked_overlays']:
        assert hashlib.sha256((output / 'overlay' / overlay['path']).read_bytes()).hexdigest() == overlay['sha256']
    assert {p.name for p in user_data.iterdir()} == {'sentinel.txt'}
    assert sentinel.read_text(encoding='utf-8') == 'untouched'
    with pytest.raises(FileExistsError):
        baseline.capture(output)
    # Exercise the full commit + patch + overlay protocol in a separate checkout.
    repo = baseline.git('rev-parse', '--show-toplevel').decode().strip()
    checkout = tmp_path / 'checkout'
    subprocess.run(['git', 'clone', '--shared', '--no-checkout', repo, str(checkout)], check=True,
                   capture_output=True, timeout=60)
    subprocess.run(['git', '-C', str(checkout), 'checkout', '--detach', report['commit']], check=True,
                   capture_output=True, timeout=60)
    if (output / 'workspace.patch').stat().st_size:
        subprocess.run(['git', '-C', str(checkout), 'apply', '--binary', str(output / 'workspace.patch')],
                       check=True, capture_output=True, timeout=30)
    for overlay in report['untracked_overlays']:
        target = checkout / overlay['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output / 'overlay' / overlay['path'], target)
    proof = baseline.verify_sources(report, checkout)
    assert proof['source_files_verified'] > 0
    # A real source edit must fail even when checkout line endings are tolerated.
    changed = checkout / next(row['path'] for row in report['source_files'] if row['path'].endswith('solver.py'))
    changed.write_bytes(changed.read_bytes() + b'\n# changed after baseline\n')
    with pytest.raises(ValueError, match='哈希不一致'):
        baseline.verify_sources(report, checkout)


@pytest.mark.parametrize('directory', ['.runtime', 'modules', 'tests'])
def test_in_repository_output_cannot_touch_user_data_or_sources(directory):
    with pytest.raises(ValueError):
        baseline.output_directory(ROOT / directory / 'module-baseline-forbidden')


@pytest.mark.parametrize('case', CASES)
def test_module_baseline_cases_use_real_workers_and_accepted_ledgers(case):
    result = benchmark.run_case(case)
    assert result['status'] == 'passed', result['checks']
    if case == 'worker-failure':
        assert result['counts']['accepted_frames'] == 0
        assert any(r['status'] == 'failed' for r in result['rpc_trace'])
        assert result['checks'][-1]['workers_observed'] > 0
    elif case != 'dual-thermal':
        assert result['counts']['module_evaluation_requests'] > 0
        assert all(len(m['definition_hash']) == len(m['content_hash']) == 64 for m in result['modules'])


def test_fault_case_does_not_accept_an_unrelated_error_or_success(monkeypatch):
    success = benchmark.run_case('worker-failure', project=build_case('single-valve'))
    assert success['status'] == 'failed'
    unrelated = build_case('worker-failure')
    unrelated.modules[-1].source['runtime'] = unrelated.modules[-1].source['runtime'].replace(
        'MOD_B1_INJECTED_FAILURE', 'ANOTHER_FAILURE')
    result = benchmark.run_case('worker-failure', project=unrelated)
    assert result['status'] == 'failed'
    original_close = benchmark.SimulationSession.close
    closes = 0

    def faulty_close(session):
        nonlocal closes
        original_close(session)
        closes += 1
        if closes > 1:
            raise RuntimeError('injected cleanup failure')

    monkeypatch.setattr(benchmark.SimulationSession, 'close', faulty_close)
    cleanup = benchmark.run_case('worker-failure')
    assert cleanup['status'] == 'failed'
    assert not next(c for c in cleanup['checks'] if c['id'] == 'lifecycle_cleanup')['passed']


def test_batched_shards_and_unbatched_have_equal_results_and_distinct_rpc_counts():
    results = [benchmark.run_case('multi-instance', batch=batch, workers=workers)
               for batch, workers in ((False, 1), (True, 1), (True, 2))]
    for result in results:
        assert result['status'] == 'passed', result['checks']
        assert result['counts']['module_evaluation_requests'] > 0
        for instance in ('N0', 'N1', 'N2', 'N3'):
            for suffix in ('main.mass_flow_kg_s', 'state.throughput_kg', 'state.commit_count'):
                key = f'{instance}.{suffix}'
                assert result['frames'][-1]['variables'][key] == pytest.approx(
                    results[0]['frames'][-1]['variables'][key], rel=1e-6, abs=1e-8)
    assert results[1]['counts']['rpc_requests'] < results[0]['counts']['rpc_requests']
    assert results[1]['counts']['actions']['batch'] > 0
    assert results[2]['checks'][-1]['workers_observed'] == 2


def test_cli_replays_exact_project_instead_of_rebuilding_catalog(tmp_path):
    project = build_case('single-valve')
    next(i for i in project.instances if i.id == 'D1').parameters['kv_m3_h'] = 32.
    case_dir = tmp_path / 'input' / 'single-valve'
    case_dir.mkdir(parents=True)
    snapshot = case_dir / 'project.json'
    snapshot.write_text(project.model_dump_json(), encoding='utf-8')
    user_dir = tmp_path / 'user'
    user_dir.mkdir()
    sentinel = user_dir / 'keep.json'
    sentinel.write_text('{}', encoding='utf-8')
    output = tmp_path / 'replayed'
    process = subprocess.run([sys.executable, str(ROOT / 'scripts/benchmark_modules.py'),
                              '--replay', str(snapshot), '--output', str(output)],
                             cwd=tmp_path, capture_output=True, text=True, timeout=60,
                             env={**os.environ, 'FLUIDNET_DATA_DIR': str(user_dir),
                                  'FLUIDNET_MODULE_STORE': str(user_dir)})
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads((output / 'single-valve/result.json').read_text(encoding='utf-8'))
    reference = next(c for c in result['checks'] if c['id'] == 'independent_kv')
    assert reference['value'] == pytest.approx(8.100919039, rel=1e-6)
    assert list(user_dir.iterdir()) == [sentinel]
