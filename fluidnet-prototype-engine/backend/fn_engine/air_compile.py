"""风侧跨字段校验与房间状态登记。"""
from .compiler import CompilationError, service_at
from .moist_air import AirPropertyError, MoistAirService
from .properties import PropertyError
from .refrigeration.cycle import DeviceRangeError


def validate_air_parameters(network, overrides=None, check_boundary_conflicts=True):
    service=MoistAirService()
    boundaries={}
    for inst in network.instances.values():
        definition=network.modules[inst.module_id]
        params=(overrides or {}).get(inst.id,network.parameters[inst.id])
        kind=definition.solver_model
        try:
            first = network.port_nodes[f'{inst.id}:{definition.ports[0].id}']
            if first in network.air_nodes and kind=='pressure_source':
                state=service.state_ptw(params['pressure_pa'],params['temperature_k'],params.get('humidity_ratio_kg_kg',0.))
                node=network.port_nodes[f'{inst.id}:{definition.ports[0].id}']
                triple=(state.pressure_pa,state.temperature_k,state.humidity_ratio_kg_kg)
                if check_boundary_conflicts and node in boundaries and any(abs(a-b)>1e-9 for a,b in zip(triple,boundaries[node])):
                    raise AirPropertyError('BOUNDARY_CONFLICT','同节点多个压力/温湿度边界冲突')
                boundaries[node]=triple
            if kind=='humidifier' and (params['mode'] not in ('adiabatic','isothermal')
                                       or params.get('saturation_action','limit') not in ('limit','error')):
                raise AirPropertyError('AIR_HUMIDIFIER_PARAMETERS','加湿模式或饱和策略无效')
            if kind=='air_room':
                service.state_ptw(params['initial_pressure_pa'],params['outdoor_temperature_k'],params['outdoor_humidity_ratio_kg_kg'])
            if kind=='cooling_tower_moist':
                if not network.project.solver.thermal:
                    raise AirPropertyError('TOWER_THERMAL_REQUIRED','湿空气冷却塔需要启用热力计算')
                config=network.fluid_at(network.port_nodes[f'{inst.id}:in0'])
                if config.fluid!='Water' or config.phase_policy not in ('liquid','single_phase'):
                    raise AirPropertyError('TOWER_WATER_REQUIRED','湿空气冷却塔水侧只支持液态纯水')
                service.state_ptw(params['air_pressure_pa'],params['air_temperature_k'],params['air_humidity_ratio_kg_kg'])
            if kind in ('water_coil', 'water_chiller'):
                if not network.project.solver.thermal:
                    raise AirPropertyError('WATER_DEVICE_THERMAL_REQUIRED', '水盘管和冷水机组需要启用热力计算')
                liquid_ports = ('in1',) if kind == 'water_coil' else ('in0', 'in1')
                circuits = []
                for port in liquid_ports:
                    node = network.port_nodes[f'{inst.id}:{port}']
                    config = network.fluid_at(node)
                    if config.phase_policy not in ('liquid', 'single_phase') or config.fluid.split('::')[-1] == 'Air':
                        raise AirPropertyError('WATER_DEVICE_LIQUID_REQUIRED', '设备水侧必须接独立单相液体回路')
                    circuit = network.node_circuit[node]
                    from .thermal import phase_family
                    for boundary in network.fixed_pressures:
                        if network.node_circuit[boundary] == circuit:
                            state = service_at(network, node).state_pt(network.fixed_pressures[boundary],network.fixed_temperatures[boundary])
                            if phase_family(state) != 'liquid':
                                raise AirPropertyError('WATER_DEVICE_LIQUID_REQUIRED', '设备水侧的参考状态必须为液相')
                    circuits.append(circuit)
                if kind == 'water_chiller':
                    from .water_chiller import refrigerant_service
                    from .refrigeration.cycle import rated_displacement
                    if circuits[0] == circuits[1]:
                        raise AirPropertyError('CHILLER_CIRCUITS', '冷冻水与冷却水必须是两个独立回路')
                    if params['min_evaporating_temperature_k'] >= params['max_evaporating_temperature_k'] or params['min_condensing_temperature_k'] >= params['max_condensing_temperature_k']:
                        raise AirPropertyError('CHILLER_PARAMETERS', '机组运行温度下限必须小于上限')
                    rated_displacement(refrigerant_service(params), params)
            if network.project.solver.moist_air and params.get('thermal_cells',0):
                raise AirPropertyError('AIR_STORAGE_UNSUPPORTED','风水联算暂不支持管段分布热容；请使用房间状态')
        except (AirPropertyError, PropertyError, DeviceRangeError) as error:
            raise CompilationError(error.code,f'{inst.id}：{error}',inst.id) from error
        except ValueError as error:
            raise CompilationError('CHILLER_PARAMETERS', f'{inst.id}：{error}', inst.id) from error


def compile_air_network(network):
    from .air_room import build_spec
    validate_air_parameters(network)
    for inst in network.instances.values():
        definition=network.modules[inst.module_id]
        if definition.solver_model=='air_room':
            node=network.port_nodes[f'{inst.id}:supply_in']
            if node in network.air_rooms or node in network.fixed_pressures:
                raise CompilationError('AIR_ROOM_NODE_CONFLICT','每节点只能有一个房间，不能和压力边界直接合并',inst.id)
            try:
                network.air_rooms[node]=build_spec(inst.id,network.parameters[inst.id])
            except AirPropertyError as error:
                raise CompilationError(error.code,str(error),inst.id) from error
