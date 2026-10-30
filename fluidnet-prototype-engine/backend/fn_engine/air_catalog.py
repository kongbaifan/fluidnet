"""风系统设备合同；与通用目录共用参数/单位生成器。"""
from .models import Direction, ModuleDefinition, ParameterSpec, PortSpec


def air_catalog():
    from .catalog import channel, number, ports

    def temperature(key,label,value,minimum=253.15,maximum=333.15,runtime=False):
        return number(key,label,value,'temperature','K','°C',minimum=minimum,maximum=maximum,runtime=runtime,offset=-273.15)

    def humidity(key,label,value,runtime=False):
        return number(key,label,value,'humidity_ratio','kg/kg_da','g/kg_da',.001,0.,.05,runtime)

    mixing = ModuleDefinition(id='air_mixing_box',name='新回风混合箱',category='风侧设备',solver_model='air_mixing_box',
        description='三端口同压理想混合；按干空气流量混合焓和含湿量，新风比例由上游风管阻力决定。',
        ports=[PortSpec(id=k,label=label,direction=direction) for k,label,direction in (
            ('fresh_in','新风入口',Direction.in_),('return_in','回风入口',Direction.in_),('supply_out','混合送风',Direction.out))])
    air_filter = ModuleDefinition(id='air_filter',name='空气过滤器',category='风侧设备',solver_model='air_filter',
        description='按实际体积流量平方计算压降；污堵比例可在运行中改变。允许反向，热湿状态透传。',
        ports=ports('in0','out0'),channels=[channel('ch0','air_filter')],parameters=[
            number('rated_volume_flow_m3_s','额定实际风量',1.,'volume_flow','m3/s','m3/h',1/3600,1e-8,100.),
            number('clean_pressure_drop_pa','干净过滤器额定压降',100.,'pressure','Pa',minimum=1e-8,maximum=10000),
            number('loading_ratio','污堵比例',0.,'ratio','1','%',.01,0.,1.,True),
            number('loaded_drop_multiplier','完全污堵压降倍数',2.,'ratio','1',minimum=1.,maximum=20.)])
    room = ModuleDefinition(id='air_room',name='房间热湿节点',category='风侧设备',solver_model='air_room',state_model='moist_air_room',
        description='完全混合、固定有效干空气存量房间；围护、散湿与平衡渗透独立记账。',
        ports=[PortSpec(id='supply_in',label='送风入口',direction=Direction.in_),
               PortSpec(id='return_out',label='回风出口',direction=Direction.out)],parameters=[
            number('volume_m3','初态有效体积',100.,'volume','m3',minimum=1e-8,maximum=1e6),
            temperature('initial_temperature_k','初始温度',299.15,273.15,323.15),
            humidity('initial_humidity_ratio_kg_kg','初始含湿量',.010),
            number('initial_pressure_pa','初态存量参考压力',101325.,'pressure','Pa','kPa',1000.,60000.,120000.),
            number('additional_heat_capacity_j_k','围护家具等效热容',1e6,'heat_capacity','J/K','kJ/K',1000.,0.,1e12),
            number('envelope_ua_w_k','围护传热系数 UA',100.,'conductance','W/K',minimum=0.),
            temperature('outdoor_temperature_k','室外温度',308.15,runtime=True),
            humidity('outdoor_humidity_ratio_kg_kg','室外含湿量',.014,True),
            number('infiltration_dry_air_kg_s','平衡渗透干空气流量',0.,'dry_air_mass_flow','kg_da/s',minimum=0.,maximum=100.,runtime=True),
            number('sensible_load_w','室内显热负荷',1000.,'power','W','kW',1000.,-1e7,1e7,True),
            number('moisture_load_kg_s','人员货物散湿量',.0001,'mass_flow','kg/s',minimum=0.,maximum=10.,runtime=True),
            temperature('moisture_source_temperature_k','散湿蒸汽参考温度',307.15,273.15,333.15,True)])
    tower = ModuleDefinition(id='cooling_tower_moist',name='湿空气冷却塔',category='热力设备',solver_model='cooling_tower_moist',
        description='接触效能教学模型：循环水与规定外界空气交换热湿，核算蒸发、飘水、排污和补水；无空气端口。',
        ports=ports('in0','out0'),channels=[channel('ch0','resistance')],parameters=[
            temperature('air_temperature_k','进风干球温度',303.15,273.15,323.15,True),
            number('air_pressure_pa','空气绝对压力',101325.,'pressure','Pa','kPa',1000.,60000.,120000.),
            humidity('air_humidity_ratio_kg_kg','进风含湿量',.014,True),
            number('air_volume_flow_m3_s','进风实际体积流量',3.,'volume_flow','m3/s','m3/h',1/3600,0.,1000.,True),
            number('contact_effectiveness','接触效能',.7,'ratio','1','%',.01,0.,1.,True),
            number('cycles_of_concentration','目标浓缩倍数',3.,'ratio','1',minimum=1.000001,maximum=100.,runtime=True),
            number('drift_fraction','循环水飘水比例',.0002,'ratio','1','%',.01,0.,.01),
            temperature('makeup_temperature_k','补水温度',293.15,273.15,323.15,True),
            number('loss_coefficient','水侧阻力系数',2.,'ratio','1',minimum=0.),
            number('diameter_m','水侧等效直径',.05,'length','m','mm',.001,1e-8,2.)])
    return [mixing,air_filter,room,tower,water_coil(),water_chiller()]


def _derived(id, label, quantity, unit, display=None, scale=1., offset=0., source='derived'):
    from .models import UnitSpec, VariableSpec
    return VariableSpec(id=id, label=label, source=source, quantity=quantity,
                        unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=display or unit,
                                      display_scale=scale, display_offset=offset))


def water_coil():
    """风侧 ch0（in0→out0）与冷/热水侧 ch1（in1→out1）；两侧分属湿空气回路和液体回路。"""
    from .catalog import channel, number
    kw = lambda id, label, source='derived': _derived(id, label, 'power', 'W', 'kW', 1000., source=source)
    return ModuleDefinition(id='water_coil', name='冷/热水盘管', category='风侧设备', solver_model='water_coil',
        description='逆流 ε–NTU：干段在进风端、湿段在进水端，交界处表面温度等于进风露点；湿段按 Braun 焓效能法。'
                    '水侧得热 = 空气焓降 − 凝水携出焓。需开启湿空气模式，水侧接液体回路。',
        ports=[PortSpec(id='in0',label='进风',direction=Direction.in_),PortSpec(id='out0',label='出风',direction=Direction.out),
               PortSpec(id='in1',label='进水',direction=Direction.in_),PortSpec(id='out1',label='出水',direction=Direction.out)],
        channels=[channel('ch0','resistance'),channel('ch1','resistance_secondary','in1','out1')],
        parameters=[
            number('air_side_ua_w_k','空气侧换热能力 UA',4000.,'conductance','W/K',minimum=0.),
            number('water_side_ua_w_k','水侧换热能力 UA',8000.,'conductance','W/K',minimum=0.),
            number('loss_coefficient','风侧阻力系数 K',2.,'ratio','1',minimum=0.),
            number('diameter_m','风侧水力等效内径',.4,'length','m','mm',.001,.001),
            number('secondary_loss_coefficient','水侧阻力系数 K',5.,'ratio','1',minimum=0.),
            number('secondary_diameter_m','水侧水力等效内径',.05,'length','m','mm',.001,.001)],
        variables=[kw('total_heat_w','空气侧总冷量'),kw('sensible_heat_w','显热冷量'),kw('latent_heat_w','潜热冷量'),
                   _derived('condensate_kg_s','凝水量','mass_flow','kg/s'),_derived('shr','显热比 SHR','ratio','1'),
                   kw('water_heat_w','水侧得热'),_derived('wet_fraction','湿表面比例','ratio','1','%',.01),
                   _derived('surface_temperature_k','湿段等效表面温度','temperature','K','°C',offset=-273.15),
                   _derived('state.condensate_kg','累计凝水量','mass','kg',source='state'),
                   _derived('state.cooling_energy_j','累计水侧冷量','energy','J','kWh',3600000.,source='state')])


def water_chiller():
    """蒸发器 ch0（冷冻水 in0→out0）与冷凝器 ch1（冷却水 in1→out1），单级循环复用 refrigeration/cycle.py。"""
    from .catalog import _celsius, _ratio, channel, number
    kw = lambda id, label, source='derived': _derived(id, label, 'power', 'W', 'kW', 1000., source=source)
    celsius = lambda id, label: _derived(id, label, 'temperature', 'K', '°C', offset=-273.15)
    return ModuleDefinition(id='water_chiller', name='水冷冷水机组', category='热力设备', solver_model='water_chiller',
        description='单级蒸气压缩循环，蒸发器与冷凝器各接一条水通路；把冷冻水出水压到设定值，满载不足时出水温度上漂。'
                    '负荷比在 0–1 连续变化，不模拟最小负荷启停；Q冷凝 = Q制冷 + 压缩轴功。',
        ports=[PortSpec(id='in0',label='冷冻水进水',direction=Direction.in_),PortSpec(id='out0',label='冷冻水出水',direction=Direction.out),
               PortSpec(id='in1',label='冷却水进水',direction=Direction.in_),PortSpec(id='out1',label='冷却水出水',direction=Direction.out)],
        channels=[channel('ch0','resistance'),channel('ch1','resistance_secondary','in1','out1')],
        parameters=[
            number('running','启停（1 运行 / 0 停机）',1.,'ratio','1',minimum=0.,maximum=1.,runtime=True),
            _celsius('chilled_water_setpoint_k','冷冻水出水设定',280.15,runtime=True),
            ParameterSpec(id='refrigerant',label='制冷剂（CoolProp 名称）',value_type='text',default='HEOS::R134a'),
            number('rated_cooling_power_w','额定制冷量',35000.,'power','W','kW',1000.,minimum=1.),
            _celsius('rated_evaporating_temperature_k','额定蒸发温度',277.15),
            _celsius('rated_condensing_temperature_k','额定冷凝温度',313.15),
            number('superheat_k','吸气过热度',5.,'temperature_difference','K',minimum=.1),
            number('subcooling_k','冷凝器出口过冷度',3.,'temperature_difference','K',minimum=.1),
            _ratio('isentropic_efficiency','等熵效率',.7,minimum=.01),
            _ratio('volumetric_efficiency','容积效率',.85,minimum=.01),
            _ratio('motor_efficiency','电机效率',.92,minimum=.01),
            number('evaporator_ua_w_k','蒸发器 UA',8000.,'conductance','W/K',minimum=0.),
            number('condenser_ua_w_k','冷凝器 UA',6000.,'conductance','W/K',minimum=0.),
            number('loss_coefficient','冷冻水侧阻力系数 K',5.,'ratio','1',minimum=0.),
            number('diameter_m','冷冻水侧等效内径',.05,'length','m','mm',.001,.001),
            number('secondary_loss_coefficient','冷却水侧阻力系数 K',5.,'ratio','1',minimum=0.),
            number('secondary_diameter_m','冷却水侧等效内径',.05,'length','m','mm',.001,.001),
            _celsius('min_evaporating_temperature_k','运行范围：最低蒸发温度',268.15),
            _celsius('max_evaporating_temperature_k','运行范围：最高蒸发温度',293.15),
            _celsius('min_condensing_temperature_k','运行范围：最低冷凝温度',293.15),
            _celsius('max_condensing_temperature_k','运行范围：最高冷凝温度',333.15),
            _celsius('max_discharge_temperature_k','运行范围：最高排气温度',383.15),
            number('max_pressure_ratio','运行范围：最大压比',10.,'ratio','1',minimum=1.)],
        variables=[kw('cooling_power_w','制冷量'),kw('condenser_heat_w','冷凝排热'),kw('shaft_power_w','压缩轴功率'),
                   kw('electric_power_w','压缩机电功率'),_derived('cop','COP（制冷量/电功率）','ratio','1'),
                   _derived('load_ratio','负荷比','ratio','1','%',.01),
                   _derived('capacity_limited','满载仍未达设定','ratio','1'),
                   celsius('evaporating_temperature_k','蒸发温度'),celsius('condensing_temperature_k','冷凝温度'),
                   celsius('discharge_temperature_k','排气温度'),_derived('pressure_ratio','压比','ratio','1'),
                   _derived('refrigerant_mass_flow_kg_s','制冷剂质量流量','mass_flow','kg/s'),
                   _derived('state.cooling_energy_j','累计制冷量','energy','J','kWh',3600000.,source='state'),
                   _derived('state.electric_energy_j','累计耗电量','energy','J','kWh',3600000.,source='state')])


def upgrade_air_catalog(definitions):
    """新目录版本的默认值与运行可写性；已保存定义保留原默认值。"""
    by_id = {d.id:d for d in definitions}
    for identifier in ('cooling_coil','humidifier'):
        definition = by_id[identifier]
        definition.version = 2
        for p in definition.parameters:
            if p.id in ('coil_surface_temperature_k','bypass_factor','moisture_addition_kg_kg'):
                p.runtime = True
            if p.id == 'coil_surface_temperature_k':
                p.minimum,p.maximum = 273.15,323.15
            if p.id == 'loss_coefficient':
                p.default = 2. if identifier == 'cooling_coil' else 1.
    by_id['cooling_coil'].description = '规定外部冷源机器露点与旁通系数；湿区按焓/含湿量混合，输出冷量、凝水和显潜热；不含真实冷水侧。'
    by_id['humidifier'].parameters.append(ParameterSpec(id='saturation_action',label='超饱和处理（limit / error）',
                                                        value_type='text',default='limit'))
    for p in by_id['source'].parameters:
        if p.id in ('temperature_k','pressure_pa','humidity_ratio_kg_kg'):
            p.runtime = True
