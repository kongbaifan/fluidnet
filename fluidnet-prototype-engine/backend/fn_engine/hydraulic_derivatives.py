"""内置水力关系的解析导数（J0/J1）。

`solver` 从本模块导入**数值**函数（`pipe_drop`、`pump_head`、`branch_drop_value`），
本模块同时提供对应的 `*_and_slope` 版本供解析 Jacobian 使用。
MOD-S1 将标量阻力计算与管道基础项提取到 fn_sdk._hydraulic_core；引擎保留历史入口、
常数及运算顺序，作者通过 fn_sdk.hydraulics 的校验入口使用同一计算，不在残差热路径重复校验。

分段约定的显式说明
------------------
- 层流/湍流过渡带 `2300 < Re < 4000` 用线性混合 `lam*(1-b) + turb*b`，`b = (Re-2300)/1700`。
  `Re = 2300` 处取右导数（含混合项），`Re = 4000` 处取湍流导数（混合项为 0）：
  这是单侧约定，不伪称该点全局可导。
- 泵曲线是分段线性插值：拐点处取右段斜率；超出曲线范围时沿用 `pump_head` 的线性外推
  （线性外推自身可导，端点取相邻段斜率）。
- 阀门/阻力/管道的 `q·|q|` 型二次项在 `q = 0` 处导数为 0（与数学极限一致）。

所有斜率都定义在**质量流量 q [kg/s]** 上（不是体积流量 m³/h）。
"""
from __future__ import annotations

import math

from fn_sdk import _hydraulic_core as _shared

GRAVITY = 9.80665
# Reference values at 250 kPa / 20 °C（历史公开默认值；与项目配置的物性服务无关）。
RHO_WATER = 998.2752462838249
MU_WATER = 1.0015503944484675e-3


def _pipe_area(diameter: float) -> float:
    return _shared.pipe_area(diameter)


def haaland_friction(roughness: float, diameter: float, reynolds: float) -> float:
    """Haaland 湍流摩阻系数（与历史实现完全一致）。"""
    return _shared.haaland_friction(roughness, diameter, reynolds)


def _haaland_slope(roughness: float, diameter: float, reynolds: float, friction: float) -> float:
    """d f / d Re。x = (ε/D/3.7)^1.11 + 6.9/Re，g = -1.8·log10 x，f = g^-2，df/dx = 3.6/(x·ln10·g³)。"""
    x = (roughness / diameter / 3.7) ** 1.11 + 6.9 / reynolds
    g = -1.8 * math.log10(x)
    df_dx = 2 * 1.8 / (x * math.log(10) * g ** 3)
    return df_dx * (-6.9 / reynolds ** 2)


def _pipe_terms(params, density: float, viscosity: float):
    length, diameter = params['length_m'], params['diameter_m']
    return _shared.pipe_terms(length, diameter, density, viscosity)


def pipe_drop(params, flow, density=RHO_WATER, viscosity=MU_WATER) -> float:
    """值版本（历史语义：不含高差项，`solver.pipe_drop` 直接复用）。"""
    return _shared.pipe_drop(params['length_m'], params['diameter_m'], params['roughness_m'], flow, density, viscosity)


def pipe_drop_and_slope(params, flow, density=RHO_WATER, viscosity=MU_WATER) -> tuple[float, float]:
    """不含高差项的管道压降与导数；高差常量项在 `branch_drop_*` 里加。"""
    length, diameter, area, coef = _pipe_terms(params, density, viscosity)
    reynolds = abs(flow) * diameter / (viscosity * area)
    laminar = coef * flow
    if reynolds < 2300:
        return laminar, coef
    roughness = params['roughness_m']
    friction = haaland_friction(roughness, diameter, reynolds)
    turbulent = friction * length / diameter * flow * abs(flow) / (2 * density * area ** 2)
    blend = min(1., (reynolds - 2300) / 1700)
    value = laminar * (1 - blend) + turbulent * blend
    d_re_dq = diameter / (viscosity * area) * (1. if flow >= 0 else -1.)
    d_f_dq = _haaland_slope(roughness, diameter, reynolds, friction) * d_re_dq
    d_turbulent_dq = length / diameter / (2 * density * area ** 2) * (
        d_f_dq * flow * abs(flow) + friction * 2 * abs(flow))
    if reynolds >= 4000:
        return value, d_turbulent_dq
    d_blend_dq = d_re_dq / 1700
    return value, coef * (1 - blend) + d_turbulent_dq * blend + (turbulent - laminar) * d_blend_dq


def duct_geometry(params) -> tuple[float, float]:
    """矩形风管的流通面积 [m²] 与水力直径 Dh = 2WH/(W+H) [m]。"""
    width, height = params['duct_width_m'], params['duct_height_m']
    return width * height, 2. * width * height / (width + height)


def duct_drop(params, flow, density=RHO_WATER, viscosity=MU_WATER) -> float:
    """矩形风管沿程压降：水力直径近似 + 与 pipe 相同的 Haaland 湍流摩擦。"""
    area, diameter = duct_geometry(params)
    length, roughness = params['length_m'], params['roughness_m']
    reynolds = abs(flow) * diameter / (viscosity * area)
    if reynolds < 1e-12:
        return 0.
    coef = 128. * viscosity * length / (math.pi * diameter ** 4 * density)
    if reynolds < 2300:
        return coef * flow
    friction = haaland_friction(roughness, diameter, reynolds)
    turbulent = friction * length / diameter * flow * abs(flow) / (2. * density * area ** 2)
    blend = min(1., (reynolds - 2300) / 1700.)
    return coef * flow * (1 - blend) + turbulent * blend


def duct_drop_and_slope(params, flow, density=RHO_WATER, viscosity=MU_WATER) -> tuple[float, float]:
    """矩形风管压降与对 q 的导数（层流/过渡/湍流分段约定与 pipe 一致）。"""
    area, diameter = duct_geometry(params)
    length, roughness = params['length_m'], params['roughness_m']
    coef = 128. * viscosity * length / (math.pi * diameter ** 4 * density)
    laminar = coef * flow
    reynolds = abs(flow) * diameter / (viscosity * area)
    if reynolds < 2300:
        return laminar, coef
    friction = haaland_friction(roughness, diameter, reynolds)
    turbulent = friction * length / diameter * flow * abs(flow) / (2. * density * area ** 2)
    blend = min(1., (reynolds - 2300) / 1700.)
    value = laminar * (1 - blend) + turbulent * blend
    d_re_dq = diameter / (viscosity * area) * (1. if flow >= 0 else -1.)
    d_f_dq = _haaland_slope(roughness, diameter, reynolds, friction) * d_re_dq
    d_turbulent_dq = length / diameter / (2. * density * area ** 2) * (
        d_f_dq * flow * abs(flow) + friction * 2. * abs(flow))
    if reynolds >= 4000:
        return value, d_turbulent_dq
    d_blend_dq = d_re_dq / 1700.
    return value, coef * (1 - blend) + d_turbulent_dq * blend + (turbulent - laminar) * d_blend_dq


def _pump_segment(curve, x: float):
    points = curve
    if x < points[0][0]:
        return points[0], points[1]
    if x > points[-1][0]:
        return points[-2], points[-1]
    for k in range(len(points) - 1):
        left, right = points[k], points[k + 1]
        # 拐点取右段（左闭右开）：这是显式的单侧约定，末端点归最后一段。
        if left[0] <= x < right[0]:
            return left, right
    return points[-2], points[-1]


def pump_head(curve, flow_m3_h: float, speed: float) -> float:
    """值版本（历史语义，`solver.pump_head` 直接复用）。"""
    x = flow_m3_h / speed
    a, b = _pump_segment(curve, x)
    return (a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])) * speed ** 2


def pump_head_and_slope(curve, flow_m3_h: float, speed: float) -> tuple[float, float]:
    x = flow_m3_h / speed
    a, b = _pump_segment(curve, x)
    head = (a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])) * speed ** 2
    # d head / d(flow_m3_h) = 段斜率 · speed² · d x/d flow = 段斜率 · speed
    return head, (b[1] - a[1]) / (b[0] - a[0]) * speed


def branch_drop_value(model: str, params: dict, flow: float, density: float, viscosity: float) -> float:
    """单条内置支路的压降（不含两端压力项），与历史 `branch_drop` 完全一致。"""
    if model == 'valve':
        kv = params['kv_m3_h'] * params['opening_ratio']
        return _shared.valve_drop(kv, flow, density) + density * GRAVITY * params.get('height_m', 0)
    if model == 'pipe':
        return pipe_drop(params, flow, density, viscosity) + density * GRAVITY * params.get('height_m', 0)
    if model == 'duct':
        return duct_drop(params, flow, density, viscosity)
    if model == 'pump_curve':
        if params['speed_ratio'] <= 0:
            raise ValueError('停泵阻力模型尚未定义，转速必须大于零')
        return -density * GRAVITY * pump_head(params['head_curve'], flow / density * 3600, params['speed_ratio'])
    if model == 'resistance':
        return _shared.resistance_drop(params['diameter_m'], params['loss_coefficient'], flow, density)
    raise ValueError(f'未注册的支路模型：{model}')


def branch_drop_and_slope(model: str, params: dict, flow: float, density: float,
                          viscosity: float) -> tuple[float, float]:
    """单条内置支路的压降与其对 q 的导数。"""
    if model == 'valve':
        kv = params['kv_m3_h'] * params['opening_ratio']
        volume_coef = 3600. / density
        scale = 100000 * (density / 1000) / kv ** 2
        volume = flow * volume_coef
        value = scale * volume * abs(volume) + density * GRAVITY * params.get('height_m', 0)
        return value, 2 * scale * abs(volume) * volume_coef
    if model == 'pipe':
        value, slope = pipe_drop_and_slope(params, flow, density, viscosity)
        return value + density * GRAVITY * params.get('height_m', 0), slope
    if model == 'duct':
        return duct_drop_and_slope(params, flow, density, viscosity)
    if model == 'pump_curve':
        if params['speed_ratio'] <= 0:
            raise ValueError('停泵阻力模型尚未定义，转速必须大于零')
        head, head_slope = pump_head_and_slope(params['head_curve'], flow / density * 3600, params['speed_ratio'])
        return -density * GRAVITY * head, -density * GRAVITY * head_slope * 3600 / density
    if model == 'resistance':
        area = _pipe_area(params['diameter_m'])
        coef = params['loss_coefficient'] / (2 * density * area ** 2)
        return coef * flow * abs(flow), 2 * coef * abs(flow)
    raise ValueError(f'未注册的支路模型：{model}')
