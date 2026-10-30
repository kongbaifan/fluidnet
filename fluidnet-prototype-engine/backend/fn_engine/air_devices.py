"""风侧设备纯函数。只生成候选出口与独立源汇，不提交累计量。"""
from dataclasses import dataclass, field
import math

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


def counterflow_effectiveness(ntu, ratio):
    """逆流换热器效能；ratio = C_min/C_max ∈ [0, 1]。"""
    if ntu <= 0:
        return 0.
    if ratio < 1e-12:
        return -math.expm1(-ntu)
    if abs(1-ratio) < 1e-9:
        return ntu/(1+ntu)
    exponential = math.exp(-ntu*(1-ratio))
    return (1-exponential)/(1-ratio*exponential)


def _transfer(ua, c_air, c_water):
    """逆流 ε–NTU 的传热导纳 ε·C_min（W/K 或以焓差为势时 kg/s）。"""
    low, high = min(c_air, c_water), max(c_air, c_water)
    if low <= 0 or ua <= 0:
        return 0.
    return counterflow_effectiveness(ua/low, low/high)*low


def evaluate_water_coil(inlet, dry_air_flow_kg_s, water_inlet_temperature_k, water_flow_kg_s, water_cp_j_kg_k,
                        parameters, pressure_pa=None, service=None):
    """冷/热水盘管：逆流，干段在进风端、湿段在进水端，交界处表面温度等于进风露点（部分湿工况）。

    干段为普通 ε–NTU；湿段为 Braun 焓效能法，饱和空气焓 h_s(T) 在段内进出水温之间按弦线斜率线性化，
    焓差为势、刘易斯数取 1；出风含湿量由湿段外侧 NTU 求得的等效表面状态给出。
    水侧得热 = 空气焓降 − 凝水携出焓，两本账同时闭合。
    """
    service = service or MoistAirService()
    p = inlet.pressure_pa if pressure_pa is None else pressure_pa
    ua_a, ua_w = parameters['air_side_ua_w_k'], parameters['water_side_ua_w_k']
    m, mw, tw = dry_air_flow_kg_s, water_flow_kg_s, water_inlet_temperature_k
    if ua_a < 0 or ua_w < 0:
        raise AirPropertyError('AIR_COIL_PARAMETERS', '盘管内外侧 UA 不能为负')
    if m < -1e-10:
        raise AirPropertyError('AIR_REVERSE_FLOW_UNSUPPORTED', '水盘管风侧不支持反向流动')
    if mw < -1e-10:
        raise AirPropertyError('AIR_REVERSE_FLOW_UNSUPPORTED', '水盘管水侧不支持反向流动')
    t, w, h = inlet.temperature_k, inlet.humidity_ratio_kg_kg, inlet.enthalpy_j_kg_dry_air
    idle = {'total_heat_w': 0., 'sensible_heat_w': 0., 'latent_heat_w': 0., 'condensate_kg_s': 0., 'shr': None,
            'cooling_load_w': 0., 'water_heat_w': 0., 'condensate_enthalpy_flow_w': 0.,
            'outlet_humidity_ratio_kg_kg': w, 'surface_temperature_k': None, 'wet': False, 'active': False,
            'wet_fraction': 0., 'saturation_limited': False}
    if m <= 1e-10 or mw <= 1e-10 or ua_a == 0 or ua_w == 0 or abs(t-tw) < 1e-9:
        return AirDeviceResult(service.state_phw(p, h, w), outputs=idle)
    if tw < 273.15:
        raise AirPropertyError('AIR_COIL_FROST_UNSUPPORTED', '盘管进水低于 0 °C，表面会结霜，超出模型范围')
    cp = inlet.specific_heat_j_kg_dry_air_k
    c_air, c_water = m*cp, mw*water_cp_j_kg_k
    dew = inlet.dew_point_k
    if dew is None or tw >= dew:
        # 最冷处（进水端）表面也不低于露点：全干。热水盘管同样走这里。
        f, q_air, w_out, surface_t = 1., _transfer(1/(1/ua_a+1/ua_w), c_air, c_water)*(t-tw), w, None
    else:
        from .moist_air import _ha
        def saturated(temperature):
            return _ha('H', 'P', p, 'T', temperature, 'R', 1.)
        hs_in, slope_in = saturated(tw), (saturated(tw+.01)-saturated(tw))/.01
        # 交界水温上界：进风焓对应的饱和温度。ε ≤ 1 保证解满足 h_s(t_b) ≤ h_b，不必另设上限。
        top = brentq(lambda temperature: saturated(temperature)-h, tw, t, xtol=1e-10)

        def split(f):
            """干段在进风端占 UA 的 f，湿段在进水端；交界水温 t_b 同时满足两段能量方程。

            湿段：c_w(t_b − tw) = g(t_b)·(h_b − h_s(tw))，h_b = h − Q_干/m，g 为以焓为势的 ε·C_min。
            返回 (干段热量, 湿段热量, 交界水温, 交界空气温度)。"""
            dry_g = _transfer(ua_a*ua_w*f/(ua_a+ua_w), c_air, c_water)
            if f >= 1:
                q1 = dry_g*(t-tw)
                return q1, 0., tw, t-q1/c_air
            a, b = ua_a*(1-f), ua_w*(1-f)

            def wet(t_b):
                cs = (saturated(t_b)-hs_in)/(t_b-tw) if t_b-tw > 1e-7 else slope_in
                return _transfer(1/(cp/a+cs/b), m, c_water/cs)*max(h-dry_g*(t-t_b)/m-hs_in, 0.)
            t_b = brentq(lambda value: c_water*(value-tw)-wet(value), tw, top, xtol=1e-10)
            q1 = dry_g*(t-t_b)
            return q1, c_water*(t_b-tw), t_b, t-q1/c_air

        def surface_margin(f):
            """交界处干表面温度相对进风露点的余量；为零即为干/湿交界位置。"""
            _, _, t_b, t_air_b = split(f)
            return (ua_a*t_air_b+ua_w*t_b)/(ua_a+ua_w)-dew

        if surface_margin(1.) >= 0:
            f = 1.
        elif surface_margin(0.) <= 0:
            f = 0.
        else:
            f = brentq(surface_margin, 0., 1., xtol=1e-9)
        q1, q2, _, _ = split(f)
        q_air = q1+q2
        if f >= 1:
            w_out, surface_t = w, None
        else:
            # 湿段外侧 NTU 给出等效表面焓；表面饱和含湿量决定出风含湿量（刘易斯数 1）。
            h_b, h_out = h-q1/m, h-q_air/m
            effectiveness = -math.expm1(-ua_a*(1-f)/(m*cp))
            surface_h = h_b-(h_b-h_out)/effectiveness
            surface_t = tw if surface_h <= hs_in else brentq(lambda temperature: saturated(temperature)-surface_h, tw, t,
                                                              xtol=1e-10)
            ws = saturation_humidity_ratio(surface_t, p)
            w_out = w-max(w-ws, 0.)*effectiveness
    h_out = h-q_air/m
    limited = False
    try:
        outlet = service.state_phw(p, h_out, w_out)
    except AirPropertyError as error:
        if error.code != 'AIR_HUMIDITY_SUPERSATURATED':
            raise
        # 线性化可能把出风推过饱和线：同一焓下回到饱和点，多出的水计为凝水。
        from .moist_air import _ha
        limit_t = brentq(lambda temperature: _ha('H', 'P', p, 'T', temperature, 'R', 1.)-h_out, 253.15, t, xtol=1e-10)
        outlet = service.saturated_state(p, limit_t)
        limited = True
    condensate = m*(w-outlet.humidity_ratio_kg_kg)
    removed_h = liquid_enthalpy(surface_t if surface_t is not None else outlet.temperature_k)
    water_heat = q_air-condensate*removed_h
    sensible = m*(service.state_ptw(p, t, outlet.humidity_ratio_kg_kg).enthalpy_j_kg_dry_air-outlet.enthalpy_j_kg_dry_air)
    return AirDeviceResult(outlet, -water_heat, water_removed_kg_s=condensate, removed_water_enthalpy_j_kg=removed_h,
        outputs={'total_heat_w': q_air, 'sensible_heat_w': sensible, 'latent_heat_w': q_air-sensible,
                 'condensate_kg_s': condensate, 'shr': sensible/q_air if q_air > 1e-3 else None,
                 'cooling_load_w': water_heat, 'water_heat_w': water_heat,
                 'condensate_enthalpy_flow_w': condensate*removed_h,
                 'outlet_humidity_ratio_kg_kg': outlet.humidity_ratio_kg_kg, 'surface_temperature_k': surface_t,
                 'wet_fraction': 1-f, 'wet': condensate > 0, 'active': True, 'saturation_limited': limited})


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
