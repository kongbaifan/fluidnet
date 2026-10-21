"""Lumped refrigeration-station devices (case B): pure functions of parameters and vessel states.

Pressure lives only in saturated vessels. Every other device is an algebraic relation between the
vessel(s) it connects to; two-phase properties are queried here, never in the fluid network
(ALGORITHM.md keeps network two-phase flow out of scope). Services should use phase_policy='any'.
"""
from dataclasses import asdict, dataclass
import math

from ..models import Diagnostic

TWO_PHASE = 'twophase'


class DeviceRangeError(ValueError):
    """A device evaluated outside its model range; `code` is the diagnostic code."""

    def __init__(self, code, message, instance_id=None):
        self.code, self.instance_id = code, instance_id
        super().__init__(message)


def running(params):
    return params.get('running', 1.) >= .5


@dataclass(frozen=True)
class VesselState:
    pressure_pa: float
    temperature_k: float
    mass_kg: float
    internal_energy_j: float
    liquid_mass_kg: float
    vapor_mass_kg: float
    quality: float
    level_ratio: float
    level_m: float
    liquid_enthalpy_j_kg: float
    vapor_enthalpy_j_kg: float
    liquid_density_kg_m3: float
    vapor_density_kg_m3: float

    def variables(self, prefix):
        return {f'{prefix}.state.{key}' if key in STATE_KEYS else f'{prefix}.{key}': value
                for key, value in asdict(self).items()}


STATE_KEYS = {'pressure_pa', 'temperature_k', 'mass_kg', 'internal_energy_j', 'liquid_mass_kg',
              'vapor_mass_kg', 'quality', 'level_ratio', 'level_m'}


def saturated(service, temperature):
    """Saturated liquid and vapor at `temperature`; raises when no saturation exists there."""
    return service.state_tq(temperature, 0.), service.state_tq(temperature, 1.)


def vessel_initial(service, params):
    """(M, U) of a vessel filled to `level_ratio` (liquid volume fraction) at saturation `temperature_k`."""
    volume, level = params['volume_m3'], params['level_ratio']
    if not 0 < level < 1:
        raise DeviceRangeError('VESSEL_PHASE_RANGE', '初始液位必须在 0 与 1 之间（不含端点）')
    liquid, vapor = saturated(service, params['temperature_k'])
    liquid_mass = level * volume * liquid.density_kg_m3
    vapor_mass = (1 - level) * volume * vapor.density_kg_m3
    return (liquid_mass + vapor_mass,
            liquid_mass * liquid.internal_energy_j_kg + vapor_mass * vapor.internal_energy_j_kg)


def vessel_state(service, params, mass, internal_energy):
    """Pressure, level and phase enthalpies of a closed volume from its stored mass and internal energy."""
    volume, height = params['volume_m3'], params['height_m']
    if not (math.isfinite(mass) and math.isfinite(internal_energy)) or mass <= 0:
        raise DeviceRangeError('VESSEL_PHASE_RANGE', '容器存量必须为有限正数')
    state = service.state_du(mass / volume, internal_energy / mass)
    if state.phase != TWO_PHASE or state.quality is None:
        raise DeviceRangeError('VESSEL_PHASE_RANGE', f'容器内为 {state.phase}，集总饱和容器只适用于气液两相')
    liquid, vapor = saturated(service, state.temperature_k)
    vapor_mass = state.quality * mass
    liquid_mass = mass - vapor_mass
    level = liquid_mass / liquid.density_kg_m3 / volume
    return VesselState(state.pressure_pa, state.temperature_k, mass, internal_energy, liquid_mass, vapor_mass,
                       state.quality, level, level * height, liquid.enthalpy_j_kg, vapor.enthalpy_j_kg,
                       liquid.density_kg_m3, vapor.density_kg_m3)


def check_vessel(params, state):
    """The level band in which the lumped vessel is used; outside it a run stops instead of clamping."""
    if not params['min_level_ratio'] <= state.level_ratio <= params['max_level_ratio']:
        raise DeviceRangeError('VESSEL_LEVEL_RANGE', f'液位 {state.level_ratio:.3f} 超出模型适用区间 '
                               f'[{params["min_level_ratio"]:g}, {params["max_level_ratio"]:g}]')


def compressor_point(service, params, suction_pa, discharge_pa):
    """Forced mass flow from displacement, load and saturated suction vapor; discharge pressure is given.

    Motor losses leave to the machine room; only shaft work enters the refrigerant (PLAN 3.3)."""
    vapor = service.state_pq(suction_pa, 1.)
    load = params['load_ratio'] if running(params) else 0.
    result = {'mass_flow_kg_s': 0., 'shaft_power_w': 0., 'electric_power_w': 0.,
              'suction_enthalpy_j_kg': vapor.enthalpy_j_kg, 'discharge_enthalpy_j_kg': vapor.enthalpy_j_kg,
              'discharge_temperature_k': None, 'pressure_ratio': discharge_pa / suction_pa,
              'running': 1. if running(params) else 0., 'diagnostics': []}
    if load <= 0:
        return result
    if discharge_pa <= suction_pa:
        raise DeviceRangeError('COMPRESSOR_PRESSURE_RATIO', '运行中的压缩机排气压力必须高于吸气压力')
    mass = params['displacement_m3_s'] * load * params['volumetric_efficiency'] * vapor.density_kg_m3
    isentropic = service.state_ps(discharge_pa, vapor.entropy_j_kg_k).enthalpy_j_kg
    enthalpy = vapor.enthalpy_j_kg + (isentropic - vapor.enthalpy_j_kg) / params['isentropic_efficiency']
    shaft = mass * (enthalpy - vapor.enthalpy_j_kg)
    ratio = discharge_pa / suction_pa
    diagnostics = []
    if ratio > params['max_pressure_ratio']:
        diagnostics.append(Diagnostic(code='COMPRESSOR_ENVELOPE', severity='warning', field='max_pressure_ratio',
                                      message=f'压比 {ratio:.2f} 超过单级包络 {params["max_pressure_ratio"]:g}'))
    result.update(mass_flow_kg_s=mass, shaft_power_w=shaft, electric_power_w=shaft / params['motor_efficiency'],
                  discharge_enthalpy_j_kg=enthalpy, pressure_ratio=ratio, diagnostics=diagnostics,
                  discharge_temperature_k=service.state_ph(discharge_pa, enthalpy).temperature_k)
    return result


def condenser_duty(service, params, pressure_pa):
    """Heat rejected to the wet-bulb sink. Closing the receiver return-gas valve floods part of the coil."""
    condensing = service.saturation_t(pressure_pa)
    fan = params['fan_ratio']
    ua = (params['ua_w_k'] * (params['natural_ua_ratio'] + (1 - params['natural_ua_ratio']) * fan)
          * (params['flooded_ua_ratio'] + (1 - params['flooded_ua_ratio']) * params['return_gas_ratio']))
    # The sign is kept: below the wet-bulb temperature the coil would take heat in, not reject it.
    return {'heat_rejection_w': ua * (condensing - params['wet_bulb_temperature_k']), 'effective_ua_w_k': ua,
            'condensing_temperature_k': condensing, 'fan_power_w': params['fan_power_w'] * fan}


def valve_flow(service, params, inlet_pa, outlet_pa):
    """Saturated receiver liquid through an expansion valve; m = Kv·opening·sqrt(ρ·Δp/1e5)/3.6 (same Kv as `valve`)."""
    liquid = service.state_pq(inlet_pa, 0.)
    drop = inlet_pa - outlet_pa
    kv = params['kv_m3_h'] * params['opening_ratio']
    # Solenoid expansion valves pass liquid one way only; no forward pressure difference means no flow.
    mass = kv / 3600 * math.sqrt(1000 * liquid.density_kg_m3 * drop / 1e5) if kv > 0 and drop > 0 else 0.
    flashed = service.state_ph(outlet_pa, liquid.enthalpy_j_kg) if drop > 0 else None
    return {'mass_flow_kg_s': mass, 'pressure_drop_pa': drop, 'enthalpy_j_kg': liquid.enthalpy_j_kg,
            'outlet_quality': flashed.quality if flashed else None}


def cascade_duty(evaporating, condensing, params, evaporating_pa, condensing_pa):
    """Flooded cascade exchanger: both sides saturated, Q = UA·(T_sat,cond − T_sat,evap)."""
    t_evap, t_cond = evaporating.saturation_t(evaporating_pa), condensing.saturation_t(condensing_pa)
    duty = params['ua_w_k'] * (t_cond - t_evap)
    latent_evap = evaporating.state_pq(evaporating_pa, 1.).enthalpy_j_kg - evaporating.state_pq(evaporating_pa, 0.).enthalpy_j_kg
    latent_cond = condensing.state_pq(condensing_pa, 1.).enthalpy_j_kg - condensing.state_pq(condensing_pa, 0.).enthalpy_j_kg
    return {'heat_w': duty, 'approach_k': t_cond - t_evap, 'evaporating_temperature_k': t_evap,
            'condensing_temperature_k': t_cond, 'evaporated_kg_s': duty / latent_evap,
            'condensed_kg_s': duty / latent_cond}


def pump_point(service, params, suction_pa):
    """Liquid pump: flow ∝ speed, Δp ∝ speed². A canned pump puts all electric power into the liquid."""
    speed = params['speed_ratio'] if running(params) else 0.
    liquid = service.state_pq(suction_pa, 0.)
    mass = params['rated_mass_flow_kg_s'] * speed
    rise = params['rated_pressure_rise_pa'] * speed ** 2
    power = mass * rise / liquid.density_kg_m3 / params['efficiency_ratio']
    return {'mass_flow_kg_s': mass, 'pressure_rise_pa': rise, 'electric_power_w': power,
            'heat_to_fluid_w': power, 'running': 1. if running(params) else 0.}


def split_supply(total, openings):
    """Pump flow shared by the coils on one header in proportion to their supply-valve openings."""
    weight = sum(openings.values())
    return {key: total * value / weight if weight > 0 else 0. for key, value in openings.items()}


def air_cooler_point(service, params, pressure_pa, room_temperature_k, supply_kg_s):
    """Overfed coil: air-side UA·ΔT, capped by the liquid supplied for evaporation up to `max_outlet_quality`.

    Fan heat stays in the room, so the room sees refrigerant heat minus fan power."""
    liquid, vapor = service.state_pq(pressure_pa, 0.), service.state_pq(pressure_pa, 1.)
    latent = vapor.enthalpy_j_kg - liquid.enthalpy_j_kg
    fan = params['fan_ratio'] if running(params) else 0.
    ua = params['ua_w_k'] * (params['natural_ua_ratio'] + (1 - params['natural_ua_ratio']) * fan)
    # A room colder than the coil would only subcool the liquid slightly; that sensible term is neglected.
    air_side = max(0., ua * (room_temperature_k - liquid.temperature_k))
    supply_side = supply_kg_s * latent * params['max_outlet_quality']
    heat = min(air_side, supply_side)
    fan_power = params['fan_power_w'] * fan
    return {'refrigerant_heat_w': heat, 'room_cooling_w': heat - fan_power, 'fan_power_w': fan_power,
            'supply_mass_flow_kg_s': supply_kg_s, 'evaporating_temperature_k': liquid.temperature_k,
            'outlet_quality': heat / latent / supply_kg_s if supply_kg_s > 0 else None,
            'outlet_enthalpy_j_kg': liquid.enthalpy_j_kg + heat / supply_kg_s if supply_kg_s > 0 else liquid.enthalpy_j_kg,
            'supply_limited': air_side > supply_side}
