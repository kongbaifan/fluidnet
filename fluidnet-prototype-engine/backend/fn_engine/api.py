from __future__ import annotations

import logging
import math
import uuid
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, Lock
from typing import Callable

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
    RunCommand,
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
from .solver import SolveCancelled, solve_dynamic, solve_steady

logger = logging.getLogger('fn_engine.api')

RUN_RETENTION = 20
TERMINAL_STATUSES = frozenset({'completed', 'failed', 'cancelled'})
RUN_NOT_FOUND = '运行记录不存在或已过期;仅在内存保留最近 20 次运行'


class RunControl:
    """Cooperative cancellation/pause flags shared between the API and the solving thread.

    Cancellation is *cooperative*: `solve_dynamic` polls `should_cancel` between
    timeline frames, so the frame currently in flight always finishes before the
    run stops. `pause` reuses the very same hook - while paused the poll call
    blocks until `resume`, `cancel`, or the internal pause budget expires.
    """

    # A paused run gives up waiting after this many seconds and resumes on its
    # own, so a client that disappears cannot pin a solver thread forever.
    PAUSE_BUDGET_S = 30.0

    def __init__(self) -> None:
        self._cancel = Event()
        # Open gate: "not paused". `pause` gates it while `resume`/`cancel` open
        # it, so a parked solver thread wakes immediately instead of waiting out
        # the budget.
        self._resume = Event()
        self._resume.set()
        self._lock = Lock()
        self._paused = False
        # Bumped by every `pause`. A parked solver thread remembers the value it
        # parked on and clears the flag only if nothing newer arrived, so a
        # second pause landing while the first is parked can never be swallowed.
        self._pause_seq = 0

    # -- solver-thread side ------------------------------------------------
    def should_cancel(self) -> bool:
        if self._cancel.is_set():
            return True
        with self._lock:
            paused = self._paused
            seq = self._pause_seq
        if paused:
            self._resume.wait(timeout=self.PAUSE_BUDGET_S)
            with self._lock:
                if self._pause_seq == seq:
                    self._paused = False
        return self._cancel.is_set()

    # -- API-thread side ---------------------------------------------------
    def cancel(self) -> None:
        with self._lock:
            self._paused = False
            self._resume.set()
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    def pause(self) -> None:
        with self._lock:
            self._paused = True
            self._pause_seq += 1
            self._resume.clear()

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            self._resume.set()


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
                           if key in wanted or key.split('.', 2)[1:2] == ['state']}
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
        trend_history(history, request.trend_variables)


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


def create_app(frontend_root: str | Path | None = None, module_storage_root: str | Path | None = None) -> FastAPI:
    runs = OrderedDict()
    controls: dict[str, RunControl] = {}
    lock = Lock()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='fluidnet-run')

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # The executor is owned by this app; tests build one app per case, so
        # shutting it down stops live thread pools from accumulating. Teardown
        # must never raise: a run may still be mid-flight while the app closes.
        try:
            yield
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:  # pragma: no cover - defensive teardown
                logger.exception('FluidNet run executor shutdown failed')

    app = FastAPI(title='FluidNet Prototype Engine', version=__version__, lifespan=lifespan)
    project_root = Path(__file__).resolve().parents[2]
    store = ModuleStore(project_root / 'modules', Path(module_storage_root or os.environ.get('FLUIDNET_MODULE_STORE') or project_root / '.runtime' / 'module-packages'))

    @app.get('/api/v1/health')
    def health():
        return {'status':'ok','version':__version__,'solver':'declarative-fluid-v1','supported_domains':['fluid'],
                'capabilities':{'steady_hydraulics':True,'quasi_steady_series':True,'thermal':True,
                                'property_coupling':['reference','node'],'tank_state':False,
                                'coolprop_single_phase':True,'user_code':True,'worker_process':True,'async_runs':True,
                                'module_versions':True,'run_control':True},
                'max_frames':2001,'run_retention':RUN_RETENTION}

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
        except Exception as error:
            status, detail = _unexpected_failure(error)
            raise HTTPException(status, detail=detail) from error

    def compute_run(run_id: str, request: RunRequest, control: RunControl | None = None) -> dict:
        """Solve a run and always write a terminal record.

        `control` is the cancellation/pause token for background runs; it is
        consulted once more at record-write time so a `stop` that lands after
        the last frame still reports `cancelled` instead of losing the race.
        """
        cancel_hook: Callable[[], bool] | None = control.should_cancel if control is not None else None
        history: list[RunFrame] = []
        try:
            project = apply_scenario(request.project, request.scenario_id)
            network = compile_project(project)
            if request.mode == 'steady':
                history = [solve_steady(network)]
            else:
                history = solve_dynamic(network, request.duration_s, request.dt_s, should_cancel=cancel_hook)
            shape_history(history, request, project)
            frame, status = history[-1], 'completed'
        except SolveCancelled as error:
            # Keep the frames completed before the cancellation was observed:
            # a cancelled run is partial, not empty.
            history = list(getattr(error, 'frames', None) or ())
            try:
                shape_history(history, request, request.project)
            except ValueError:
                pass  # a cancelled run keeps its frames even if the requested shaping is invalid
            status = 'cancelled'
            frame = history[-1] if history else RunFrame(status='cancelled', valid=False, time_s=0)
        except ValueError as error:
            history, status = [], 'failed'
            frame = RunFrame(status='failed',valid=False,time_s=0,diagnostics=[diagnostic(error)])
        # A cancel that arrives while the final frame is being written must not
        # be lost. Only a completed run is flipped: a real failure stays failed.
        if status == 'completed' and control is not None and control.cancelled:
            status = 'cancelled'
        if status == 'cancelled':
            frame = frame.model_copy(update={'status':'cancelled','valid':False})
        with lock:
            previous = runs.get(run_id, {})
        events = list(previous.get('events', []))
        # `stop` publishes `cancelled` (and its event) the moment it lands so a
        # poller exits without waiting for the in-flight frame. If that event is
        # already the tail, appending here would duplicate it.
        if not (events and events[-1].get('type') in TERMINAL_STATUSES):
            events.append({'type':status, 'time_s':float(frame.time_s)})
        record = {'id':run_id,'status':status,'mode':request.mode,'request':request.model_dump(mode='json'),
                  'frame':frame.model_dump(mode='json'),'history':[f.model_dump(mode='json') for f in history],
                  'events':events}
        with lock:
            runs[run_id] = record
            while len(runs) > RUN_RETENTION:
                runs.popitem(last=False)
            controls.pop(run_id, None)
        return record

    def run_task(run_id: str, request: RunRequest, control: RunControl) -> None:
        """Background entry point: the record is terminal no matter what happens."""
        with lock:
            record = runs.get(run_id)
            if record is not None and record.get('status') not in TERMINAL_STATUSES:
                record['status'] = 'running'
                record.setdefault('events', []).append({'type':'running','time_s':0.0})
        try:
            compute_run(run_id, request, control)
        except BaseException as error:
            # compute_run handles every exception it can name; this is the last
            # line of defence so a phantom `running` entry can never survive.
            logger.exception('Background run %s crashed before it could terminalize', run_id)
            # Only `SolveCancelled` proves the cancellation *caused* the exit;
            # a stop being requested is not evidence that an escaped fault was
            # one. Labelling a crash as `cancelled` would hide it - compute_run
            # already reports every genuine cancellation from its own handler.
            status = 'cancelled' if isinstance(error, SolveCancelled) else 'failed'
            detail = diagnostic(error) if isinstance(error, Exception) else None
            try:
                with lock:
                    record = runs.get(run_id)
                    if record is None:
                        return
                    # Only a *finalized* terminal record is untouchable. A `stop`
                    # may have written a provisional `cancelled` (no frame) a
                    # moment before this fault landed; treating that as final
                    # would hide the real failure and strand the record frameless.
                    if record.get('status') in TERMINAL_STATUSES and record.get('frame') is not None:
                        return
                    record['status'] = status
                    events = record.setdefault('events', [])
                    terminal = {'type':status,'time_s':0.0}
                    # Supersede a provisional terminal event rather than appending
                    # a second one, so the record still ends with exactly one.
                    if events and events[-1].get('type') in TERMINAL_STATUSES:
                        events[-1] = terminal
                    else:
                        events.append(terminal)
                    if record.get('frame') is None and detail is not None:
                        record['frame'] = RunFrame(status=status, valid=False, time_s=0,
                                                   diagnostics=[detail]).model_dump(mode='json')
            except Exception:  # pragma: no cover - defensive terminalization
                logger.exception('Failed to terminalize run %s', run_id)
            finally:
                with lock:
                    controls.pop(run_id, None)

    @app.post('/api/v1/runs',status_code=201, response_model=RunCreateResponse)
    def run(request: RunRequest, background: bool = Query(False)):
        run_id = uuid.uuid4().hex
        if background:
            control = RunControl()
            with lock:
                runs[run_id] = {'id':run_id,'status':'queued','mode':request.mode,
                                'request':request.model_dump(mode='json'),'frame':None,'history':[],
                                'events':[{'type':'queued','time_s':0.0}]}
                controls[run_id] = control
            executor.submit(run_task, run_id, request, control)
            return JSONResponse(status_code=202, content=RunStatus(run_id=run_id,status='queued',mode=request.mode).model_dump(mode='json'))
        try:
            record = compute_run(run_id, request)
        except Exception as error:
            # compute_run turns ValueError into a failed record; this catches the
            # unexpected solver/worker faults so they surface as a declared HTTP
            # error instead of a bare traceback.
            status, detail = _unexpected_failure(error)
            raise HTTPException(status, detail=detail) from error
        return {'run_id':run_id,'status':record['status'],'frame':record['frame'],'total_rows':len(record['history'])}

    def get_run(run_id):
        with lock:
            record = runs.get(run_id)
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
                'progress':progress,'frame':frame,'total_rows':len(record.get('history') or [])}

    @app.get('/api/v1/runs/{run_id}', response_model=RunRecordResponse)
    def run_status(run_id: str):
        record = get_run(run_id)
        # `history` is served by /runs/{id}/history; `events` stays visible here.
        return {key:value for key,value in record.items() if key != 'history'}

    @app.get('/api/v1/runs/{run_id}/events', response_model=RunEventsResponse)
    def run_events(run_id: str):
        return {'run_id': run_id, 'events': [RunEvent.model_validate(event) for event in get_run(run_id).get('events', [])]}

    @app.get('/api/v1/runs/{run_id}/history', response_model=RunHistoryResponse)
    def run_history(run_id: str, offset: int = Query(0,ge=0), limit: int = Query(2001,ge=1,le=2001)):
        history = get_run(run_id)['history']
        return {'rows':history[offset:offset+limit],'total_rows':len(history),'offset':offset}

    @app.post('/api/v1/runs/{run_id}/command', response_model=RunStatus)
    def run_command(run_id: str, command: RunCommand):
        """Pause/resume/stop a background run. `step` and `set` are not supported yet."""
        with lock:
            record = runs.get(run_id)
            control = controls.get(run_id)
        if record is None:
            raise HTTPException(404, detail=RUN_NOT_FOUND)
        if command.action in {'step', 'set'}:
            raise HTTPException(422, detail={'code':'RUN_COMMAND_UNSUPPORTED','action':command.action,
                'message':f'运行控制命令 {command.action} 尚未支持:中途改变参数会使已固定的模块版本失效,单步请新建一次指定步长的运行'})
        with lock:
            if record.get('status') in TERMINAL_STATUSES:
                raise HTTPException(409, detail={'code':'RUN_ALREADY_FINISHED','status':record['status'],
                    'message':f'运行已结束({record["status"]}),无法再执行 {command.action}'})
        if control is None:
            raise HTTPException(409, detail={'code':'RUN_NOT_CONTROLLABLE','status':record.get('status'),
                'message':'该运行不是后台任务,同步运行无法中途控制'})
        if command.action == 'stop':
            control.cancel()
            # Record the cancellation immediately so pollers observe it without
            # waiting for the in-flight frame. compute_run appends the matching
            # terminal event; its dict swap then replaces this provisional one.
            with lock:
                current = runs.get(run_id)
                if current is record and record.get('status') not in TERMINAL_STATUSES:
                    record['status'] = 'cancelled'
                    record.setdefault('events', []).append({'type':'cancelled','time_s':0.0})
        elif command.action == 'pause':
            control.pause()
        elif command.action == 'resume':
            control.resume()
        with lock:
            record = runs.get(run_id) or record
        return status_payload(record)

    if frontend_root:
        app.mount('/',StaticFiles(directory=str(Path(frontend_root)),html=True),name='frontend')
    return app
