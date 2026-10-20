"""Select the physics session while keeping public run/command/archive contracts."""
from typing import Protocol

from .models import RunFrame
from .simulation import SimulationSession


class RunSession(Protocol):
    time: float
    revision: int
    frames: object
    done: bool

    def initialize(self) -> RunFrame: ...
    def advance(self) -> RunFrame: ...
    def set_parameter(self, instance_id, parameter_id, value): ...
    def update_controller(self, controller_id, field, value): ...
    def write_variables(self, values): ...
    def close(self): ...


def create_session(network, duration_s, dt_s, keep=None):
    if getattr(network, 'execution_domain', None) == 'thermal':
        from .refrigeration.session import ThermalSession
        return ThermalSession(network, duration_s, dt_s, keep)
    return SimulationSession(network, duration_s, dt_s, keep)
