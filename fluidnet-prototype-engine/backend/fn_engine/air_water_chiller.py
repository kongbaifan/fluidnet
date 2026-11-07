"""One liquid circuit and an external dry-air condenser boundary, without air-network ports."""
from types import SimpleNamespace

from .refrigeration.air_condenser import condenser_duty
from .refrigeration.cycle import DeviceRangeError
from .water_chiller import evaluate_chiller, refrigerant_service, check_chiller_flow_limits


def check_flow_limits(params, flow):
    check_chiller_flow_limits(params | {'condenser_min_flow_kg_s':0.},flow,0.)


def evaluate_air_chiller(inlet, flow, params, water_service, outlet_pressure, *, check=False, check_min_flow=True):
    """Reuse the cycle/evaporator solver with a sensible external-air capacity rate.

    This carrier is an internal T/h/cp boundary, not a fictitious connected water loop.
    Dry air has prescribed constant cp. No air pressure state or duct flow is solved.
    """
    p=params
    air_flow=p['rated_air_mass_flow_kg_s']*p['fan_ratio']
    cp=p['air_specific_heat_j_kg_k'];ambient=p['air_inlet_temperature_k']
    air=SimpleNamespace(temperature_k=ambient,specific_heat_j_kg_k=cp,enthalpy_j_kg=cp*ambient)
    adapted=p | {'condenser_ua_w_k':p['air_side_ua_w_k'],'condenser_min_flow_kg_s':0.}
    if check and check_min_flow:check_flow_limits(p,flow)
    try:
        result=evaluate_chiller(inlet,flow,air,air_flow,adapted,water_service,outlet_pressure,
                                check=check,check_min_flow=False)
    except DeviceRangeError as error:
        if error.code=='CHILLER_CONDENSER_NO_FLOW':
            raise DeviceRangeError('AIR_CHILLER_NO_AIR','风冷机组有制冷需求但风机停转，无法向环境排热',field='fan_ratio') from error
        raise
    outputs=result['outputs'];duty=outputs['cycling_ratio'] if result['active'] else 0.
    compressor_power=outputs['electric_power_w']
    fan_power=duty*p['fan_power_w']*p['fan_ratio']**3
    air_point=None
    if result['active']:
        air_point=condenser_duty(refrigerant_service(p),{
            'ua_w_k':p['air_side_ua_w_k'],'rated_air_mass_flow_kg_s':p['rated_air_mass_flow_kg_s'],
            'air_specific_heat_j_kg_k':cp,'air_inlet_temperature_k':ambient,'fan_ratio':p['fan_ratio'],
            'fan_power_w':p['fan_power_w'],'natural_ua_w_k':0.},outputs['condensing_pressure_pa'])
    outputs.update(compressor_electric_power_w=compressor_power,fan_power_w=fan_power,
        electric_power_w=compressor_power+fan_power,
        system_cop=outputs['cooling_power_w']/(compressor_power+fan_power) if compressor_power+fan_power>0 else None,
        air_inlet_temperature_k=ambient,air_outlet_temperature_k=air_point['air_outlet_temperature_k'] if air_point else None,
        air_mass_flow_kg_s=duty*air_flow,air_heat_rejection_w=outputs['condenser_heat_w'],
        air_equation_residual_w=duty*air_point['heat_rejection_w']-outputs['condenser_heat_w'] if air_point else 0.)
    return {'active':result['active'],'outlet_h':result['evaporator_outlet_h'],'outputs':outputs}
