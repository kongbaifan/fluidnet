"""送/回风口：由额定风量与额定压降折算等效 Kv。

阀门关系 Q = Kv·√(Δp / (1e5·ρ/1000))，取额定点反解得
Kv = Q_nom / √(Δp_nom / (1e5·ρ/1000))。
"""

import math


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("throughput_kg", 0.0)

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        outlet = ctx.port("out0")
        if inlet.pressure_pa is not None and outlet.pressure_pa is not None and outlet.pressure_pa > inlet.pressure_pa:
            inlet = outlet
        flow_m3_h = max(float(ctx.parameter("nominal_flow_m3_h", 1000.0)), 1e-9)
        drop_pa = max(float(ctx.parameter("nominal_pressure_drop_pa", 50.0)), 1e-6)
        density = max(float(inlet.density_kg_m3 or ctx.parameter("density_kg_m3", 1.2)), 1e-4)

        # Q[m³/h] = Kv·√(Δp[Pa] / (1e5·ρ/1000))  → 额定点反解 Kv。
        kv_m3_h = flow_m3_h / math.sqrt(drop_pa / (1e5 * density / 1000.0))
        if kv_m3_h <= 0.0 or not math.isfinite(kv_m3_h):
            raise ValueError("送/回风口额定点无法折算出有效 Kv，请检查额定风量与额定压降")
        ctx.net.valve(channel="main", kv=kv_m3_h, opening=1.0, density_kg_m3=density)
        ctx.var("kv_m3_h", kv_m3_h)

    def commit_step(self, ctx, dt_s):
        mass_flow = abs(ctx.channel("main").mass_flow_kg_s or 0.0)
        ctx.state["throughput_kg"] = float(ctx.state.get("throughput_kg", 0.0)) + mass_flow * dt_s

    def finalize(self, ctx):
        pass
