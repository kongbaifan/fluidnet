"""困液定容压力第一阶段原型（I0–I4）：单一均匀液体的刚性封闭容积。

范围（硬约束，见 docs/NUMERICS_OPTIMIZATION_PLAN.md §13.1）：

- 仅 HEOS 纯水、单相液体；几何体积 V 固定、质量 M 固定，积分状态是流体总内能 U。
  p/T 一律由 ``property_service.state_du(M/V, U/M)`` 得到（不另写 EOS，也不用定压管道
  “等效质量×焓变化”冒充定容守恒）。
- 可选集总管壁与流体同温：总储能 ``E = U + C_wall·(T − T_ref)``，``T_ref`` 取编译期初温，
  以热量收支推进；刚性封闭体不做边界体积功。
- 唯一的外部能量交换是 ``heat_input_w`` 与 ``heat_loss_ua_w_k·(T − T_ambient)``。
- 不支持 INCOMP、气垫、两相、弹性管壁、泄漏、水锤、多容积串联与完整开闭周期（I5–I9）。
  本模块只提供“单容积封闭原型”，不能对外声称“任意阀门隔离网络已支持”。

本文件只放纯函数与状态数据类（隐式 Euler 的标量内能推进、能量账本、诊断码），
不依赖 compiler/solver/simulation，便于单独验证。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .models import Diagnostic, FluidState
from .properties import PropertyError

# 诊断码（编译期/运行期共用）。前缀 TRAPPED_ 让 simulation 识别“困液专属停止”，
# 与普通水力/热力不收敛分开处理。
TRAPPED_FLUID_UNSUPPORTED = 'TRAPPED_FLUID_UNSUPPORTED'
TRAPPED_VOLUME_REQUIRED = 'TRAPPED_VOLUME_REQUIRED'
TRAPPED_INITIAL_STATE_INVALID = 'TRAPPED_INITIAL_STATE_INVALID'
TRAPPED_INITIAL_STATE_INCONSISTENT = 'TRAPPED_INITIAL_STATE_INCONSISTENT'
TRAPPED_STATE_RANGE = 'TRAPPED_STATE_RANGE'
TRAPPED_PRESSURE_LIMIT = 'TRAPPED_PRESSURE_LIMIT'
TRAPPED_PHASE_UNSUPPORTED = 'TRAPPED_PHASE_UNSUPPORTED'
TRAPPED_ENERGY_STEP = 'TRAPPED_ENERGY_STEP'
TRAPPED_OPEN_UNSUPPORTED = 'TRAPPED_OPEN_UNSUPPORTED'
TRAPPED_BOUNDARY_FLOW = 'TRAPPED_BOUNDARY_FLOW'


class TrappedError(ValueError):
    """带稳定诊断码的困液状态错误；compiler 把它转成 CompilationError，simulation 转成停止事件。"""

    def __init__(self, code: str, message: str, instance_id: str | None = None, field: str | None = None):
        self.code, self.instance_id, self.field = code, instance_id, field
        super().__init__(message)


@dataclass
class TrappedSpec:
    """编译期确定的封闭容积配置与初态（节点、V、管壁、初温初压、边界热量参数）。"""

    instance_id: str
    node: int
    volume_m3: float
    wall_heat_capacity_j_k: float
    # 管壁能量零点；等于初温，因此初始管壁储能恒为 0。
    reference_temperature_k: float
    heat_input_w: float
    heat_loss_ua_w_k: float
    ambient_temperature_k: float
    initial_mass_kg: float
    initial_internal_energy_j: float
    initial_pressure_pa: float
    initial_temperature_k: float


@dataclass(frozen=True)
class TrappedState:
    """封闭容积的积分状态：质量 M [kg] 与流体总内能 U [J]（V 由 TrappedSpec 固定）。"""

    mass_kg: float
    internal_energy_j: float


@dataclass(frozen=True)
class TrappedLedger:
    """能量账本：初始总储能、累计热量收支与步数。"""

    initial_total_energy_j: float
    cumulative_heat_j: float = 0.0
    cumulative_absolute_heat_j: float = 0.0
    steps: int = 0
    # 最近一次 accepted 子步的热流（W，正为加入），只用于帧输出，不参与积分。
    last_heat_flow_w: float = 0.0


@dataclass(frozen=True)
class TrappedStep:
    """一次隐式 Euler 推进的结果（不提交，由调用方决定 accepted/trial）。"""

    state: TrappedState
    fluid: FluidState
    heat_flow_w: float
    iterations: int
    residual_j: float


def _require_liquid(spec: TrappedSpec, fluid: FluidState, density: float, specific_internal_energy: float) -> None:
    if 'liquid' not in fluid.phase:
        raise TrappedError(
            TRAPPED_PHASE_UNSUPPORTED,
            f'{spec.instance_id} 的困液状态 ρ={density:.6g} kg/m³、u={specific_internal_energy:.6g} J/kg '
            f'为 {fluid.phase}（p={fluid.pressure_pa:.6g} Pa，T={fluid.temperature_k:.4f} K）；'
            'I0–I4 只接受单相液体，不把两相/气态状态当作保压成功',
            spec.instance_id)


def _require_limits(service, spec: TrappedSpec, fluid: FluidState) -> None:
    limits = service.limits()
    t_min, t_max, p_max = limits['t_min_k'], limits['t_max_k'], limits['p_max_pa']
    if not (t_min - 1e-9 <= fluid.temperature_k <= t_max + 1e-9):
        raise TrappedError(
            TRAPPED_STATE_RANGE,
            f'{spec.instance_id} 的困液状态 T={fluid.temperature_k:.4f} K 超出 {service.fluid} 的适用范围 '
            f'{t_min:.2f}…{t_max:.2f} K；不把外推状态当作可计算状态', spec.instance_id)
    if fluid.pressure_pa <= 0:
        raise TrappedError(TRAPPED_STATE_RANGE,
                           f'{spec.instance_id} 的困液压力 p={fluid.pressure_pa:.6g} Pa 非正；拒绝该状态', spec.instance_id)
    if p_max is not None and fluid.pressure_pa > p_max:
        raise TrappedError(
            TRAPPED_PRESSURE_LIMIT,
            f'{spec.instance_id} 的困液压力 p={fluid.pressure_pa:.6g} Pa 超过 {service.fluid} 的最高压力 '
            f'{p_max:g} Pa；拒绝越界状态（不夹断压力）', spec.instance_id)


def state_of(service, spec: TrappedSpec, state: TrappedState) -> FluidState:
    """由 (M/V, U/M) 求 p/T；两相、越界或物性失败都抛 TrappedError，不返回替代状态。"""
    if not (math.isfinite(state.mass_kg) and state.mass_kg > 0):
        raise TrappedError(TRAPPED_STATE_RANGE, f'{spec.instance_id} 的困液质量 {state.mass_kg!r} 非正', spec.instance_id)
    density = state.mass_kg / spec.volume_m3
    specific = state.internal_energy_j / state.mass_kg
    try:
        fluid = service.state_du(density, specific)
    except PropertyError as error:
        raise TrappedError(error.code, f'{spec.instance_id} 的困液状态 ρ={density:.6g} kg/m³、'
                                       f'u={specific:.6g} J/kg 物性计算失败：{error}', spec.instance_id) from error
    _require_liquid(spec, fluid, density, specific)
    _require_limits(service, spec, fluid)
    return fluid


def total_energy_j(spec: TrappedSpec, state: TrappedState, fluid: FluidState) -> float:
    """总储能 E = U + C_wall·(T − T_ref)；刚性体无边界体积功项。"""
    return state.internal_energy_j + spec.wall_heat_capacity_j_k * (fluid.temperature_k - spec.reference_temperature_k)


def boundary(service, spec: TrappedSpec, state: TrappedState) -> tuple[float, float]:
    """动态子步的水力/热力边界：由 accepted 状态算出的 (p, T)。"""
    fluid = state_of(service, spec, state)
    return fluid.pressure_pa, fluid.temperature_k


def _initial_parameters(instance_id: str, params: dict, service) -> tuple[float, ...]:
    """从模块参数取 V/C_wall/T0/p0/Q/UA/T_amb，并对范围与工质能力做明确拒绝。"""
    from .properties import _parse_fluid

    try:
        backend, name, fractions, _ = _parse_fluid(service.config)
    except PropertyError as error:
        raise TrappedError(error.code, f'{instance_id} 的工质 {service.fluid} 无法解析：{error}', instance_id) from error
    if backend != 'HEOS' or name.lower() != 'water' or fractions:
        raise TrappedError(
            TRAPPED_FLUID_UNSUPPORTED,
            f'{instance_id}：困液定容原型只支持 HEOS 纯水，当前工质为 {service.fluid}（{backend}）；'
            'INCOMP/IF97/混合物与其它流体尚未通过压缩性/相态能力检查，不开放', instance_id, 'fluid')
    volume = float(params['volume_m3'])
    if not math.isfinite(volume) or volume <= 0:
        raise TrappedError(
            TRAPPED_VOLUME_REQUIRED,
            f'{instance_id}.volume_m3 = {params["volume_m3"]!r} 无效：定容原型必须显式给出有效液体容积 '
            'V > 0（未建模阀腔不能默认按零容积通过）', instance_id, 'volume_m3')
    wall = float(params['wall_heat_capacity_j_k'])
    if not math.isfinite(wall) or wall < 0:
        raise TrappedError(TRAPPED_INITIAL_STATE_INVALID, f'{instance_id}.wall_heat_capacity_j_k 必须是非负有限数',
                           instance_id, 'wall_heat_capacity_j_k')
    temperature = float(params['initial_temperature_k'])
    pressure = float(params['initial_pressure_pa'])
    heat_input = float(params['heat_input_w'])
    heat_loss = float(params['heat_loss_ua_w_k'])
    ambient = float(params['ambient_temperature_k'])
    for key, value in (('heat_input_w', heat_input), ('heat_loss_ua_w_k', heat_loss), ('ambient_temperature_k', ambient)):
        if not math.isfinite(value):
            raise TrappedError(TRAPPED_INITIAL_STATE_INVALID, f'{instance_id}.{key} 必须是有限数', instance_id, key)
    if heat_loss < 0 or ambient <= 0:
        raise TrappedError(TRAPPED_INITIAL_STATE_INVALID,
                           f'{instance_id} 的散热参数必须非负、环境温度必须为正（UA={heat_loss:g} W/K，T_amb={ambient:g} K）',
                           instance_id, 'heat_loss_ua_w_k')
    limits = service.limits()
    t_min, t_max, p_max = limits['t_min_k'], limits['t_max_k'], limits['p_max_pa']
    if not (t_min - 1e-9 <= temperature <= t_max + 1e-9):
        raise TrappedError(TRAPPED_INITIAL_STATE_INVALID,
                           f'{instance_id}.initial_temperature_k = {temperature:.4f} K 超出 {service.fluid} 的'
                           f'适用范围 {t_min:.2f}…{t_max:.2f} K', instance_id, 'initial_temperature_k')
    if not (t_min - 1e-9 <= ambient <= t_max + 1e-9):
        raise TrappedError(TRAPPED_INITIAL_STATE_INVALID,
                           f'{instance_id}.ambient_temperature_k = {ambient:.4f} K 超出 {service.fluid} 的'
                           f'适用范围 {t_min:.2f}…{t_max:.2f} K', instance_id, 'ambient_temperature_k')
    if not math.isfinite(pressure) or pressure <= 0 or (p_max is not None and pressure > p_max):
        raise TrappedError(TRAPPED_INITIAL_STATE_INVALID,
                           f'{instance_id}.initial_pressure_pa = {pressure!r} 无效：必须为 (0, {p_max}] Pa 内的正数',
                           instance_id, 'initial_pressure_pa')
    return volume, wall, temperature, pressure, heat_input, heat_loss, ambient


def build_spec(instance_id: str, node: int, params: dict, service) -> tuple[TrappedSpec, TrappedState]:
    """编译期构造封闭容积配置与初态；任何不支持/越界配置都以稳定诊断码拒绝。"""
    volume, wall, temperature, pressure, heat_input, heat_loss, ambient = _initial_parameters(
        instance_id, params, service)
    try:
        start = service.state_pt(pressure, temperature)
    except PropertyError as error:
        raise TrappedError(error.code, f'{instance_id} 的初态（{pressure:g} Pa，{temperature - 273.15:.2f} °C）：'
                                       f'{error}', instance_id, 'initial_temperature_k') from error
    if 'liquid' not in start.phase:
        raise TrappedError(
            TRAPPED_PHASE_UNSUPPORTED,
            f'{instance_id} 的初态在 {pressure:g} Pa、{temperature - 273.15:.2f} °C 下为 {start.phase}；'
            '定容原型只接受单相液体初态（气垫/两相不在 I0–I4 范围）', instance_id, 'initial_temperature_k')
    mass = start.density_kg_m3 * volume
    if start.internal_energy_j_kg is None:
        raise TrappedError(TRAPPED_INITIAL_STATE_INVALID, f'{instance_id} 的初态缺少比内能', instance_id)
    spec = TrappedSpec(
        instance_id=instance_id, node=node, volume_m3=volume, wall_heat_capacity_j_k=wall,
        reference_temperature_k=temperature, heat_input_w=heat_input, heat_loss_ua_w_k=heat_loss,
        ambient_temperature_k=ambient, initial_mass_kg=mass,
        initial_internal_energy_j=mass * float(start.internal_energy_j_kg),
        initial_pressure_pa=pressure, initial_temperature_k=temperature)
    return spec, initial_state(service, spec)


def initial_state(service, spec: TrappedSpec) -> TrappedState:
    """初态的 DU 往返检查：state_du(M/V, U/M) 必须复现给定 p/T/ρ（I1 的物性闭合证据）。"""
    state = TrappedState(spec.initial_mass_kg, spec.initial_internal_energy_j)
    density = spec.initial_mass_kg / spec.volume_m3
    specific = spec.initial_internal_energy_j / spec.initial_mass_kg
    try:
        fluid = service.state_du(density, specific)
    except PropertyError as error:
        raise TrappedError(error.code, f'{spec.instance_id} 的初态无法由 (ρ, u) 重建：{error}',
                           spec.instance_id) from error
    dp = abs(fluid.pressure_pa - spec.initial_pressure_pa)
    dt = abs(fluid.temperature_k - spec.initial_temperature_k)
    drho = abs(fluid.density_kg_m3 - density) / density
    p_tolerance = max(10.0, 1e-5 * abs(spec.initial_pressure_pa))
    if dp > p_tolerance or dt > 1e-3 or drho > 1e-6:
        raise TrappedError(
            TRAPPED_INITIAL_STATE_INCONSISTENT,
            f'{spec.instance_id} 的初态往返不一致：给定 p={spec.initial_pressure_pa:g} Pa、T={spec.initial_temperature_k:g} K、'
            f'ρ={density:.6f} kg/m³；由 (ρ, u) 重建得 p={fluid.pressure_pa:g} Pa、T={fluid.temperature_k:.6f} K、'
            f'ρ={fluid.density_kg_m3:.6f} kg/m³（差 Δp={dp:.3g} Pa、ΔT={dt:.3g} K、Δρ/ρ={drho:.3g}）',
            spec.instance_id)
    _require_liquid(spec, fluid, density, specific)
    _require_limits(service, spec, fluid)
    return state


def advance(service, spec: TrappedSpec, state: TrappedState, dt_s: float, *,
            heat_input_w: float | None = None, heat_loss_ua_w_k: float | None = None,
            ambient_temperature_k: float | None = None, max_iterations: int = 60) -> TrappedStep:
    """隐式（后向）Euler 推进一个子步：以总储能 E=U+C_wall(T−T_ref) 与热量收支平衡求 U。

    方程 F(U) = E(U) − E_old − Δt·[Q_in − UA·(T(U) − T_amb)] = 0，其中 T(U) 由 state_du 给出。
    对固定 M/V，F 关于 U 单调（dU/dT = M·cv > 0），用带括区的 Newton 求根，失败就明确报错。
    """
    if not (math.isfinite(dt_s) and dt_s > 0):
        raise TrappedError(TRAPPED_ENERGY_STEP, f'{spec.instance_id} 的步长 {dt_s!r} 非正', spec.instance_id)
    qin = spec.heat_input_w if heat_input_w is None else float(heat_input_w)
    ua = spec.heat_loss_ua_w_k if heat_loss_ua_w_k is None else float(heat_loss_ua_w_k)
    ambient = spec.ambient_temperature_k if ambient_temperature_k is None else float(ambient_temperature_k)
    mass = state.mass_kg
    density = mass / spec.volume_m3
    specific_old = state.internal_energy_j / mass
    fluid_old = state_of(service, spec, state)
    energy_old = total_energy_j(spec, state, fluid_old)
    wall, reference = spec.wall_heat_capacity_j_k, spec.reference_temperature_k

    def evaluate(specific: float) -> tuple[float, float, FluidState]:
        """(F [J], dF/dU [1], 状态)；物性失败直接抛 TrappedError。"""
        try:
            fluid = service.state_du(density, specific)
        except PropertyError as error:
            raise TrappedError(error.code, f'{spec.instance_id} 的能量步搜索越出物性范围（ρ={density:.6g} kg/m³、'
                                           f'u={specific:.6g} J/kg）：{error}', spec.instance_id) from error
        temperature = fluid.temperature_k
        energy = mass * specific + wall * (temperature - reference)
        residual = energy - energy_old - dt_s * (qin - ua * (temperature - ambient))
        cv = fluid.cv_j_kg_k
        derivative = 1.0 + (wall + dt_s * ua) / (mass * cv) if cv and cv > 0 else 1.0
        return residual, derivative, fluid

    heat_old = qin - ua * (fluid_old.temperature_k - ambient)
    delta_specific = dt_s * heat_old / mass
    tolerance = max(1e-9, 1e-12 * abs(energy_old))
    if abs(delta_specific) <= tolerance / mass:
        # 绝热且没有净热流：U、M、p、T 全都不变（刚性体没有体积功）。
        return TrappedStep(state, fluid_old, heat_old, 0, 0.0)

    residual_old, _, _ = evaluate(specific_old)
    lo = hi = specific_old
    step = max(abs(delta_specific), max(1e-9 * abs(specific_old), 1e-6))
    if residual_old < 0:
        hi = specific_old + step
        for _ in range(100):
            if evaluate(hi)[0] > 0:
                break
            step *= 2.0
            hi = specific_old + step
        else:
            raise TrappedError(TRAPPED_ENERGY_STEP, f'{spec.instance_id} 的能量步无法括住根（加热方向）', spec.instance_id)
    else:
        lo = specific_old - step
        for _ in range(100):
            if evaluate(lo)[0] < 0:
                break
            step *= 2.0
            lo = specific_old - step
        else:
            raise TrappedError(TRAPPED_ENERGY_STEP, f'{spec.instance_id} 的能量步无法括住根（冷却方向）', spec.instance_id)

    specific = 0.5 * (lo + hi)
    converged, iterations, residual = False, 0, math.inf
    for iterations in range(1, max_iterations + 1):
        residual, derivative, fluid = evaluate(specific)
        if abs(residual) <= tolerance:
            converged = True
            break
        if residual < 0:
            lo = specific
        else:
            hi = specific
        candidate = specific - residual / derivative if derivative > 0 else math.nan
        if not math.isfinite(candidate) or not lo < candidate < hi:
            candidate = 0.5 * (lo + hi)
        if abs(candidate - specific) <= 4.0 * math.ulp(max(1.0, abs(specific))):
            specific = candidate
            residual, _, fluid = evaluate(specific)
            converged = abs(residual) <= max(tolerance, 1e-9 * abs(energy_old))
            break
        specific = candidate
    if not converged:
        raise TrappedError(
            TRAPPED_ENERGY_STEP,
            f'{spec.instance_id} 的能量步在 {max_iterations} 次 Newton 后残差 {residual:.6g} J 仍超过 '
            f'{tolerance:.3g} J；拒绝该子步（不夹断内能/温度）', spec.instance_id)
    fluid = state_of(service, spec, TrappedState(mass, mass * specific))
    heat_flow = qin - ua * (fluid.temperature_k - ambient)
    return TrappedStep(TrappedState(mass, mass * specific), fluid, heat_flow, iterations, residual)


def record_heat(ledger: TrappedLedger, heat_flow_w: float, dt_s: float) -> TrappedLedger:
    """把一次 accepted 子步的热流计入账本（累计热量与累计绝对热量）。"""
    heat = float(heat_flow_w) * float(dt_s)
    return replace(ledger, cumulative_heat_j=ledger.cumulative_heat_j + heat,
                   cumulative_absolute_heat_j=ledger.cumulative_absolute_heat_j + abs(heat),
                   steps=ledger.steps + 1, last_heat_flow_w=float(heat_flow_w))


def energy_residual_j(ledger: TrappedLedger, spec: TrappedSpec, state: TrappedState, fluid: FluidState) -> float:
    """能量账本残差：(E − E₀) − ΣQ·Δt。"""
    return total_energy_j(spec, state, fluid) - ledger.initial_total_energy_j - ledger.cumulative_heat_j


def energy_scale_j(ledger: TrappedLedger, spec: TrappedSpec, state: TrappedState, fluid: FluidState) -> float:
    """能量尺度 E_scale = max(累计绝对热量, |总储能变化|)，按计划 §13 的定义冻结口径。"""
    return max(ledger.cumulative_absolute_heat_j, abs(total_energy_j(spec, state, fluid) - ledger.initial_total_energy_j))


def relative_mass_drift(spec: TrappedSpec, state: TrappedState) -> float:
    """封闭阶段质量相对漂移 (M − M₀)/M₀；封闭容积的 M 不参与积分，应恒为 0。"""
    return (state.mass_kg - spec.initial_mass_kg) / spec.initial_mass_kg


def frame_terms(service, spec: TrappedSpec, state: TrappedState, ledger: TrappedLedger) -> tuple[dict, dict]:
    """`<实例>.state.*` 帧变量与 `trapped_*` 指标（单容积原型的稳定键名）。"""
    fluid = state_of(service, spec, state)
    total = total_energy_j(spec, state, fluid)
    scale = energy_scale_j(ledger, spec, state, fluid)
    residual = energy_residual_j(ledger, spec, state, fluid)
    variables = {
        f'{spec.instance_id}.state.pressure_pa': fluid.pressure_pa,
        f'{spec.instance_id}.state.temperature_k': fluid.temperature_k,
        f'{spec.instance_id}.state.density_kg_m3': fluid.density_kg_m3,
        f'{spec.instance_id}.state.specific_internal_energy_j_kg': state.internal_energy_j / state.mass_kg,
        f'{spec.instance_id}.state.internal_energy_j': state.internal_energy_j,
        f'{spec.instance_id}.state.mass_kg': state.mass_kg,
        f'{spec.instance_id}.state.volume_m3': spec.volume_m3,
        f'{spec.instance_id}.state.total_energy_j': total,
        f'{spec.instance_id}.state.wall_energy_j': wall_energy_j(spec, fluid),
        f'{spec.instance_id}.state.cumulative_heat_j': ledger.cumulative_heat_j,
        f'{spec.instance_id}.state.heat_flow_w': ledger.last_heat_flow_w,
        f'{spec.instance_id}.state.relative_mass_drift': relative_mass_drift(spec, state),
    }
    metrics = {
        'trapped_mass_kg': state.mass_kg,
        'trapped_volume_m3': spec.volume_m3,
        'trapped_pressure_pa': fluid.pressure_pa,
        'trapped_temperature_k': fluid.temperature_k,
        'trapped_density_kg_m3': fluid.density_kg_m3,
        'trapped_internal_energy_j': state.internal_energy_j,
        'trapped_total_energy_j': total,
        'trapped_cumulative_heat_j': ledger.cumulative_heat_j,
        'trapped_energy_scale_j': scale,
        'trapped_energy_residual_j': residual,
        'trapped_relative_mass_drift': relative_mass_drift(spec, state),
    }
    return variables, metrics


def wall_energy_j(spec: TrappedSpec, fluid: FluidState) -> float:
    """管壁储能 C_wall·(T − T_ref)；无管壁时恒为 0，不和管道热容重复计能。"""
    return spec.wall_heat_capacity_j_k * (fluid.temperature_k - spec.reference_temperature_k)


def ledger_diagnostic(ledger: TrappedLedger, spec: TrappedSpec, state: TrappedState, fluid: FluidState) -> Diagnostic | None:
    """账本超门限时给出 error 诊断（门限与计划 §13 的 I 数值门一致）。"""
    residual = energy_residual_j(ledger, spec, state, fluid)
    scale = energy_scale_j(ledger, spec, state, fluid)
    limit = max(1.0, 1e-6 * scale)
    drift = abs(relative_mass_drift(spec, state))
    if abs(residual) <= limit and drift <= 1e-10:
        return None
    return Diagnostic(
        code='TRAPPED_LEDGER_VIOLATION', severity='error', instance_id=spec.instance_id,
        message=f'{spec.instance_id} 困液账本超门限：能量残差 {residual:.6g} J（限 {limit:.6g} J，E_scale={scale:.6g} J），'
                f'质量相对漂移 {drift:.3g}（限 1e-10）；不把该帧当作守恒通过')


def initial_states(network) -> dict[int, TrappedState]:
    """动态会话使用的初态（节点 -> 状态）；封闭时刻的 M/U 即 accepted 初态。"""
    return {node: TrappedState(spec.initial_mass_kg, spec.initial_internal_energy_j)
            for node, spec in getattr(network, 'trapped', {}).items()}


def initial_ledgers(network, states: dict[int, TrappedState], service_for) -> dict[int, TrappedLedger]:
    ledgers = {}
    for node, spec in getattr(network, 'trapped', {}).items():
        fluid = state_of(service_for(node), spec, states[node])
        ledgers[node] = TrappedLedger(initial_total_energy_j=total_energy_j(spec, states[node], fluid))
    return ledgers


def step_network(network, states: dict[int, TrappedState], ledgers: dict[int, TrappedLedger],
                 flows, dt_s: float, service_for) -> tuple[dict[int, TrappedState], dict[int, TrappedLedger]]:
    """动态子步：校验封闭不变量（无开阀/无边界质量流），推进 M/U 并累计账本。"""
    new_states, new_ledgers = {}, {}
    branch_flows = list(flows)
    for node, spec in network.trapped.items():
        for branch, flow in zip(network.branches, branch_flows):
            if node not in (branch.start_node, branch.end_node):
                continue
            if not branch.closed:
                raise TrappedError(
                    TRAPPED_OPEN_UNSUPPORTED,
                    f'{spec.instance_id} 的相邻支路 {branch.instance_id} 处于打开状态；I0–I4 的封闭容积只允许'
                    '两端阀门全关，完整开闭周期（I5–I9）未实现', spec.instance_id)
            if abs(float(flow)) > 1e-12:
                raise TrappedError(
                    TRAPPED_BOUNDARY_FLOW,
                    f'{spec.instance_id} 的关闭支路 {branch.instance_id} 出现 {float(flow):.3g} kg/s 的质量流；'
                    '封闭定容体不允许边界质量交换', spec.instance_id)
        step = advance(service_for(node), spec, states[node], dt_s)
        new_states[node] = step.state
        new_ledgers[node] = record_heat(ledgers[node], step.heat_flow_w, dt_s)
    return new_states, new_ledgers


def open_rejection_message(service, spec: TrappedSpec, state: TrappedState, target: str) -> str:
    """开阀请求在生效前被拒绝时给出的释放账本（只报告，不写入相邻节点）。"""
    fluid = state_of(service, spec, state)
    return (
        f'{spec.instance_id} 为封闭定容原型，当前 M={state.mass_kg:.9g} kg、U={state.internal_energy_j:.9g} J、'
        f'p={fluid.pressure_pa:.9g} Pa、T={fluid.temperature_k:.6g} K（V={spec.volume_m3:g} m³）；'
        f'打开 {target} 会把库存释放到相邻节点，完整开闭周期（I5–I9）未实现，请求在生效前拒绝。'
        f'释放账本（仅报告）：质量 {state.mass_kg:.9g} kg、内能 {state.internal_energy_j:.9g} J、'
        f'总储能 {total_energy_j(spec, state, fluid):.9g} J、管壁储能 {wall_energy_j(spec, fluid):.9g} J')
