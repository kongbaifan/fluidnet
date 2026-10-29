"""风侧合同：物理配置与展示元数据共用明确的质量基准。"""
from typing import Literal

from pydantic import Field, model_validator

from ._module_schema_v1 import StrictModel, UnitSpec


class MoistAirOptions(StrictModel):
    contract_version: Literal[1] = 1
    property_backend: Literal['coolprop_ha'] = 'coolprop_ha'
    humidity_tolerance_kg_kg: float = Field(default=1e-8, gt=0, le=1e-3)
    max_iterations: int = Field(default=60, ge=1, le=500)
    relaxation: float = Field(default=.7, gt=0, le=1)
    moisture_atol_kg_s: float = Field(default=1e-9, gt=0)
    moisture_rtol: float = Field(default=1e-6, gt=0, le=1e-3)
    energy_atol_w: float = Field(default=1e-3, gt=0)
    energy_rtol: float = Field(default=1e-6, gt=0, le=1e-3)
    flow_zero_tolerance_kg_s: float = Field(default=1e-10, gt=0, le=1e-6)
    supersaturation_policy: Literal['error'] = 'error'


class AirVariableDescriptor(StrictModel):
    key: str
    label: str
    instance_id: str
    port_id: str | None = None
    channel_id: str | None = None
    value_type: Literal['number', 'boolean', 'text'] = 'number'
    quantity: str
    unit: UnitSpec | None = None
    mass_basis: Literal['none', 'mixture', 'dry_air', 'water'] = 'none'
    source: Literal['parameter', 'port', 'state', 'derived', 'system'] = 'derived'
    writable: bool = False
    nullable: bool = False
    available_in: list[Literal['steady', 'dynamic']] = Field(default=['steady', 'dynamic'])
    contract_version: Literal[1] = 1


class AirPropertyRequest(StrictModel):
    input_mode: Literal['ptw','ptrh','phw']
    pressure_pa: float = Field(ge=60000, le=120000)
    temperature_k: float | None = Field(default=None,ge=253.15, le=333.15)
    humidity_ratio_kg_kg: float | None = Field(default=None, ge=0, le=.05)
    relative_humidity: float | None = Field(default=None, ge=0, le=1)
    enthalpy_j_kg_dry_air: float | None = None

    @model_validator(mode='after')
    def inputs_match_mode(self):
        expected={'ptw':{'temperature_k','humidity_ratio_kg_kg'},'ptrh':{'temperature_k','relative_humidity'},
                  'phw':{'enthalpy_j_kg_dry_air','humidity_ratio_kg_kg'}}[self.input_mode]
        actual={name for name in ('temperature_k','humidity_ratio_kg_kg','relative_humidity','enthalpy_j_kg_dry_air')
                if getattr(self,name) is not None}
        if actual != expected:
            raise ValueError(f'{self.input_mode} 必须且只能提供 {sorted(expected)}')
        return self


class AirGridRequest(StrictModel):
    pressure_pa: float = Field(default=101325, ge=60000, le=120000)
    temperature_min_k: float = Field(default=273.15, ge=253.15, le=333.15)
    temperature_max_k: float = Field(default=323.15, ge=253.15, le=333.15)
    points: int = Field(default=41, ge=2, le=101)
    humidity_max_kg_kg: float = Field(default=.03,gt=0,le=.05)


class PsychrometricPoint(StrictModel):
    temperature_k: float
    humidity_ratio_kg_kg: float


class PsychrometricLine(StrictModel):
    relative_humidity: float
    segments: list[list[PsychrometricPoint]]
