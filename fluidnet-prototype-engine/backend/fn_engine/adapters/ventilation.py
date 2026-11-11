"""Outdoor-air requirements without building-specific objects or code-compliance claims."""
from typing import Literal, Self

from pydantic import Field, model_validator

from .contracts import AdapterModel
from .registry import AdapterDefinition


class VentilationZone(AdapterModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    area_m2: float = Field(gt=0, le=1e7)
    height_m: float = Field(gt=0, le=100)
    people: int = Field(ge=0, le=1000000)
    per_person_m3_h: float = Field(default=30, ge=0, le=1000)
    air_changes_h: float = Field(default=0, ge=0, le=100)


class VentilationInput(AdapterModel):
    zones: list[VentilationZone] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def unique_ids(self) -> Self:
        if len({zone.id for zone in self.zones}) != len(self.zones):
            raise ValueError('新风区域编号不能重复')
        return self


class VentilationZoneResult(AdapterModel):
    id: str
    name: str
    volume_m3: float
    people_flow_m3_h: float
    air_changes_flow_m3_h: float
    design_flow_m3_h: float
    governing: Literal['people', 'air_changes', 'both', 'none']


class VentilationOutput(AdapterModel):
    total_flow_m3_h: float
    total_people: int
    total_area_m2: float
    zones: list[VentilationZoneResult]


def requirements(p: VentilationInput) -> VentilationOutput:
    results = []
    for zone in p.zones:
        volume = zone.area_m2*zone.height_m
        people_flow = zone.people*zone.per_person_m3_h
        changes_flow = volume*zone.air_changes_h
        flow = max(people_flow, changes_flow)
        governing: Literal['people', 'air_changes', 'both', 'none'] = 'none'
        if flow > 0:
            governing = 'both' if people_flow == changes_flow else 'people' if people_flow > changes_flow else 'air_changes'
        results.append(VentilationZoneResult(id=zone.id, name=zone.name, volume_m3=volume,
            people_flow_m3_h=people_flow, air_changes_flow_m3_h=changes_flow,
            design_flow_m3_h=flow, governing=governing))
    return VentilationOutput(total_flow_m3_h=sum(r.design_flow_m3_h for r in results),
        total_people=sum(z.people for z in p.zones), total_area_m2=sum(z.area_m2 for z in p.zones), zones=results)


def definition() -> AdapterDefinition:
    return AdapterDefinition('ventilation.requirements',
        '逐区域按人数新风量与体积换气量取大后汇总；参数由调用方提供，不自动判定规范符合性。',
        VentilationInput, VentilationOutput, requirements)
