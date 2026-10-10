from __future__ import annotations

import uuid
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import __version__
from .bridge import PARAMETER_BINDINGS, normalize_prototype_export
from .catalog import builtin_catalog
from .compiler import CompilationError, compile_project, validate_project
from .models import Diagnostic, Project, RunFrame, RunRequest
from .solver import solve_dynamic, solve_steady


def apply_scenario(project, scenario_id):
    project = project.model_copy(deep=True)
    if not scenario_id:
        return project
    scenario = next((s for s in project.scenarios if s.id == scenario_id), None)
    if scenario is None:
        raise ValueError(f'工况不存在：{scenario_id}')
    instances = {i.id:i for i in project.instances}
    for id, overrides in scenario.overrides.items():
        if id not in instances:
            raise ValueError(f'工况引用不存在的实例：{id}')
        instances[id].parameters.update(overrides)
    return project


def diagnostic(error):
    return error.diagnostic if isinstance(error, CompilationError) else Diagnostic(code='SOLVER_ERROR',message=str(error))


def create_app(frontend_root: str | Path | None = None) -> FastAPI:
    app = FastAPI(title='FluidNet Prototype Engine',version=__version__)
    runs = OrderedDict()
    lock = Lock()

    @app.get('/api/v1/health')
    def health():
        return {'status':'ok','version':__version__,'solver':'declarative-fluid-v1','supported_domains':['fluid'],
                'capabilities':{'steady_hydraulics':True,'quasi_steady_series':True,'thermal':False,'tank_state':False,'user_code':False},
                'max_frames':2001,'run_retention':20}

    @app.get('/api/v1/catalog')
    def catalog():
        return {'modules':[m.model_dump(mode='json') for m in builtin_catalog()], 'prototype_parameter_bindings':PARAMETER_BINDINGS}

    @app.post('/api/v1/projects/validate')
    def validate(project: Project):
        items = validate_project(project)
        return {'valid':not any(d.severity == 'error' for d in items),'diagnostics':items}

    @app.post('/api/v1/prototype/normalize')
    def normalize(payload: dict):
        try:
            return normalize_prototype_export(payload)
        except (ValueError,KeyError,TypeError,AttributeError,IndexError) as error:
            raise HTTPException(422,detail=str(error)) from error

    @app.post('/api/v1/solve',response_model=RunFrame)
    def solve(project: Project):
        try:
            return solve_steady(compile_project(project))
        except ValueError as error:
            raise HTTPException(422,detail=diagnostic(error).model_dump()) from error

    @app.post('/api/v1/runs',status_code=201)
    def run(request: RunRequest):
        run_id = uuid.uuid4().hex
        try:
            project = apply_scenario(request.project,request.scenario_id)
            network = compile_project(project)
            history = [solve_steady(network)] if request.mode == 'steady' else solve_dynamic(network,request.duration_s,request.dt_s)
            selected = request.selected_variables if request.selected_variables is not None else project.selected_variables
            if selected:
                missing = set(selected) - history[0].variables.keys()
                if missing:
                    raise ValueError(f'未知观察变量：{sorted(missing)}')
                for frame in history:
                    frame.variables = {key:frame.variables[key] for key in selected}
            frame, status = history[-1], 'completed'
        except ValueError as error:
            history, status = [], 'failed'
            frame = RunFrame(status='failed',valid=False,time_s=0,diagnostics=[diagnostic(error)])
        record = {'id':run_id,'status':status,'mode':request.mode,'request':request.model_dump(mode='json'),
                  'frame':frame.model_dump(mode='json'),'history':[f.model_dump(mode='json') for f in history]}
        with lock:
            runs[run_id] = record
            while len(runs) > 20:
                runs.popitem(last=False)
        return {'run_id':run_id,'status':status,'frame':frame,'total_rows':len(history)}

    def get_run(run_id):
        with lock:
            record = runs.get(run_id)
        if record is None:
            raise HTTPException(404,detail='运行记录不存在或已过期；仅在内存保留最近 20 次运行')
        return record

    @app.get('/api/v1/runs/{run_id}')
    def run_status(run_id: str):
        record = get_run(run_id)
        return {key:value for key,value in record.items() if key != 'history'}

    @app.get('/api/v1/runs/{run_id}/history')
    def run_history(run_id: str, offset: int = Query(0,ge=0), limit: int = Query(2001,ge=1,le=2001)):
        history = get_run(run_id)['history']
        return {'rows':history[offset:offset+limit],'total_rows':len(history),'offset':offset}

    if frontend_root:
        app.mount('/',StaticFiles(directory=str(Path(frontend_root)),html=True),name='frontend')
    return app
