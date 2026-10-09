import time

import pytest
from fastapi.testclient import TestClient

from fluidnet.api import create_app
from fluidnet.examples import parallel_network, single_pipe
from fluidnet.models import Project
from fluidnet.storage import ConflictError, Store, html_report


def wait_for(client, rid, statuses, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/v1/runs/{rid}").json()
        if data["status"] in statuses:
            return data
        time.sleep(0.04)
    pytest.fail(f"任务未进入状态 {statuses}: {data}")


def test_store_revisions_and_conflicts(tmp_path):
    store = Store(tmp_path)
    p = single_pipe()
    saved = store.save_project(p)
    assert saved.revision == 1
    with pytest.raises(ConflictError):
        store.save_project(p)
    saved.name = "新版本"
    assert store.save_project(saved).revision == 2
    assert store.get_project(p.id, 1).name != "新版本"
    store.close()


def test_api_steady_job_and_exports(tmp_path):
    with TestClient(create_app(tmp_path, seed=False)) as client:
        p = single_pipe().model_dump()
        response = client.post("/api/v1/projects", json=p)
        assert response.status_code == 200
        assert client.post("/api/v1/validate", json=p).json()["valid"]
        rid = client.post("/api/v1/runs", json={"project": p}).json()["run_id"]
        result = wait_for(client, rid, {"completed", "failed"})
        assert result["status"] == "completed", result
        assert result["frame"]["elements"]["pipe"]["mass_flow_kg_s"] > 0
        history = client.get(f"/api/v1/runs/{rid}/history").json()
        assert history["total_rows"] == 1
        assert "time_s" in client.get(f"/api/v1/runs/{rid}/results?format=csv").text
        assert "计算报告" in client.get(f"/api/v1/runs/{rid}/results?format=html").text


def test_dynamic_pause_single_step_and_stop(tmp_path):
    with TestClient(create_app(tmp_path, seed=False)) as client:
        rid = client.post("/api/v1/runs", json={"project": parallel_network().model_dump(),
            "mode": "dynamic", "start_paused": True, "duration_s": 20, "dt_s": 0.1}).json()["run_id"]
        state = wait_for(client, rid, {"paused", "failed"})
        assert state["status"] == "paused", state
        assert state["frame"]["time_s"] == 0
        response = client.post(f"/api/v1/runs/{rid}/commands", json={"action": "step"})
        assert response.status_code == 202
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = client.get(f"/api/v1/runs/{rid}").json()
            if state["frame"]["time_s"] > 0:
                break
            time.sleep(0.04)
        assert state["frame"]["time_s"] == pytest.approx(0.1)
        time.sleep(0.15)
        assert client.get(f"/api/v1/runs/{rid}").json()["frame"]["time_s"] == pytest.approx(0.1)
        client.post(f"/api/v1/runs/{rid}/commands", json={"action": "stop"})
        assert wait_for(client, rid, {"stopped", "failed"})["status"] == "stopped"


def test_report_escapes_project_content():
    project = single_pipe().model_dump()
    project["name"] = "<script>alert(1)</script>"
    output = html_report({"id": "test", "status": "completed", "request": {"project": project}, "frame": {}})
    assert "<script>" not in output
    assert "&lt;script&gt;" in output
