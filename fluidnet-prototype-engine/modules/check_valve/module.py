class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("closed_steps", 0)
        ctx.state.setdefault("throughput_kg", 0.0)
        ctx.state.setdefault("last_direction", 1)

    @staticmethod
    def _direction(ctx):
        """+1 forward, -1 reverse; unknown pressures are treated as forward."""
        pressure_in = ctx.port("in0").pressure_pa
        pressure_out = ctx.port("out0").pressure_pa
        if pressure_in is None or pressure_out is None:
            return 1
        cracking = float(ctx.parameter("cracking_pressure_pa", 0.0) or 0.0)
        return -1 if pressure_out - pressure_in > cracking else 1

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        direction = self._direction(ctx)
        opening_ratio = float(ctx.parameter("opening_ratio", 1.0))
        opening = 0.0 if direction < 0 else opening_ratio
        density_kg_m3 = inlet.density_kg_m3 or float(ctx.parameter("density_kg_m3", 998.2))

        # opening=0 makes the branch a zero-flow constraint in the hydraulic solver.
        ctx.net.valve(
            channel="main",
            kv=float(ctx.parameter("kv_m3_h", 50.0)),
            opening=opening,
            density_kg_m3=density_kg_m3,
        )
        ctx.var("opening_ratio", opening)
        ctx.var("direction", direction)

    def commit_step(self, ctx, dt_s):
        direction = self._direction(ctx)
        # last_direction keeps the committed direction for the next step's bookkeeping.
        if direction < 0:
            ctx.state["closed_steps"] = int(ctx.state.get("closed_steps", 0)) + 1
        ctx.state["last_direction"] = direction
        mass_flow_kg_s = ctx.channel("main").mass_flow_kg_s or 0.0
        ctx.state["throughput_kg"] = float(ctx.state.get("throughput_kg", 0.0)) + abs(mass_flow_kg_s) * dt_s

    def finalize(self, ctx):
        pass
