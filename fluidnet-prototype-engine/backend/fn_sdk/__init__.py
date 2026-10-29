"""Lightweight author-facing interfaces for FluidNet Python device modules.

The host supplies implementations of these protocols. Importing this package
requires only Python's standard library; it does not start a runner or load EOS.
"""
from typing import Final

from ._protocols import (
    CallbackPhase, ChannelDataKind, ChannelResult, CommitResult, DeviceModule, Diagnostic, DiagnosticSeverity,
    EvaluateResult, ExecutionInfo, FluidState, JSONValue, ModuleContext, NetworkBuilder,
    NetworkRelation, PortDataKind, PortState, PropertyService, RelationKind, ScalarValue, StateDataKind,
)
from .hydraulics import (
    kv_from_loss_coefficient, mass_flow_to_volume_flow_m3_h, pipe_pressure_drop_pa,
    resistance_pressure_drop_pa, valve_pressure_drop_pa, volume_flow_m3_h_to_mass_flow_kg_s,
)
from .thermal import heat_exchanger_effectiveness

SDK_API_VERSION: Final[str] = '0.6.0'

__all__ = [
    'heat_exchanger_effectiveness',
    'SDK_API_VERSION', 'CallbackPhase', 'ChannelDataKind', 'ChannelResult', 'CommitResult', 'DeviceModule', 'Diagnostic',
    'DiagnosticSeverity', 'EvaluateResult', 'FluidState', 'JSONValue', 'ModuleContext',
    'ExecutionInfo', 'NetworkBuilder', 'NetworkRelation', 'PortDataKind', 'PortState',
    'PropertyService', 'RelationKind', 'ScalarValue', 'StateDataKind',
    'kv_from_loss_coefficient', 'mass_flow_to_volume_flow_m3_h', 'pipe_pressure_drop_pa',
    'resistance_pressure_drop_pa', 'valve_pressure_drop_pa', 'volume_flow_m3_h_to_mass_flow_kg_s',
]
