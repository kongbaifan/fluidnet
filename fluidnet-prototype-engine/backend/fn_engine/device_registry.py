"""Definition and presentation registration pilot for the five liquid storage devices.

Descriptors do not dispatch equations or decide fluid/model eligibility. Those checks
remain in their existing physical implementations. Factories are lazy so reading
presentation metadata does not import the numerical implementations.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from importlib import import_module

from .model_types.module import ModuleDefinition


@dataclass(frozen=True)
class DeviceDescriptor:
    module_id: str
    factory: Callable[[], ModuleDefinition]
    domains: tuple[str, ...]
    capabilities: tuple[str, ...]
    icon: str
    canvas_family: str

    def definition(self) -> ModuleDefinition:
        definition = self.factory()
        if definition.id != self.module_id or definition.runtime != 'builtin':
            raise ValueError(f'Device descriptor identity mismatch: {self.module_id}')
        if {p.domain.value for p in definition.ports} != set(self.domains):
            raise ValueError(f'Device descriptor port domains mismatch: {self.module_id}')
        return definition


def _definition(module: str, factory: str = 'definition') -> ModuleDefinition:
    return getattr(import_module(module, package=__package__), factory)()


STORAGE_DEVICES = (
    DeviceDescriptor('closed_buffer_tank', partial(_definition, '.buffer_tank'), ('fluid',),
                     ('thermal_storage',), 'Database', 'tank'),
    DeviceDescriptor('hydronic_buffer_tank', partial(_definition, '.buffer_tank', 'hydronic_definition'), ('fluid',),
                     ('thermal_storage', 'air_liquid_coupling'), 'Database', 'tank'),
    DeviceDescriptor('gas_expansion_tank', partial(_definition, '.expansion_tank'), ('fluid',),
                     ('mass_storage', 'pressure_reference'), 'Database', 'tank'),
    DeviceDescriptor('tower_pool', partial(_definition, '.tower_pool'), ('fluid',),
                     ('mass_storage', 'thermal_storage'), 'Database', 'tank'),
    DeviceDescriptor('coupled_tower_pool', partial(_definition, '.coupled_tower_pool'), ('fluid',),
                     ('mass_storage', 'thermal_storage', 'wet_contact'), 'Droplets', 'tank'),
)


def registered_definitions(descriptors: Iterable[DeviceDescriptor] = STORAGE_DEVICES) -> list[ModuleDefinition]:
    definitions = []
    seen = set()
    for descriptor in descriptors:
        if descriptor.module_id in seen:
            raise ValueError(f'Duplicate device descriptor: {descriptor.module_id}')
        seen.add(descriptor.module_id)
        definitions.append(descriptor.definition())
    return definitions


def presentation_catalog() -> dict:
    return {'version': 1, 'devices': [
        {'module_id': item.module_id, 'runtime': 'builtin', 'domains': item.domains,
         'capabilities': item.capabilities, 'icon': item.icon, 'canvas_family': item.canvas_family}
        for item in STORAGE_DEVICES
    ]}
