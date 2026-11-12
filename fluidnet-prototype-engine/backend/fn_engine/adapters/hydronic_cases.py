"""Size a shared pipe tree across distinct design cases, then recompute each case."""
from typing import Literal, Self

from pydantic import Field, model_validator

from .contracts import AdapterModel
from .hydronics import HydronicDesignInput, HydronicDesignOutput, design
from .registry import AdapterDefinition


class HydronicCase(AdapterModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    inputs: HydronicDesignInput


class HydronicCasesInput(AdapterModel):
    cases: list[HydronicCase] = Field(min_length=2, max_length=8)

    @model_validator(mode='after')
    def same_pipe_system(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError('工况编号不能重复')

        def geometry(p):
            return {s.id: (s.parent_id, s.length_m, s.local_loss_coefficient, s.fixed_dn) for s in p.segments}

        first = self.cases[0].inputs
        sizes = {size.dn: size.inner_diameter_m for size in first.pipe_sizes}
        for case in self.cases[1:]:
            p = case.inputs
            if geometry(p) != geometry(first) or p.roughness_m != first.roughness_m:
                raise ValueError('共用管路的拓扑、管长、K、指定管径及粗糙度必须一致')
            if {size.dn: size.inner_diameter_m for size in p.pipe_sizes} != sizes:
                raise ValueError('共用管路必须使用同一份管径与实际内径目录')
        return self


class SharedPipe(AdapterModel):
    id: str
    name: str
    dn: int
    inner_diameter_m: float
    selection: Literal['automatic', 'fixed']
    minimum_dn_by_case: dict[str, int]
    governing_cases: list[str]


class CaseResult(AdapterModel):
    id: str
    name: str
    design: HydronicDesignOutput


class HydronicCasesOutput(AdapterModel):
    feasible: bool
    shared_pipes: list[SharedPipe]
    cases: list[CaseResult]


def design_cases(p: HydronicCasesInput) -> HydronicCasesOutput:
    # First choose each case's smallest permitted bore, preserving explicit manual sizes.
    preliminary = {case.id: {s.id: s for s in design(case.inputs).segments} for case in p.cases}
    shared = []
    for segment in p.cases[0].inputs.segments:
        results = {case.id: preliminary[case.id][segment.id] for case in p.cases}
        largest = max(results.values(), key=lambda s: s.inner_diameter_m)
        shared.append(SharedPipe(id=segment.id, name=segment.name, dn=largest.dn,
            inner_diameter_m=largest.inner_diameter_m, selection='fixed' if segment.fixed_dn is not None else 'automatic',
            minimum_dn_by_case={key: result.dn for key, result in results.items()},
            governing_cases=[key for key, result in results.items()
                if result.inner_diameter_m == largest.inner_diameter_m and result.flow_m3_h > 0]))
    fixed = {pipe.id: pipe.dn for pipe in shared}
    cases = []
    for case in p.cases:
        inputs = case.inputs.model_copy(deep=True)
        for segment in inputs.segments:
            segment.fixed_dn = fixed[segment.id]
        # Changing the bore changes every path loss and may change the critical path.
        cases.append(CaseResult(id=case.id, name=case.name, design=design(inputs)))
    return HydronicCasesOutput(feasible=all(case.design.feasible for case in cases), shared_pipes=shared, cases=cases)


def definition() -> AdapterDefinition:
    return AdapterDefinition('hydronics.design_cases', '多工况共用管路设计：逐段按实际内径包络选径，分别复算各工况阻力、最不利路径和泵阀需求。',
        HydronicCasesInput, HydronicCasesOutput, design_cases)
