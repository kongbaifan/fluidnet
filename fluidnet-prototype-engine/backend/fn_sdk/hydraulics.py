"""Single-phase hydraulic utilities with explicit SI inputs and finite outputs.

Pressure drops are signed along the declared input -> output direction and exclude
elevation, shaft work and heat. No property service, clipping, or flow inversion.
"""
from __future__ import annotations

from collections.abc import Callable
import math

from . import _hydraulic_core as core

__all__ = ['pipe_pressure_drop_pa', 'resistance_pressure_drop_pa', 'valve_pressure_drop_pa',
           'kv_from_loss_coefficient', 'mass_flow_to_volume_flow_m3_h', 'volume_flow_m3_h_to_mass_flow_kg_s']


def _finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a finite number')
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f'{name} must be a finite number')


def _positive(name: str, value: float) -> None:
    _finite(name, value)
    if value <= 0:
        raise ValueError(f'{name} must be greater than zero')


def _nonnegative(name: str, value: float) -> None:
    _finite(name, value)
    if value < 0:
        raise ValueError(f'{name} must be nonnegative')


def _calculate(operation: Callable[[], float], *, nonzero: bool = False) -> float:
    try:
        result = operation()
    except ArithmeticError as error:
        raise ValueError('hydraulic calculation is outside the finite floating-point range') from error
    if not math.isfinite(result):
        raise ValueError('hydraulic result must be finite')
    if nonzero and result == 0:
        raise ValueError('hydraulic result underflowed to zero')
    return result


def pipe_pressure_drop_pa(*, mass_flow_kg_s: float, density_kg_m3: float, viscosity_pa_s: float,
                          length_m: float, diameter_m: float, roughness_m: float = 0.0) -> float:
    """Darcy-Weisbach/Haaland; Poiseuille at Re <= 2300, linear blend to Re = 4000."""
    _finite('mass_flow_kg_s', mass_flow_kg_s)
    for name, value in (('density_kg_m3', density_kg_m3), ('viscosity_pa_s', viscosity_pa_s),
                        ('length_m', length_m), ('diameter_m', diameter_m)):
        _positive(name, value)
    _nonnegative('roughness_m', roughness_m)
    return _calculate(lambda: core.pipe_drop(length_m, diameter_m, roughness_m, mass_flow_kg_s,
                                              density_kg_m3, viscosity_pa_s), nonzero=mass_flow_kg_s != 0)


def resistance_pressure_drop_pa(*, mass_flow_kg_s: float, density_kg_m3: float,
                                diameter_m: float, loss_coefficient: float) -> float:
    """Local loss K*m*abs(m)/(2*rho*A**2); K=0 is allowed, no hidden K floor."""
    _finite('mass_flow_kg_s', mass_flow_kg_s)
    _positive('density_kg_m3', density_kg_m3)
    _positive('diameter_m', diameter_m)
    _nonnegative('loss_coefficient', loss_coefficient)
    return _calculate(lambda: core.resistance_drop(diameter_m, loss_coefficient, mass_flow_kg_s, density_kg_m3),
                      nonzero=mass_flow_kg_s != 0 and loss_coefficient != 0)


def valve_pressure_drop_pa(*, mass_flow_kg_s: float, density_kg_m3: float, kv_m3_h: float,
                           opening_ratio: float = 1.0) -> float:
    """Kv pressure law; requires 0 < opening <= 1. Closed valves are constraints, not this law."""
    _finite('mass_flow_kg_s', mass_flow_kg_s)
    _positive('density_kg_m3', density_kg_m3)
    _positive('kv_m3_h', kv_m3_h)
    _positive('opening_ratio', opening_ratio)
    if opening_ratio > 1:
        raise ValueError('opening_ratio must not exceed one')
    return _calculate(lambda: core.valve_drop(kv_m3_h * opening_ratio, mass_flow_kg_s, density_kg_m3),
                      nonzero=mass_flow_kg_s != 0)


def kv_from_loss_coefficient(*, diameter_m: float, loss_coefficient: float) -> float:
    """Exact Kv [m^3/h] = 3600*sqrt(200)*A/sqrt(K). K=0 has no finite equivalent Kv."""
    _positive('diameter_m', diameter_m)
    _positive('loss_coefficient', loss_coefficient)
    return _calculate(lambda: 3600.0 * math.sqrt(200.0) * core.pipe_area(diameter_m) / math.sqrt(loss_coefficient),
                      nonzero=True)


def mass_flow_to_volume_flow_m3_h(*, mass_flow_kg_s: float, density_kg_m3: float) -> float:
    """Signed kg/s -> m^3/h, using the supplied positive density."""
    _finite('mass_flow_kg_s', mass_flow_kg_s)
    _positive('density_kg_m3', density_kg_m3)
    return _calculate(lambda: mass_flow_kg_s / density_kg_m3 * 3600.0, nonzero=mass_flow_kg_s != 0)


def volume_flow_m3_h_to_mass_flow_kg_s(*, volume_flow_m3_h: float, density_kg_m3: float) -> float:
    """Signed m^3/h -> kg/s, using the supplied positive density."""
    _finite('volume_flow_m3_h', volume_flow_m3_h)
    _positive('density_kg_m3', density_kg_m3)
    return _calculate(lambda: volume_flow_m3_h / 3600.0 * density_kg_m3, nonzero=volume_flow_m3_h != 0)
