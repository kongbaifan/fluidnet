"""Review summaries must catch meaningful changes without dumping frozen module source."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('generated_artifacts', ROOT / 'scripts/generated_artifacts.py')
assert SPEC and SPEC.loader
reviewer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reviewer)


def test_semantic_summary_ignores_key_order_but_not_booleans_or_removed_fields():
    assert reviewer.semantic_changes({'a': 1, 'b': [2]}, {'b': [2.0], 'a': 1.0})['change_count'] == 0
    result = reviewer.semantic_changes({'a': True, 'b': None}, {'a': 1, 'c': None})
    assert result['changes'] == [
        {'path': '/a', 'kind': 'changed'}, {'path': '/b', 'kind': 'removed'}, {'path': '/c', 'kind': 'added'}]


def test_summary_limits_output_without_losing_total_or_source_change():
    result = reviewer.semantic_changes({'a/b': {'~': 0}, 'source': 'old'}, {'a/b': {'~': 1}, 'source': 'private code'}, 1)
    assert result == {'change_count': 2, 'changes': [{'path': '/a~1b/~0', 'kind': 'changed'}], 'truncated': True}
    assert 'private code' not in json.dumps(result)
    assert reviewer.semantic_changes([1, 2], [1])['changes'] == [{'path': '/1', 'kind': 'removed'}]


def test_registration_covers_all_read_only_generators():
    entries = reviewer.load_manifest()
    assert len(entries) == 14
    assert {'contracts', 'hydronic-buffer', 'open-refrigeration'} <= {entry['id'] for entry in entries}


@pytest.mark.parametrize(('generator', 'builder', 'examples'), [
    ('generate_hvac_expansion', 'hvac_expansion_examples', 'hvac-expansion'),
    ('generate_design_groups', 'equipment_library', 'equipment-library'),
])
def test_portable_generator_checks_survive_checkout_relocation(tmp_path, monkeypatch, generator, builder, examples):
    """Use a different checkout root, as on CI, with the real frozen module files."""
    relocated = tmp_path / 'another checkout'
    shutil.copytree(ROOT / 'modules', relocated / 'modules')
    shutil.copytree(ROOT / 'examples' / examples, relocated / 'examples' / examples)
    spec = importlib.util.spec_from_file_location(generator, ROOT / 'scripts' / (generator + '.py'))
    assert spec and spec.loader
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(script, 'ROOT', relocated)
    monkeypatch.setattr(importlib.import_module('fn_engine.' + builder), 'ROOT', relocated)
    monkeypatch.setattr(sys, 'argv', [generator, '--check'])
    files = [path for path in relocated.rglob('*') if path.is_file()]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
    script.main()
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files} == before
    for path in (relocated / 'examples' / examples).glob('*.project.json'):
        project = json.loads(path.read_text(encoding='utf-8'))
        assert all(module.get('package_path') is None for module in project['modules']), path


@pytest.mark.parametrize('problem', ['duplicate', 'escape', 'unregistered', 'missing-output'])
def test_manifest_rejects_broken_registrations(tmp_path, problem):
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'contracts').mkdir()
    (tmp_path / 'scripts/generate_one.py').write_text('# --check', encoding='utf-8')
    (tmp_path / 'contracts/one.json').write_text('{}', encoding='utf-8')
    entry = {'id': 'one', 'script': 'scripts/generate_one.py', 'outputs': ['contracts/*.json']}
    entries = [entry]
    if problem == 'duplicate':
        entries.append(entry.copy())
    elif problem == 'escape':
        entry['outputs'] = ['../contracts/*.json']
    elif problem == 'unregistered':
        (tmp_path / 'scripts/generate_two.py').write_text('# --check', encoding='utf-8')
    else:
        entry['outputs'] = ['missing/*.json']
    (tmp_path / 'scripts/generated-artifacts.json').write_text(json.dumps({'version': 1, 'generators': entries}), encoding='utf-8')
    with pytest.raises(ValueError):
        reviewer.load_manifest(tmp_path)


def test_git_review_includes_staged_unstaged_untracked_and_deleted_without_writing(tmp_path):
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_path), *args], check=True, capture_output=True)

    git('init')
    project = tmp_path / 'nested project'
    artifacts = project / 'contracts'
    artifacts.mkdir(parents=True)
    for name in ['changed', 'deleted', 'format']:
        (artifacts / (name + '.json')).write_text('{"value":1}', encoding='utf-8')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'baseline')
    (artifacts / 'changed.json').write_text('{"value":2}', encoding='utf-8')
    git('add', '.')
    (artifacts / 'deleted.json').unlink()
    (artifacts / 'format.json').write_text('{\n  "value": 1\n}\n', encoding='utf-8')
    (artifacts / 'new.json').write_text('{"source":"sensitive code"}', encoding='utf-8')
    before = git('status', '--porcelain=v1').stdout
    result = reviewer.review(project, [{'id': 'contracts', 'outputs': ['contracts/*.json']}])
    assert git('status', '--porcelain=v1').stdout == before
    assert result['file_count'] == 4
    files = {item['path']: item for item in result['files']}
    assert files['contracts/changed.json']['change_count'] == 1
    assert files['contracts/deleted.json']['status'] == 'deleted'
    assert files['contracts/new.json']['status'] == 'added'
    assert files['contracts/format.json']['change_count'] == 0
    assert 'sensitive code' not in json.dumps(result)
    (artifacts / 'new.json').write_text('{invalid', encoding='utf-8')
    assert any('error' in item for item in reviewer.review(project, [{'id': 'contracts', 'outputs': ['contracts/*.json']}])['files'])
    with pytest.raises(ValueError):
        reviewer.review(project, [], '--not-a-ref')
