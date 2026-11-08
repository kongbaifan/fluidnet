"""Module Testing contracts; wire fields and validation preserve the legacy model semantics."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .._module_schema_v1 import Identifier, StrictModel
from ..air_models import MoistAirOptions
from .base import Diagnostic, FluidConfig
from .domain import Project
from .module import ModuleDefinition
from .protocol import CommitStepResponse, EvaluateResponse, RefrigerationEvaluateResponse
from .run import RunFrame


class ChannelTestBoundary(StrictModel):
    inlet_pressure_pa: float = Field(default=250000., gt=0)
    outlet_pressure_pa: float = Field(default=120000., gt=0)
    inlet_temperature_k: float = Field(default=293.15, gt=0)
    outlet_temperature_k: float = Field(default=293.15, gt=0)
    fluid: FluidConfig = Field(default_factory=FluidConfig)
    inlet_humidity_ratio_kg_kg: float = Field(default=.008,ge=0,le=.05,exclude_if=lambda v:v==.008)
    outlet_humidity_ratio_kg_kg: float = Field(default=.008,ge=0,le=.05,exclude_if=lambda v:v==.008)


class ModuleTestConditions(StrictModel):
    host_project: Project | None = Field(default=None,exclude_if=lambda v:v is None)
    host_instance_id: Identifier = Field(default='D1',exclude_if=lambda v:v=='D1')
    moist_air: bool = Field(default=False,exclude_if=lambda v:not v)
    moist_air_options: MoistAirOptions | None = Field(default=None,exclude_if=lambda v:v is None)
    humidity_ratio_kg_kg: float = Field(default=.008,ge=0,le=.05,exclude_if=lambda v:v==.008)
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=FluidConfig)
    inlet_pressure_pa: float = Field(default=250000.0, gt=0)
    outlet_pressure_pa: float = Field(default=120000.0, gt=0)
    temperature_k: float = Field(default=293.15, gt=0)
    duration_s: float = Field(default=0.1, gt=0, le=60)
    dt_s: float = Field(default=0.1, gt=0, le=60)
    channel_boundaries: dict[Identifier, ChannelTestBoundary] = Field(default_factory=dict)
    property_coupling: Literal['reference','node'] = 'reference'

    @model_validator(mode="after")
    def limit_frames(self):
        if self.duration_s > 2000 * self.dt_s:
            raise ValueError("独立测试最多 2001 帧")
        return self


class ModuleTestRequest(ModuleTestConditions):
    module: ModuleDefinition


class ModuleTestAssertion(StrictModel):
    """An author's expected final-frame value, expressed in canonical units."""

    key: str = Field(min_length=1, max_length=256, pattern=r'^\S+$')
    expected: float = Field(strict=True)
    absolute_tolerance: float = Field(default=0., ge=0, strict=True)
    relative_tolerance: float = Field(default=0., ge=0, strict=True)


class ModuleTestCase(StrictModel):
    id: Identifier
    conditions: ModuleTestConditions = Field(default_factory=ModuleTestConditions)
    assertions: list[ModuleTestAssertion] = Field(default_factory=list, max_length=256)

    @model_validator(mode='after')
    def unique_assertions(self):
        if len({assertion.key for assertion in self.assertions}) != len(self.assertions):
            raise ValueError('测试断言变量键重复')
        return self


class ModuleTestSuiteRequest(StrictModel):
    module: ModuleDefinition
    cases: list[ModuleTestCase] = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def unique_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError('测试组合 ID 重复')
        return self


class ModuleTemplateRequest(StrictModel):
    template: Literal['resistance', 'pump', 'heat_exchanger', 'managed_state', 'refrigeration_throttle', 'refrigeration_compressor', 'refrigeration_condenser', 'custom_pressure_drop']
    id: Identifier
    name: str = Field(min_length=1, max_length=80)
    category: str = '自定义模块'


class ModuleGroupRequest(StrictModel):
    project: Project
    instance_ids: list[Identifier] = Field(min_length=1,max_length=100)
    id: Identifier
    name: str = Field(min_length=1,max_length=80)


class CompositeTestContextRequest(StrictModel):
    project: Project
    instance_ids: list[Identifier] = Field(min_length=1,max_length=100)
    module: ModuleDefinition


class ModuleTestResponse(StrictModel):
    constitutive_evaluation: dict | None = Field(default=None, exclude_if=lambda value: value is None)
    execution_domain: Literal['refrigeration'] | None = Field(default=None,exclude_if=lambda value:value is None)
    refrigeration_evaluation: RefrigerationEvaluateResponse | None = Field(default=None,exclude_if=lambda value:value is None)
    module_id: str
    content_hash: str
    state: dict[str, Any] = Field(default_factory=dict)
    evaluation: EvaluateResponse
    committed: CommitStepResponse
    frame: RunFrame
    history: list[RunFrame] = Field(default_factory=list)


class ModuleTestAssertionResult(ModuleTestAssertion):
    actual: float | int | str | bool | None = None
    absolute_error: float | None = None
    allowed_error: float | None = None
    passed: bool
    status: Literal['passed', 'outside_tolerance', 'missing', 'non_numeric', 'non_finite', 'not_evaluated']
    message: str = ''


class ModuleTestCaseResult(StrictModel):
    id: Identifier
    passed: bool
    input_hash: str
    level: Literal['L3'] = 'L3'
    result: ModuleTestResponse | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    assertions: list[ModuleTestAssertionResult] = Field(default_factory=list)


class ModuleTestSuiteResponse(StrictModel):
    module_id: str
    content_hash: str
    definition_hash: str
    passed: bool
    cases: list[ModuleTestCaseResult]


class ModuleDesignRequest(StrictModel):
    """Run design.py once on one library-value set; nothing is stored."""
    module: ModuleDefinition
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=FluidConfig)


class ParameterChange(StrictModel):
    id: str
    before: Any = None
    after: Any = None


class ModuleDesignResponse(StrictModel):
    module_id: str
    design_hash: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    changes: list[ParameterChange] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class UnitWorkpointRequest(StrictModel):
    """Condensing-unit bench (cold-store case): one cycle point at given saturation temperatures (K)."""
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=lambda: FluidConfig(fluid='HEOS::R290'))
    evaporating_temperature_k: float = Field(gt=0)
    condensing_temperature_k: float = Field(gt=0)
    capacity_ratio: float = Field(default=1., gt=0, le=1)


class UnitWorkpointResponse(StrictModel):
    design: dict[str, float]
    point: dict[str, float | None]
    unit_electric_power_w: float
    unit_cop: float
    diagnostics: list[Diagnostic] = Field(default_factory=list)
