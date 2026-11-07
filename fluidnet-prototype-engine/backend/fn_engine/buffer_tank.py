"""Fixed thermal-mass, perfectly mixed liquid buffer; no pressure or mass storage.

The stored quantity M*h uses the incompressible sensible-heat approximation. Network
pressure determines the liquid state; expansion and pressure work are outside this model.
"""
from scipy.optimize import brentq

from .compiler import CompilationError
from .model_types.module import ModuleDefinition
from ._module_schema_v1 import VariableSpec
from .properties import PropertyError


def definition():
    from .catalog import _celsius, channel, number, ports
    parameters = [
        number('mass_kg', '固定液体热质量', 1000., 'mass', 'kg', minimum=.001),
        _celsius('temperature_k', '初始混合温度', 293.15),
        _celsius('minimum_temperature_k', '最低适用温度', 274.15),
        _celsius('maximum_temperature_k', '最高适用温度', 363.15),
        number('heat_loss_ua_w_k', '对环境散热 UA', 0., 'conductance', 'W/K', minimum=0.),
        _celsius('ambient_temperature_k', '环境温度', 293.15, runtime=True),
        number('heat_input_w', '外部加热功率', 0., 'power', 'W', 'kW', 1000., runtime=True),
        number('loss_coefficient', '两口局部阻力 K', 2., 'ratio', '1', minimum=0.),
        number('diameter_m', '接口等效内径', .05, 'length', 'm', 'mm', .001, .001)]
    variables = [VariableSpec(id='param.' + p.id, label=p.label, source='parameter', parameter_id=p.id,
                              quantity=p.unit.quantity, unit=p.unit) for p in parameters]
    from .catalog import _var
    variables.extend([
        _var('state.temperature_k', '混合液温度', 'temperature', 'K', '°C', offset=-273.15, source='state'),
        _var('state.mass_kg', '固定热质量', 'mass', 'kg', source='state'),
        _var('state.enthalpy_j_kg', '混合液比焓', 'specific_enthalpy', 'J/kg', 'kJ/kg', 1000., source='state'),
        _var('state.stored_energy_j', '焓储能 M·h（同一物性基准）', 'energy', 'J', 'MJ', 1e6, source='state'),
        _var('state.stored_power_w', '本步储热功率', 'power', 'W', 'kW', 1000., source='state'),
        _var('ambient_heat_loss_w', '向环境散热（正为散出）', 'power', 'W', 'kW', 1000.),
        _var('energy_residual_w', '混合储热方程残差', 'power', 'W')])
    return ModuleDefinition(id='closed_buffer_tank', name='闭式缓冲水箱（定热质量）', category='热力设备',
        solver_model='closed_buffer_tank', state_model='mixed_liquid_buffer', ports=ports('in0', 'out0'),
        channels=[channel('ch0', 'resistance')], parameters=parameters, variables=variables,
        description='双口充分混合液体储热，显式固定热质量；水力压力由外网给定，两口流量相等。'
                    '仅普通单相液体动态，不提供压力参考或质量储存，不计算热膨胀、气垫或分层。')


def validate(parameters, service, pressure_pa, instance_id):
    p = parameters
    if not p['minimum_temperature_k'] <= p['temperature_k'] <= p['maximum_temperature_k'] or (
            p['minimum_temperature_k'] >= p['maximum_temperature_k']):
        raise CompilationError('BUFFER_TEMPERATURE_RANGE', '初温须位于有效的温度上下限之间', instance_id)
    for temperature in (p['minimum_temperature_k'], p['temperature_k'], p['maximum_temperature_k']):
        liquid_state(service, pressure_pa, temperature, instance_id)


def hydronic_definition():
    value = definition().model_copy(deep=True)
    value.id = 'hydronic_buffer_tank'
    value.name = '风水联算混合缓冲箱'
    value.description = ('独立液体回路中的双口固定热质量缓冲箱，支持普通液体及风水动态联算；'
                         '混合焓与房间热湿在同一接受步提升。不提供压力参考、质量库存、分层或热膨胀。')
    return value


def liquid_state(service, pressure_pa, temperature_k, instance_id):
    try:
        state = service.state_pt(pressure_pa, temperature_k)
    except PropertyError as error:
        raise CompilationError(error.code, f'{instance_id} 缓冲液体物性不可用：{error}', instance_id) from error
    if state.phase not in ('liquid', 'supercritical_liquid') or (
            state.quality is not None and 0. <= state.quality <= 1.):
        raise CompilationError('BUFFER_LIQUID_REQUIRED', '缓冲水箱只允许单相液体，不能使用气体或两相状态', instance_id)
    return state


def candidate(parameters, service, pressure_pa, inlet_h, flow_kg_s, old_h=None, dt_s=None, instance_id='buffer'):
    """Pure implicit-Euler trial, including zero flow. Nothing is committed here."""
    p = parameters
    if old_h is None:
        state = liquid_state(service, pressure_pa, p['temperature_k'], instance_id)
        stored, residual = 0., 0.
    else:
        if dt_s is None or dt_s <= 0:
            raise ValueError('缓冲储热推进需要正时间步')
        def residual_at(temperature):
            value = liquid_state(service, pressure_pa, temperature, instance_id)
            return (p['mass_kg'] * (value.enthalpy_j_kg - old_h) / dt_s
                    - flow_kg_s * (inlet_h - value.enthalpy_j_kg) - p['heat_input_w']
                    + p['heat_loss_ua_w_k'] * (temperature - p['ambient_temperature_k']))
        low, high = p['minimum_temperature_k'], p['maximum_temperature_k']
        if residual_at(low) > 0 or residual_at(high) < 0:
            raise CompilationError('BUFFER_TEMPERATURE_RANGE', '候选混合温度超出水箱适用范围，拒绝该子步', instance_id)
        temperature = brentq(residual_at, low, high, xtol=1e-10)
        state = liquid_state(service, pressure_pa, temperature, instance_id)
        stored = p['mass_kg'] * (state.enthalpy_j_kg - old_h) / dt_s
        residual = residual_at(temperature)
    loss = p['heat_loss_ua_w_k'] * (state.temperature_k - p['ambient_temperature_k'])
    outputs = {'state.mass_kg': p['mass_kg'], 'state.temperature_k': state.temperature_k,
               'state.enthalpy_j_kg': state.enthalpy_j_kg, 'state.stored_energy_j': p['mass_kg'] * state.enthalpy_j_kg,
               'state.stored_power_w': stored, 'ambient_heat_loss_w': loss, 'energy_residual_w': residual}
    return state.enthalpy_j_kg, outputs
