"""CI scope and gate behavior, without running the full suites they describe."""
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT.parent / '.github' / 'workflows'


def workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding='utf-8'))


def triggers(document):
    # PyYAML uses YAML 1.1; GitHub's YAML 1.2 treats the key "on" as text.
    return document.get('on', document.get(True))


def commands(job):
    return '\n'.join(step.get('run', '') for step in job['steps'])


def test_daily_ci_is_automatic_and_full_ci_requires_explicit_dispatch():
    quick, full = workflow('ci.yml'), workflow('ci-full.yml')
    assert set(triggers(quick)) == {'push', 'pull_request'}
    assert triggers(quick)['push']['branches'] == ['master']
    assert set(triggers(full)) == {'workflow_dispatch'}
    assert quick['concurrency']['cancel-in-progress'] is True
    assert full['concurrency']['cancel-in-progress'] is False


def test_daily_backend_uses_the_reviewed_plan_and_retains_static_and_contract_checks():
    jobs = workflow('ci.yml')['jobs']
    backend = jobs['backend']
    assert backend['needs'] == 'frontend-checks'
    assert 'strategy' not in backend
    steps = commands(backend)
    assert 'ci-quick.mjs --run-backend --plan artifacts/ci-quick-plan.json' in steps
    assert 'pytest' not in steps and '--cov=fn_engine' not in steps
    for check in ('ruff check', 'python -m mypy', 'mypy-session.ini', 'mypy-runner.ini',
                  'generated_artifacts.py --verify'):
        assert check in steps
    assert '--cov=fn_sdk' in commands(jobs['module-sdk'])


def test_quick_backend_and_browser_consume_the_same_uploaded_scope():
    jobs = workflow('ci.yml')['jobs']
    planning = jobs['frontend-checks']
    step = next(step for step in planning['steps'] if step.get('id') == 'quick-plan')
    assert 'pull_request.base.sha' in step['env']['IMPACT_BASE']
    assert 'pull_request.head.sha' in step['env']['IMPACT_HEAD']
    assert '--base $env:IMPACT_BASE --head $env:IMPACT_HEAD' in step['run']
    assert 'ci-quick.mjs --matrix --output artifacts/ci-quick-plan.json' in step['run']
    assert '--all' not in step['run']
    uploaded = next(step['with'] for step in planning['steps'] if step.get('uses', '').startswith('actions/upload-artifact@'))
    assert uploaded['name'] == 'ci-quick-plan'
    assert uploaded['if-no-files-found'] == 'error'
    for name in ('backend', 'browser'):
        downloaded = next(step['with'] for step in jobs[name]['steps'] if step.get('uses', '').startswith('actions/download-artifact@'))
        assert downloaded['name'] == uploaded['name']
        assert downloaded['path'] == 'fluidnet-prototype-engine/artifacts'
    browser = jobs['browser']
    assert 'ci-quick.mjs --run-browser --plan artifacts/ci-quick-plan.json --group' in commands(browser)
    assert '--ci' in commands(browser)
    assert 'browser-groups.mjs --run' not in commands(browser)
    assert browser['strategy']['max-parallel'] == 3
    assert 'needs.frontend-checks.outputs.matrix' in browser['strategy']['matrix']


def test_manual_ci_keeps_complete_coverage_cpu_variants_and_every_browser_group():
    jobs = workflow('ci-full.yml')['jobs']
    assert jobs['backend']['strategy']['matrix']['openblas'] == ['', 'Haswell']
    backend = commands(jobs['backend'])
    assert 'python -m pytest -q --cov=fn_engine --cov-report=term-missing --cov-report=xml:coverage.xml' in backend
    assert "@('Haswell', 'Sandybridge')" in backend
    assert 'generated_artifacts.py --verify' in backend
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    assert config['tool']['coverage']['report']['fail_under'] == 85
    assert 'browser-impact.mjs --all --matrix' in commands(jobs['frontend-checks'])
    assert 'browser-groups.mjs --run --group ${{ matrix.group }} --retries 1 --ci' in commands(jobs['browser'])
    assert jobs['frontend']['name'] != workflow('ci.yml')['jobs']['frontend']['name']


@pytest.mark.parametrize(('file', 'gate', 'dependencies'), [
    ('ci.yml', 'frontend', ['frontend-checks', 'browser']),
    ('ci.yml', 'quick-gate', ['module-sdk', 'backend', 'frontend']),
    ('ci-full.yml', 'frontend', ['frontend-checks', 'browser']),
])
def test_aggregate_gates_reject_failure_cancellation_and_skipped_jobs(file, gate, dependencies, tmp_path):
    job = workflow(file)['jobs'][gate]
    assert job['needs'] == dependencies and job['if'] == 'always()'
    step = job['steps'][0]
    assert set(step['env'].values()) == {'${{ needs.' + name + '.result }}' for name in dependencies}
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell is available on the Windows CI runner')
    # Execute the actual workflow gate against all dependency states in one process.
    # Catching throws inside the harness lets us distinguish rejection from a crash.
    lines = ["$ErrorActionPreference = 'Stop'", '$gate = {', step['run'], '}']
    keys = list(step['env'])
    cases = [dict.fromkeys(keys, 'success')]
    for key in keys:
        for status in ('failure', 'cancelled', 'skipped'):
            cases.append({**dict.fromkeys(keys, 'success'), key: status})
    for case in cases:
        lines.extend(f"$env:{key} = '{value}'" for key, value in case.items())
        lines.extend(['$accepted = $true', 'try { & $gate } catch { $accepted = $false }'])
        expected = '$true' if all(status == 'success' for status in case.values()) else '$false'
        lines.append(f'if ($accepted -ne {expected}) {{ throw "Gate accepted the wrong dependency state" }}')
    script = tmp_path / 'verify-gate.ps1'
    script.write_text('\n'.join(lines), encoding='utf-8')
    result = subprocess.run([pwsh, '-NoProfile', '-File', str(script)], capture_output=True, text=True,
                            encoding='utf-8', timeout=30,
                            env={**os.environ, 'GITHUB_STEP_SUMMARY': str(tmp_path / 'summary.md')})
    assert result.returncode == 0, result.stdout + result.stderr
