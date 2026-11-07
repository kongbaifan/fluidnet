"""Protocol contracts; wire fields and validation preserve the legacy model semantics."""
from __future__ import annotations

import math
from typing import Any, Literal

from fn_sdk import CallbackPhase, ChannelDataKind, PortDataKind, StateDataKind
from pydantic import ConfigDict, Field, model_validator

from .._module_schema_v1 import Identifier, StrictModel
from ..refrigeration_models import RefrigerationThrottleFlow, RefrigerationThrottleInput
from .base import ChannelState, Diagnostic, FluidConfig, ModulePackageRef, PortState
from .module import ModuleDefinition


class NetworkRelation(StrictModel):
    relation_id: Identifier
    kind: Literal["pipe", "valve", "pump", "compressor", "resistance", "pressure_drop"]
    channel: Identifier
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_parameters(self):
        required = {'pipe':['length_m','diameter_m','roughness_m'], 'valve':['kv_m3_h','opening_ratio'],
                    'pump':['head_curve','speed_ratio'], 'compressor':['forced_mass_flow_kg_s'],
                    'resistance':['diameter_m','loss_coefficient'], 'pressure_drop':['pressure_drop_pa']}[self.kind]
        if self.kind == 'pressure_drop' and set(self.parameters) != {'pressure_drop_pa'}:
            raise ValueError('自定义压降关系只接受 pressure_drop_pa；热流请使用 thermal 回调')
        if set(required) - self.parameters.keys():
            raise ValueError(f'{self.kind} 缺少关系参数 {sorted(set(required)-self.parameters.keys())}')
        for key,value in self.parameters.items():
            if key == 'head_curve':
                continue
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
                raise ValueError(f'{self.kind}.{key} 必须是有限数值')
            if key in {'diameter_m','length_m','kv_m3_h','speed_ratio'} and value <= 0:
                raise ValueError(f'{self.kind}.{key} 必须大于零')
            if key in {'roughness_m','density_kg_m3','viscosity_pa_s','loss_coefficient'} and value < 0:
                raise ValueError(f'{self.kind}.{key} 不能小于零')
            if key == 'opening_ratio' and not 0 <= value <= 1:
                raise ValueError('阀门开度必须在 [0,1] 内')
        if self.kind == 'pump':
            curve=self.parameters['head_curve']
            valid=isinstance(curve,list) and len(curve)>=2
            valid=valid and all(isinstance(p,list) and len(p)==2 and all(isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 for v in p) for p in curve)
            valid=valid and curve[0][0]==0 and curve[-1][1]==0 and all(b[0]>a[0] and b[1]<a[1] for a,b in zip(curve,curve[1:]))
            if not valid:
                raise ValueError('扬程曲线必须流量递增、扬程递减，从零流量到零扬程')
        return self


class ModuleRequestContext(StrictModel):
    """Optional transport metadata; callback phase/time are derived from the action itself."""

    request_id: Identifier
    step_id: Identifier | None = None
    accepted_time_s: float | None = Field(default=None, ge=0)
    port_data: Literal['trial', 'converged'] = 'trial'


class ModuleExecutionInfo(StrictModel):
    model_config = ConfigDict(frozen=True)

    phase: CallbackPhase = 'manual'
    time_s: float | None = Field(default=None, ge=0)
    run_id: str | None = None
    instance_id: str | None = None
    request_id: str | None = None
    step_id: str | None = None
    iteration_id: int | None = Field(default=None, ge=0)
    dt_s: float | None = Field(default=None, gt=0)
    accepted_time_s: float | None = Field(default=None, ge=0)
    port_data: PortDataKind = 'unavailable'
    channel_data: ChannelDataKind = 'unavailable'
    state_data: StateDataKind = 'unavailable'


class InitializeRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    package: ModulePackageRef
    parameters: dict[str, Any] = Field(default_factory=dict)
    fluid: FluidConfig = Field(default_factory=FluidConfig)
    # Fluid per port where it differs from `fluid` (a module spanning two circuits); ctx.fluid_at(port).
    port_fluids: dict[str, FluidConfig] = Field(default_factory=dict)
    initial_state: dict[str, Any] = Field(default_factory=dict)
    cache_enabled: bool = Field(default=False, exclude_if=lambda value: value is False)
    context: ModuleRequestContext | None = Field(default=None, exclude_if=lambda value: value is None)


class EvaluateRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    iteration_id: int = Field(ge=0)
    time_s: float = Field(ge=0)
    trial_ports: dict[Identifier, PortState] = Field(default_factory=dict)
    # Only supplied to net.pressure_drop modules; omitted from legacy wire payloads.
    trial_channels: dict[Identifier, ChannelState] = Field(default_factory=dict, exclude_if=lambda value: not value)
    readonly_state: dict[str, Any] = Field(default_factory=dict)
    state_revision: int | None = Field(default=None,ge=0,exclude_if=lambda value:value is None)
    context: ModuleRequestContext | None = Field(default=None, exclude_if=lambda value: value is None)


class EvaluateResponse(StrictModel):
    relations: list[NetworkRelation] = Field(default_factory=list)
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list["Diagnostic"] = Field(default_factory=list)
    accessed_ports: list[Identifier] = Field(default_factory=list, exclude_if=lambda value: not value)
    cache_hit: bool = Field(default=False, exclude_if=lambda value: value is False)


class RefrigerationEvaluateRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    iteration_id: int = Field(ge=0)
    time_s: float = Field(ge=0)
    throttle: RefrigerationThrottleInput
    state_revision: int | None = Field(default=None,ge=0)
    context: ModuleRequestContext | None = None


class RefrigerationEvaluateResponse(StrictModel):
    flow: RefrigerationThrottleFlow
    variables: dict[str,float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list['Diagnostic'] = Field(default_factory=list)


class ModulePhaseRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    time_s: float = Field(ge=0)
    ports: dict[Identifier, PortState] = Field(default_factory=dict)
    channels: dict[Identifier, ChannelState] = Field(default_factory=dict)
    context: ModuleRequestContext | None = Field(default=None, exclude_if=lambda value: value is None)


class ModuleThermalResponse(StrictModel):
    heat_w: dict[Identifier, float] = Field(default_factory=dict)
    diagnostics: list['Diagnostic'] = Field(default_factory=list)


class ModuleRelationDerivative(StrictModel):
    flow_slope_pa_per_kg_s: float
    port_pressure_derivatives: dict[Identifier, float] = Field(default_factory=dict)
    smooth: bool = True


class ModuleDerivativeResponse(StrictModel):
    derivatives: dict[Identifier, ModuleRelationDerivative]
    diagnostics: list['Diagnostic'] = Field(default_factory=list)


class CommitStepRequest(StrictModel):
    run_id: Identifier
    instance_id: Identifier
    time_s: float = Field(ge=0)
    dt_s: float = Field(gt=0)
    converged_ports: dict[Identifier, PortState] = Field(default_factory=dict)
    converged_channels: dict[Identifier, ChannelState] = Field(default_factory=dict)
    context: ModuleRequestContext | None = Field(default=None, exclude_if=lambda value: value is None)


class CommitStepResponse(StrictModel):
    state: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list["Diagnostic"] = Field(default_factory=list)


class ModuleStepCandidate(StrictModel):
    candidate_id: Identifier
    step_id: Identifier
    base_revision: int = Field(ge=0)
    time_s: float = Field(ge=0)
    result: CommitStepResponse
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    definition_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class ModuleReplaySnapshot(StrictModel):
    """Inputs captured before one Python callback; never an accepted network frame."""
    format_version: Literal[1]
    capture_kind: Literal['callback_input']
    module: ModuleDefinition
    parameters: dict[str, Any]
    state: dict[str, Any]
    fluid: FluidConfig
    port_fluids: dict[str, FluidConfig] = Field(default_factory=dict)
    ports: dict[str, PortState] = Field(default_factory=dict)
    channels: dict[str, ChannelState] = Field(default_factory=dict)
    execution: ModuleExecutionInfo
    refrigeration: RefrigerationThrottleInput | None = None
    content_hash: str = Field(pattern=r'^[a-fA-F0-9]{64}$')
    definition_hash: str = Field(pattern=r'^[a-fA-F0-9]{64}$')
    failure: Diagnostic


EvaluateResponse.model_rebuild()
CommitStepResponse.model_rebuild()
