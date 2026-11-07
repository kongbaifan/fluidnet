"""Directional single-phase reducer losses, referenced to the smaller bore velocity."""
from __future__ import annotations

import math


def geometry(parameters, forward=True):
    """Common engineering minor-loss correlations; no static-pressure recovery or wall friction."""
    inlet = float(parameters['inlet_diameter_m'])
    outlet = float(parameters['outlet_diameter_m'])
    length = float(parameters['transition_length_m'])
    scale = float(parameters['loss_multiplier'])
    if not all(math.isfinite(value) for value in (inlet, outlet, length, scale)):
        raise ValueError('异径管尺寸和阻力倍率必须为有限数值')
    if min(inlet, outlet) <= 0 or length < 0 or scale <= 0:
        raise ValueError('两端管径和阻力倍率必须为正，过渡长度不能为负')
    profile = parameters['profile']
    if profile not in ('gradual', 'sudden'):
        raise ValueError('过渡形式只能为 gradual（渐变）或 sudden（突变）')
    if profile == 'gradual' and length <= 0:
        raise ValueError('渐变异径管的过渡长度必须大于零')
    small, large = min(inlet, outlet), max(inlet, outlet)
    area_ratio = (small / large) ** 2
    angle = 2 * math.atan2(large - small, 2 * length) if profile == 'gradual' else math.pi
    upstream, downstream = (inlet, outlet) if forward else (outlet, inlet)
    contraction = upstream > downstream
    if inlet == outlet:
        coefficient = 0.0
    elif contraction:
        sine = math.sin(angle / 2)
        coefficient = ((0.8 * sine) if angle <= math.pi / 4 else (0.5 * math.sqrt(sine))) * (1 - area_ratio)
    else:
        factor = 2.6 * math.sin(angle / 2) if angle <= math.pi / 4 else 1.0
        coefficient = factor * (1 - area_ratio) ** 2
    return small, coefficient * scale, area_ratio, math.degrees(angle), contraction


class Module:
    def initialize(self, ctx):
        geometry(ctx.parameters)
        ctx.state.setdefault('throughput_kg', 0.0)

    def evaluate(self, ctx):
        inlet, outlet = ctx.port('in0'), ctx.port('out0')
        forward = (inlet.pressure_pa or 0.0) >= (outlet.pressure_pa or 0.0)
        diameter, coefficient, ratio, angle, contraction = geometry(ctx.parameters, forward)
        densities = [p.density_kg_m3 for p in (inlet, outlet) if p.density_kg_m3 is not None]
        if not densities or any(not math.isfinite(value) or value <= 0 for value in densities):
            raise ValueError('异径管端口必须提供有效单相密度')
        density = sum(densities) / len(densities)
        ctx.net.resistance(channel='main', diameter_m=diameter,
                           loss_coefficient=coefficient, density_kg_m3=density)
        ctx.var('loss_coefficient', coefficient)
        ctx.var('area_ratio', ratio)
        ctx.var('included_angle_deg', angle)
        ctx.var('is_contraction', int(contraction and ratio < 1))

    def observe(self, ctx):
        channel = ctx.channel('main')
        flow = channel.mass_flow_kg_s
        for port_id, diameter_key, variable in (
            ('in0', 'inlet_diameter_m', 'inlet_velocity_m_s'),
            ('out0', 'outlet_diameter_m', 'outlet_velocity_m_s'),
        ):
            density = ctx.port(port_id).density_kg_m3
            area = math.pi * ctx.parameters[diameter_key] ** 2 / 4
            ctx.var(variable, flow / (density * area))
        ctx.var('pressure_loss_pa', channel.pressure_drop_pa)

    def commit_step(self, ctx, dt_s):
        ctx.state['throughput_kg'] += abs(ctx.channel('main').mass_flow_kg_s) * dt_s

    def finalize(self, ctx):
        pass
