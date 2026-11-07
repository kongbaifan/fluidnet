"""Quasi-steady two-zone DX branch; no refrigerant storage in the evaporator or piping."""
import math
from scipy.optimize import brentq

from .cycle import DeviceRangeError, compress

KINDS={'dx_expansion_valve','dx_evaporator','dx_compressor'}


def evaporator_point(service,p,pressure,hin,mass,room_temperature):
    liquid=service.state_pq(pressure,0.);vapor=service.state_pq(pressure,1.)
    if mass<=0.:
        return {'outlet_enthalpy_j_kg':hin,'heat_w':0.,'superheat_k':0.,'superheated':False,'outlet_temperature_k':liquid.temperature_k}
    approach=room_temperature-vapor.temperature_k
    if approach<=0.:raise DeviceRangeError('DX_NO_DRIVING_TEMPERATURE','库温必须高于蒸发温度')
    needed=mass*max(0.,vapor.enthalpy_j_kg-hin)
    boiling_ua=needed/approach
    if boiling_ua>=p['ua_w_k']:
        heat=p['ua_w_k']*approach
        return {'outlet_enthalpy_j_kg':hin+heat/mass,'heat_w':heat,'superheat_k':0.,'superheated':False,
                'outlet_temperature_k':vapor.temperature_k}
    cp=vapor.specific_heat_j_kg_k
    superheat=approach*(-math.expm1(-(p['ua_w_k']-boiling_ua)/(mass*cp)))
    out=service.state_pt(pressure,vapor.temperature_k+max(superheat,1e-7))
    return {'outlet_enthalpy_j_kg':out.enthalpy_j_kg,'heat_w':mass*(out.enthalpy_j_kg-hin),
            'superheat_k':superheat,'superheated':True,'outlet_temperature_k':out.temperature_k}


def branch_point(service,high,room_temperature,valve,evaporator,compressor):
    if valve['opening_ratio']==0. or compressor['running']<.5 or compressor['load_ratio']==0.:
        if valve['opening_ratio']>0. and (compressor['running']<.5 or compressor['load_ratio']==0.):
            raise DeviceRangeError('DX_OFF_VALVE_OPEN','DX无制冷剂储量模型要求停机时关闭供液阀')
        if valve['opening_ratio']==0. and compressor['running']>=.5 and compressor['load_ratio']>0.:
            raise DeviceRangeError('DX_COMPRESSOR_STARVED','阀关闭时须同步停机；首版不模拟抽空过程')
        return {'mass_flow_kg_s':0.,'heat_w':0.,'shaft_power_w':0.,'electric_power_w':0.,'superheat_k':None,
                'evaporating_pressure_pa':None,'outlet_temperature_k':None,'outlet_enthalpy_j_kg':None,'discharge_enthalpy_j_kg':None}
    hin=high.liquid_enthalpy_j_kg
    def point(temperature):
        pressure=service.state_tq(temperature,1.).pressure_pa
        if pressure>=high.pressure_pa:return None
        mass=valve['kv_m3_h']*valve['opening_ratio']/3600.*math.sqrt(1000.*high.liquid_density_kg_m3*(high.pressure_pa-pressure)/1e5)
        evap=evaporator_point(service,evaporator,pressure,hin,mass,room_temperature)
        if not evap['superheated'] or evap['superheat_k']<evaporator['minimum_superheat_k']:return None
        suction=service.state_ph(pressure,evap['outlet_enthalpy_j_kg'])
        flow=compressor['displacement_m3_s']*compressor['load_ratio']*compressor['volumetric_efficiency']*suction.density_kg_m3
        return mass-flow,mass,pressure,evap,suction
    low=evaporator['minimum_evaporating_temperature_k'];high_t=min(room_temperature-1e-3,high.temperature_k-1e-3)
    previous=None;solution=None
    def root_between(a,b):
        left,right=point(a),point(b)
        if left is not None and right is not None and left[0]*right[0]<=0.:
            return brentq(lambda t:point(t)[0],a,b,xtol=1e-9)
        return None
    def valid_edge(valid_t,invalid_t):
        # Include the actual admissible edge, rather than dropping the final coarse interval.
        for _ in range(60):
            middle=(valid_t+invalid_t)/2.
            if point(middle) is None:invalid_t=middle
            else:valid_t=middle
        return valid_t
    for index in range(97):
        temperature=low+(high_t-low)*index/96.
        current=point(temperature)
        if previous is not None:
            last_t,last=previous
            if last is not None and current is None:
                solution=root_between(last_t,valid_edge(last_t,temperature))
            elif last is None and current is not None:
                solution=root_between(valid_edge(temperature,last_t),temperature)
            elif last is not None and current is not None:
                solution=root_between(last_t,temperature)
            if solution is not None:break
        if current is None:previous=temperature,None;continue
        if current[0]==0.:solution=temperature;break
        previous=temperature,current
    if solution is None:raise DeviceRangeError('DX_OPERATING_POINT','阀、蒸发器与压缩机在声明温区内无满足最小过热的联立工作点')
    residual,mass,pressure,evap,suction=point(solution)
    if abs(residual)>1e-8:raise DeviceRangeError('DX_MASS_RESIDUAL','DX流量联立残差超过1e-8 kg/s')
    _,hout=compress(service,suction,high.pressure_pa,compressor['isentropic_efficiency'])
    shaft=mass*(hout-suction.enthalpy_j_kg)
    return dict(evap,mass_flow_kg_s=mass,shaft_power_w=shaft,electric_power_w=shaft/compressor['motor_efficiency'],
                evaporating_pressure_pa=pressure,discharge_enthalpy_j_kg=hout)


def definitions():
    from ..catalog import _stream,_var,_ratio,_switch,_celsius,number
    from ..model_types.module import ModuleDefinition
    from .._module_schema_v1 import Direction, Domain, PortSpec
    stream=lambda: [_stream('in0','入口',Direction.in_),_stream('out0','出口',Direction.out)]
    values=[_var('mass_flow_kg_s','质量流量','mass_flow','kg/s'),_var('inlet_enthalpy_j_kg','真实入口焓','specific_enthalpy','J/kg'),
            _var('outlet_enthalpy_j_kg','真实出口焓','specific_enthalpy','J/kg')]
    valve=ModuleDefinition(id='dx_expansion_valve',name='DX供液调节阀',category='制冷站设备',solver_model='dx_expansion_valve',
        description='DX局部联立专用Kv等焓阀；供液量和蒸发压力与蒸发器/压缩机联合求解，非单独过热控制器。',ports=stream(),
        parameters=[number('kv_m3_h','额定Kv',.04,'flow_coefficient','m³/h',minimum=1e-6),_ratio('opening_ratio','开度',.5,runtime=True)],variables=values)
    evaporator=ModuleDefinition(id='dx_evaporator',name='DX两区蒸发器',category='制冷站设备',solver_model='dx_evaporator',
        description='沸腾区UA按潜热需求划分，剩余UA加热气相；实际焓进入压缩机。冷媒无储量，库房有热容。过供无气相出口时拒绝；不含结霜/压降。',
        ports=stream()+[PortSpec(id='heat',label='库房冷量',domain=Domain.thermal,direction=Direction.out,circuit='thermal')],
        parameters=[number('ua_w_k','总UA',1000.,'conductance','W/K',minimum=.01),
            _celsius('minimum_evaporating_temperature_k','蒸发工作温区下限',233.15),number('minimum_superheat_k','最小合法过热度',.5,'temperature_difference','K',minimum=.001)],
        variables=values+[_var('heat_w','制冷剂吸热','power','W'),_var('room_cooling_w','库房净冷量','power','W'),
            _var('superheat_k','真实出口过热度','temperature_difference','K'),_var('evaporating_pressure_pa','蒸发压力','pressure','Pa'),
            _var('state.cooling_energy_j','累计冷量','energy','J',source='state')])
    compressor=ModuleDefinition(id='dx_compressor',name='DX真实吸气压缩机',category='制冷站设备',solver_model='dx_compressor',
        description='与DX蒸发器和阀联合求蒸发压力；由实际出口气态密度/焓计算流量和功，冷媒侧无储量。',ports=stream(),
        parameters=[_switch(),_ratio('load_ratio','载量',.75,runtime=True),number('displacement_m3_s','排量',.01,'volume_flow','m³/s','m³/h',1/3600,minimum=1e-8),
            _ratio('volumetric_efficiency','容积效率',.8,minimum=.01),_ratio('isentropic_efficiency','等熵效率',.72,minimum=.01),_ratio('motor_efficiency','电机效率',.92,minimum=.01)],
        variables=values+[_var('shaft_power_w','轴功','power','W'),_var('electric_power_w','电功','power','W'),
            _var('state.electric_energy_j','累计电量','energy','J',source='state')])
    return [valve,evaporator,compressor]
