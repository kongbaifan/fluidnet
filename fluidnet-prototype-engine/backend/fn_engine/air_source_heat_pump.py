"""Air-source heating cycle, dry/sensible external air and one heated liquid circuit."""
import math

from scipy.optimize import brentq

from .refrigeration.cycle import DeviceRangeError, cycle_rates, cycle_point, rated_displacement, check_envelope
from .water_chiller import refrigerant_service


def check_flow_limits(p,flow):
    if p['running']>=.5 and flow<p['water_min_flow_kg_s']:
        raise DeviceRangeError('HEAT_PUMP_LOW_FLOW','热泵水流量低于最小运行值',field='water_min_flow_kg_s')


def evaluate_heat_pump(inlet,flow,p,water_service,pressure,*,check=False,check_min_flow=True):
    if flow < -1e-9:raise DeviceRangeError('HEAT_PUMP_REVERSE_FLOW','供热热泵不支持水侧反流')
    if check and check_min_flow:check_flow_limits(p,flow)
    outputs=dict.fromkeys(('heating_power_w','air_heat_extracted_w','shaft_power_w','compressor_electric_power_w',
        'fan_power_w','electric_power_w','load_ratio','water_equation_residual_w','air_equation_residual_w','air_mass_flow_kg_s'),0.)
    outputs.update(cop=None,evaporating_temperature_k=None,condensing_temperature_k=None,air_outlet_temperature_k=None,capacity_limited=False)
    if p['running']<.5 or flow<=1e-9:return {'outlet_h':inlet.enthalpy_j_kg,'outputs':outputs}
    target=flow*(water_service.state_pt(pressure,p['hot_water_setpoint_k']).enthalpy_j_kg-inlet.enthalpy_j_kg) if flow>1e-9 else 0.
    if target<=1e-3:return {'outlet_h':inlet.enthalpy_j_kg,'outputs':outputs}
    air_flow=p['rated_air_mass_flow_kg_s']*p['fan_ratio'];ca=air_flow*p['air_specific_heat_j_kg_k']
    if ca<=0:raise DeviceRangeError('HEAT_PUMP_NO_AIR','供热需求存在但空气流量为零',field='fan_ratio')
    cw=flow*inlet.specific_heat_j_kg_k
    ga=ca*-math.expm1(-p['air_side_ua_w_k']/ca);gw=cw*-math.expm1(-p['condenser_ua_w_k']/cw)
    if min(ga,gw)<=0:raise DeviceRangeError('HEAT_PUMP_UA','热泵两侧UA必须为正')
    service=refrigerant_service(p);displacement=rated_displacement(service,p);ta=p['air_inlet_temperature_k'];tw=inlet.temperature_k
    def evaporation(tc,load=None):
        def residual(te):
            rates=cycle_rates(service,p,displacement,te,tc,1.)
            fraction=target/rates['rejection_w'] if load is None else load
            return ga*(ta-te)-fraction*rates['cooling_w']
        high=min(ta-1e-4,tc-1.);low=high-5.
        while residual(low)<0 and low>233.15:low=max(233.15,low-5.)
        if residual(low)<0:raise DeviceRangeError('HEAT_PUMP_AIR_INFEASIBLE','空气侧不能提供所需吸热量')
        return brentq(residual,low,high,xtol=1e-9)
    tc=tw+target/gw;te=evaporation(tc)
    load=target/cycle_rates(service,p,displacement,te,tc,1.)['rejection_w']
    limited=load>1.
    if limited:
        load=1.
        def balance(cond):
            evap=evaporation(cond,1.)
            return cycle_rates(service,p,displacement,evap,cond,1.)['rejection_w']-gw*(cond-tw)
        tc=brentq(balance,max(tw,ta)+.01,tc,xtol=1e-9);te=evaporation(tc,1.)
    point=cycle_point(service,p,displacement,te,tc,load)
    if check:
        if te<273.15:raise DeviceRangeError('HEAT_PUMP_FROST_UNSUPPORTED','空气源热泵蒸发温度低于0°C；首版不含结霜和除霜',field='air_inlet_temperature_k')
        if te<p['air_dew_point_k']:raise DeviceRangeError('HEAT_PUMP_CONDENSATION_UNSUPPORTED','蒸发温度低于输入空气露点；首版仅显热干盘管',field='air_dew_point_k')
        check_envelope(p,point)
    heating=point['condenser_heat_w'];extracted=point['cooling_power_w'];fan=p['fan_power_w']*p['fan_ratio']**3
    outputs.update(heating_power_w=heating,air_heat_extracted_w=extracted,shaft_power_w=point['shaft_power_w'],
        compressor_electric_power_w=point['electric_power_w'],fan_power_w=fan,electric_power_w=point['electric_power_w']+fan,
        cop=heating/(point['electric_power_w']+fan),load_ratio=load,capacity_limited=limited,
        evaporating_temperature_k=te,condensing_temperature_k=tc,air_outlet_temperature_k=ta-extracted/ca,air_mass_flow_kg_s=air_flow,
        water_equation_residual_w=gw*(tc-tw)-heating,air_equation_residual_w=ga*(ta-te)-extracted)
    return {'outlet_h':inlet.enthalpy_j_kg+heating/flow,'outputs':outputs}


def definition():
    from .air_catalog import water_chiller, _derived
    from .catalog import number, _celsius, _ratio, channel
    from .models import ModuleDefinition
    reference=water_chiller().model_dump(mode='json')
    remove={'evaporator_min_flow_kg_s','condenser_min_flow_kg_s','minimum_load_ratio','chilled_water_setpoint_k',
            'evaporator_ua_w_k','secondary_loss_coefficient','secondary_diameter_m'}
    reference.update(id='air_source_heat_pump',name='空气源供热热泵（干盘管）',solver_model='air_source_heat_pump',
        description='单水回路供热，室外空气是显热边界；按压缩循环和两侧ε–NTU联立求解。连续调节，低于0°C蒸发或空气露点时拒绝，不包含结霜除霜/潜热/厂家标定。',
        ports=[port for port in reference['ports'] if port['id'] in ('in0','out0')],channels=[channel('ch0','resistance').model_dump(mode='json')],
        parameters=[v for v in reference['parameters'] if v['id'] not in remove],variables=[])
    defaults={'rated_cooling_power_w':15000.,'rated_evaporating_temperature_k':278.15,'rated_condensing_temperature_k':323.15,
              'min_evaporating_temperature_k':273.15,'max_evaporating_temperature_k':303.15,'max_condensing_temperature_k':333.15}
    for spec in reference['parameters']:
        if spec['id'] in defaults:spec['default']=defaults[spec['id']]
    extra=[_celsius('hot_water_setpoint_k','供热出水设定',313.15,True),
        number('water_min_flow_kg_s','最小水流量',0.,'mass_flow','kg/s',minimum=0.),
        number('air_side_ua_w_k','空气侧UA',6000.,'conductance','W/K',minimum=.001),
        number('rated_air_mass_flow_kg_s','额定空气质量流量',8.,'mass_flow','kg/s',minimum=.001),
        number('air_specific_heat_j_kg_k','空气恒定比热',1006.,'specific_heat','J/(kg·K)',minimum=1.),
        _celsius('air_inlet_temperature_k','环境进风干球温度',293.15,True),_celsius('air_dew_point_k','环境空气露点（干盘管适用检查）',273.15,True),
        _ratio('fan_ratio','风机转速比',1.,True),number('fan_power_w','额定风机功率',1000.,'power','W','kW',1000.,minimum=0.)]
    reference['parameters'] += [s.model_dump(mode='json') for s in extra]
    for key,label in [('heating_power_w','供热量'),('air_heat_extracted_w','空气吸热'),('shaft_power_w','轴功'),('compressor_electric_power_w','压缩机电耗'),
        ('fan_power_w','风机电耗'),('electric_power_w','总电耗'),('water_equation_residual_w','水侧能量残差'),('air_equation_residual_w','空气能量残差')]:
        reference['variables'].append(_derived(key,label,'power','W','kW',1000.).model_dump(mode='json'))
    for key,label in [('evaporating_temperature_k','蒸发温度'),('condensing_temperature_k','冷凝温度'),('air_outlet_temperature_k','出风温度')]:
        reference['variables'].append(_derived(key,label,'temperature','K','°C',offset=-273.15).model_dump(mode='json'))
    for key,label in [('cop','供热COP含风机'),('load_ratio','负荷比'),('capacity_limited','容量不足')]:
        reference['variables'].append(_derived(key,label,'ratio','1').model_dump(mode='json'))
    reference['variables'].append(_derived('air_mass_flow_kg_s','空气流量','mass_flow','kg/s').model_dump(mode='json'))
    for key,label in [('heating_energy_j','累计供热'),('electric_energy_j','累计电量')]:
        reference['variables'].append(_derived('state.'+key,label,'energy','J','kWh',3600000.,source='state').model_dump(mode='json'))
    return ModuleDefinition.model_validate(reference)
