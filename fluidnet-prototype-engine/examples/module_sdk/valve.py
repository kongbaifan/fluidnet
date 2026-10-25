"""Typed valve for the existing v1 programmable_valve contract.

Used as source in isolated tests; this file is not a new published module version.
All pressures are absolute Pa; Kv uses m^3/h, opening is a ratio, flow is kg/s.
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
        opening = _number(ctx.parameter('opening_ratio'), 'opening_ratio')
        kv = _number(ctx.parameter('kv_m3_h'), 'kv_m3_h')
        rho = ctx.port('in0').density_kg_m3
        if rho is None or rho <= 0:
            raise ValueError('inlet density must be provided by the host')
        ctx.net.valve(channel='main', kv=kv, opening=opening, density_kg_m3=rho)
        ctx.var('opening_ratio', opening)
        ctx.var('density_kg_m3', rho)

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
    """Static conformance check for all four callback signatures."""
    return Module()
