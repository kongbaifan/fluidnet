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


def validate_chiller_flows(network, flows):
    """Protect the final network flow before any module observation or accepted-state update."""
    from .water_chiller import check_chiller_flow_limits
    groups = {}
    for j, branch in enumerate(network.branches):
        if network.modules[network.instances[branch.instance_id].module_id].solver_model in ('water_chiller','air_cooled_chiller','air_source_heat_pump'):
            groups.setdefault(branch.instance_id, {})[branch.channel_id] = float(flows[j])
    for iid, channels in groups.items():
        try:
            if network.modules[network.instances[iid].module_id].solver_model=='air_source_heat_pump':
                from .air_source_heat_pump import check_flow_limits as check_heating_flow
                check_heating_flow(network.parameters[iid],channels['ch0'])
            elif network.modules[network.instances[iid].module_id].solver_model=='air_cooled_chiller':
                from .air_water_chiller import check_flow_limits
                check_flow_limits(network.parameters[iid],channels['ch0'])
            else:check_chiller_flow_limits(network.parameters[iid], channels['ch0'], channels['ch1'])
        except DeviceRangeError as error:
            raise CompilationError(error.code, f'{iid}：{error}', iid, error.field) from error


def validate_final_device_ranges(network,result):
    """New equipment range guards run after density/moisture outer coupling, before observation."""
    if result.thermal is None or not any(m.solver_model in ('air_cooled_chiller','air_source_heat_pump','enthalpy_recovery')
                                         for m in network.modules.values()):return
    thermal=result.thermal;hydraulic=result.hydraulic
    coupled_device_results(network,thermal.node_states,hydraulic.flows,hydraulic.pressures,
                           thermal.upstream,thermal.downstream,check=True,final=True)


def coupled_device_results(network, states, flows, pressures, upstream, downstream, air_service=None, check=False, final=False):
    groups = {}
    for j, branch in enumerate(network.branches):
        kind = network.modules[network.instances[branch.instance_id].module_id].solver_model
        if kind in ('water_coil', 'water_chiller','air_cooled_chiller','air_source_heat_pump','enthalpy_recovery'):
            groups.setdefault(branch.instance_id, {})[branch.channel_id] = j
    results = {}
    for iid, channels in groups.items():
        one_sided=network.modules[network.instances[iid].module_id].solver_model
        if one_sided=='enthalpy_recovery':
            from .enthalpy_recovery import evaluate
            a,b=channels['ch0'],channels['ch1']
            try:
                pair=evaluate(states[upstream[a]],states[upstream[b]],float(flows[a]),float(flows[b]),network.parameters[iid],
                    float(pressures[downstream[a]]),float(pressures[downstream[b]]),air_service,check=check and final)
                results[a],results[b]=pair.exhaust,pair.supply
            except AirPropertyError as error:raise CompilationError(error.code,f'{iid}：{error}',iid) from error
            continue
        if one_sided in ('air_cooled_chiller','air_source_heat_pump'):
            from .air_water_chiller import evaluate_air_chiller
            from .air_source_heat_pump import evaluate_heat_pump
            j=channels['ch0'];node=upstream[j];pressure=float(pressures[downstream[j]])
            try:
                evaluate_device=evaluate_heat_pump if one_sided=='air_source_heat_pump' else evaluate_air_chiller
                result=evaluate_device(states[node],float(flows[j]),network.parameters[iid],service_at(network,node),pressure,
                                            check=check and final,check_min_flow=False)
                results[j]=AirDeviceResult(service_at(network,node).state_ph(pressure,result['outlet_h']),
                                           result['outputs'].get('heating_power_w',-result['outputs'].get('cooling_power_w',0.)),outputs=result['outputs'])
            except (AirPropertyError,PropertyError,DeviceRangeError) as error:
                raise CompilationError(error.code,f'{iid}：{error}',iid,getattr(error,'field',None)) from error
            continue
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
                # check=True here only completes an inner thermal solve; density may still change.
                chiller = evaluate_chiller(ia, float(flows[a]), ib, float(flows[b]), params,
                                           service_at(network, na), pa, check=check, check_min_flow=False)
                values = chiller['outputs']
                if check and values['low_load_cycling']:
                    # Average outlets must not hide an invalid liquid state during the ON portion.
                    service_at(network, nb).state_ph(pb, chiller['on_condenser_outlet_h'])
                results[a] = AirDeviceResult(service_at(network, na).state_ph(pa, chiller['evaporator_outlet_h']),
                    -values['cooling_power_w'], outputs=values)
                results[b] = AirDeviceResult(service_at(network, nb).state_ph(pb, chiller['condenser_outlet_h']),
                    values['condenser_heat_w'])
        except (AirPropertyError, PropertyError, DeviceRangeError) as error:
            raise CompilationError(error.code, f'{iid}：{error}', iid, getattr(error, 'field', None)) from error
    return results
