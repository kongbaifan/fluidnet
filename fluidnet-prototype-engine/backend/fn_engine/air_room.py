"""固定有效干空气存量的单区房间，隐式 Euler 候选状态。"""
from dataclasses import dataclass

from scipy.optimize import brentq

from .moist_air import AirPropertyError, MoistAirService, vapor_enthalpy


@dataclass(frozen=True)
class AirRoomSpec:
    instance_id: str
    dry_air_mass_kg: float
    initial_state: object


@dataclass
class AirRoomResult:
    state: object
    moisture_source_kg_s: float
    energy_source_w: float
    moisture_storage_kg_s: float
    energy_storage_w: float
    outputs: dict


def build_spec(instance_id,parameters):
    service=MoistAirService()
    state=service.state_ptw(parameters['initial_pressure_pa'],parameters['initial_temperature_k'],
                            parameters['initial_humidity_ratio_kg_kg'])
    mass=state.density_kg_m3*parameters['volume_m3']/(1+state.humidity_ratio_kg_kg)
    return AirRoomSpec(instance_id,mass,state)


def evaluate_room(spec,parameters,pressure,outflow,h_in,w_in,old,dt,service):
    old=old or spec.initial_state
    mass=spec.dry_air_mass_kg
    c=parameters['additional_heat_capacity_j_k']
    infiltration=parameters['infiltration_dry_air_kg_s']
    outdoor=service.state_ptw(pressure,parameters['outdoor_temperature_k'],parameters['outdoor_humidity_ratio_kg_kg'])
    moisture=parameters['moisture_load_kg_s']
    sensible=parameters['sensible_load_w']
    source_h=vapor_enthalpy(parameters['moisture_source_temperature_k'])
    ua=parameters['envelope_ua_w_k']
    e_old=mass*old.enthalpy_j_kg_dry_air+c*(old.temperature_k-273.15)
    if dt == 0:
        state=service.state_ptw(pressure,old.temperature_k,old.humidity_ratio_kg_kg)
    else:
        storage=mass/dt if dt else 0.
        divisor=outflow+infiltration+storage
        moisture_rhs=w_in+infiltration*outdoor.humidity_ratio_kg_kg+moisture+storage*old.humidity_ratio_kg_kg
        if divisor <= 1e-12:
            if abs(moisture_rhs)>1e-12:
                raise AirPropertyError('AIR_ROOM_NO_STEADY_STATE','封闭房间持续散湿，没有稳态平衡')
            w=old.humidity_ratio_kg_kg
        else:
            w=moisture_rhs/divisor
        if not 0 <= w <= .05:
            raise AirPropertyError('AIR_HUMIDITY_SUPERSATURATED','房间含湿量越界，请增加除湿或排风')
        # 固定 w 时由露点确定非过饱和温度下界。
        from .moist_air import _ha
        lower=max(273.15,_ha('D','P',pressure,'T',323.15,'W',w) if w else 273.15)
        def energy_residual(t):
            h=_ha('H','P',pressure,'T',t,'W',w)
            energy=mass*h+c*(t-273.15)
            return ((energy-e_old)/dt if dt else 0.)-h_in+outflow*h-infiltration*(outdoor.enthalpy_j_kg_dry_air-h)\
                -ua*(outdoor.temperature_k-t)-sensible-moisture*source_h
        if lower > 323.15 or energy_residual(lower)*energy_residual(323.15)>0:
            raise AirPropertyError('AIR_ROOM_NO_STEADY_STATE' if dt is None else 'AIR_ROOM_STATE_INFEASIBLE',
                                   '房间在 0–50 °C 非过饱和范围内没有可行热湿状态')
        t=brentq(energy_residual,lower,323.15,xtol=1e-10) if lower < 323.15 else lower
        state=service.state_ptw(pressure,t,w)
    energy=mass*state.enthalpy_j_kg_dry_air+c*(state.temperature_k-273.15)
    envelope=ua*(outdoor.temperature_k-state.temperature_k)
    infiltration_heat=infiltration*(outdoor.enthalpy_j_kg_dry_air-state.enthalpy_j_kg_dry_air)
    infiltration_moisture=infiltration*(outdoor.humidity_ratio_kg_kg-state.humidity_ratio_kg_kg)
    source_water=moisture+infiltration_moisture
    source_energy=sensible+moisture*source_h+envelope+infiltration_heat
    water_rate=(mass*(state.humidity_ratio_kg_kg-old.humidity_ratio_kg_kg)/dt if dt
                else w_in-outflow*state.humidity_ratio_kg_kg+source_water if dt == 0 else 0.)
    energy_rate=((energy-e_old)/dt if dt
                 else h_in-outflow*state.enthalpy_j_kg_dry_air+source_energy if dt == 0 else 0.)
    return AirRoomResult(state,source_water,source_energy,water_rate,energy_rate,{
        'state.temperature_k':state.temperature_k,'state.humidity_ratio_kg_kg':state.humidity_ratio_kg_kg,
        'state.relative_humidity':state.relative_humidity,'state.dry_air_mass_kg':mass,
        'state.water_vapor_mass_kg':mass*state.humidity_ratio_kg_kg,'state.stored_energy_j':energy,
        'sensible_load_w':sensible,'moisture_load_kg_s':moisture,'envelope_heat_w':envelope,
        'infiltration_heat_w':infiltration_heat,'infiltration_moisture_kg_s':infiltration_moisture})
