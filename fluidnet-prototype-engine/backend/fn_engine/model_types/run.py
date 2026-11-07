"""Run contracts; wire fields and validation preserve the legacy model semantics."""
from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import Field, model_validator

from .._module_schema_v1 import Identifier, StrictModel
from .base import Diagnostic
from .domain import Project


class RunOptions(StrictModel):
    """Shared scheduling and result-selection options for both run entry points."""
    mode: Literal["steady", "dynamic"] = "steady"
    # None runs a background dynamic session until it is stopped.
    duration_s: float | None = Field(default=60, gt=0, le=604800)
    dt_s: float = Field(default=0.1, gt=0, le=60)
    selected_variables: list[str] | None = Field(default=None, max_length=64)
    scenario_id: str | None = None
    # 'trend' keeps every variable only on key frames (first, last, every K-th; ≤ ~51 in total)
    # and only trend_variables plus module state on the others. Dynamic runs only.
    history: Literal["full", "trend"] = "full"
    trend_variables: list[str] = Field(default_factory=list, max_length=256)
    execution_mode: Literal['fast', 'realtime'] = 'fast'
    speed_ratio: float = Field(default=1.0, gt=0, le=100)
    start_paused: bool = False
    # Background runs keep only the most recent `history_window` frames plus a decimated
    # overview of the whole run; synchronous runs return everything (at most 2001 frames).
    history_window: int = Field(default=2001, ge=10, le=20001)

    @model_validator(mode="after")
    def check_duration(self):
        if self.duration_s is None and self.mode != "dynamic":
            raise ValueError("只有动态运行可以不设时长（持续运行）")
        return self

    def frame_count(self) -> int | None:
        """Frames of a finite dynamic run, t=0 included; None for steady or continuous runs."""
        if self.mode != "dynamic" or self.duration_s is None:
            return None
        return math.ceil(self.duration_s / self.dt_s - 1e-9) + 1


class RunRequest(RunOptions):
    project: Project
    project_revision: int | None = Field(default=None, ge=1)


class RunCommand(StrictModel):
    action: Literal["pause", "resume", "step", "stop", "set", "controller", "write"]
    instance_id: str | None = None
    parameter_id: str | None = None
    value: Any = None
    # action="write": frame keys -> values, applied together at one frame boundary (see VariableWrite).
    values: dict[str, Any] | None = Field(default=None, max_length=256)
    command_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')
    controller_id: Identifier | None = None


class RunFrame(StrictModel):
    status: str
    valid: bool
    time_s: float
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    # B0 观测器：仅 hydraulic_diagnostics 打开时非空（真实残差/Jacobian/RPC 计数与分项计时）。
    solve_counters: dict | None = None
    # S1/J2 求解选择摘要（请求方法/实际方法/原因/矩阵规模/Jacobian 模式），始终记录。
    solve_summary: dict | None = None
    # False on trend-history frames that carry only the trend variables (see RunRequest.history).
    full: bool = True
    sequence: int = 0
    parameter_revision: int = 0


class RunRecord(StrictModel):
    id: str
    status: str
    mode: str
    request: RunRequest
    frame: RunFrame | None = None
    history: list[RunFrame] = Field(default_factory=list)


class VariableWrite(StrictModel):
    """POST /runs/{id}/variables: values by frame key, all applied at one frame boundary or none."""
    values: dict[str, float | int | str | bool] = Field(min_length=1, max_length=256)
    command_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')
    # Wait up to this long for the write to be applied or rejected (0 = return the accepted receipt).
    wait_s: float = Field(default=0., ge=0, le=10)


class VariableValues(StrictModel):
    run_id: str
    status: str
    time_s: float | None = None
    sequence: int | None = None
    parameter_revision: int | None = None
    values: dict[str, float | int | str | bool | None] = Field(default_factory=dict)


class RunEvent(StrictModel):
    type: str
    time_s: float = Field(default=0.0, ge=0)
    command_id: str | None = None
    command_status: str | None = None
    message: str | None = None
    command: RunCommand | None = None
    parameter_revision: int | None = None
