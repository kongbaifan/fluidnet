import json
from pathlib import Path

from fn_engine.bridge import normalize_prototype_export
from fn_engine.models import Project, SolverOptions

FIXTURE = Path('tests') / 'fixtures' / 'prototype.json'


def _export():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def test_legacy_snapshot_without_field_stays_dense():
    project = Project(id='legacy', name='legacy')
    assert project.solver.hydraulic_method == 'dense'
    payload = json.loads(project.model_dump_json())
    payload['solver'].pop('hydraulic_method', None)
    restored = Project.model_validate(payload)
    assert restored.solver.hydraulic_method == 'dense'


def test_export_without_hydraulic_method_imports_as_dense():
    raw = _export()
    if isinstance(raw, dict) and 'activeProject' in raw:
        raw['activeProject'] = None
    project = normalize_prototype_export(raw)
    assert project.solver.hydraulic_method == 'dense'


def test_export_with_auto_keeps_auto_after_save_and_restart():
    raw = _export()
    if isinstance(raw, dict) and 'activeProject' in raw:
        raw['activeProject'] = None
    raw['activeProject'] = raw['projects'][0]['id']
    for project in raw['projects']:
        project.setdefault('solver', {})['hydraulicMethod'] = 'auto'
    project = normalize_prototype_export(raw)
    assert project.solver.hydraulic_method == 'auto'
    again = Project.model_validate(json.loads(project.model_dump_json()))
    assert again.solver.hydraulic_method == 'auto'
    assert SolverOptions.model_validate({'hydraulic_method': 'auto'}).hydraulic_method == 'auto'
