"""Regenerate contracts from the executable models. Run from the project root."""
import json
from pathlib import Path

from fn_engine.api import create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.models import (
    CommitStepRequest, CommitStepResponse, EvaluateRequest, EvaluateResponse,
    FluidConfig, ModuleDefinition, ModulePackageRef, ModuleTestRequest,
    ModuleTestResponse, NetworkRelation, PortState, Project, RunCreateResponse,
    RunEventsResponse, RunFrame, RunHistoryResponse, RunRequest, RunStatus,
    ErrorResponse, ValidationResponse,
    ModuleSaveRequest, ModuleVersionResponse, ModuleVersionsResponse,
    ModuleDesignRequest, ModuleDesignResponse,
    ProjectDocument, ProjectSaveRequest, ProjectRevisionRequest, ProjectDeleteRequest, ProjectUpgradeRequest,
)
from fn_engine.compiler import compile_project
from fn_engine.solver import solve_steady

root=Path(__file__).resolve().parents[1]
output=root/'contracts'

def write(name,data):
    (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

models = [
    ('module', ModuleDefinition), ('project', Project), ('run-request', RunRequest), ('run-frame', RunFrame),
    ('fluid-config', FluidConfig), ('module-package-ref', ModulePackageRef),
    ('port-state', PortState), ('network-relation', NetworkRelation),
    ('evaluate-request', EvaluateRequest), ('evaluate-response', EvaluateResponse),
    ('commit-step-request', CommitStepRequest), ('commit-step-response', CommitStepResponse),
    ('module-test-request', ModuleTestRequest), ('module-test-response', ModuleTestResponse),
    ('module-save-request', ModuleSaveRequest), ('module-version-response', ModuleVersionResponse),
    ('module-versions-response', ModuleVersionsResponse),
    ('module-design-request', ModuleDesignRequest), ('module-design-response', ModuleDesignResponse),
    ('project-document', ProjectDocument), ('project-save-request', ProjectSaveRequest),
    ('project-revision-request', ProjectRevisionRequest), ('project-delete-request', ProjectDeleteRequest),
    ('project-upgrade-request', ProjectUpgradeRequest),
    ('run-status', RunStatus), ('run-create-response', RunCreateResponse),
    ('run-history-response', RunHistoryResponse), ('run-events-response', RunEventsResponse),
    ('error-response', ErrorResponse), ('validation-response', ValidationResponse),
]
for name,model in models:
    schema=model.model_json_schema()
    schema['$schema']='https://json-schema.org/draft/2020-12/schema'
    write(name+'.schema.json',schema)
write('openapi.json',create_app().openapi())
raw=json.loads((root/'tests'/'fixtures'/'prototype.json').read_text(encoding='utf-8'))
project=normalize_prototype_export(raw)
write('reference-project.json',project.model_dump(mode='json'))
write('reference-result.json',solve_steady(compile_project(project)).model_dump(mode='json'))
print('Generated schemas, OpenAPI, reference project and result.')
