class Condenser:
    def initialize(self, ctx):
        pass

    def commit_step(self, ctx, dt_s):
        pass

    def finalize(self, ctx):
        pass

    def evaluate(self, ctx):
        x = ctx.refrigeration.point
        p = ctx.parameters
        # A custom fan-speed law, with explicit natural convection at zero fan.
        ua = p['ua_w_k'] * (p['natural_ua_ratio'] + (1.0 - p['natural_ua_ratio']) * p['fan_ratio'] ** 0.8)
        ua *= p['flooded_ua_ratio'] + (1.0 - p['flooded_ua_ratio']) * p['return_gas_ratio']
        ctx.refrigeration.balance(outlet_enthalpy_j_kg=x.inlet_enthalpy_j_kg,
            heat_rejection_w=ua * (x.inlet_temperature_k - x.sink_temperature_k),
            electric_power_w=p['fan_power_w'] * p['fan_ratio'] ** 3)
