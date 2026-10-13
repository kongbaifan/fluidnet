from __future__ import annotations

from enum import Enum
import math
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

    @model_validator(mode="after")
    def validate_default(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("参数最小值不能大于最大值")
        if self.value_type == "number":
            if isinstance(self.default, bool) or not isinstance(self.default, (int, float)) or not math.isfinite(self.default):
                raise ValueError("数值参数默认值必须是有限数值")
            if self.minimum is not None and self.default < self.minimum or self.maximum is not None and self.default > self.maximum:
                raise ValueError("参数默认值超出声明范围")
        elif self.value_type == "boolean" and not isinstance(self.default, bool):
            raise ValueError("布尔参数默认值必须是布尔值")
        elif self.value_type == "text" and not isinstance(self.default, str):
            raise ValueError("文本参数默认值必须是字符串")
        elif self.value_type == "curve":
            if not isinstance(self.default, list) or not all(isinstance(row, list) and len(row) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in row) for row in self.default):
                raise ValueError("曲线默认值必须是有限数值点对数组")
        if self.value_type != "number" and self.unit is not None:
            raise ValueError("仅数值参数可以声明单位换算")
        return self


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


class FluidConfig(StrictModel):
    """Serializable fluid selection passed to the property service."""

    backend: Literal["coolprop"] = "coolprop"
    fluid: str = "Water"
    composition: dict[str, float] = Field(default_factory=dict)
    reference: Literal["mass", "mole"] = "mass"
    # "any" lets module code query two-phase states; network flow still requires single phase.
    phase_policy: Literal["single_phase", "liquid", "gas", "any"] = "single_phase"

    @model_validator(mode="after")
    def validate_composition(self):
        if any(not isinstance(value, (int, float)) or value < 0 for value in self.composition.values()):
            raise ValueError("工质组分必须是非负数")
        if self.composition:
            total = sum(self.composition.values())
            if total <= 0 or abs(total - 1.0) > 1e-8:
                raise ValueError("工质组分比例之和必须为 1")
        return self


class ModulePackageRef(StrictModel):
    module_id: Identifier
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    definition_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")


class FluidState(StrictModel):
    pressure_pa: float
    temperature_k: float
    enthalpy_j_kg: float
    density_kg_m3: float
    # Transport properties are undefined for a two-phase mixture and stay None there.
    viscosity_pa_s: float | None = None
    specific_heat_j_kg_k: float | None = None
    thermal_conductivity_w_m_k: float | None = None
    # Caloric extras for module code (isentropic compression etc.); speed of sound is None in two-phase.
    entropy_j_kg_k: float | None = None
    internal_energy_j_kg: float | None = None
    cv_j_kg_k: float | None = None
    speed_of_sound_m_s: float | None = None
    phase: str = "unknown"
    quality: float | None = None
    composition: dict[str, float] = Field(default_factory=dict)


class PortState(StrictModel):
    pressure_pa: float | None = None
    temperature_k: float | None = None
    enthalpy_j_kg: float | None = None
    density_kg_m3: float | None = None
    viscosity_pa_s: float | None = None
    specific_heat_j_kg_k: float | None = None
    mass_flow_kg_s: float | None = None
    quality: float | None = None
    composition: dict[str, float] = Field(default_factory=dict)


class NetworkRelation(StrictModel):
    relation_id: Identifier
    kind: Literal["pipe", "valve", "pump", "compressor", "resistance"]
    channel: Identifier
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_parameters(self):
        required = {'pipe':['length_m','diameter_m','roughness_m'], 'valve':['kv_m3_h','opening_ratio'],
                    'pump':['head_curve','speed_ratio'], 'compressor':['forced_mass_flow_kg_s'],
                    'resistance':['diameter_m','loss_coefficient']}[self.kind]
        if set(required) - self.parameters.keys():
            raise ValueError(f'{self.kind} 缺少关系参数 {sorted(set(required)-self.parameters.keys())}')
        for key,value in self.parameters.items():
            if key == 'head_curve':
                continue
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
                raise ValueError(f'{self.kind}.{key} 必须是有限数值')
            if key in {'diameter_m','length_m','kv_m3_h','speed_ratio'} and value <= 0:
                raise ValueError(f'{self.kind}.{key} 必须大于零')
            if key in {'roughness_m','density_kg_m3','viscosity_pa_s','loss_coefficient'} and value < 0:
                raise ValueError(f'{self.kind}.{key} 不能小于零')
            if key == 'opening_ratio' and not 0 <= value <= 1:
                raise ValueError('阀门开度必须在 [0,1] 内')
        if self.kind == 'pump':
            curve=self.parameters['head_curve']
            valid=isinstance(curve,list) and len(curve)>=2
            valid=valid and all(isinstance(p,list) and len(p)==2 and all(isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 for v in p) for p in curve)
            valid=valid and curve[0][0]==0 and curve[-1][1]==0 and all(b[0]>a[0] and b[1]<a[1] for a,b in zip(curve,curve[1:]))
            if not valid:
                raise ValueError('扬程曲线必须流量递增、扬程递减，从零流量到零扬程')
        return self


class InitializeRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    package: ModulePackageRef
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=FluidConfig)
    initial_state: dict[str, Any] = Field(default_factory=dict)


class EvaluateRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    iteration_id: int = Field(ge=0)
    time_s: float = Field(ge=0)
    trial_ports: dict[Identifier, PortState] = Field(default_factory=dict)
    readonly_state: dict[str, Any] = Field(default_factory=dict)


class EvaluateResponse(StrictModel):
    relations: list[NetworkRelation] = Field(default_factory=list)
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list["Diagnostic"] = Field(default_factory=list)


class ChannelState(StrictModel):
    mass_flow_kg_s: float = 0.0
    pressure_drop_pa: float = 0.0


class CommitStepRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    time_s: float = Field(ge=0)
    dt_s: float = Field(gt=0)
    converged_ports: dict[Identifier, PortState] = Field(default_factory=dict)
    converged_channels: dict[Identifier, ChannelState] = Field(default_factory=dict)


class CommitStepResponse(StrictModel):
    state: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list["Diagnostic"] = Field(default_factory=list)


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
    runtime: Literal["builtin", "python"] = "builtin"
    entrypoint: str = ""
    content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    definition_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    package_path: str | None = None
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
            if variable.parameter_id and variable.parameter_id not in parameter_ids:
                raise ValueError("变量引用了不存在的参数")
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
    package: ModulePackageRef | None = None


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
    # Thermal layer: node enthalpy transport after the hydraulic solve.
    thermal: bool = True
    # reference: hydraulics keep the constant reference water properties (one-way);
    # node: outer iteration feeds node-averaged density/viscosity back into hydraulics.
    property_coupling: Literal["reference", "node"] = "reference"
    thermal_tolerance_k: float = Field(default=1e-6, gt=0)
    max_thermal_iterations: int = Field(default=50, ge=1, le=500)
    max_coupling_iterations: int = Field(default=20, ge=1, le=200)
    coupling_density_rtol: float = Field(default=1e-6, gt=0)
    # Implicit time stepping (networks with tanks): a failed substep is retried with half the step.
    max_step_halvings: int = Field(default=6, ge=0, le=20)
    hydraulic_method: Literal['dense', 'sparse'] = 'dense'
    module_parallelism: int = Field(default=1, ge=1, le=16)
    batch_modules: bool = True


class PIDController(StrictModel):
    id: Identifier
    measurement: str
    instance_id: Identifier
    parameter_id: Identifier
    setpoint: float
    kp: float = 2.0
    ki: float = 0.0
    kd: float = 0.0
    sample_s: float = Field(default=0.1, gt=0, le=60)
    minimum: float = 0.0
    maximum: float = 1.0
    mode: Literal['manual', 'auto'] = 'auto'
    manual_output: float | None = None

    @model_validator(mode='after')
    def check_limits(self):
        if self.minimum >= self.maximum:
            raise ValueError('PID 输出下限必须小于上限')
        if self.manual_output is not None and not self.minimum <= self.manual_output <= self.maximum:
            raise ValueError('PID 手动输出超出范围')
        return self


class Project(StrictModel):
    schema_version: Literal[1] = 1
    id: str
    name: str
    description: str = ""
    fluid: FluidConfig = Field(default_factory=FluidConfig)
    modules: list[ModuleDefinition] = Field(default_factory=list)
    instances: list[ModuleInstance] = Field(default_factory=list, max_length=1000)
    connections: list[Connection] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    selected_variables: list[str] = Field(default_factory=list, max_length=64)
    import_diagnostics: list[Diagnostic] = Field(default_factory=list)
    solver: SolverOptions = Field(default_factory=SolverOptions)
    controllers: list[PIDController] = Field(default_factory=list)

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
        if len({c.id for c in self.controllers}) != len(self.controllers):
            raise ValueError('控制器 ID 重复')
        targets = [(c.instance_id, c.parameter_id) for c in self.controllers]
        if len(set(targets)) != len(targets):
            raise ValueError('同一参数只能绑定一个控制器')
        if any(c.instance_id not in instance_map for c in self.controllers):
            raise ValueError('控制器目标设备不存在')
        definitions = {m.id: m for m in self.modules}
        for instance in self.instances:
            if instance.package:
                definition = definitions[instance.module_id]
                ref = instance.package
                if (definition.runtime != "python" or ref.module_id != definition.id
                        or ref.version != f"{definition.version}.0.0" or ref.content_hash != definition.content_hash
                        or ref.definition_hash != definition.definition_hash):
                    raise ValueError(f"实例 {instance.id} 的模块版本绑定与定义快照不一致")
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
    # None runs a background dynamic session until it is stopped.
    duration_s: float | None = Field(default=60, gt=0, le=604800)
    dt_s: float = Field(default=0.1, gt=0, le=60)
    selected_variables: list[str] | None = Field(default=None, max_length=64)
    scenario_id: str | None = None
    # 'trend' keeps every variable only on key frames (first, last, every K-th; ≤ ~51 in total)
    # and only trend_variables plus module state on the others. Dynamic runs only.
    history: Literal["full", "trend"] = "full"
    trend_variables: list[str] = Field(default_factory=list, max_length=256)
    execution_mode: Literal['fast', 'realtime'] = 'fast'
    speed_ratio: float = Field(default=1.0, gt=0, le=100)
    start_paused: bool = False
    # Background runs keep only the most recent `history_window` frames plus a decimated
    # overview of the whole run; synchronous runs return everything (at most 2001 frames).
    history_window: int = Field(default=2001, ge=10, le=20001)

    @model_validator(mode="after")
    def check_duration(self):
        if self.duration_s is None and self.mode != "dynamic":
            raise ValueError("只有动态运行可以不设时长（持续运行）")
        return self

    def frame_count(self) -> int | None:
        """Frames of a finite dynamic run, t=0 included; None for steady or continuous runs."""
        if self.mode != "dynamic" or self.duration_s is None:
            return None
        return math.ceil(self.duration_s / self.dt_s - 1e-9) + 1


class RunCommand(StrictModel):
    action: Literal["pause", "resume", "step", "stop", "set", "controller"]
    instance_id: str | None = None
    parameter_id: str | None = None
    value: Any = None
    command_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')
    controller_id: Identifier | None = None


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
    # False on trend-history frames that carry only the trend variables (see RunRequest.history).
    full: bool = True
    sequence: int = 0
    parameter_revision: int = 0


class RunRecord(StrictModel):
    id: str
    status: str
    mode: str
    request: RunRequest
    frame: RunFrame | None = None
    history: list[RunFrame] = Field(default_factory=list)


class ModuleManifest(ModuleDefinition):
    """Public name for a module package manifest."""

    runtime: Literal["builtin", "python"] = "python"


class ModuleTestConditions(StrictModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=FluidConfig)
    inlet_pressure_pa: float = Field(default=250000.0, gt=0)
    outlet_pressure_pa: float = Field(default=120000.0, gt=0)
    temperature_k: float = Field(default=293.15, gt=0)
    duration_s: float = Field(default=0.1, gt=0, le=60)
    dt_s: float = Field(default=0.1, gt=0, le=60)

    @model_validator(mode="after")
    def limit_frames(self):
        if self.duration_s > 2000 * self.dt_s:
            raise ValueError("独立测试最多 2001 帧")
        return self


class ModuleTestRequest(ModuleTestConditions):
    module: ModuleDefinition


class ModuleTestResponse(StrictModel):
    module_id: str
    content_hash: str
    state: dict[str, Any] = Field(default_factory=dict)
    evaluation: EvaluateResponse
    committed: CommitStepResponse
    frame: RunFrame
    history: list[RunFrame] = Field(default_factory=list)


class ModuleSaveRequest(StrictModel):
    module: ModuleDefinition
    expected_latest_version: int = Field(ge=0)
    release_notes: str = Field(default="", max_length=2000)
    test: ModuleTestConditions = Field(default_factory=ModuleTestConditions)


class ModuleVersionInfo(StrictModel):
    package: ModulePackageRef
    created_at: str | None = None
    release_notes: str = ""
    tested: bool = False


class ModuleVersionResponse(ModuleVersionInfo):
    module: ModuleDefinition
    test_conditions: ModuleTestConditions | None = None
    test_result: ModuleTestResponse | None = None


class ModuleVersionsResponse(StrictModel):
    versions: list[ModuleVersionInfo] = Field(default_factory=list)


class RunStatus(StrictModel):
    run_id: str
    status: Literal["queued", "running", "paused", "stopping", "completed", "failed", "cancelled", "interrupted"]
    mode: Literal["steady", "dynamic"]
    progress: float = Field(default=0.0, ge=0, le=1)
    frame: RunFrame | None = None
    total_rows: int = Field(default=0, ge=0)
    command_id: str | None = None
    command_status: Literal['accepted', 'applied', 'rejected'] | None = None
    applied_time_s: float | None = None
    message: str | None = None
    lag_s: float = 0.0


class ErrorResponse(StrictModel):
    code: str
    message: str
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    request_id: str | None = None


class ValidationResponse(StrictModel):
    valid: bool
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class RunCreateResponse(StrictModel):
    run_id: str
    status: str
    frame: RunFrame | None = None
    total_rows: int = Field(default=0, ge=0)


class RunHistoryResponse(StrictModel):
    rows: list[RunFrame] = Field(default_factory=list)
    # total_rows counts every frame published so far; offsets are absolute frame indices.
    total_rows: int = Field(default=0, ge=0)
    offset: int = Field(default=0, ge=0)
    # Oldest frame still held (older frames left the history window); `truncated` when the
    # requested offset was older than that and the rows start at first_offset instead.
    first_offset: int = Field(default=0, ge=0)
    truncated: bool = False


class RunOverviewResponse(StrictModel):
    """Every `stride`-th frame of the whole run (≤ ~2000 rows) plus the latest frame."""
    rows: list[RunFrame] = Field(default_factory=list)
    stride: int = Field(default=1, ge=1)
    total_rows: int = Field(default=0, ge=0)


class RunEvent(StrictModel):
    type: str
    time_s: float = Field(default=0.0, ge=0)
    command_id: str | None = None
    command_status: str | None = None
    message: str | None = None
    command: RunCommand | None = None
    parameter_revision: int | None = None


class RunEventsResponse(StrictModel):
    run_id: str
    events: list[RunEvent] = Field(default_factory=list)


class CatalogResponse(StrictModel):
    modules: list[ModuleDefinition] = Field(default_factory=list)
    prototype_parameter_bindings: dict[str, dict[str, str]] = Field(default_factory=dict)


class ModuleCatalogItem(ModuleDefinition):
    package: ModulePackageRef | None = None


class ModuleCatalogResponse(StrictModel):
    modules: list[ModuleCatalogItem] = Field(default_factory=list)


class ProjectValidationResponse(ValidationResponse):
    pass


class RunRecordResponse(StrictModel):
    id: str
    status: str
    mode: str
    request: RunRequest
    frame: RunFrame | None = None
    events: list[RunEvent] = Field(default_factory=list)
    total_rows: int = 0
    lag_s: float = 0.0


EvaluateResponse.model_rebuild()
CommitStepResponse.model_rebuild()
