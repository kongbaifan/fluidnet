"""Dry sensible-heat tower, wet-bulb driving temperature; no evaporation model."""
from fn_sdk import heat_exchanger_effectiveness


from fn_sdk import ModuleContext,DeviceModule


def number(ctx: ModuleContext, name: str) -> float:
    value = ctx.parameter(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be numeric')
    return float(value)


def stored(ctx: ModuleContext, name: str) -> float:
    value = ctx.state.get(name, 0.)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be numeric')
    return float(value)


class Module:
    def initialize(self, ctx: ModuleContext) -> None:
        ctx.state.setdefault('thermal_energy_j', 0.)

    def evaluate(self, ctx: ModuleContext) -> None:
        water = ctx.port('in0')
        ctx.net.pipe(channel='main', length_m=number(ctx, 'water_side_length_m'),
            diameter_m=number(ctx, 'water_side_diameter_m'), roughness_m=number(ctx, 'roughness_m'),
            density_kg_m3=water.density_kg_m3, viscosity_pa_s=water.viscosity_pa_s)

    def terms(self, ctx: ModuleContext) -> tuple[float, float, float]:
        flow = ctx.channel('main').mass_flow_kg_s
        water = ctx.port('in0' if flow >= 0 else 'out0')
        if water.specific_heat_j_kg_k is None or water.temperature_k is None:
            raise ValueError('host must provide inlet temperature and heat capacity')
        cw = abs(flow) * water.specific_heat_j_kg_k
        ca = number(ctx, 'air_flow_m3_s') * number(ctx, 'air_density_kg_m3') * number(ctx, 'air_cp_j_kg_k')
        epsilon = heat_exchanger_effectiveness(ua_w_k=number(ctx, 'ua_w_k'), capacity_a_w_k=cw, capacity_b_w_k=ca)
        return -epsilon * min(ca, cw) * (water.temperature_k - number(ctx, 'air_wet_bulb_temperature_k')), epsilon, ca

    def thermal(self, ctx: ModuleContext) -> None:
        power, _, _ = self.terms(ctx)
        ctx.heat('main', power)

    def observe(self, ctx: ModuleContext) -> None:
        _, epsilon, ca = self.terms(ctx)
        flow = ctx.channel('main').mass_flow_kg_s
        outlet = ctx.port('out0' if flow >= 0 else 'in0')
        if outlet.temperature_k is None: raise ValueError('host must provide outlet temperature')
        power = ctx.channel('main').heat_w
        ctx.var('heat_flow_w', power)
        ctx.var('water_outlet_temperature_k', outlet.temperature_k)
        ctx.var('air_outlet_temperature_k', number(ctx, 'air_inlet_temperature_k') - power / ca if ca else number(ctx, 'air_inlet_temperature_k'))
        ctx.var('effectiveness', epsilon)
        ctx.var('approach_k', outlet.temperature_k - number(ctx, 'air_wet_bulb_temperature_k'))

    def commit_step(self, ctx: ModuleContext, dt_s: float) -> None:
        ctx.state['thermal_energy_j'] = stored(ctx, 'thermal_energy_j') + ctx.channel('main').heat_w * dt_s

    def finalize(self, ctx: ModuleContext) -> None:
        pass


def typed_module() -> DeviceModule:
    return Module()
