"""风管管件：局部阻力系数 K 折算为阀门等效 Kv（矩形断面）。

Δp = K·ρv²/2 与阀门模型 Δp = 1e5·(ρ/1000)·Q|Q|/Kv² 同解，得到
Kv = 50912·A/√K（与 modules/pipe_fitting 同一推导，见 docs/MODULES_P0.md §1.5）。
K 取工程手册教学默认值，可用 fitting_type=custom + loss_coefficient 覆盖。
"""

import math

# 风管常用局部阻力系数（教学默认值；矩形/圆形按当地手册可覆写）。
LOSS_COEFFICIENTS = {
    "elbow_90": 0.3,        # 90° 弯头（圆弧/导流叶片，R/D≈1.5）
    "elbow_45": 0.2,        # 45° 弯头
    "tee_through": 0.2,     # 三通直通
    "tee_branch": 1.0,      # 三通支管
    "transition": 0.15,     # 渐扩/渐缩
    "entrance": 0.5,        # 进口
    "exit": 1.0,            # 出口
}

K_MIN = 0.01
KV_CONSTANT = 50912.0


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("throughput_kg", 0.0)

    def _loss_coefficient(self, ctx):
        fitting_type = str(ctx.parameter("fitting_type", "elbow_90"))
        fallback = float(ctx.parameter("loss_coefficient", 0.3))
        if fitting_type == "custom":
            coefficient = fallback
        elif fitting_type in LOSS_COEFFICIENTS:
            coefficient = LOSS_COEFFICIENTS[fitting_type]
        else:
            coefficient = fallback
            ctx.diagnostic("DF_FITTING_UNKNOWN", f"未知风管管件类型 {fitting_type!r}，回退 loss_coefficient={fallback}")
        if coefficient < K_MIN:
            ctx.diagnostic("DF_K_CLAMPED", f"K={coefficient} 低于下限 {K_MIN}，已按 {K_MIN} 计算")
            coefficient = K_MIN
        return coefficient

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        outlet = ctx.port("out0")
        if inlet.pressure_pa is not None and outlet.pressure_pa is not None and outlet.pressure_pa > inlet.pressure_pa:
            inlet = outlet
        coefficient = self._loss_coefficient(ctx)
        width = max(float(ctx.parameter("duct_width_m", 0.4)), 1e-3)
        height = max(float(ctx.parameter("duct_height_m", 0.4)), 1e-3)
        density = max(float(inlet.density_kg_m3 or ctx.parameter("density_kg_m3", 1.2)), 1e-4)
        area = width * height

        kv_m3_h = KV_CONSTANT * area / math.sqrt(coefficient)
        ctx.net.valve(channel="main", kv=kv_m3_h, opening=1.0, density_kg_m3=density)

        pressure_in = inlet.pressure_pa
        pressure_out = ctx.port("out0").pressure_pa
        if pressure_in is None or pressure_out is None:
            velocity = 0.0
            ctx.diagnostic("DF_PRESSURE_UNKNOWN", "试算端口压力缺失，velocity_m_s 暂按 0 输出")
        else:
            velocity = math.sqrt(2.0 * abs(pressure_in - pressure_out) / (coefficient * density))

        ctx.var("loss_coefficient", coefficient)
        ctx.var("velocity_m_s", velocity)

    def commit_step(self, ctx, dt_s):
        mass_flow = abs(ctx.channel("main").mass_flow_kg_s or 0.0)
        ctx.state["throughput_kg"] = float(ctx.state.get("throughput_kg", 0.0)) + mass_flow * dt_s

    def finalize(self, ctx):
        pass
