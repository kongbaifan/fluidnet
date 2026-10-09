from __future__ import annotations

import math
import re
import uuid
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def new_id():
    return uuid.uuid4().hex[:16]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)


class MediumDefinition(StrictModel):
    id: str = "water"
    name: str = "液态水"
    kind: str = "water"
    components: list[str] = Field(default_factory=lambda: ["Water"])
    mass_fractions: list[float] = Field(default_factory=lambda: [1.0])
    backend: str = "coolprop_if97"
    backend_fluid: str = "IF97::Water"
    phase_policy: str = "liquid"
    version: int = 1

    @model_validator(mode="after")
    def composition(self):
        if not self.components or len(self.components) != len(self.mass_fractions):
            raise ValueError("组分与质量分数必须一一对应")
        if len(set(self.components)) != len(self.components):
            raise ValueError("组分不能重复")
        if any(not math.isfinite(v) or v < 0 for v in self.mass_fractions):
            raise ValueError("质量分数必须是非负有限数")
        if abs(sum(self.mass_fractions) - 1) > 1e-8:
            raise ValueError("质量分数之和必须为 1")
        return self


class Position(StrictModel):
    x: float = 0
    y: float = 0


class Element(StrictModel):
    id: str = Field(default_factory=new_id, pattern=r"^[A-Za-z0-9_-]+$")
    type: str
    name: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    media: dict[str, str] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)
    page: int = Field(default=0, ge=0, le=15)
    group_id: str | None = None
    version: int = 1
    template_id: str | None = None
    template_revision: int | None = Field(default=None, ge=1)

    @field_validator("parameters")
    @classmethod
    def finite(cls, values):
        def walk(v):
            if isinstance(v, float) and not math.isfinite(v):
                raise ValueError("参数不能包含 NaN 或无穷值")
            if isinstance(v, dict):
                for value in v.values():
                    walk(value)
            if isinstance(v, list):
                for value in v:
                    walk(value)
        walk(values)
        return values


class Connection(StrictModel):
    id: str = Field(default_factory=new_id)
    source: str
    source_port: str
    target: str
    target_port: str


class Group(StrictModel):
    id: str = Field(default_factory=new_id)
    name: str = "组合模块"
    element_ids: list[str] = Field(default_factory=list)
    exposed_ports: dict[str, str] = Field(default_factory=dict)
    exposed_parameters: dict[str, str] = Field(default_factory=dict)
    port_labels: dict[str, str] = Field(default_factory=dict)
    parameter_labels: dict[str, str] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)
    page: int = Field(default=0, ge=0, le=15)
    collapsed: bool = False
    template_id: str | None = None
    template_revision: int | None = Field(default=None, ge=1)
    member_keys: dict[str, str] = Field(default_factory=dict)


class ModuleInterface(StrictModel):
    exposed_ports: dict[str, str] = Field(default_factory=dict)
    exposed_parameters: dict[str, str] = Field(default_factory=dict)
    port_labels: dict[str, str] = Field(default_factory=dict)
    parameter_labels: dict[str, str] = Field(default_factory=dict)


class TestBoundary(StrictModel):
    pressure_pa: float = Field(default=301325, gt=0)
    temperature_k: float = Field(default=293.15, gt=0)


class TemplateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["equipment", "group"]
    body: dict
    interface: ModuleInterface | None = None
    test_conditions: dict[str, TestBoundary] = Field(default_factory=dict)
    revision: int = Field(default=0, ge=0)


class Scenario(StrictModel):
    id: str = Field(default_factory=new_id)
    name: str = "设计工况"
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SolverOptions(StrictModel):
    max_iterations: int = Field(default=100, ge=1, le=500)
    max_thermal_iterations: int = Field(default=80, ge=1, le=300)
    mass_atol: float = Field(default=1e-8, gt=0)
    mass_rtol: float = Field(default=1e-6, gt=0)
    pressure_atol: float = Field(default=1.0, gt=0)
    pressure_rtol: float = Field(default=1e-6, gt=0)
    thermal_tolerance_k: float = Field(default=1e-5, gt=0)
    thermal: bool = True


class Project(StrictModel):
    schema_version: Literal[2] = 2
    id: str = Field(default_factory=new_id, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = "未命名项目"
    description: str = ""
    revision: int = 0
    atmosphere_pa: float = Field(default=101325.0, gt=0)
    initial_temperature_k: float = Field(default=293.15, gt=0)
    default_medium_id: str = "water"
    media: list[MediumDefinition] = Field(default_factory=lambda: [MediumDefinition()])
    elements: list[Element] = Field(default_factory=list, max_length=1000)
    connections: list[Connection] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    selected_variables: list[str] = Field(default_factory=list, max_length=64)
    options: SolverOptions = Field(default_factory=SolverOptions)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value):
        if not isinstance(value, dict) or value.get("schema_version", 2) != 1:
            return value
        value = deepcopy(value)
        value["schema_version"] = 2
        value["elements"] = [e.model_dump() if isinstance(e, Element) else e for e in value.get("elements", [])]
        value["groups"] = [g.model_dump() if isinstance(g, Group) else g for g in value.get("groups", [])]
        elements = {e["id"]: e for e in value.get("elements", [])}
        for e in elements.values():
            e["group_id"] = None
        for group in value.get("groups", []):
            members = [elements[eid] for eid in group.get("element_ids", []) if eid in elements]
            group.setdefault("collapsed", False)
            group.setdefault("position", {"x": min((e.get("position", {}).get("x", 0) for e in members), default=0),
                                          "y": min((e.get("position", {}).get("y", 0) for e in members), default=0)})
            group.setdefault("page", members[0].get("page", 0) if members else 0)
            group.setdefault("member_keys", {e["id"]: e["id"] for e in members})
            old = group.get("exposed_parameters", {})
            group["exposed_parameters"] = {f"param_{i}": target for i, target in enumerate(old.values(), 1)}
            group["parameter_labels"] = {f"param_{i}": label for i, label in enumerate(old, 1)}
            for e in members:
                e["group_id"] = group["id"]
        return value

    @model_validator(mode="after")
    def identities(self):
        for label, items in [("元件", self.elements), ("连接", self.connections),
                             ("介质", self.media), ("组合", self.groups),
                             ("工况", self.scenarios)]:
            ids = [x.id for x in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} ID 重复")
        if self.default_medium_id not in {m.id for m in self.media}:
            raise ValueError("默认介质不存在")
        if self.groups or any(e.group_id is not None for e in self.elements):
            from .modules import validate_groups
            validate_groups(self)
        return self

    def with_scenario(self, scenario_id: str | None):
        result = self.model_copy(deep=True)
        if scenario_id is None:
            return result
        scenario = next((s for s in self.scenarios if s.id == scenario_id), None)
        if scenario is None:
            raise ValueError("工况不存在")
        elements = {e.id: e for e in result.elements}
        for eid, overrides in scenario.overrides.items():
            if eid not in elements:
                raise ValueError(f"工况引用了不存在的元件 {eid}")
            elements[eid].parameters.update(overrides)
        return result


class RunRequest(StrictModel):
    project: Project | None = None
    project_id: str | None = None
    scenario_id: str | None = None
    mode: Literal["steady", "dynamic"] = "steady"
    duration_s: float = Field(default=60, gt=0, le=604800)
    dt_s: float = Field(default=0.1, ge=0.001, le=60)
    speed: float = Field(default=1, gt=0, le=1000)
    start_paused: bool = False
    selected_variables: list[str] | None = Field(default=None, max_length=64)


class RunCommand(StrictModel):
    action: Literal["pause", "resume", "step", "stop", "reset", "set"]
    element_id: str | None = None
    parameter: str | None = None
    value: Any = None
