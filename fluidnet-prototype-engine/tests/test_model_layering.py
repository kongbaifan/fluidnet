"""The type split is structural: existing wire formats and import identities stay compatible."""
import ast
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from fn_engine import models
from fn_engine.model_types.base import Diagnostic, FluidConfig
from fn_engine.model_types.domain import Project
from fn_engine.model_types.protocol import CommitStepResponse, EvaluateResponse, InitializeRequest, ModuleExecutionInfo

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT/'tests/fixtures/model-layering.json').read_text(encoding='utf-8'))


def test_all_legacy_classes_keep_their_schema_and_import_identity():
    assert len(BASELINE['classes']) == 127
    for name, record in BASELINE['classes'].items():
        implementation = getattr(importlib.import_module('fn_engine.model_types.'+record['layer']), name)
        assert getattr(models, name) is implementation
        data = json.dumps(implementation.model_json_schema(), sort_keys=True,
                          separators=(',', ':'), ensure_ascii=False).encode()
        assert hashlib.sha256(data).hexdigest() == record['schema_sha256'], name
    assert len(models.__all__) == len(set(models.__all__))
    assert all(hasattr(models, name) for name in models.__all__)


def test_protocol_defaults_omissions_and_frozen_execution_identity_are_unchanged():
    request = InitializeRequest(run_id='run', instance_id='D1',
        package={'module_id':'device', 'version':'1.0.0', 'content_hash':'0'*64})
    assert set(request.model_dump()) == {'run_id','instance_id','package','parameters','fluid','port_fluids','initial_state'}
    assert request.fluid == FluidConfig()
    assert 'context' not in request.model_dump() and 'cache_enabled' not in request.model_dump()
    for response in (EvaluateResponse(), CommitStepResponse()):
        assert response.diagnostics == []
        assert response.model_validate_json(response.model_dump_json()) == response
    first, second = CommitStepResponse(), CommitStepResponse()
    first.state['counter'] = 1
    assert second.state == {}
    info = ModuleExecutionInfo(instance_id='D1')
    with pytest.raises(ValidationError):
        info.instance_id = 'changed'
    with pytest.raises(ValidationError):
        Diagnostic(code='error', message='bad', unknown=True)
    assert Diagnostic(code='error', message='bad').model_dump() == {
        'code':'error','message':'bad','severity':'error','instance_id':None,'field':None}


def test_domain_keeps_validation_and_optional_field_omission():
    project = Project(id='empty', name='empty')
    exported = project.model_dump(mode='json')
    assert 'thermal_couplings' not in exported and 'measurements' not in exported and 'coupling_mode' not in exported
    assert Project.model_validate(exported) == project
    with pytest.raises(ValidationError):
        Project(id='bad', name='bad', unexpected='field')
    with pytest.raises(ValidationError):
        Project(id='bad', name='bad', instances=[{'id':'D1','name':'device','module_id':'missing'}])


@pytest.mark.parametrize('target', ['fn_engine.model_types.protocol','fn_engine.runtime','fn_engine.worker'])
def test_worker_imports_do_not_load_the_http_or_project_layer(target):
    code = f"""import importlib, json, sys
importlib.import_module({target!r})
print(json.dumps([name for name in sys.modules if name in (
    'fn_engine.models','fn_engine.model_types.http','fn_engine.model_types.domain','fn_engine.api')]))
"""
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_layers_and_engine_imports_cannot_reintroduce_the_compatibility_aggregator():
    allowed = {
        'base': set(), 'module': {'base'}, 'protocol': {'base','module'},
        'domain': {'base','module'}, 'run': {'base','domain'},
        'module_testing': {'base','module','protocol','domain','run'},
        'http': {'base','module','protocol','domain','run','module_testing'},
    }
    for path in (ROOT/'backend/fn_engine').rglob('*.py'):
        if path.name == 'models.py':
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.ImportFrom):
                assert node.module != 'fn_engine.models' and not (node.module == 'models' and node.level), path
                if path.parent.name == 'model_types' and node.level == 1:
                    assert node.module in allowed[path.stem], (path, node.module)


def test_historical_pickles_resolve_through_the_compatibility_facade():
    import pickle
    # GLOBAL refers to the old class location; no serialized user code is executed.
    for name in BASELINE['classes']:
        assert pickle.loads(f'cfn_engine.models\n{name}\n.'.encode()) is getattr(models, name)
