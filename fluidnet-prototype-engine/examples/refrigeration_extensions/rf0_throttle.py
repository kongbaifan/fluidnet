"""RF-0 experimental author module, executed only by the dedicated validation harness.

Uses the public SDK and no fn_engine imports. This is not a published station SDK.
Inputs are SI port states from the SAME candidate vessel state; Kv is m3/h.
"""
import math

from fn_sdk import JSONValue, ModuleContext


def number(value: JSONValue) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('expected a finite number')
    return float(value)


class Module:
    def initialize(self, ctx: ModuleContext) -> None:
        ctx.state['accepted_segments'] = 0
        ctx.state['last_accepted_time_s'] = 0.0

    def evaluate(self, ctx: ModuleContext) -> None:
        inlet, outlet = ctx.port('in0'), ctx.port('out0')
        assert inlet.pressure_pa is not None and outlet.pressure_pa is not None
        assert inlet.density_kg_m3 is not None
        opening = number(ctx.parameter('opening_ratio'))
        kv = number(ctx.parameter('kv_m3_h'))
        effective = kv * opening
        drop = inlet.pressure_pa - outlet.pressure_pa
        mass = effective / 3600 * math.sqrt(1000 * inlet.density_kg_m3 * drop / 1e5) if drop > 0 else 0.0
        ctx.var('mass_flow_kg_s', mass)
        ctx.var('effective_kv_m3_h', effective)

    def commit_step(self, ctx: ModuleContext, dt_s: float) -> None:
        count = ctx.state['accepted_segments']
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError('accepted_segments must be an integer')
        ctx.state['accepted_segments'] = count + 1
        ctx.state['last_accepted_time_s'] = ctx.time_s

    def finalize(self, ctx: ModuleContext) -> None:
        pass
