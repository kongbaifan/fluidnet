import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import (
    Connection,
    Endpoint,
    FluidConfig,
    ModuleDefinition,
    ModuleInstance,
    Project,
    PortSpec,
    ChannelSpec,
    ParameterSpec,
)
from fn_engine.packages import load_module_package
from fn_engine.properties import property_service
from fn_engine.solver import solve_steady


ROOT = Path(__file__).parents[1]


def custom_module():
    return load_module_package(ROOT / "modules" / "programmable_valve")


def custom_project():
    catalog = catalog_map()
    module = custom_module()
    return Project(
        id="custom-valve-project",
        name="可编程阀门验收",
        modules=[catalog["source"], module],
        instances=[
            ModuleInstance(id="B1", module_id="source", name="入口", parameters={"pressure_pa": 250000.0}),
            ModuleInstance(id="V1", module_id=module.id, name="可编程阀", parameters={"opening_ratio": 0.5, "kv_m3_h": 10.0}),
            ModuleInstance(id="B2", module_id="source", name="出口", parameters={"pressure_pa": 120000.0}),
        ],
        connections=[
            Connection(id="e1", source=Endpoint(instance_id="B1", port_id="out0"), target=Endpoint(instance_id="V1", port_id="in0")),
            Connection(id="e2", source=Endpoint(instance_id="V1", port_id="out0"), target=Endpoint(instance_id="B2", port_id="out0")),
        ],
    )


def test_coolprop_service_supports_single_phase_water_and_air():
    water = property_service(FluidConfig(fluid="Water", phase_policy="liquid")).state_pt(250000, 293.15)
    air = property_service(FluidConfig(fluid="Air", phase_policy="gas")).state_pt(250000, 293.15)
    assert water.density_kg_m3 > 900
    assert water.viscosity_pa_s > 0
    assert air.density_kg_m3 > 1
    assert "gas" in air.phase


def test_versioned_python_package_runs_in_worker_and_commits_once():
    module = custom_module()
    client = TestClient(create_app())
    response = client.post("/api/v1/modules/test", json={
        "module": module.model_dump(mode="json"),
        "parameters": {"opening_ratio": 0.5, "kv_m3_h": 10.0},
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content_hash"] == module.content_hash
    assert body["evaluation"]["relations"][0]["kind"] == "valve"
    assert body["committed"]["state"]["commit_count"] == 1


def test_module_catalog_discovers_versioned_package():
    response = TestClient(create_app()).get("/api/v1/modules")
    assert response.status_code == 200
    item = next(module for module in response.json()["modules"] if module["id"] == "programmable_valve")
    assert item["runtime"] == "python"
    assert len(item["package"]["content_hash"]) == 64


def test_python_module_relation_is_used_by_network_solver():
    frame = solve_steady(compile_project(custom_project()))
    assert frame.valid
    assert frame.variables["V1.mass_flow_kg_s"] > 0
    assert frame.variables["V1.param.opening_ratio"] == pytest.approx(0.5)


def test_module_default_is_not_overwritten_by_registered_builtin():
    module = custom_module().model_copy(update={
        "parameters": [ParameterSpec(id="opening_ratio", label="开度", default=0.25, minimum=0, maximum=1),
                        ParameterSpec(id="kv_m3_h", label="Kv", default=20.0, minimum=.001)]
    })
    project = custom_project()
    project.modules[-1] = module
    project.instances[1].parameters = {}
    compiled = compile_project(project)
    assert compiled.parameters["V1"]["opening_ratio"] == pytest.approx(0.25)
    assert compiled.parameters["V1"]["kv_m3_h"] == pytest.approx(20.0)


def test_dynamic_background_run_is_queryable():
    client = TestClient(create_app())
    response = client.post("/api/v1/runs?background=true", json={
        "project": custom_project().model_dump(mode="json"),
        "mode": "dynamic",
        "duration_s": 0.2,
        "dt_s": 0.1,
    })
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    for _ in range(50):
        status = client.get(f"/api/v1/runs/{run_id}").json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.02)
    assert status["status"] == "completed", status
    assert client.get(f"/api/v1/runs/{run_id}/events").json()["events"]
