"""Role negotiation and numeric validation, with no solver/EOS or user-code imports."""
import hashlib
import math

from ._module_schema_v1 import ParameterSpec
from ._module_schema_v4 import THROTTLE_ROLE
from .module_contracts import ModuleCompatibilityError, check_module_compatibility, definition_hash
from .refrigeration_models import RefrigerationThrottleFlow, RefrigerationThrottleInput

RESERVED_FLOW_VARIABLES = {'mass_flow_kg_s','effective_kv_m3_h','pressure_drop_pa','enthalpy_j_kg','outlet_quality'}


def require_throttle_role(definition):
    if definition.schema_version != 4 or definition.execution_role != THROTTLE_ROLE:
        raise ModuleCompatibilityError('MODULE_REFRIGERATION_ROLE_REQUIRED',
            '此调用要求 schema 4 的等焓节流角色','execution_role')
    check_module_compatibility(definition)
    source = definition.source.get('runtime','')
    if isinstance(source,list): source='\n'.join(source)
    if not source.strip() or not definition.entrypoint:
        raise ModuleCompatibilityError('MODULE_ENTRYPOINT_MISSING','制冷设备必须有入口和 runtime 源码','entrypoint')
    if definition.content_hash and hashlib.sha256(source.encode('utf-8')).hexdigest()!=definition.content_hash:
        raise ModuleCompatibilityError('MODULE_HASH_MISMATCH','制冷模块源码哈希不一致','content_hash')
    if definition.definition_hash and definition_hash(definition)!=definition.definition_hash:
        raise ModuleCompatibilityError('MODULE_DEFINITION_HASH_MISMATCH','制冷模块定义哈希不一致','definition_hash')


def role_parameters(definition, overrides):
    declared = {p.id:p for p in definition.parameters}
    unknown = set(overrides)-declared.keys()
    if unknown:
        raise ModuleCompatibilityError('PARAMETER_UNKNOWN',f'未声明的制冷设备参数：{sorted(unknown)}','parameters')
    result = {key:overrides.get(key,spec.default) for key,spec in declared.items()}
    for key,spec in declared.items():
        try:
            ParameterSpec.model_validate({**spec.model_dump(),'default':result[key]})
        except ValueError as error:
            raise ModuleCompatibilityError('PARAMETER_RANGE',f'制冷参数 {key}：{error}',f'parameters.{key}') from error
    return result


def role_fluid(definition, fluid, port_fluids=None):
    if fluid.phase_policy!='any':
        raise ModuleCompatibilityError('MODULE_REFRIGERATION_FLUID_REQUIRED',
            '制冷节流需要允许饱和液体与两相出口的回路工质（phase_policy=any）','fluid.phase_policy')
    if definition.applicability.fluids and fluid.fluid.casefold() not in {name.casefold() for name in definition.applicability.fluids}:
        raise ModuleCompatibilityError('MODULE_FLUID_UNSUPPORTED',f'模块不支持工质 {fluid.fluid}','applicability.fluids')
    if any(key not in {'in0','out0'} or value!=fluid for key,value in (port_fluids or {}).items()):
        raise ModuleCompatibilityError('MODULE_REFRIGERATION_FLUID_CONFLICT',
            '等焓节流的两端必须属于同一制冷剂回路','port_fluids')


def updated_role_parameters(definition, current, changes):
    result = role_parameters(definition,{**current,**changes})
    for spec in definition.parameters:
        if result[spec.id]!=current[spec.id] and not (spec.runtime and spec.writable):
            raise ModuleCompatibilityError('MODULE_PARAMETER_IMMUTABLE',
                f'制冷参数 {spec.id} 不允许在运行中修改',f'parameters.{spec.id}')
    return result


def validate_throttle_input(value, parameters):
    value = RefrigerationThrottleInput.model_validate(value.model_dump() if isinstance(value,RefrigerationThrottleInput) else value)
    if value.opening_ratio!=parameters['opening_ratio'] or value.rated_kv_m3_h!=parameters['kv_m3_h']:
        raise ModuleCompatibilityError('MODULE_REFRIGERATION_INPUT_STALE',
            '制冷输入的开度或额定 Kv 与当前参数不一致','throttle')
    return value


def validate_throttle_flow(value, inlet):
    flow = RefrigerationThrottleFlow.model_validate(value.model_dump() if isinstance(value,RefrigerationThrottleFlow) else value)
    if flow.effective_kv_m3_h>inlet.rated_kv_m3_h:
        raise ModuleCompatibilityError('MODULE_REFRIGERATION_OUTPUT_INVALID','有效 Kv 超出额定值','flow.effective_kv_m3_h')
    drop = inlet.inlet_pressure_pa-inlet.outlet_pressure_pa
    expected = flow.effective_kv_m3_h/3600*math.sqrt(1000*inlet.inlet_density_kg_m3*max(drop,0)/1e5)
    if inlet.opening_ratio==0 and (flow.mass_flow_kg_s!=0 or flow.effective_kv_m3_h!=0) or \
            not math.isclose(flow.mass_flow_kg_s,expected,rel_tol=1e-10,abs_tol=1e-12) or drop<=0 and flow.mass_flow_kg_s!=0:
        raise ModuleCompatibilityError('MODULE_REFRIGERATION_OUTPUT_INVALID',
            '流量不满足单向、零开度关断及有效 Kv 关系','flow.mass_flow_kg_s')
    return flow


class RefrigerationCollector:
    def __init__(self, throttle):
        self._throttle = throttle
        self.result = None

    @property
    def throttle(self):
        return self._throttle

    def flow(self, *, mass_flow_kg_s, effective_kv_m3_h):
        if self.result is not None:
            raise ModuleCompatibilityError('MODULE_REFRIGERATION_OUTPUT_DUPLICATE',
                '一次制冷求值只能提交一个流量结果','flow')
        self.result = validate_throttle_flow({'mass_flow_kg_s':mass_flow_kg_s,'effective_kv_m3_h':effective_kv_m3_h},self._throttle)
