"""止回阀（check valve）V0–V2 冻结语义的独立参考与纯函数关系。

本文件是模块行为之外的第二条、**不经过求解器**的参考路径：

* 解析 Δp–q 曲线：给定 Kv、正向开启压差 ``p_crack``、开度与密度，直接算出流量，
  供 ``tests/test_check_valve_numerics.py`` 对照真实 ``solve_network`` 的实测曲线；
* 开关判据、迟滞状态机、互补残差：求解器将来若要实现外层活动集，直接复用这些纯函数；
* 方案 (a) 光滑二极管的对照曲线与“有界泄漏”上界：V1 二选一证据的一部分。

权威语义见 ``docs/MODULES_P0.md`` §5.1–§5.3；冻结的阀门方程与 ``solver.py``
``branch_drop`` 的 ``valve`` 分支一致（``solver.py``：``Δp = 1e5·(ρ/1000)·Q|Q|/Kv_eff²``）。
为了不在 Worker 侧形成 import 依赖，模块包 ``modules/check_valve_v2/module.py``
按同一公式自包含实现；本文件与模块的一致性由测试逐点对照，不靠人工同步。

不依赖 numpy / scipy / solver.py，可在任何进程里导入。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# solver.branch_drop 的阀门换算常数：Δp_pa = 1e5·(ρ/1000)·Q_m3h·|Q_m3h| / Kv_eff²
VALVE_PRESSURE_SCALE = 100000.0
SECONDS_PER_HOUR = 3600.0
REFERENCE_DENSITY_KG_M3 = 998.2

# ---- V0 冻结的默认值（与 docs/MODULES_P0.md §5.2 表格逐项一致） -----------------
DEFAULT_P_CRACK_PA = 0.0
DEFAULT_OPENING_MAX = 1.0
DEFAULT_HYSTERESIS_PA = 0.0
#: 反向截止是精确语义：Δp ≤ p_crack 时 ``opening_ratio`` 精确为 0，求解器把支路
#: 变成 ``flow == 0`` 等式约束，所以反向通过质量的上界就是 0。
REVERSE_LEAK_UPPER_BOUND_KG_S = 0.0
CLOSED_OPENING = 0.0


def _finite(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f'止回阀参数 {name} 必须是有限数值')
    return value


@dataclass(frozen=True)
class ValveParameters:
    """一条止回阀通路的冻结参数；默认值即 V2 发布默认。"""

    kv_m3_h: float = 50.0
    p_crack_pa: float = DEFAULT_P_CRACK_PA
    opening_max: float = DEFAULT_OPENING_MAX
    hysteresis_pa: float = DEFAULT_HYSTERESIS_PA
    density_kg_m3: float = REFERENCE_DENSITY_KG_M3

    def __post_init__(self) -> None:
        object.__setattr__(self, 'kv_m3_h', _finite('kv_m3_h', self.kv_m3_h))
        object.__setattr__(self, 'p_crack_pa', _finite('p_crack_pa', self.p_crack_pa))
        object.__setattr__(self, 'opening_max', _finite('opening_max', self.opening_max))
        object.__setattr__(self, 'hysteresis_pa', _finite('hysteresis_pa', self.hysteresis_pa))
        object.__setattr__(self, 'density_kg_m3', _finite('density_kg_m3', self.density_kg_m3))
        if self.kv_m3_h <= 0:
            raise ValueError('止回阀 kv_m3_h 必须大于零')
        if self.p_crack_pa < 0:
            raise ValueError('止回阀 p_crack_pa 不能为负')
        if not 0.0 <= self.opening_max <= 1.0:
            raise ValueError('止回阀 opening_max 必须在 [0, 1] 内')
        if self.hysteresis_pa < 0:
            raise ValueError('止回阀 hysteresis_pa 不能为负')
        if self.density_kg_m3 <= 0:
            raise ValueError('止回阀 density_kg_m3 必须大于零')


def clamp_opening(opening: float) -> float:
    """把开度夹到 [0, 1]；返回 Python float，便于与关系参数逐位比较。"""
    return min(1.0, max(0.0, float(opening)))


def is_open(delta_p_pa: float, p_crack_pa: float = DEFAULT_P_CRACK_PA,
            hysteresis_pa: float = DEFAULT_HYSTERESIS_PA, was_open: bool = False) -> bool:
    """V0/V2 冻结的开关判据；``delta_p_pa = p_in - p_out``。

    * ``delta_p_pa <= 0``：反向或零压差，**无论迟滞状态如何都关闭**，保证反向精确零流；
    * 默认 ``hysteresis_pa = 0``：开度判据与 accepted state 无关（Δp > p_crack 即开），
      因此 evaluate 是纯函数、同一次求解内不会因状态而变，也不需要求解器外层循环；
    * ``hysteresis_pa > 0``：关闭态要在 Δp > p_crack + h 才开，开启态保持到
      Δp ≤ max(0, p_crack − h) 才关。这条路径要求状态只在 accepted 步更新，
      并在求解器外层重算活动集（见 ``docs/numerics/results/V2.md``）。
    """
    delta_p, p_crack, band = _finite('delta_p_pa', delta_p_pa), _finite('p_crack_pa', p_crack_pa), _finite(
        'hysteresis_pa', hysteresis_pa)
    if band < 0:
        raise ValueError('止回阀 hysteresis_pa 不能为负')
    if delta_p <= 0.0:
        return False
    if not was_open:
        return delta_p > p_crack + band
    return delta_p > max(0.0, p_crack - band)


def required_opening(delta_p_pa: float, p_crack_pa: float = DEFAULT_P_CRACK_PA,
                     opening_max: float = DEFAULT_OPENING_MAX,
                     hysteresis_pa: float = DEFAULT_HYSTERESIS_PA, was_open: bool = False) -> float:
    """返回 evaluate 应写入 ``valve.opening_ratio`` 的开度（精确 0 表示关闭）。

    开启（Δp > p_crack）时取 ``opening_max·sqrt(1 − p_crack/Δp)``，于是
    ``q_vol = Kv·opening·sqrt(Δp/C) = Kv·opening_max·sqrt((Δp − p_crack)/C)``，
    即“开启压差 + 阀门阻力”串联的物理曲线。开启压差以上、迟滞保持开启
    （0 < Δp ≤ p_crack）时按全开处理，这是迟滞状态下的**正向**亚阈值流量，
    反向仍被 ``is_open`` 的第一个分支挡住。
    """
    opening_max = clamp_opening(_finite('opening_max', opening_max))
    if not is_open(delta_p_pa, p_crack_pa, hysteresis_pa, was_open):
        return CLOSED_OPENING
    if opening_max <= 0.0:
        return CLOSED_OPENING
    delta_p, p_crack = float(delta_p_pa), float(p_crack_pa)
    if delta_p <= p_crack:
        return opening_max
    gate = math.sqrt(max(0.0, 1.0 - p_crack / delta_p))
    return clamp_opening(opening_max * gate)


def valve_mass_flow_kg_s(kv_m3_h: float, opening: float, delta_p_pa: float,
                         density_kg_m3: float = REFERENCE_DENSITY_KG_M3) -> float:
    """求解器 ``valve`` 关系的流量（kg/s，正=入口→出口）：``Kv_eff·sqrt(Δp/C)``。

    ``opening == 0`` 返回 0：求解器此时把支路当 ``flow == 0`` 约束，不按本式反算。
    """
    opening = float(opening)
    if opening <= 0.0:
        return 0.0
    kv_eff = float(kv_m3_h) * opening
    ratio = 1e5 * (float(density_kg_m3) / 1000.0)
    return kv_eff * math.sqrt(abs(delta_p_pa) / ratio) * (1.0 if delta_p_pa >= 0 else -1.0) \
        * float(density_kg_m3) / SECONDS_PER_HOUR


def reference_volume_flow_m3_h(params: ValveParameters, delta_p_pa: float,
                               was_open: bool = False) -> float:
    """独立解析参考 Δp–q 曲线（m³/h）；**不**经过“开度反算”这一步。

    关闭（含全部反向）精确 0；开启时 ``Kv·opening_max·sqrt((Δp − p_crack)/C)``；
    迟滞保持开启且 0 < Δp ≤ p_crack 时 ``Kv·opening_max·sqrt(Δp/C)``。
    """
    delta_p = float(delta_p_pa)
    if not is_open(delta_p, params.p_crack_pa, params.hysteresis_pa, was_open):
        return 0.0
    ratio = 1e5 * (params.density_kg_m3 / 1000.0)
    head = delta_p - params.p_crack_pa if delta_p > params.p_crack_pa else delta_p
    if head <= 0.0:
        return 0.0
    return params.kv_m3_h * params.opening_max * math.sqrt(head / ratio)


def reference_mass_flow_kg_s(params: ValveParameters, delta_p_pa: float,
                             was_open: bool = False) -> float:
    """独立解析参考 Δp–q 曲线（kg/s）；与求解器实测流量对照用。"""
    return reference_volume_flow_m3_h(params, delta_p_pa, was_open) * params.density_kg_m3 / SECONDS_PER_HOUR


def reference_pressure_drop_pa(params: ValveParameters, mass_flow_kg_s: float,
                               was_open: bool = False) -> float:
    """参考曲线的逆函数（给定流量求压降），用于独立生成 Δp–q 采样点。"""
    flow = float(mass_flow_kg_s)
    if flow == 0.0:
        return params.p_crack_pa
    volume = abs(flow) * SECONDS_PER_HOUR / params.density_kg_m3
    kv_eff = params.kv_m3_h * params.opening_max
    if kv_eff <= 0.0:
        raise ValueError('全开开度为 0 时止回阀是零流量约束，不存在有限压降')
    drop = 1e5 * (params.density_kg_m3 / 1000.0) * volume * volume / kv_eff ** 2
    return params.p_crack_pa + drop


def opening_slack_pa(delta_p_pa: float, p_crack_pa: float = DEFAULT_P_CRACK_PA) -> float:
    """互补条件里的闭合力余量 λ = p_crack − Δp（Pa）。

    V0 冻结的互补关系：λ ≥ 0 ⇒ q = 0；q > 0 ⇒ λ < 0（即 Δp > p_crack）。
    """
    return float(p_crack_pa) - float(delta_p_pa)


def complementarity_residual(delta_p_pa: float, mass_flow_kg_s: float,
                             p_crack_pa: float = DEFAULT_P_CRACK_PA) -> dict:
    """互补残差三元组：``gap_pa = p_crack − Δp``、``q`` 与 ``gap·q``。

    理想止回阀要求 ``gap ≥ 0`` 时 ``q == 0``、``q > 0`` 时 ``gap < 0``，且 ``gap·q == 0``。
    求解器若实现外层活动集，可用 ``abs(gap·q)`` 判定阀门状态是否自洽。
    """
    gap = opening_slack_pa(delta_p_pa, p_crack_pa)
    flow = float(mass_flow_kg_s)
    return {'opening_slack_pa': gap, 'mass_flow_kg_s': flow, 'product': gap * flow,
            'closed_consistent': gap >= 0.0 and flow == 0.0,
            'open_consistent': gap < 0.0 and flow > 0.0}


def next_open_state(was_open: bool, delta_p_pa: float, p_crack_pa: float = DEFAULT_P_CRACK_PA,
                    hysteresis_pa: float = DEFAULT_HYSTERESIS_PA) -> bool:
    """V2 迟滞状态机的 accepted 步转移函数（commit_step 用；纯函数）。"""
    return is_open(delta_p_pa, p_crack_pa, hysteresis_pa, was_open)


# ---- 方案 (a) 对照：光滑二极管（C¹ 过渡 + 有界泄漏） ------------------------------
def smooth_gate(delta_p_pa: float, p_crack_pa: float, width_pa: float) -> float:
    """tanh 光滑门：Δp → −∞ 时 0，Δp = p_crack 时 0.5，Δp → +∞ 时 1。"""
    width = _finite('width_pa', width_pa)
    if width <= 0:
        raise ValueError('光滑过渡宽度必须大于零')
    x = (float(delta_p_pa) - float(p_crack_pa)) / width
    if x < -60.0:  # tanh 在 |x| 很大时数值上就是 ±1，避免 exp 溢出
        return 0.0
    return 0.5 * (1.0 + math.tanh(x))


def smooth_diode_opening(delta_p_pa: float, p_crack_pa: float, width_pa: float,
                         opening_max: float = DEFAULT_OPENING_MAX) -> float:
    return clamp_opening(opening_max * smooth_gate(delta_p_pa, p_crack_pa, width_pa))


def smooth_diode_mass_flow_kg_s(params: ValveParameters, width_pa: float, delta_p_pa: float) -> float:
    """方案 (a) 的流量：始终以正开度通过阀门律，因此反向有**非零**泄漏。"""
    opening = smooth_diode_opening(delta_p_pa, params.p_crack_pa, width_pa, params.opening_max)
    return valve_mass_flow_kg_s(params.kv_m3_h, opening, delta_p_pa, params.density_kg_m3)


def smooth_reverse_leak_upper_bound(params: ValveParameters, width_pa: float,
                                    floor_pa: float = 1e-3, ceiling_pa: float = 1e7) -> tuple[float, float]:
    """方案 (a) 在全部反向压差上的最大反向流量 (kg/s, 发生处 Δp)。

    反向流量 = ``Kv·gate(Δp)·sqrt(|Δp|/C)``：gate 指数衰减、sqrt 增长，最大值出现在
    中等反向压差处，用对数网格扫描求上界（单调段之间足够密）。返回 (上界, Δp*)。
    """
    if floor_pa <= 0 or ceiling_pa <= floor_pa:
        raise ValueError('反向扫描区间必须满足 0 < floor < ceiling')
    best_flow, best_at = 0.0, 0.0
    steps = 4000
    log_floor, log_ceiling = math.log(floor_pa), math.log(ceiling_pa)
    for index in range(steps + 1):
        delta_p = -math.exp(log_floor + (log_ceiling - log_floor) * index / steps)
        flow = abs(smooth_diode_mass_flow_kg_s(params, width_pa, delta_p))
        if flow > best_flow:
            best_flow, best_at = flow, delta_p
    return best_flow, best_at


def smooth_threshold_flow_kg_s(params: ValveParameters, width_pa: float) -> float:
    """方案 (a) 在开启压差处的流量（gate = 0.5，物理上“尚未开启却已半开”）。"""
    return abs(smooth_diode_mass_flow_kg_s(params, width_pa, params.p_crack_pa))


def curve_points(params: ValveParameters, delta_p_values) -> list[tuple[float, float]]:
    """参考曲线采样：[(Δp_pa, q_kg_s)]，负压差处精确 0。"""
    points = []
    for delta_p in delta_p_values:
        points.append((float(delta_p), reference_mass_flow_kg_s(params, float(delta_p))))
    return points


__all__ = [
    'VALVE_PRESSURE_SCALE', 'SECONDS_PER_HOUR', 'REFERENCE_DENSITY_KG_M3', 'DEFAULT_P_CRACK_PA',
    'DEFAULT_OPENING_MAX', 'DEFAULT_HYSTERESIS_PA', 'REVERSE_LEAK_UPPER_BOUND_KG_S', 'CLOSED_OPENING',
    'ValveParameters', 'clamp_opening', 'is_open', 'required_opening', 'valve_mass_flow_kg_s',
    'reference_volume_flow_m3_h', 'reference_mass_flow_kg_s', 'reference_pressure_drop_pa',
    'opening_slack_pa', 'complementarity_residual', 'next_open_state', 'smooth_gate',
    'smooth_diode_opening', 'smooth_diode_mass_flow_kg_s', 'smooth_reverse_leak_upper_bound',
    'smooth_threshold_flow_kg_s', 'curve_points',
]
