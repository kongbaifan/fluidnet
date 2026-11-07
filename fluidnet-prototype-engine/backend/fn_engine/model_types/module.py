"""Module contracts; wire fields and validation preserve the legacy model semantics."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from .._module_schema_v1 import Identifier, ModuleDefinitionV1, ModuleFieldsV1, StrictModel
from .._module_schema_v2 import ModuleDefinitionV2, ModuleSDKRequirements
from .._module_schema_v3 import CompositeDefinition, ModuleApplicability, ModuleDefinitionV3
from .._module_schema_v4 import ModuleDefinitionV4, RefrigerationApplicability
from .base import ModulePackageRef


class ModuleDefinition(ModuleFieldsV1):
    """Schema-dispatched module facade; v1 never receives SDK default fields."""

    schema_version: Literal[1, 2, 3, 4] = 1
    sdk: ModuleSDKRequirements | None = Field(default=None, exclude_if=lambda value: value is None)
    applicability: ModuleApplicability | RefrigerationApplicability | None = Field(default=None, exclude_if=lambda value: value is None)
    execution_role: Literal['refrigeration.isenthalpic_throttle.v1'] | None = Field(default=None,exclude_if=lambda value:value is None)
    hydraulic_dependencies: dict[Identifier, list[Identifier]] | None = Field(default=None, exclude_if=lambda value: value is None)
    dependency_mode: Literal['conservative','tracked'] | None = Field(default=None, exclude_if=lambda value: value is None)
    pure_evaluate: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    composite: CompositeDefinition | None = Field(default=None, exclude_if=lambda value: value is None)
    model_config = ConfigDict(json_schema_extra={"allOf": [{
        "if": {"properties": {"schema_version": {"enum": [2, 3, 4]}}, "required": ["schema_version"]},
        "then": {"required": ["sdk", "runtime"], "properties": {"sdk": {"type": "object"}, "runtime": {"const": "python"}}},
        "else": {"not": {"required": ["sdk"]}},
    }, {
        'if': {'properties': {'schema_version': {'const': 3}}, 'required': ['schema_version']},
        'then': {'properties': {'applicability': {'type':'object','properties':{'execution_domains':{'items':{'const':'fluid'}}}}, 'hydraulic_dependencies': {'type':'object'},
                                'dependency_mode': {'type':'string'}, 'pure_evaluate': {'type':'boolean'}}},
        'else': {'not': {'anyOf': [{'required':[name]} for name in
            ['hydraulic_dependencies','dependency_mode','pure_evaluate','composite']]}}
    }, {
        'if': {'properties': {'schema_version': {'const':4}}, 'required':['schema_version']},
        'then': {'required':['execution_role'], 'properties': {
            'execution_role':{'const':'refrigeration.isenthalpic_throttle.v1'},
            'applicability':{'type':'object','properties':{'execution_domains':{'items':{'const':'refrigeration'}}}}, 'solver_model':{'const':'generic'},
            'state_model':{'type':'null'}, 'thermal_model':{'type':'null'}, 'source_format':{'const':'python-v1'}, 'channels':{'maxItems':0}}},
        'else': {'not':{'required':['execution_role']}}
    }, {
        'if': {'properties': {'schema_version': {'enum':[1,2]}}},
        'then': {'not':{'required':['applicability']}}
    }]})

    @model_validator(mode="before")
    @classmethod
    def parse_contract_schema(cls, data):
        if not isinstance(data, dict):
            return data
        # Catalog response subclasses have presentation-only fields outside the contract.
        fields = set(ModuleDefinitionV3.model_fields) | set(ModuleDefinitionV4.model_fields)
        core = {key: value for key, value in data.items() if key in fields}
        schema = core.get("schema_version", 1)
        parser = {1: ModuleDefinitionV1, 2: ModuleDefinitionV2, 3: ModuleDefinitionV3, 4: ModuleDefinitionV4}.get(schema) if isinstance(schema, (int, float)) else None
        if parser is None:
            raise ValueError(f"不支持的模块合同 schema_version：{schema}")
        if schema == 1:
            core.setdefault("runtime", cls.model_fields["runtime"].default)
        parsed = parser.model_validate(core).model_dump(mode="python")
        return {**data, **parsed}


class CanonicalUnitConversion(StrictModel):
    from_unit: str
    to_unit: str
    scale: float = Field(gt=0)
    offset: float = 0.


class ModuleMigration(StrictModel):
    parameters: dict[Identifier, Identifier | None] = Field(default_factory=dict)
    ports: dict[Identifier, Identifier | None] = Field(default_factory=dict)
    channels: dict[Identifier, Identifier | None] = Field(default_factory=dict)
    variables: dict[str, str | None] = Field(default_factory=dict)
    defaults: dict[Identifier, Any] = Field(default_factory=dict)
    unit_conversions: dict[Identifier, CanonicalUnitConversion] = Field(default_factory=dict)
    script_sources: dict[Identifier, str] = Field(default_factory=dict)


class ModuleManifest(ModuleDefinition):
    """Public name for a module package manifest."""

    runtime: Literal["builtin", "python"] = "python"


class ModuleValidationEvidence(StrictModel):
    level: Literal['L1','L2','L3','L4','external']
    status: Literal['passed','failed','pending']
    source: str
    content_hash: str
    definition_hash: str
    input_hash: str
    engine_version: str
    sdk_version: str
    tolerances: dict[str, float] = Field(default_factory=dict)


class ModuleVersionInfo(StrictModel):
    package: ModulePackageRef
    created_at: str | None = None
    release_notes: str = ""
    tested: bool = False
    validation_evidence: list[ModuleValidationEvidence] = Field(default_factory=list)
