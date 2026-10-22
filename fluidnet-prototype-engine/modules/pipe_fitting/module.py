import math

# 常用管件的局部阻力系数 K（工程手册参考值）；custom 用参数 loss_coefficient。
LOSS_COEFFICIENTS = {
    "elbow_90": 0.9,
    "elbow_45": 0.4,
    "reducer": 0.5,
    "tee_through": 0.2,
    "tee_branch": 1.0,
    "entrance": 0.5,
    "exit": 1.0,
}

# 极小 K 会让等效 Kv 过大、放大数值噪声，保留工程下限。
K_MIN = 0.05
# Kv[m3/h] = 50912 * A[m2] / sqrt(K)；推导见 docs/MODULES_P0.md §1.5。
KV_CONSTANT = 50912.0


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("throughput_kg", 0.0)

    def _loss_coefficient(self, ctx):
        fitting_type = str(ctx.parameter("fitting_type", "elbow_90"))
        fallback = float(ctx.parameter("loss_coefficient", 0.9))
        if fitting_type == "custom":
            coefficient = fallback
        elif fitting_type in LOSS_COEFFICIENTS:
            coefficient = LOSS_COEFFICIENTS[fitting_type]
        else:
            coefficient = fallback
            ctx.diagnostic(
                "PF_FITTING_UNKNOWN",
                f"未知管件类型 {fitting_type!r}，回退 loss_coefficient={fallback}",
            )
        if coefficient < K_MIN:
            ctx.diagnostic(
                "PF_K_CLAMPED",
                f"K={coefficient} 低于下限 {K_MIN}，已按 {K_MIN} 计算",
            )
            coefficient = K_MIN
        return coefficient

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        coefficient = self._loss_coefficient(ctx)
        diameter_m = max(float(ctx.parameter("diameter_m", 0.05)), 1e-4)
        density_kg_m3 = max(float(inlet.density_kg_m3 or ctx.parameter("density_kg_m3", 998.2)), 1e-3)
        area_m2 = math.pi * diameter_m ** 2 / 4.0

        # 把管件的 K 折算成等效阀门 Kv：Δp = K·m|m|/(2ρA²) 与阀门模型同压力降。
        kv_m3_h = KV_CONSTANT * area_m2 / math.sqrt(coefficient)
        ctx.net.valve(
            channel="main",
            kv=kv_m3_h,
            opening=1.0,
            density_kg_m3=density_kg_m3,
        )

        # evaluate 处于数值迭代中，端口流量尚不可用；有压差时用 Δp=K·ρv²/2 折算流速。
        pressure_in = inlet.pressure_pa
        pressure_out = ctx.port("out0").pressure_pa
        if pressure_in is None or pressure_out is None:
            velocity_m_s = 0.0
            ctx.diagnostic("PF_PRESSURE_UNKNOWN", "试算端口压力缺失，velocity_m_s 暂按 0 输出")
        else:
            velocity_m_s = math.sqrt(2.0 * abs(pressure_in - pressure_out) / (coefficient * density_kg_m3))

        ctx.var("loss_coefficient", coefficient)
        ctx.var("velocity_m_s", velocity_m_s)

    def commit_step(self, ctx, dt_s):
        mass_flow_kg_s = abs(ctx.channel("main").mass_flow_kg_s or 0.0)
        ctx.state["throughput_kg"] = float(ctx.state.get("throughput_kg", 0.0)) + mass_flow_kg_s * dt_s

    def finalize(self, ctx):
        pass
