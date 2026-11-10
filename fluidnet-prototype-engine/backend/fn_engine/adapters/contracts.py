"""Versioned, business-neutral computation envelopes. Physical models keep their own schemas."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

AdapterId = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$', max_length=100)]


class AdapterModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class AdapterRequest(AdapterModel):
    adapter_id: AdapterId
    version: int = Field(default=1, ge=1)
    request_id: str | None = Field(default=None, max_length=128)
    inputs: dict[str, JsonValue] = Field(default_factory=dict)
    input_units: dict[str, str] = Field(default_factory=dict)
    output_units: dict[str, str] = Field(default_factory=dict)


class AdapterResult(AdapterModel):
    adapter_id: AdapterId
    version: int
    request_id: str | None = None
    engine_version: str
    outputs: dict[str, JsonValue]
    output_units: dict[str, str]


class UnitDescription(AdapterModel):
    quantity: str
    canonical_unit: str
    accepted_units: list[str]


class AdapterDescription(AdapterModel):
    adapter_id: AdapterId
    version: int = Field(ge=1)
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    input_units: dict[str, UnitDescription]
    output_units: dict[str, UnitDescription]


class AdapterCatalog(AdapterModel):
    contract_version: Literal[1] = 1
    adapters: list[AdapterDescription]


class AdapterFailure(AdapterModel):
    code: str
    message: str
    adapter_id: str | None = None
    version: int | None = None
    request_id: str | None = None
    field: str | None = None
    diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)


class AdapterErrorResponse(AdapterModel):
    detail: AdapterFailure


def correlate_failure(detail: AdapterFailure, body: Any) -> None:
    """Preserve bounded request identifiers even when envelope validation fails."""
    if not isinstance(body, Mapping):
        return
    for name, limit in (('request_id', 128), ('adapter_id', 100)):
        value = body.get(name)
        if isinstance(value, str) and len(value) <= limit:
            setattr(detail, name, value)
    version = body.get('version', 1)
    if isinstance(version, int) and not isinstance(version, bool) and version > 0:
        detail.version = version


class AdapterError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 422,
                 field: str | None = None, diagnostics: list | None = None):
        super().__init__(message)
        self.status = status
        self.detail = AdapterFailure(code=code, message=message, field=field, diagnostics=diagnostics or [])
