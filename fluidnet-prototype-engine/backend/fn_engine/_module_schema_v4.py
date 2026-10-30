"""Schema 4: explicit refrigeration roles; schemas 1/2/3 remain frozen."""
from typing import Literal

from pydantic import Field, model_validator

from ._module_schema_v1 import ModuleFieldsV1, StrictModel
from ._module_schema_v2 import ModuleSDKRequirements

THROTTLE_ROLE = 'refrigeration.isenthalpic_throttle.v1'
THROTTLE_CAPABILITY = 'refrigeration.throttle.v1'
_DOMAINS:tuple[Literal['refrigeration'],...] = ('refrigeration',)


class RefrigerationApplicability(StrictModel):
    execution_domains: list[Literal['refrigeration']] = Field(default_factory=lambda:list(_DOMAINS),min_length=1,max_length=1)
    fluids: list[str] = Field(default_factory=list,max_length=64)
    assumptions: list[str] = Field(default_factory=list,max_length=32)


class ModuleDefinitionV4(ModuleFieldsV1):
    schema_version: Literal[4] = 4
    sdk: ModuleSDKRequirements
    runtime: Literal['python'] = Field(...)
    execution_role: Literal['refrigeration.isenthalpic_throttle.v1']
    applicability: RefrigerationApplicability = Field(default_factory=RefrigerationApplicability)
    solver_model: Literal['generic'] = 'generic'
    state_model: None = None
    thermal_model: None = None
    source_format: Literal['python-v1'] = 'python-v1'
    channels: list = Field(default_factory=list,max_length=0)

    @model_validator(mode='after')
    def validate_role(self):
        expected = {('in0','refrigerant','in',True,'refrigerant'),('out0','refrigerant','out',True,'refrigerant')}
        if {(p.id,p.domain,p.direction,p.required,p.circuit) for p in self.ports} != expected:
            raise ValueError('制冷节流角色必须有 in0/out0 两个必连制冷剂端口，方向为 in/out，属于同一 refrigerant 回路')
        specs = {p.id:p for p in self.parameters}
        for name,quantity,unit in [('kv_m3_h','flow_coefficient','m³/h'),('opening_ratio','ratio','1')]:
            spec = specs.get(name)
            if spec is None or spec.value_type != 'number' or spec.unit is None or \
                    spec.unit.quantity != quantity or spec.unit.canonical_unit != unit:
                raise ValueError(f'制冷节流参数 {name} 必须为数值，规范单位为 {unit}（{quantity}）')
        kv,opening = specs['kv_m3_h'],specs['opening_ratio']
        if kv.minimum is None or kv.minimum <= 0 or kv.runtime:
            raise ValueError('额定 Kv 必须声明正下限，且不能在运行中修改')
        if opening.minimum is None or opening.maximum is None or opening.minimum < 0 or opening.maximum > 1 \
                or not opening.runtime or not opening.writable:
            raise ValueError('开度必须可在运行中写入，且声明范围包含于 0–1')
        return self
