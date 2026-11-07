"""Electric defrost state machine and explicit heat allocation for a pumped cooler."""
from copy import deepcopy


def transition(state, parameters, time_s):
    result=deepcopy(state)
    request=parameters['defrost_request']>=.5
    if result['mode']==1 and time_s>=result['since']+parameters['defrost_duration_s']-1e-9:
        result.update(mode=2,since=result['since']+parameters['defrost_duration_s'])
    if result['mode']==2 and time_s>=result['since']+parameters['drip_duration_s']-1e-9:
        result.update(mode=0,count=result['count']+1)
    if result['mode']==0 and request and not result['requested']:
        result.update(mode=1,since=time_s)
    result['requested']=request
    return result


def deadline(state, p):
    return state['since']+p['defrost_duration_s' if state['mode']==1 else 'drip_duration_s'] if state['mode'] else None


def idle_outputs(service, pressure, p, state):
    heater=p['defrost_heater_power_w'] if state['mode']==1 else 0.
    room_heat=heater*p['defrost_room_fraction']
    fluid_heat=heater-room_heat
    return {'refrigerant_heat_w':fluid_heat,'room_cooling_w':-room_heat,'fan_power_w':0.,
        'supply_mass_flow_kg_s':0.,'evaporating_temperature_k':service.saturation_t(pressure),
        'outlet_quality':None,'outlet_enthalpy_j_kg':service.state_pq(pressure,0.).enthalpy_j_kg,
        'supply_limited':False,'heater_power_w':heater,'defrost_room_heat_w':room_heat}
