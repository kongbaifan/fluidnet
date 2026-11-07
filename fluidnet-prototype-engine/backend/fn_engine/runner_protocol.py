"""Structural boundary for parent-owned module step transactions.

Lifecycle and evaluation remain transport specific: a batch Handle is initialized
by its shard and evaluated through BatchRunners, rather than owning a process.
This protocol does not add hooks at the physical acceptance point.
"""
from typing import Any, Protocol

from .model_types.base import ChannelState
from .model_types.module import ModuleDefinition
from .model_types.protocol import (
    CommitStepRequest, CommitStepResponse, EvaluateResponse, ModuleDerivativeResponse,
    ModulePhaseRequest, ModuleStepCandidate, ModuleThermalResponse,
)
from .module_execution import InvocationState


class ModuleRunner(Protocol):
    definition: ModuleDefinition
    state: dict[str, Any]
    state_revision: int
    execution: InvocationState
    _accepted_candidate: ModuleStepCandidate | None

    def prepare_step(self, request: CommitStepRequest,
                     channels: dict[str, ChannelState] | None = None) -> ModuleStepCandidate: ...

    def commit_step(self, request: CommitStepRequest,
                    channels: dict[str, ChannelState] | None = None) -> CommitStepResponse: ...

    def synchronize_state(self, candidate: ModuleStepCandidate) -> None: ...

    def discard_candidate(self) -> None: ...

    def phase_call(self, phase: str, request: ModulePhaseRequest
                   ) -> ModuleThermalResponse | ModuleDerivativeResponse | EvaluateResponse: ...


class LocalAcceptanceState(Protocol):
    """Existing in-process retry bookkeeping, updated only by the parent."""
    _last_committed_time_s: float | None
    _accepted_digest: str | None
    _pending_digest: str | None
    _pending_candidate: ModuleStepCandidate | None


class ClosableTransport(Protocol):
    def close(self, force: bool = False) -> None: ...
