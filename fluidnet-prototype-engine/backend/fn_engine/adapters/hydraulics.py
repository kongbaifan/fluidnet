"""Scalar adapters delegate all physics to the public fn_sdk helpers."""
from pydantic import Field

from fn_sdk import (
    kv_from_loss_coefficient, mass_flow_to_volume_flow_m3_h, pipe_pressure_drop_pa,
    resistance_pressure_drop_pa, valve_pressure_drop_pa, volume_flow_m3_h_to_mass_flow_kg_s,
)

from .contracts import AdapterModel
from .registry import AdapterDefinition
from .units import UnitRule


class MassFlowInput(AdapterModel):
    mass_flow: float
    density: float = Field(gt=0)


class PipeInput(MassFlowInput):
    viscosity: float = Field(gt=0)
    length: float = Field(gt=0)
    diameter: float = Field(gt=0)
    roughness: float = Field(default=0., ge=0)


class LocalLossInput(MassFlowInput):
    diameter: float = Field(gt=0)
    loss_coefficient: float = Field(ge=0)


class ValveInput(MassFlowInput):
    kv: float = Field(gt=0)
    opening: float = Field(default=1., gt=0, le=1)


class KvInput(AdapterModel):
    diameter: float = Field(gt=0)
    loss_coefficient: float = Field(gt=0)


class VolumeFlowInput(AdapterModel):
    volume_flow: float
    density: float = Field(gt=0)


class PressureDropOutput(AdapterModel):
    pressure_drop: float


class KvOutput(AdapterModel):
    kv: float


class VolumeFlowOutput(AdapterModel):
    volume_flow: float


class MassFlowOutput(AdapterModel):
    mass_flow: float


def pipe(p: PipeInput) -> PressureDropOutput:
    return PressureDropOutput(pressure_drop=pipe_pressure_drop_pa(mass_flow_kg_s=p.mass_flow,
        density_kg_m3=p.density, viscosity_pa_s=p.viscosity, length_m=p.length,
        diameter_m=p.diameter, roughness_m=p.roughness))


def local(p: LocalLossInput) -> PressureDropOutput:
    return PressureDropOutput(pressure_drop=resistance_pressure_drop_pa(mass_flow_kg_s=p.mass_flow,
        density_kg_m3=p.density, diameter_m=p.diameter, loss_coefficient=p.loss_coefficient))


def valve(p: ValveInput) -> PressureDropOutput:
    return PressureDropOutput(pressure_drop=valve_pressure_drop_pa(mass_flow_kg_s=p.mass_flow,
        density_kg_m3=p.density, kv_m3_h=p.kv, opening_ratio=p.opening))


def kv(p: KvInput) -> KvOutput:
    return KvOutput(kv=kv_from_loss_coefficient(diameter_m=p.diameter, loss_coefficient=p.loss_coefficient))


def volume(p: MassFlowInput) -> VolumeFlowOutput:
    return VolumeFlowOutput(volume_flow=mass_flow_to_volume_flow_m3_h(mass_flow_kg_s=p.mass_flow, density_kg_m3=p.density))


def mass(p: VolumeFlowInput) -> MassFlowOutput:
    return MassFlowOutput(mass_flow=volume_flow_m3_h_to_mass_flow_kg_s(volume_flow_m3_h=p.volume_flow, density_kg_m3=p.density))


def definitions() -> list[AdapterDefinition]:
    length = UnitRule('length', 'm')
    flow = {'mass_flow': UnitRule('mass_flow', 'kg/s'), 'density': UnitRule('density', 'kg/m3')}
    pressure = {'pressure_drop': UnitRule('pressure', 'Pa')}
    kv_units = {'kv': UnitRule('kv', 'm3/h')}
    volume_units = {'volume_flow': UnitRule('volume_flow', 'm3/h')}
    return [
        AdapterDefinition('hydraulics.pipe_pressure_drop', '圆管单相沿程压降；不含局部阻力或高差。',
            PipeInput, PressureDropOutput, pipe, input_units=flow | {'viscosity': UnitRule('dynamic_viscosity', 'Pa.s'),
                'length': length, 'diameter': length, 'roughness': length}, output_units=pressure),
        AdapterDefinition('hydraulics.local_pressure_drop', '给定 K 的局部压降；按圆形流通截面计算。',
            LocalLossInput, PressureDropOutput, local, input_units=flow | {'diameter': length}, output_units=pressure),
        AdapterDefinition('hydraulics.valve_pressure_drop', '单相 Kv 压降；有效开度必须大于零。',
            ValveInput, PressureDropOutput, valve, input_units=flow | kv_units | {'opening': UnitRule('ratio', '1')}, output_units=pressure),
        AdapterDefinition('hydraulics.kv_from_loss_coefficient', '局部阻力系数 K 转等效 Kv。',
            KvInput, KvOutput, kv, input_units={'diameter': length}, output_units=kv_units),
        AdapterDefinition('hydraulics.mass_to_volume_flow', '按指定密度将质量流量换成体积流量。',
            MassFlowInput, VolumeFlowOutput, volume, input_units=flow, output_units=volume_units),
        AdapterDefinition('hydraulics.volume_to_mass_flow', '按指定密度将体积流量换成质量流量。',
            VolumeFlowInput, MassFlowOutput, mass, input_units=volume_units | {'density': flow['density']},
            output_units={'mass_flow': flow['mass_flow']}),
    ]
