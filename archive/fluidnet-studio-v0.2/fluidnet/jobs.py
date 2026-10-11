from __future__ import annotations

import copy
import multiprocessing as mp
import queue
import threading
import time
import traceback
from pathlib import Path

from .errors import ModelError
from .models import RunCommand, RunRequest, new_id
from .simulation import SimulationSession
from .solver import solve_steady
from .storage import Recorder, atomic_json


TERMINAL = {"completed", "stopped", "failed", "event", "interrupted"}


def worker(request_dict, folder_string, commands, output):
    request = RunRequest.model_validate(request_dict)
    folder = Path(folder_string)
    session = None
    recorder = None
    events = []
    last_frame = None
    def emit(status, frame=None, final=False, **extra):
        message = {"status": status, "frame": frame, "final": final, **extra}
        if final:
            output.put(message, timeout=10)
        else:
            try:
                output.put_nowait(message)
            except queue.Full:
                pass
    try:
        emit("running")
        selected = request.selected_variables if request.selected_variables is not None else request.project.selected_variables
        if request.mode == "steady":
            last_frame = solve_steady(request.project)
            recorder = Recorder(folder, selected)
            recorder.append(last_frame)
            recorder.flush()
            atomic_json(folder / "result.json", last_frame)
            atomic_json(folder / "events.json", [])
            emit("completed", last_frame, True)
            return
        session = SimulationSession(request.project, request.dt_s)
        recorder = Recorder(folder, selected)
        recorder.append(session.frame)
        paused = request.start_paused
        session.status = "paused" if paused else "running"
        session._annotate()
        last_frame = copy.deepcopy(session.frame)
        emit(session.status, last_frame)
        wall_anchor, sim_anchor = time.monotonic(), session.time_s
        last_emission = 0.0
        stopped = False
        while session.time_s < request.duration_s - 1e-10:
            one_step = False
            while True:
                try:
                    data = commands.get_nowait()
                except queue.Empty:
                    break
                command_id = data.pop("command_id")
                try:
                    command = RunCommand.model_validate(data)
                    if command.action == "stop":
                        stopped = True
                    elif command.action == "pause":
                        paused = True
                    elif command.action == "resume":
                        paused = False
                        wall_anchor, sim_anchor = time.monotonic(), session.time_s
                    elif command.action == "step":
                        if not paused:
                            raise ModelError("STEP_REQUIRES_PAUSE", "请先暂停，再单步推进")
                        one_step = True
                    elif command.action == "set":
                        session.set_parameter(command.element_id, command.parameter, command.value)
                    events.append({"command_id": command_id, "time_s": session.time_s, "accepted": True, **command.model_dump()})
                    session.status = "paused" if paused else "running"
                    session._annotate()
                    emit(session.status, copy.deepcopy(session.frame), command_id=command_id)
                except ModelError as exc:
                    events.append({"command_id": command_id, "time_s": session.time_s, "accepted": False, "diagnostic": exc.diagnostic.to_dict()})
                    emit("paused" if paused else "running", command_id=command_id, command_error=exc.diagnostic.to_dict())
                atomic_json(folder / "events.json", events + session.events)
            if stopped:
                break
            if paused and not one_step:
                time.sleep(0.015)
                continue
            if not one_step:
                due = wall_anchor + (session.time_s - sim_anchor) / request.speed
                if due > time.monotonic():
                    time.sleep(min(0.02, due - time.monotonic()))
                    continue
            session.advance(min(request.dt_s, request.duration_s - session.time_s))
            last_frame = copy.deepcopy(session.frame)
            recorder.append(last_frame)
            if time.monotonic() - last_emission >= 0.1 or one_step or session.status == "event":
                emit("event" if session.status == "event" else ("paused" if paused else "running"), last_frame)
                last_emission = time.monotonic()
            if session.status == "event":
                break
        recorder.flush()
        status = "stopped" if stopped else ("event" if session.status == "event" else "completed")
        session.status = status
        session._annotate()
        last_frame = session.frame
        atomic_json(folder / "result.json", last_frame)
        atomic_json(folder / "events.json", events + session.events)
        emit(status, last_frame, True)
    except Exception as exc:
        if recorder:
            recorder.flush()
        diagnostic = exc.diagnostic.to_dict() if isinstance(exc, ModelError) else {
            "code": "WORKER_ERROR", "message": str(exc), "severity": "error", "element_id": None}
        if session is not None:
            last_frame = copy.deepcopy(session.frame)
            last_frame["last_valid_state"] = True
            if diagnostic not in last_frame["diagnostics"]:
                last_frame["diagnostics"].append(diagnostic)
        else:
            last_frame = {"status": "failed", "valid": False, "time_s": 0,
                          "elements": {}, "ports": {}, "diagnostics": [diagnostic], "metrics": {}}
        last_frame["simulation_status"] = "failed"
        atomic_json(folder / "result.json", last_frame)
        (folder / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        emit("failed", last_frame, True)


class JobManager:
    def __init__(self, store, max_workers=2):
        self.store = store
        self.max_workers = max_workers
        self.context = mp.get_context("spawn")
        self.handles = {}
        self.lock = threading.RLock()
        self.closing = threading.Event()
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def submit(self, request: RunRequest):
        rid, folder = self.store.create_run(request)
        with self.lock:
            self.handles[rid] = {"request": request.model_dump(), "folder": str(folder),
                "status": "queued", "frame": None, "sequence": 0, "process": None,
                "commands": self.context.Queue(), "output": self.context.Queue(maxsize=16),
                "last_store": 0, "command_error": None}
        return rid

    def state(self, run_id):
        with self.lock:
            item = self.handles.get(run_id)
            if item:
                return {"id": run_id, "status": item["status"], "frame": item["frame"],
                        "sequence": item["sequence"], "command_error": item.get("command_error")}
        run = self.store.get_run(run_id)
        return {"id": run_id, "status": run["status"], "frame": run["frame"], "sequence": 0}

    def command(self, run_id, command):
        with self.lock:
            item = self.handles.get(run_id)
            if command.action == "reset":
                run = self.store.get_run(run_id)
                if item and item["status"] not in TERMINAL:
                    self.command(run_id, RunCommand(action="stop"))
                request = RunRequest.model_validate(run["request"])
                request.start_paused = True
                return {"run_id": self.submit(request), "action": "reset"}
            if not item or item["status"] in TERMINAL:
                raise ModelError("RUN_NOT_ACTIVE", "任务已经结束")
            if item["status"] == "queued":
                if command.action == "stop":
                    item["status"] = "stopped"
                    item["sequence"] += 1
                    self.store.update_run(run_id, "stopped")
                    return {"accepted": True}
                raise ModelError("RUN_QUEUED", "任务尚在队列中")
            if item["request"]["mode"] == "steady":
                if command.action == "stop":
                    item["process"].terminate()
                    item["status"] = "stopped"
                    item["sequence"] += 1
                    self.store.update_run(run_id, "stopped")
                    return {"accepted": True}
                raise ModelError("STEADY_COMMAND", "稳态任务仅支持停止或重置")
            cid = new_id()
            item["commands"].put({"command_id": cid, **command.model_dump()})
            return {"accepted": True, "command_id": cid}

    def _monitor(self):
        while not self.closing.is_set():
            with self.lock:
                active = sum(h["process"] is not None and h["process"].is_alive() for h in self.handles.values())
                for rid, h in list(self.handles.items()):
                    if h["status"] == "queued" and active < self.max_workers:
                        process = self.context.Process(target=worker, args=(h["request"], h["folder"], h["commands"], h["output"]), daemon=True)
                        process.start()
                        h["process"], h["status"] = process, "running"
                        h["sequence"] += 1
                        active += 1
                        self.store.update_run(rid, "running")
                    while True:
                        try:
                            message = h["output"].get_nowait()
                        except queue.Empty:
                            break
                        h["status"] = message["status"]
                        h["sequence"] += 1
                        h["command_error"] = message.get("command_error")
                        if message.get("frame") is not None:
                            h["frame"] = message["frame"]
                        now = time.monotonic()
                        if message["final"] or now - h["last_store"] > 1:
                            self.store.update_run(rid, h["status"], h["frame"])
                            h["last_store"] = now
                    process = h["process"]
                    if process and not process.is_alive() and h["status"] not in TERMINAL:
                        # A queue feeder can finish shortly after the process; a final
                        # result on disk is authoritative after the queue is drained.
                        path = Path(h["folder"]) / "result.json"
                        if path.exists():
                            import json
                            frame = json.loads(path.read_text(encoding="utf-8"))
                            h["frame"] = frame
                            h["status"] = frame.get("simulation_status", "completed" if frame.get("valid") else "failed")
                        else:
                            h["status"] = "failed"
                            h["frame"] = {"valid": False, "elements": {}, "diagnostics": [{"code": "PROCESS_EXIT", "message": f"工作进程意外退出（{process.exitcode}）", "severity": "error"}]}
                        h["sequence"] += 1
                        self.store.update_run(rid, h["status"], h["frame"])
            self.closing.wait(0.04)

    def close(self):
        self.closing.set()
        self.thread.join(timeout=3)
        with self.lock:
            for rid, h in self.handles.items():
                process = h["process"]
                if process and process.is_alive():
                    process.terminate()
                    process.join(timeout=3)
                    self.store.update_run(rid, "interrupted", h["frame"])
                for name in ("commands", "output"):
                    h[name].close()
