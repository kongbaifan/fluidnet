"""Stable public catalog entry points backed by the family registry."""
from .catalog_definitions import (
    _celsius as _celsius, _heat_port as _heat_port, _moist_var as _moist_var,
    _ratio as _ratio, _stream as _stream, _switch as _switch, _var as _var,
    channel as channel, number as number, ports as ports,
)
from .model_types.module import ModuleDefinition


def builtin_catalog() -> list[ModuleDefinition]:
    from .device_registry import builtin_definitions
    return builtin_definitions()


def thermal_catalog() -> list[ModuleDefinition]:
    from .device_registry import family_definitions
    return family_definitions('thermal')


def cold_store_catalog() -> list[ModuleDefinition]:
    from .device_registry import family_definitions
    return family_definitions('cold-store')


def refrigeration_catalog() -> list[ModuleDefinition]:
    from .device_registry import family_definitions
    return family_definitions('refrigeration')


def catalog_map() -> dict[str, ModuleDefinition]:
    return {module.id: module for module in builtin_catalog()}
