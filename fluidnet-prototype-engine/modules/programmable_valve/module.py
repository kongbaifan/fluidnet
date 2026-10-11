class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("throughput_kg", 0.0)
        ctx.state.setdefault("commit_count", 0)

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        rho = inlet.density_kg_m3 or 0.0
        if not rho and inlet.pressure_pa and inlet.temperature_k:
            rho = ctx.fluid.state_pt(inlet.pressure_pa, inlet.temperature_k).density_kg_m3
        ctx.net.valve(
            channel="main",
            kv=ctx.parameter("kv_m3_h"),
            opening=ctx.parameter("opening_ratio"),
            density_kg_m3=rho,
        )
        ctx.var("opening_ratio", ctx.parameter("opening_ratio"))
        ctx.var("density_kg_m3", rho)

    def commit_step(self, ctx, dt_s):
        flow = abs(ctx.channel("main").mass_flow_kg_s)
        ctx.state["throughput_kg"] += flow * dt_s
        ctx.state["commit_count"] += 1

    def finalize(self, ctx):
        pass
