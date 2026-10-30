"""Typed, finite SI messages for an isenthalpic refrigeration throttle."""
from pydantic import ConfigDict, Field

from ._module_schema_v1 import StrictModel


class RefrigerationThrottleInput(StrictModel):
    model_config = ConfigDict(frozen=True,extra='forbid',allow_inf_nan=False)
    inlet_pressure_pa: float = Field(gt=0,strict=True)
    outlet_pressure_pa: float = Field(gt=0,strict=True)
    inlet_temperature_k: float = Field(gt=0,strict=True)
    inlet_enthalpy_j_kg: float = Field(strict=True)
    inlet_density_kg_m3: float = Field(gt=0,strict=True)
    opening_ratio: float = Field(ge=0,le=1,strict=True)
    rated_kv_m3_h: float = Field(gt=0,strict=True)


class RefrigerationThrottleFlow(StrictModel):
    model_config = ConfigDict(frozen=True,extra='forbid',allow_inf_nan=False)
    mass_flow_kg_s: float = Field(ge=0,strict=True)
    effective_kv_m3_h: float = Field(ge=0,strict=True)
