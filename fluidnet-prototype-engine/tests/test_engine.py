import json
from pathlib import Path

from fn_engine.bridge import normalize_prototype_export
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project, validate_project
from fn_engine.models import Connection, Endpoint, ModuleInstance, Project
from fn_engine.solver import solve_dynamic, solve_steady


def reference_project() -> Project:
    catalog = list(catalog_map().values())
    modules = {item.id: item for item in catalog}
    instances = [
        ModuleInstance(id="B1", module_id="source", name="供水边界", parameters={"pressure_pa": 250000.0, "temperature_k": 293.15}),
        ModuleInstance(id="P1", module_id="pump", name="循环泵"),
        ModuleInstance(id="N1", module_id="junction", name="分流节点"),
        ModuleInstance(id="V1", module_id="valve", name="调节阀", parameters={"opening_ratio": 0.8, "kv_m3_h": 16.0}),
        ModuleInstance(id="L1", module_id="pipe", name="管道"),
        ModuleInstance(id="B2", module_id="source", name="回水边界", parameters={"pressure_pa": 120000.0, "temperature_k": 293.15}),
    ]
    connections = [
        Connection(id="e1", source=Endpoint(instance_id="B1", port_id="out0"), target=Endpoint(instance_id="P1", port_id="in0")),
        Connection(id="e2", source=Endpoint(instance_id="P1", port_id="out0"), target=Endpoint(instance_id="N1", port_id="in0")),
        Connection(id="e3", source=Endpoint(instance_id="N1", port_id="out0"), target=Endpoint(instance_id="V1", port_id="in0")),
        Connection(id="e4", source=Endpoint(instance_id="V1", port_id="out0"), target=Endpoint(instance_id="L1", port_id="in0")),
        Connection(id="e5", source=Endpoint(instance_id="L1", port_id="out0"), target=Endpoint(instance_id="B2", port_id="out0")),
    ]
    return Project(id="reference", name="参考泵阀网络", modules=list(modules.values()), instances=instances, connections=connections)


def test_catalog_uses_canonical_units():
    valve = catalog_map()["valve"]
    opening = next(item for item in valve.parameters if item.id == "opening_ratio")
    assert opening.unit.canonical_unit == "1"
    assert opening.unit.display_unit == "%"
    assert opening.unit.from_canonical(0.65) == 65


def test_reference_project_compiles_and_solves():
    project = reference_project()
    assert not [item for item in validate_project(project) if item.severity == "error"]
    network = compile_project(project)
    frame = solve_steady(network)
    assert frame.valid
    assert frame.metrics["branch_count"] == 3
    assert frame.variables["P1.mass_flow_kg_s"] > 0


def test_dynamic_returns_explicit_quasi_steady_warning():
    frames = solve_dynamic(compile_project(reference_project()), duration_s=0.2, dt_s=0.1)
    assert len(frames) == 3
    assert any(item.code == "DYNAMIC_QUASI_STEADY" for item in frames[-1].diagnostics)


def test_prototype_export_converts_display_units():
    payload = {
        "format": "fluidnet-studio-prototype",
        "activeProject": "p1",
        "modules": [{"id": key} for key in ("source", "pump", "junction", "valve", "pipe")],
        "projects": [{
            "id": "p1", "name": "原型项目", "description": "",
            "pages": [{"id": "main", "nodes": [
                {"id": "B1", "moduleId": "source", "name": "源", "params": {"pressure": 201.325, "temperature": 20}, "draft": {"pressure": 201.325, "temperature": 20}},
                {"id": "B2", "moduleId": "source", "name": "汇", "params": {"pressure": 120, "temperature": 20}, "draft": {"pressure": 120, "temperature": 20}},
            ], "edges": []}],
        }],
    }
    project = normalize_prototype_export(payload)
    first = next(item for item in project.instances if item.id == "B1")
    assert first.parameters["pressure_pa"] == 201325
    assert first.parameters["temperature_k"] == 293.15
