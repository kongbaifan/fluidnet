import json
import sqlite3
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from fluidnet.api import create_app
from fluidnet.examples import example_templates, parallel_network, single_pipe, controlled
from fluidnet.models import ModuleInterface, Position, Project
from fluidnet.modules import (apply_template, configure_group, extract_group, insert_template,
                              make_bench, normalize_template)
from fluidnet.simulation import SimulationSession
from fluidnet.solver import solve_steady
from fluidnet.storage import ConflictError, Store


def grouped_pipe():
    return configure_group(single_pipe(), ["pipe"], "可复用管段")


def test_grouping_and_expansion_preserve_the_physical_solution():
    original = single_pipe()
    expected = solve_steady(original)
    grouped, gid = grouped_pipe()
    for collapsed in (True, False):
        grouped.groups[0].collapsed = collapsed
        result = solve_steady(grouped)
        assert result["elements"] == expected["elements"]
        assert result["ports"] == expected["ports"]
    assert original.groups == []


def test_v1_groups_upgrade_without_moving_or_rewriting_input():
    grouped, gid = grouped_pipe()
    raw = grouped.model_dump()
    raw["schema_version"] = 1
    raw["groups"] = [{"id": gid, "name": "旧分组", "element_ids": ["pipe"],
                      "exposed_ports": grouped.groups[0].exposed_ports,
                      "exposed_parameters": {"管长": "pipe.length_m"}}]
    frozen = deepcopy(raw)
    migrated = Project.model_validate(raw)
    assert raw == frozen
    assert migrated.schema_version == 2
    assert not migrated.groups[0].collapsed
    assert migrated.groups[0].parameter_labels == {"param_1": "管长"}
    assert migrated.elements[1].position == grouped.elements[1].position
    assert solve_steady(migrated)["elements"] == solve_steady(grouped)["elements"]


@pytest.mark.parametrize("index", range(3))
def test_supplied_module_benches_solve(index):
    template = example_templates()[index]
    original = deepcopy(template)
    bench = make_bench(template)
    assert solve_steady(bench)["valid"]
    session = SimulationSession(bench, 0.1)
    assert session.advance()["valid"]
    assert template == original
    assert not any(e["id"].startswith("bench_") for e in template["body"]["elements"])


def test_copies_remap_control_and_media_without_merging_colliding_ids():
    original = controlled()
    original, gid = configure_group(original, [e.id for e in original.elements], "控制回路")
    template = extract_group(original, gid)
    template["body"]["media"][0]["name"] = "独立工质配置"
    host = Project()
    first, first_id, ids1 = insert_template(host, template)
    second, second_id, ids2 = insert_template(first, template, Position(x=900, y=100))
    assert not set(ids1) & set(ids2)
    assert first_id != second_id
    assert len(second.media) == 2
    for group in second.groups:
        members = [e for e in second.elements if e.id in group.element_ids]
        pid = next(e for e in members if e.type == "pid")
        assert pid.parameters["target_element"] in group.element_ids
        assert pid.parameters["measurement"].split(".")[0] in group.element_ids
        assert all(mid != "water" for e in members for mid in e.media.values())
    assert solve_steady(second)["valid"]
    assert len(host.elements) == 0


def test_version_preview_keeps_ids_connections_and_scenario_overrides():
    project, gid = grouped_pipe()
    definition = extract_group(project, gid)
    definition.update(id="pipe_template", revision=1)
    project.groups[0].template_id = "pipe_template"
    project.groups[0].template_revision = 1
    project_data = project.model_dump()
    project_data["scenarios"] = [{"id": "case", "name": "校准工况", "overrides": {"pipe": {"length_m": 77}}}]
    project = Project.model_validate(project_data)
    before = project.model_dump()
    definition["body"]["elements"][0]["parameters"]["length_m"] = 60
    alias = next(iter(definition["interface"]["exposed_ports"]))
    definition["interface"]["port_labels"][alias] = "供水入口"
    definition["revision"] = 2
    candidate, changes = apply_template(project, definition, group_id=gid)
    assert project.model_dump() == before
    assert candidate.connections == project.connections
    assert candidate.scenarios == project.scenarios
    assert candidate.selected_variables == project.selected_variables
    assert candidate.elements[-1].id == "pipe"
    assert candidate.elements[-1].parameters["length_m"] == 60
    assert candidate.with_scenario("case").elements[-1].parameters["length_m"] == 77
    assert candidate.groups[0].template_revision == 2
    assert changes["parameters"]
    assert any("供水入口" in line for line in changes["interfaces"])


def test_removing_connected_interface_is_rejected_atomically():
    project, gid = grouped_pipe()
    definition = extract_group(project, gid)
    before = project.model_dump()
    # Changing the public ID keeps the definition valid, but would break the host connection.
    ports = definition["interface"]["exposed_ports"]
    alias = next(iter(ports))
    ports["new_port"] = ports.pop(alias)
    definition["test_conditions"]["new_port"] = definition["test_conditions"].pop(alias)
    with pytest.raises(ValueError, match="外部连接"):
        apply_template(project, definition, group_id=gid)
    assert project.model_dump() == before


def test_nested_groups_and_external_control_dependencies_are_rejected():
    project, gid = grouped_pipe()
    with pytest.raises(ValueError, match="嵌套"):
        configure_group(project, ["pipe", "source"], "嵌套")
    project = controlled()
    with pytest.raises(ValueError, match="控制目标"):
        configure_group(project, ["controller", "pipe_a"], "不完整控制器")


def test_changed_element_type_cannot_silently_invalidate_a_recorded_variable():
    project, gid = grouped_pipe()
    project.selected_variables.append("pipe.friction_factor")
    definition = extract_group(project, gid)
    body = definition["body"]["elements"][0]
    body.update(type="valve", parameters={"opening": 0.8})
    before = project.model_dump()
    with pytest.raises(ValueError, match="记录变量失效"):
        apply_template(project, definition, group_id=gid)
    assert project.model_dump() == before


def test_mapping_same_external_interfaces_to_new_members_preserves_connections():
    project, gid = grouped_pipe()
    project.selected_variables = []
    definition = extract_group(project, gid)
    definition["body"]["elements"][0]["id"] = "replacement"
    definition["interface"]["exposed_ports"] = {a: address.replace("pipe:", "replacement:")
                                                  for a, address in definition["interface"]["exposed_ports"].items()}
    candidate, changes = apply_template(project, definition, group_id=gid)
    assert changes["added"] and changes["removed"]
    assert {c.id for c in candidate.connections} == {c.id for c in project.connections}
    assert solve_steady(candidate)["valid"]


def test_exchanger_copies_preserve_two_circuits():
    template = example_templates()[1]
    host = Project()
    inserted, gid, _ = insert_template(host, template)
    definition = extract_group(inserted, gid)
    result = solve_steady(make_bench({**definition, "test_conditions": template["test_conditions"]}))
    assert len(result["circuits"]) == 2
    assert len({c["medium_id"] for c in result["circuits"]}) == 2


def test_legacy_database_backup_and_template_history(tmp_path):
    raw = single_pipe().model_dump()
    raw["schema_version"] = 1
    dbpath = tmp_path / "studio.sqlite3"
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE templates(id TEXT PRIMARY KEY,name TEXT,kind TEXT,body TEXT,updated REAL)")
        db.execute("INSERT INTO templates VALUES(?,?,?,?,?)", ("legacy", "旧型号", "group", json.dumps(raw), 1))
        db.execute("INSERT INTO templates VALUES(?,?,?,?,?)", ("broken", "旧型号待修复", "group", "{}", 1))
    store = Store(tmp_path)
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1
    assert len(store.templates()) == 2
    broken = store.get_template("broken")
    assert broken["body"] == {}
    assert "至少需要一个元件" in broken["validation_error"]
    store.archive_template("broken", 1)
    old = store.get_template("legacy")
    assert old["revision"] == 1
    assert store.get_template("legacy", 1)["id"] == "legacy"
    new = store.save_template("新名称", "group", old["body"], old["interface"], old["test_conditions"], revision=1, template_id="legacy")
    assert new["revision"] == 2
    assert store.get_template("legacy", 1)["name"] == "旧型号"
    with pytest.raises(ConflictError):
        store.save_template("冲突", "group", old["body"], revision=1, template_id="legacy")
    store.archive_template("legacy", 2)
    assert store.templates() == []
    assert len(store.templates(True)) == 2
    assert len(store.template_versions("legacy")) == 2
    store.close()
    reopened = Store(tmp_path)
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1
    reopened.close()


def test_module_api_versioning_and_bench(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        templates = client.get("/api/v1/templates").json()
        assert len(templates) == 3
        definition = {k: v for k, v in templates[0].items() if k not in {"id", "updated", "archived"}}
        definition["name"] = "可编辑副本"
        created = client.post("/api/v1/templates", json=definition).json()
        definition["revision"] = created["revision"]
        definition["name"] = "第二版"
        updated = client.put(f"/api/v1/templates/{created['id']}", json=definition)
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2
        assert client.put(f"/api/v1/templates/{created['id']}", json=definition).status_code == 409
        assert len(client.get(f"/api/v1/templates/{created['id']}/versions").json()) == 2
        bench = client.post("/api/v1/modules/bench", json=definition)
        assert bench.status_code == 200, bench.text
        assert client.post("/api/v1/validate", json=bench.json()).json()["valid"]
        archived = client.delete(f"/api/v1/templates/{created['id']}?revision=2")
        assert archived.status_code == 200
        assert len(client.get("/api/v1/templates").json()) == 3
