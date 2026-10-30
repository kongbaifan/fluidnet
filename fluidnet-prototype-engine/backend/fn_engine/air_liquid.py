"""Two-circuit devices evaluated from the same candidate network state.

Air transports dry-air enthalpy; liquids transport their own specific enthalpy.
No device mutates accepted states or injects a temperature boundary into a closed loop.
"""
from .air_devices import AirDeviceResult, evaluate_water_coil
from .compiler import CompilationError, service_at
from .moist_air import AirPropertyError
from .properties import PropertyError
from .refrigeration.cycle import DeviceRangeError


def enthalpy(state):
    return state.enthalpy_j_kg_dry_air if state.humidity_ratio_kg_kg is not None else state.enthalpy_j_kg


def humidity(state):
    return state.humidity_ratio_kg_kg or 0.


def coupled_device_results(network, states, flows, pressures, upstream, downstream, air_service=None, check=False):
    groups = {}
    for j, branch in enumerate(network.branches):
        kind = network.modules[network.instances[branch.instance_id].module_id].solver_model
        if kind in ('water_coil', 'water_chiller'):
            groups.setdefault(branch.instance_id, {})[branch.channel_id] = j
    results = {}
    for iid, channels in groups.items():
        a, b = channels['ch0'], channels['ch1']
        na, nb = upstream[a], upstream[b]
        ia, ib = states[na], states[nb]
        pa, pb = float(pressures[downstream[a]]), float(pressures[downstream[b]])
        params = network.parameters[iid]
        kind = network.modules[network.instances[iid].module_id].solver_model
        try:
            if kind == 'water_coil':
                air = evaluate_water_coil(ia, float(flows[a]), ib.temperature_k, float(flows[b]),
                    ib.specific_heat_j_kg_k, params, pa, air_service)
                heat = air.outputs['water_heat_w']
                outlet = service_at(network, nb).state_ph(pb, ib.enthalpy_j_kg + (heat/abs(flows[b]) if abs(flows[b]) > 1e-10 else 0.))
                results[a], results[b] = air, AirDeviceResult(outlet, heat)
            else:
                from .water_chiller import evaluate_chiller
                chiller = evaluate_chiller(ia, float(flows[a]), ib, float(flows[b]), params,
                                           service_at(network, na), pa, check=check)
                values = chiller['outputs']
                results[a] = AirDeviceResult(service_at(network, na).state_ph(pa, chiller['evaporator_outlet_h']),
                    -values['cooling_power_w'], outputs=values)
                results[b] = AirDeviceResult(service_at(network, nb).state_ph(pb, chiller['condenser_outlet_h']),
                    values['condenser_heat_w'])
        except (AirPropertyError, PropertyError, DeviceRangeError) as error:
            raise CompilationError(error.code, f'{iid}：{error}', iid) from error
    return results
