"""Hydrostatic ports of a headed saturated reservoir; no free-surface transient model."""
from .cycle import DeviceRangeError


def port_state(params,state,port):
    if port=='liquid':return state.pressure_pa,state.liquid_enthalpy_j_kg,'liquid'
    if port=='vapor':return state.pressure_pa,state.vapor_enthalpy_j_kg,'vapor'
    height=params[port+'_height_ratio']*params['diameter_m']
    submerged=state.level_m>height
    pressure=state.pressure_pa+state.liquid_density_kg_m3*9.80665*max(0.,state.level_m-height)
    return pressure,state.liquid_enthalpy_j_kg if submerged else state.vapor_enthalpy_j_kg,'liquid' if submerged else 'vapor'


def require(params,state,port,phase):
    p,h,actual=port_state(params,state,port)
    if actual!=phase:raise DeviceRangeError('VESSEL_TAP_PHASE',f'取口{port}当前为{actual}，设备需要{phase}，拒绝运行点')
    return p,h
