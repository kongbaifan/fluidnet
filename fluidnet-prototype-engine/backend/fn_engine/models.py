from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,80}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Domain(str, Enum):
    fluid = "fluid"
    info = "info"
    power = "power"
    mech = "mech"


class Direction(str, Enum):
    in_ = "in"
    out = "out"
    bidirectional = "bidirectional"


class UnitSpec(StrictModel):
    quantity: str
    canonical_unit: str
    display_unit: str
    display_scale: float = Field(default=1.0, gt=0)
    display_offset: float = 0.0

    def to_canonical(self, value: float) -> float:
        return (float(value) - self.display_offset) * self.display_scale

    def from_canonical(self, value: float) -> float:
        return float(value) / self.display_scale + self.display_offset


class ParameterSpec(StrictModel):
    id: Identifier
    label: str
    value_type: Literal["number", "boolean", "text", "curve"] = "number"
    default: Any
    unit: UnitSpec | None = None
    minimum: float | None = None
    maximum: float | None = None
    runtime: bool = False
    writable: bool = True


class PortSpec(StrictModel):
    id: Identifier
    label: str
    domain: Domain = Domain.fluid
    direction: Direction = Direction.bidirectional
    required: bool = True
    circuit: str = "fluid"


class ChannelSpec(StrictModel):
    id: Identifier
    name: str
    input_port: str
    output_port: str
    relation: Literal["resistance", "pump_curve", "pressure_source", "heat_transfer", "signal"]
    solver_model: str
    enabled: bool = True


class VariableSpec(StrictModel):
    id: str
    label: str
    quantity: str
    unit: UnitSpec | None = None
    source: Literal["parameter", "port", "state", "derived", "system"]
    writable: bool = False
    sampleable: bool = True
    parameter_id: str | None = None
    port_id: str | None = None


class ModuleDefinition(StrictModel):
    schema_version: Literal[1] = 1
    id: Identifier
    name: str
    version: int = Field(default=1, ge=1)
    category: str = "自定义模块"
    description: str = ""
    ports: list[PortSpec] = Field(default_factory=list)
    parameters: list[ParameterSpec] = Field(default_factory=list)
    variables: list[VariableSpec] = Field(default_factory=list)
    channels: list[ChannelSpec] = Field(default_factory=list)
    solver_model: str = "generic"
    state_model: str | None = None
    thermal_model: str | None = None
    source_format: str = "python-v1"
    source: dict[str, str | list[str]] = Field(default_factory=dict)
    bank_names: list[str] = Field(default_factory=lambda: ["额定工况", "部分负荷", "调试备份"])

    @model_validator(mode="after")
    def validate_definition(self):
        port_ids = [p.id for p in self.ports]
        parameter_ids = [p.id for p in self.parameters]
        variable_ids = [v.id for v in self.variables]
        if len(port_ids) != len(set(port_ids)):
            raise ValueError(f"模块 {self.id} 的端口 ID 重复")
        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError(f"模块 {self.id} 的参数 ID 重复")
        if len(variable_ids) != len(set(variable_ids)):
            raise ValueError(f"模块 {self.id} 的变量 ID 重复")
        if len(self.channels) != len({c.id for c in self.channels}):
            raise ValueError(f"模块 {self.id} 的通路 ID 重复")
        ports = set(port_ids)
        for channel in self.channels:
            if channel.input_port not in ports or channel.output_port not in ports:
                raise ValueError(f"模块 {self.id} 的通路引用了不存在的端口")
            if channel.input_port == channel.output_port:
                raise ValueError("通路两端不能是同一端口")
        for variable in self.variables:
            if variable.port_id and variable.port_id not in ports:
                raise ValueError("变量引用了不存在的端口")
        return self


class Position(StrictModel):
    x: float = 0.0
    y: float = 0.0


class LibraryBank(StrictModel):
    name: str
    values: dict[str, Any] = Field(default_factory=dict)


class ModuleInstance(StrictModel):
    id: Identifier
    module_id: str
    name: str
    page_id: str = "main"
    position: Position = Field(default_factory=Position)
    rotation: int = 0
    parameters: dict[str, Any] = Field(default_factory=dict)
    draft_parameters: dict[str, Any] = Field(default_factory=dict)
    banks: list[LibraryBank] = Field(default_factory=list)
    model_id: str | None = None
    model_version: int | None = None


class Endpoint(StrictModel):
    instance_id: str
    port_id: str


class Connection(StrictModel):
    id: str
    source: Endpoint
    target: Endpoint


class Scenario(StrictModel):
    id: str
    name: str
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SolverOptions(StrictModel):
    pressure_tolerance_pa: float = Field(default=1.0, gt=0)
    mass_tolerance_kg_s: float = Field(default=1e-8, gt=0)
    max_iterations: int = Field(default=80, ge=1, le=500)
    dynamic_step_s: float = Field(default=0.1, gt=0, le=60)


class Project(StrictModel):
    schema_version: Literal[1] = 1
    id: str
    name: str
    description: str = ""
    modules: list[ModuleDefinition] = Field(default_factory=list)
    instances: list[ModuleInstance] = Field(default_factory=list, max_length=1000)
    connections: list[Connection] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    selected_variables: list[str] = Field(default_factory=list, max_length=64)
    import_diagnostics: list[Diagnostic] = Field(default_factory=list)
    solver: SolverOptions = Field(default_factory=SolverOptions)

    @model_validator(mode="after")
    def validate_project(self):
        module_ids = {m.id for m in self.modules}
        if len(module_ids) != len(self.modules):
            raise ValueError("模块 ID 重复")
        instance_ids = [i.id for i in self.instances]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("实例 ID 重复")
        if any(i.module_id not in module_ids for i in self.instances):
            raise ValueError("实例引用了不存在的模块")
        instance_map = {i.id: i for i in self.instances}
        definitions = {m.id: m for m in self.modules}
        connection_ids = [c.id for c in self.connections]
        if len(connection_ids) != len(set(connection_ids)):
            raise ValueError("连接 ID 重复")
        if len({s.id for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("工况 ID 重复")
        for c in self.connections:
            for endpoint in (c.source, c.target):
                if endpoint.instance_id not in instance_map:
                    raise ValueError(f"连接 {c.id} 引用了不存在的实例")
                definition = definitions[instance_map[endpoint.instance_id].module_id]
                if endpoint.port_id not in {p.id for p in definition.ports}:
                    raise ValueError(f"连接 {c.id} 引用了不存在的端口")
        return self


class RunRequest(StrictModel):
    project: Project
    mode: Literal["steady", "dynamic"] = "steady"
    duration_s: float = Field(default=60, gt=0, le=604800)
    dt_s: float = Field(default=0.1, gt=0, le=60)
    selected_variables: list[str] | None = Field(default=None, max_length=64)
    scenario_id: str | None = None

    @model_validator(mode="after")
    def limit_frames(self):
        if self.mode == "dynamic" and self.duration_s > 2000 * self.dt_s:
            raise ValueError("单次准稳态运行最多 2001 帧，请增大步长或缩短时长")
        return self


class RunCommand(StrictModel):
    action: Literal["pause", "resume", "step", "stop", "set"]
    instance_id: str | None = None
    parameter_id: str | None = None
    value: Any = None


class Diagnostic(StrictModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "error"
    instance_id: str | None = None
    field: str | None = None


class RunFrame(StrictModel):
    status: str
    valid: bool
    time_s: float
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    metrics: dict[str, float | int | None] = Field(default_factory=dict)


class RunRecord(StrictModel):
    id: str
    status: str
    mode: str
    request: RunRequest
    frame: RunFrame | None = None
    history: list[RunFrame] = Field(default_factory=list)
