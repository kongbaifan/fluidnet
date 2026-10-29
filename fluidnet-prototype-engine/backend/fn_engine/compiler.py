from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field

from .catalog import builtin_catalog
from .models import Diagnostic, Domain, FluidConfig, ModuleDefinition, ModuleInstance, Project
from .trapped import TrappedError, TrappedSpec, build_spec as trapped_build_spec


class CompilationError(ValueError):
    def __init__(self, code, message, instance_id=None, field=None):
        self.diagnostic = Diagnostic(code=code, message=message, instance_id=instance_id, field=field)
        super().__init__(message)


class DisjointSet:
    def __init__(self, values):
        self.parent = {value: value for value in values}

    def find(self, value):
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while value != root:
            value, self.parent[value] = self.parent[value], root
        return root

    def union(self, left, right):
        self.parent[self.find(right)] = self.find(left)


@dataclass
class CompiledBranch:
    instance_id: str
    channel_id: str
    solver_model: str
    input_port: str
    output_port: str
    start_node: int
    end_node: int
    closed: bool = False


GRAVITY = 9.80665


@dataclass
class StorageSpec:
    """An open tank: one well-mixed node whose bottom pressure is p_surface + g·M/A."""
    instance_id: str
    node: int
    area_m2: float
    height_m: float
    surface_pressure_pa: float
    heat_input_w: float
    heat_loss_ua_w_k: float
    ambient_temperature_k: float
    # Initial state, consistent with the property service: level = M/(ρ(p_bottom, T)·A).
    initial_mass_kg: float
    initial_pressure_pa: float
    initial_temperature_k: float
    initial_enthalpy_j_kg: float

    def pressure(self, mass_kg: float) -> float:
        return self.surface_pressure_pa + GRAVITY * mass_kg / self.area_m2


@dataclass
class TankState:
    """Accepted tank state at the start of an implicit step."""
    mass_kg: float
    enthalpy_j_kg: float


@dataclass
class CompiledNetwork:
    composite_maps: dict = field(default_factory=dict, kw_only=True)
    project: Project
    modules: dict[str, ModuleDefinition]
    instances: dict[str, ModuleInstance]
    parameters: dict[str, dict]
    port_nodes: dict[str, int]
    node_keys: list[str]
    branches: list[CompiledBranch]
    fixed_pressures: dict[int, float]
    diagnostics: list[Diagnostic]
    # Boundary temperature per fixed-pressure node and the static hydraulic component of every node.
    fixed_temperatures: dict[int, float] = field(default_factory=dict)
    node_component: list[int] = field(default_factory=list)
    # Tank nodes. They also appear in fixed_pressures/fixed_temperatures with their initial state,
    # which is how steady runs and the first dynamic frame treat them (a large reservoir).
    storage: dict[int, StorageSpec] = field(default_factory=dict)
    # Fluid circuits: nodes joined by connections and enabled channels, closed valves included.
    # node_circuit[node] indexes circuit_fluids; `mixed` is False when every circuit uses the same
    # fluid, and then every caller keeps using the single project fluid exactly as before.
    node_circuit: list[int] = field(default_factory=list)
    circuit_fluids: list[FluidConfig] = field(default_factory=list)
    circuit_sources: list[str] = field(default_factory=list)
    mixed: bool = False
    # 困液定容容积（I0–I4）：节点 -> 配置。节点同时出现在 fixed_pressures/fixed_temperatures 里，
    # 作为编译期与首帧的初态压力/温度参考；动态步用积分状态覆盖它们。
    trapped: dict[int, TrappedSpec] = field(default_factory=dict)
    # 湿空气模式：固定压力节点的边界含湿量（kg 水/kg 干空气）；放在末尾以保持位置参数向后兼容。
    fixed_humidities: dict[int, float] = field(default_factory=dict)

    def fluid_at(self, node: int) -> FluidConfig:
        return self.circuit_fluids[self.node_circuit[node]] if self.mixed else self.project.fluid


def service_at(network: CompiledNetwork, node: int, default=None):
    """Property service for the fluid at `node`; `default` (the project service) when not mixed."""
    if not network.mixed and default is not None:
        return default
    from .properties import property_service
    return property_service(network.fluid_at(node))


def instance_fluids(network: CompiledNetwork, instance_id: str) -> tuple[FluidConfig, dict[str, FluidConfig]]:
    """A module's fluid (its first port's circuit) and the ports whose circuit uses another fluid."""
    definition = network.modules[network.instances[instance_id].module_id]
    nodes = {port.id: network.port_nodes[f'{instance_id}:{port.id}'] for port in definition.ports}
    if not network.mixed or not nodes:
        return network.project.fluid, {}
    main = network.fluid_at(next(iter(nodes.values())))
    return main, {port: network.fluid_at(node) for port, node in nodes.items() if network.fluid_at(node) != main}


@functools.lru_cache(maxsize=1)
def _registered_models() -> dict[str, ModuleDefinition]:
    """First built-in definition per solver_model; read-only (runtime writes validate parameters every sample)."""
    registered: dict[str, ModuleDefinition] = {}
    for module in builtin_catalog():
        registered.setdefault(module.solver_model, module)
    return registered


def validated_parameters(instance, definition):
    # Registered model constraints remain authoritative for safety limits, while
    # the project definition owns defaults. This keeps custom package defaults
    # from being silently replaced by a same-shaped built-in model.
    registered = _registered_models().get(definition.solver_model) if definition.runtime == 'builtin' else None
    specs = {p.id: p for p in definition.parameters}
    if registered:
        for registered_spec in registered.parameters:
            current = specs.get(registered_spec.id)
            if current is None:
                specs[registered_spec.id] = registered_spec
            else:
                updates = {}
                if registered_spec.minimum is not None:
                    updates['minimum'] = max(current.minimum, registered_spec.minimum) if current.minimum is not None else registered_spec.minimum
                if registered_spec.maximum is not None:
                    updates['maximum'] = min(current.maximum, registered_spec.maximum) if current.maximum is not None else registered_spec.maximum
                if updates:
                    specs[registered_spec.id] = current.model_copy(update=updates)
    unknown = instance.parameters.keys() - specs.keys()
    if unknown:
        raise CompilationError('UNKNOWN_PARAMETER', f'{instance.id} 未定义参数：{sorted(unknown)}', instance.id)
    values = {p.id: p.default for p in specs.values()} | instance.parameters
    for key, spec in specs.items():
        value = values[key]
        if spec.value_type == 'number':
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise CompilationError('PARAMETER_INVALID', f'{instance.id}.{key} 必须是有限数值', instance.id, key)
            if spec.minimum is not None and value < spec.minimum or spec.maximum is not None and value > spec.maximum:
                raise CompilationError('PARAMETER_RANGE', f'{instance.id}.{key} 超出范围 [{spec.minimum}, {spec.maximum}]', instance.id, key)
        elif spec.value_type == 'boolean' and not isinstance(value, bool):
            raise CompilationError('PARAMETER_INVALID', f'{instance.id}.{key} 必须是布尔值', instance.id, key)
        elif spec.value_type == 'text' and not isinstance(value, str):
            raise CompilationError('PARAMETER_INVALID', f'{instance.id}.{key} 必须是文本', instance.id, key)
        if key == 'head_curve':
            valid = isinstance(value, list) and len(value) >= 2
            valid = valid and all(isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0 for x in p) for p in value)
            valid = valid and value[0][0] == 0 and value[-1][1] == 0
            valid = valid and all(b[0] > a[0] and b[1] < a[1] for a, b in zip(value, value[1:]))
            if not valid:
                raise CompilationError('CURVE_INVALID', f'{instance.id} 扬程曲线需从零流量开始，流量递增、扬程严格递减且末点扬程为零', instance.id, key)
    # 相对粗糙度的分母必须严格为正: 未声明最小值的自定义模块可能传入 0 或负值,
    # 若不拦截会让 ZeroDivisionError 逃出所有处理器并变成 HTTP 500。
    if 'roughness_m' in values and 'diameter_m' in values:
        diameter, roughness = values['diameter_m'], values['roughness_m']
        if isinstance(diameter, bool) or not isinstance(diameter, (int, float)) or not math.isfinite(diameter) or diameter <= 0:
            raise CompilationError('PARAMETER_RANGE', f'{instance.id}.diameter_m 必须大于零', instance.id, 'diameter_m')
        if isinstance(roughness, bool) or not isinstance(roughness, (int, float)) or not math.isfinite(roughness) or roughness < 0:
            raise CompilationError('PARAMETER_RANGE', f'{instance.id}.roughness_m 不能小于零', instance.id, 'roughness_m')
        if roughness / diameter > .05:
            raise CompilationError('ROUGHNESS_RANGE', '相对粗糙度必须不大于 0.05', instance.id, 'roughness_m')
    if 'thermal_cells' in values and float(values['thermal_cells']) != int(values['thermal_cells']):
        raise CompilationError('PARAMETER_INVALID', f'{instance.id}.thermal_cells 必须是整数', instance.id, 'thermal_cells')
    return values


def fluid_service(project: Project, config: FluidConfig | None = None, label: str = '项目工质'):
    """The property service of a fluid; an unusable fluid string is a compile error, not a solve failure."""
    from .properties import PropertyError, property_service
    config = config or project.fluid
    try:
        service = property_service(config)
        service.limits()  # loads the fluid: unknown names fail here with FLUID_UNKNOWN
    except PropertyError as error:
        raise CompilationError(error.code, f'{label} {config.fluid}：{error}', field='fluid') from error
    return service


def _fluid_identity(config: FluidConfig):
    """Two configs name the same fluid ('Water' and 'HEOS::Water', same basis and phase policy)."""
    from .properties import _parse_fluid
    return _parse_fluid(config), config.phase_policy


def assign_circuits(project, modules, nodes, node_count):
    """Circuit index per node, fluid per circuit and the CircuitFluid id that set it."""
    circuits = DisjointSet(range(node_count))
    for inst in project.instances:
        definition = modules[inst.module_id]
        if definition.solver_model in ('pressure_source', 'junction', 'tank'):
            continue
        for ch in definition.channels:
            if ch.enabled:
                circuits.union(nodes[f'{inst.id}:{ch.input_port}'], nodes[f'{inst.id}:{ch.output_port}'])
    first = {}
    for n in range(node_count):
        first.setdefault(circuits.find(n), n)
    index = {root: i for i, root in enumerate(sorted(first, key=first.get))}
    node_circuit = [index[circuits.find(n)] for n in range(node_count)]
    fluids, sources = [project.fluid] * len(index), ['project'] * len(index)
    instances = {i.id: i for i in project.instances}
    for entry in project.circuit_fluids:
        key = f'{entry.anchor.instance_id}:{entry.anchor.port_id}'
        if key not in nodes:
            raise CompilationError('CIRCUIT_ANCHOR_UNKNOWN', f'回路工质 {entry.id} 的锚点端口 {key} 不存在',
                                   entry.anchor.instance_id if entry.anchor.instance_id in instances else None, 'circuit_fluids')
        fluid_service(project, entry.fluid, f'回路工质 {entry.id}')
        circuit = node_circuit[nodes[key]]
        if sources[circuit] != 'project' and _fluid_identity(fluids[circuit]) != _fluid_identity(entry.fluid):
            raise CompilationError('FLUID_CONFLICT', f'回路工质 {entry.id}（{entry.fluid.fluid}）与 {sources[circuit]}'
                                   f'（{fluids[circuit].fluid}）指定在同一个回路；同一回路只能有一种工质',
                                   entry.anchor.instance_id, 'circuit_fluids')
        fluids[circuit], sources[circuit] = entry.fluid, entry.id
    # Compared with the project fluid, not only among circuits: a single circuit given another
    # fluid must not fall back to Project.fluid.
    mixed = len({_fluid_identity(f) for f in fluids} | {_fluid_identity(project.fluid)}) > 1
    return node_circuit, fluids, sources, mixed


def check_fluid_conditions(instance_id: str, params: dict, solver_model: str, service, thermal: bool = True) -> None:
    """Boundary/ambient conditions must lie inside the fluid's valid range.

    Replaces the old fixed 1–90 °C bounds: liquid ammonia at −30 °C is fine, water below its
    triple point is not. A water boundary must also be liquid, because the reference
    hydraulics use the constant liquid-water density for it.
    """
    from .properties import PropertyError, is_pure_water
    limits, name = service.limits(), service.fluid
    span = f'{limits["t_min_k"] - 273.15:.2f}…{limits["t_max_k"] - 273.15:.2f} °C'
    checks = [('temperature_k', params.get('temperature_k'))] if solver_model in ('pressure_source', 'tank') else []
    if solver_model in ('pipe', 'duct', 'tank'):
        checks.append(('ambient_temperature_k', params.get('ambient_temperature_k')))
    for key, temperature in checks:
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            continue
        if not limits['t_min_k'] <= temperature <= limits['t_max_k']:
            raise CompilationError('PARAMETER_RANGE', f'{instance_id}.{key} = {temperature - 273.15:.2f} °C 超出 {name} 的适用范围 {span}',
                                   instance_id, key)
    if solver_model != 'pressure_source':
        return
    pressure, temperature = params.get('pressure_pa'), params.get('temperature_k')
    if not isinstance(pressure, (int, float)) or isinstance(pressure, bool) or not math.isfinite(pressure):
        raise CompilationError('PARAMETER_INVALID', f'{instance_id}.pressure_pa 必须是有限数值', instance_id, 'pressure_pa')
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not math.isfinite(temperature):
        raise CompilationError('PARAMETER_INVALID', f'{instance_id}.temperature_k 必须是有限数值', instance_id, 'temperature_k')
    if limits['p_max_pa'] is not None and pressure > limits['p_max_pa']:
        raise CompilationError('PARAMETER_RANGE', f'{instance_id}.pressure_pa = {pressure:g} Pa 超出 {name} 的最高压力 '
                               f'{limits["p_max_pa"]:g} Pa', instance_id, 'pressure_pa')
    try:
        state = service.state_pt(pressure, temperature)
    except PropertyError as error:
        raise CompilationError(error.code, f'{instance_id} 的边界状态（{pressure:g} Pa，{temperature - 273.15:.2f} °C）：{error}',
                               instance_id, 'temperature_k') from error
    # Only with the thermal layer on: thermal=False must keep accepting what 0.3.0 accepted.
    # Same code as the thermal layer's own phase check.
    if thermal and is_pure_water(service.config) and 'liquid' not in state.phase:
        raise CompilationError('PHASE_UNSUPPORTED', f'{instance_id} 的边界在 {pressure:g} Pa、{temperature - 273.15:.2f} °C 下 Water 为'
                               f' {state.phase}；水按液态参考物性计算，边界必须是液相', instance_id, 'temperature_k')


def tank_initial_state(instance_id: str, params: dict, node: int, service) -> StorageSpec:
    """Initial mass and bottom pressure of an open tank from its level, area and temperature.

    p_bottom = p_surface + ρ(p_bottom, T)·g·level is a fixed point; liquid density hardly depends
    on pressure, so a few passes reach machine precision. The tank must hold a liquid.
    """
    from .properties import PropertyError
    level, area, height = params['level_m'], params['area_m2'], params['height_m']
    surface, temperature = params['surface_pressure_pa'], params['temperature_k']
    if level > height:
        raise CompilationError('PARAMETER_RANGE', f'{instance_id}.level_m = {level:g} m 超过罐高 {height:g} m', instance_id, 'level_m')
    pressure = surface
    try:
        for _ in range(6):
            state = service.state_pt(pressure, temperature)
            pressure = surface + state.density_kg_m3 * GRAVITY * level
        state = service.state_pt(pressure, temperature)
    except PropertyError as error:
        raise CompilationError(error.code, f'{instance_id} 的初始状态（{temperature - 273.15:.2f} °C）：{error}',
                               instance_id, 'temperature_k') from error
    if 'liquid' not in state.phase:
        raise CompilationError('PHASE_UNSUPPORTED', f'{instance_id} 在 {pressure:g} Pa、{temperature - 273.15:.2f} °C 下 '
                               f'{service.fluid} 为 {state.phase}；开式水箱只能储存液体', instance_id, 'temperature_k')
    mass = state.density_kg_m3 * area * level
    pressure = surface + GRAVITY * mass / area
    enthalpy = service.state_pt(pressure, temperature).enthalpy_j_kg
    return StorageSpec(instance_id, node, area, height, surface, params['heat_input_w'], params['heat_loss_ua_w_k'],
                       params['ambient_temperature_k'], mass, pressure, temperature, enthalpy)


def _compile_trapped(project, modules, parameters, nodes, branches, fixed, fixed_temperatures, storage,
                     service_of, diagnostics) -> dict[int, TrappedSpec]:
    """困液定容容积（I0–I4）的识别、范围检查与拒绝条件。

    只接受单一均匀容积、HEOS 纯水单相液体、两端相邻支路全关的被动段，并把初态压力/温度登记为
    该子网络的唯一压力参考。多容积、与开式水箱混用、与压力边界同节点、非 HEOS/非纯水、初态越界
    都在编译期给出具体诊断，不生成“定压近似”的替代结果。
    """
    instances = [inst for inst in project.instances if modules[inst.module_id].solver_model == 'closed_volume']
    if not instances:
        return {}
    first = instances[0]
    if storage:
        tank = next(iter(storage.values()))
        raise CompilationError('TRAPPED_TANK_MIXED', f'{first.id}（封闭定容容积）不能与开式水箱 {tank.instance_id} 混用；'
                               '水箱是定压储量节点，困液定容需要独立的单容积压力参考', first.id)
    if len(instances) > 1:
        names = '、'.join(inst.id for inst in instances)
        raise CompilationError('TRAPPED_MULTIVOLUME_UNSUPPORTED', f'第一阶段只支持单一均匀容积；检测到多个封闭定容容积'
                               f'（{names}）。多容积串联需要逐段显式体积与共同压力方程，属 I5–I9 的后续扩展', first.id)
    definition, params = modules[first.module_id], parameters[first.id]
    node = nodes[f'{first.id}:{definition.ports[0].id}']
    if node in fixed:
        raise CompilationError('TRAPPED_PRESSURE_REFERENCE_CONFLICT', f'{first.id} 与压力边界（或其他定压节点）接在同一节点；'
                               '封闭定容容积本身就是该子网络的唯一压力参考，不能再跨接到别的压力参考', first.id)
    try:
        spec, _ = trapped_build_spec(first.id, node, params, service_of(first.id))
    except TrappedError as error:
        raise CompilationError(error.code, str(error), first.id, error.field) from error
    open_branches = [b for b in branches if node in (b.start_node, b.end_node) and not b.closed]
    if open_branches:
        names = '、'.join(branch.instance_id for branch in open_branches)
        raise CompilationError('TRAPPED_NOT_CLOSED', f'{first.id} 的相邻设备/支路 {names} 在初始时刻未关闭'
                               '（opening_ratio > 0）；第一阶段要求两端全关，初态 p/T 显式给定并保持封闭', first.id)
    fixed[node] = spec.initial_pressure_pa
    fixed_temperatures[node] = spec.initial_temperature_k
    diagnostics.append(Diagnostic(code='TRAPPED_PROTOTYPE_ONLY', severity='info', instance_id=first.id,
        message=f'{first.id} 是单容积封闭定容原型（I0–I4）：V={spec.volume_m3:g} m³，M={spec.initial_mass_kg:.6g} kg，'
                f'p={spec.initial_pressure_pa:.6g} Pa，T={spec.initial_temperature_k:.6g} K，'
                f'C_wall={spec.wall_heat_capacity_j_k:g} J/K；只支持 HEOS 纯水单相液体与两端全关，'
                '完整开闭周期与任意阀门隔离网络仍未实现'))
    return {node: spec}


def compile_project(project: Project) -> CompiledNetwork:
    from .composites import expand_composites
    project, composite_maps = expand_composites(project)
    if project.thermal_couplings:
        from .refrigeration.coupling import compile_coupled_project
        return compile_coupled_project(project)
    used = {instance.module_id for instance in project.instances}
    used_domains = {port.domain for module in project.modules if module.id in used for port in module.ports}
    if Domain.fluid in used_domains and Domain.refrigerant in used_domains:
        raise CompilationError('COUPLED_RELATION_MISSING',
            '项目同时包含单相流体网络与制冷站，但尚未建立热耦合；请选择液体管段和饱和制冷剂容器建立关系',
            field='thermal_couplings')
    if Domain.thermal in used_domains or Domain.refrigerant in used_domains:
        from .refrigeration.cold_store import check_event_conflicts, compile_cold_store, uses_cold_store
        if uses_cold_store(project):
            network = compile_cold_store(project)
            check_event_conflicts(network)
            return network
    if project.events and Domain.refrigerant not in used_domains:
        raise CompilationError('SCHEDULE_UNSUPPORTED', '只有冷库系统和集总制冷站执行运行日程', field='events')
    if Domain.refrigerant in used_domains:
        from .refrigeration.station import compile_station
        return compile_station(project)
    if Domain.thermal in used_domains:
        from .refrigeration.compile import compile_thermal_project
        return compile_thermal_project(project)
    modules = {m.id: m for m in project.modules}
    instances = {i.id: i for i in project.instances}
    if not instances:
        raise CompilationError('EMPTY_NETWORK', '项目没有设备')
    diagnostics = list(project.import_diagnostics)
    parameters, port_keys = {}, []
    supported = {'pressure_source', 'junction', 'valve', 'pipe', 'duct', 'pump_curve', 'heat_exchanger', 'tank',
                 'closed_volume', 'heater', 'cooling_coil', 'humidifier'}
    # 湿空气网络只接受空气单相与内置风侧元件（Python 模块按干空气近似参与）。
    moist = project.solver.moist_air
    moist_models = {'pressure_source', 'junction', 'valve', 'pipe', 'duct', 'heater', 'cooling_coil', 'humidifier'}
    if moist:
        fluid_name = (project.fluid.fluid or '').split('::')[-1]
        if project.fluid.phase_policy != 'gas' or fluid_name != 'Air':
            raise CompilationError('MOIST_AIR_FLUID_REQUIRED', '湿空气模式要求 fluid=Air 且 phase_policy=gas')
        if project.solver.moist_air_options is None:
            raise CompilationError('AIR_CONTRACT_VERSION_REQUIRED', '旧湿空气项目需先预览迁移并确认合同版本 1', field='solver.moist_air_options')
        if not project.solver.thermal or project.solver.property_coupling != 'node':
            raise CompilationError('AIR_SOLVER_OPTIONS', '湿空气模式必须启用 thermal=true、property_coupling=node', field='solver')
        unsupported = [name for name in ('series_compression','hydraulic_blocks','module_mixed_jacobian')
                       if getattr(project.solver,name)]
        if project.solver.thermal_acceleration != 'none' or project.solver.coupling_acceleration != 'none':
            unsupported.append('acceleration')
        if unsupported:
            raise CompilationError('AIR_OPTIMIZATION_UNSUPPORTED', f'湿空气暂不支持优化选项：{unsupported}', field='solver')
        if project.fluid.composition or any(_fluid_identity(entry.fluid) != _fluid_identity(project.fluid)
                                            for entry in project.circuit_fluids):
            raise CompilationError('MOIST_AIR_FLUID_REQUIRED','湿空气只允许相同 Air/gas 回路，含湿量不能写入组分')
    elif project.solver.moist_air_options is not None:
        raise CompilationError('AIR_SOLVER_OPTIONS', '关闭湿空气模式时 moist_air_options 必须为空', field='solver.moist_air_options')
    # Built-in state models and the solver model each one belongs to.
    state_models = {'open_tank': 'tank', 'closed_volume': 'closed_volume'}
    service = fluid_service(project)
    for inst in project.instances:
        definition = modules[inst.module_id]
        state_ok = state_models.get(definition.state_model) == definition.solver_model if definition.state_model else \
            definition.solver_model != 'tank'
        if definition.runtime != 'python' and (definition.solver_model not in supported or not state_ok):
            raise CompilationError('MODEL_NOT_SUPPORTED', f'{inst.id} 的模型 {definition.state_model or definition.solver_model} 尚未实现；不能生成替代计算结果', inst.id)
        if definition.solver_model in ('cooling_coil', 'humidifier') and not moist:
            raise CompilationError('MOIST_AIR_REQUIRED', f'{inst.id} 的 {definition.solver_model} 需要 SolverOptions.moist_air=True',
                                   inst.id)
        if moist and definition.runtime != 'python' and definition.solver_model not in moist_models:
            raise CompilationError('MOIST_AIR_MODEL_UNSUPPORTED', f'{inst.id} 的模型 {definition.solver_model} 不适用于湿空气网络',
                                   inst.id)
        if definition.runtime == 'python':
            if moist and (definition.sdk is None or 'air.pass_through.v1' not in definition.sdk.capabilities):
                raise CompilationError('MODULE_AIR_CAPABILITY_REQUIRED',f'{inst.id} 需升级为声明湿空气透传能力的模块版本',inst.id)
            from .module_contracts import ModuleCompatibilityError, check_module_compatibility
            try:
                check_module_compatibility(definition)
            except ModuleCompatibilityError as error:
                raise CompilationError(error.code, str(error), inst.id, error.field) from error
            if not definition.entrypoint:
                raise CompilationError('MODULE_ENTRYPOINT_MISSING', f'{inst.id} 的 Python 模块没有入口', inst.id)
            source = definition.source.get('runtime', '') if definition.source else ''
            if isinstance(source, list):
                source = '\n'.join(source)
            if not source.strip():
                raise CompilationError('MODULE_SOURCE_MISSING', f'{inst.id} 的 Python 模块没有 runtime 源码', inst.id)
            if definition.content_hash:
                import hashlib
                digest = hashlib.sha256(source.encode('utf-8')).hexdigest()
                if digest != definition.content_hash:
                    raise CompilationError('MODULE_HASH_MISMATCH', f'{inst.id} 的模块内容哈希与源码不一致', inst.id)
            if definition.definition_hash:
                from .runtime import module_definition_hash
                if module_definition_hash(definition) != definition.definition_hash:
                    raise CompilationError('MODULE_DEFINITION_HASH_MISMATCH', f'{inst.id} 的模块契约或源码与保存版本不一致', inst.id)
        parameters[inst.id] = validated_parameters(inst, definition)
        if not definition.ports:
            raise CompilationError('PORTS_MISSING', f'{inst.id} 没有端口', inst.id)
        if definition.solver_model == 'pressure_source' and len(definition.ports) != 1:
            raise CompilationError('BOUNDARY_PORT_COUNT', '压力边界必须只有一个端口', inst.id)
        if definition.thermal_model and not project.solver.thermal:
            diagnostics.append(Diagnostic(code='THERMAL_NOT_SOLVED', message=f'{inst.id} 仅计算两侧水力阻力，不计算热量交换和出口温度', severity='warning', instance_id=inst.id))
        for port in definition.ports:
            if port.domain != Domain.fluid:
                raise CompilationError('DOMAIN_NOT_SOLVABLE', f'{inst.id}:{port.id} 不是流体端口', inst.id, port.id)
            port_keys.append(f'{inst.id}:{port.id}')
    dsu = DisjointSet(port_keys)
    used = set()
    for connection in project.connections:
        source = f'{connection.source.instance_id}:{connection.source.port_id}'
        target = f'{connection.target.instance_id}:{connection.target.port_id}'
        if source == target or source in used or target in used:
            raise CompilationError('PORT_REUSED', f'连接端口重复使用：{source} 或 {target}')
        used.update((source, target))
        dsu.union(source, target)
    for inst in project.instances:
        definition = modules[inst.module_id]
        if definition.solver_model in ('junction', 'tank', 'closed_volume'):
            for p in definition.ports[1:]:
                dsu.union(f'{inst.id}:{definition.ports[0].id}', f'{inst.id}:{p.id}')
        for port in definition.ports:
            if port.required and f'{inst.id}:{port.id}' not in used:
                raise CompilationError('PORT_UNCONNECTED', f'必需端口未连接：{inst.id} · {port.label}', inst.id, port.id)
    roots = sorted({dsu.find(key) for key in port_keys})
    index = {root: n for n, root in enumerate(roots)}
    nodes = {key: index[dsu.find(key)] for key in port_keys}
    node_circuit, circuit_fluids, circuit_sources, mixed = assign_circuits(project, modules, nodes, len(roots))

    def service_of(instance_id):
        """Service of the circuit an instance's first port belongs to (a built-in's ports share one, exchangers aside)."""
        if not mixed:
            return service
        first = modules[instances[instance_id].module_id].ports[0].id
        return fluid_service(project, circuit_fluids[node_circuit[nodes[f'{instance_id}:{first}']]])

    for inst in project.instances:
        if modules[inst.module_id].runtime == 'builtin':
            check_fluid_conditions(inst.id, parameters[inst.id], modules[inst.module_id].solver_model, service_of(inst.id),
                                   project.solver.thermal)
            if modules[inst.module_id].solver_model == 'duct':
                width, height = parameters[inst.id]['duct_width_m'], parameters[inst.id]['duct_height_m']
                ratio = max(width, height) / min(width, height)
                if ratio > 8.:
                    diagnostics.append(Diagnostic(code='DUCT_ASPECT_RATIO', severity='warning', instance_id=inst.id,
                        message=f'{inst.id} 断面宽高比 {ratio:.1f} 超过 8；水力直径近似误差增大，建议拆分风管或改用等效直径'))
    branches: list[CompiledBranch] = []
    fixed: dict[int, float] = {}
    fixed_temperatures: dict[int, float] = {}
    fixed_humidities: dict[int, float] = {}
    storage: dict[int, StorageSpec] = {}
    for inst in project.instances:
        definition, params = modules[inst.module_id], parameters[inst.id]
        if definition.solver_model == 'pressure_source':
            node, value = nodes[f'{inst.id}:{definition.ports[0].id}'], params['pressure_pa']
            if node in storage:
                raise CompilationError('STORAGE_CONFLICT', f'{inst.id} 与水箱 {storage[node].instance_id} 接在同一节点；'
                                       '水箱本身就是压力参考，不能再接压力边界', inst.id)
            if node in fixed and not math.isclose(fixed[node], value, rel_tol=0, abs_tol=1e-6):
                raise CompilationError('BOUNDARY_CONFLICT', f'{inst.id} 与同节点压力边界冲突', inst.id)
            temperature = float(params.get('temperature_k', 293.15))
            if (project.solver.thermal and node in fixed_temperatures
                    and not math.isclose(fixed_temperatures[node], temperature, rel_tol=0, abs_tol=1e-9)):
                raise CompilationError('BOUNDARY_TEMPERATURE_CONFLICT', f'{inst.id} 与同节点压力边界的温度不同', inst.id,
                                       'temperature_k')
            fixed[node] = value
            fixed_temperatures.setdefault(node, temperature)
            if moist:
                humidity = float(params.get('humidity_ratio_kg_kg', 0.0) or 0.0)
                if humidity < 0.0 or humidity > 0.05:
                    raise CompilationError('PARAMETER_RANGE', f'{inst.id}.humidity_ratio_kg_kg 超出 0–0.05 kg/kg_da',
                                           inst.id, 'humidity_ratio_kg_kg')
                from .moist_air import saturation_humidity_ratio
                from .moist_air import MoistAirService, AirPropertyError
                try:
                    MoistAirService().state_ptw(value, temperature, humidity)
                except AirPropertyError as error:
                    raise CompilationError(error.code, str(error), inst.id) from error
                if humidity > saturation_humidity_ratio(temperature, value):
                    raise CompilationError('AIR_HUMIDITY_SUPERSATURATED',
                                           f'{inst.id} 的边界含湿量 {humidity:.5g} 超过该温度压力下的饱和含湿量', inst.id,
                                           'humidity_ratio_kg_kg')
                if node in fixed_humidities and not math.isclose(fixed_humidities[node], humidity, rel_tol=0, abs_tol=1e-9):
                    raise CompilationError('BOUNDARY_HUMIDITY_CONFLICT', f'{inst.id} 与同节点边界的含湿量不同', inst.id,
                                           'humidity_ratio_kg_kg')
                fixed_humidities.setdefault(node, humidity)
            continue
        if definition.solver_model == 'tank':
            node = nodes[f'{inst.id}:{definition.ports[0].id}']
            if node in storage:
                raise CompilationError('STORAGE_CONFLICT', f'{inst.id} 与水箱 {storage[node].instance_id} 直接相连；'
                                       '两个水箱之间需要阀门或管道', inst.id)
            if node in fixed:
                raise CompilationError('STORAGE_CONFLICT', f'{inst.id} 与压力边界接在同一节点；水箱本身就是压力参考，'
                                       '不能再接压力边界', inst.id)
            spec = tank_initial_state(inst.id, params, node, service_of(inst.id))
            storage[node] = spec
            fixed[node], fixed_temperatures[node] = spec.initial_pressure_pa, spec.initial_temperature_k
            continue
        if definition.solver_model in ('junction', 'closed_volume'):
            continue
        channels = [c for c in definition.channels if c.enabled]
        covered = {p for c in channels for p in (c.input_port, c.output_port)}
        if covered != {p.id for p in definition.ports}:
            raise CompilationError('CHANNEL_COVERAGE', f'{inst.id} 存在未绑定到有效通路的端口', inst.id)
        for ch in channels:
            expected = 'resistance' if definition.solver_model in ('heat_exchanger', 'heater', 'cooling_coil', 'humidifier') \
                else definition.solver_model
            relation = 'pump_curve' if expected == 'pump_curve' else 'resistance'
            if definition.runtime != 'python' and (ch.solver_model != expected or ch.relation != relation):
                raise CompilationError('CHANNEL_MODEL_INVALID', f'{inst.id}.{ch.id} 未注册的通路关系 {ch.solver_model}/{ch.relation}', inst.id, ch.id)
            start, end = nodes[f'{inst.id}:{ch.input_port}'], nodes[f'{inst.id}:{ch.output_port}']
            if start == end:
                raise CompilationError('BRANCH_SHORTED', f'{inst.id}.{ch.id} 的两端被直接短接', inst.id)
            branches.append(CompiledBranch(inst.id, ch.id, ch.solver_model, ch.input_port, ch.output_port, start, end,
                                            definition.runtime == 'builtin' and ch.solver_model == 'valve' and params['opening_ratio'] == 0))
    if not branches:
        raise CompilationError('NO_BRANCHES', '网络没有可计算支路')
    trapped = _compile_trapped(project, modules, parameters, nodes, branches, fixed, fixed_temperatures, storage,
                               service_of, diagnostics)
    components = DisjointSet(range(len(roots)))
    for branch in branches:
        if not branch.closed:
            components.union(branch.start_node, branch.end_node)
    referenced = {components.find(n) for n in fixed}
    for node in range(len(roots)):
        if components.find(node) not in referenced:
            raise CompilationError('PRESSURE_REFERENCE_MISSING', f'子网络 {roots[node]} 缺少压力边界（关闭阀门也可能隔离回路）')
    validate_controllers(project, modules, instances)
    from .control import validate_scripts
    validate_scripts(project, modules, instances)
    if mixed:
        names = '、'.join(dict.fromkeys(f.fluid for f in circuit_fluids))
        diagnostics.append(Diagnostic(code='MULTIPLE_FLUIDS', severity='info',
                                      message=f'项目包含 {len(circuit_fluids)} 个回路，回路工质：{names}（项目工质 '
                                      f'{project.fluid.fluid}）；各回路物性独立计算'))
    network = CompiledNetwork(project, modules, instances, parameters, nodes, roots, branches, fixed, diagnostics,
                           fixed_temperatures, [components.find(n) for n in range(len(roots))], storage,
                           node_circuit, circuit_fluids, circuit_sources, mixed, trapped=trapped,
                           fixed_humidities=fixed_humidities)
    network.composite_maps = composite_maps or getattr(project,'_composite_maps',{})
    from .module_scope import check_scope_configuration
    for key, instance in instances.items():
        definition = modules[instance.module_id]
        fluid, port_fluids = instance_fluids(network, key)
        try:
            for config in [fluid, *port_fluids.values()]:
                check_scope_configuration(definition, config)
        except ValueError as error:
            raise CompilationError('MODULE_SCOPE_UNSUPPORTED', str(error), key) from error
    return network


def runtime_parameter(instance, definition, parameter_id):
    """The ParameterSpec a run may write; shared by PID binding and the `set` command."""
    spec = next((p for p in definition.parameters if p.id == parameter_id), None)
    if spec is None or not spec.writable or not spec.runtime:
        raise CompilationError('PARAMETER_NOT_RUNTIME', f'{instance.id}.{parameter_id} 不允许运行时修改', instance.id, parameter_id)
    return spec


def validate_controllers(project: Project, modules, instances) -> None:
    """Static PID checks; a declared measurement that is absent at t=0 still fails the run."""
    for c in project.controllers:
        target = instances[c.instance_id]
        spec = runtime_parameter(target, modules[target.module_id], c.parameter_id)
        if spec.value_type != 'number':
            raise CompilationError('PID_TARGET_INVALID', f'PID {c.id} 的目标 {c.instance_id}.{c.parameter_id} 不是数值参数',
                                   c.instance_id, c.parameter_id)
        if spec.minimum is not None and c.minimum < spec.minimum or spec.maximum is not None and c.maximum > spec.maximum:
            raise CompilationError('PID_TARGET_INVALID', f'PID {c.id} 的输出范围 [{c.minimum:g}, {c.maximum:g}] 超出目标参数范围 '
                                   f'[{spec.minimum}, {spec.maximum}]', c.instance_id, c.parameter_id)
        instance_id, _, variable_id = c.measurement.partition('.')
        source = instances.get(instance_id)
        variable = source and next((v for v in modules[source.module_id].variables if v.id == variable_id), None)
        if not variable or not variable.sampleable or variable.source == 'parameter':
            raise CompilationError('PID_MEASUREMENT_UNKNOWN', f'PID {c.id} 的反馈变量 {c.measurement} 不是可采样的设备变量',
                                   instance_id if source else None, 'measurement')


def validate_scenarios(project: Project, modules: dict[str, ModuleDefinition]) -> list[Diagnostic]:
    # 复用运行链路的同一套参数校验(validated_parameters): 运行时会先
    # apply_scenario 把工况覆盖合并进实例参数,再走 compile_project。校验端
    # 若只跑 compile_project,工况里写错的实例 id 或越界数值就会被静默放过。
    diagnostics: list[Diagnostic] = []
    instances = {i.id: i for i in project.instances}
    for scenario in project.scenarios:
        for instance_id, overrides in scenario.overrides.items():
            instance = instances.get(instance_id)
            if instance is None:
                diagnostics.append(Diagnostic(code='SCENARIO_INSTANCE_MISSING', severity='error',
                                               message=f'工况 {scenario.id} 引用不存在的实例:{instance_id}',
                                               instance_id=instance_id))
                continue
            definition = modules.get(instance.module_id)
            if definition is None:
                continue
            merged = instance.model_copy(update={'parameters': {**instance.parameters, **overrides}})
            try:
                validated_parameters(merged, definition)
            except CompilationError as error:
                error.diagnostic.message = f'工况 {scenario.id}:{error.diagnostic.message}'
                diagnostics.append(error.diagnostic)
        if scenario.events is not None:
            # The schedule is resolved against the scenario's merged parameters, as a run would.
            candidate = project.model_copy(deep=True)
            candidate.events = list(scenario.events)
            targets = {i.id: i for i in candidate.instances}
            for instance_id, overrides in scenario.overrides.items():
                if instance_id in targets:
                    targets[instance_id].parameters.update(overrides)
            try:
                compile_project(candidate)
            except CompilationError as error:
                if error.diagnostic.code.startswith('SCHEDULE_'):
                    error.diagnostic.message = f'工况 {scenario.id}:{error.diagnostic.message}'
                    diagnostics.append(error.diagnostic)
    return diagnostics


def validate_project(project: Project) -> list[Diagnostic]:
    return validate_project_details(project)[0]


def circuit_info(network: CompiledNetwork) -> list[dict]:
    """Fluid circuits of a compiled network (one entry for a single-fluid project)."""
    if getattr(network, 'execution_domain', None) == 'coupled':
        from .refrigeration.coupling import coupled_circuits
        return coupled_circuits(network)
    if getattr(network, 'execution_domain', None) in ('thermal', 'cold_store'):
        return []
    if getattr(network, 'execution_domain', None) == 'refrigeration':
        from .refrigeration.station import station_circuits
        return station_circuits(network)
    count = len(network.circuit_fluids) or 1
    ports: list[list[str]] = [[] for _ in range(count)]
    for key, node in network.port_nodes.items():
        ports[network.node_circuit[node] if network.node_circuit else 0].append(key)
    return [{'id': i, 'fluid': network.circuit_fluids[i] if network.circuit_fluids else network.project.fluid,
             'source': network.circuit_sources[i] if network.circuit_sources else 'project', 'ports': sorted(ports[i])}
            for i in range(count)]


def validate_project_details(project: Project) -> tuple[list[Diagnostic], list[dict]]:
    """Diagnostics plus the fluid circuits (empty when the project does not compile)."""
    try:
        network = compile_project(project)
    except CompilationError as error:
        return [error.diagnostic], []
    except ValueError as error:
        return [Diagnostic(code='PROJECT_INVALID', message=str(error))], []
    return network.diagnostics + validate_scenarios(project, network.modules), circuit_info(network)
