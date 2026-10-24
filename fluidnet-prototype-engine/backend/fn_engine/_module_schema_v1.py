"""Frozen schema-1 module parsing/defaults, captured at 98dadd5 (MOD-S2).

Do not extend these classes for new contracts. Add a new schema instead; the
models module re-exports the historical public type names for existing imports.
"""
from __future__ import annotations

from enum import Enum
import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,80}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Domain(str, Enum):
    fluid = "fluid"
    thermal = "thermal"
    # Lumped refrigeration-station streams: no pressure node of their own (see ALGORITHM.md).
    refrigerant = "refrigerant"
    info = "info"
    power = "power"
    mech = "mech"


class Direction(str, Enum):
    in_ = "in"
    out = "out"
    bidirectional = "bidirectional"


class UnitSpec(StrictModel):
    quantity: str
    canonical_unit: str
    display_unit: str
    display_scale: float = Field(default=1.0, gt=0)
    display_offset: float = 0.0

    def to_canonical(self, value: float) -> float:
        return (float(value) - self.display_offset) * self.display_scale

    def from_canonical(self, value: float) -> float:
        return float(value) / self.display_scale + self.display_offset


class ParameterSpec(StrictModel):
    id: Identifier
    label: str
    value_type: Literal["number", "boolean", "text", "curve"] = "number"
    default: Any
    unit: UnitSpec | None = None
    minimum: float | None = None
    maximum: float | None = None
    runtime: bool = False
    writable: bool = True

    @model_validator(mode="after")
    def validate_default(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("参数最小值不能大于最大值")
        if self.value_type == "number":
            if isinstance(self.default, bool) or not isinstance(self.default, (int, float)) or not math.isfinite(self.default):
                raise ValueError("数值参数默认值必须是有限数值")
            if self.minimum is not None and self.default < self.minimum or self.maximum is not None and self.default > self.maximum:
                raise ValueError("参数默认值超出声明范围")
        elif self.value_type == "boolean" and not isinstance(self.default, bool):
            raise ValueError("布尔参数默认值必须是布尔值")
        elif self.value_type == "text" and not isinstance(self.default, str):
            raise ValueError("文本参数默认值必须是字符串")
        elif self.value_type == "curve":
            if not isinstance(self.default, list) or not all(isinstance(row, list) and len(row) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in row) for row in self.default):
                raise ValueError("曲线默认值必须是有限数值点对数组")
        if self.value_type != "number" and self.unit is not None:
            raise ValueError("仅数值参数可以声明单位换算")
        return self


class PortSpec(StrictModel):
    id: Identifier
    label: str
    domain: Domain = Domain.fluid
    direction: Direction = Direction.bidirectional
    required: bool = True
    circuit: str = "fluid"


class ChannelSpec(StrictModel):
    id: Identifier
    name: str
    input_port: str
    output_port: str
    relation: Literal["resistance", "pump_curve", "pressure_source", "heat_transfer", "signal"]
    solver_model: str
    enabled: bool = True


class VariableSpec(StrictModel):
    id: str
    label: str
    quantity: str
    unit: UnitSpec | None = None
    source: Literal["parameter", "port", "state", "derived", "system"]
    writable: bool = False
    sampleable: bool = True
    parameter_id: str | None = None
    port_id: str | None = None


class ModuleFieldsV1(StrictModel):
    """Frozen field layout shared by parsers, not itself a schema entry point."""

    schema_version: int = 1
    id: Identifier
    name: str
    version: int = Field(default=1, ge=1)
    category: str = "自定义模块"
    description: str = ""
    ports: list[PortSpec] = Field(default_factory=list)
    parameters: list[ParameterSpec] = Field(default_factory=list)
    variables: list[VariableSpec] = Field(default_factory=list)
    channels: list[ChannelSpec] = Field(default_factory=list)
    solver_model: str = "generic"
    state_model: str | None = None
    thermal_model: str | None = None
    source_format: str = "python-v1"
    source: dict[str, str | list[str]] = Field(default_factory=dict)
    runtime: Literal["builtin", "python"] = "builtin"
    entrypoint: str = ""
    content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    definition_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    package_path: str | None = None
    bank_names: list[str] = Field(default_factory=lambda: ["额定工况", "部分负荷", "调试备份"])

    @model_validator(mode="after")
    def validate_definition(self):
        port_ids = [p.id for p in self.ports]
        parameter_ids = [p.id for p in self.parameters]
        variable_ids = [v.id for v in self.variables]
        if len(port_ids) != len(set(port_ids)):
            raise ValueError(f"模块 {self.id} 的端口 ID 重复")
        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError(f"模块 {self.id} 的参数 ID 重复")
        if len(variable_ids) != len(set(variable_ids)):
            raise ValueError(f"模块 {self.id} 的变量 ID 重复")
        if len(self.channels) != len({c.id for c in self.channels}):
            raise ValueError(f"模块 {self.id} 的通路 ID 重复")
        ports = set(port_ids)
        for channel in self.channels:
            if channel.input_port not in ports or channel.output_port not in ports:
                raise ValueError(f"模块 {self.id} 的通路引用了不存在的端口")
            if channel.input_port == channel.output_port:
                raise ValueError("通路两端不能是同一端口")
        for variable in self.variables:
            if variable.port_id and variable.port_id not in ports:
                raise ValueError("变量引用了不存在的端口")
            if variable.parameter_id and variable.parameter_id not in parameter_ids:
                raise ValueError("变量引用了不存在的参数")
        return self


class ModuleDefinitionV1(ModuleFieldsV1):
    schema_version: Literal[1] = 1


