"""Editable algebraic water/brine valve, with a bounded opening characteristic."""
from __future__ import annotations

import math

from fn_sdk import DeviceModule, JSONValue, ModuleContext


def _number(value: JSONValue) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('参数必须是有限数值')
    return float(value)


class Module:
    def initialize(self, ctx: ModuleContext) -> None:
        ctx.state.setdefault('throughput_kg', 0.0)
        ctx.state.setdefault('commit_count', 0)

    def evaluate(self, ctx: ModuleContext) -> None:
        opening = _number(ctx.parameter('opening_ratio'))
        exponent = _number(ctx.parameter('characteristic_exponent'))
        effective = opening ** exponent
        density = ctx.port('in0').density_kg_m3
        if density is None or density <= 0:
            raise ValueError('入口液体密度必须为正')
        ctx.net.valve(channel='main', kv=_number(ctx.parameter('kv_m3_h')),
                      opening=effective, density_kg_m3=density)
        ctx.var('effective_opening_ratio', effective)
        ctx.var('density_kg_m3', density)

    def commit_step(self, ctx: ModuleContext, dt_s: float) -> None:
        # Discrete author bookkeeping uses the accepted segment END flow.
        # The host separately integrates state.transferred_mass_kg from all true
        # accepted integration substeps, including adaptive half-steps.
        ctx.state['throughput_kg'] = _number(ctx.state.get('throughput_kg', 0.0)) + abs(ctx.channel('main').mass_flow_kg_s) * dt_s
        count = ctx.state.get('commit_count', 0)
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError('接受段计数必须是整数')
        ctx.state['commit_count'] = count + 1

    def finalize(self, ctx: ModuleContext) -> None:
        pass


def typed_module() -> DeviceModule:
    return Module()
