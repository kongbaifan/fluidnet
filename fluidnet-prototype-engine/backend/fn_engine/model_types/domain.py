"""Domain contracts; wire fields and validation preserve the legacy model semantics."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .._module_schema_v1 import Identifier, StrictModel, UnitSpec
from ..air_models import MoistAirOptions
from .base import Diagnostic, FluidConfig, ModulePackageRef
from .module import ModuleDefinition


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
    coupling_viscosity_rtol: float = Field(default=1e-6, gt=0, exclude_if=lambda v: v == 1e-6)
    # Flow acceptance combines this relative bound with mass_tolerance_kg_s at zero flow.
    coupling_flow_rtol: float = Field(default=1e-6, gt=0, exclude_if=lambda v: v == 1e-6)
    # L1/L2：迭代加速模式。'none' = v0.5.0 的固定 0.7/0.3 阻尼（旧项目默认不变）。
    thermal_acceleration: Literal['none', 'adaptive', 'aitken'] = 'none'
    coupling_acceleration: Literal['none', 'adaptive', 'aitken'] = 'none'
    # 湿空气网络：把含湿量作为与焓并列的输运标量（默认关闭，旧项目行为不变）。
    # 仅支持空气单相网络与内置风侧元件；湿工况表冷器/加湿器需要开启本项。
    moist_air: bool = False
    moist_air_options: MoistAirOptions | None = Field(default=None, exclude_if=lambda v: v is None)
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


class MeasurementSpec(StrictModel):
    id: Identifier
    label: str
    kind: Literal['value', 'difference', 'volume_flow', 'thermal_power'] = 'value'
    sources: list[str] = Field(min_length=1, max_length=3)
    unit: UnitSpec

    @model_validator(mode='after')
    def check_sources(self):
        count = {'value':1, 'difference':2, 'volume_flow':2, 'thermal_power':3}[self.kind]
        if len(self.sources) != count:
            raise ValueError('测点输入数量与计算类型不一致')
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
    measurements: list[MeasurementSpec] = Field(default_factory=list, max_length=64, exclude_if=lambda value: not value)
    import_diagnostics: list[Diagnostic] = Field(default_factory=list)
    solver: SolverOptions = Field(default_factory=SolverOptions)
    controllers: list[PIDController] = Field(default_factory=list)
    control_scripts: list[ControlScript] = Field(default_factory=list, max_length=16)
    circuit_fluids: list[CircuitFluid] = Field(default_factory=list, max_length=64)
    coupling_mode: Literal['legacy','storage_v1'] = Field(default='legacy',exclude_if=lambda v:v=='legacy')
    thermal_couplings: list[ThermalCoupling] = Field(default_factory=list, max_length=8,
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
        if self.coupling_mode=='legacy' and len(self.thermal_couplings)>2:
            raise ValueError('旧热耦合模式最多两条关系')
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
