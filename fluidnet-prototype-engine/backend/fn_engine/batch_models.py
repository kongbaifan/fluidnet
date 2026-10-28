"""Contracts for bounded, reproducible scenario batches."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictFloat, model_validator

from .models import Diagnostic, Scenario, StrictModel, UnitSpec

BatchState = Literal['ready', 'running', 'completed', 'completed_with_errors', 'cancelled', 'interrupted', 'failed']
BatchItemState = Literal['pending', 'running', 'completed', 'failed', 'cancelled', 'interrupted']


class SweepRange(StrictModel):
    start: StrictFloat
    stop: StrictFloat
    count: int = Field(ge=2, le=20, strict=True)


class ParameterSweep(StrictModel):
    instance_id: str = Field(min_length=1, max_length=100)
    parameter_id: str = Field(min_length=1, max_length=100)
    # These are display-unit values, converted against the saved parameter contract.
    values: list[StrictFloat] | None = Field(default=None, min_length=1, max_length=20)
    range: SweepRange | None = None

    @model_validator(mode='after')
    def check_source(self):
        if (self.values is None) == (self.range is None):
            raise ValueError('请选择显式值列表或等间距序列，不能同时提供')
        return self


class BatchRunOptions(StrictModel):
    mode: Literal['steady', 'dynamic'] = 'steady'
    duration_s: float = Field(default=60., gt=0, le=604800)
    dt_s: float = Field(default=.1, gt=0, le=60)


class BatchPlanRequest(StrictModel):
    revision: int | None = Field(default=None, ge=1)
    sweep: ParameterSweep | None = None
    scenario_ids: list[str] = Field(default_factory=list, max_length=20)
    variables: list[str] = Field(min_length=1, max_length=16)
    options: BatchRunOptions = Field(default_factory=BatchRunOptions)

    @model_validator(mode='after')
    def check_selection(self):
        if (self.sweep is None) == (not self.scenario_ids):
            raise ValueError('请选择参数扫描或已有工况')
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError('所选工况不能重复')
        if len(set(self.variables)) != len(self.variables):
            raise ValueError('观察变量不能重复')
        return self


class BatchCreateRequest(BatchPlanRequest):
    request_id: str = Field(min_length=1, max_length=96, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
    preview_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    name: str = Field(default='批量工况', min_length=1, max_length=120)


class BatchVariable(StrictModel):
    key: str
    label: str
    unit: UnitSpec


class BatchParameter(StrictModel):
    instance_id: str
    instance_name: str
    parameter_id: str
    label: str
    unit: UnitSpec
    value: float
    minimum: float | None = None
    maximum: float | None = None


class BatchScenarioChoice(StrictModel):
    id: str
    name: str


class BatchSetupResponse(StrictModel):
    project_id: str
    project_name: str
    revision: int
    parameters: list[BatchParameter]
    variables: list[BatchVariable]
    scenarios: list[BatchScenarioChoice]


class BatchModuleSource(StrictModel):
    id: str
    name: str
    version: int
    definition_hash: str
    content_hash: str | None = None


class BatchControlSource(StrictModel):
    id: str
    enabled: bool
    content_hash: str


class BatchSource(StrictModel):
    project_id: str
    project_name: str
    revision: int
    snapshot_hash: str
    modules: list[BatchModuleSource]
    controls: list[BatchControlSource]


class BatchPreviewItem(StrictModel):
    id: str
    name: str
    scenario: Scenario
    source_scenario_id: str | None = None
    parameter_value: float | None = None
    parameter_unit: str | None = None


class BatchPreviewResponse(StrictModel):
    source: BatchSource
    options: BatchRunOptions
    variables: list[BatchVariable]
    items: list[BatchPreviewItem] = Field(min_length=1, max_length=20)
    preview_hash: str


class BatchAttempt(StrictModel):
    run_id: str
    status: BatchItemState
    started_at: str
    finished_at: str | None = None


class BatchItemResponse(StrictModel):
    id: str
    name: str
    scenario_id: str
    status: BatchItemState
    run_id: str | None = None
    parameter_value: float | None = None
    parameter_unit: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    time_s: float | None = None
    values: dict[str, float | None] = Field(default_factory=dict)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    attempts: list[BatchAttempt] = Field(default_factory=list)


class BatchSummary(StrictModel):
    id: str
    name: str
    project_id: str
    project_name: str
    project_revision: int
    snapshot_hash: str
    status: BatchState
    created_at: str
    updated_at: str
    total: int
    completed: int
    failed: int
    cancelled: int
    interrupted: int
    error: str | None = None


class BatchDetailResponse(BatchSummary):
    source: BatchSource
    options: BatchRunOptions
    variables: list[BatchVariable]
    items: list[BatchItemResponse]


class BatchListResponse(StrictModel):
    batches: list[BatchSummary]
    total: int
    offset: int


class BatchCurveResponse(StrictModel):
    batch_id: str
    item_id: str
    status: BatchItemState
    variable: BatchVariable
    # Time and canonical value. Null is unavailable, never a fabricated zero.
    points: list[tuple[float, float | None]] = Field(max_length=2000)
    stride: int = Field(ge=1)
    total_rows: int = Field(ge=0)


class BatchDeleteResponse(StrictModel):
    id: str
    deleted: bool
