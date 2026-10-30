from pathlib import Path

import pytest

from fn_engine.air_examples import air_example
from fn_engine.migrations import preview_air_migration
from fn_engine.packages import load_module_package


def test_migration_is_explicit_and_does_not_mutate_input():
    project=air_example('ahu-wet')
    project.solver.moist_air_options=None
    project.solver.property_coupling='reference'
    old=load_module_package(Path(__file__).resolve().parents[1]/'modules/fan/history/v1')
    project.modules=[old if m.id=='fan' else m for m in project.modules]
    before=project.model_dump(mode='json')
    without=preview_air_migration(project)
    assert not without['valid']
    preview=preview_air_migration(project,True)
    assert preview['valid'],preview['diagnostics']
    assert project.model_dump(mode='json')==before
    assert preview['original_project'].model_dump(mode='json')==before
    assert preview['project'].solver.moist_air_options.contract_version==1
    assert next(m for m in preview['project'].modules if m.id=='fan').version==2


def test_unknown_module_source_is_not_silently_upgraded():
    project=air_example('ahu-wet');project.solver.moist_air_options=None
    old=load_module_package(Path(__file__).resolve().parents[1]/'modules/fan/history/v1')
    old.source['runtime']+='\n# 用户修改\n';old.content_hash=None;old.definition_hash=None
    project.modules=[old if m.id=='fan' else m for m in project.modules]
    preview=preview_air_migration(project,True)
    assert not preview['valid']
    assert next(m for m in preview['project'].modules if m.id=='fan').source==old.source
    dry=air_example('cooling-tower-moist')
    with pytest.raises(ValueError):
        preview_air_migration(dry)
