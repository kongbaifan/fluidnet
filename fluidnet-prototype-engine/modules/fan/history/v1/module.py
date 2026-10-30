"""风机：风压-风量曲线折算为泵扬程曲线，按效率换算轴功率与电功率。

参数已是规范单位；evaluate 无流量信息，功率在 commit_step 用收敛流量/压差计算。
"""

import math

DEFAULT_PRESSURE_CURVE = ((0.0, 300.0), (2000.0, 250.0), (4000.0, 120.0), (5000.0, 0.0))
GRAVITY = 9.80665
SPEED_MIN = 0.05
SPEED_MAX = 2.0


def _clamp(value, low, high):
    return min(max(value, low), high)


def _clean_curve(raw):
    """校验风压曲线并返回 (流量 m³/h, 压力 Pa) 点列；非法返回 None。"""
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    points = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            return None
        x, y = row
        if isinstance(x, bool) or isinstance(y, bool):
            return None
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        if not math.isfinite(x) or not math.isfinite(y) or x < 0.0 or y < 0.0:
            return None
        points.append((float(x), float(y)))
    # 泵曲线关系要求首点流量为 0；风压曲线同样应从零流量起。
    if points[0][0] != 0.0:
        return None
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        return None
    if any(b[1] >= a[1] for a, b in zip(points, points[1:])):
        return None
    return points


def _interpolate(points, x):
    """分段线性插值，超出曲线范围时按端点取值（与 numpy.interp 一致）。"""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("shaft_energy_j", 0.0)
        ctx.state.setdefault("electric_energy_j", 0.0)

    def _pressure_curve(self, ctx):
        """校验参数曲线；非法回退默认曲线，末点压力非零时强制归零。"""
        points = _clean_curve(ctx.parameter("pressure_curve", DEFAULT_PRESSURE_CURVE))
        if points is None:
            ctx.diagnostic(
                "FAN_CURVE_INVALID",
                "风压曲线需至少 2 点、首点流量为 0、流量严格递增、压力严格递减且非负；已回退默认曲线",
            )
            points = list(DEFAULT_PRESSURE_CURVE)
        if points[-1][1] != 0.0:
            last_pressure_pa = points[-1][1]
            points = points[:-1] + [(points[-1][0], 0.0)]
            ctx.diagnostic(
                "FAN_CURVE_CLIPPED",
                f"风压曲线末点压力 {last_pressure_pa:g} Pa 不为 0，已强制末点扬程为 0 以保证泵曲线可解",
            )
        return points

    def evaluate(self, ctx):
        air_density_kg_m3 = max(float(ctx.parameter("air_density_kg_m3", 1.2)), 1e-3)
        speed_ratio = _clamp(float(ctx.parameter("speed_ratio", 1.0)), SPEED_MIN, SPEED_MAX)
        points = self._pressure_curve(ctx)
        # H = p/(ρg)：风压曲线按空气柱高折算，泵关系再乘 speed²。
        head_curve = [[x, y / (air_density_kg_m3 * GRAVITY)] for x, y in points]
        ctx.net.pump(
            channel="main",
            head_curve=head_curve,
            speed_ratio=speed_ratio,
            density_kg_m3=air_density_kg_m3,
        )

        nominal_flow_m3_h = max(float(ctx.parameter("nominal_flow_m3_h", 2000.0)), 0.0)
        # 风机相似律：Q∝n、p∝n²；先在折算流量处查曲线再乘 speed²。
        pressure_rise_pa = _interpolate(points, nominal_flow_m3_h / speed_ratio) * speed_ratio ** 2
        ctx.var("pressure_rise_pa", pressure_rise_pa)
        # evaluate 拿不到流量，功率先给 0；commit_step 用收敛值覆盖。
        ctx.var("shaft_power_w", 0.0)
        ctx.var("electric_power_w", 0.0)

    def commit_step(self, ctx, dt_s):
        channel = ctx.channel("main")
        mass_flow_kg_s = abs(float(channel.mass_flow_kg_s or 0.0))
        pressure_drop_pa = abs(float(channel.pressure_drop_pa or 0.0))
        air_density_kg_m3 = max(float(ctx.parameter("air_density_kg_m3", 1.2)), 1e-3)
        efficiency = _clamp(float(ctx.parameter("efficiency", 0.6)), 1e-6, 1.0)
        motor_efficiency = _clamp(float(ctx.parameter("motor_efficiency", 0.9)), 1e-6, 1.0)

        hydraulic_power_w = pressure_drop_pa * mass_flow_kg_s / air_density_kg_m3
        shaft_power_w = hydraulic_power_w / efficiency
        electric_power_w = shaft_power_w / motor_efficiency
        ctx.state["shaft_energy_j"] = float(ctx.state.get("shaft_energy_j", 0.0)) + shaft_power_w * dt_s
        ctx.state["electric_energy_j"] = float(ctx.state.get("electric_energy_j", 0.0)) + electric_power_w * dt_s
        ctx.var("pressure_rise_pa", pressure_drop_pa)
        ctx.var("shaft_power_w", shaft_power_w)
        ctx.var("electric_power_w", electric_power_w)

    def finalize(self, ctx):
        pass
