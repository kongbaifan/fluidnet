"""SDK 0.7 role example. RF-1 supports typed Worker calls; station integration follows in RF-2."""
import math

from fn_sdk import DeviceModule, ModuleContext


class Module:
    def initialize(self, ctx: ModuleContext) -> None:
        ctx.state['accepted_segments'] = 0

    def evaluate(self, ctx: ModuleContext) -> None:
        point = ctx.refrigeration.throttle
        effective = point.rated_kv_m3_h * point.opening_ratio
        drop = max(point.inlet_pressure_pa-point.outlet_pressure_pa,0.)
        mass = effective/3600*math.sqrt(1000*point.inlet_density_kg_m3*drop/100000)
        ctx.refrigeration.flow(mass_flow_kg_s=mass,effective_kv_m3_h=effective)
        ctx.var('opening',point.opening_ratio)

    def commit_step(self, ctx: ModuleContext, dt_s: float) -> None:
        count = ctx.state['accepted_segments']
        if isinstance(count,bool) or not isinstance(count,int):
            raise ValueError('accepted_segments must be an integer')
        ctx.state['accepted_segments'] = count+1

    def finalize(self, ctx: ModuleContext) -> None:
        pass


def typed_module() -> DeviceModule:
    return Module()
