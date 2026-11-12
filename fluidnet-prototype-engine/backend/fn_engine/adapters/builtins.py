"""Initial capabilities span hydraulics, heat transfer, properties, networks and module design."""
from typing import Literal

from pydantic import Field

from fn_sdk import heat_exchanger_effectiveness
from ..air_models import AirPropertyRequest
from ..model_types.base import FluidConfig, FluidState
from ..model_types.domain import Project
from ..model_types.http import ValidationResponse
from ..model_types.module_testing import ModuleDesignRequest, ModuleDesignResponse
from ..model_types.run import RunFrame
from .contracts import AdapterError, AdapterModel
from .hydraulics import definitions as hydraulic_definitions
from .hydronics import definition as hydronic_definition
from .hydronic_cases import definition as hydronic_cases_definition
from .airducts import definition as airduct_definition
from .ventilation import definition as ventilation_definition
from .registry import AdapterDefinition
from .units import UnitRule


class HeatExchangerInput(AdapterModel):
    ua: float = Field(ge=0)
    capacity_a: float = Field(ge=0)
    capacity_b: float = Field(ge=0)
    counterflow: bool = True


class EffectivenessOutput(AdapterModel):
    effectiveness: float = Field(ge=0, le=1)


class FluidStateInput(AdapterModel):
    pressure: float = Field(gt=0, description='Absolute pressure, not gauge pressure.')
    temperature: float = Field(gt=0)
    fluid: FluidConfig = Field(default_factory=FluidConfig)


class FluidStateOutput(AdapterModel):
    state: FluidState


class AirInput(AdapterModel):
    input_mode: Literal['ptw', 'ptrh', 'phw']
    pressure: float = Field(ge=60000, le=120000, description='Absolute pressure.')
    temperature: float | None = Field(default=None, ge=253.15, le=333.15)
    humidity_ratio: float | None = Field(default=None, ge=0, le=.05)
    relative_humidity: float | None = Field(default=None, ge=0, le=1)
    enthalpy_dry_air: float | None = None


class AirOutput(AdapterModel):
    pressure: float
    temperature: float
    humidity_ratio: float
    relative_humidity: float
    enthalpy_dry_air: float
    density: float
    dew_point: float | None
    wet_bulb: float


class NetworkInput(AdapterModel):
    project: Project


def exchanger(p: HeatExchangerInput) -> EffectivenessOutput:
    return EffectivenessOutput(effectiveness=heat_exchanger_effectiveness(ua_w_k=p.ua,
        capacity_a_w_k=p.capacity_a, capacity_b_w_k=p.capacity_b, counterflow=p.counterflow))


def fluid_state(p: FluidStateInput) -> FluidStateOutput:
    from ..properties import property_service
    return FluidStateOutput(state=property_service(p.fluid).state_pt(p.pressure, p.temperature))


def air_state(p: AirInput) -> AirOutput:
    from ..moist_air import MoistAirService
    # Reuse the native mode validation; only the names/units of the scalar boundary differ.
    request = AirPropertyRequest(input_mode=p.input_mode, pressure_pa=p.pressure,
        temperature_k=p.temperature, humidity_ratio_kg_kg=p.humidity_ratio,
        relative_humidity=p.relative_humidity, enthalpy_j_kg_dry_air=p.enthalpy_dry_air)
    service = MoistAirService()
    if request.input_mode == 'phw':
        state = service.state_phw(request.pressure_pa, request.enthalpy_j_kg_dry_air, request.humidity_ratio_kg_kg)
    else:
        w = service.humidity_from_rh(request.pressure_pa, request.temperature_k, request.relative_humidity) if request.input_mode == 'ptrh' else request.humidity_ratio_kg_kg
        state = service.state_ptw(request.pressure_pa, request.temperature_k, w)
    return AirOutput.model_validate(dict(pressure=state.pressure_pa, temperature=state.temperature_k,
        humidity_ratio=state.humidity_ratio_kg_kg, relative_humidity=state.relative_humidity,
        enthalpy_dry_air=state.enthalpy_j_kg_dry_air, density=state.density_kg_m3,
        dew_point=state.dew_point_k, wet_bulb=state.wet_bulb_k))


def validate_network(p: NetworkInput) -> ValidationResponse:
    from ..compiler import validate_project_details
    diagnostics, circuits = validate_project_details(p.project)
    return ValidationResponse.model_validate(dict(valid=not any(d.severity == 'error' for d in diagnostics),
                                                   diagnostics=diagnostics, circuits=circuits))


def solve_network(p: NetworkInput) -> RunFrame:
    from ..compiler import compile_project
    from ..solver import solve_steady
    frame = solve_steady(compile_project(p.project))
    if not frame.valid:
        raise AdapterError('ADAPTER_CALCULATION_FAILED', '管网未得到有效计算结果',
                           diagnostics=[d.model_dump(mode='json') for d in frame.diagnostics])
    return frame


def design_module(p: ModuleDesignRequest) -> ModuleDesignResponse:
    from ..design import run_design
    return run_design(p)


def definitions() -> list[AdapterDefinition]:
    conductance = UnitRule('conductance', 'W/K')
    pressure, temperature = UnitRule('pressure', 'Pa'), UnitRule('temperature', 'K')
    air_units = {'pressure': pressure, 'temperature': temperature,
        'humidity_ratio': UnitRule('humidity_ratio', 'kg/kg_da'),
        'relative_humidity': UnitRule('ratio', '1'), 'enthalpy_dry_air': UnitRule('dry_air_enthalpy', 'J/kg_da')}
    return hydraulic_definitions() + [
        hydronic_definition(),
        hydronic_cases_definition(),
        ventilation_definition(),
        airduct_definition(),
        AdapterDefinition('thermal.heat_exchanger_effectiveness', '单相显热换热器 ε–NTU 效率。',
            HeatExchangerInput, EffectivenessOutput, exchanger,
            input_units={key: conductance for key in ('ua', 'capacity_a', 'capacity_b')},
            output_units={'effectiveness': UnitRule('ratio', '1')}),
        AdapterDefinition('properties.fluid_state_pt', '指定工质的压力温度物性；嵌套 state 保持原生 SI 合同。',
            FluidStateInput, FluidStateOutput, fluid_state, input_units={'pressure': pressure, 'temperature': temperature}),
        AdapterDefinition('properties.moist_air', '湿空气物性；焓与含湿量采用干空气质量基准。',
            AirInput, AirOutput, air_state, input_units=air_units,
            output_units=air_units | {'density': UnitRule('density', 'kg/m3'), 'dew_point': temperature, 'wet_bulb': temperature}),
        AdapterDefinition('network.validate', '检查原生 Project；outputs.valid=false 表示项目存在问题，未执行稳态求解。',
            NetworkInput, ValidationResponse, validate_network),
        AdapterDefinition('network.solve_steady', '原生 Project 稳态计算；输出原生 RunFrame，不创建运行记录。',
            NetworkInput, RunFrame, solve_network),
        AdapterDefinition('modules.design', '原生模块设计请求，Worker 执行后返回参数建议；不保存或应用结果。',
            ModuleDesignRequest, ModuleDesignResponse, design_module),
    ]
