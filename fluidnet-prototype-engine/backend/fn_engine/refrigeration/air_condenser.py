"""A lumped air-cooled condenser with an explicit, external dry-air boundary.

The refrigerant side is isothermal at its pressure level's saturation temperature.
UA is a constant forced-air coil input, not a calibrated function of fan speed.
An optional natural-convection conductance is a separate parallel ambient path.
No refrigerant mass flow, outlet enthalpy, storage or air network is solved here.
"""
from collections.abc import Mapping
import math
from typing import Protocol

from ..model_types.module import ModuleDefinition
from .cycle import DeviceRangeError


DEFAULT_PARAMETERS = {
    'ua_w_k': 4000.,
    'rated_air_mass_flow_kg_s': 5.,
    'air_specific_heat_j_kg_k': 1006.,
    'air_inlet_temperature_k': 303.15,
    'fan_ratio': 1.,
    'fan_power_w': 1000.,
    'natural_ua_w_k': 0.,
}

OUTPUT_KEYS = (
    'heat_rejection_w', 'effective_ua_w_k', 'forced_heat_w', 'natural_heat_w',
    'condensing_temperature_k', 'air_inlet_temperature_k', 'air_outlet_temperature_k',
    'air_mass_flow_kg_s', 'air_capacity_rate_w_k', 'effectiveness', 'approach_k',
    'fan_power_w', 'reverse_heat_flow',
)


class SaturationService(Protocol):
    def saturation_t(self, pressure: float) -> float: ...


def _number(params: Mapping[str, float], key: str, minimum: float, *, positive: bool = False) -> float:
    try:
        value = float(params.get(key, DEFAULT_PARAMETERS[key]))
    except (TypeError, ValueError, OverflowError) as error:
        raise DeviceRangeError('AIR_CONDENSER_PARAMETER', f'{key} 必须为有限数值', field=key) from error
    if not math.isfinite(value) or value < minimum or positive and value == minimum:
        bound = '大于' if positive else '不小于'
        raise DeviceRangeError('AIR_CONDENSER_PARAMETER', f'{key} 必须为有限数值且{bound} {minimum:g}', field=key)
    return value


def condenser_duty(service: SaturationService, params: Mapping[str, float], pressure_pa: float) -> dict[str, float | None]:
    """Signed heat rejected from the refrigerant level, W; positive means rejection.

    Forced-air capacity rate C = rated_air_mass_flow * fan_ratio * cp. For the
    constant-temperature phase-change side, epsilon = 1-exp(-UA/C), so G = C*epsilon.
    Natural UA is independent of that air stream and applies at every fan speed.
    The reported outlet is coil-leaving air before fan heat, and is undefined at
    zero forced flow. All fan electrical input is dissipated to the environment;
    it is not added to the refrigerant heat balance.
    """
    ua = _number(params, 'ua_w_k', 0.)
    rated_flow = _number(params, 'rated_air_mass_flow_kg_s', 0., positive=True)
    cp = _number(params, 'air_specific_heat_j_kg_k', 0., positive=True)
    ambient = _number(params, 'air_inlet_temperature_k', 0., positive=True)
    fan = _number(params, 'fan_ratio', 0.)
    rated_power = _number(params, 'fan_power_w', 0.)
    natural_ua = _number(params, 'natural_ua_w_k', 0.)
    if fan > 1.:
        raise DeviceRangeError('AIR_CONDENSER_PARAMETER', '风机转速比须在 0–1 内；当前未标定超速工况', field='fan_ratio')
    if not math.isfinite(pressure_pa) or pressure_pa <= 0.:
        raise DeviceRangeError('AIR_CONDENSER_PRESSURE', '冷凝压力必须为有限正数')
    condensing = service.saturation_t(pressure_pa)
    if not math.isfinite(condensing) or condensing <= 0.:
        raise DeviceRangeError('AIR_CONDENSER_TEMPERATURE', '制冷剂饱和温度必须为有限正数')
    flow = rated_flow * fan
    capacity = flow * cp
    if not math.isfinite(capacity):
        raise DeviceRangeError('AIR_CONDENSER_PARAMETER', '空气热容量流率超出有限数值范围')
    effectiveness = -math.expm1(-ua / capacity) if capacity > 0. else 0.
    forced_conductance = capacity * effectiveness
    approach = condensing - ambient
    forced_heat = forced_conductance * approach
    natural_heat = natural_ua * approach
    result = {
        'heat_rejection_w': forced_heat + natural_heat,
        'effective_ua_w_k': forced_conductance + natural_ua,
        'forced_heat_w': forced_heat,
        'natural_heat_w': natural_heat,
        'condensing_temperature_k': condensing,
        'air_inlet_temperature_k': ambient,
        'air_outlet_temperature_k': ambient + effectiveness * approach if capacity > 0. else None,
        'air_mass_flow_kg_s': flow,
        'air_capacity_rate_w_k': capacity,
        'effectiveness': effectiveness,
        'approach_k': approach,
        'fan_power_w': rated_power * fan ** 3,
        'reverse_heat_flow': float(forced_heat + natural_heat < 0.),
    }
    if any(value is not None and not math.isfinite(value) for value in result.values()):
        raise DeviceRangeError('AIR_CONDENSER_RESULT', '风冷冷凝器结果超出有限数值范围')
    return result


def definition() -> ModuleDefinition:
    """Catalog factory; the catalog adds standard param.* variables to all devices."""
    # The helpers live in catalog.py, which also imports this factory when assembling
    # its definitions. Keep this dependency lazy to avoid an import-time cycle.
    from ..catalog import _celsius, _ratio, _stream, _var, number
    from .._module_schema_v1 import Direction

    defaults = DEFAULT_PARAMETERS
    return ModuleDefinition(id='air_cooled_condenser', name='风冷冷凝器', category='制冷站设备',
        solver_model='air_cooled_condenser',
        description='单一制冷剂压力等级上的饱和排热设备；环境干空气边界，按恒定 UA 与有限空气热容量流率计算。'
                    '有效掠过风量随转速变化，风机电功率按转速立方；可配置独立自然散热通道。'
                    '负排热表示环境反向加热，不截断。未解析实际风网、冷凝管路或厂家性能表。',
        ports=[_stream('in0', '排气进口', Direction.in_), _stream('out0', '冷凝液出口', Direction.out)],
        parameters=[
            number('ua_w_k', '强制风侧盘管 UA（恒定简化）', defaults['ua_w_k'], 'conductance', 'W/K', 'kW/K', 1000., minimum=0.),
            number('rated_air_mass_flow_kg_s', '额定有效掠过空气质量流量', defaults['rated_air_mass_flow_kg_s'], 'mass_flow', 'kg/s', minimum=1e-9),
            number('air_specific_heat_j_kg_k', '空气定压比热（恒定）', defaults['air_specific_heat_j_kg_k'], 'specific_heat', 'J/(kg·K)', 'kJ/(kg·K)', 1000., minimum=1e-9),
            _celsius('air_inlet_temperature_k', '环境进风干球温度', defaults['air_inlet_temperature_k'], runtime=True),
            _ratio('fan_ratio', '风机转速比', defaults['fan_ratio'], runtime=True),
            number('fan_power_w', '额定风机电功率', defaults['fan_power_w'], 'power', 'W', 'kW', 1000., minimum=0.),
            number('natural_ua_w_k', '独立自然散热导热系数（全转速，0 关闭）', defaults['natural_ua_w_k'], 'conductance', 'W/K', 'kW/K', 1000., minimum=0.),
        ],
        variables=[
            _var('heat_rejection_w', '净排热量（负值为环境加热）', 'power', 'W', 'kW', 1000.),
            _var('effective_ua_w_k', '总有效导热系数', 'conductance', 'W/K', 'kW/K', 1000.),
            _var('forced_heat_w', '强制风侧排热量', 'power', 'W', 'kW', 1000.),
            _var('natural_heat_w', '自然散热量', 'power', 'W', 'kW', 1000.),
            _var('condensing_temperature_k', '制冷剂饱和温度', 'temperature', 'K', '°C', offset=-273.15),
            _var('air_inlet_temperature_k', '环境进风干球温度', 'temperature', 'K', '°C', offset=-273.15),
            _var('air_outlet_temperature_k', '盘管出风温度（不含风机热）', 'temperature', 'K', '°C', offset=-273.15),
            _var('air_mass_flow_kg_s', '有效掠过空气质量流量', 'mass_flow', 'kg/s'),
            _var('air_capacity_rate_w_k', '空气热容量流率', 'conductance', 'W/K', 'kW/K', 1000.),
            _var('effectiveness', '强制风侧换热有效度', 'ratio', '1', '%', .01),
            _var('approach_k', '饱和温度减进风干球温度', 'temperature_difference', 'K'),
            _var('fan_power_w', '风机电功率', 'power', 'W', 'kW', 1000.),
            _var('reverse_heat_flow', '反向换热（1 为环境加热）', 'ratio', '1'),
            _var('state.heat_rejected_j', '累计净排热（可为负）', 'energy', 'J', 'kWh', 3600000., source='state'),
            _var('state.fan_energy_j', '累计风机电量', 'energy', 'J', 'kWh', 3600000., source='state'),
        ])
