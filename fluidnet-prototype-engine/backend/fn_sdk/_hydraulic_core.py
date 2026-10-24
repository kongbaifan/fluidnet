"""Trusted scalar arithmetic shared by the engine and checked public helpers.

Internal to this jointly shipped project. Preserve the historical operation order;
the solver has already validated its inputs and must not repeat public checks per residual.
"""
from __future__ import annotations

import math


def pipe_area(diameter: float) -> float:
    return math.pi * diameter ** 2 / 4


def haaland_friction(roughness: float, diameter: float, reynolds: float) -> float:
    return (-1.8 * math.log10((roughness / diameter / 3.7) ** 1.11 + 6.9 / reynolds)) ** -2


def pipe_terms(length: float, diameter: float, density: float, viscosity: float) -> tuple[float, float, float, float]:
    area = pipe_area(diameter)
    return length, diameter, area, 32 * viscosity * length / (density * area * diameter ** 2)


def pipe_drop(length: float, diameter: float, roughness: float, flow: float, density: float, viscosity: float) -> float:
    length, diameter, area, coef = pipe_terms(length, diameter, density, viscosity)
    reynolds = abs(flow) * diameter / (viscosity * area)
    laminar = coef * flow
    if reynolds <= 2300:
        return laminar
    friction = haaland_friction(roughness, diameter, reynolds)
    turbulent = friction * length / diameter * flow * abs(flow) / (2 * density * area ** 2)
    blend = min(1., (reynolds - 2300) / 1700)
    return laminar * (1 - blend) + turbulent * blend


def valve_drop(effective_kv: float, flow: float, density: float) -> float:
    volume = flow / density * 3600
    return 100000 * (density / 1000) * volume * abs(volume) / effective_kv ** 2


def resistance_drop(diameter: float, coefficient: float, flow: float, density: float) -> float:
    area = pipe_area(diameter)
    return coefficient * flow * abs(flow) / (2 * density * area ** 2)
