"""水冷冷水机组：单级蒸气压缩循环与蒸发器、冷凝器两条水通路。

蒸发器、冷凝器按等温制冷剂侧 ε = 1 − exp(−UA/C_水)。机组把冷冻水出水温度压到设定值；
满载仍达不到时出水温度上漂（capacity_limited）。负荷比在 0–1 连续变化，不模拟最小负荷启停。
Q冷凝 = Q蒸发 + 压缩轴功；电机损失进入机房，不进入任何水回路。
"""
import math

from scipy.optimize import brentq

from .models import FluidConfig
from .properties import property_service
from .refrigeration.cycle import DeviceRangeError, check_envelope, cycle_point, cycle_rates, rated_displacement

LOWEST_EVAPORATING_K = 233.15
OUTPUT_KEYS = ('cooling_power_w', 'condenser_heat_w', 'shaft_power_w', 'electric_power_w', 'cop', 'load_ratio',
               'capacity_limited', 'evaporating_temperature_k', 'condensing_temperature_k', 'evaporating_pressure_pa',
               'condensing_pressure_pa', 'discharge_temperature_k', 'pressure_ratio', 'refrigerant_mass_flow_kg_s',
               'evaporator_equation_residual_w', 'condenser_equation_residual_w')


def refrigerant_service(parameters):
    return property_service(FluidConfig(fluid=parameters['refrigerant'], phase_policy='any'))


def _effectiveness(ua, capacity):
    return -math.expm1(-ua/capacity)


def _idle(evaporator_inlet, condenser_inlet):
    values = dict.fromkeys(OUTPUT_KEYS, 0.)
    values.update(capacity_limited=False, cop=None, evaporating_temperature_k=None, condensing_temperature_k=None,
                  evaporating_pressure_pa=None, condensing_pressure_pa=None, discharge_temperature_k=None,
                  pressure_ratio=None)
    return {'active': False, 'evaporator_outlet_h': evaporator_inlet.enthalpy_j_kg,
            'condenser_outlet_h': condenser_inlet.enthalpy_j_kg, 'outputs': values}


def _condensing(service, params, displacement, t_evap, t_water, conductance, rejection):
    """冷凝温度：冷却水吸热 conductance·(Tc − Tw) 等于循环排热 rejection(满载循环速率)。"""
    def residual(t_cond):
        return conductance*(t_cond-t_water)-rejection(cycle_rates(service, params, displacement, t_evap, t_cond, 1.))
    low = max(t_water, t_evap)+1e-3
    high = low+5.
    while True:
        try:
            if residual(high) > 0:
                break
        except DeviceRangeError as error:
            raise DeviceRangeError('CHILLER_CONDENSER_INFEASIBLE', f'冷却水不能在可求物性的冷凝温度内带走排热：{error}',
                                   field='condenser_ua_w_k') from error
        low, high = high, high+5.
    try:
        residual(low)
    except DeviceRangeError as error:
        raise DeviceRangeError('CHILLER_CONDENSER_INFEASIBLE', f'冷凝温度下界无法求循环：{error}') from error
    return brentq(residual, low, high, xtol=1e-9)


def evaluate_chiller(evaporator_inlet, evaporator_flow_kg_s, condenser_inlet, condenser_flow_kg_s, parameters,
                     evaporator_service, evaporator_outlet_pressure_pa, check=False):
    """给定两侧进水状态求出水焓与机组输出；`check` 为真时按声明运行范围拒绝外推点。"""
    p = parameters
    flow_eps = 1e-9
    if evaporator_flow_kg_s < -flow_eps or condenser_flow_kg_s < -flow_eps:
        raise DeviceRangeError('CHILLER_REVERSE_FLOW', '冷水机组两侧都不支持反向流动')
    if p['running'] < .5 or evaporator_flow_kg_s <= flow_eps:
        return _idle(evaporator_inlet, condenser_inlet)
    setpoint_h = evaporator_service.state_pt(evaporator_outlet_pressure_pa, p['chilled_water_setpoint_k']).enthalpy_j_kg
    target = evaporator_flow_kg_s*(evaporator_inlet.enthalpy_j_kg-setpoint_h)
    if target <= 1e-3:
        return _idle(evaporator_inlet, condenser_inlet)
    if condenser_flow_kg_s <= flow_eps:
        raise DeviceRangeError('CHILLER_CONDENSER_NO_FLOW', '冷水机组有制冷负荷但冷却水流量为零，无法排热')
    service = refrigerant_service(p)
    displacement = rated_displacement(service, p)
    c_e = evaporator_flow_kg_s*evaporator_inlet.specific_heat_j_kg_k
    c_c = condenser_flow_kg_s*condenser_inlet.specific_heat_j_kg_k
    g_e = _effectiveness(p['evaporator_ua_w_k'], c_e)*c_e
    g_c = _effectiveness(p['condenser_ua_w_k'], c_c)*c_c
    t_ei, t_ci = evaporator_inlet.temperature_k, condenser_inlet.temperature_k
    if g_e <= 0 or g_c <= 0:
        raise DeviceRangeError('CHILLER_PARAMETERS', '蒸发器与冷凝器 UA 必须为正')

    def full_load(t_evap):
        """满载时蒸发温度 t_evap 下的 (冷凝温度, 制冷量)。"""
        t_cond = _condensing(service, p, displacement, t_evap, t_ci, g_c, lambda rates: rates['rejection_w'])
        return t_cond, cycle_rates(service, p, displacement, t_evap, t_cond, 1.)['cooling_w']

    t_evap = t_ei-target/g_e
    if t_evap <= LOWEST_EVAPORATING_K:
        raise DeviceRangeError('CHILLER_EVAPORATOR_INFEASIBLE', '蒸发器 UA 过小：达到设定出水温度所需蒸发温度低于 −40 °C',
                               field='evaporator_ua_w_k')
    # 定 Te 时制冷量与排热都和负荷比成正比：制冷量等于 target 时排热为 target·Q排/Q制冷。
    t_cond = _condensing(service, p, displacement, t_evap, t_ci, g_c,
                         lambda rates: target*rates['rejection_w']/rates['cooling_w'])
    load = target/cycle_rates(service, p, displacement, t_evap, t_cond, 1.)['cooling_w']
    limited = load > 1.
    if limited:
        load = 1.

        # 满载制冷量随 Te 升高而增大、蒸发器所需换热随 Te 升高而减小：在 Te_设定 处不足，接近进水温度时富余。
        def surplus(value):
            return full_load(value)[1]-g_e*(t_ei-value)
        high = t_ei-1e-3
        if surplus(high) <= 0:
            raise DeviceRangeError('CHILLER_EVAPORATOR_INFEASIBLE', '满载工况下找不到与冷冻水平衡的蒸发温度')
        t_evap = brentq(surplus, t_evap, high, xtol=1e-9)
        t_cond = full_load(t_evap)[0]
    point = cycle_point(service, p, displacement, t_evap, t_cond, load)
    if check:
        check_envelope(p, point)
    cooling = point['cooling_power_w']
    rejection = point['condenser_heat_w']
    evaporator_h = evaporator_inlet.enthalpy_j_kg-cooling/evaporator_flow_kg_s
    condenser_h = condenser_inlet.enthalpy_j_kg+rejection/condenser_flow_kg_s
    outputs = {'cooling_power_w': cooling, 'condenser_heat_w': rejection, 'shaft_power_w': point['shaft_power_w'],
               'electric_power_w': point['electric_power_w'], 'cop': point['cop'], 'load_ratio': load,
               'capacity_limited': limited, 'evaporating_temperature_k': t_evap, 'condensing_temperature_k': t_cond,
               'evaporating_pressure_pa': point['evaporating_pressure_pa'],
               'condensing_pressure_pa': point['condensing_pressure_pa'],
               'discharge_temperature_k': point['discharge_temperature_k'], 'pressure_ratio': point['pressure_ratio'],
               'refrigerant_mass_flow_kg_s': point['mass_flow_kg_s'],
               'evaporator_equation_residual_w': g_e*(t_ei-t_evap)-cooling,
               'condenser_equation_residual_w': g_c*(t_cond-t_ci)-rejection}
    return {'active': True, 'evaporator_outlet_h': evaporator_h, 'condenser_outlet_h': condenser_h, 'outputs': outputs}
