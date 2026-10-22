"""毛细管（毛细节流阀）单相液体近似模块。

只注册一条 `pipe` 阻力关系；两相壅塞/闪发不在模型内，每次 evaluate 都发
`CAP_TWO_PHASE_UNSUPPORTED(info)` 提示。参数已是规范单位（m、Pa·s、kg/m³），
模块内不再换算；evaluate 无副作用，只有 commit_step 里改 ctx.state 才会保存。
"""
import math


# 与 backend/fn_engine/solver.py::pipe_drop 保持同一摩擦律；改动求解器时必须同步本函数。
def _pipe_drop(length_m, diameter_m, roughness_m, density_kg_m3, viscosity_pa_s, flow_kg_s):
    area = math.pi * diameter_m ** 2 / 4.0
    reynolds = abs(flow_kg_s) * diameter_m / (viscosity_pa_s * area)
    laminar = 32.0 * viscosity_pa_s * length_m * flow_kg_s / (density_kg_m3 * area * diameter_m ** 2)
    if reynolds <= 2300:
        return laminar
    friction = (-1.8 * math.log10((roughness_m / diameter_m / 3.7) ** 1.11 + 6.9 / reynolds)) ** -2
    turbulent = friction * length_m / diameter_m * flow_kg_s * abs(flow_kg_s) / (2.0 * density_kg_m3 * area ** 2)
    blend = min(1.0, (reynolds - 2300.0) / 1700.0)
    return laminar * (1.0 - blend) + turbulent * blend


def _flow_from_pressure_drop(pressure_drop_pa, length_m, diameter_m, roughness_m, density_kg_m3, viscosity_pa_s):
    """二分反解与 _pipe_drop 同一关系的 |m|；evaluate 阶段拿不到流量时使用。"""
    target = abs(pressure_drop_pa)
    if target <= 0.0:
        return 0.0
    low, high = 0.0, 1.0e4  # 覆盖常规流量；越界按端点取值。
    for _ in range(80):
        middle = 0.5 * (low + high)
        drop = _pipe_drop(length_m, diameter_m, roughness_m, density_kg_m3, viscosity_pa_s, middle)
        if drop < target:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


class Module:
    def initialize(self, ctx):
        # state 的键必须与 manifest 里 source=state 的变量 id 对齐：state.<key>
        ctx.state.setdefault("throughput_kg", 0.0)

    def evaluate(self, ctx):
        # 单相液体近似：两相壅塞/闪发不在模型内，逐次 evaluate 都提示一次。
        ctx.diagnostic(
            "CAP_TWO_PHASE_UNSUPPORTED",
            "capillary_tube 采用单相液体近似：两相壅塞、闪发与出口干度不在模型内，"
            "跨相或湿蒸气工况的流量/压降结果不可信",
            "info",
        )

        inlet = ctx.port("in0")
        diameter_m = max(float(ctx.parameter("diameter_m", 0.0015)), 1e-4)
        length_m = float(ctx.parameter("length_m", 1.5))
        if length_m < 1e-6:
            ctx.diagnostic(
                "CAP_LENGTH_CLAMPED",
                f"length_m={length_m:g} m 低于数值下限 1e-6 m，已按 1e-6 m 计算",
                "warning",
            )
            length_m = 1e-6
        roughness_m = max(float(ctx.parameter("roughness_m", 1.5e-06)), 0.0)
        density_kg_m3 = max(float(inlet.density_kg_m3 or ctx.parameter("density_kg_m3", 998.2)), 1e-3)

        viscosity_raw = float(inlet.viscosity_pa_s or ctx.parameter("viscosity_pa_s", 0.001))
        viscosity_pa_s = max(viscosity_raw, 1e-6)
        if viscosity_raw <= 0.0:
            ctx.diagnostic(
                "CAP_VISCOSITY_FALLBACK",
                f"viscosity_pa_s={viscosity_raw:g} Pa·s 不大于 0，已按 1e-6 Pa·s 计算",
                "warning",
            )

        area_m2 = math.pi * diameter_m ** 2 / 4.0

        # 始终注册细长管阻力关系；毛细管按绝热处理（heat_w=0）。
        ctx.net.pipe(
            channel="main",
            length_m=length_m,
            diameter_m=diameter_m,
            roughness_m=roughness_m,
            density_kg_m3=density_kg_m3,
            viscosity_pa_s=viscosity_pa_s,
            heat_w=0.0,
        )

        # evaluate 处于数值迭代中：端口 mass_flow 优先；否则用试算压差按同一摩擦律反解。
        mass_flow_kg_s = inlet.mass_flow_kg_s
        if mass_flow_kg_s is None:
            pressure_in = inlet.pressure_pa
            pressure_out = ctx.port("out0").pressure_pa
            if pressure_in is None or pressure_out is None:
                mass_flow_kg_s = 0.0
                ctx.diagnostic(
                    "CAP_PRESSURE_UNKNOWN",
                    "试算端口流量与压力均缺失，mean_velocity_m_s 按 0 输出",
                    "warning",
                )
            else:
                mass_flow_kg_s = _flow_from_pressure_drop(
                    pressure_in - pressure_out,
                    length_m,
                    diameter_m,
                    roughness_m,
                    density_kg_m3,
                    viscosity_pa_s,
                )
        velocity_m_s = abs(float(mass_flow_kg_s)) / (density_kg_m3 * area_m2)

        ctx.var("flow_area_m2", area_m2)
        ctx.var("mean_velocity_m_s", velocity_m_s)

    def commit_step(self, ctx, dt_s):
        mass_flow_kg_s = abs(ctx.channel("main").mass_flow_kg_s or 0.0)
        ctx.state["throughput_kg"] = float(ctx.state.get("throughput_kg", 0.0)) + mass_flow_kg_s * dt_s

    def finalize(self, ctx):
        pass  # 运行结束即丢弃实例，不写状态
