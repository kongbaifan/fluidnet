"""Reproduce review observations in isolated example workspaces, without edits to FluidNet.

Run from the repository root: python -X utf8 output/reports/evidence/review_probes.py
An observation marked True confirms the described limitation; it is not a product test pass.
"""
from __future__ import annotations

import copy
import hashlib
import json
import platform
import queue
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / ".runtime/python"), str(ROOT)]

import numpy as np

from fluidnet.compiler import compile_project
from fluidnet.errors import ConvergenceError
from fluidnet.examples import controlled, parallel_network
from fluidnet.hydraulics import solve_hydraulics
from fluidnet.jobs import worker
from fluidnet.models import RunRequest
from fluidnet.simulation import SimulationSession
from fluidnet.storage import Recorder, read_history


def tolerance_probe(_folder):
    fields = ("mass_atol", "mass_rtol", "pressure_atol", "pressure_rtol")
    baseline = solve_hydraulics(compile_project(parallel_network()))
    variants = []
    for field in fields:
        for value in (1e-15, 100.0 if field.endswith("atol") else 0.5):
            project = parallel_network()
            setattr(project.options, field, value)
            result = solve_hydraulics(compile_project(project))
            variants.append({
                "field": field, "value": value,
                "same_pressures": bool(np.array_equal(result.pressures, baseline.pressures)),
                "same_flows": bool(np.array_equal(result.flows, baseline.flows)),
                "same_iteration_history": result.history == baseline.history,
                "iterations": result.iterations,
                "mass_residual_kg_s": result.mass_residual,
                "pressure_residual_pa": result.pressure_residual,
            })
    return {
        "id": "R01", "finding": "F01",
        "description": "Changing each hydraulic tolerance leaves the complete iteration history and solution unchanged.",
        "method": "Unmodified hydraulic solver; built-in parallel network; 8 one-field variants plus baseline.",
        "observed": all(v["same_pressures"] and v["same_flows"] and v["same_iteration_history"] for v in variants),
        "baseline_options": parallel_network().options.model_dump(),
        "baseline_iterations": baseline.iterations,
        "variants": variants,
    }


def recorder_probe(folder):
    frame = {"time_s": 0.0, "elements": {"pipe": {"mass_flow_kg_s": 1.0}}}
    # Advancing this clock without append reproduces the paused worker condition.
    with patch("fluidnet.storage.time.monotonic", return_value=100.0) as clock:
        recorder = Recorder(folder, ["pipe.mass_flow_kg_s"])
        recorder.append(frame)
        clock.return_value = 110.0
        before = read_history(folder)
        buffered = len(recorder.rows)
        recorder.flush()
        after = read_history(folder)
    return {
        "id": "R02", "finding": "F07",
        "description": "Unflushed curve tail remains invisible even after the 2-second threshold when no append occurs.",
        "method": "Real Recorder/read_history and isolated files; wall clock advanced by 10 seconds with a mock; explicit flush control.",
        "observed": before["total_rows"] == 0 and buffered == 1 and after["total_rows"] == 1,
        "buffered_rows_before_flush": buffered,
        "history_rows_after_10_seconds_without_append": before["total_rows"],
        "history_rows_after_explicit_flush": after["total_rows"],
    }


class CongestedOutput:
    """Real bounded queue kept full for non-final sends; consumer frees space for final."""
    def __init__(self):
        self.buffer = queue.Queue(maxsize=16)
        for i in range(16):
            self.buffer.put_nowait({"preloaded": i})
        self.dropped = []
        self.final = None

    def put_nowait(self, message):
        try:
            self.buffer.put_nowait(message)
        except queue.Full:
            self.dropped.append({k: v for k, v in message.items() if k != "frame"})
            raise

    def put(self, message, timeout):
        # Simulates a delayed consumer beginning to drain at final delivery.
        self.buffer.get_nowait()
        self.buffer.put(message, timeout=timeout)
        self.final = message


def congestion_probe(folder):
    commands = queue.Queue()
    commands.put({"command_id": "review-rejected", "action": "set", "element_id": "trunk", "parameter": "length_m", "value": 25})
    commands.put({"command_id": "review-stop", "action": "stop"})
    output = CongestedOutput()
    request = RunRequest(project=parallel_network(), mode="dynamic", start_paused=True, duration_s=1)
    worker(request.model_dump(), str(folder), commands, output)
    events = json.loads((folder / "events.json").read_text(encoding="utf-8"))
    dropped_ids = [message.get("command_id") for message in output.dropped if message.get("command_id")]
    return {
        "id": "R03", "finding": "F08",
        "description": "Both rejection and successful command acknowledgements are dropped by the worker under output queue saturation.",
        "method": "Unmodified worker with an injected full 16-item queue; final send allowed after one consumer read. Not a production load benchmark.",
        "observed": dropped_ids == ["review-rejected", "review-stop"] and len(events) == 2 and output.final["status"] == "stopped",
        "dropped_command_ids": dropped_ids,
        "persisted_command_events": events,
        "final_status": output.final["status"],
    }


def state_probe(_folder):
    session = SimulationSession(controlled(), dt_s=0.1)
    controls_before = copy.deepcopy(session.controllers)
    physical_before = copy.deepcopy((session.volumes, session.pipes))
    speed_before = session.net.parameters["pump"]["speed_ratio"]
    failure_code = None
    with patch.object(session, "_attempt_step", side_effect=ConvergenceError("REVIEW_INJECTED_FAILURE", "Review-only rejected physical trial")) as attempt:
        try:
            session.advance()
        except ConvergenceError as exc:
            failure_code = exc.diagnostic.code
    controls_changed = controls_before != session.controllers
    physical_unchanged = physical_before == (session.volumes, session.pipes)
    return {
        "id": "R04", "finding": "F04",
        "description": "A failed physical advance leaves controller state/target changed while physical time remains at the old accepted state.",
        "method": "Fault injection at _attempt_step; all physical attempts rejected. Does not establish occurrence or frequency in ordinary projects.",
        "observed": controls_changed and physical_unchanged and session.time_s == 0 and failure_code == "REVIEW_INJECTED_FAILURE",
        "rejected_attempts": attempt.call_count,
        "time_s_after_failure": session.time_s,
        "physical_state_unchanged": physical_unchanged,
        "controller_before": controls_before,
        "controller_after": session.controllers,
        "pump_speed_before": speed_before,
        "pump_speed_after": session.net.parameters["pump"]["speed_ratio"],
        "controller_in_last_valid_frame": session.frame["elements"]["controller"],
        "status": session.status,
        "last_valid_state": session.frame.get("last_valid_state"),
    }


def await_state(client, run_id, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        response.raise_for_status()
        state = response.json()
        if predicate(state):
            return state
        time.sleep(0.04)
    raise RuntimeError(f"Timed out waiting for isolated review run: {state.get('status')}")


def correlation_probe(folder):
    from fastapi.testclient import TestClient
    from fluidnet.api import create_app

    with TestClient(create_app(folder, seed=False)) as client:
        response = client.post("/api/v1/runs", json={"project": parallel_network().model_dump(), "mode": "dynamic", "start_paused": True, "duration_s": 1})
        response.raise_for_status()
        run_id = response.json()["run_id"]
        state = await_state(client, run_id, lambda s: s["status"] in {"paused", "failed"})
        if state["status"] != "paused":
            raise RuntimeError("Review example failed to initialize")
        acknowledgement = client.post(f"/api/v1/runs/{run_id}/commands", json={"action": "set", "element_id": "trunk", "parameter": "length_m", "value": 25})
        acknowledgement.raise_for_status()
        command_id = acknowledgement.json()["command_id"]
        state = await_state(client, run_id, lambda s: bool(s.get("command_error")))
        events = client.get(f"/api/v1/runs/{run_id}/events").json()
        with client.websocket_connect(f"/api/v1/runs/{run_id}/stream") as stream:
            stream_state = stream.receive_json()
        client.post(f"/api/v1/runs/{run_id}/commands", json={"action": "stop"}).raise_for_status()
        await_state(client, run_id, lambda s: s["status"] in {"stopped", "failed"})
    return {
        "id": "R05", "finding": "F08",
        "description": "REST acceptance includes command_id, but the subsequent command error in both status and WebSocket lacks it.",
        "method": "Real in-process HTTP/WebSocket app with its spawned worker and a fresh isolated SQLite workspace; no congestion injection.",
        "observed": bool(command_id) and "command_id" not in state and "command_id" not in stream_state and any(e.get("command_id") == command_id for e in events),
        "http_status": acknowledgement.status_code,
        "received_command_id": command_id,
        "status_command_error": state["command_error"],
        "status_has_command_id": "command_id" in state,
        "websocket_command_error": stream_state.get("command_error"),
        "websocket_has_command_id": "command_id" in stream_state,
        "event_lookup_retains_command_id": any(e.get("command_id") == command_id for e in events),
    }


def main():
    work = ROOT / ".cache" / "review-probes" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    work.mkdir(parents=True)
    observations = []
    for probe in (tolerance_probe, recorder_probe, congestion_probe, state_probe, correlation_probe):
        folder = work / probe.__name__
        folder.mkdir()
        try:
            result = probe(folder)
        except Exception as exc:
            result = {"probe": probe.__name__, "observed": False, "error": f"{type(exc).__name__}: {exc}"}
        observations.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    source_hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "fluidnet").glob("*.py"))}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python": platform.python_version(), "platform": platform.platform(),
        "workspace": str(work), "source_sha256": source_hashes,
        "meaning": "observed=true confirms the review limitation; it does not mean a product acceptance test passed.",
        "observations": observations,
    }
    (Path(__file__).parent / "review-probes.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(r["observed"] for r in observations) else 1


if __name__ == "__main__":
    raise SystemExit(main())
