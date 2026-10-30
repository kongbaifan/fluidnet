"""风阀：额定 Kv × 开度特性 → 有效 Kv，0% 开度以 opening=0 精确关断。

特性（教学口径，均以额定 Kv 为满开值）：
- linear：Kv = Kv_max · x
- equal_percentage：Kv = Kv_max · ALF^(x−1)（x>0）；x=0 关断
- quick_open：Kv = Kv_max · x^0.2（约 20% 开度即达 72% 流量，近似快开特性）
"""

CHARACTERISTICS = ("linear", "equal_percentage", "quick_open")


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("throughput_kg", 0.0)

    def _effective_kv(self, ctx, kv_rated, opening):
        characteristic = str(ctx.parameter("characteristic", "linear"))
        if opening <= 0.0:
            return 0.0, characteristic
        if characteristic == "linear":
            return kv_rated * opening, characteristic
        if characteristic == "equal_percentage":
            alf = max(float(ctx.parameter("rangeability_alf", 30.0)), 2.0)
            return kv_rated * alf ** (opening - 1.0), characteristic
        if characteristic == "quick_open":
            return kv_rated * opening ** 0.2, characteristic
        ctx.diagnostic("DD_CHARACTERISTIC_UNKNOWN", f"未知开度特性 {characteristic!r}，按 linear 计算")
        return kv_rated * opening, "linear"

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        outlet = ctx.port("out0")
        if inlet.pressure_pa is not None and outlet.pressure_pa is not None and outlet.pressure_pa > inlet.pressure_pa:
            inlet = outlet
        kv_rated = max(float(ctx.parameter("kv_m3_h", 500.0)), 1e-6)
        opening = min(max(float(ctx.parameter("opening_ratio", 0.5)), 0.0), 1.0)
        density = max(float(inlet.density_kg_m3 or ctx.parameter("density_kg_m3", 1.2)), 1e-4)

        effective_kv, _ = self._effective_kv(ctx, kv_rated, opening)
        if effective_kv <= 0.0:
            ctx.net.valve(channel="main", kv=kv_rated, opening=0.0, density_kg_m3=density)
        else:
            ctx.net.valve(channel="main", kv=effective_kv, opening=1.0, density_kg_m3=density)

        ctx.var("effective_kv_m3_h", effective_kv)
        ctx.var("effective_opening_ratio", opening)

    def commit_step(self, ctx, dt_s):
        mass_flow = abs(ctx.channel("main").mass_flow_kg_s or 0.0)
        ctx.state["throughput_kg"] = float(ctx.state.get("throughput_kg", 0.0)) + mass_flow * dt_s

    def finalize(self, ctx):
        pass
