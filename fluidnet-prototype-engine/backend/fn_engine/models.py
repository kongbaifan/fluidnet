from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from fn_sdk import CallbackPhase, ChannelDataKind, PortDataKind, StateDataKind

from ._module_schema_v1 import (
    ChannelSpec as ChannelSpec, Direction as Direction, Domain as Domain,
    Identifier, ModuleDefinitionV1, ModuleFieldsV1, ParameterSpec as ParameterSpec,
    PortSpec as PortSpec, StrictModel, UnitSpec as UnitSpec, VariableSpec as VariableSpec,
)
from ._module_schema_v2 import ModuleDefinitionV2, ModuleSDKRequirements
from ._module_schema_v3 import ModuleDefinitionV3, ModuleApplicability, CompositeDefinition


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


class ModuleRequestContext(StrictModel):
    """Optional transport metadata; callback phase/time are derived from the action itself."""

    request_id: Identifier
    step_id: Identifier | None = None
    accepted_time_s: float | None = Field(default=None, ge=0)
    port_data: Literal['trial', 'converged'] = 'trial'


class ModuleExecutionInfo(StrictModel):
    model_config = ConfigDict(frozen=True)

    phase: CallbackPhase = 'manual'
    time_s: float | None = Field(default=None, ge=0)
    run_id: str | None = None
    instance_id: str | None = None
    request_id: str | None = None
    step_id: str | None = None
    iteration_id: int | None = Field(default=None, ge=0)
    dt_s: float | None = Field(default=None, gt=0)
    accepted_time_s: float | None = Field(default=None, ge=0)
    port_data: PortDataKind = 'unavailable'
    channel_data: ChannelDataKind = 'unavailable'
    state_data: StateDataKind = 'unavailable'


class InitializeRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    package: ModulePackageRef
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=FluidConfig)
    # Fluid per port where it differs from `fluid` (a module spanning two circuits); ctx.fluid_at(port).
    port_fluids: dict[str, FluidConfig] = Field(default_factory=dict)
    initial_state: dict[str, Any] = Field(default_factory=dict)
    cache_enabled: bool = Field(default=False, exclude_if=lambda value: value is False)
    context: ModuleRequestContext | None = Field(default=None, exclude_if=lambda value: value is None)


class EvaluateRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    iteration_id: int = Field(ge=0)
    time_s: float = Field(ge=0)
    trial_ports: dict[Identifier, PortState] = Field(default_factory=dict)
    readonly_state: dict[str, Any] = Field(default_factory=dict)
    state_revision: int | None = Field(default=None,ge=0,exclude_if=lambda value:value is None)
    context: ModuleRequestContext | None = Field(default=None, exclude_if=lambda value: value is None)


class EvaluateResponse(StrictModel):
    relations: list[NetworkRelation] = Field(default_factory=list)
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list["Diagnostic"] = Field(default_factory=list)
    accessed_ports: list[Identifier] = Field(default_factory=list, exclude_if=lambda value: not value)
    cache_hit: bool = Field(default=False, exclude_if=lambda value: value is False)


class ChannelState(StrictModel):
    mass_flow_kg_s: float = 0.0
    pressure_drop_pa: float = 0.0
    heat_w: float = Field(default=0.0, exclude_if=lambda value: value == 0)


class ModulePhaseRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    time_s: float = Field(ge=0)
    ports: dict[Identifier, PortState] = Field(default_factory=dict)
    channels: dict[Identifier, ChannelState] = Field(default_factory=dict)
    context: ModuleRequestContext | None = Field(default=None, exclude_if=lambda value: value is None)


class ModuleThermalResponse(StrictModel):
    heat_w: dict[Identifier, float] = Field(default_factory=dict)
    diagnostics: list['Diagnostic'] = Field(default_factory=list)


class ModuleRelationDerivative(StrictModel):
    flow_slope_pa_per_kg_s: float
    port_pressure_derivatives: dict[Identifier, float] = Field(default_factory=dict)
    smooth: bool = True


class ModuleDerivativeResponse(StrictModel):
    derivatives: dict[Identifier, ModuleRelationDerivative]
    diagnostics: list['Diagnostic'] = Field(default_factory=list)


class CommitStepRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    time_s: float = Field(ge=0)
    dt_s: float = Field(gt=0)
    converged_ports: dict[Identifier, PortState] = Field(default_factory=dict)
    converged_channels: dict[Identifier, ChannelState] = Field(default_factory=dict)
    context: ModuleRequestContext | None = Field(default=None, exclude_if=lambda value: value is None)


class CommitStepResponse(StrictModel):
    state: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list["Diagnostic"] = Field(default_factory=list)


class ModuleStepCandidate(StrictModel):
    candidate_id: Identifier
    step_id: Identifier
    base_revision: int = Field(ge=0)
    time_s: float = Field(ge=0)
    result: CommitStepResponse
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    definition_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class ModuleDefinition(ModuleFieldsV1):
    """Schema-dispatched module facade; v1 never receives SDK default fields."""

    schema_version: Literal[1, 2, 3] = 1
    sdk: ModuleSDKRequirements | None = Field(default=None, exclude_if=lambda value: value is None)
    applicability: ModuleApplicability | None = Field(default=None, exclude_if=lambda value: value is None)
    hydraulic_dependencies: dict[Identifier, list[Identifier]] | None = Field(default=None, exclude_if=lambda value: value is None)
    dependency_mode: Literal['conservative','tracked'] | None = Field(default=None, exclude_if=lambda value: value is None)
    pure_evaluate: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    composite: CompositeDefinition | None = Field(default=None, exclude_if=lambda value: value is None)
    model_config = ConfigDict(json_schema_extra={"allOf": [{
        "if": {"properties": {"schema_version": {"enum": [2, 3]}}, "required": ["schema_version"]},
        "then": {"required": ["sdk", "runtime"], "properties": {"sdk": {"type": "object"}, "runtime": {"const": "python"}}},
        "else": {"not": {"required": ["sdk"]}},
    }, {
        'if': {'properties': {'schema_version': {'const': 3}}, 'required': ['schema_version']},
        'then': {'properties': {'applicability': {'type':'object'}, 'hydraulic_dependencies': {'type':'object'},
                                'dependency_mode': {'type':'string'}, 'pure_evaluate': {'type':'boolean'}}},
        'else': {'not': {'anyOf': [{'required':[name]} for name in
            ['applicability','hydraulic_dependencies','dependency_mode','pure_evaluate','composite']]}}
    }]})

    @model_validator(mode="before")
    @classmethod
    def parse_contract_schema(cls, data):
        if not isinstance(data, dict):
            return data
        # Catalog response subclasses have presentation-only fields outside the contract.
        fields = set(ModuleDefinitionV3.model_fields)
        core = {key: value for key, value in data.items() if key in fields}
        schema = core.get("schema_version", 1)
        parser = {1: ModuleDefinitionV1, 2: ModuleDefinitionV2, 3: ModuleDefinitionV3}.get(schema) if isinstance(schema, (int, float)) else None
        if parser is None:
            raise ValueError(f"不支持的模块合同 schema_version：{schema}")
        if schema == 1:
            core.setdefault("runtime", cls.model_fields["runtime"].default)
        parsed = parser.model_validate(core).model_dump(mode="python")
        return {**data, **parsed}


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


class ScheduleEvent(StrictModel):
    """A load or operation event at a simulation time (cold-store projects; canonical units).

    door_heat: `heat_w` for `duration_s` [time_s, time_s + duration_s); goods_addition: `mass_kg` frozen goods
    at `temperature_k`, mixed by energy; ambient_temperature: outdoor `temperature_k` from `time_s` on;
    electric_defrost: start one defrost cycle of the target cooler; set_variable: write `value` to `key`
    (`<instance>.param.<runtime parameter>` or `controller.<id>.setpoint|manual_output`) like a run command.
    `instance_id` may be omitted when the project has exactly one matching device (ambient: every device
    with an outdoor temperature)."""
    id: Identifier
    type: Literal['door_heat', 'goods_addition', 'ambient_temperature', 'electric_defrost', 'set_variable']
    time_s: float = Field(ge=0)
    instance_id: Identifier | None = None
    duration_s: float | None = Field(default=None, gt=0)
    heat_w: float | None = Field(default=None, ge=0)
    mass_kg: float | None = Field(default=None, gt=0)
    temperature_k: float | None = Field(default=None, gt=0)
    key: str | None = Field(default=None, max_length=200)
    value: float | None = None

    @model_validator(mode='after')
    def check_fields(self):
        required = {'door_heat': {'duration_s', 'heat_w'}, 'goods_addition': {'mass_kg', 'temperature_k'},
                    'ambient_temperature': {'temperature_k'}, 'electric_defrost': set(),
                    'set_variable': {'key', 'value'}}[self.type]
        given = {k for k in ('duration_s', 'heat_w', 'mass_kg', 'temperature_k', 'key', 'value') if getattr(self, k) is not None}
        if given != required:
            raise ValueError(f'{self.type} 事件需要且只能填写 {sorted(required) or "时间"}（当前 {sorted(given)}）')
        return self


class Scenario(StrictModel):
    id: str
    name: str
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # None keeps the project schedule; a list (also empty) replaces it for this scenario.
    events: list[ScheduleEvent] | None = Field(default=None, max_length=500)


class TimeStepOptions(StrictModel):
    """Euler 时间步误差控制（A0；计划 §12.1）。

    默认关闭，关闭时按 `SolverOptions.dynamic_step_s` 固定步长推进，旧项目与旧默认完全不变。
    开启后每次整步试算都要用两个半步做局部截断误差估计；容差按单位分开，不用一个裸数混合 kg/J/K。
    """

    enabled: bool = False
    # 误差尺度：atol_i + rtol·max(|x_old_i|,|x_fine_i|)；能量先相对冻结参考态中心化（见 timestep.py）。
    mass_atol_kg: float = Field(default=1e-9, gt=0)
    energy_atol_j: float = Field(default=1e-3, gt=0)
    temperature_atol_k: float = Field(default=1e-5, gt=0)
    rtol: float = Field(default=1e-6, gt=0, le=1)
    min_internal_step_s: float = Field(default=1e-3, gt=0, le=60)
    # None 表示沿用 SolverOptions.dynamic_step_s；显式值给出自适应内部步长上限。
    max_internal_step_s: float | None = Field(default=None, gt=0, le=3600)
    safety: float = Field(default=0.9, gt=0, le=1)
    growth_factor: float = Field(default=2.0, gt=1, le=10)
    shrink_factor: float = Field(default=0.5, gt=0, lt=1)

    @model_validator(mode='before')
    @classmethod
    def check_units(cls, data):
        """容差必须带明确单位后缀；漏写单位或写错类别时直接拒绝，不猜数量级。"""
        if not isinstance(data, dict):
            return data
        expected = {'mass_atol_kg', 'energy_atol_j', 'temperature_atol_k'}
        for key in data:
            if key in expected:
                continue
            if key.startswith('atol') or '_atol' in key:
                raise ValueError(f'时间误差容差字段 {key!r} 单位不明确：质量用 mass_atol_kg、'
                                 '能量用 energy_atol_j、温度用 temperature_atol_k')
        return data

    @model_validator(mode='after')
    def check_ranges(self):
        if self.max_internal_step_s is not None and self.min_internal_step_s >= self.max_internal_step_s:
            raise ValueError('内部最小步长必须小于最大步长')
        return self


class SolverOptions(StrictModel):
    module_mixed_jacobian: bool = False
    module_cache: bool = False
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
    # L1/L2：迭代加速模式。'none' = v0.5.0 的固定 0.7/0.3 阻尼（旧项目默认不变）。
    thermal_acceleration: Literal['none', 'adaptive', 'aitken'] = 'none'
    coupling_acceleration: Literal['none', 'adaptive', 'aitken'] = 'none'
    # Implicit time stepping (networks with tanks): a failed substep is retried with half the step.
    max_step_halvings: int = Field(default=6, ge=0, le=20)
    # S1: 'auto' 由实际未知量、Jacobian 稀疏度与模块端口依赖选择；旧项目缺字段仍按 dense。
    hydraulic_method: Literal['dense', 'sparse', 'auto'] = 'dense'
    # B0 观测器开关：只额外返回求解计数/计时（默认关闭），不改变任何数值结果。
    hydraulic_diagnostics: bool = False
    # J2：纯内置关系使用解析 Jacobian；Python 混合网络与非注册模型自动保留有限差分。
    analytic_jacobian: bool = True
    # C/D：串联压缩（C）与依赖安全分块（D）。先默认关闭，验收由 R 决定默认值。
    series_compression: bool = False
    hydraulic_blocks: bool = False
    module_parallelism: int = Field(default=1, ge=1, le=16)
    batch_modules: bool = True
    # A0：Euler 时间步误差控制；默认关闭，旧固定步长语义不变。
    time_step: TimeStepOptions = Field(default_factory=TimeStepOptions)


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


class ControlScript(StrictModel):
    id: Identifier = 'control'
    language: Literal['python'] = 'python'
    enabled: bool = False
    source: str = Field(min_length=1, max_length=100000)
    sample_s: float = Field(default=0.1, ge=0.001, le=60)
    inputs: list[str] = Field(default_factory=list, max_length=256)
    outputs: list[str] = Field(default_factory=list, max_length=256)
    timeout_s: float = Field(default=5, ge=0.1, le=30)
    content_hash: str | None = None

    @model_validator(mode='after')
    def check_script(self):
        import hashlib
        digest = hashlib.sha256(self.source.encode('utf-8')).hexdigest()
        if self.content_hash and self.content_hash != digest:
            raise ValueError('控制脚本源码与哈希不一致')
        self.content_hash = digest
        if len(set(self.inputs)) != len(self.inputs) or len(set(self.outputs)) != len(self.outputs):
            raise ValueError('控制脚本的输入或输出重复')
        return self


class CircuitFluid(StrictModel):
    """Fluid of one circuit: every port connected to `anchor` through connections and enabled
    channels (closed valves included). Circuits without an entry use Project.fluid."""
    id: Identifier
    anchor: Endpoint
    fluid: FluidConfig


class ThermalCoupling(StrictModel):
    """A storage-free single-phase coil immersed in a saturated refrigerant vessel."""

    id: Identifier
    fluid_instance_id: Identifier
    fluid_channel_id: Identifier = 'ch0'
    refrigerant_vessel_id: Identifier
    ua_w_k: float = Field(ge=0)


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
    control_scripts: list[ControlScript] = Field(default_factory=list, max_length=16)
    circuit_fluids: list[CircuitFluid] = Field(default_factory=list, max_length=64)
    thermal_couplings: list[ThermalCoupling] = Field(default_factory=list, max_length=2,
                                                   exclude_if=lambda value: not value)
    # Load/operation schedule; only cold-store projects execute it (others reject a non-empty list).
    events: list[ScheduleEvent] = Field(default_factory=list, max_length=500)

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
        if len({c.id for c in self.thermal_couplings}) != len(self.thermal_couplings):
            raise ValueError('热耦合关系 ID 重复')
        if len({(c.fluid_instance_id, c.fluid_channel_id) for c in self.thermal_couplings}) != len(self.thermal_couplings):
            raise ValueError('同一液体通路只能绑定一条热耦合关系')
        for coupling in self.thermal_couplings:
            if coupling.fluid_instance_id not in instance_map or coupling.refrigerant_vessel_id not in instance_map:
                raise ValueError('热耦合引用了不存在的设备')
        if len({c.id for c in self.controllers}) != len(self.controllers):
            raise ValueError('控制器 ID 重复')
        if len({c.id for c in self.control_scripts}) != len(self.control_scripts):
            raise ValueError('控制脚本 ID 重复')
        targets = [(c.instance_id, c.parameter_id) for c in self.controllers]
        if len(set(targets)) != len(targets):
            raise ValueError('同一参数只能绑定一个控制器')
        if any(c.instance_id not in instance_map for c in self.controllers):
            raise ValueError('控制器目标设备不存在')
        if len({c.id for c in self.circuit_fluids}) != len(self.circuit_fluids):
            raise ValueError('回路工质 ID 重复')
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


class ControlPreviewRequest(StrictModel):
    project: Project
    script: ControlScript


class WorkspaceSaveRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    data: dict[str, Any]

    @model_validator(mode='after')
    def check_workspace(self):
        import json
        if self.data.get('schema') != 1:
            raise ValueError('工作区 schema 必须为 1')
        for field in ('projects', 'modules', 'models'):
            items = self.data.get(field)
            if not isinstance(items, list) or (field != 'models' and not items):
                raise ValueError(f'工作区缺少 {field}')
            ids = [item.get('id') for item in items if isinstance(item, dict)]
            if len(ids) != len(items) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
                raise ValueError(f'{field} 的 ID 必须是唯一的非空字符串')
        if self.data.get('activeProject') not in {p['id'] for p in self.data['projects']}:
            raise ValueError('活动项目不存在')
        if len(json.dumps(self.data, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 64 * 1024 * 1024:
            raise ValueError('工作区超过 64 MiB，请导出并清理不需要的浏览器历史')
        return self


class ProjectDocument(StrictModel):
    format: Literal['fluidnet-project'] = 'fluidnet-project'
    schema_version: Literal[1] = Field(default=1, alias='schema')
    project: dict[str, Any]
    modules: list[dict[str, Any]]
    models: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_document(self):
        import json
        if not isinstance(self.project.get('id'), str) or not self.project['id']:
            raise ValueError('项目 ID 必须是非空字符串')
        for items in (self.modules, self.models):
            ids = [item.get('id') for item in items]
            if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
                raise ValueError('模块和型号 ID 必须唯一且非空')
        if len(json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False).encode('utf-8')) > 64 * 1024**2:
            raise ValueError('单项目文档超过 64 MiB')
        return self


class ProjectSaveRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    document: ProjectDocument


class ProjectRevisionRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    revision: int = Field(ge=1)


class ProjectDeleteRequest(StrictModel):
    expected_revision: int = Field(ge=0)


class CanonicalUnitConversion(StrictModel):
    from_unit: str
    to_unit: str
    scale: float = Field(gt=0)
    offset: float = 0.


class ModuleMigration(StrictModel):
    parameters: dict[Identifier, Identifier | None] = Field(default_factory=dict)
    ports: dict[Identifier, Identifier | None] = Field(default_factory=dict)
    channels: dict[Identifier, Identifier | None] = Field(default_factory=dict)
    variables: dict[str, str | None] = Field(default_factory=dict)
    defaults: dict[Identifier, Any] = Field(default_factory=dict)
    unit_conversions: dict[Identifier, CanonicalUnitConversion] = Field(default_factory=dict)
    script_sources: dict[Identifier, str] = Field(default_factory=dict)


class ProjectUpgradeRequest(StrictModel):
    project: Project
    module_id: Identifier
    target_version: int = Field(ge=1)
    migration: ModuleMigration | None = None


class RunOptions(StrictModel):
    """Shared scheduling and result-selection options for both run entry points."""
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


class RunRequest(RunOptions):
    project: Project
    project_revision: int | None = Field(default=None, ge=1)


class SavedProjectRunRequest(RunOptions):
    """Run a persisted project snapshot; the server supplies its actual revision."""
    revision: int | None = Field(default=None, ge=1)


class RunCommand(StrictModel):
    action: Literal["pause", "resume", "step", "stop", "set", "controller", "write"]
    instance_id: str | None = None
    parameter_id: str | None = None
    value: Any = None
    # action="write": frame keys -> values, applied together at one frame boundary (see VariableWrite).
    values: dict[str, Any] | None = Field(default=None, max_length=256)
    command_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')
    controller_id: Identifier | None = None


class Diagnostic(StrictModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "error"
    instance_id: str | None = None
    field: str | None = None
    module_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    module_version: int | None = Field(default=None, exclude_if=lambda value: value is None)
    phase: str | None = Field(default=None, exclude_if=lambda value: value is None)
    time_s: float | None = Field(default=None, exclude_if=lambda value: value is None)
    source_file: str | None = Field(default=None, exclude_if=lambda value: value is None)
    source_line: int | None = Field(default=None, exclude_if=lambda value: value is None)
    channel_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    source_path: str | None = Field(default=None, exclude_if=lambda value: value is None)
    occurrences: int = Field(default=1, ge=1, exclude_if=lambda value: value == 1)
    first_time_s: float | None = Field(default=None, exclude_if=lambda value: value is None)
    last_time_s: float | None = Field(default=None, exclude_if=lambda value: value is None)


class RunFrame(StrictModel):
    status: str
    valid: bool
    time_s: float
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    # B0 观测器：仅 hydraulic_diagnostics 打开时非空（真实残差/Jacobian/RPC 计数与分项计时）。
    solve_counters: dict | None = None
    # S1/J2 求解选择摘要（请求方法/实际方法/原因/矩阵规模/Jacobian 模式），始终记录。
    solve_summary: dict | None = None
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


class ChannelTestBoundary(StrictModel):
    inlet_pressure_pa: float = Field(default=250000., gt=0)
    outlet_pressure_pa: float = Field(default=120000., gt=0)
    inlet_temperature_k: float = Field(default=293.15, gt=0)
    outlet_temperature_k: float = Field(default=293.15, gt=0)
    fluid: FluidConfig = Field(default_factory=FluidConfig)


class ModuleTestConditions(StrictModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=FluidConfig)
    inlet_pressure_pa: float = Field(default=250000.0, gt=0)
    outlet_pressure_pa: float = Field(default=120000.0, gt=0)
    temperature_k: float = Field(default=293.15, gt=0)
    duration_s: float = Field(default=0.1, gt=0, le=60)
    dt_s: float = Field(default=0.1, gt=0, le=60)
    channel_boundaries: dict[Identifier, ChannelTestBoundary] = Field(default_factory=dict)
    property_coupling: Literal['reference','node'] = 'reference'

    @model_validator(mode="after")
    def limit_frames(self):
        if self.duration_s > 2000 * self.dt_s:
            raise ValueError("独立测试最多 2001 帧")
        return self


class ModuleTestRequest(ModuleTestConditions):
    module: ModuleDefinition


class ModuleTestAssertion(StrictModel):
    """An author's expected final-frame value, expressed in canonical units."""

    key: str = Field(min_length=1, max_length=256, pattern=r'^\S+$')
    expected: float = Field(strict=True)
    absolute_tolerance: float = Field(default=0., ge=0, strict=True)
    relative_tolerance: float = Field(default=0., ge=0, strict=True)


class ModuleTestCase(StrictModel):
    id: Identifier
    conditions: ModuleTestConditions = Field(default_factory=ModuleTestConditions)
    assertions: list[ModuleTestAssertion] = Field(default_factory=list, max_length=256)

    @model_validator(mode='after')
    def unique_assertions(self):
        if len({assertion.key for assertion in self.assertions}) != len(self.assertions):
            raise ValueError('测试断言变量键重复')
        return self


class ModuleTestSuiteRequest(StrictModel):
    module: ModuleDefinition
    cases: list[ModuleTestCase] = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def unique_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError('测试组合 ID 重复')
        return self


class ModuleTemplateRequest(StrictModel):
    template: Literal['resistance', 'pump', 'heat_exchanger', 'managed_state']
    id: Identifier
    name: str = Field(min_length=1, max_length=80)
    category: str = '自定义模块'


class ModuleGroupRequest(StrictModel):
    project: Project
    instance_ids: list[Identifier] = Field(min_length=1,max_length=100)
    id: Identifier
    name: str = Field(min_length=1,max_length=80)


class ModuleTestResponse(StrictModel):
    module_id: str
    content_hash: str
    state: dict[str, Any] = Field(default_factory=dict)
    evaluation: EvaluateResponse
    committed: CommitStepResponse
    frame: RunFrame
    history: list[RunFrame] = Field(default_factory=list)


class ModuleTestAssertionResult(ModuleTestAssertion):
    actual: float | int | str | bool | None = None
    absolute_error: float | None = None
    allowed_error: float | None = None
    passed: bool
    status: Literal['passed', 'outside_tolerance', 'missing', 'non_numeric', 'non_finite', 'not_evaluated']
    message: str = ''


class ModuleTestCaseResult(StrictModel):
    id: Identifier
    passed: bool
    input_hash: str
    level: Literal['L3'] = 'L3'
    result: ModuleTestResponse | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    assertions: list[ModuleTestAssertionResult] = Field(default_factory=list)


class ModuleTestSuiteResponse(StrictModel):
    module_id: str
    content_hash: str
    definition_hash: str
    passed: bool
    cases: list[ModuleTestCaseResult]


class ModuleDesignRequest(StrictModel):
    """Run design.py once on one library-value set; nothing is stored."""
    module: ModuleDefinition
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=FluidConfig)


class ParameterChange(StrictModel):
    id: str
    before: Any = None
    after: Any = None


class ModuleDesignResponse(StrictModel):
    module_id: str
    design_hash: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    changes: list[ParameterChange] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class UnitWorkpointRequest(StrictModel):
    """Condensing-unit bench (cold-store case): one cycle point at given saturation temperatures (K)."""
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=lambda: FluidConfig(fluid='HEOS::R290'))
    evaporating_temperature_k: float = Field(gt=0)
    condensing_temperature_k: float = Field(gt=0)
    capacity_ratio: float = Field(default=1., gt=0, le=1)


class UnitWorkpointResponse(StrictModel):
    design: dict[str, float]
    point: dict[str, float | None]
    unit_electric_power_w: float
    unit_cop: float
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class ModuleSaveRequest(StrictModel):
    module: ModuleDefinition
    expected_latest_version: int = Field(ge=0)
    release_notes: str = Field(default="", max_length=2000)
    test: ModuleTestConditions = Field(default_factory=ModuleTestConditions)


class ModuleValidationEvidence(StrictModel):
    level: Literal['L1','L2','L3','L4','external']
    status: Literal['passed','failed','pending']
    source: str
    content_hash: str
    definition_hash: str
    input_hash: str
    engine_version: str
    sdk_version: str
    tolerances: dict[str, float] = Field(default_factory=dict)


class ModuleVersionInfo(StrictModel):
    package: ModulePackageRef
    created_at: str | None = None
    release_notes: str = ""
    tested: bool = False
    validation_evidence: list[ModuleValidationEvidence] = Field(default_factory=list)


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


class ErrorDetail(Diagnostic):
    """结构化错误 `detail`：服务端主动抛出的 code/message，可带诊断与定位字段。"""
    code: str
    message: str
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    keys: list[str] = Field(default_factory=list)
    instance_id: str | None = None
    field: str | None = None
    replay: dict[str, Any] | None = Field(default=None, exclude_if=lambda value: value is None)


class ValidationIssue(BaseModel):
    """FastAPI/Pydantic 请求校验失败时 `detail` 列表中的一项（字段随错误类型变化）。"""
    model_config = ConfigDict(extra='allow')

    type: str
    loc: list[str | int] = Field(default_factory=list)
    msg: str
    input: Any = None


class ErrorResponse(StrictModel):
    """HTTP 错误响应包络。

    运行时 FastAPI 统一输出 `{"detail": …}`：`detail` 可能是结构化错误（`ErrorDetail`）、
    纯文本说明，或请求校验问题列表。本模型只用于 OpenAPI 文档化，不改变运行时响应体。
    """
    detail: ErrorDetail | str | list[ValidationIssue]


class CircuitInfo(StrictModel):
    """One fluid circuit of a compiled project: its fluid and the ports it contains."""
    id: int
    fluid: FluidConfig
    source: str  # CircuitFluid.id that set the fluid, or "project"
    ports: list[str] = Field(default_factory=list)


class ValidationResponse(StrictModel):
    valid: bool
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    circuits: list[CircuitInfo] = Field(default_factory=list)


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


class VariableWrite(StrictModel):
    """POST /runs/{id}/variables: values by frame key, all applied at one frame boundary or none."""
    values: dict[str, float | int | str | bool] = Field(min_length=1, max_length=256)
    command_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')
    # Wait up to this long for the write to be applied or rejected (0 = return the accepted receipt).
    wait_s: float = Field(default=0., ge=0, le=10)


class VariableValues(StrictModel):
    run_id: str
    status: str
    time_s: float | None = None
    sequence: int | None = None
    parameter_revision: int | None = None
    values: dict[str, float | int | str | bool | None] = Field(default_factory=dict)


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
    validation_evidence: list[ModuleValidationEvidence] = Field(default_factory=list)
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
    persisted_at: str | None = None
    persisted_rows: int = 0


class RefpropInfo(StrictModel):
    """`GET /health` 上报的 REFPROP 运行时发现结果（不加载 DLL）。"""
    installed: bool
    source: Literal['env', 'bundled', 'system'] | None = None
    path: str | None = None
    version: str | None = None


class HealthCapabilities(StrictModel):
    thermal_coupling: bool = False
    # Two immersed coils bound to one saturated vessel (contract limit is two).
    dual_thermal_coupling: bool = False
    # Built-in ideal electric heater in the single-phase fluid network.
    heater: bool = False
    scenario_batches: bool = False
    # Saturated vessels with up to four stream inlets (`hp_receiver_multi`, `lp_drum_multi`).
    multi_inlet_vessels: bool = False
    cold_room_ideal_source: bool = False
    refrigeration_station: bool = False
    # Case A: storage room + goods, unit cooler, single-stage cycle, schedule events and reports.
    cold_store_cycle: bool = False
    steady_hydraulics: bool
    quasi_steady_series: bool
    thermal: bool
    property_coupling: list[str] = Field(default_factory=list)
    tank_state: bool
    time_integration: str
    coolprop_single_phase: bool
    user_code: bool
    worker_process: bool
    async_runs: bool
    module_versions: bool
    run_control: bool
    live_runs: bool
    pid: bool
    runtime_parameters: bool
    continuous_step: bool
    continuous_runs: bool
    variables_api: bool
    run_stream: bool
    python_controls: bool
    persistent_workspace: bool
    refprop: RefpropInfo


class HealthAuth(StrictModel):
    required: bool


class HealthResponse(StrictModel):
    """`GET /health`：版本、能力标志与全局上限。"""
    status: str
    mode: Literal['studio', 'headless']
    version: str
    solver: str
    supported_domains: list[str] = Field(default_factory=list)
    capabilities: HealthCapabilities
    max_frames: int = Field(ge=0)
    run_retention: int = Field(ge=0)
    history_window_max: int = Field(ge=0)
    overview_points: int = Field(ge=0)
    auth: HealthAuth


class WorkspaceRevision(StrictModel):
    revision: int = Field(ge=0)
    saved_at: str


class WorkspaceResponse(StrictModel):
    """`GET /workspace`：最新（或指定修订）完整工作区；未保存时 revision=0、data=null。"""
    revision: int = Field(ge=0)
    saved_at: str | None = None
    data: dict[str, Any] | None = None
    project_revisions: dict[str, int] = Field(default_factory=dict)


class WorkspaceRevisionsResponse(StrictModel):
    revisions: list[WorkspaceRevision] = Field(default_factory=list)


class WorkspaceStorageResponse(StrictModel):
    database_bytes: int = Field(ge=0)
    reusable_bytes: int = Field(ge=0)
    wal_bytes: int = Field(ge=0)
    free_disk_bytes: int = Field(ge=0)
    runs: int = Field(ge=0)
    frames: int = Field(ge=0)
    revision_retention: int = Field(ge=0)
    run_retention: int = Field(ge=0)
    history_window_max: int = Field(ge=0)
    overview_points: int = Field(ge=0)


class WorkspaceSaveResponse(StrictModel):
    revision: int = Field(ge=1)
    saved_at: str
    project_revisions: dict[str, int] = Field(default_factory=dict)


class WorkspaceRestoreResponse(StrictModel):
    directory: str
    revision: int = Field(ge=0)
    command: str
    message: str


class ControlPreviewResponse(StrictModel):
    """`POST /controls/preview`：一次 initialize+step 的拟写入值，不产生运行档案。"""
    state: dict[str, Any] = Field(default_factory=dict)
    writes: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    content_hash: str
    time_s: float = 0.0
    applied: bool = False


class ProjectSummary(StrictModel):
    id: str
    name: str
    revision: int = Field(ge=1)
    saved_at: str
    instances: int = Field(ge=0)


class ProjectListResponse(StrictModel):
    projects: list[ProjectSummary] = Field(default_factory=list)


class ProjectRevisionInfo(StrictModel):
    revision: int = Field(ge=1)
    saved_at: str
    deleted: bool = False


class ProjectRevisionsResponse(StrictModel):
    revisions: list[ProjectRevisionInfo] = Field(default_factory=list)


class ProjectDetailResponse(StrictModel):
    revision: int = Field(ge=1)
    saved_at: str
    document: ProjectDocument


class ProjectSaveResponse(StrictModel):
    revision: int = Field(ge=1)
    saved_at: str
    workspace_revision: int = Field(ge=1)
    previous_workspace_revision: int = Field(ge=0)


class ProjectRestoreResponse(ProjectSaveResponse):
    document: ProjectDocument


class ProjectDeleteResponse(ProjectSaveResponse):
    pass


class ProjectUpgradeChange(StrictModel):
    field: str
    id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class ProjectUpgradeResponse(StrictModel):
    """`POST /project-upgrades/preview`：版本差异与兼容性结论；兼容时附升级后的项目。"""
    module_id: str
    from_version: int = Field(ge=1)
    to_version: int = Field(ge=1)
    from_hashes: ModulePackageRef
    to_hashes: ModulePackageRef
    source_before: str
    source_after: str
    changes: list[ProjectUpgradeChange] = Field(default_factory=list)
    compatible: bool
    reasons: list[str] = Field(default_factory=list)
    module: ModuleDefinition
    project: Project | None = None
    references: list[str] = Field(default_factory=list)
    migration: ModuleMigration | None = None


class RunSummary(StrictModel):
    id: str
    status: str
    mode: str
    name: str
    time_s: float = 0.0


class RunListResponse(StrictModel):
    runs: list[RunSummary] = Field(default_factory=list)


class RunDeleteResponse(StrictModel):
    deleted: str


EvaluateResponse.model_rebuild()
CommitStepResponse.model_rebuild()
