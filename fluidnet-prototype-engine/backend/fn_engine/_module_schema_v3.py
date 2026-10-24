"""Frozen schema 3: applicability, explicit dependencies and bounded composition."""
from typing import Literal
from pydantic import Field, model_validator
from ._module_schema_v1 import Identifier, ModuleFieldsV1, StrictModel
from ._module_schema_v2 import ModuleSDKRequirements
_DOMAINS:tuple[Literal['fluid'],...]=('fluid',)
_PHASES:tuple[Literal['liquid','gas'],...]=('liquid','gas')


class ModuleOperatingLimit(StrictModel):
    target: Literal['port', 'channel']
    id: Identifier
    quantity: Literal['pressure_pa', 'temperature_k', 'mass_flow_kg_s']
    minimum: float | None = None
    maximum: float | None = None
    kind: Literal['hard', 'envelope'] = 'envelope'

    @model_validator(mode='after')
    def valid_range(self):
        if self.minimum is None and self.maximum is None:
            raise ValueError('工况限制必须包含至少一个端点')
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('工况范围下限大于上限')
        if self.target == 'channel' and self.quantity != 'mass_flow_kg_s':
            raise ValueError('通路限制目前只支持质量流量')
        return self


class ModuleApplicability(StrictModel):
    execution_domains: list[Literal['fluid']] = Field(default_factory=lambda:list(_DOMAINS), min_length=1)
    phases: list[Literal['liquid','gas']] = Field(default_factory=lambda:list(_PHASES), min_length=1)
    fluids: list[str] = Field(default_factory=list, max_length=64)
    limits: list[ModuleOperatingLimit] = Field(default_factory=list, max_length=128)
    assumptions: list[str] = Field(default_factory=list, max_length=32)


class CompositeEndpoint(StrictModel):
    instance_id: Identifier
    port_id: Identifier


class CompositeParameterTarget(StrictModel):
    instance_id: Identifier
    parameter_id: Identifier


class CompositeChild(StrictModel):
    id: Identifier
    module_id: Identifier
    version: int = Field(ge=1)
    content_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    definition_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    parameters: dict = Field(default_factory=dict)


class CompositeConnection(StrictModel):
    id: Identifier
    source: CompositeEndpoint
    target: CompositeEndpoint


class CompositeDefinition(StrictModel):
    children: list[CompositeChild] = Field(min_length=1, max_length=100)
    modules: list[dict] = Field(default_factory=list, max_length=100)
    connections: list[CompositeConnection] = Field(default_factory=list, max_length=500)
    external_ports: dict[Identifier, CompositeEndpoint]
    parameter_maps: dict[Identifier, list[CompositeParameterTarget]] = Field(default_factory=dict)
    output_aliases: dict[str, str] = Field(default_factory=dict)


class ModuleDefinitionV3(ModuleFieldsV1):
    schema_version: Literal[3] = 3
    sdk: ModuleSDKRequirements
    runtime: Literal['python'] = Field(...)
    applicability: ModuleApplicability = Field(default_factory=ModuleApplicability)
    hydraulic_dependencies: dict[Identifier, list[Identifier]] = Field(default_factory=dict)
    dependency_mode: Literal['conservative','tracked'] = 'conservative'
    pure_evaluate: bool = False
    composite: CompositeDefinition | None = None

    @model_validator(mode='after')
    def validate_extensions(self):
        channels, ports = {channel.id for channel in self.channels}, {port.id for port in self.ports}
        if set(self.hydraulic_dependencies) - channels:
            raise ValueError('依赖声明引用了不存在的通路')
        if any(set(names) - ports or len(names) != len(set(names)) for names in self.hydraulic_dependencies.values()):
            raise ValueError('依赖端口不存在或重复')
        for limit in self.applicability.limits:
            if limit.id not in (ports if limit.target == 'port' else channels):
                raise ValueError('工况限制引用了不存在的端口或通路')
        return self
