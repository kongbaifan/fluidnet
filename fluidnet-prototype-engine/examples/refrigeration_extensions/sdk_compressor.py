class Compressor:
    def evaluate(self, ctx):
        x = ctx.refrigeration.point
        p = ctx.parameters
        # A custom pressure-ratio dependent volumetric-efficiency curve.
        ratio = x.outlet_pressure_pa / x.inlet_pressure_pa
        eta_v = max(0.1, p['volumetric_efficiency'] - 0.01 * max(0.0, ratio - 2.0))
        mass = p['displacement_m3_s'] * p['load_ratio'] * eta_v * x.inlet_density_kg_m3 if x.enabled else 0.0
        hout = x.inlet_enthalpy_j_kg + (x.isentropic_outlet_enthalpy_j_kg - x.inlet_enthalpy_j_kg) / p['isentropic_efficiency']
        shaft = mass * (hout - x.inlet_enthalpy_j_kg)
        ctx.refrigeration.balance(mass_flow_kg_s=mass, outlet_enthalpy_j_kg=hout,
            shaft_power_w=shaft, electric_power_w=shaft / p['motor_efficiency'])

    def initialize(self, ctx):
        ctx.state['accepted_seconds'] = 0.0

    def commit_step(self, ctx, dt_s):
        ctx.state['accepted_seconds'] += dt_s

    def finalize(self, ctx):
        pass
