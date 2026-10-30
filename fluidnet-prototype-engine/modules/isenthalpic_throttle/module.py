"""Public SDK isenthalpic throttle: linear and normalized equal-percentage characteristics."""
import math

from fn_sdk import DeviceModule, ModuleContext


class Module:
    def initialize(self, ctx: ModuleContext) -> None:
        ctx.state['accepted_segments'] = 0

    def evaluate(self, ctx: ModuleContext) -> None:
        point = ctx.refrigeration.throttle
        characteristic = ctx.parameter('characteristic', 'linear')
        opening = point.opening_ratio
        if characteristic == 'linear':
            fraction = opening
        elif characteristic == 'equal_percentage':
            ratio = ctx.parameter('rangeability', 50.0)
            if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or ratio <= 1:
                raise ValueError('rangeability must be finite and greater than one')
            fraction = opening if opening in (0.0, 1.0) else math.expm1(opening * math.log(ratio)) / (ratio - 1)
        else:
            raise ValueError('characteristic must be linear or equal_percentage')
        effective = point.rated_kv_m3_h * fraction
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
