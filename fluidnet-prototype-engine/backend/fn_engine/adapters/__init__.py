"""Business-neutral access to versioned FluidNet calculations."""
from .contracts import AdapterError, AdapterModel, AdapterRequest, AdapterResult
from .registry import AdapterDefinition, AdapterRegistry
from .units import UnitRule


def default_registry() -> AdapterRegistry:
    # Lazy import keeps the registry usable for third-party adapters without loading solvers/EOS.
    from .builtins import definitions
    return AdapterRegistry(definitions())


__all__ = ['AdapterDefinition', 'AdapterError', 'AdapterModel', 'AdapterRegistry', 'AdapterRequest',
           'AdapterResult', 'UnitRule', 'default_registry']
