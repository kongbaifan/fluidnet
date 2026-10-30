"""Lightweight structural interfaces for schema-4 refrigeration author modules."""
from typing import Protocol


class RefrigerationThrottleInput(Protocol):
    """One candidate state, SI units; rated Kv retains the m³/h coefficient convention."""

    @property
    def inlet_pressure_pa(self) -> float: ...
    @property
    def outlet_pressure_pa(self) -> float: ...
    @property
    def inlet_temperature_k(self) -> float: ...
    @property
    def inlet_enthalpy_j_kg(self) -> float: ...
    @property
    def inlet_density_kg_m3(self) -> float: ...
    @property
    def opening_ratio(self) -> float: ...
    @property
    def rated_kv_m3_h(self) -> float: ...


class RefrigerationThrottleFlow(Protocol):
    @property
    def mass_flow_kg_s(self) -> float: ...
    @property
    def effective_kv_m3_h(self) -> float: ...


class RefrigerationContext(Protocol):
    """Available only to a declared refrigeration role during evaluate."""

    @property
    def throttle(self) -> RefrigerationThrottleInput: ...

    def flow(self, *, mass_flow_kg_s: float, effective_kv_m3_h: float) -> None: ...
