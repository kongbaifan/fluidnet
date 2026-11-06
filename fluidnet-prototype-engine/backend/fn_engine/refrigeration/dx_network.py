"""Compile and evaluate a restricted DX loop around a single dynamic high-side vessel."""
from ..compiler import CompilationError
from .dx_devices import KINDS,branch_point


def compile_dx(kinds,nodes,used):
    groups={}
    for key in used:
        if key in nodes.parent and kinds[key[0]]!='refrigerant_header':groups.setdefault(nodes.find(key),[]).append(key)
    def neighbour(iid,port):
        candidates=[p for p in groups.get(nodes.find((iid,port)),[]) if p!=(iid,port)]
        if len(candidates)!=1:raise CompilationError('DX_SERIAL_REQUIRED','DX分支首版只允许阀→蒸发器→压缩机单路径',iid,port)
        return candidates[0]
    paths={};covered=set()
    for iid,kind in kinds.items():
        if kind!='dx_evaporator':continue
        valve,vport=neighbour(iid,'in0');compressor,cport=neighbour(iid,'out0')
        if kinds[valve]!='dx_expansion_valve' or vport!='out0' or kinds[compressor]!='dx_compressor' or cport!='in0':
            raise CompilationError('DX_CHAIN_INVALID','DX蒸发器必须接DX阀出口和DX压缩机进口',iid)
        vessel,port=neighbour(valve,'in0');sink,sink_port=neighbour(compressor,'out0')
        if kinds[sink] in ('evaporative_condenser','air_cooled_condenser') and sink_port=='in0':
            sink,sink_port=neighbour(sink,'out0')
        if kinds[vessel]!='saturated_vessel' or port!='liquid' or sink!=vessel or not sink_port.startswith('in'):
            raise CompilationError('DX_HIGH_SIDE_REQUIRED','DX分支必须从同一高压容器液相供液，并经冷凝器回到该容器',iid)
        paths[iid]={'valve':valve,'compressor':compressor,'vessel':vessel};covered.update((valve,compressor,iid))
    missing={iid for iid,kind in kinds.items() if kind in KINDS}-covered
    if missing:raise CompilationError('DX_CHAIN_INCOMPLETE','DX设备未组成完整合法分支',sorted(missing)[0])
    return paths


def evaluate_dx(network,services,vessels,temperatures,groups):
    room_of={c:r for r,cs in groups.items() for c in cs};out={};heat={};boundary=0.
    for iid,path in network.dx_paths.items():
        valve,compressor,vessel=path['valve'],path['compressor'],path['vessel'];p=network.parameters
        point=branch_point(services[vessel],vessels[vessel],temperatures[room_of[iid]],p[valve],p[iid],p[compressor])
        mass=point['mass_flow_kg_s'];hin=vessels[vessel].liquid_enthalpy_j_kg
        heat[vessel]=heat.get(vessel,0.)+point['heat_w']+point['shaft_power_w']
        boundary+=point['shaft_power_w']
        out[iid]={key:value for key,value in dict(point,room_cooling_w=point['heat_w'],inlet_enthalpy_j_kg=hin).items()
                  if key not in ('shaft_power_w','electric_power_w','discharge_enthalpy_j_kg')}
        out[valve]={'mass_flow_kg_s':mass,'inlet_enthalpy_j_kg':hin,'outlet_enthalpy_j_kg':hin}
        out[compressor]={'mass_flow_kg_s':mass,'inlet_enthalpy_j_kg':point['outlet_enthalpy_j_kg'],
            'outlet_enthalpy_j_kg':point['discharge_enthalpy_j_kg'],'shaft_power_w':point['shaft_power_w'],'electric_power_w':point['electric_power_w']}
    return out,heat,boundary
