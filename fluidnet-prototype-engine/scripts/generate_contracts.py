"""Regenerate contracts from the executable models. Run from the project root."""
import json
from pathlib import Path

from fn_engine.api import create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.models import ModuleDefinition, Project, RunRequest, RunFrame
from fn_engine.compiler import compile_project
from fn_engine.solver import solve_steady

root=Path(__file__).resolve().parents[1]
output=root/'contracts'

def write(name,data):
    (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

for name,model in [('module',ModuleDefinition),('project',Project),('run-request',RunRequest),('run-frame',RunFrame)]:
    schema=model.model_json_schema()
    schema['$schema']='https://json-schema.org/draft/2020-12/schema'
    write(name+'.schema.json',schema)
write('openapi.json',create_app().openapi())
raw=json.loads((root/'tests'/'fixtures'/'prototype.json').read_text(encoding='utf-8'))
project=normalize_prototype_export(raw)
write('reference-project.json',project.model_dump(mode='json'))
write('reference-result.json',solve_steady(compile_project(project)).model_dump(mode='json'))
print('Generated schemas, OpenAPI, reference project and result.')
