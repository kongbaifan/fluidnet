"""变速水泵：扬程-流量曲线 + 效率链，输出扬程、轴功率与电功率。

参数已是规范单位；evaluate 无流量信息，功率在 commit_step 用收敛流量/压差计算。
"""

import math

DEFAULT_HEAD_CURVE = ((0.0, 20.0), (10.0, 18.0), (20.0, 12.0), (30.0, 0.0))
GRAVITY = 9.80665
SPEED_MIN = 0.05
SPEED_MAX = 2.0


def _clamp(value, low, high):
    return min(max(value, low), high)


def _clean_curve(raw):
    """校验扬程曲线（首点流量 0、末点扬程 0、流量递增、扬程严格递减且非负）；非法返回 None。"""
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
    if points[0][0] != 0.0 or points[-1][1] != 0.0:
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

    def _head_curve(self, ctx):
        """校验参数曲线；非法时回退默认曲线，保证泵关系可解。"""
        points = _clean_curve(ctx.parameter("head_curve", DEFAULT_HEAD_CURVE))
        if points is None:
            ctx.diagnostic(
                "PUMP_CURVE_INVALID",
                "扬程曲线需至少 2 点、首点流量为 0、末点扬程为 0、流量严格递增、扬程严格递减且非负；"
                "已回退默认曲线",
            )
            points = list(DEFAULT_HEAD_CURVE)
        return points

    def evaluate(self, ctx):
        density_kg_m3 = max(float(ctx.parameter("density_kg_m3", 998.2)), 1e-3)
        speed_ratio = _clamp(float(ctx.parameter("speed_ratio", 1.0)), SPEED_MIN, SPEED_MAX)
        points = self._head_curve(ctx)
        ctx.net.pump(
            channel="main",
            head_curve=[[x, y] for x, y in points],
            speed_ratio=speed_ratio,
            density_kg_m3=density_kg_m3,
        )

        nominal_flow_m3_h = max(float(ctx.parameter("nominal_flow_m3_h", 10.0)), 0.0)
        # 相似律：Q∝n、H∝n²；与 solver.pump_head 一致，先在折算流量处查曲线再乘 speed²。
        pump_head_m = _interpolate(points, nominal_flow_m3_h / speed_ratio) * speed_ratio ** 2
        ctx.var("pump_head_m", pump_head_m)
        # evaluate 拿不到流量，功率先给 0；commit_step 用收敛值覆盖。
        ctx.var("shaft_power_w", 0.0)
        ctx.var("electric_power_w", 0.0)

    def commit_step(self, ctx, dt_s):
        channel = ctx.channel("main")
        mass_flow_kg_s = abs(float(channel.mass_flow_kg_s or 0.0))
        pressure_drop_pa = abs(float(channel.pressure_drop_pa or 0.0))
        density_kg_m3 = max(float(ctx.parameter("density_kg_m3", 998.2)), 1e-3)
        efficiency = _clamp(float(ctx.parameter("efficiency", 0.7)), 1e-6, 1.0)
        motor_efficiency = _clamp(float(ctx.parameter("motor_efficiency", 0.9)), 1e-6, 1.0)

        hydraulic_power_w = pressure_drop_pa * mass_flow_kg_s / density_kg_m3
        shaft_power_w = hydraulic_power_w / efficiency
        electric_power_w = shaft_power_w / motor_efficiency
        ctx.state["shaft_energy_j"] = float(ctx.state.get("shaft_energy_j", 0.0)) + shaft_power_w * dt_s
        ctx.state["electric_energy_j"] = float(ctx.state.get("electric_energy_j", 0.0)) + electric_power_w * dt_s
        ctx.var("pump_head_m", pressure_drop_pa / (density_kg_m3 * GRAVITY))
        ctx.var("shaft_power_w", shaft_power_w)
        ctx.var("electric_power_w", electric_power_w)

    def finalize(self, ctx):
        pass
