"""All physics uses SI; display conversions are explicit and reversible."""

G = 9.80665


def pressure_from_gauge_kpa(value, atmosphere_pa=101325.0):
    return float(value) * 1000 + atmosphere_pa


def pressure_to_gauge_kpa(value, atmosphere_pa=101325.0):
    return (float(value) - atmosphere_pa) / 1000


def mass_to_volume_m3_h(mass_flow, density):
    if density <= 0:
        raise ValueError("密度必须大于 0")
    return mass_flow / density * 3600


def volume_to_mass_kg_s(volume_flow, density):
    if density <= 0:
        raise ValueError("密度必须大于 0")
    return volume_flow * density / 3600
