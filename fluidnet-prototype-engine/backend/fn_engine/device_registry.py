"""Family registration for every built-in definition and its separate UI metadata.

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


def _validate(definition: ModuleDefinition, item: DeviceDescriptor | DeviceMetadata) -> ModuleDefinition:
    if definition.id != item.module_id or definition.runtime != 'builtin':
        raise ValueError(f'Device descriptor identity mismatch: {item.module_id}')
    if {p.domain.value for p in definition.ports} != set(item.domains):
        raise ValueError(f'Device descriptor port domains mismatch: {item.module_id}')
    return definition


@dataclass(frozen=True)
class DeviceDescriptor:
    module_id: str
    factory: Callable[[], ModuleDefinition]
    domains: tuple[str, ...]
    capabilities: tuple[str, ...]
    icon: str
    canvas_family: str

    def definition(self) -> ModuleDefinition:
        return _validate(self.factory(), self)


@dataclass(frozen=True)
class DeviceMetadata:
    module_id: str
    icon: str
    canvas_family: str
    domains: tuple[str, ...] = ('fluid',)
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeviceFamily:
    name: str
    factory: Callable[[], list[ModuleDefinition]]
    members: tuple[DeviceMetadata | DeviceDescriptor, ...]

    def definitions(self) -> list[ModuleDefinition]:
        definitions = self.factory()
        expected = [item.module_id for item in self.members]
        if len(set(expected)) != len(expected):
            raise ValueError(f'Duplicate device descriptor in family: {self.name}')
        if [definition.id for definition in definitions] != expected:
            raise ValueError(f'Device family membership or order mismatch: {self.name}')
        return [_validate(definition, item) for definition, item in zip(definitions, self.members)]


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


def _process_definitions():
    from .refrigeration.process_devices import definitions
    return definitions()


def _network_definitions() -> list[ModuleDefinition]:
    from .refrigeration.network_devices import definitions
    return definitions()


def _family_definitions(factory: str) -> list[ModuleDefinition]:
    return getattr(import_module('.catalog_definitions', package=__package__), factory)()


# Order is part of the existing catalog contract. Factories build each family once
# per call; no mutable ModuleDefinition is cached between requests or projects.
BUILTIN_FAMILIES = (
    DeviceFamily('fluid', partial(_family_definitions, 'fluid_definitions'), (
        DeviceMetadata('source', 'Droplets', 'source'),
        DeviceMetadata('junction', 'Waypoints', 'junction'),
        DeviceMetadata('pump', 'Triangle', 'pump'),
        DeviceMetadata('valve', 'SlidersHorizontal', 'valve'),
        DeviceMetadata('pipe', 'Minus', 'pipe'),
        DeviceMetadata('duct', 'Wind', 'pipe'),
        DeviceMetadata('cooling_coil', 'Snowflake', 'coil'),
        DeviceMetadata('humidifier', 'Droplets', 'module'),
        DeviceMetadata('exchanger', 'ArrowRightLeft', 'exchanger'),
        DeviceMetadata('tank', 'Database', 'tank'),
        DeviceMetadata('closed_volume', 'Database', 'module'),
        DeviceMetadata('heater', 'Flame', 'heater'),
    )),
    DeviceFamily('hvac', partial(_family_definitions, 'hvac_definitions'), (
        DeviceMetadata('air_mixing_box', 'GitMerge', 'header'),
        DeviceMetadata('air_filter', 'Filter', 'filter'),
        DeviceMetadata('air_room', 'Home', 'room'),
        DeviceMetadata('cooling_tower_moist', 'Wind', 'tower'),
        DeviceMetadata('water_coil', 'Snowflake', 'coil'),
        DeviceMetadata('water_chiller', 'Snowflake', 'chiller'),
        DeviceMetadata('air_cooled_chiller', 'Snowflake', 'chiller'),
        DeviceMetadata('air_source_heat_pump', 'Flame', 'heat-pump'),
        DeviceMetadata('enthalpy_recovery', 'ArrowRightLeft', 'exchanger'),
    )),
    DeviceFamily('storage', registered_definitions, STORAGE_DEVICES),
    DeviceFamily('thermal', partial(_family_definitions, 'thermal_catalog'), (
        DeviceMetadata('cold_room', 'Home', 'room', ('thermal',)),
        DeviceMetadata('ideal_cold_source', 'Snowflake', 'module', ('thermal',)),
    )),
    DeviceFamily('cold-store', partial(_family_definitions, 'cold_store_catalog'), (
        DeviceMetadata('storage_room', 'Home', 'room', ('thermal',)),
        DeviceMetadata('unit_cooler', 'Snowflake', 'module', ('thermal',)),
        DeviceMetadata('condensing_unit', 'Gauge', 'compressor', ('thermal',)),
    )),
    DeviceFamily('refrigeration', partial(_family_definitions, 'refrigeration_catalog'), (
        DeviceMetadata('hp_receiver', 'Database', 'tank', ('refrigerant',)),
        DeviceMetadata('lp_drum', 'Database', 'tank', ('refrigerant',)),
        DeviceMetadata('pumped_drum', 'Database', 'tank', ('refrigerant',)),
        DeviceMetadata('hp_receiver_multi', 'Database', 'tank', ('refrigerant',)),
        DeviceMetadata('lp_drum_multi', 'Database', 'tank', ('refrigerant',)),
        DeviceMetadata('horizontal_receiver', 'Database', 'horizontal-tank', ('refrigerant',)),
        DeviceMetadata('horizontal_drum', 'Database', 'horizontal-tank', ('refrigerant',)),
        DeviceMetadata('headed_receiver', 'Database', 'horizontal-tank', ('refrigerant',)),
        DeviceMetadata('refrigerant_compressor', 'Gauge', 'compressor', ('refrigerant',)),
        DeviceMetadata('evaporative_condenser', 'Wind', 'condenser', ('refrigerant',)),
        DeviceMetadata('air_cooled_condenser', 'Wind', 'condenser', ('refrigerant',)),
        DeviceMetadata('expansion_valve', 'SlidersHorizontal', 'valve', ('refrigerant',)),
        DeviceMetadata('cascade_exchanger', 'ArrowRightLeft', 'exchanger', ('refrigerant',)),
        DeviceMetadata('refrigerant_pump', 'Gauge', 'pump', ('refrigerant',)),
        DeviceMetadata('air_cooler', 'Snowflake', 'coil', ('refrigerant', 'thermal')),
        DeviceMetadata('refrigerant_header', 'GitMerge', 'header', ('refrigerant',)),
        DeviceMetadata('performance_compressor', 'Gauge', 'compressor', ('refrigerant',)),
        DeviceMetadata('cold_room_multi', 'Home', 'room', ('thermal',)),
        DeviceMetadata('defrost_air_cooler', 'Snowflake', 'coil', ('refrigerant', 'thermal')),
        DeviceMetadata('refrigerant_line', 'Minus', 'pipe', ('refrigerant',)),
        DeviceMetadata('enthalpy_compressor', 'Gauge', 'compressor', ('refrigerant',)),
        DeviceMetadata('enthalpy_valve', 'SlidersHorizontal', 'valve', ('refrigerant',)),
        DeviceMetadata('refrigerant_subcooler', 'Snowflake', 'exchanger', ('refrigerant',)),
        DeviceMetadata('refrigerant_recuperator', 'ArrowRightLeft', 'exchanger', ('refrigerant',)),
        DeviceMetadata('immersed_tube_bundle', 'ArrowRightLeft', 'exchanger', ('refrigerant',)),
        DeviceMetadata('dx_expansion_valve', 'SlidersHorizontal', 'valve', ('refrigerant',)),
        DeviceMetadata('dx_evaporator', 'Snowflake', 'coil', ('refrigerant', 'thermal')),
        DeviceMetadata('dx_compressor', 'Gauge', 'compressor', ('refrigerant',)),
        DeviceMetadata('room_heat_manifold', 'GitMerge', 'header', ('thermal',)),
    )),
    DeviceFamily('cold-process', _process_definitions, (
        DeviceMetadata('logistics_cold_room', 'Home', 'room', ('thermal',)),
        DeviceMetadata('frost_hotgas_cooler', 'Snowflake', 'coil', ('refrigerant', 'thermal')),
        DeviceMetadata('compressor_oil_system', 'Filter', 'filter', ('refrigerant',)),
    )),
    DeviceFamily('refrigeration-network', _network_definitions, (
        DeviceMetadata('refrigerant_network_pipe', 'Minus', 'pipe', ('refrigerant',)),
        DeviceMetadata('refrigerant_curve_pump', 'Gauge', 'pump', ('refrigerant',)),
        DeviceMetadata('network_air_cooler', 'Snowflake', 'coil', ('refrigerant', 'thermal')),
        DeviceMetadata('refrigerant_network_valve', 'SlidersHorizontal', 'valve', ('refrigerant',)),
        DeviceMetadata('refrigerant_inventory_cell', 'Database', 'tank', ('refrigerant',)),
        DeviceMetadata('refrigerant_check_valve', 'ArrowRight', 'check', ('refrigerant',)),
        DeviceMetadata('refrigerant_strainer', 'Filter', 'filter', ('refrigerant',)),
    )),
)


def family_definitions(name: str) -> list[ModuleDefinition]:
    for family in BUILTIN_FAMILIES:
        if family.name == name:
            return family.definitions()
    raise ValueError(f'Unknown device family: {name}')


def _members() -> list[DeviceDescriptor | DeviceMetadata]:
    names: set[str] = set()
    ids: set[str] = set()
    members: list[DeviceDescriptor | DeviceMetadata] = []
    for family in BUILTIN_FAMILIES:
        if family.name in names:
            raise ValueError(f'Duplicate device family: {family.name}')
        names.add(family.name)
        for item in family.members:
            if item.module_id in ids:
                raise ValueError(f'Duplicate device descriptor: {item.module_id}')
            ids.add(item.module_id)
            members.append(item)
    return members


def builtin_definitions() -> list[ModuleDefinition]:
    _members()
    return [definition for family in BUILTIN_FAMILIES for definition in family.definitions()]


def presentation_catalog() -> dict:
    return {'version': 1, 'devices': [
        {'module_id': item.module_id, 'runtime': 'builtin', 'domains': item.domains,
         'capabilities': item.capabilities, 'icon': item.icon, 'canvas_family': item.canvas_family}
        for item in _members()
    ]}
