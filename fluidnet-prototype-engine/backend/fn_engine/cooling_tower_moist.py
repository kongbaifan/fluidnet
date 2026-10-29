"""湿空气接触效能教学塔；补水、排液和空气焓均进入同一水池能量账。"""
from dataclasses import dataclass

from scipy.optimize import brentq

from .moist_air import AirPropertyError, MoistAirService, _ha, liquid_enthalpy


@dataclass
class TowerResult:
    outlet_state: object
    outputs: dict
    concentration_limited: bool = False


def evaluate_tower(inlet,water_flow_kg_s,parameters,water_service,outlet_pressure_pa=None,air_service=None):
    service=air_service or MoistAirService()
    p=parameters
    air=service.state_ptw(p['air_pressure_pa'],p['air_temperature_k'],p['air_humidity_ratio_kg_kg'])
    pressure=inlet.pressure_pa if outlet_pressure_pa is None else outlet_pressure_pa
    m=water_flow_kg_s
    if m < -1e-10:
        raise AirPropertyError('AIR_REVERSE_FLOW_UNSUPPORTED','湿空气冷却塔只支持水侧正向流动')
    if not 273.15 <= inlet.temperature_k <= 333.15:
        raise AirPropertyError('TOWER_WATER_RANGE','冷却塔入口水温必须在 0–60 °C 内')
    bypass={
        'heat_rejected_w':0.,'water_outlet_temperature_k':inlet.temperature_k,
        'air_outlet_temperature_k':air.temperature_k,'air_outlet_humidity_ratio_kg_kg':air.humidity_ratio_kg_kg,
        'approach_k':inlet.temperature_k-air.wet_bulb_k,
        'evaporation_kg_s':0.,'drift_kg_s':0.,'blowdown_kg_s':0.,'makeup_kg_s':0.,
        'achieved_concentration_ratio':None,'water_residual_kg_s':0.,'energy_residual_w':0.}
    if m <= 1e-10 or p['air_volume_flow_m3_s']==0 or p['contact_effectiveness']==0:
        return TowerResult(water_service.state_ph(pressure,inlet.enthalpy_j_kg),bypass)
    if air.wet_bulb_k >= inlet.temperature_k:
        raise AirPropertyError('TOWER_OPERATING_POINT_INFEASIBLE','入口空气湿球不低于进水温度，无法冷却')
    dry_air=p['air_volume_flow_m3_s']*air.density_kg_m3/(1+air.humidity_ratio_kg_kg)
    offset=water_service.state_pt(101325.,273.16).enthalpy_j_kg-liquid_enthalpy(273.16)
    h_in=inlet.enthalpy_j_kg-offset
    drift=p['drift_fraction']*m

    def candidate(t):
        film=(inlet.temperature_k+t)/2
        hs=_ha('H','P',p['air_pressure_pa'],'T',film,'R',1.)
        ws=_ha('W','P',p['air_pressure_pa'],'T',film,'R',1.)
        ha=air.enthalpy_j_kg_dry_air+p['contact_effectiveness']*(hs-air.enthalpy_j_kg_dry_air)
        wa=air.humidity_ratio_kg_kg+p['contact_effectiveness']*(ws-air.humidity_ratio_kg_kg)
        evaporation=dry_air*(wa-air.humidity_ratio_kg_kg)
        blowdown=max(evaporation/(p['cycles_of_concentration']-1)-drift,0.)
        makeup=evaporation+drift+blowdown
        water=water_service.state_pt(pressure,t)
        hw=water.enthalpy_j_kg-offset
        residual=m*(h_in-hw)+makeup*liquid_enthalpy(p['makeup_temperature_k'])\
            -(drift+blowdown)*hw-dry_air*(ha-air.enthalpy_j_kg_dry_air)
        return residual,water,ha,wa,evaporation,blowdown,makeup

    lower=max(273.16,air.wet_bulb_k)
    upper=inlet.temperature_k
    if candidate(lower)[0]*candidate(upper)[0]>0:
        raise AirPropertyError('TOWER_OPERATING_POINT_INFEASIBLE','湿球至进水温度区间没有能量平衡工作点')
    t=brentq(lambda value:candidate(value)[0],lower,upper,xtol=1e-10)
    residual,water,ha,wa,evaporation,blowdown,makeup=candidate(t)
    if evaporation < 0:
        raise AirPropertyError('TOWER_OPERATING_POINT_INFEASIBLE','该工况会凝水，超出蒸发冷却塔范围')
    air_out=service.state_phw(p['air_pressure_pa'],ha,wa)
    concentration=1+evaporation/(drift+blowdown) if drift+blowdown else None
    limited=concentration is not None and concentration < p['cycles_of_concentration']-1e-8
    return TowerResult(water,{
        'heat_rejected_w':m*(inlet.enthalpy_j_kg-water.enthalpy_j_kg),
        'water_outlet_temperature_k':t,'air_outlet_temperature_k':air_out.temperature_k,
        'air_outlet_humidity_ratio_kg_kg':wa,'approach_k':t-air.wet_bulb_k,
        'evaporation_kg_s':evaporation,'drift_kg_s':drift,'blowdown_kg_s':blowdown,'makeup_kg_s':makeup,
        'achieved_concentration_ratio':concentration,'water_residual_kg_s':makeup-evaporation-drift-blowdown,
        'energy_residual_w':residual},limited)
