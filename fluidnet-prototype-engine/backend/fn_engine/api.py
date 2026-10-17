from __future__ import annotations

import asyncio
import logging
import math
import uuid
import os
import tempfile
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth import AuthConfig, allowed, bearer, websocket_secret
from .jobs import OVERVIEW_POINTS, TERMINAL, RunManager
from .bridge import PARAMETER_BINDINGS, normalize_prototype_export
from .catalog import builtin_catalog
from .compiler import CompilationError, compile_project, validate_project_details
from .models import (
    CatalogResponse,
    Diagnostic,
    ModuleDefinition,
    ModuleDesignRequest,
    ModuleDesignResponse,
    ModuleTestRequest,
    ModuleTestResponse,
    ModuleCatalogResponse,
    Project,
    RunCommand,
    RunFrame,
    RunRequest,
    RunStatus,
    RunRecordResponse,
    RunCreateResponse,
    RunEventsResponse,
    RunEvent,
    RunHistoryResponse,
    RunOverviewResponse,
    VariableValues,
    VariableWrite,
    ValidationResponse,
    ModuleSaveRequest,
    ModuleVersionResponse,
    ModuleVersionsResponse,
)
from .properties import PropertyError, refprop_info
from .packages import ModuleStore, ModuleVersionConflict, ModuleSaveInvalid, package_ref
from .module_validation import validate_module_definition
from .solver import SolveFailed, solve_dynamic, solve_steady
from .models import (ControlPreviewRequest, WorkspaceSaveRequest, ProjectSaveRequest,
                     ProjectRevisionRequest, ProjectDeleteRequest, ProjectUpgradeRequest)
from .storage import WorkspaceStore, WorkspaceConflict, StorageError

logger = logging.getLogger('fn_engine.api')

RUN_RETENTION = 20
RUN_NOT_FOUND = '运行记录不存在或已过期；保留最近 20 次已结束运行'


def apply_scenario(project, scenario_id):
    project = project.model_copy(deep=True)
    if not scenario_id:
        return project
    scenario = next((s for s in project.scenarios if s.id == scenario_id), None)
    if scenario is None:
        raise CompilationError('SCENARIO_NOT_FOUND', f'工况不存在:{scenario_id}')
    instances = {i.id:i for i in project.instances}
    for id, overrides in scenario.overrides.items():
        if id not in instances:
            # Same code the validator emits (compiler.validate_scenarios); a run
            # that reaches the merge step still has to point at the instance.
            raise CompilationError('SCENARIO_INSTANCE_MISSING', f'工况引用不存在的实例:{id}', instance_id=id)
        instances[id].parameters.update(overrides)
    return project


TREND_KEY_FRAMES = 50


def trend_history(history: list[RunFrame], variables: list[str]) -> None:
    """Slim a dynamic history in place: key frames keep everything, the rest only the trend.

    Key frames are the first, the last and every K-th frame (K = ceil(n / 50), so at most ~51).
    Other frames keep `variables` plus every module state key (`<instance>.state.*`) and all
    metrics, and are marked `full=False`. Curve values are untouched on every frame. Slim frames
    drop diagnostics identical to the preceding key frame's (the same warnings repeat every frame);
    any frame-specific diagnostic is kept.
    """
    if len(history) <= 2:
        return
    known = history[0].variables.keys() | history[-1].variables.keys()
    unknown = sorted(set(variables) - known)
    if unknown:
        raise CompilationError('TREND_VARIABLE_UNKNOWN', f'未知曲线变量:{unknown}')
    wanted = set(variables)
    every = math.ceil(len(history) / TREND_KEY_FRAMES)
    last = len(history) - 1
    reference = history[0].diagnostics
    for index, frame in enumerate(history):
        if index in (0, last) or index % every == 0:
            reference = frame.diagnostics
            continue
        frame.variables = {key: value for key, value in frame.variables.items()
                           if key in wanted or key.split('.', 2)[1:2] == ['state'] or key.startswith('script.')}
        if frame.diagnostics == reference:
            frame.diagnostics = []
        frame.full = False


def shape_history(history: list[RunFrame], request: RunRequest, project: Project) -> None:
    """Apply `selected_variables` (every frame), then the dynamic `history='trend'` slimming."""
    if not history:
        return
    selected = request.selected_variables if request.selected_variables is not None else project.selected_variables
    if selected:
        missing = set(selected) - history[0].variables.keys()
        if missing:
            raise ValueError(f'未知观察变量:{sorted(missing)}')
        for frame in history:
            frame.variables = {key:frame.variables[key] for key in selected}
    if request.mode == 'dynamic' and request.history == 'trend':
        outputs = {key for script in project.control_scripts if script.enabled for key in script.outputs}
        outputs &= history[0].variables.keys() | history[-1].variables.keys()
        trend_history(history, list(set(request.trend_variables) | outputs))


def diagnostic(error):
    if isinstance(error, CompilationError):
        return error.diagnostic
    if isinstance(error, PropertyError):
        return Diagnostic(code=error.code, message=str(error))
    return Diagnostic(code=getattr(error, 'code', 'SOLVER_ERROR'), message=str(error))


def _unexpected_failure(error: BaseException) -> tuple[int, dict]:
    """Map the residual solver/worker faults to a status a UI can act on.

    `ValueError` is handled by each route at 422 before this is reached, and that
    already covers `RuntimeErrorBase` (the user-module / Worker-contract failure
    type, a `ValueError` subclass) together with its own `code`. What remains here
    is the subprocess boundary (`OSError` -> 422, still an actionable request
    problem) and genuine engine faults (-> 500 with the original message preserved
    and the traceback logged rather than swallowed).
    """
    if isinstance(error, OSError):
        return 422, {'code': 'MODULE_WORKER_IO_ERROR', 'message': str(error)}
    logger.exception('Unexpected failure while running a FluidNet request')
    return 500, {'code': 'INTERNAL_ERROR', 'message': str(error)}


def create_app(frontend_root: str | Path | None = None, module_storage_root: str | Path | None = None,
               auth: AuthConfig | None = None, cors_origins: list[str] | tuple[str, ...] = (),
               data_root: str | Path | None = None) -> FastAPI:
    """`auth.required` puts every /api/ call except /api/v1/health behind a bearer token (see auth.py)."""
    auth = auth or AuthConfig()
    runs = OrderedDict()
    lock = Lock()
    archive = WorkspaceStore(data_root) if data_root is not None else None
    manager = RunManager(apply_scenario, archive)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # The run manager is owned by this app; tests build one app per case, so
        # closing it stops live thread pools from accumulating. Teardown must
        # never raise: a run may still be mid-flight while the app closes.
        try:
            yield
        finally:
            try:
                manager.close()
            except Exception:  # pragma: no cover - defensive teardown
                logger.exception('FluidNet run manager shutdown failed')
            finally:
                if archive:
                    archive.close()

    app = FastAPI(title='FluidNet Prototype Engine', version=__version__, lifespan=lifespan)
    @app.exception_handler(StorageError)
    async def storage_error(_request, error):
        return JSONResponse(status_code=507, content={'detail': {'code': 'STORAGE_FAILED', 'message': str(error)}})
    @app.exception_handler(WorkspaceConflict)
    async def project_conflict(_request, error):
        return JSONResponse(status_code=409, content={'detail': {'code': 'PROJECT_CONFLICT', 'message': str(error)}})
    project_root = Path(__file__).resolve().parents[2]
    restored_modules = Path(data_root) / 'module-packages' if data_root is not None else None
    store = ModuleStore(project_root / 'modules', Path(module_storage_root or (
        restored_modules if restored_modules is not None and restored_modules.is_dir() else None)
        or os.environ.get('FLUIDNET_MODULE_STORE') or project_root / '.runtime' / 'module-packages'))

    @app.middleware('http')
    async def require_token(request: Request, call_next):
        path = request.url.path
        if (auth.required and path.startswith('/api/') and path != '/api/v1/health'
                and request.method != 'OPTIONS'):
            record = auth.store.verify(bearer(request.headers.get('authorization')))
            if record is None:
                return JSONResponse(status_code=401, headers={'WWW-Authenticate': 'Bearer'},
                                    content={'detail': {'code': 'AUTH_REQUIRED', 'message': '需要有效的访问令牌（Authorization: Bearer …）'}})
            if not allowed(record, request.method):
                return JSONResponse(status_code=403, content={'detail': {'code': 'AUTH_SCOPE',
                                    'message': f'令牌 {record["name"]} 只有 {record["scope"]} 权限，不能执行 {request.method}'}})
        return await call_next(request)

    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins), allow_methods=['GET', 'POST'],
                           allow_headers=['Authorization', 'Content-Type'])

    @app.get('/api/v1/health')
    def health():
        return {'status':'ok','version':__version__,'solver':'declarative-fluid-v1','supported_domains':['fluid'],
                'capabilities':{'steady_hydraulics':True,'quasi_steady_series':True,'thermal':True,
                                'property_coupling':['reference','node'],'tank_state':True,
                                'time_integration':'implicit_euler',
                                'coolprop_single_phase':True,'user_code':True,'worker_process':True,'async_runs':True,
                                'module_versions':True,'run_control':True,'live_runs':True,'pid':True,'runtime_parameters':True,'continuous_step':True,
                                'continuous_runs':True,'variables_api':True,'run_stream':True,
                                'python_controls':True,'persistent_workspace':archive is not None,
                                # REFPROP 运行时发现（环境变量/捆绑目录/系统安装）；不加载 DLL。
                                'refprop':refprop_info()},
                'max_frames':2001,'run_retention':RUN_RETENTION,'history_window_max':20001,'overview_points':OVERVIEW_POINTS,
                'auth':{'required':auth.required}}

    def require_archive():
        if archive is None:
            raise HTTPException(503, detail='持久存储未启用，请使用 serve 启动服务或为 create_app 配置 data_root')
        return archive

    @app.get('/api/v1/workspace')
    def read_workspace(revision: int | None = Query(None, ge=1)):
        try:
            return require_archive().workspace(revision)
        except KeyError:
            raise HTTPException(404, detail='工作区备份修订不存在')

    @app.get('/api/v1/workspace/revisions')
    def workspace_revisions():
        return {'revisions': require_archive().revisions()}

    @app.get('/api/v1/workspace/storage')
    def workspace_storage():
        return require_archive().usage()

    @app.post('/api/v1/workspace/backup', response_class=FileResponse,
              responses={200: {'content': {'application/zip': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def workspace_backup():
        from .backup import backup_workspace
        storage = require_archive()
        temporary = tempfile.TemporaryDirectory(prefix='.download-', dir=storage.root.parent)
        path = Path(temporary.name) / 'fluidnet-backup.zip'
        try:
            backup_workspace(storage, store, path)
            return FileResponse(path, media_type='application/zip', filename='fluidnet-backup.zip',
                                background=BackgroundTask(temporary.cleanup))
        except BaseException:
            temporary.cleanup()
            raise

    @app.post('/api/v1/workspace/restore', openapi_extra={
        'requestBody': {'required': True, 'content': {'application/zip': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    async def workspace_restore(request: Request):
        from .backup import restore_workspace
        storage = require_archive()
        target = storage.root.parent / ('restored-' + uuid.uuid4().hex[:12])
        with tempfile.TemporaryDirectory(prefix='.upload-', dir=storage.root.parent) as temporary:
            source = Path(temporary) / 'backup.zip'
            size = 0
            with source.open('wb') as incoming:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 256 * 1024**2:
                        raise HTTPException(413, detail='上传备份超过 256 MiB，请使用 workspace restore 命令恢复')
                    incoming.write(chunk)
            try:
                manifest = await run_in_threadpool(restore_workspace, source, target)
            except ValueError as error:
                raise HTTPException(422, detail=str(error)) from error
        return {'directory': str(target.resolve()), 'revision': manifest['revision'],
                'command': f'python -m fn_engine serve --data-dir "{target.resolve()}"',
                'message': '已恢复到独立目录。关闭当前服务后使用下方命令打开；原工作区保留。'}

    @app.post('/api/v1/workspace')
    def save_workspace(request: WorkspaceSaveRequest):
        try:
            return require_archive().save_workspace(request.data, request.expected_revision)
        except WorkspaceConflict as error:
            raise HTTPException(409, detail={'code': 'WORKSPACE_CONFLICT', 'message': str(error)}) from error

    @app.post('/api/v1/controls/preview')
    def preview_control(request: ControlPreviewRequest):
        from .simulation import SimulationSession
        script = request.script.model_copy(update={'enabled': True})
        project = request.project.model_copy(deep=True, update={'control_scripts': [script]})
        session = None
        try:
            session = SimulationSession(compile_project(project), script.sample_s, script.sample_s)
            session.initialize()
            session._control()
            result = session.scripts[script.id].pending[0]
            return {**result, 'content_hash': script.content_hash, 'time_s': 0., 'applied': False}
        except ValueError as error:
            raise HTTPException(422, detail=diagnostic(error).model_dump(mode='json')) from error
        finally:
            if session:
                session.close()

    @app.post('/api/v1/projects/validate', response_model=ValidationResponse)
    def validate(project: Project):
        items, circuits = validate_project_details(project)
        return {'valid':not any(d.severity == 'error' for d in items),'diagnostics':items,'circuits':circuits}

    def project_idle(project_id):
        with manager.lock:
            if any(j.request.project.id == project_id and j.record['status'] not in TERMINAL for j in manager.jobs.values()):
                raise HTTPException(409, detail='请先停止该项目的活动运行，再更改项目版本或删除项目')

    @app.get('/api/v1/projects')
    def list_projects():
        return {'projects': require_archive().projects()}

    @app.get('/api/v1/projects/{project_id}')
    def read_project(project_id: str, revision: int | None = Query(None, ge=1)):
        try:
            return require_archive().project(project_id, revision)
        except KeyError:
            raise HTTPException(404, detail='项目或修订不存在')

    @app.get('/api/v1/projects/{project_id}/revisions')
    def project_revisions(project_id: str):
        return {'revisions': require_archive().project_history(project_id)}

    @app.post('/api/v1/projects/{project_id}')
    def save_project(project_id: str, request: ProjectSaveRequest):
        project_idle(project_id)
        if request.document.project['id'] != project_id:
            raise HTTPException(422, detail='路径与文档项目 ID 不一致')
        try:
            return require_archive().save_project(request.document.model_dump(mode='json', by_alias=True), request.expected_revision)
        except ValueError as error:
            if isinstance(error, WorkspaceConflict):
                raise
            raise HTTPException(422, detail=str(error)) from error

    @app.post('/api/v1/projects/{project_id}/restore')
    def restore_project_revision(project_id: str, request: ProjectRevisionRequest):
        project_idle(project_id)
        storage = require_archive()
        try:
            document = storage.project(project_id, request.revision)['document']
            receipt = storage.save_project(document, request.expected_revision)
            return {**receipt, 'document': document}
        except KeyError:
            raise HTTPException(404, detail='项目修订不存在')

    @app.post('/api/v1/projects/{project_id}/delete')
    def delete_project(project_id: str, request: ProjectDeleteRequest):
        project_idle(project_id)
        try:
            return require_archive().save_project({'project': {'id': project_id}}, request.expected_revision, delete=True)
        except ValueError as error:
            if isinstance(error, WorkspaceConflict):
                raise
            raise HTTPException(422, detail=str(error)) from error

    @app.post('/api/v1/project-upgrades/preview')
    def preview_project_upgrade(request: ProjectUpgradeRequest):
        from .projects import upgrade_project
        project_idle(request.project.id)
        try:
            target = store.get(request.module_id, request.target_version).module
            return upgrade_project(request.project, target)
        except KeyError:
            raise HTTPException(404, detail='模块版本不存在')
        except ValueError as error:
            raise HTTPException(422, detail=str(error)) from error

    @app.get('/api/v1/catalog', response_model=CatalogResponse)
    def catalog():
        return {'modules':builtin_catalog(), 'prototype_parameter_bindings':PARAMETER_BINDINGS}

    @app.get('/api/v1/examples/{name}', response_model=Project)
    def example(name: str):
        from .examples import pid_example
        try:
            return pid_example(name)
        except KeyError:
            raise HTTPException(404, detail='示例不存在')

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
            raise HTTPException(500, detail={'code':'MODULE_STORAGE_ERROR','message':'模块版本写入失败,请检查存储目录权限和剩余空间'}) from error

    @app.post('/api/v1/modules/test', response_model=ModuleTestResponse)
    def test_module(request: ModuleTestRequest):
        from .bench import run_module_test
        try:
            return run_module_test(request)
        except ValueError as error:
            raise HTTPException(422, detail=diagnostic(error).model_dump(mode='json')) from error
        except Exception as error:
            # Worker/solver boundary faults must not escape as an opaque 500;
            # the caller gets an actionable status plus the original message.
            status, detail = _unexpected_failure(error)
            raise HTTPException(status, detail=detail) from error

    @app.post('/api/v1/modules/design', response_model=ModuleDesignResponse)
    def design_module(request: ModuleDesignRequest):
        from .design import run_design
        try:
            return run_design(request)
        except ValueError as error:
            raise HTTPException(422, detail=diagnostic(error).model_dump(mode='json')) from error
        except Exception as error:
            status, detail = _unexpected_failure(error)
            raise HTTPException(status, detail=detail) from error

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
        except Exception as error:
            status, detail = _unexpected_failure(error)
            raise HTTPException(status, detail=detail) from error

    def compute_run(run_id: str, request: RunRequest) -> dict:
        """Solve a synchronous run and always write a terminal record (background runs use RunManager)."""
        history: list[RunFrame] = []
        try:
            project = apply_scenario(request.project, request.scenario_id)
            network = compile_project(project)
            if request.mode == 'steady':
                history = [solve_steady(network)]
            else:
                history = solve_dynamic(network, request.duration_s, request.dt_s)
            shape_history(history, request, project)
            frame, status = history[-1], 'completed'
        except SolveFailed as error:
            # A dynamic run that stopped at a tank limit or an unsolvable step keeps its accepted frames.
            history = list(error.frames)
            try:
                shape_history(history, request, request.project)
            except ValueError:
                pass
            status = 'failed'
            frame = RunFrame(status='failed', valid=False, time_s=history[-1].time_s if history else 0,
                             diagnostics=[error.diagnostic])
        except ValueError as error:
            history, status = [], 'failed'
            frame = RunFrame(status='failed',valid=False,time_s=0,diagnostics=[diagnostic(error)])
        events = [{'type':status, 'time_s':float(frame.time_s)}]
        record = {'id':run_id,'status':status,'mode':request.mode,'request':request.model_dump(mode='json'),
                  'frame':frame.model_dump(mode='json'),'history':[f.model_dump(mode='json') for f in history],
                  'events':events, 'total_rows':len(history)}
        if archive:
            stride = 1 if len(record['history']) <= OVERVIEW_POINTS else 2
            archive.save_run(record, list(enumerate(record['history'])), len(record['history']), 2001,
                             {'rows': record['history'][::stride], 'stride': stride})
        with lock:
            runs[run_id] = record
            while len(runs) > RUN_RETENTION:
                runs.popitem(last=False)
        return record

    @app.post('/api/v1/runs',status_code=201, response_model=RunCreateResponse)
    def run(request: RunRequest, background: bool = Query(False)):
        run_id = uuid.uuid4().hex
        if background:
            try:
                run_id = manager.submit(request)
            except ValueError as error:
                raise HTTPException(422, detail={'code':'RUN_LIMIT', 'message':str(error)}) from error
            return JSONResponse(status_code=202, content=RunStatus(run_id=run_id,status='queued',mode=request.mode).model_dump(mode='json'))
        frames = request.frame_count()
        if request.mode == 'dynamic' and (frames is None or frames > 2001):
            raise HTTPException(422, detail={'code':'RUN_TOO_LONG', 'message':'同步运行一次返回全部帧，最多 2001 帧且必须设定时长；'
                                             '更长或持续的运行请用 background=true'})
        try:
            record = compute_run(run_id, request)
        except Exception as error:
            # compute_run turns ValueError into a failed record; this catches the
            # unexpected solver/worker faults so they surface as a declared HTTP
            # error instead of a bare traceback.
            status, detail = _unexpected_failure(error)
            raise HTTPException(status, detail=detail) from error
        return {'run_id':run_id,'status':record['status'],'frame':record['frame'],'total_rows':len(record['history'])}

    @app.get('/api/v1/runs')
    def list_runs():
        records = {r['id']: r for r in archive.records()} if archive else {}
        with lock:
            records.update({r['id']: {'id': r['id'], 'status': r['status'], 'mode': r['mode'],
                'name': r['request']['project']['name'], 'time_s': r['frame']['time_s']} for r in reversed(runs.values())})
        records.update({r['id']: r for r in manager.records()})
        return {'runs': list(records.values())}

    def get_run(run_id, history=False):
        try:
            return manager.snapshot(run_id, history=history)
        except KeyError:
            pass
        with lock:
            record = runs.get(run_id)
        if record is None and archive:
            try:
                record = archive.record(run_id)
            except KeyError:
                pass
        if record is None:
            raise HTTPException(404,detail=RUN_NOT_FOUND)
        return record

    def status_payload(record) -> dict:
        """Build the `RunStatus` view of an in-memory record."""
        request = record.get('request') or {}
        frame = record.get('frame') if isinstance(record.get('frame'), dict) else None
        progress = 0.0
        if record.get('status') == 'completed':
            progress = 1.0
        elif request.get('mode') == 'dynamic' and frame and request.get('duration_s'):
            progress = max(0.0, min(1.0, float(frame.get('time_s') or 0.0) / float(request['duration_s'])))
        return {'run_id':record['id'],'status':record.get('status','queued'),'mode':record.get('mode','steady'),
                'progress':progress,'frame':frame,'total_rows':record.get('total_rows',len(record.get('history') or [])),
                'lag_s':record.get('lag_s',0.)}

    @app.get('/api/v1/runs/{run_id}', response_model=RunRecordResponse)
    def run_status(run_id: str):
        record = get_run(run_id)
        # `history` is served by /runs/{id}/history; `events` stays visible here.
        return {key:value for key,value in record.items() if key != 'history'}

    @app.post('/api/v1/runs/{run_id}/delete')
    def delete_run(run_id: str):
        record = get_run(run_id)
        if record['status'] not in TERMINAL:
            raise HTTPException(409, detail='请先停止活动运行，再删除档案')
        # Disk deletion must succeed before dropping the in-memory copy.
        if archive:
            try:
                archive.delete_run(run_id)
            except KeyError:
                pass
        with manager.lock:
            manager.jobs.pop(run_id, None)
        with lock:
            runs.pop(run_id, None)
        return {'deleted': run_id}

    @app.get('/api/v1/runs/{run_id}/events', response_model=RunEventsResponse)
    def run_events(run_id: str):
        return {'run_id': run_id, 'events': [RunEvent.model_validate(event) for event in get_run(run_id).get('events', [])]}

    @app.get('/api/v1/runs/{run_id}/history', response_model=RunHistoryResponse)
    def run_history(run_id: str, offset: int = Query(0,ge=0), limit: int = Query(2001,ge=1,le=2001)):
        try:
            return manager.history(run_id, offset, limit)
        except KeyError:
            record = get_run(run_id)
            if 'history' not in record and archive:
                return archive.history(run_id, offset, limit)
            history = record['history']
        return {'rows':history[offset:offset+limit],'total_rows':len(history),'offset':offset}

    @app.get('/api/v1/runs/{run_id}/overview', response_model=RunOverviewResponse)
    def run_overview(run_id: str):
        try:
            return manager.overview(run_id)
        except KeyError:
            record = get_run(run_id)
            if 'history' not in record and archive:
                return archive.overview(run_id)
            history = record['history']
        stride = 1
        while math.ceil(len(history) / stride) > OVERVIEW_POINTS:
            stride *= 2
        rows = history[::stride]
        if history and (len(history) - 1) % stride:
            rows = rows + [history[-1]]
        return {'rows':rows,'stride':stride,'total_rows':len(history)}

    @app.post('/api/v1/runs/{run_id}/command', response_model=RunStatus)
    def run_command(run_id: str, command: RunCommand):
        record = get_run(run_id)
        try:
            receipt = manager.command(run_id, command)
        except KeyError:
            raise HTTPException(409, detail={'code':'RUN_ALREADY_FINISHED', 'message':'同步运行已结束'})
        except CompilationError as error:
            raise HTTPException(409 if error.diagnostic.code in {'RUN_ALREADY_FINISHED','COMMAND_ID_CONFLICT'} else 422,
                                detail={'code':error.diagnostic.code, 'message':str(error)}) from error
        return status_payload(manager.snapshot(run_id)) | receipt

    def frame_values(run_id, wanted):
        """Latest values of a run (background or synchronous) with the known keys of its frame."""
        try:
            return manager.latest(run_id, wanted)
        except KeyError:
            record = get_run(run_id)
        frame = record.get('frame') or {}
        variables = frame.get('variables') or {}
        return {'run_id': run_id, 'status': record.get('status'), 'time_s': frame.get('time_s'), 'sequence': frame.get('sequence'),
                'parameter_revision': frame.get('parameter_revision'), 'known': set(variables),
                'values': {k: variables[k] for k in wanted if k in variables} if wanted is not None else dict(variables)}

    def split_keys(keys):
        return [key.strip() for key in keys.split(',') if key.strip()] if keys else None

    def check_keys(data, wanted):
        if wanted and not data['known']:
            raise HTTPException(409, detail={'code': 'NO_FRAME', 'message': f'运行 {data["status"]}，还没有可读的帧'})
        unknown = sorted(set(wanted or ()) - data['known'])
        if unknown:
            raise HTTPException(422, detail={'code': 'VARIABLE_UNKNOWN', 'message': f'帧中没有这些变量：{unknown}',
                                             'keys': unknown})

    @app.get('/api/v1/runs/{run_id}/variables', response_model=VariableValues)
    def run_variables(run_id: str, keys: str | None = Query(None, max_length=16384)):
        """Latest frame values; `keys` is a comma-separated list of frame keys (default: all)."""
        wanted = split_keys(keys)
        data = frame_values(run_id, wanted)
        check_keys(data, wanted)
        return {key: data[key] for key in ('run_id', 'status', 'time_s', 'sequence', 'parameter_revision', 'values')}

    @app.post('/api/v1/runs/{run_id}/variables', response_model=RunStatus)
    def write_run_variables(run_id: str, body: VariableWrite):
        """Write runtime parameters / PID settings by frame key, together at the next frame boundary."""
        get_run(run_id)
        command = RunCommand(action='write', values=body.values, command_id=body.command_id)
        try:
            receipt = manager.command(run_id, command)
        except KeyError:
            raise HTTPException(409, detail={'code':'RUN_ALREADY_FINISHED', 'message':'同步运行已结束'})
        except CompilationError as error:
            raise HTTPException(409, detail={'code':error.diagnostic.code, 'message':str(error)}) from error
        if body.wait_s:
            try:
                receipt = manager.wait_receipt(run_id, receipt['command_id'], body.wait_s)
            except KeyError:
                pass
        return status_payload(manager.snapshot(run_id)) | receipt

    @app.websocket('/api/v1/runs/{run_id}/stream')
    async def run_stream(websocket: WebSocket, run_id: str, keys: str | None = None, interval_ms: int = 50):
        """Push the latest frame (selected `keys`) whenever a new one is published, then an `end` message.

        A slow client skips frames instead of queueing them; `sequence` shows the gaps.
        """
        subprotocol = None
        if auth.required:
            secret, subprotocol = websocket_secret(websocket.headers)
            if not allowed(auth.store.verify(secret), 'GET'):
                await websocket.accept(subprotocol=subprotocol)
                await websocket.close(code=4401, reason='AUTH_REQUIRED')
                return
        wanted = split_keys(keys)
        interval = min(max(interval_ms, 10), 5000) / 1000
        await websocket.accept(subprotocol=subprotocol)
        last = None
        try:
            while True:
                try:
                    data = manager.latest(run_id, wanted)
                except KeyError:
                    await websocket.send_json({'type': 'error', 'code': 'RUN_NOT_FOUND', 'message': RUN_NOT_FOUND + '；只有后台运行可以订阅'})
                    await websocket.close(code=4404)
                    return
                unknown = sorted(set(wanted or ()) - data['known']) if data['known'] else []
                if unknown:
                    await websocket.send_json({'type': 'error', 'code': 'VARIABLE_UNKNOWN', 'keys': unknown})
                    await websocket.close(code=4422)
                    return
                terminal = data['status'] in TERMINAL
                if data['known'] and data['sequence'] != last and not (terminal and data['status'] == 'failed'):
                    last = data['sequence']
                    await websocket.send_json({'type': 'frame', **{k: data[k] for k in ('status', 'time_s', 'sequence', 'parameter_revision', 'values')}})
                if terminal:
                    await websocket.send_json({'type': 'end', 'status': data['status']})
                    await websocket.close()
                    return
                await asyncio.sleep(interval)
        except (WebSocketDisconnect, RuntimeError):
            return

    if frontend_root:
        app.mount('/',StaticFiles(directory=str(Path(frontend_root)),html=True),name='frontend')
    return app
