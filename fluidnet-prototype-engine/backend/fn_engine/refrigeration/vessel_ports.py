"""Hydrostatic ports of a headed saturated reservoir; no free-surface transient model."""
from .cycle import DeviceRangeError


def port_state(params,state,port):
    if port=='liquid':return state.pressure_pa,state.liquid_enthalpy_j_kg,'liquid'
    if port=='vapor':return state.pressure_pa,state.vapor_enthalpy_j_kg,'vapor'
    if port == 'bulk' or port.startswith('in'):
        from .devices import vessel_dimensions
        volume = state.volume_m3 if state.volume_m3 is not None else vessel_dimensions(params)[0]
        enthalpy = state.bulk_enthalpy_j_kg if state.bulk_enthalpy_j_kg is not None else (
            state.internal_energy_j / state.mass_kg + state.pressure_pa * volume / state.mass_kg)
        return state.pressure_pa, enthalpy, state.phase or 'twophase'
    height=params[port+'_height_ratio']*params['diameter_m']
    submerged=state.level_m>height
    pressure=state.pressure_pa+state.liquid_density_kg_m3*9.80665*max(0.,state.level_m-height)
    return pressure,state.liquid_enthalpy_j_kg if submerged else state.vapor_enthalpy_j_kg,'liquid' if submerged else 'vapor'


def require(params,state,port,phase):
    p,h,actual=port_state(params,state,port)
    if actual!=phase:raise DeviceRangeError('VESSEL_TAP_PHASE',f'取口{port}当前为{actual}，设备需要{phase}，拒绝运行点')
    return p,h
