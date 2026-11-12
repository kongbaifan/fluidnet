"""Unit-aware host-owned physical coordinates shared by native and author devices."""
from dataclasses import dataclass
import math

from .compiler import CompilationError


@dataclass(frozen=True)
class StateCoordinate:
    key: str
    instance_id: str
    name: str
    quantity: str
    unit: str
    initial: float
    scale: float
    medium: str = ''
    ledger: bool = False
    minimum: float | None = None
    maximum: float | None = None


class PhysicalStateSpace:
    def __init__(self):
        self.coordinates = {}

    def add(self, iid, name, quantity, initial, *, medium='', ledger=False, minimum=None, maximum=None, scale=None):
        key = f'{iid}::{name}'
        units = {'mass': 'kg', 'energy': 'J', 'temperature': 'K', 'ratio': '1'}
        if key in self.coordinates or quantity not in units or not math.isfinite(initial):
            raise CompilationError('PHYSICAL_STATE_INVALID', '物理状态重复、量纲不支持或初值非有限', iid, name)
        if scale is None:
            scale = max(abs(initial), 1.) if quantity == 'mass' else max(abs(initial), 1e5) if quantity == 'energy' else 1.
        if not math.isfinite(scale) or scale <= 0.:
            raise CompilationError('PHYSICAL_STATE_INVALID', '物理状态归一化尺度必须为有限正数', iid, name)
        self.coordinates[key] = StateCoordinate(key, iid, name, quantity, units[quantity], float(initial), float(scale),
                                                 medium, ledger, minimum, maximum)
        return key

    def initial_values(self):
        return {key: coordinate.initial for key, coordinate in self.coordinates.items()}

    def validate(self, values):
        if set(values) != set(self.coordinates):
            raise ValueError('Physical state keys do not match their declared coordinates')
        for key, value in values.items():
            c = self.coordinates[key]
            if not math.isfinite(value) or c.minimum is not None and value < c.minimum or c.maximum is not None and value > c.maximum:
                from .refrigeration.cycle import DeviceRangeError
                raise DeviceRangeError('PHYSICAL_STATE_RANGE', f'{c.instance_id}.{c.name} 超出物理状态范围', c.instance_id)

    def energy(self, values):
        return sum(values[key] for key, c in self.coordinates.items() if key in values and c.quantity == 'energy' and not c.ledger)

    def mass(self, values, medium):
        return sum(values[key] for key, c in self.coordinates.items() if key in values and c.quantity == 'mass' and c.medium == medium and not c.ledger)

    def variables(self, values):
        return {f'{c.instance_id}.state.{c.name}': values[key] for key, c in self.coordinates.items()}
