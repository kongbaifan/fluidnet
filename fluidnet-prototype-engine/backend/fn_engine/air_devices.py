"""风侧设备纯函数。只生成候选出口与独立源汇，不提交累计量。"""
from dataclasses import dataclass, field

from scipy.optimize import brentq

from .models import FluidState
from .moist_air import AirPropertyError, MoistAirService, liquid_enthalpy, saturation_humidity_ratio


@dataclass
class AirDeviceResult:
    outlet_state: FluidState
    heat_to_air_w: float = 0.
    water_added_kg_s: float = 0.
    water_removed_kg_s: float = 0.
    removed_water_enthalpy_j_kg: float = 0.
    outputs: dict = field(default_factory=dict)


def evaluate_cooling_coil(inlet, dry_air_flow_kg_s, parameters, pressure_pa=None, service=None):
    service = service or MoistAirService()
    p = inlet.pressure_pa if pressure_pa is None else pressure_pa
    m, t, w, h = dry_air_flow_kg_s, inlet.temperature_k, inlet.humidity_ratio_kg_kg, inlet.enthalpy_j_kg_dry_air
    adp, bf = parameters['coil_surface_temperature_k'], parameters['bypass_factor']
    if not 273.15 <= adp <= 323.15 or not 0 <= bf <= 1:
        raise AirPropertyError('AIR_COIL_PARAMETERS', '盘管表面必须在 0–50 °C、旁通系数在 0–1 内；不支持结霜')
    if m < -1e-10:
        raise AirPropertyError('AIR_REVERSE_FLOW_UNSUPPORTED', '表冷器不支持反向流动')
    active = m > 1e-10 and t > adp and bf < 1
    wet = active and w > saturation_humidity_ratio(adp, p)
    if wet:
        saturated = service.saturated_state(p, adp)
        wo = bf*w + (1-bf)*saturated.humidity_ratio_kg_kg
        ho = bf*h + (1-bf)*saturated.enthalpy_j_kg_dry_air
        outlet = service.state_phw(p, ho, wo)
    elif active:
        outlet = service.state_ptw(p, adp+bf*(t-adp), w)
    else:
        outlet = service.state_phw(p, h, w)
    condensate = max(m, 0)*(w-outlet.humidity_ratio_kg_kg)
    total = max(m, 0)*(h-outlet.enthalpy_j_kg_dry_air) if active else 0.
    removed_h = liquid_enthalpy(adp)
    cooling = total-condensate*removed_h
    sensible = (max(m, 0)*(service.state_ptw(p,t,outlet.humidity_ratio_kg_kg).enthalpy_j_kg_dry_air
                          -outlet.enthalpy_j_kg_dry_air)) if wet else total
    return AirDeviceResult(outlet, -cooling, water_removed_kg_s=condensate,
        removed_water_enthalpy_j_kg=removed_h, outputs={
            'total_heat_w': total, 'sensible_heat_w': sensible, 'latent_heat_w': total-sensible,
            'condensate_kg_s': condensate, 'shr': sensible/total if total > 1e-3 else None,
            'cooling_load_w': cooling, 'condensate_enthalpy_flow_w': condensate*removed_h,
            'outlet_humidity_ratio_kg_kg': outlet.humidity_ratio_kg_kg, 'wet': bool(wet), 'active': bool(active)})


def evaluate_humidifier(inlet, dry_air_flow_kg_s, parameters, pressure_pa=None, service=None):
    service = service or MoistAirService()
    p = inlet.pressure_pa if pressure_pa is None else pressure_pa
    m, t, w, h = dry_air_flow_kg_s, inlet.temperature_k, inlet.humidity_ratio_kg_kg, inlet.enthalpy_j_kg_dry_air
    mode, action = parameters['mode'], parameters.get('saturation_action', 'limit')
    delta = parameters['moisture_addition_kg_kg']
    if mode not in ('adiabatic', 'isothermal') or action not in ('limit', 'error') or not 0 <= delta <= .05:
        raise AirPropertyError('AIR_HUMIDIFIER_PARAMETERS', '加湿模式、饱和策略或请求含湿量无效')
    if m < -1e-10:
        raise AirPropertyError('AIR_REVERSE_FLOW_UNSUPPORTED', '加湿器不支持反向流动')
    if m <= 1e-10:
        return AirDeviceResult(service.state_phw(p,h,w), outputs={
            'requested_moisture_kg_s': 0., 'moisture_addition_kg_s': 0., 'limited': False})
    if mode == 'isothermal':
        maximum = min(.05, saturation_humidity_ratio(t,p))
    else:
        # 等焓线与饱和线的交点。只在已验证温度区间内有界求根。
        from .moist_air import _ha
        def residual(temperature):
            return _ha('H','P',p,'T',temperature,'R',1.)-h
        if residual(253.15) > 0:
            raise AirPropertyError('AIR_PROPERTY_RANGE', '等焓加湿极限低于湿空气温度包络')
        ts = brentq(residual,253.15,min(t+1.,333.15),xtol=1e-10)
        maximum = min(.05,saturation_humidity_ratio(ts,p))
    available = max(0.,maximum-w)
    limited = delta > available+1e-11
    if limited and action == 'error':
        raise AirPropertyError('HUMIDIFIER_SATURATION_LIMIT', '请求加湿量超过饱和极限')
    actual = min(delta,available)
    outlet = (service.state_ptw(p,t,w+actual) if mode == 'isothermal'
              else service.state_phw(p,h,w+actual))
    heat = m*(outlet.enthalpy_j_kg_dry_air-h) if mode == 'isothermal' else 0.
    return AirDeviceResult(outlet, heat, water_added_kg_s=m*actual, outputs={
        'requested_moisture_kg_s': m*delta, 'moisture_addition_kg_s': m*actual, 'limited': limited})


def evaluate_pass_through(inlet, mass, pressure, heat, service):
    if mass <= 1e-10 and abs(heat) > 1e-8:
        raise AirPropertyError('ZERO_FLOW_HEAT_INPUT', '零流量通路不能持续加热或冷却')
    h = inlet.enthalpy_j_kg_dry_air + (heat/mass if mass > 1e-10 else 0.)
    return AirDeviceResult(service.state_phw(pressure,h,inlet.humidity_ratio_kg_kg),heat)
