"""Massless, acyclic thermal aggregation without duplicate room heat capacities."""
def definition():
    from ..model_types.module import ModuleDefinition
    from .._module_schema_v1 import PortSpec, Domain, Direction
    from ..catalog import _var
    return ModuleDefinition(id='room_heat_manifold',name='库房冷量汇集器',category='制冷站设备',solver_model='room_heat_manifold',
        description='八个热输入可级联汇入一个库房；无热容、不改变冷量。环路、空汇集器和重复归属拒绝。',
        variables=[_var('cooling_power_w','汇入净冷量','power','W','kW',1000.),_var('cooler_count','汇集冷风机数','count','1')],
        ports=[PortSpec(id=f'in{i}',label=f'冷量输入{i+1}',domain=Domain.thermal,direction=Direction.in_,required=False) for i in range(8)]+
              [PortSpec(id='out0',label='库房热接口',domain=Domain.thermal,direction=Direction.out)])


def groups(kinds,links,ports):
    from ..compiler import CompilationError
    incoming={};parents={}
    for a,b in links:
        if ports[a].domain!='thermal':continue
        source,target=(a,b) if ports[a].direction=='out' else (b,a)
        incoming.setdefault(target[0],[]).append(source[0]);parents.setdefault(source[0],[]).append(target[0])
    manifolds={i for i,k in kinds.items() if k=='room_heat_manifold'}
    visited=set();assigned=set();result={}
    def descend(iid,stack):
        if iid in stack:raise CompilationError('ROOM_HEAT_CYCLE','冷量汇集不能形成环',iid)
        if kinds[iid] in ('air_cooler','dx_evaporator'):
            if iid in assigned:raise CompilationError('ROOM_HEAT_DUPLICATE','冷风机不能重复计入库房',iid)
            assigned.add(iid);return [iid]
        if iid not in manifolds:raise CompilationError('ROOM_HEAT_ROLE','冷量汇集只接受冷风机或汇集器',iid)
        visited.add(iid)
        if not incoming.get(iid):raise CompilationError('ROOM_HEAT_EMPTY','汇集器至少需要一个冷风机输入',iid)
        if len(parents.get(iid,[]))!=1:raise CompilationError('ROOM_HEAT_OWNER','汇集器只能归属一个库房',iid)
        return [cooler for source in incoming[iid] for cooler in descend(source,stack|{iid})]
    for room,kind in kinds.items():
        if kind=='cold_room':result[room]=[c for source in incoming.get(room,[]) for c in descend(source,{room})]
    if manifolds-visited:raise CompilationError('ROOM_HEAT_ORPHAN','汇集器须最终连接库房，不得形成独立环',sorted(manifolds-visited)[0])
    return result


def outputs(network, device_outputs):
    inputs={}
    for edge in network.project.connections:
        a,b=edge.source,edge.target
        definition=network.modules[network.instances[a.instance_id].module_id]
        port=next(port for port in definition.ports if port.id==a.port_id)
        source,target=(a,b) if port.direction=='out' else (b,a)
        if network.kinds.get(target.instance_id)=='room_heat_manifold':
            inputs.setdefault(target.instance_id,[]).append(source.instance_id)
    def leaves(iid):
        if network.kinds[iid] in ('air_cooler','dx_evaporator'):return [iid]
        return [leaf for child in inputs.get(iid,[]) for leaf in leaves(child)]
    return {iid:{'cooling_power_w':sum(device_outputs[leaf]['room_cooling_w'] for leaf in leaves(iid)),
        'cooler_count':len(leaves(iid))} for iid,kind in network.kinds.items() if kind=='room_heat_manifold'}
