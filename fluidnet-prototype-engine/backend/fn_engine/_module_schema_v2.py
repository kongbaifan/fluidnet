"""Frozen schema-2 module contract (MOD-S2); new semantics need a new schema."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._module_schema_v1 import ModuleFieldsV1, StrictModel


class ModuleSDKRequirements(StrictModel):
    api_version: str = Field(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
    capabilities: list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")]] = Field(default_factory=list)
    state_contract_version: int = Field(default=1, ge=1, strict=True)

    @model_validator(mode="after")
    def canonical_capabilities(self):
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("SDK 能力声明不能重复")
        self.capabilities = sorted(self.capabilities)
        return self


class ModuleDefinitionV2(ModuleFieldsV1):
    schema_version: Literal[2] = 2
    sdk: ModuleSDKRequirements
    runtime: Literal["python"] = Field(...)
