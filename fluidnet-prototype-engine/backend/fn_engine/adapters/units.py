"""Explicit scalar conversions. No unit guessing, density inference or gauge-pressure conversion."""
from dataclasses import dataclass
import math

from .contracts import UnitDescription

# (scale, offset) maps each unit to its quantity's reference unit.
_UNITS = {
    'length': {'m': (1., 0.), 'mm': (.001, 0.), 'cm': (.01, 0.)},
    'pressure': {'Pa': (1., 0.), 'kPa': (1000., 0.), 'MPa': (1e6, 0.), 'bar': (1e5, 0.)},
    'temperature': {'K': (1., 0.), 'degC': (1., 273.15), '°C': (1., 273.15),
                    'degF': (5/9, 273.15-32*5/9), '°F': (5/9, 273.15-32*5/9)},
    'temperature_difference': {'K': (1., 0.), 'delta_degC': (1., 0.), 'delta_degF': (5/9, 0.)},
    'mass_flow': {'kg/s': (1., 0.), 'kg/h': (1/3600, 0.), 'g/s': (.001, 0.)},
    'volume_flow': {'m3/s': (1., 0.), 'm3/h': (1/3600, 0.), 'L/s': (.001, 0.), 'L/min': (1/60000, 0.)},
    'density': {'kg/m3': (1., 0.), 'g/cm3': (1000., 0.)},
    'dynamic_viscosity': {'Pa.s': (1., 0.), 'mPa.s': (.001, 0.), 'cP': (.001, 0.)},
    'power': {'W': (1., 0.), 'kW': (1000., 0.)},
    'conductance': {'W/K': (1., 0.), 'kW/K': (1000., 0.)},
    'ratio': {'1': (1., 0.), '%': (.01, 0.)},
    'humidity_ratio': {'kg/kg_da': (1., 0.), 'g/kg_da': (.001, 0.)},
    'dry_air_enthalpy': {'J/kg_da': (1., 0.), 'kJ/kg_da': (1000., 0.)},
    'kv': {'m3/h': (1., 0.)},
}


@dataclass(frozen=True)
class UnitRule:
    quantity: str
    canonical_unit: str

    def __post_init__(self):
        if self.quantity not in _UNITS or self.canonical_unit not in _UNITS[self.quantity]:
            raise ValueError(f'Unknown canonical unit: {self.quantity}/{self.canonical_unit}')

    def describe(self) -> UnitDescription:
        return UnitDescription(quantity=self.quantity, canonical_unit=self.canonical_unit,
                               accepted_units=list(_UNITS[self.quantity]))

    def check(self, unit: str) -> None:
        if unit not in _UNITS[self.quantity]:
            raise ValueError(f'{self.quantity} 不支持单位 {unit!r}；可用：{", ".join(_UNITS[self.quantity])}')

    def convert(self, value: object, source: str, target: str) -> float:
        self.check(source)
        self.check(target)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('单位转换要求有限数值，不能使用字符串或布尔值')
        try:
            a, b = _UNITS[self.quantity][source]
            c, d = _UNITS[self.quantity][target]
            result = (value*a + b - d)/c
            if not math.isfinite(value) or not math.isfinite(result):
                raise ValueError('单位转换输入和结果必须为有限数值')
        except OverflowError as error:
            raise ValueError('单位转换超出数值范围') from error
        return result
