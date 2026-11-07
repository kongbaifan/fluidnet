"""Base contracts; wire fields and validation preserve the legacy model semantics."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .._module_schema_v1 import Identifier, StrictModel


class FluidConfig(StrictModel):
    """Serializable fluid selection passed to the property service."""

    backend: Literal["coolprop"] = "coolprop"
    fluid: str = "Water"
    composition: dict[str, float] = Field(default_factory=dict)
    reference: Literal["mass", "mole"] = "mass"
    # "any" lets module code query two-phase states; network flow still requires single phase.
    phase_policy: Literal["single_phase", "liquid", "gas", "any"] = "single_phase"

    @model_validator(mode="after")
    def validate_composition(self):
        if any(not isinstance(value, (int, float)) or value < 0 for value in self.composition.values()):
            raise ValueError("工质组分必须是非负数")
        if self.composition:
            total = sum(self.composition.values())
            if total <= 0 or abs(total - 1.0) > 1e-8:
                raise ValueError("工质组分比例之和必须为 1")
        return self


class ModulePackageRef(StrictModel):
    module_id: Identifier
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    definition_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")


class FluidState(StrictModel):
    pressure_pa: float
    temperature_k: float
    enthalpy_j_kg: float
    density_kg_m3: float
    # Transport properties are undefined for a two-phase mixture and stay None there.
    viscosity_pa_s: float | None = None
    specific_heat_j_kg_k: float | None = None
    thermal_conductivity_w_m_k: float | None = None
    # Caloric extras for module code (isentropic compression etc.); speed of sound is None in two-phase.
    entropy_j_kg_k: float | None = None
    internal_energy_j_kg: float | None = None
    cv_j_kg_k: float | None = None
    speed_of_sound_m_s: float | None = None
    phase: str = "unknown"
    quality: float | None = None
    # Moist-air mode only: kg water / kg dry air at this node or port.
    humidity_ratio_kg_kg: float | None = Field(default=None, exclude_if=lambda v: v is None)
    relative_humidity: float | None = Field(default=None, exclude_if=lambda v: v is None)
    enthalpy_j_kg_dry_air: float | None = Field(default=None, exclude_if=lambda v: v is None)
    specific_heat_j_kg_dry_air_k: float | None = Field(default=None, exclude_if=lambda v: v is None)
    dew_point_k: float | None = Field(default=None, exclude_if=lambda v: v is None)
    wet_bulb_k: float | None = Field(default=None, exclude_if=lambda v: v is None)
    composition: dict[str, float] = Field(default_factory=dict)


class PortState(StrictModel):
    pressure_pa: float | None = None
    temperature_k: float | None = None
    enthalpy_j_kg: float | None = None
    density_kg_m3: float | None = None
    viscosity_pa_s: float | None = None
    specific_heat_j_kg_k: float | None = None
    mass_flow_kg_s: float | None = None
    dry_air_mass_flow_kg_s: float | None = Field(default=None, exclude_if=lambda v: v is None)
    water_vapor_mass_flow_kg_s: float | None = Field(default=None, exclude_if=lambda v: v is None)
    quality: float | None = None
    humidity_ratio_kg_kg: float | None = Field(default=None, exclude_if=lambda v: v is None)
    relative_humidity: float | None = Field(default=None, exclude_if=lambda v: v is None)
    enthalpy_j_kg_dry_air: float | None = Field(default=None, exclude_if=lambda v: v is None)
    specific_heat_j_kg_dry_air_k: float | None = Field(default=None, exclude_if=lambda v: v is None)
    dew_point_k: float | None = Field(default=None, exclude_if=lambda v: v is None)
    wet_bulb_k: float | None = Field(default=None, exclude_if=lambda v: v is None)
    composition: dict[str, float] = Field(default_factory=dict)


class ChannelState(StrictModel):
    dry_air_mass_flow_kg_s: float | None = Field(default=None, exclude_if=lambda v: v is None)
    inlet_mass_flow_kg_s: float | None = Field(default=None, exclude_if=lambda v: v is None)
    outlet_mass_flow_kg_s: float | None = Field(default=None, exclude_if=lambda v: v is None)
    mass_flow_kg_s: float = 0.0
    pressure_drop_pa: float = 0.0
    heat_w: float = Field(default=0.0, exclude_if=lambda value: value == 0)


class Diagnostic(StrictModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "error"
    instance_id: str | None = None
    field: str | None = None
    module_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    module_version: int | None = Field(default=None, exclude_if=lambda value: value is None)
    phase: str | None = Field(default=None, exclude_if=lambda value: value is None)
    time_s: float | None = Field(default=None, exclude_if=lambda value: value is None)
    source_file: str | None = Field(default=None, exclude_if=lambda value: value is None)
    source_line: int | None = Field(default=None, exclude_if=lambda value: value is None)
    channel_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    source_path: str | None = Field(default=None, exclude_if=lambda value: value is None)
    occurrences: int = Field(default=1, ge=1, exclude_if=lambda value: value == 1)
    first_time_s: float | None = Field(default=None, exclude_if=lambda value: value is None)
    last_time_s: float | None = Field(default=None, exclude_if=lambda value: value is None)
