"""风侧跨字段校验与房间状态登记。"""
from .compiler import CompilationError
from .moist_air import AirPropertyError, MoistAirService


def validate_air_parameters(network, overrides=None, check_boundary_conflicts=True):
    service=MoistAirService()
    boundaries={}
    for inst in network.instances.values():
        definition=network.modules[inst.module_id]
        params=(overrides or {}).get(inst.id,network.parameters[inst.id])
        kind=definition.solver_model
        try:
            if network.project.solver.moist_air and kind=='pressure_source':
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
                config=network.fluid_at(network.port_nodes[f'{inst.id}:in0'])
                if config.fluid!='Water' or config.phase_policy not in ('liquid','single_phase'):
                    raise AirPropertyError('TOWER_WATER_REQUIRED','湿空气冷却塔水侧只支持液态纯水')
                service.state_ptw(params['air_pressure_pa'],params['air_temperature_k'],params['air_humidity_ratio_kg_kg'])
            if network.project.solver.moist_air and params.get('thermal_cells',0):
                raise AirPropertyError('AIR_STORAGE_UNSUPPORTED','湿空气风管暂不支持管段分布热容；请使用房间状态')
        except AirPropertyError as error:
            raise CompilationError(error.code,f'{inst.id}：{error}',inst.id) from error


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
