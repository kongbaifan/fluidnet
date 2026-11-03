"""Select the physics session while keeping public run/command/archive contracts."""
from typing import Any, Protocol

from .models import RunFrame
from .simulation import SimulationSession
from .session_base import FrameBuffer, SessionNetwork


class RunSession(Protocol):
    """Commands and observations available to scheduling, API and test benches."""
    time: float
    revision: int

    @property
    def frames(self) -> FrameBuffer: ...

    @property
    def done(self) -> bool: ...

    @property
    def report_keys(self) -> frozenset[str]: ...

    def initialize(self) -> RunFrame: ...
    def advance(self) -> RunFrame: ...
    def snapshot(self) -> RunFrame: ...
    def set_parameter(self, instance_id: str, parameter_id: str, value: Any) -> None: ...
    def update_controller(self, controller_id: str, field: str, value: Any) -> None: ...
    def write_variables(self, values: dict[str, Any]) -> None: ...
    def preview_control(self, script_id: str) -> dict[str, Any]: ...
    def close(self) -> None: ...


def create_session(network: SessionNetwork, duration_s: float | None, dt_s: float, keep: int | None = None) -> RunSession:
    if getattr(network, 'execution_domain', None) == 'coupled':
        from .refrigeration.coupling import CoupledStationSession
        return CoupledStationSession(network, duration_s, dt_s, keep)
    if getattr(network, 'execution_domain', None) == 'cold_store':
        from .refrigeration.cold_store import ColdStoreSession
        return ColdStoreSession(network, duration_s, dt_s, keep)
    if getattr(network, 'execution_domain', None) == 'refrigeration':
        from .refrigeration.station import StationSession
        return StationSession(network, duration_s, dt_s, keep)
    if getattr(network, 'execution_domain', None) == 'thermal':
        from .refrigeration.session import ThermalSession
        return ThermalSession(network, duration_s, dt_s, keep)
    return SimulationSession(network, duration_s, dt_s, keep)
