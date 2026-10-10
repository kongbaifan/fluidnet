from __future__ import annotations


def percent_to_ratio(value: float) -> float:
    return float(value) / 100.0


def ratio_to_percent(value: float) -> float:
    return float(value) * 100.0


def kpa_to_pa(value: float) -> float:
    return float(value) * 1000.0


def pa_to_kpa(value: float) -> float:
    return float(value) / 1000.0


def celsius_to_kelvin(value: float) -> float:
    return float(value) + 273.15


def kelvin_to_celsius(value: float) -> float:
    return float(value) - 273.15


def volume_flow_m3_h_to_mass_kg_s(value: float, density_kg_m3: float = 998.2) -> float:
    return float(value) / 3600.0 * density_kg_m3


def mass_flow_kg_s_to_volume_m3_h(value: float, density_kg_m3: float = 998.2) -> float:
    return float(value) / density_kg_m3 * 3600.0
