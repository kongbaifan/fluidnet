"""Run-control regression tests: cancellation, pause/resume, and terminal records.

Every polling loop here is bounded by an explicit iteration cap so a regression
can never hang the suite.
"""
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.catalog import catalog_map
from fn_engine.models import Connection, Endpoint, ModuleDefinition, ModuleInstance, Project
from fn_engine.packages import load_module_package

ROOT = Path(__file__).parents[1]
POLL_CAP = 600


def custom_module() -> ModuleDefinition:
    return load_module_package(ROOT / "modules" / "programmable_valve")


def custom_project(module: ModuleDefinition | None = None) -> Project:
    module = module or custom_module()
    return Project(
        id="custom-valve-project",
        name="可编程阀门验收",
        modules=[catalog_map()["source"], module],
        instances=[
            ModuleInstance(id="B1", module_id="source", name="入口", parameters={"pressure_pa": 250000.0}),
            ModuleInstance(id="V1", module_id=module.id, name="可编程阀",
                           parameters={"opening_ratio": 0.5, "kv_m3_h": 10.0}),
            ModuleInstance(id="B2", module_id="source", name="出口", parameters={"pressure_pa": 120000.0}),
        ],
        connections=[
            Connection(id="e1", source=Endpoint(instance_id="B1", port_id="out0"),
                       target=Endpoint(instance_id="V1", port_id="in0")),
            Connection(id="e2", source=Endpoint(instance_id="V1", port_id="out0"),
                       target=Endpoint(instance_id="B2", port_id="out0")),
        ],
    )


def failing_project(exception: str = "TypeError") -> Project:
    """Project whose Python module raises a non-`ValueError` inside the Worker."""
    project = custom_project()
    module = project.modules[-1]
    module.content_hash = None
    module.definition_hash = None
    module.source["runtime"] = (
        "class Module:\n"
        "    def evaluate(self, ctx):\n"
        f"        raise {exception}('boom')\n"
    )
    return project


def slow_module(delay_s: float = 0.02) -> ModuleDefinition:
    """Programmable valve with a deliberate per-evaluate delay.

    Lets a test land a `stop`/`pause` mid-timeline deterministically: each frame
    costs several Worker round-trips, so the cancel window is wide.
    """
    module = custom_module()
    module.content_hash = None
    module.definition_hash = None
    module.source["runtime"] = module.source["runtime"].replace(
        "    def evaluate(self, ctx):\n",
        f"    def evaluate(self, ctx):\n        import time\n        time.sleep({delay_s!r})\n",
    )
    return module


def probed_module(probe: Path) -> ModuleDefinition:
    """Programmable valve whose `commit_step` appends a byte to `probe`.

    `commit_step` runs once per committed timeline frame, so the probe file is an
    observable count of *completed frames* outside the Worker - which lets a test
    cancel only once real partial frames exist, instead of racing startup.
    """
    module = custom_module()
    module.content_hash = None
    module.definition_hash = None
    module.source["runtime"] = module.source["runtime"].replace(
        "    def commit_step(self, ctx, dt_s):\n",
        "    def commit_step(self, ctx, dt_s):\n"
        "        import os\n"
        "        path = os.environ.get('FLUIDNET_TEST_PROBE')\n"
        "        if path:\n"
        "            with open(path, 'a', encoding='utf-8') as handle:\n"
        "                handle.write('.')\n",
    )
    return module


def wait_for_probe(probe: Path, count: int) -> int:
    seen = 0
    for _ in range(POLL_CAP):
        seen = len(probe.read_text(encoding="utf-8")) if probe.exists() else 0
        if seen >= count:
            break
        time.sleep(0.01)
    return seen


def dynamic_request(project: Project, duration_s: float = 1.0, dt_s: float = 0.05) -> dict:
    return {"project": project.model_dump(mode="json"), "mode": "dynamic",
            "duration_s": duration_s, "dt_s": dt_s}


def wait_terminal(client: TestClient, run_id: str):
    """Poll until the record is terminal, with a hard iteration cap."""
    record = None
    for _ in range(POLL_CAP):
        record = client.get(f"/api/v1/runs/{run_id}").json()
        if record["status"] in {"completed", "failed", "cancelled"}:
            return record
        time.sleep(0.02)
    return record


def wait_finalized(client: TestClient, run_id: str):
    """Like `wait_terminal`, but also waits for the solving thread to finish.

    A `stop` publishes `cancelled` immediately while the frame in flight keeps
    running; the final record is the one that carries a frame.
    """
    record = None
    for _ in range(POLL_CAP):
        record = client.get(f"/api/v1/runs/{run_id}").json()
        if record["status"] in {"completed", "failed", "cancelled"} and record["frame"] is not None:
            return record
        time.sleep(0.02)
    return record


def wait_running(client: TestClient, run_id: str) -> bool:
    for _ in range(POLL_CAP):
        if client.get(f"/api/v1/runs/{run_id}").json()["status"] == "running":
            return True
        time.sleep(0.01)
    return False


def test_background_run_can_be_cancelled(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        response = client.post("/api/v1/runs?background=true", json=dynamic_request(custom_project()))
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        assert wait_running(client, run_id)

        command = client.post(f"/api/v1/runs/{run_id}/command", json={"action": "stop"})
        assert command.status_code == 200, command.text
        assert command.json()["command_status"] == "accepted"

        record = wait_terminal(client, run_id)
        assert record is not None and record["status"] == "cancelled", record
        events = client.get(f"/api/v1/runs/{run_id}/events").json()["events"]
        assert any(event["type"] == "cancelled" for event in events), events

        # `stop` publishes the cancelled event at once; the record write must
        # then supersede it rather than append a second one, so that a CLI or a
        # scripted poller never sees the same terminal transition twice.
        endpoint = wait_finalized(client, run_id)
        assert endpoint["status"] == "cancelled", endpoint
        settled = client.get(f"/api/v1/runs/{run_id}/events").json()["events"]
        assert [event["type"] for event in settled].count("cancelled") == 1, settled

        # Two shapes of "stop again", and they differ: a *sequential* second stop
        # on a record that is already terminal is refused with 409 rather than
        # silently accepted, while a second stop racing the first in the
        # not-yet-terminal window is absorbed by the terminal-status guard and
        # the tail check, adding nothing. The browser test's second stop targets
        # the gap window, so both halves of that have to hold.
        again = client.post(f"/api/v1/runs/{run_id}/command", json={"action": "stop"})
        assert again.status_code == 409, again.text
        assert again.json()["detail"]["code"] == "RUN_ALREADY_FINISHED"
        assert [event["type"] for event in
                client.get(f"/api/v1/runs/{run_id}/events").json()["events"]].count("cancelled") == 1


def test_command_on_unknown_and_finished_runs(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        missing = client.post("/api/v1/runs/nope/command", json={"action": "stop"})
        assert missing.status_code == 404, missing.text

        created = client.post("/api/v1/runs?background=true",
                              json=dynamic_request(custom_project(), .2, .1)).json()
        run_id = created["run_id"]
        record = wait_terminal(client, run_id)
        assert record["status"] == "completed", record
        finished = client.post(f"/api/v1/runs/{run_id}/command", json={"action": "stop"})
        assert finished.status_code == 409, finished.text
        assert finished.json()["detail"]["code"] == "RUN_ALREADY_FINISHED"


def test_background_failure_is_terminal_not_stuck_running(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        response = client.post("/api/v1/runs?background=true", json=dynamic_request(failing_project()))
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        record = wait_terminal(client, run_id)
        assert record is not None and record["status"] == "failed", record
        assert record["frame"]["diagnostics"][0]["message"] == "boom"
        events = client.get(f"/api/v1/runs/{run_id}/events").json()["events"]
        assert any(event["type"] == "failed" for event in events), events


def test_blocking_run_reports_worker_fault(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        # A Worker fault is a `RuntimeErrorBase` (a `ValueError` subclass), so a
        # blocking run reports it as a failed record. Crucially it is a declared
        # 201 + terminal record, never a 500 traceback.
        payload = {"project": failing_project().model_dump(mode="json"), "mode": "steady"}
        response = client.post("/api/v1/runs", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "failed"
        assert body["frame"]["diagnostics"][0]["message"] == "boom"


def test_solve_endpoint_reports_worker_fault_without_500(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        response = client.post("/api/v1/solve", json=failing_project().model_dump(mode="json"))
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["message"] == "boom"


def test_pause_then_resume_reaches_completed(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        created = client.post("/api/v1/runs?background=true",
                              json=dynamic_request(custom_project(), 1.0, 0.05)).json()
        run_id = created["run_id"]
        assert wait_running(client, run_id)

        paused = client.post(f"/api/v1/runs/{run_id}/command", json={"action": "pause"})
        assert paused.status_code == 200, paused.text
        # Give the timeline loop time to reach the pause barrier; it must still
        # be parked there instead of racing to completion.
        time.sleep(0.4)
        assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "paused"

        resumed = client.post(f"/api/v1/runs/{run_id}/command", json={"action": "resume"})
        assert resumed.status_code == 200, resumed.text
        record = wait_terminal(client, run_id)
        assert record is not None and record["status"] == "completed", record


@pytest.mark.parametrize("action", ["step", "set"])
def test_invalid_step_and_set_are_reported_in_command_events(tmp_path, action):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        created = client.post("/api/v1/runs?background=true",
                              json=dynamic_request(custom_project(), 1.0, 0.05)).json()
        run_id = created["run_id"]
        assert wait_running(client, run_id)
        response = client.post(f"/api/v1/runs/{run_id}/command", json={"action": action})
        assert response.status_code == 200, response.text
        key=response.json()['command_id']
        for _ in range(POLL_CAP):
            events=client.get(f'/api/v1/runs/{run_id}/events').json()['events']
            result=next((e for e in reversed(events) if e.get('command_id')==key),{})
            if result.get('command_status')=='rejected': break
            time.sleep(.01)
        assert result['command_status']=='rejected' 
        assert client.post(f"/api/v1/runs/{run_id}/command", json={"action": "stop"}).status_code == 200
        wait_terminal(client, run_id)


def test_cancellation_does_not_poison_the_executor(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        created = client.post("/api/v1/runs?background=true",
                              json=dynamic_request(custom_project(), 1.0, 0.05)).json()
        run_id = created["run_id"]
        assert wait_running(client, run_id)
        assert client.post(f"/api/v1/runs/{run_id}/command", json={"action": "stop"}).status_code == 200
        assert wait_terminal(client, run_id)["status"] == "cancelled"

        # A fresh run still completes on the same executor: no leaked worker and
        # no poisoned thread pool.
        again = client.post("/api/v1/runs?background=true",
                            json=dynamic_request(custom_project(), .2, .1)).json()
        record = wait_terminal(client, again["run_id"])
        assert record is not None and record["status"] == "completed", record


def test_command_on_sync_run_is_rejected(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        # A blocking run has no control token; by the time the request returns it
        # is terminal, so the command is refused with a clear 409.
        result = client.post("/api/v1/runs", json=dynamic_request(custom_project(), .2, .1)).json()
        response = client.post(f"/api/v1/runs/{result['run_id']}/command", json={"action": "pause"})
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "RUN_ALREADY_FINISHED"


def test_health_declares_run_control_capability(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        capabilities = client.get("/api/v1/health").json()["capabilities"]
        assert capabilities["run_control"] is True
        assert capabilities["async_runs"] is True
        assert capabilities["thermal"] is True
        assert capabilities["property_coupling"] == ["reference", "node"]


def test_background_crash_before_record_write_is_terminalized(tmp_path, monkeypatch):
    """A fault compute_run cannot name must still terminalize the record."""
    import fn_engine.api as api

    def explode(*args, **kwargs):
        raise RuntimeError("solver exploded")

    from fn_engine.simulation import SimulationSession
    monkeypatch.setattr(SimulationSession, "initialize", explode)
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        created = client.post("/api/v1/runs?background=true",
                              json=dynamic_request(custom_project(), .2, .1)).json()
        record = wait_terminal(client, created["run_id"])
        assert record is not None and record["status"] == "failed", record
        assert record["frame"]["diagnostics"][0]["message"] == "solver exploded"
        events = client.get(f"/api/v1/runs/{created['run_id']}/events").json()["events"]
        assert any(event["type"] == "failed" for event in events), events


def test_cancel_closes_the_worker_subprocess(tmp_path, monkeypatch):
    from fn_engine.runtime import WorkerProcess

    processes = []
    original_close = WorkerProcess.close

    def tracked_close(self, force=False):
        processes.append(self.process)
        return original_close(self, force=force)

    monkeypatch.setattr(WorkerProcess, "close", tracked_close)
    slow = slow_module()
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        created = client.post("/api/v1/runs?background=true",
                              json=dynamic_request(custom_project(slow), 5.0, 0.05)).json()
        run_id = created["run_id"]
        assert wait_running(client, run_id)
        time.sleep(0.1)
        assert client.post(f"/api/v1/runs/{run_id}/command", json={"action": "stop"}).status_code == 200
        assert wait_finalized(client, run_id)["status"] == "cancelled"

    live = [process for process in processes if process is not None]
    assert live, "cancellation must run the Worker cleanup path"
    assert all(process.poll() is not None for process in live)


def test_cancel_keeps_partial_frames(tmp_path, monkeypatch):
    probe = tmp_path / "frames.log"
    monkeypatch.setenv("FLUIDNET_TEST_PROBE", str(probe))
    slow = probed_module(probe)
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        created = client.post("/api/v1/runs?background=true",
                              json=dynamic_request(custom_project(slow), 5.0, 0.05)).json()
        run_id = created["run_id"]
        assert wait_running(client, run_id)
        # Only stop once real frames have been committed, so the assertion below
        # cannot pass by accident of timing.
        assert wait_for_probe(probe, 2) >= 2
        assert client.post(f"/api/v1/runs/{run_id}/command", json={"action": "stop"}).status_code == 200

        record = wait_finalized(client, run_id)
        assert record is not None and record["status"] == "cancelled", record
        # Frames computed before the cancellation is observed are kept.
        assert client.get(f"/api/v1/runs/{run_id}/history").json()["total_rows"] >= 1
        assert record["frame"]["status"] == "cancelled"
        assert record["frame"]["time_s"] < 5.0


def test_paused_run_stays_paused(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        created=client.post('/api/v1/runs?background=true',json=dynamic_request(custom_project()) | {'start_paused':True}).json()
        run_id=created['run_id']
        for _ in range(POLL_CAP):
            record=client.get(f'/api/v1/runs/{run_id}').json()
            if record['status']=='paused':break
            time.sleep(.01)
        time.sleep(.3)
        record=client.get(f'/api/v1/runs/{run_id}').json()
        assert record['status']=='paused' and record['frame']['time_s']==0


def test_stop_then_engine_fault_still_reports_the_fault(tmp_path, monkeypatch):
    """A provisional `cancelled` must not be allowed to bury a real fault.

    `stop` publishes `cancelled` immediately; if the engine then dies before
    writing the final record, that provisional write would otherwise be the last
    one - a permanently frameless `cancelled` record instead of the failure.
    """
    import fn_engine.api as api

    def slow_explode(*args, **kwargs):
        time.sleep(0.4)
        raise RuntimeError("engine fault after stop")

    from fn_engine.simulation import SimulationSession
    monkeypatch.setattr(SimulationSession, "initialize", slow_explode)
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        created = client.post("/api/v1/runs?background=true",
                              json=dynamic_request(custom_project(), 1.0, 0.05)).json()
        run_id = created["run_id"]
        assert client.post(f"/api/v1/runs/{run_id}/command", json={"action": "stop"}).status_code == 200

        record = wait_finalized(client, run_id)
        assert record is not None and record["status"] == "failed", record
        assert record["frame"]["diagnostics"][0]["message"] == "engine fault after stop"

        events = client.get(f"/api/v1/runs/{run_id}/events").json()["events"]
        terminal = [event["type"] for event in events if event["type"] in {"completed", "failed", "cancelled"}]
        assert terminal == ["failed"], events


def test_queued_pause_resume_pause_preserves_order(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as client:
        run_id=client.post('/api/v1/runs?background=true',json=dynamic_request(custom_project(),3,.1) | {'start_paused':True}).json()['run_id']
        receipts=[]
        for action in ('pause','resume','pause'):
            receipts.append(client.post(f'/api/v1/runs/{run_id}/command',json={'action':action}).json()['command_id'])
        for _ in range(POLL_CAP):
            record=client.get(f'/api/v1/runs/{run_id}').json()
            applied=[e['command_id'] for e in record['events'] if e.get('command_status')=='applied']
            if len(applied)==3:break
            time.sleep(.01)
        assert applied==receipts
        assert record['status']=='paused'
