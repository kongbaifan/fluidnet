"""干空气连续性与湿空气 h/w 输运，使用真实边界流股独立核算守恒。"""
from __future__ import annotations

import math

import numpy as np

from .air_devices import evaluate_cooling_coil, evaluate_humidifier, evaluate_pass_through
from .compiler import CompilationError
from .models import Diagnostic
from .moist_air import AIR_STATE_FIELDS, AirPropertyError, MoistAirService


def _initial(network, service, warm):
    if warm is not None and warm.thermal is not None:
        return list(warm.thermal.node_states)
    boundary = {n: service.state_ptw(p,network.fixed_temperatures[n],network.fixed_humidities[n])
                for n,p in network.fixed_pressures.items()}
    seeds = list(boundary.values())
    if not seeds:
        raise CompilationError('MOISTURE_REFERENCE_MISSING','湿空气网络缺少入口状态')
    # 初值只是迭代种子；不得把它当成实际水分/能量源。
    initial = [boundary.get(n,seeds[0]) for n in range(len(network.node_keys))]
    for node,spec in network.air_rooms.items():
        initial[node] = spec.initial_state
    return initial


def solve_air_network(network, runners, time_s, warm=None, room_step=None):
    from .solver import NetworkResult, _solve_hydraulics, _node_ports, build_port_states
    service = MoistAirService()
    try:
        states = _initial(network, service, warm)
        options = network.project.solver
        air_options = options.moist_air_options
        start = warm.hydraulic.solution if warm else None
        flows = warm.hydraulic.flows if warm else np.ones(len(network.branches))
        for outer in range(1, options.max_coupling_iterations+1):
            upstream = [b.start_node if q >= 0 else b.end_node for b,q in zip(network.branches,flows)]
            rho = np.array([states[n].density_kg_m3 for n in upstream])
            mu = np.array([states[n].viscosity_pa_s for n in upstream])
            factors = np.array([[1+states[b.start_node].humidity_ratio_kg_kg,
                                 1+states[b.end_node].humidity_ratio_kg_kg] for b in network.branches])
            hydraulic = _solve_hydraulics(network,runners,time_s,branch_density=rho,branch_viscosity=mu,
                port_base=_node_ports(network,states),initial=start,air_mass_factors=factors)
            thermal = solve_air_transport(network,hydraulic,states,service,runners,time_s,room_step)
            new_upstream = thermal.upstream
            rho_new = np.array([thermal.node_states[n].density_kg_m3 for n in new_upstream])
            density_defect = float(np.max(np.abs(rho_new-rho)/rho_new))
            humidity_defect = max(abs(a.humidity_ratio_kg_kg-b.humidity_ratio_kg_kg)
                                 for a,b in zip(states,thermal.node_states))
            temp_defect = max(abs(a.temperature_k-b.temperature_k) for a,b in zip(states,thermal.node_states))
            if (density_defect <= options.coupling_density_rtol and temp_defect <= options.thermal_tolerance_k
                    and humidity_defect <= air_options.humidity_tolerance_kg_kg):
                result = NetworkResult(hydraulic,thermal,outer,build_port_states(network,hydraulic,thermal))
                return result
            states, flows, start = thermal.node_states, hydraulic.flows, hydraulic.solution
        raise CompilationError('COUPLING_NOT_CONVERGED','水力与热湿物性联合迭代未收敛')
    except AirPropertyError as error:
        raise CompilationError(error.code,str(error)) from error


def solve_air_transport(network, hydraulic, previous, service, runners, time_s, room_step=None):
    from .thermal import ThermalResult
    from .module_phases import heat_hook
    o = network.project.solver.moist_air_options
    branches, p = network.branches, hydraulic.pressures
    flows = np.array(hydraulic.flows,copy=True)
    flows[np.abs(flows) <= o.flow_zero_tolerance_kg_s] = 0.
    mass = np.abs(flows)
    n, m = len(previous), len(branches)
    up = [b.start_node if q >= 0 else b.end_node for b,q in zip(branches,flows)]
    down = [b.end_node if q >= 0 else b.start_node for b,q in zip(branches,flows)]
    incoming, outgoing = [[] for _ in range(n)], [[] for _ in range(n)]
    for j in range(m):
        if mass[j]:
            outgoing[up[j]].append(j)
            incoming[down[j]].append(j)
    boundary_supply = {node:sum(mass[j] for j in outgoing[node])-sum(mass[j] for j in incoming[node])
                       for node in network.fixed_pressures}
    boundary_states = {node:service.state_ptw(float(p[node]),network.fixed_temperatures[node],network.fixed_humidities[node])
                       for node in network.fixed_pressures}
    rooms = getattr(network,'air_rooms',{})
    reached = {node for node,q in boundary_supply.items() if q > o.flow_zero_tolerance_kg_s} | set(rooms)
    pending = list(reached)
    while pending:
        node = pending.pop()
        for j in outgoing[node]:
            if down[j] not in reached:
                reached.add(down[j]); pending.append(down[j])
    for node in range(n):
        if node not in reached and (incoming[node] or outgoing[node]):
            raise CompilationError('MOISTURE_REFERENCE_MISSING','流动回路没有实际供气湿度参考或房间状态')
    states = list(previous)
    module_heat = heat_hook(network,runners,hydraulic,service,time_s)
    heat_previous = np.zeros(m)
    diagnostics = []
    room_results = {}
    for iteration in range(1,o.max_iterations+1):
        extra_heat, heat_diagnostics = module_heat(states,heat_previous) if module_heat else ({},[])
        devices = []
        for j,b in enumerate(branches):
            params = network.parameters[b.instance_id]
            definition = network.modules[network.instances[b.instance_id].module_id]
            kind, inlet = definition.solver_model, states[up[j]]
            pressure = float(p[down[j]])
            try:
                if kind == 'cooling_coil':
                    device = evaluate_cooling_coil(inlet,float(flows[j]),params,pressure,service)
                elif kind == 'humidifier':
                    device = evaluate_humidifier(inlet,float(flows[j]),params,pressure,service)
                else:
                    relation = hydraulic.relations.get((b.instance_id,b.channel_id))
                    heat = float(params.get('heat_input_w',0)) if kind == 'heater' else 0.
                    if relation:
                        heat += relation.parameters.get('heat_w',0.)
                        if relation.kind in ('pump','compressor'):
                            # 沿用现有风机边界：进入空气的是水力功，轴/电功单独报告。
                            heat += (float(p[down[j]])-float(p[up[j]]))*mass[j]*(1+inlet.humidity_ratio_kg_kg)/inlet.density_kg_m3
                    heat += extra_heat.get((b.instance_id,b.channel_id),0.)
                    ua = params.get('heat_loss_ua_w_k',0.)
                    if ua and mass[j]:
                        # 分布式显热散热，使用当地 cp；出口焓由统一物性构造。
                        tout = params['ambient_temperature_k']+(inlet.temperature_k-params['ambient_temperature_k'])*math.exp(
                            -ua/(mass[j]*inlet.specific_heat_j_kg_dry_air_k))
                        target = service.state_ptw(pressure,tout,inlet.humidity_ratio_kg_kg)
                        heat += mass[j]*(target.enthalpy_j_kg_dry_air-inlet.enthalpy_j_kg_dry_air)
                    device = evaluate_pass_through(inlet,mass[j],pressure,heat,service)
                if mass[j] == 0:
                    device.outlet_state = states[down[j]]
                devices.append(device)
            except AirPropertyError as error:
                raise CompilationError(error.code,f'{b.instance_id}：{error}',b.instance_id) from error
        candidate = list(states)
        room_results = {}
        for node in range(n):
            supplied = max(boundary_supply.get(node,0.),0.)
            total = sum(mass[j] for j in incoming[node])+supplied
            h_in = sum(mass[j]*devices[j].outlet_state.enthalpy_j_kg_dry_air for j in incoming[node])
            w_in = sum(mass[j]*devices[j].outlet_state.humidity_ratio_kg_kg for j in incoming[node])
            if supplied:
                h_in += supplied*boundary_states[node].enthalpy_j_kg_dry_air
                w_in += supplied*boundary_states[node].humidity_ratio_kg_kg
            if node in rooms:
                from .air_room import evaluate_room
                dt, old = room_step if room_step is not None else (None,{})
                spec = rooms[node]
                room = evaluate_room(spec, network.parameters[spec.instance_id],float(p[node]),total,h_in,w_in,
                                     old.get(node),dt,service)
                candidate[node] = room.state
                room_results[node] = room
            elif total > o.flow_zero_tolerance_kg_s:
                candidate[node] = service.state_phw(float(p[node]),h_in/total,w_in/total)
            elif node in boundary_states:
                candidate[node] = boundary_states[node]
            elif not incoming[node] and not outgoing[node]:
                # 有明确初态/上一接受解的停滞节点保留状态，不形成边界源。
                candidate[node] = service.state_phw(float(p[node]),states[node].enthalpy_j_kg_dry_air,states[node].humidity_ratio_kg_kg)
        humidity_defect = max(abs(a.humidity_ratio_kg_kg-b.humidity_ratio_kg_kg) for a,b in zip(candidate,states))
        temperature_defect = max(abs(a.temperature_k-b.temperature_k) for a,b in zip(candidate,states))
        heat_previous = np.array([d.heat_to_air_w for d in devices])
        if humidity_defect <= o.humidity_tolerance_kg_kg and temperature_defect <= network.project.solver.thermal_tolerance_k:
            # 账本使用这一轮设备实际流股，节点误差仍由独立守恒门槛检查。
            states = candidate
            break
        states = [service.state_phw(float(p[node]),
                    a.enthalpy_j_kg_dry_air+o.relaxation*(b.enthalpy_j_kg_dry_air-a.enthalpy_j_kg_dry_air),
                    a.humidity_ratio_kg_kg+o.relaxation*(b.humidity_ratio_kg_kg-a.humidity_ratio_kg_kg))
                  for node,(a,b) in enumerate(zip(states,candidate))]
    else:
        raise CompilationError('THERMAL_NOT_CONVERGED','热湿联合固定点未收敛')
    diagnostics.extend(heat_diagnostics)
    if any(value == 0 for value in mass):
        diagnostics.append(Diagnostic(code='AIR_STAGNANT_STATE',severity='info',
            message='零流量通路保留各端节点初态或已接受状态，不产生水分和热量输运'))
    outputs = {b.instance_id:d.outputs for b,d in zip(branches,devices) if d.outputs}
    for inst in network.instances.values():
        if network.modules[inst.module_id].solver_model == 'air_filter':
            outputs[inst.id] = {'loading_ratio':network.parameters[inst.id]['loading_ratio']}
    from .solver import port_mass_flows
    port_flows = port_mass_flows(network,flows)
    for inst in network.instances.values():
        kind = network.modules[inst.module_id].solver_model
        if kind in ('air_mixing_box','air_room'):
            inlet_ports = ('fresh_in','return_in') if kind == 'air_mixing_box' else ('supply_in',)
            outlet_port = 'supply_out' if kind == 'air_mixing_box' else 'return_out'
            inputs = [port_flows.get(f'{inst.id}:{name}',0.) for name in inlet_ports]
            output = port_flows.get(f'{inst.id}:{outlet_port}',0.)
            if any(q < -o.flow_zero_tolerance_kg_s for q in inputs) or output > o.flow_zero_tolerance_kg_s:
                raise CompilationError('AIR_REVERSE_FLOW_UNSUPPORTED',f'{inst.id} 不支持反向流动',inst.id)
            if kind == 'air_mixing_box':
                outputs[inst.id] = {'fresh_air_fraction':inputs[0]/sum(inputs) if sum(inputs)>o.flow_zero_tolerance_kg_s else None,
                                   'dry_air_mass_residual_kg_s':sum(inputs)+output}
    for b,d in zip(branches,devices):
        if d.outputs.get('limited'):
            diagnostics.append(Diagnostic(code='HUMIDIFIER_SATURATION_LIMITED',severity='warning',instance_id=b.instance_id,
                                           message='加湿量已按饱和极限限制，输出实际水量和补热量'))
    for j,b in enumerate(branches):
        params = network.parameters[b.instance_id]
        area = (params['duct_width_m']*params['duct_height_m'] if 'duct_width_m' in params
                else math.pi*params['diameter_m']**2/4 if 'diameter_m' in params else None)
        if area:
            inlet = states[up[j]]
            velocity = mass[j]*(1+inlet.humidity_ratio_kg_kg)/inlet.density_kg_m3/area
            if velocity > 100:
                raise CompilationError('AIR_VELOCITY_UNSUPPORTED',f'{b.instance_id} 实际速度 {velocity:.1f} m/s 超出低速模型范围',b.instance_id)
            if velocity > 30:
                diagnostics.append(Diagnostic(code='AIR_VELOCITY_HIGH',severity='warning',instance_id=b.instance_id,
                                              message=f'实际风速 {velocity:.1f} m/s 超过推荐的 30 m/s'))
    water_terms, energy_terms = [], []
    for node,q in boundary_supply.items():
        stream = boundary_states[node] if q > 0 else states[node]
        water_terms.append(q*stream.humidity_ratio_kg_kg)
        energy_terms.append(q*stream.enthalpy_j_kg_dry_air)
    for d in devices:
        water_terms.extend((d.water_added_kg_s,-d.water_removed_kg_s))
        energy_terms.extend((d.heat_to_air_w,-d.water_removed_kg_s*d.removed_water_enthalpy_j_kg))
    for node,room in room_results.items():
        outputs[rooms[node].instance_id] = room.outputs
        water_terms.extend((room.moisture_source_kg_s,-room.moisture_storage_kg_s))
        energy_terms.extend((room.energy_source_w,-room.energy_storage_w))
    wr, er = sum(water_terms),sum(energy_terms)
    # 初始动态帧固定房间初态，仅登记不平衡通量，不把它当作接受的时间步。
    for residual,terms,atol,rtol,scale,code in (
        (wr,water_terms,o.moisture_atol_kg_s,o.moisture_rtol,1e-6,'AIR_MOISTURE_IMBALANCE'),
        (er,energy_terms,o.energy_atol_w,o.energy_rtol,1.,'THERMAL_ENERGY_IMBALANCE')):
        if abs(residual) > atol+rtol*max(sum(map(abs,terms)),scale):
            raise CompilationError(code,f'湿空气独立守恒账未闭合：残差 {residual:.8g}')
    port_states = {key:states[node] for key,node in network.port_nodes.items()}
    branch_ports = set()
    for j,b in enumerate(branches):
        a,z = (b.input_port,b.output_port) if flows[j] >= 0 else (b.output_port,b.input_port)
        port_states[f'{b.instance_id}:{a}'] = states[up[j]]
        port_states[f'{b.instance_id}:{z}'] = devices[j].outlet_state
        branch_ports.update((f'{b.instance_id}:{a}',f'{b.instance_id}:{z}'))
    for c in network.project.connections:
        a,z = f'{c.source.instance_id}:{c.source.port_id}',f'{c.target.instance_id}:{c.target.port_id}'
        if a in branch_ports and z not in branch_ports:
            port_states[z] = port_states[a]
        elif z in branch_ports and a not in branch_ports:
            port_states[a] = port_states[z]
    for inst in network.instances.values():
        definition = network.modules[inst.module_id]
        if definition.solver_model == 'pressure_source':
            key = f'{inst.id}:{definition.ports[0].id}'
            node = network.port_nodes[key]
            port_states[key] = boundary_states[node] if boundary_supply[node] > 0 else states[node]
    result = ThermalResult(np.array([s.enthalpy_j_kg_dry_air for s in states]),states,flows,up,down,
        np.array([d.outlet_state.enthalpy_j_kg_dry_air for d in devices]),[d.outlet_state for d in devices],
        heat_previous,boundary_supply,boundary_states,port_states,0.,er,iteration,diagnostics=diagnostics,
        humidity_ratio=np.array([s.humidity_ratio_kg_kg for s in states]),coil_outputs=outputs,
        humidifier_moisture_kg_s=sum(d.water_added_kg_s for d in devices),moisture_residual_kg_s=wr)
    result.air_metrics = {'air_transport_iterations':iteration,'humidity_defect_max_kg_kg':humidity_defect,
        'dry_air_mass_residual_kg_s':hydraulic.mass_residual,'condensate_kg_s':sum(d.water_removed_kg_s for d in devices),
        'room_moisture_storage_rate_kg_s':sum(r.moisture_storage_kg_s for r in room_results.values())}
    result.air_room_results = room_results
    return result


def air_frame_values(network,result,variables,metrics,summary):
    """对外始终显示当地混合物质量；内部 m_da 不冒充公共质量流量。"""
    thermal = result.thermal
    for j,b in enumerate(network.branches):
        q = float(result.hydraulic.flows[j])
        inlet,outlet = thermal.node_states[thermal.upstream[j]],thermal.outlet_states[j]
        values = {'dry_air_mass_flow_kg_s':q,'mass_flow_kg_s':q*(1+inlet.humidity_ratio_kg_kg),
            'inlet_mass_flow_kg_s':q*(1+inlet.humidity_ratio_kg_kg),
            'outlet_mass_flow_kg_s':q*(1+outlet.humidity_ratio_kg_kg),
            'volume_flow_m3_h':q*(1+inlet.humidity_ratio_kg_kg)/inlet.density_kg_m3*3600}
        prefixes = [f'{b.instance_id}.{b.channel_id}']
        if sum(other.instance_id == b.instance_id for other in network.branches) == 1:
            prefixes.append(b.instance_id)
        for prefix in prefixes:
            variables.update({f'{prefix}.{k}':v for k,v in values.items()})
    for key,state in result.port_states.items():
        prefix = key.replace(':','.')
        for name in (*AIR_STATE_FIELDS,'mass_flow_kg_s','dry_air_mass_flow_kg_s','water_vapor_mass_flow_kg_s'):
            variables[f'{prefix}.{name}'] = getattr(state,name)
    metrics.update(thermal.air_metrics)
    summary.update(air_contract_version=1,continuity_basis='dry_air',public_mass_basis='humid_air',
                   thermal_basis='dry_air',moist_air_backend='coolprop_ha')
