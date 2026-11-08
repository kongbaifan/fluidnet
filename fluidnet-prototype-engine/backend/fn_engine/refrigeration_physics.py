"""Schema-5 finite-SI constitutive messages and parent-side conservation checks."""
from copy import deepcopy
import math

from pydantic import ConfigDict, Field

from ._module_schema_v1 import StrictModel
from ._module_schema_v5 import COMPRESSOR_ROLE
from .refrigeration_models import PhysicsInput
from .model_types.base import Diagnostic
from .model_types.protocol import ModuleRequestContext
from .module_contracts import ModuleCompatibilityError


def model_kind(definition):
    return ('expansion_valve' if definition.schema_version == 4 else
            'refrigerant_compressor' if definition.execution_role == COMPRESSOR_ROLE else 'evaporative_condenser')


def inlet_port(definition):
    return 'suction' if definition.execution_role == COMPRESSOR_ROLE else 'in0'




class PhysicsResult(StrictModel):
    model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False, strict=True)
    mass_flow_kg_s: float = Field(ge=0, default=0.)
    outlet_enthalpy_j_kg: float
    shaft_power_w: float = Field(ge=0, default=0.)
    electric_power_w: float = Field(ge=0, default=0.)
    heat_rejection_w: float = 0.


class PhysicsRequest(StrictModel):
    run_id: str
    instance_id: str
    iteration_id: int = Field(ge=0)
    time_s: float = Field(ge=0)
    point: PhysicsInput
    state_revision: int = Field(ge=0)
    context: ModuleRequestContext | None = None


class PhysicsResponse(StrictModel):
    result: PhysicsResult
    variables: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


RESERVED = {'mass_flow_kg_s', 'outlet_enthalpy_j_kg', 'shaft_power_w', 'electric_power_w',
            'heat_rejection_w', 'suction_enthalpy_j_kg', 'discharge_enthalpy_j_kg',
            'discharge_temperature_k', 'pressure_ratio', 'running', 'fan_power_w', 'condensing_temperature_k'}


def validate_result(value, point):
    r = PhysicsResult.model_validate(value.model_dump() if isinstance(value, PhysicsResult) else value)
    def require(condition, message):
        if not condition:
            raise ModuleCompatibilityError('MODULE_PHYSICS_OUTPUT_INVALID', message, 'result')
    if point.kind == 'compressor':
        require(r.heat_rejection_w == 0., '绝热压缩机不能隐含向外传热')
        require(math.isclose(r.shaft_power_w, r.mass_flow_kg_s * (r.outlet_enthalpy_j_kg - point.inlet_enthalpy_j_kg),
                            rel_tol=1e-9, abs_tol=1e-6), '压缩机轴功与流股焓升不守恒')
        require(r.electric_power_w + 1e-9 >= r.shaft_power_w, '压缩机输入电功不能小于轴功')
        require(r.mass_flow_kg_s == 0. or point.outlet_pressure_pa > point.inlet_pressure_pa, '压缩机要求正压升')
        require(r.mass_flow_kg_s == 0. or r.outlet_enthalpy_j_kg >= point.isentropic_outlet_enthalpy_j_kg - 1e-6,
                '压缩机排气焓低于等熵下限')
        require(point.enabled or (r.mass_flow_kg_s == r.shaft_power_w == r.electric_power_w == 0.), '停机状态必须零流量零功率')
        require(r.mass_flow_kg_s > 0. or r.shaft_power_w == r.electric_power_w == 0., '零流量不能输出压缩功率')
    else:
        require(r.mass_flow_kg_s == r.shaft_power_w == 0., '冷凝器只返回容器热交换，不另造流量或轴功')
        require(r.outlet_enthalpy_j_kg == point.inlet_enthalpy_j_kg, '冷凝器不覆盖平台流股焓')
        require(r.heat_rejection_w * (point.inlet_temperature_k - point.sink_temperature_k) >= 0., '被动换热方向与温差冲突')
        require(point.inlet_temperature_k != point.sink_temperature_k or r.heat_rejection_w == 0., '零温差的被动换热必须为零')
    return r


class PhysicsCollector:
    def __init__(self, point):
        self.point = point
        self.result = None

    @property
    def throttle(self):
        # Existing failure capture records the complete frozen role input here.
        return self.point

    def balance(self, **values):
        if self.result is not None:
            raise ValueError('每次本构求值只能提交一次 balance')
        self.result = validate_result(values, self.point)


def validate_input(definition, parameters, point):
    from .refrigeration_roles import require_refrigeration_role
    require_refrigeration_role(definition)
    if definition.schema_version != 5:
        raise ValueError('本构协议仅支持 schema 5')
    expected = 'compressor' if definition.execution_role == COMPRESSOR_ROLE else 'condenser'
    enabled = parameters.get('running', 1.) >= .5 and parameters.get('load_ratio', 1.) > 0.
    if point.kind != expected or point.enabled != enabled or (expected == 'condenser' and
            point.sink_temperature_k != parameters['wet_bulb_temperature_k']):
        raise ModuleCompatibilityError('MODULE_PHYSICS_INPUT_STALE', '本构输入种类、启停或热沉与冻结参数不一致', 'point')
    if expected == 'condenser' and point.inlet_pressure_pa != point.outlet_pressure_pa:
        raise ModuleCompatibilityError('MODULE_PHYSICS_BOUNDARY_INVALID', '集总冷凝器两端必须属于同一饱和容器压力', 'point')


def evaluate_in_process(runner, request):
    from .runtime import ModuleContext, RuntimeErrorBase
    from .module_state import checked_result
    validate_input(runner.definition, runner.parameters, request.point)
    if not runner.initialized:
        runner.initialize()
    if (request.run_id, request.instance_id, request.state_revision) != (
            runner.execution.run_id, runner.execution.instance_id, runner.state_revision):
        raise RuntimeErrorBase('本构请求身份或状态修订不匹配', code='MODULE_REQUEST_CONFLICT')
    context = request.context or runner.execution.context()
    if context.accepted_time_s is not None and (context.accepted_time_s > request.time_s or
            context.accepted_time_s != (runner._last_committed_time_s or 0.)):
        raise RuntimeErrorBase('本构请求接受时刻不匹配', code='MODULE_REQUEST_CONFLICT')
    info = runner._info('evaluate', request.time_s, context, run_id=request.run_id,
        instance_id=request.instance_id, iteration_id=request.iteration_id, port_data='trial', state_data='input_copy')
    ctx = ModuleContext(deepcopy(runner.parameters), runner.fluid, state=deepcopy(runner.state),
                        execution=info, refrigeration_input=request.point)
    runner._invoke(getattr(runner.module, 'evaluate'), ctx)
    if ctx.net.relations or ctx.heat_w or ctx.derivatives or RESERVED & ctx.variables.keys():
        raise RuntimeErrorBase('本构角色不能覆盖平台物理字段或提交其他方程', code='MODULE_PHYSICS_OUTPUT_INVALID')
    if ctx.refrigeration.result is None:
        raise RuntimeErrorBase('本构求值没有提交 balance', code='MODULE_PHYSICS_OUTPUT_MISSING')
    response = PhysicsResponse(result=validate_result(ctx.refrigeration.result, request.point),
                               variables=ctx.variables, diagnostics=ctx.diagnostics)
    checked_result(response)
    return response


def evaluate_worker(runner, request):
    from .module_state import checked_result
    request = PhysicsRequest.model_validate(request)
    validate_input(runner.definition, runner.parameters, request.point)
    request = request.model_copy(deep=True, update={'context': request.context or runner.execution.context()})
    response = PhysicsResponse.model_validate(runner._request({'action': 'evaluate_physics', 'request': request.model_dump(mode='json')}))
    validate_result(response.result, request.point)
    checked_result(response)
    if RESERVED & response.variables.keys() or any(d.severity == 'error' for d in response.diagnostics):
        raise ValueError('本构响应包含平台保留字段或错误诊断')
    return response
