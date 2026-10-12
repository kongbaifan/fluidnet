"""Bounded computation pool with a non-blocking realtime/paused-session scheduler."""
from __future__ import annotations

from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
import math
from threading import Condition, RLock, Thread
import time
import uuid

from .compiler import CompilationError, compile_project
from .models import RunFrame
from .simulation import SimulationSession
from .solver import SolveFailed, solve_steady

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


@dataclass
class Job:
    request: object
    record: dict
    session: SimulationSession | None = None
    pending: deque = field(default_factory=deque)
    receipts: dict = field(default_factory=dict)
    busy: bool = False
    due: float = 0.0
    stepping: bool = False


class RunManager:
    def __init__(self, project_factory, storage=None):
        self.project_factory = project_factory
        self.storage = storage
        self.lock = RLock()
        self.wake = Condition(self.lock)
        self.jobs = OrderedDict()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='fluidnet-step')
        self.thread = None
        self.closed = False
        self.active = 0
        if storage:
            for record in storage.load_runs():
                self.jobs[record['id']] = Job(None, record)

    def submit(self, request):
        with self.wake:
            if self.closed:
                raise ValueError('运行服务已关闭')
            if sum(j.record['status'] not in TERMINAL for j in self.jobs.values()) >= 20:
                raise ValueError('最多保留 20 个活动运行，请先停止不用的任务')
            run_id = uuid.uuid4().hex
            record = {'id': run_id, 'status': 'queued', 'mode': request.mode,
                'request': request.model_dump(mode='json'), 'frame': None, 'history': [], 'events': [{'type': 'queued', 'time_s': 0.}]}
            self.jobs[run_id] = Job(request.model_copy(deep=True), record)
            if self.storage:
                self.storage.save_run(record)
            if self.thread is None:
                self.thread = Thread(target=self._schedule, name='fluidnet-scheduler', daemon=True)
                self.thread.start()
            self.wake.notify_all()
            return run_id

    def snapshot(self, run_id, history=False):
        with self.lock:
            job = self.jobs[run_id]
            record = job.record
            result = deepcopy(record if history else {k:v for k,v in record.items() if k!='history'})
            result['total_rows'] = len(record['history'])
            result['lag_s'] = max(0., time.monotonic()-job.due) if record['status']=='running' and job.request.execution_mode=='realtime' else 0.
            return result

    def records(self):
        with self.lock:
            return [dict(id=j.record['id'], status=j.record['status'], mode=j.record['mode'],
                         name=j.record['request']['project']['name'], time_s=(j.record.get('frame') or {}).get('time_s', 0))
                    for j in reversed(self.jobs.values())]

    def command(self, run_id, command):
        with self.wake:
            job = self.jobs[run_id]
            key = command.command_id or uuid.uuid4().hex
            if key in job.receipts:
                receipt, previous = job.receipts[key]
                if previous != command.model_dump(exclude={'command_id'}):
                    raise CompilationError('COMMAND_ID_CONFLICT', '命令 ID 已用于不同内容')
                return deepcopy(receipt)
            if job.record['status'] in TERMINAL:
                raise CompilationError('RUN_ALREADY_FINISHED', '运行已结束')
            receipt = {'command_id': key, 'command_status': 'accepted', 'applied_time_s': None, 'message': None}
            job.receipts[key] = receipt, command.model_dump(exclude={'command_id'})
            job.pending.append((key, command.model_copy(deep=True)))
            self._event(job, 'command', key, 'accepted', command=command.model_copy(update={'command_id': key}).model_dump(mode='json'))
            self.wake.notify_all()
            return deepcopy(receipt)

    def _event(self, job, kind, key=None, status=None, message=None, command=None):
        event = {'type': kind, 'time_s': job.session.time if job.session else 0.}
        if key:
            event.update(command_id=key, command_status=status, message=message)
        if command:
            event['command'] = command
        if job.session:
            event['parameter_revision'] = job.session.revision
        job.record['events'].append(event)

    def _schedule(self):
        while True:
            with self.wake:
                if self.closed:
                    return
                now = time.monotonic()
                due = []
                for job in self.jobs.values():
                    if job.busy or job.record['status'] in TERMINAL:
                        continue
                    if job.pending or job.record['status'] == 'queued' or job.record['status'] == 'running' and job.due <= now:
                        if self.active < 2:
                            job.busy = True
                            self.active += 1
                            self.pool.submit(self._tick, job)
                    elif job.record['status'] == 'running':
                        due.append(job.due)
                self.wake.wait(timeout=max(.001, min(due) - now) if due and self.active < 2 else .05)

    def _publish(self, job, frame):
        # Frame objects are never exposed to clients; history is shaped before publication.
        row = frame.model_dump(mode='json')
        selected = job.request.selected_variables or job.request.project.selected_variables
        if selected:
            missing = set(selected) - row['variables'].keys()
            if missing:
                raise CompilationError('TREND_VARIABLE_UNKNOWN', f'未知观察变量：{sorted(missing)}')
            row['variables'] = {key: row['variables'][key] for key in selected}
        job.record['frame'] = deepcopy(row)
        history = job.record['history']
        if history and history[-1]['time_s'] == row['time_s']:
            return
        if job.request.history == 'trend':
            missing = set(job.request.trend_variables) - frame.variables.keys()
            if missing:
                raise CompilationError('TREND_VARIABLE_UNKNOWN', f'未知曲线变量：{sorted(missing)}')
            every = max(1, math.ceil((math.ceil(job.request.duration_s / job.request.dt_s) + 1) / 50))
            if len(history) % every and frame.time_s < job.request.duration_s and job.record['status'] != 'paused':
                row['variables'] = {k: v for k, v in row['variables'].items() if k in job.request.trend_variables
                                    or '.state.' in k or k.startswith('controller.')}
                row['full'] = False
        history.append(row)
        if job.session and len(job.session.frames)>1 and len(history)>1:
            job.session.frames[-2] = RunFrame.model_validate(history[-2])
        if self.storage:
            self.storage.save_run(job.record)

    def _finish(self, job, status, error=None):
        session = job.session
        if session:
            # Event-boundary frames may have been accepted just before SolveFailed.
            for frame in session.frames[len(job.record['history']):]:
                self._publish(job, frame)
            session.close()
        job.record['status'] = status
        if error:
            diagnostic = getattr(error, 'diagnostic', DiagnosticError(error))
            job.record['frame'] = RunFrame(status='failed', valid=False, time_s=session.time if session else 0,
                                          diagnostics=[diagnostic]).model_dump(mode='json')
        elif job.record.get('frame'):
            job.record['frame']['status'] = status
            job.record['frame']['valid'] = status == 'completed'
        if job.record['history'] and session and session.frames:
            # Preserve a full final accepted frame for inspecting any variable.
            job.record['history'][-1] = session.frames[-1].model_dump(mode='json')
        while job.pending:
            key, command = job.pending.popleft()
            receipt = job.receipts[key][0]
            receipt.update(command_status='rejected', message='运行已结束')
            self._event(job, 'command', key, 'rejected', '运行已结束')
        self._event(job, status)
        if self.storage:
            self.storage.save_run(job.record)
        # Keep every active job; only completed records count toward retention.
        ended = [key for key, value in self.jobs.items() if value.record['status'] in TERMINAL]
        for key in ended[:-20]:
            del self.jobs[key]

    def _commands(self, job):
        while job.pending:
            key, command = job.pending.popleft()
            receipt = job.receipts[key][0]
            try:
                action = command.action
                if action == 'pause':
                    job.record['status'] = 'paused'
                elif action == 'resume':
                    job.record['status'] = 'running'
                    job.due = time.monotonic()
                elif action == 'step':
                    if job.record['status'] != 'paused':
                        raise ValueError('单步只能在暂停时执行')
                    job.stepping = True
                elif action == 'set':
                    job.session.set_parameter(command.instance_id, command.parameter_id, command.value)
                elif action == 'controller':
                    job.session.update_controller(command.controller_id, command.parameter_id, command.value)
                elif action == 'stop':
                    receipt.update(command_status='applied', applied_time_s=job.session.time)
                    self._event(job, 'command', key, 'applied')
                    self._finish(job, 'cancelled')
                    return
                receipt.update(command_status='applied', applied_time_s=job.session.time)
                self._event(job, 'command', key, 'applied')
            except ValueError as error:
                receipt.update(command_status='rejected', message=str(error))
                self._event(job, 'command', key, 'rejected', str(error))

    def _tick(self, job):
        try:
            if job.session is None:
                project = self.project_factory(job.request.project, job.request.scenario_id)
                network = compile_project(project)
                if job.request.mode == 'steady':
                    frame = solve_steady(network)
                    with self.wake:
                        self._publish(job, frame)
                        self._finish(job, 'completed')
                    return
                job.session = SimulationSession(network, job.request.duration_s, job.request.dt_s)
                frame = job.session.initialize()
                with self.wake:
                    job.record['status'] = 'paused' if job.request.start_paused else 'running'
                    self._publish(job, frame)
                    self._event(job, job.record['status'])
                    job.due = time.monotonic() + (job.request.dt_s / job.request.speed_ratio if job.request.execution_mode == 'realtime' else 0.)
                return
            with self.wake:
                self._commands(job)
                if job.record['status'] in TERMINAL or job.record['status'] == 'paused' and not job.stepping:
                    return
                if not job.stepping and job.request.execution_mode == 'realtime' and job.due > time.monotonic():
                    return
            frame = job.session.advance()
            with self.wake:
                self._publish(job, frame)
                if job.session.done:
                    self._finish(job, 'completed')
                elif job.stepping:
                    job.stepping = False
                    job.record['status'] = 'paused'
                    self._event(job, 'paused')
                elif job.request.execution_mode == 'realtime':
                    job.due += job.request.dt_s / job.request.speed_ratio
        except BaseException as error:
            with self.wake:
                try:
                    self._finish(job, 'failed', error)
                except BaseException:
                    job.record['status'] = 'failed'
                    if job.session:
                        job.session.close()
        finally:
            with self.wake:
                job.busy = False
                self.active -= 1
                self.wake.notify_all()

    def close(self):
        with self.wake:
            self.closed = True
            self.wake.notify_all()
        self.pool.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            for job in list(self.jobs.values()):
                if job.record['status'] not in TERMINAL:
                    self._finish(job, 'interrupted')


def DiagnosticError(error):
    from .models import Diagnostic
    return Diagnostic(code=getattr(error, 'code', 'SOLVER_ERROR'), message=str(error))
