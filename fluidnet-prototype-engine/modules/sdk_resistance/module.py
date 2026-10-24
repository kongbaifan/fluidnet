"""Unpublished typed local-resistance example; see SDK_API.md for the test contract.

Registers a K relationship and uses accepted channel flow only for accumulation.
No pressure-based flow inversion or property flash is needed.
"""
from __future__ import annotations

import math

from fn_sdk import DeviceModule, JSONValue, ModuleContext


def _number(value: JSONValue, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


class Module:
    def initialize(self, ctx: ModuleContext) -> None:
        ctx.state.setdefault('throughput_kg', 0.0)
        ctx.state.setdefault('commit_count', 0)

    def evaluate(self, ctx: ModuleContext) -> None:
        diameter = _number(ctx.parameter('diameter_m', .05), 'diameter_m')
        coefficient = _number(ctx.parameter('loss_coefficient', 8.0), 'loss_coefficient')
        heat = _number(ctx.parameter('heat_w', 0.0), 'heat_w')
        density = ctx.port('in0').density_kg_m3
        ctx.net.resistance(channel='main', diameter_m=diameter, loss_coefficient=coefficient,
                           density_kg_m3=density, heat_w=heat)
        ctx.var('loss_coefficient', coefficient)
        ctx.var('density_kg_m3', density)

    def commit_step(self, ctx: ModuleContext, dt_s: float) -> None:
        count = ctx.state.get('commit_count', 0)
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError('commit_count must be an integer')
        mass = _number(ctx.state.get('throughput_kg', 0.0), 'throughput_kg')
        ctx.state['throughput_kg'] = mass + abs(ctx.channel('main').mass_flow_kg_s) * dt_s
        ctx.state['commit_count'] = count + 1

    def finalize(self, ctx: ModuleContext) -> None:
        pass


def typed_module() -> DeviceModule:
    return Module()
