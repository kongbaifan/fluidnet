"""Bounded computation pool with a non-blocking realtime/paused-session scheduler.

Per-frame archives are written by a dedicated `_ArchiveWriter` thread. The global `wake`
lock only guards in-memory state; SQLite transactions and Worker RPCs (command
set/controller/write, session finalize) run outside it, so a slow disk or a stuck Worker
can no longer park every API call behind the scheduler. The writer batches the frames of a
run into one transaction, throttles the large overview blob, and applies backpressure
outside the lock; see docs/BACKUP_ACCEPTANCE.md「批量写入与锁范围」for the durability
window this introduces.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
import math
from threading import Condition, Event, RLock, Thread
import time
import uuid

from .compiler import CompilationError, compile_project
from .models import RunFrame
from .simulation import SimulationSession
from .solver import SolveFailed, solve_steady
from .storage import StorageError

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}
# Overview of a whole run: every `stride`-th frame, the stride doubling whenever this is exceeded.
OVERVIEW_POINTS = 2000
# Frames a background session holds itself; history and overview live on the record.
SESSION_FRAMES = 8
# A long run with frequent writes keeps only the most recent events and settled receipts.
EVENT_LIMIT = 1000
RECEIPT_LIMIT = 1000
# Archive batching: the writer collects a run's frames for ARCHIVE_COALESCE_S before each
# transaction, and producers wait (outside the global lock) once ARCHIVE_BACKLOG frames are
# queued. A crash can therefore lose at most ARCHIVE_BACKLOG queued frames - normally just
# the frames of one coalescing window (tens of milliseconds).
ARCHIVE_COALESCE_S = 0.01
ARCHIVE_BACKLOG = 256
# The decimated overview blob is the largest per-write payload (it grows to OVERVIEW_POINTS
# full frames). Persist it only when both thresholds are met - so slow realtime runs batch
# many frames and fast runs still checkpoint about twice a second - plus immediately on a
# stride change and on every terminal write; the live overview API reads the memory copy.
ARCHIVE_OVERVIEW_FRAMES = 64
ARCHIVE_OVERVIEW_S = 0.5


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
    published: int = 0          # frames published so far (absolute index of the next one)
    last_sequence: int = -1     # RunFrame.sequence of the last published session frame
    overview: list = field(default_factory=list)   # (absolute index, slim row)
    stride: int = 1
    finishing: bool = False     # terminal finalize in progress; new commands are refused
    archive_error: BaseException | None = None  # last failed archive write for this run
    overview_dirty: bool = False  # overview changed (stride/trim) since the last archive
    overview_pending: int = 0     # overview points added since the last archived overview
    overview_due: float = 0.0     # monotonic deadline of the next throttled overview write


class _ArchiveWriter:
    """One writer thread; coalesces per-run frame rows into batched SQLite transactions."""

    def __init__(self, manager, storage):
        self.manager = manager
        self.storage = storage
        self.condition = Condition()
        self.items = {}  # run_id -> pending write; insertion order is the write order
        self.closed = False
        self.thread = Thread(target=self._run, name='fluidnet-archive', daemon=True)
        self.thread.start()

    def enqueue(self, job, record, rows, total_rows, window, overview=None, wait=False):
        """Merge a record snapshot (and optional new rows) into the run's pending write.

        `wait=True` makes this a write-through: it returns only after that snapshot (plus
        every row queued before it) is committed, and re-raises a storage failure.
        """
        run_id = job.record['id']
        waiter, box = (Event(), {}) if wait else (None, None)
        with self.condition:
            if self.closed:
                raise StorageError('归档写入已关闭')
            item = self.items.get(run_id)
            if item is None:
                item = {'job': job, 'record': record, 'rows': [], 'total_rows': total_rows,
                        'window': window, 'overview': None, 'waiters': []}
                self.items[run_id] = item
            item['record'] = record
            item['total_rows'] = total_rows
            item['window'] = window
            item['rows'].extend(rows)
            if overview is not None:
                item['overview'] = overview
            if waiter is not None:
                item['waiters'].append((waiter, box))
            self.condition.notify_all()
        if waiter is None:
            return None
        if not waiter.wait(timeout=30.):
            raise StorageError('归档写入超时')
        if 'error' in box:
            raise box['error']
        return box.get('persisted')

    def throttle(self, job):
        """Backpressure: block the producer (without the global lock) when a run is behind."""
        run_id = job.record['id']
        while True:
            with self.condition:
                item = self.items.get(run_id)
                if item is None or len(item['rows']) <= ARCHIVE_BACKLOG:
                    return
                self.condition.wait(timeout=.05)
            if job.archive_error is not None:
                raise job.archive_error

    def _run(self):
        while True:
            with self.condition:
                while not self.items and not self.closed:
                    self.condition.wait()
                if not self.items:
                    return
                # Let a few frames accumulate before committing, unless someone is waiting
                # on a write-through (commands, terminal records, shutdown).
                if not self.closed and not any(item['waiters'] for item in self.items.values()):
                    self.condition.wait(timeout=ARCHIVE_COALESCE_S)
                # Write-through items (command receipts, terminal records) jump the queue
                # so a stop/command never waits for a full coalescing batch of frames;
                # per-run order is still preserved because one run owns one item.
                waiting = [key for key, value in self.items.items() if value['waiters']]
                run_id = waiting[0] if waiting else next(iter(self.items))
                item = self.items.pop(run_id)
            try:
                self.storage.save_run(item['record'], item['rows'], item['total_rows'],
                                      item['window'], item['overview'])
            except BaseException as error:  # a run must fail visibly instead of hanging
                self._failed(item, error)
                continue
            self._persisted(item)

    def _persisted(self, item):
        job = item['job']
        record = item['record']
        with self.manager.wake:
            # `save_run` stamps persisted_at/persisted_rows on the snapshot it wrote; the
            # in-memory record keeps the latest confirmed archive boundary.
            if job.record.get('persisted_rows', 0) <= item['total_rows']:
                job.record['persisted_at'] = record.get('persisted_at')
                job.record['persisted_rows'] = item['total_rows']
            self.manager.wake.notify_all()
        for waiter, box in item['waiters']:
            box['persisted'] = item['total_rows']
            waiter.set()

    def _failed(self, item, error):
        job = item['job']
        with self.manager.wake:
            job.archive_error = error
            self.manager.wake.notify_all()
        for waiter, box in item['waiters']:
            box['error'] = error
            waiter.set()

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        self.thread.join(timeout=30.)


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
        self.archive = _ArchiveWriter(self, storage) if storage is not None else None

    def submit(self, request):
        with self.wake:
            if self.closed:
                raise ValueError('运行服务已关闭')
            if sum(j.record['status'] not in TERMINAL for j in self.jobs.values()) >= 20:
                raise ValueError('最多保留 20 个活动运行，请先停止不用的任务')
            run_id = uuid.uuid4().hex
            record = {'id': run_id, 'status': 'queued', 'mode': request.mode,
                'request': request.model_dump(mode='json'), 'frame': None, 'history': [], 'events': [{'type': 'queued', 'time_s': 0.}]}
            job = Job(request.model_copy(deep=True), record)
        # Durable before the scheduler can see the job; one small write per run is fine.
        self._persist(job)
        with self.wake:
            self.jobs[run_id] = job
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
            result['total_rows'] = job.published
            result['lag_s'] = max(0., time.monotonic()-job.due) if record['status']=='running' and job.request.execution_mode=='realtime' else 0.
            return result

    def history(self, run_id, offset, limit):
        """Rows at absolute frame indices [offset, offset+limit) that are still in the window."""
        with self.lock:
            job = self.jobs[run_id]
            rows = job.record['history']
            first = job.published - len(rows)
            start = max(offset, first)
            return {'rows': deepcopy(rows[start - first:start - first + limit]), 'total_rows': job.published,
                    'offset': start, 'first_offset': first, 'truncated': offset < first}

    def overview(self, run_id):
        with self.lock:
            job = self.jobs[run_id]
            rows = [row for _, row in job.overview]
            history = job.record['history']
            if history and (not job.overview or job.overview[-1][0] != job.published - 1):
                rows.append(history[-1])
            return {'rows': deepcopy(rows), 'stride': job.stride, 'total_rows': job.published}

    def wait_receipt(self, run_id, key, timeout_s):
        """The receipt of command `key` once applied or rejected, or as it stands after `timeout_s`."""
        deadline = time.monotonic() + timeout_s
        with self.wake:
            while True:
                receipt = self.jobs[run_id].receipts[key][0]
                remaining = deadline - time.monotonic()
                if receipt['command_status'] != 'accepted' or remaining <= 0:
                    return deepcopy(receipt)
                self.wake.wait(timeout=remaining)

    def latest(self, run_id, keys=None):
        """Latest published frame values (all, or `keys`) without copying the whole record."""
        with self.lock:
            job = self.jobs[run_id]
            frame = job.record.get('frame') or {}
            variables = frame.get('variables') or {}
            if keys is not None:
                variables = {key: variables[key] for key in keys if key in variables}
            return {'run_id': run_id, 'status': job.record['status'], 'time_s': frame.get('time_s'),
                    'sequence': frame.get('sequence'), 'parameter_revision': frame.get('parameter_revision'),
                    'values': dict(variables), 'known': set(frame.get('variables') or ())}

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
            if job.record['status'] in TERMINAL or job.finishing:
                raise CompilationError('RUN_ALREADY_FINISHED', '运行已结束')
            receipt = {'command_id': key, 'command_status': 'accepted', 'applied_time_s': None, 'message': None}
            job.receipts[key] = receipt, command.model_dump(exclude={'command_id'})
            if len(job.receipts) > RECEIPT_LIMIT:
                # Oldest settled receipts go first; a retried id older than that runs as a new command.
                settled = [k for k, (r, _) in job.receipts.items() if r['command_status'] != 'accepted']
                for old in settled[:len(job.receipts) - RECEIPT_LIMIT]:
                    del job.receipts[old]
            # The command only becomes executable once its accepted receipt is durable.
            ready = Event()
            job.pending.append((key, command.model_copy(deep=True), ready))
            accepted = self._event_data(job, 'command', key, 'accepted',
                                        command=command.model_copy(update={'command_id': key}).model_dump(mode='json'))
            self._append_event(job, accepted)
            record = self._archive_record(job)
            total_rows = job.published
            window = job.request.history_window
        try:
            if self.archive is not None:
                self.archive.enqueue(job, record, [], total_rows, window, wait=True)
        except BaseException:
            # An unacknowledged command must not execute after a failed disk write.
            with self.wake:
                for index, item in enumerate(job.pending):
                    if item[0] == key:
                        del job.pending[index]
                        break
                job.receipts.pop(key, None)
                events = job.record['events']
                for index in range(len(events) - 1, -1, -1):
                    if events[index] is accepted:
                        del events[index]
                        break
                self.wake.notify_all()
            raise
        with self.wake:
            ready.set()
            self.wake.notify_all()
        return deepcopy(receipt)

    def _event_data(self, job, kind, key=None, status=None, message=None, command=None):
        event = {'type': kind, 'time_s': job.session.time if job.session else 0.}
        if key:
            event.update(command_id=key, command_status=status, message=message)
        if command:
            event['command'] = command
        if job.session:
            event['parameter_revision'] = job.session.revision
        return event

    def _event(self, job, kind, key=None, status=None, message=None, command=None):
        self._append_event(job, self._event_data(job, kind, key, status, message, command))

    def _append_event(self, job, event):
        events = job.record['events']
        events.append(event)
        if len(events) > EVENT_LIMIT:
            del events[:len(events) - EVENT_LIMIT]

    def _archive_record(self, job):
        """Snapshot of the record metadata (without the history list) for the writer."""
        record = {key: value for key, value in job.record.items() if key != 'history'}
        record['events'] = list(job.record.get('events') or ())
        return record

    def _overview_payload(self, job):
        return {'rows': [value for _, value in job.overview], 'stride': job.stride}

    def _enqueue_archive(self, job, row=None, overview=None):
        """Queue an in-memory snapshot for the writer; the caller holds the global lock."""
        if self.archive is None:
            return
        self.archive.enqueue(job, self._archive_record(job), [row] if row is not None else [],
                             job.published, job.request.history_window, overview)

    def _persist(self, job):
        """Write the current record through the writer; must not be called holding the lock."""
        if self.archive is None:
            return
        with self.wake:
            record = self._archive_record(job)
            total_rows = job.published
            window = job.request.history_window
            overview = self._overview_payload(job) if job.overview else None
        self.archive.enqueue(job, record, [], total_rows, window, overview, wait=True)

    def _archive_throttle(self, job):
        if self.archive is not None:
            self.archive.throttle(job)

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
                    ready = bool(job.pending) and job.pending[0][2].is_set()
                    if ready or job.record['status'] == 'queued' or job.archive_error is not None \
                            or job.record['status'] == 'running' and job.due <= now:
                        if self.active < 2:
                            job.busy = True
                            self.active += 1
                            self.pool.submit(self._tick, job)
                    elif job.record['status'] == 'running':
                        due.append(job.due)
                self.wake.wait(timeout=max(.001, min(due) - now) if due and self.active < 2 else .05)

    def _publish(self, job, frame):
        # Frame objects are never exposed to clients; history is shaped before publication.
        request = job.request
        # Marked first: a frame rejected below must not be published again by _finish.
        job.last_sequence = frame.sequence
        row = frame.model_dump(mode='json')
        selected = request.selected_variables or request.project.selected_variables
        if selected:
            missing = set(selected) - row['variables'].keys()
            if missing:
                raise CompilationError('TREND_VARIABLE_UNKNOWN', f'未知观察变量：{sorted(missing)}')
            row['variables'] = {key: row['variables'][key] for key in selected}
        job.record['frame'] = deepcopy(row)
        history = job.record['history']
        if history and history[-1]['time_s'] == row['time_s']:
            return
        index = job.published
        script_outputs = {key for script in request.project.control_scripts if script.enabled for key in script.outputs}
        trend = {k for k in row['variables'] if k in request.trend_variables or k in script_outputs
                 or '.state.' in k or k.startswith(('controller.', 'script.'))}
        if request.history == 'trend':
            missing = set(request.trend_variables) - frame.variables.keys()
            if missing:
                raise CompilationError('TREND_VARIABLE_UNKNOWN', f'未知曲线变量：{sorted(missing)}')
            # ~50 key frames per run, or per history window when the run is longer (or endless).
            every = max(1, math.ceil(min(request.frame_count() or request.history_window, request.history_window) / 50))
            if index % every and not job.session.done and job.record['status'] != 'paused':
                row['variables'] = {k: v for k, v in row['variables'].items() if k in trend}
                row['full'] = False
        history.append(row)
        job.published += 1
        if len(history) > request.history_window:
            del history[:len(history) - request.history_window]
        update_overview = index % job.stride == 0
        overview_payload = None
        if update_overview:
            # The overview keeps only curve variables (all when none are declared), no diagnostics.
            slim = dict(row, diagnostics=[])
            if request.trend_variables:
                slim['variables'] = {k: row['variables'][k] for k in trend if k in row['variables']}
                slim['full'] = slim['variables'] == row['variables'] and row['full']
            job.overview.append((index, slim))
            job.overview_pending += 1
            if len(job.overview) > OVERVIEW_POINTS:
                job.stride *= 2
                job.overview = [item for item in job.overview if item[0] % job.stride == 0]
                job.overview_dirty = True
            now = time.monotonic()
            if job.overview_dirty or (job.overview_pending >= ARCHIVE_OVERVIEW_FRAMES
                                      and now >= job.overview_due):
                overview_payload = self._overview_payload(job)
                job.overview_dirty = False
                job.overview_pending = 0
                job.overview_due = now + ARCHIVE_OVERVIEW_S
        self._enqueue_archive(job, (index, row), overview_payload)

    def _finish(self, job, status, error=None, applied_key=None):
        """Terminalize a run. Worker close and the final disk write happen outside the lock;
        the terminal status only becomes visible once its record is durable."""
        session = job.session
        with self.wake:
            if job.record['status'] in TERMINAL:
                return
            job.finishing = True
            pending_frames = [f for f in session.frames if f.sequence > job.last_sequence] if session else []
        publish_error = None
        if session:
            # Event-boundary frames may have been accepted just before SolveFailed.
            # The session owns the Worker subprocesses, so it is closed even when
            # publishing a pending frame fails.
            try:
                for frame in pending_frames:
                    with self.wake:
                        self._publish(job, frame)
            except BaseException as failure:
                publish_error = failure
            finally:
                session.close()
        if publish_error is not None:
            raise publish_error
        with self.wake:
            extra_events = []
            if applied_key is not None:
                receipt = job.receipts.get(applied_key)
                if receipt is not None:
                    receipt[0].update(command_status='applied', applied_time_s=session.time if session else 0.)
                extra_events.append(self._event_data(job, 'command', applied_key, 'applied'))
            while job.pending:
                key, command, ready = job.pending.popleft()
                receipt = job.receipts.get(key)
                if receipt is not None:
                    receipt[0].update(command_status='rejected', message='运行已结束')
                extra_events.append(self._event_data(job, 'command', key, 'rejected', '运行已结束'))
            if error:
                diagnostic = getattr(error, 'diagnostic', DiagnosticError(error))
                frame = RunFrame(status='failed', valid=False, time_s=session.time if session else 0.,
                                 diagnostics=[diagnostic]).model_dump(mode='json')
            else:
                frame = job.record.get('frame')
                if frame:
                    frame = dict(frame)
                    frame['status'] = status
                    frame['valid'] = status == 'completed'
            history = job.record['history']
            if history and session and session.frames and history[-1].get('sequence') == session.frames[-1].sequence:
                # Preserve a full final accepted frame for inspecting any variable.
                history[-1] = session.frames[-1].model_dump(mode='json')
            events = list(job.record.get('events') or ())
            events.extend(extra_events)
            events.append(self._event_data(job, status))
            events = events[-EVENT_LIMIT:]
            view = {key: value for key, value in job.record.items() if key != 'history'}
            view['events'] = events
            view['status'] = status
            view['frame'] = frame
            total_rows = job.published
            window = job.request.history_window
            overview = self._overview_payload(job)
        try:
            if self.archive is not None:
                self.archive.enqueue(job, view, [], total_rows, window, overview, wait=True)
        except BaseException:
            with self.wake:
                job.finishing = False
            raise
        with self.wake:
            job.record['status'] = status
            job.record['frame'] = frame
            job.record['events'] = events
            job.finishing = False
            # Keep every active job; only completed records count toward retention.
            ended = [key for key, value in self.jobs.items() if value.record['status'] in TERMINAL]
            for key in ended[:-20]:
                del self.jobs[key]
            self.wake.notify_all()

    def _commands(self, job):
        """Drain queued commands; Worker RPCs run outside the global lock."""
        while True:
            with self.wake:
                if not job.pending:
                    return
                key, command, ready = job.pending[0]
                if not ready.is_set():
                    return
                job.pending.popleft()
                action = command.action
                session = job.session
            if action == 'stop':
                self._finish(job, 'cancelled', applied_key=key)
                return
            if action in ('pause', 'resume', 'step'):
                with self.wake:
                    receipt = job.receipts[key][0]
                    try:
                        if action == 'pause':
                            job.record['status'] = 'paused'
                        elif action == 'resume':
                            job.record['status'] = 'running'
                            job.due = time.monotonic()
                        else:
                            if job.record['status'] != 'paused':
                                raise ValueError('单步只能在暂停时执行')
                            job.stepping = True
                        receipt.update(command_status='applied', applied_time_s=session.time if session else 0.)
                        self._event(job, 'command', key, 'applied')
                    except ValueError as failure:
                        receipt.update(command_status='rejected', message=str(failure))
                        self._event(job, 'command', key, 'rejected', str(failure))
                self._persist(job)
                continue
            # set / controller / write: the Worker round-trip must not hold the global lock.
            try:
                if action == 'set':
                    session.set_parameter(command.instance_id, command.parameter_id, command.value)
                elif action == 'controller':
                    session.update_controller(command.controller_id, command.parameter_id, command.value)
                elif action == 'write':
                    session.write_variables(command.values or {})
                with self.wake:
                    receipt = job.receipts[key][0]
                    receipt.update(command_status='applied', applied_time_s=session.time)
                    self._event(job, 'command', key, 'applied')
            except ValueError as failure:
                with self.wake:
                    receipt = job.receipts[key][0]
                    receipt.update(command_status='rejected', message=str(failure))
                    self._event(job, 'command', key, 'rejected', str(failure))
            self._persist(job)

    def _tick(self, job):
        try:
            with self.wake:
                if job.archive_error is not None:
                    raise job.archive_error
            if job.session is None:
                project = self.project_factory(job.request.project, job.request.scenario_id)
                network = compile_project(project)
                if job.request.mode == 'steady':
                    frame = solve_steady(network)
                    with self.wake:
                        self._publish(job, frame)
                    self._finish(job, 'completed')
                    return
                session = SimulationSession(network, job.request.duration_s, job.request.dt_s, keep=SESSION_FRAMES)
                job.session = session
                frame = session.initialize()
                status = 'paused' if job.request.start_paused else 'running'
                with self.wake:
                    job.record['status'] = status
                    self._publish(job, frame)
                    self._event(job, status)
                    job.due = time.monotonic() + (job.request.dt_s / job.request.speed_ratio if job.request.execution_mode == 'realtime' else 0.)
                    # Hide the new status until its record is durable, so a disk failure
                    # cannot leave a visible `running` record without an archive write.
                    job.record['status'] = 'queued'
                    record = self._archive_record(job)
                    record['status'] = status
                    total_rows = job.published
                    window = job.request.history_window
                    overview = self._overview_payload(job)
                try:
                    if self.archive is not None:
                        self.archive.enqueue(job, record, [], total_rows, window, overview, wait=True)
                except BaseException:
                    raise
                with self.wake:
                    job.record['status'] = status
                    self.wake.notify_all()
                return
            self._commands(job)
            with self.wake:
                if job.record['status'] in TERMINAL or job.record['status'] == 'paused' and not job.stepping:
                    return
                if not job.stepping and job.request.execution_mode == 'realtime' and job.due > time.monotonic():
                    return
                if job.archive_error is not None:
                    raise job.archive_error
            frame = job.session.advance()
            with self.wake:
                self._publish(job, frame)
                finished = job.session.done
                stepping = job.stepping and not finished
                if stepping:
                    job.stepping = False
                    job.record['status'] = 'paused'
                    self._event(job, 'paused')
                elif not finished and job.request.execution_mode == 'realtime':
                    job.due += job.request.dt_s / job.request.speed_ratio
            if finished:
                self._finish(job, 'completed')
            elif stepping:
                self._persist(job)
            self._archive_throttle(job)
        except BaseException as error:
            try:
                self._finish(job, 'failed', error)
            except BaseException:
                with self.wake:
                    job.record['status'] = 'failed'
                    job.record['frame'] = RunFrame(status='failed', valid=False,
                        time_s=job.session.time if job.session else 0.,
                        diagnostics=[getattr(error, 'diagnostic', DiagnosticError(error))]).model_dump(mode='json')
                    job.finishing = False
                session = job.session
                if session:
                    try:
                        session.close()
                    except BaseException:
                        pass
        finally:
            with self.wake:
                job.busy = False
                self.active -= 1
                self.wake.notify_all()

    def close(self):
        with self.wake:
            self.closed = True
            self.wake.notify_all()
        # Let the scheduler observe `closed` and exit before the pool shuts down, so a
        # late `submit` cannot race the shutdown or keep the daemon thread alive.
        thread = self.thread
        if thread is not None:
            thread.join(timeout=2.0)
        self.pool.shutdown(wait=True, cancel_futures=True)
        for job in list(self.jobs.values()):
            if job.record['status'] in TERMINAL:
                continue
            try:
                self._finish(job, 'interrupted')
            except BaseException:
                with self.wake:
                    job.record['status'] = 'interrupted'
                    if job.record.get('frame'):
                        job.record['frame']['status'] = 'interrupted'
                        job.record['frame']['valid'] = False
                    job.finishing = False
                session = job.session
                if session:
                    try:
                        session.close()
                    except BaseException:
                        pass
        if self.archive is not None:
            self.archive.close()


def DiagnosticError(error):
    from .models import Diagnostic
    return Diagnostic(code=getattr(error, 'code', 'SOLVER_ERROR'), message=str(error))
