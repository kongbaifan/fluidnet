"""Single-stage vapour-compression cycle (case A) and the compression step shared with case B.

States follow PLAN 3.3: 1 suction (superheat inside the evaporator), 2s/2 discharge, 3 subcooled
condenser outlet, 4 = isenthalpic throttle outlet. Evaporating pressure is the dew pressure at T_evap,
condensing pressure the bubble pressure at T_cond (identical for a pure fluid). Motor losses leave to
the machine room, so Q_cond = Q_evap + P_shaft exactly.
"""
from ..models import Diagnostic
from ..properties import PropertyError


class DeviceRangeError(ValueError):
    """A device evaluated outside its model range; `code` is the diagnostic code."""

    def __init__(self, code, message, instance_id=None, field=None):
        self.code, self.instance_id, self.field = code, instance_id, field
        super().__init__(message)


def compress(service, suction, discharge_pa, isentropic_efficiency):
    """Adiabatic compression of `suction` to `discharge_pa`: (h2s, h2)."""
    isentropic = service.state_ps(discharge_pa, suction.entropy_j_kg_k).enthalpy_j_kg
    return isentropic, suction.enthalpy_j_kg + (isentropic - suction.enthalpy_j_kg) / isentropic_efficiency


def displaced_flow(displacement_m3_s, load_ratio, volumetric_efficiency, suction_density):
    """Forced mass flow of a positive-displacement compressor."""
    return displacement_m3_s * load_ratio * volumetric_efficiency * suction_density


GAS_PHASES = {'gas', 'supercritical_gas'}
LIQUID_PHASES = {'liquid', 'supercritical_liquid'}


def _states(service, params, t_evap, t_cond):
    """Suction (1) and condenser outlet (3) with pressures; checks the declared phases."""
    if not t_cond > t_evap:
        raise DeviceRangeError('CYCLE_PRESSURE_RATIO', f'冷凝温度 {t_cond - 273.15:.2f} °C 须高于蒸发温度 '
                               f'{t_evap - 273.15:.2f} °C')
    try:
        p_evap = service.state_tq(t_evap, 1.).pressure_pa
        p_cond = service.state_tq(t_cond, 0.).pressure_pa
        suction = service.state_pt(p_evap, t_evap + params['superheat_k'])
        liquid = service.state_pt(p_cond, t_cond - params['subcooling_k'])
    except PropertyError as error:
        raise DeviceRangeError(error.code, f'蒸发 {t_evap - 273.15:.2f} °C / 冷凝 {t_cond - 273.15:.2f} °C 无法求物性：{error}') from error
    if suction.phase not in GAS_PHASES:
        raise DeviceRangeError('CYCLE_SUCTION_PHASE', f'吸气状态为 {suction.phase}，过热度不足以得到过热蒸气', field='superheat_k')
    if liquid.phase not in LIQUID_PHASES:
        raise DeviceRangeError('CYCLE_LIQUID_PHASE', f'冷凝器出口为 {liquid.phase}，过冷度不足以得到过冷液', field='subcooling_k')
    return p_evap, p_cond, suction, liquid


def cycle_rates(service, params, displacement_m3_s, t_evap, t_cond, load_ratio):
    """Mass flow and enthalpies at saturation temperatures (T_evap, T_cond); no extra flashes.

    Used inside the coupled Newton iteration; `cycle_point` adds the full state points."""
    p_evap, p_cond, suction, liquid = _states(service, params, t_evap, t_cond)
    try:
        h2s, h2 = compress(service, suction, p_cond, params['isentropic_efficiency'])
    except PropertyError as error:
        raise DeviceRangeError(error.code, f'等熵压缩到 {p_cond:.0f} Pa 无法求物性：{error}') from error
    mass = displaced_flow(displacement_m3_s, load_ratio, params['volumetric_efficiency'], suction.density_kg_m3)
    h1, h3 = suction.enthalpy_j_kg, liquid.enthalpy_j_kg
    if not (h2 > h1 > h3):
        raise DeviceRangeError('CYCLE_NOT_POSITIVE', '循环没有正的制冷效应或压缩功')
    return {'p_evap': p_evap, 'p_cond': p_cond, 'suction': suction, 'liquid': liquid, 'h1': h1, 'h2s': h2s, 'h2': h2,
            'h3': h3, 'mass_flow_kg_s': mass, 'cooling_w': mass * (h1 - h3), 'shaft_w': mass * (h2 - h1),
            'rejection_w': mass * (h2 - h3)}


def _state(prefix, state, quality=None):
    return {f'{prefix}.pressure_pa': state.pressure_pa, f'{prefix}.temperature_k': state.temperature_k,
            f'{prefix}.enthalpy_j_kg': state.enthalpy_j_kg, f'{prefix}.entropy_j_kg_k': state.entropy_j_kg_k,
            f'{prefix}.quality': quality}


def cycle_point(service, params, displacement_m3_s, t_evap, t_cond, load_ratio):
    """Complete operating point: rates, four state points, COP and the declared-envelope check."""
    r = cycle_rates(service, params, displacement_m3_s, t_evap, t_cond, load_ratio)
    try:
        discharge = service.state_ph(r['p_cond'], r['h2'])
        throttled = service.state_ph(r['p_evap'], r['h3'])
    except PropertyError as error:
        raise DeviceRangeError(error.code, f'排气或节流状态无法求物性：{error}') from error
    if throttled.quality is None or not 0 < throttled.quality < 1:
        raise DeviceRangeError('CYCLE_THROTTLE_PHASE', f'节流出口为 {throttled.phase}，不在两相区')
    electric = r['shaft_w'] / params['motor_efficiency']
    point = {'mass_flow_kg_s': r['mass_flow_kg_s'], 'cooling_power_w': r['cooling_w'], 'shaft_power_w': r['shaft_w'],
             'electric_power_w': electric, 'condenser_heat_w': r['rejection_w'],
             'cycle_residual_w': r['rejection_w'] - r['cooling_w'] - r['shaft_w'],
             'evaporating_temperature_k': t_evap, 'condensing_temperature_k': t_cond,
             'evaporating_pressure_pa': r['p_evap'], 'condensing_pressure_pa': r['p_cond'],
             'pressure_ratio': r['p_cond'] / r['p_evap'], 'suction_temperature_k': r['suction'].temperature_k,
             'discharge_temperature_k': discharge.temperature_k, 'isentropic_enthalpy_j_kg': r['h2s'],
             'cop': r['cooling_w'] / electric if electric > 0 else None,
             **_state('state1', r['suction']), **_state('state2', discharge),
             **_state('state3', r['liquid']), **_state('state4', throttled, throttled.quality)}
    return point


# (field, value key, bound side, label) of the declared operating envelope.
ENVELOPE = [('min_evaporating_temperature_k', 'evaporating_temperature_k', 'low', '蒸发温度'),
            ('max_evaporating_temperature_k', 'evaporating_temperature_k', 'high', '蒸发温度'),
            ('min_condensing_temperature_k', 'condensing_temperature_k', 'low', '冷凝温度'),
            ('max_condensing_temperature_k', 'condensing_temperature_k', 'high', '冷凝温度'),
            ('max_discharge_temperature_k', 'discharge_temperature_k', 'high', '排气温度'),
            ('max_pressure_ratio', 'pressure_ratio', 'high', '压比')]


def check_envelope(params, point):
    """Stop outside the declared envelope instead of reporting an extrapolated point as normal cooling."""
    for field, key, side, label in ENVELOPE:
        value, bound = point[key], params[field]
        if side == 'low' and value < bound or side == 'high' and value > bound:
            temperature = key.endswith('temperature_k')
            shown = (f'{value - 273.15:.2f} °C', f'{bound - 273.15:.2f} °C') if temperature else (f'{value:.3f}', f'{bound:g}')
            raise DeviceRangeError('REFRIGERATION_ENVELOPE', f'{label} {shown[0]} 超出声明运行范围'
                                   f'（{"下限" if side == "low" else "上限"} {shown[1]}）', field=field)


def rated_displacement(service, params):
    """Swept volume that delivers `rated_cooling_power_w` at the rated evaporating/condensing temperatures."""
    _, _, suction, liquid = _states(service, params, params['rated_evaporating_temperature_k'],
                                    params['rated_condensing_temperature_k'])
    if not suction.enthalpy_j_kg > liquid.enthalpy_j_kg:
        raise DeviceRangeError('CYCLE_DESIGN_INVALID', '额定工作点没有正的制冷效应')
    rated_mass = params['rated_cooling_power_w'] / (suction.enthalpy_j_kg - liquid.enthalpy_j_kg)
    return rated_mass / (suction.density_kg_m3 * params['volumetric_efficiency'])


def rated_design(service, params):
    """Displacement and condenser UA fixed once at the declared rated point (PLAN 3.3); never rescaled per step."""
    t_evap, t_cond = params['rated_evaporating_temperature_k'], params['rated_condensing_temperature_k']
    if not t_cond > params['rated_ambient_temperature_k']:
        raise DeviceRangeError('CYCLE_DESIGN_INVALID', '额定冷凝温度须高于额定环境温度', field='rated_condensing_temperature_k')
    displacement = rated_displacement(service, params)
    rated = cycle_rates(service, params, displacement, t_evap, t_cond, 1.)
    return {'displacement_m3_s': displacement,
            'condenser_ua_w_k': rated['rejection_w'] / (t_cond - params['rated_ambient_temperature_k'])}


def superheat_warning(params, room_temperature_k, t_evap):
    """Air leaving colder than the declared suction superheat cannot supply it (first-version assumption)."""
    if room_temperature_k - t_evap < params['superheat_k']:
        return Diagnostic(code='CYCLE_SUPERHEAT_APPROACH', severity='warning', field='superheat_k',
                          message=f'库温与蒸发温度差 {room_temperature_k - t_evap:.2f} K 小于声明过热度 '
                                  f'{params["superheat_k"]:g} K；首版假设过热在蒸发器内完成，此时偏乐观')
    return None
