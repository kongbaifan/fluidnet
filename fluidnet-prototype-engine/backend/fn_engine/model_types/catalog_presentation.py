"""Additive HTTP metadata, deliberately separate from executable module contracts."""
from typing import Literal

from .._module_schema_v1 import Identifier, StrictModel


class DevicePresentation(StrictModel):
    module_id: Identifier
    runtime: Literal['builtin']
    domains: list[Literal['fluid', 'thermal', 'refrigerant', 'signal']]
    capabilities: list[str]
    icon: str
    canvas_family: str


class CatalogPresentationResponse(StrictModel):
    version: Literal[1] = 1
    devices: list[DevicePresentation]
