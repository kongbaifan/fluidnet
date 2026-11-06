"""Explicit single-phase refrigerant streams; no hidden change to legacy saturated devices."""
import math

from ..hydraulic_derivatives import pipe_drop
from .cycle import DeviceRangeError, compress

BRIDGES={'enthalpy_compressor':('suction','discharge'),'enthalpy_valve':('in0','out0')}
LINES={'refrigerant_line','refrigerant_subcooler','immersed_tube_bundle'}
RECUPERATOR='refrigerant_recuperator'
RECUPERATOR_PORTS={'hot_in':'hot_out','cold_in':'cold_out'}


def counterflow_heat(ua,hot_capacity,cold_capacity,hot_temperature,cold_temperature):
    if min(hot_capacity,cold_capacity)<=0. or ua<=0.:return 0.
    minimum,maximum=min(hot_capacity,cold_capacity),max(hot_capacity,cold_capacity)
    ratio=minimum/maximum;ntu=ua/minimum
    if abs(1.-ratio)<1e-10:effectiveness=ntu/(1.+ntu)
    else:
        exponential=math.exp(-ntu*(1.-ratio));effectiveness=(1.-exponential)/(1.-ratio*exponential)
    return effectiveness*minimum*(hot_temperature-cold_temperature)


def single_phase(service, pressure, enthalpy, expected=None):
    if pressure<=0.:
        raise DeviceRangeError('REFRIGERANT_STREAM_PRESSURE','流股压力必须为正')
    state=service.state_ph(pressure,enthalpy)
    phase = ('liquid' if state.quality is not None and state.quality <= 1e-9 else
             'gas' if state.quality is not None and state.quality >= 1.-1e-9 else state.phase)
    if phase not in ('liquid','gas','supercritical_liquid','supercritical_gas') or expected and phase!=expected:
        raise DeviceRangeError('REFRIGERANT_LINE_PHASE','该流股必须保持声明的单相；不允许把两相管段当作单相计算')
    if state.specific_heat_j_kg_k is None and phase in ('liquid','gas'):
        # PH rounding at a saturation endpoint can report an infinitesimal two-phase quality.
        state=service.state_pq(pressure,1. if phase=='gas' else 0.).model_copy(update={'enthalpy_j_kg':enthalpy})
    return state,phase


def line_point(service,p,pressure,enthalpy,mass):
    inlet,phase=single_phase(service,pressure,enthalpy)
    initial_p,initial_h=pressure,enthalpy
    if mass<=1e-14:
        return pressure,enthalpy,{'mass_flow_kg_s':0.,'pressure_drop_pa':0.,'heat_w':0.,'inlet_enthalpy_j_kg':enthalpy,
            'outlet_enthalpy_j_kg':enthalpy,'inlet_pressure_pa':pressure,'outlet_pressure_pa':pressure,
            'inlet_temperature_k':inlet.temperature_k,'outlet_temperature_k':inlet.temperature_k}
    segments=int(p.get('segments',8))
    for _ in range(segments):
        state,_=single_phase(service,pressure,enthalpy,phase)
        cp=state.specific_heat_j_kg_k
        heat=mass*cp*(p['ambient_temperature_k']-state.temperature_k)*(-math.expm1(-p['heat_loss_ua_w_k']/segments/(mass*cp)))
        enthalpy+=heat/mass
        drop=pipe_drop({'length_m':p['length_m']/segments,'diameter_m':p['diameter_m'],'roughness_m':p['roughness_m']},mass,
                       state.density_kg_m3,state.viscosity_pa_s)
        pressure-=drop
        single_phase(service,pressure,enthalpy,phase)
    outlet,_=single_phase(service,pressure,enthalpy,phase)
    return pressure,enthalpy,{'mass_flow_kg_s':mass,'pressure_drop_pa':initial_p-pressure,'heat_w':mass*(enthalpy-initial_h),
        'inlet_enthalpy_j_kg':initial_h,'outlet_enthalpy_j_kg':enthalpy,'inlet_pressure_pa':initial_p,'outlet_pressure_pa':pressure,
        'inlet_temperature_k':inlet.temperature_k,'outlet_temperature_k':outlet.temperature_k}


def compressor_point(service,p,pressure,enthalpy,discharge):
    suction,phase=single_phase(service,pressure,enthalpy)
    if phase not in ('gas','supercritical_gas'):
        raise DeviceRangeError('STREAM_COMPRESSOR_PHASE','压缩机入口必须为气相')
    mass=p['displacement_m3_s']*p['load_ratio']*p['volumetric_efficiency']*suction.density_kg_m3 if p['running']>=.5 else 0.
    if mass<=0.:return 0.,enthalpy,0.,0.
    if discharge<=pressure:raise DeviceRangeError('COMPRESSOR_PRESSURE_RATIO','排气压力必须高于真实吸气压力')
    _,h2=compress(service,suction,discharge,p['isentropic_efficiency'])
    shaft=mass*(h2-enthalpy)
    return mass,h2,shaft,shaft/p['motor_efficiency']


def definitions():
    from ..catalog import _stream,_var,_ratio,_celsius,_switch,number
    from ..models import ModuleDefinition,Direction
    values=[_var('mass_flow_kg_s','流股质量流量','mass_flow','kg/s'),
        _var('inlet_enthalpy_j_kg','真实入口焓','specific_enthalpy','J/kg','kJ/kg',1000.),
        _var('outlet_enthalpy_j_kg','真实出口焓','specific_enthalpy','J/kg','kJ/kg',1000.),
        _var('inlet_pressure_pa','真实入口压力','pressure','Pa','kPa',1000.),
        _var('outlet_pressure_pa','真实出口压力','pressure','Pa','kPa',1000.)]
    line=ModuleDefinition(id='refrigerant_line',name='制冷剂单相流股管段',category='制冷站设备',solver_model='refrigerant_line',
        description='有焓流股专用串联管段：Darcy压降和环境换热逐段推进真实p/h。无储量、无高差，不接受两相；必须串接有焓压缩机/阀桥。',
        ports=[_stream('in0','入口',Direction.in_),_stream('out0','出口',Direction.out)],
        parameters=[number('length_m','长度',2.,'length','m',minimum=0.),number('diameter_m','内径',.05,'length','m','mm',.001,minimum=.001),
            number('roughness_m','绝对粗糙度',1e-5,'length','m','mm',.001,minimum=0.),
            number('heat_loss_ua_w_k','环境换热UA',0.,'conductance','W/K',minimum=0.),_celsius('ambient_temperature_k','环境温度',293.15),
            number('segments','空间分段数',8.,'count','1',minimum=1.,maximum=64.)],
        variables=values+[_var('pressure_drop_pa','压降','pressure','Pa','kPa',1000.),_var('heat_w','环境向流股热量','power','W'),
            _var('inlet_temperature_k','进口温度','temperature','K','°C',offset=-273.15),
            _var('outlet_temperature_k','出口温度','temperature','K','°C',offset=-273.15)])
    comp=ModuleDefinition(id='enthalpy_compressor',name='真实入口焓压缩机',category='制冷站设备',solver_model='enthalpy_compressor',
        description='显式流股桥：实际入口p/h决定吸气密度和压缩功，出口焓真实进入下游。定效率教学模型，非厂家标定。',
        ports=[_stream('suction','吸气',Direction.in_),_stream('discharge','排气',Direction.out)],
        parameters=[_switch(),_ratio('load_ratio','载量',.75,runtime=True),number('displacement_m3_s','排量',.01,'volume_flow','m³/s','m³/h',1/3600,minimum=1e-8),
            _ratio('volumetric_efficiency','容积效率',.8,minimum=.01),_ratio('isentropic_efficiency','等熵效率',.72,minimum=.01),
            _ratio('motor_efficiency','电机效率',.92,minimum=.01)],
        variables=values+[_var('shaft_power_w','压缩轴功','power','W','kW',1000.),_var('electric_power_w','压缩机电功','power','W','kW',1000.),
            _var('state.electric_energy_j','累计电量','energy','J','kWh',3600000.,source='state')])
    valve=ModuleDefinition(id='enthalpy_valve',name='真实入口焓节流阀',category='制冷站设备',solver_model='enthalpy_valve',
        description='显式流股桥：入口实际液态p/h及密度决定Kv流量，出口保留入口焓。两相出口仅能直接入容器，不能接单相管段。',
        ports=[_stream('in0','入口',Direction.in_),_stream('out0','出口',Direction.out)],
        parameters=[number('kv_m3_h','Kv',.05,'flow_coefficient','m³/h',minimum=.000001),_ratio('opening_ratio','开度',.5,runtime=True)],variables=values)
    subcooler=line.model_copy(deep=True,update={'id':'refrigerant_subcooler','name':'制冷剂外部冷源过冷器','solver_model':'refrigerant_subcooler',
        'description':'独立有焓流股设备：环境冷源UA降低液体焓，下游阀读取实际焓；无储量，外部冷源温度显式输入。'})
    for spec in subcooler.parameters:
        if spec.id=='heat_loss_ua_w_k':spec.default=50.
        if spec.id=='length_m':spec.default=0.
    recuperator=ModuleDefinition(id=RECUPERATOR,name='制冷剂吸液回热器',category='制冷站设备',solver_model=RECUPERATOR,
        description='两条显式单相流股逆流ε-NTU，热流等量反向并与两条质量桥联立；无储量、首版忽略压降，端口焓真实传播。',
        ports=[_stream('hot_in','液侧进口',Direction.in_),_stream('hot_out','液侧出口',Direction.out),
               _stream('cold_in','吸气侧进口',Direction.in_),_stream('cold_out','吸气侧出口',Direction.out)],
        parameters=[number('ua_w_k','回热UA',10.,'conductance','W/K',minimum=0.)],
        variables=[_var('heat_w','热侧向冷侧热流','power','W'),
            *[_var(f'{side}_{key}',f'{side} {label}',quantity,unit) for side in ('hot','cold')
              for key,label,quantity,unit in [('mass_flow_kg_s','质量流量','mass_flow','kg/s'),
                ('inlet_enthalpy_j_kg','入口焓','specific_enthalpy','J/kg'),('outlet_enthalpy_j_kg','出口焓','specific_enthalpy','J/kg'),
                ('inlet_temperature_k','入口温度','temperature','K'),('outlet_temperature_k','出口温度','temperature','K')]]])
    bundle=subcooler.model_copy(deep=True,update={'id':'immersed_tube_bundle','name':'有限UA浸没管束','solver_model':'immersed_tube_bundle',
        'description':'管程真实单相p/h流股与壳侧饱和容器交换有限UA热量；壳体M/U只由连接的唯一容器持有。管程无库存，shell两口无净质量，禁止重复计壳体存量。'})
    bundle.ports.extend([_stream('shell_in','壳侧容器取相连接',Direction.in_,circuit='shell'),_stream('shell_out','壳侧容器返回',Direction.out,circuit='shell')])
    for port in bundle.ports[:2]:port.circuit='tube'
    bundle.parameters=[spec for spec in bundle.parameters if spec.id!='ambient_temperature_k']
    for key,label,quantity,unit in [('shell_heat_w','管程向壳体传热','power','W'),('shell_temperature_k','壳体温度','temperature','K'),('shell_mass_kg','壳体唯一库存','mass','kg'),('shell_internal_energy_j','壳体内能','energy','J')]:
        bundle.variables.append(_var(key,label,quantity,unit))
    return [line,comp,valve,subcooler,recuperator,bundle]
