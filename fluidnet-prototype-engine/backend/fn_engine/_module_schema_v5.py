"""Schema 5: pure compressor and condenser constitutive laws; storage remains host-owned."""
from typing import Literal

from pydantic import Field, model_validator

from ._module_schema_v1 import ModuleFieldsV1
from ._module_schema_v2 import ModuleSDKRequirements
from ._module_schema_v4 import RefrigerationApplicability

PHYSICS_CAPABILITY = 'refrigeration.constitutive.v1'
COMPRESSOR_ROLE = 'refrigeration.compressor.v1'
CONDENSER_ROLE = 'refrigeration.condenser.v1'


class ModuleDefinitionV5(ModuleFieldsV1):
    schema_version: Literal[5] = 5
    sdk: ModuleSDKRequirements
    runtime: Literal['python'] = Field(...)
    execution_role: Literal['refrigeration.compressor.v1', 'refrigeration.condenser.v1']
    applicability: RefrigerationApplicability = Field(default_factory=RefrigerationApplicability)
    solver_model: Literal['generic'] = 'generic'
    state_model: None = None
    thermal_model: None = None
    source_format: Literal['python-v1'] = 'python-v1'
    channels: list = Field(default_factory=list, max_length=0)

    @model_validator(mode='after')
    def validate_role(self):
        inlet, outlet = ('suction', 'discharge') if self.execution_role == COMPRESSOR_ROLE else ('in0', 'out0')
        expected = {(inlet, 'refrigerant', 'in', True, 'refrigerant'),
                    (outlet, 'refrigerant', 'out', True, 'refrigerant')}
        if {(p.id, p.domain, p.direction, p.required, p.circuit) for p in self.ports} != expected:
            raise ValueError(f'制冷本构角色要求 {inlet}/{outlet} 两个同回路必连制冷剂端口')
        specs = {p.id: p for p in self.parameters}
        required = ('running', 'load_ratio') if self.execution_role == COMPRESSOR_ROLE else ('wet_bulb_temperature_k',)
        for name in required:
            spec = specs.get(name)
            unit = 'K' if name.endswith('_k') else '1'
            if spec is None or spec.value_type != 'number' or spec.unit is None or spec.unit.canonical_unit != unit:
                raise ValueError(f'角色参数 {name} 必须声明规范单位 {unit}')
            if spec.minimum is None or spec.minimum < 0:
                raise ValueError(f'角色参数 {name} 必须声明非负下限')
        return self
