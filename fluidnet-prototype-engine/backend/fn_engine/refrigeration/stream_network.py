"""Restricted serial stream paths between saturated storage boundaries.

Each path has one explicit compressor or valve and zero or more single-phase lines.
This is a local pressure/enthalpy solve, not a general two-phase pipe network.
"""
import math
from scipy.optimize import brentq

from ..compiler import CompilationError
from ..properties import PropertyError
from .cycle import DeviceRangeError
from .stream_devices import BRIDGES, LINES, RECUPERATOR, RECUPERATOR_PORTS, single_phase, line_point, compressor_point, counterflow_heat


def bounded_physical_root(evaluate, samples, iid):
    """Bracket roots inside valid physical intervals, refining both sides of an invalid trial."""
    previous=None;last_error=None
    def valid(x):
        nonlocal last_error
        try:
            result=evaluate(x)
            if not math.isfinite(result[0]):raise DeviceRangeError('STREAM_NOT_FINITE','流股残差不是有限数值',iid)
            return result
        except (DeviceRangeError,PropertyError) as error:
            last_error=error
            return None
    def edge(valid_x,invalid_x):
        for _ in range(48):
            middle=(valid_x+invalid_x)/2.
            if valid(middle) is None:invalid_x=middle
            else:valid_x=middle
        return valid_x,valid(valid_x)
    def between(left,right):
        if left[1][0]*right[1][0]>0.:return None
        def residual(x):
            result=valid(x)
            if result is None:raise DeviceRangeError('STREAM_ROOT_DOMAIN','流股根区间穿过无效物态',iid)
            return result[0]
        x=brentq(residual,left[0],right[0],xtol=1e-14,rtol=1e-12)
        return x,evaluate(x)
    for x in samples:
        result=valid(x)
        if result is not None and result[0]==0.:return x,result
        if previous is not None:
            last_x,last=previous
            if last is not None and result is not None:found=between(previous,(x,result))
            elif last is not None:found=between(previous,edge(last_x,x))
            elif result is not None:found=between(edge(x,last_x),(x,result))
            else:found=None
            if found is not None:return found
        previous=x,result
    raise DeviceRangeError('STREAM_NOT_CONVERGED',f'声明流股范围内未找到合法包围根：{last_error or "残差未跨零"}',iid)


def compile_paths(kinds, nodes, used, parameters):
    groups={}
    for key in used:
        if key in nodes.parent and kinds[key[0]]!='refrigerant_header':groups.setdefault(nodes.find(key),[]).append(key)
    consumed=set();paths={}
    def walk(key,backward):
        steps=[];visited=set()
        while True:
            options=[p for p in groups.get(nodes.find(key),[]) if p!=key]
            if len(options)!=1:
                raise CompilationError('STREAM_SERIAL_REQUIRED','有焓流股首版只接受无分支串联路径',key[0],key[1])
            target=options[0];iid,port=target;kind=kinds[iid]
            if iid in visited:raise CompilationError('STREAM_LOOP','有焓流股串联路径存在环',iid)
            visited.add(iid)
            if kind=='saturated_vessel':
                if backward and port not in ('vapor','liquid') or not backward and not port.startswith('in'):
                    raise CompilationError('STREAM_VESSEL_PORT','流股从容器相别出口开始并进入容器进口',iid,port)
                return target,list(reversed(steps)) if backward else steps
            if not backward and kind in ('evaporative_condenser','air_cooled_condenser') and port=='in0':
                # Legacy condenser removes heat from the destination reservoir, not this stream.
                key=(iid,'out0');continue
            if kind==RECUPERATOR:
                inlet=next((a for a,b in RECUPERATOR_PORTS.items() if port==(b if backward else a)),None)
                if inlet is None:raise CompilationError('STREAM_DIRECTION','回热器必须按端口方向连接',iid,port)
                side=inlet.split('_')[0];label=iid+'#'+side
                if label in consumed:raise CompilationError('STREAM_SHARED_LINE','回热器通路被重复使用',iid,port)
                consumed.add(label);steps.append(label);key=(iid,inlet if backward else RECUPERATOR_PORTS[inlet]);continue
            if kind not in LINES or port!=('out0' if backward else 'in0'):
                raise CompilationError('STREAM_COMPONENT_UNSUPPORTED','流股桥只能经专用单相流股设备连接容器',iid,port)
            if iid in consumed:raise CompilationError('STREAM_SHARED_LINE','同一管段不能属于两条流股桥',iid)
            if parameters[iid]['segments']!=int(parameters[iid]['segments']):
                raise CompilationError('PARAMETER_RANGE','空间分段数必须为整数',iid,'segments')
            consumed.add(iid);steps.append(iid);key=(iid,'in0' if backward else 'out0')
    for iid,kind in kinds.items():
        if kind not in BRIDGES:continue
        a,b=BRIDGES[kind];source,before=walk((iid,a),True);sink,after=walk((iid,b),False)
        expected='vapor' if kind=='enthalpy_compressor' else 'liquid'
        if source[1]!=expected:raise CompilationError('STREAM_SOURCE_PHASE',f'{iid}需要容器{expected}相出口',iid,a)
        paths[iid]={'source':source,'sink':sink,'before':before,'after':after}
    unused={iid for iid,kind in kinds.items() if kind in LINES}-consumed
    if unused:raise CompilationError('STREAM_BRIDGE_REQUIRED','单相流股管段必须属于有焓压缩机或阀路径',sorted(unused)[0])
    for iid,kind in kinds.items():
        if kind==RECUPERATOR and not {iid+'#hot',iid+'#cold'}<=consumed:
            raise CompilationError('STREAM_RECUPERATOR_PATHS','回热器两侧必须各自属于有效的流股桥',iid)
    return paths


def evaluate_path(iid,path,kind,parameters,service,vessels,options,exchanged=None):
    source,phase=path['source'];sink,_=path['sink']
    start,end=vessels[source],vessels[sink]
    p=parameters[iid]
    source_h=start.vapor_enthalpy_j_kg if phase=='vapor' else start.liquid_enthalpy_j_kg
    off=(kind=='enthalpy_compressor' and (p['running']<.5 or p['load_ratio']==0.)) or (kind=='enthalpy_valve' and (p['opening_ratio']==0. or start.pressure_pa<=end.pressure_pa))

    def candidate(mass,bridge_pressure):
        pressure,enthalpy=start.pressure_pa,source_h;outputs={};heat=0.
        def segment(line,pressure,enthalpy):
            if '#' not in line:return line_point(service,parameters[line],pressure,enthalpy,mass)
            device,side=line.split('#');q=(exchanged or {}).get(device,0.)*(-1. if side=='hot' else 1.)
            inlet,phase=single_phase(service,pressure,enthalpy)
            hout=enthalpy+q/mass if mass>1e-14 else enthalpy
            outlet,_=single_phase(service,pressure,hout,phase)
            return pressure,hout,{'mass_flow_kg_s':mass,'heat_w':q if mass>1e-14 else 0.,'inlet_enthalpy_j_kg':enthalpy,
                'outlet_enthalpy_j_kg':hout,'inlet_temperature_k':inlet.temperature_k,'outlet_temperature_k':outlet.temperature_k,
                'capacity_w_k':mass*inlet.specific_heat_j_kg_k}
        for line in path['before']:
            pressure,enthalpy,row=segment(line,pressure,enthalpy)
            outputs[line]=row;heat+=row['heat_w']
        inlet_p,inlet_h=pressure,enthalpy
        if kind=='enthalpy_compressor':
            expected,enthalpy,shaft,electric=compressor_point(service,p,pressure,enthalpy,bridge_pressure)
        else:
            liquid,fluid_phase=single_phase(service,pressure,enthalpy)
            if fluid_phase!='liquid':raise DeviceRangeError('STREAM_VALVE_PHASE','有焓节流阀入口须为液态',iid)
            expected=p['kv_m3_h']*p['opening_ratio']/3600.*math.sqrt(max(0.,1000.*liquid.density_kg_m3*(pressure-bridge_pressure)/1e5))
            shaft=electric=0.
        pressure=bridge_pressure
        outputs[iid]={'mass_flow_kg_s':mass,'inlet_pressure_pa':inlet_p,'outlet_pressure_pa':pressure,
            'inlet_enthalpy_j_kg':inlet_h,'outlet_enthalpy_j_kg':enthalpy,'shaft_power_w':shaft,'electric_power_w':electric}
        for line in path['after']:
            pressure,enthalpy,row=segment(line,pressure,enthalpy)
            outputs[line]=row;heat+=row['heat_w']
        return expected,pressure,enthalpy,shaft,electric,heat,outputs

    if off:
        # No moving mass, no instantaneous UA heat transfer in a storage-free isolated line.
        result=candidate(0.,end.pressure_pa)
        return 0.,source_h,source_h,0.,result[-1]
    if kind=='enthalpy_compressor':
        guess=p['displacement_m3_s']*p['load_ratio']*p['volumetric_efficiency']*start.vapor_density_kg_m3
    else:
        guess=p['kv_m3_h']*p['opening_ratio']/3600.*math.sqrt(1000.*start.liquid_density_kg_m3*(start.pressure_pa-end.pressure_pa)/1e5)
    def at_mass(mass):
        if not path['after']:
            result=candidate(mass,end.pressure_pa)
        else:
            def pressure_residual(bridge_pressure):
                row=candidate(mass,bridge_pressure)
                return row[1]-end.pressure_pa,row
            maximum=max(start.pressure_pa,end.pressure_pa)*10.
            _,(_,result)=bounded_physical_root(pressure_residual,
                [end.pressure_pa+(maximum-end.pressure_pa)*i/16. for i in range(17)],iid)
        return mass-result[0],result
    scale=max(guess,1e-8)
    samples=sorted({scale*value for value in (1e-6,1e-4,.01,.05,.1,.25,.5,.75,1.,1.5,2.,4.,8.,16.,32.,64.,100.)})
    mass,(_,result)=bounded_physical_root(at_mass,samples,iid)
    expected,pressure,hout,shaft,electric,heat,outputs=result
    if abs(mass-expected)>options.mass_tolerance_kg_s or abs(pressure-end.pressure_pa)>options.pressure_tolerance_pa:
        raise DeviceRangeError('STREAM_NOT_CONVERGED','有焓流股未满足原质量/压力容差',iid)
    if abs(mass*(hout-source_h)-shaft-heat)>max(.001,1e-8*max(abs(shaft),abs(heat))):
        raise DeviceRangeError('STREAM_ENERGY_RESIDUAL','有焓流股热量与轴功未闭合',iid)
    return mass,source_h,hout,shaft+heat,outputs


def evaluate_paths(network,services,vessels):
    parameters={iid:dict(p) for iid,p in network.parameters.items()}
    for iid,kind in network.kinds.items():
        if kind=='immersed_tube_bundle':parameters[iid]['ambient_temperature_k']=vessels[network.vessel(iid,'shell_in')].temperature_k
    exchanges={iid:0. for iid,kind in network.kinds.items() if kind==RECUPERATOR}
    for iteration in range(80):
        dm=dict.fromkeys(network.vessels,0.);du=dict.fromkeys(network.vessels,0.);outputs={};boundary=0.
        for iid,path in network.stream_paths.items():
            source=path['source'][0];sink=path['sink'][0]
            mass,hin,hout,power,rows=evaluate_path(iid,path,network.kinds[iid],parameters,services[source],vessels,network.project.solver,exchanges)
            dm[source]-=mass;dm[sink]+=mass;du[source]-=mass*hin;du[sink]+=mass*hout
            boundary+=power;outputs.update(rows)
        targets={}
        for iid in exchanges:
            a,b=outputs[iid+'#hot'],outputs[iid+'#cold']
            targets[iid]=counterflow_heat(network.parameters[iid]['ua_w_k'],a['capacity_w_k'],b['capacity_w_k'],a['inlet_temperature_k'],b['inlet_temperature_k'])
        if all(abs(targets[iid]-q)<1e-4 for iid,q in exchanges.items()):break
        exchanges={iid:0. if targets[iid]==0. else .5*q+.5*targets[iid] for iid,q in exchanges.items()}
    else:raise DeviceRangeError('STREAM_HEAT_NOT_CONVERGED','回热器与流股流量联立未收敛')
    for iid,q in exchanges.items():
        result={'heat_w':q}
        for side in ('hot','cold'):
            values=outputs.pop(iid+'#'+side)
            result.update({side+'_'+key:value for key,value in values.items() if key not in ('heat_w','capacity_w_k')})
        outputs[iid]=result
    for iid,kind in network.kinds.items():
        if kind=='immersed_tube_bundle':
            shell=network.vessel(iid,'shell_in');q=-outputs[iid]['heat_w']
            du[shell]+=q;boundary+=q
            state=vessels[shell]
            outputs[iid].update(shell_heat_w=q,shell_temperature_k=state.temperature_k,shell_mass_kg=state.mass_kg,shell_internal_energy_j=state.internal_energy_j)
    return dm,du,boundary,outputs
