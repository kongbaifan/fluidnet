from __future__ import annotations

import uuid
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .bridge import PARAMETER_BINDINGS, normalize_prototype_export
from .catalog import builtin_catalog
from .compiler import CompilationError, compile_project, validate_project
from .models import (
    CatalogResponse,
    Diagnostic,
    ModuleDefinition,
    ModuleTestRequest,
    ModuleTestResponse,
    ModuleCatalogResponse,
    Project,
    RunFrame,
    RunRequest,
    RunStatus,
    RunRecordResponse,
    RunCreateResponse,
    RunEventsResponse,
    RunEvent,
    RunHistoryResponse,
    ValidationResponse,
    ModuleSaveRequest,
    ModuleVersionResponse,
    ModuleVersionsResponse,
)
from .properties import PropertyError
from .packages import ModuleStore, ModuleVersionConflict, ModuleSaveInvalid, package_ref
from .module_validation import validate_module_definition
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
    if isinstance(error, CompilationError):
        return error.diagnostic
    if isinstance(error, PropertyError):
        return Diagnostic(code=error.code, message=str(error))
    return Diagnostic(code=getattr(error, 'code', 'SOLVER_ERROR'), message=str(error))


def create_app(frontend_root: str | Path | None = None, module_storage_root: str | Path | None = None) -> FastAPI:
    app = FastAPI(title='FluidNet Prototype Engine',version=__version__)
    runs = OrderedDict()
    lock = Lock()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='fluidnet-run')
    project_root = Path(__file__).resolve().parents[2]
    store = ModuleStore(project_root / 'modules', Path(module_storage_root or os.environ.get('FLUIDNET_MODULE_STORE') or project_root / '.runtime' / 'module-packages'))

    @app.get('/api/v1/health')
    def health():
        return {'status':'ok','version':__version__,'solver':'declarative-fluid-v1','supported_domains':['fluid'],
                'capabilities':{'steady_hydraulics':True,'quasi_steady_series':True,'thermal':False,'tank_state':False,
                                'coolprop_single_phase':True,'user_code':True,'worker_process':True,'async_runs':True,'module_versions':True},
                'max_frames':2001,'run_retention':20}

    @app.get('/api/v1/catalog', response_model=CatalogResponse)
    def catalog():
        return {'modules':builtin_catalog(), 'prototype_parameter_bindings':PARAMETER_BINDINGS}

    @app.get('/api/v1/modules', response_model=ModuleCatalogResponse)
    def modules():
        items = []
        definitions = builtin_catalog() + store.latest()
        for definition in definitions:
            payload = definition.model_dump(mode='json')
            payload['package'] = package_ref(definition) if definition.runtime == 'python' else None
            items.append(payload)
        return {'modules': items}

    @app.post('/api/v1/modules/validate', response_model=ValidationResponse)
    def validate_module(module: ModuleDefinition):
        return validate_module_definition(module)

    @app.get('/api/v1/modules/{module_id}/versions', response_model=ModuleVersionsResponse)
    def module_versions(module_id: str):
        return {'versions': store.versions(module_id)}

    @app.get('/api/v1/modules/{module_id}/versions/{version}', response_model=ModuleVersionResponse)
    def module_version(module_id: str, version: int):
        try:
            return store.get(module_id, version)
        except KeyError as error:
            raise HTTPException(404, detail='模块版本不存在') from error

    @app.post('/api/v1/modules/versions', response_model=ModuleVersionResponse, status_code=201)
    def save_module_version(request: ModuleSaveRequest):
        try:
            return store.save(request)
        except ModuleVersionConflict as error:
            raise HTTPException(409, detail={'code':'MODULE_VERSION_CONFLICT','message':str(error)}) from error
        except ModuleSaveInvalid as error:
            raise HTTPException(422, detail={'code':'MODULE_SAVE_INVALID','message':str(error),
                                           'diagnostics':[d.model_dump(mode='json') for d in error.diagnostics]}) from error
        except OSError as error:
            raise HTTPException(500, detail={'code':'MODULE_STORAGE_ERROR','message':'模块版本写入失败，请检查存储目录权限和剩余空间'}) from error

    @app.post('/api/v1/modules/test', response_model=ModuleTestResponse)
    def test_module(request: ModuleTestRequest):
        from .bench import run_module_test
        try:
            return run_module_test(request)
        except ValueError as error:
            raise HTTPException(422, detail=diagnostic(error).model_dump(mode='json')) from error

    @app.post('/api/v1/projects/validate', response_model=ValidationResponse)
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

    def compute_run(run_id: str, request: RunRequest):
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
        with lock:
            previous = runs.get(run_id, {})
        events = list(previous.get('events', []))
        events.append({'type':'completed' if status == 'completed' else 'failed','time_s':frame.time_s})
        record = {'id':run_id,'status':status,'mode':request.mode,'request':request.model_dump(mode='json'),
                  'frame':frame.model_dump(mode='json'),'history':[f.model_dump(mode='json') for f in history],
                  'events':events}
        with lock:
            runs[run_id] = record
            while len(runs) > 20:
                runs.popitem(last=False)
        return record

    @app.post('/api/v1/runs',status_code=201, response_model=RunCreateResponse)
    def run(request: RunRequest, background: bool = Query(False)):
        run_id = uuid.uuid4().hex
        if background:
            with lock:
                runs[run_id] = {'id':run_id,'status':'queued','mode':request.mode,
                                'request':request.model_dump(mode='json'),'frame':None,'history':[],
                                'events':[{'type':'queued','time_s':0.0}]}
            def task():
                with lock:
                    if run_id in runs:
                        runs[run_id]['status'] = 'running'
                        runs[run_id]['events'].append({'type':'running','time_s':0.0})
                compute_run(run_id, request)
            executor.submit(task)
            return JSONResponse(status_code=202, content=RunStatus(run_id=run_id,status='queued',mode=request.mode).model_dump(mode='json'))
        record = compute_run(run_id, request)
        return {'run_id':run_id,'status':record['status'],'frame':record['frame'],'total_rows':len(record['history'])}

    def get_run(run_id):
        with lock:
            record = runs.get(run_id)
        if record is None:
            raise HTTPException(404,detail='运行记录不存在或已过期；仅在内存保留最近 20 次运行')
        return record

    @app.get('/api/v1/runs/{run_id}', response_model=RunRecordResponse)
    def run_status(run_id: str):
        record = get_run(run_id)
        return {key:value for key,value in record.items() if key not in {'history', 'events'} or key == 'events'}

    @app.get('/api/v1/runs/{run_id}/events', response_model=RunEventsResponse)
    def run_events(run_id: str):
        return {'run_id': run_id, 'events': [RunEvent.model_validate(event) for event in get_run(run_id).get('events', [])]}

    @app.get('/api/v1/runs/{run_id}/history', response_model=RunHistoryResponse)
    def run_history(run_id: str, offset: int = Query(0,ge=0), limit: int = Query(2001,ge=1,le=2001)):
        history = get_run(run_id)['history']
        return {'rows':history[offset:offset+limit],'total_rows':len(history),'offset':offset}

    if frontend_root:
        app.mount('/',StaticFiles(directory=str(Path(frontend_root)),html=True),name='frontend')
    return app
