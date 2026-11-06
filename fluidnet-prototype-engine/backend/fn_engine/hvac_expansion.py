"""New HVAC equipment IDs; old seed package versions remain unchanged."""
from pathlib import Path

from .hvac_basic import base, number, output, compose, junction_module, resistance_module
from .models import ModuleDefinition

ROOT=Path(__file__).resolve().parents[2]


def air_branch_box():
    leg=resistance_module()
    data=leg.model_dump(mode='json')
    data.update(id='air_branch_leg',name='风侧分支阻力通路',description='固定K及通路面积；允许正反流，不含流量比分配经验关联。')
    data['source']['runtime']=data['source']['runtime'].replace("ctx.port('in0').density_kg_m3", "ctx.port('in0' if ctx.port('in0').pressure_pa>=ctx.port('out0').pressure_pa else 'out0').density_kg_m3")
    data['applicability'].update(phases=['gas'],fluids=['Air','HEOS::Air'])
    for p in data['parameters']:
        if p['id']=='diameter_m':p['default']=.4
        if p['id']=='loss_coefficient':p['default']=1.
    leg=ModuleDefinition.model_validate(data)
    node=junction_module(3)
    instances=[{'id':'Node','module_id':node.id,'name':'中心混合节点'},
        *[{'id':key,'module_id':leg.id,'name':label,'parameters':{'loss_coefficient':k}}
          for key,label,k in [('Common','公共腿',.2),('Branch1','支路一',.5),('Branch2','支路二',2.)]]]
    connections=[{'id':'common','source':{'instance_id':'Common','port_id':'out0'},'target':{'instance_id':'Node','port_id':'p0'}},
        *[{'id':f'branch{i}','source':{'instance_id':'Node','port_id':f'p{i}'},'target':{'instance_id':f'Branch{i}','port_id':'in0'}} for i in (1,2)]]
    return compose('air_branch_box','三端口风侧分支箱',[leg,node],instances,connections,
        {'Common_in0':('common','公共风口'),'Branch1_out0':('branch1','支路一风口'),'Branch2_out0':('branch2','支路二风口')},
        '三条独立阻力通路＋中心理想混合节点；普通气体与湿空气透传。K为用户给定定值，按各腿内径速度为参考；无储量，不含流量比相关局部K。')


def fan_performance():
    m=base('fan_performance','风机（停机阻力与效率曲线）',(ROOT/'modules/fan_performance/module.py').read_text(encoding='utf-8'),[
        number('running','运行请求',1.,maximum=1.,runtime=True),number('speed_ratio','转速比',1.,maximum=2.,runtime=True),
        {'id':'pressure_curve','label':'额定实际风量m³/h—压升Pa','value_type':'curve','default':[[0.,300.],[2000.,250.],[4000.,120.],[5000.,0.]]},
        {'id':'efficiency_curve','label':'折算风量Q/n m³/h—风机效率','value_type':'curve','default':[[0.,.4],[2000.,.65],[4000.,.55],[5000.,.35]]},
        number('motor_efficiency','电机效率',.9,minimum=.01,maximum=1.),
        number('diameter_m','停机通路内径',.4,'length','m','mm',.001,minimum=.001),
        number('stopped_loss_coefficient','停机阻力K',2.,minimum=.001)],
        variables=[output(k,label,quantity,unit,display,scale) for k,label,quantity,unit,display,scale in [
            ('pressure_rise_pa','压升','pressure','Pa','Pa',1.),('hydraulic_power_w','流体功率','power','W','kW',1000.),
            ('shaft_power_w','风机轴功率','power','W','kW',1000.),('electric_power_w','电功率','power','W','kW',1000.),
            ('efficiency_ratio','风机效率','ratio','1','%',.01),('is_running','实际运行','ratio','1','1',1.),
            ('state.electric_energy_j','累计电量','energy','J','kWh',3600000.),('state.shaft_energy_j','累计轴功','energy','J','kWh',3600000.)]])
    data=m.model_dump(mode='json')
    data['channels'][0]['solver_model']='pump_curve'
    data['sdk']['capabilities']+=['net.pump','thermal.v1']
    data['description']='气相风机，额定压升及Q/n效率曲线；停机为被动阻力。轴功进入气流，电机损失留环境。运行反流拒绝；曲线为教学输入，非厂家标定。'
    data['applicability']['phases']=['gas']
    data['applicability']['fluids']=['Air','HEOS::Air']
    return ModuleDefinition.model_validate(data)


def plate_exchanger():
    parameters=[number('clean_ua_w_k','清洁UA',2000.,'conductance','W/K','kW/K',1000.),
        number('hot_fouling_resistance_k_w','热侧总污垢热阻',0.,'thermal_resistance','K/W'),
        number('cold_fouling_resistance_k_w','冷侧总污垢热阻',0.,'thermal_resistance','K/W')]
    for side,label in [('hot','热侧'),('cold','冷侧')]:
        parameters += [number(side+'_diameter_m',label+'通路内径',.04,'length','m','mm',.001,minimum=.001),
            number(side+'_loss_coefficient',label+'阻力K',5. if side=='hot' else 12.,minimum=.001)]
    ports=[{'id':side+'_'+end,'label':label+('入口' if end=='in' else '出口'),'direction':end,'circuit':side}
           for side,label in [('hot','热侧'),('cold','冷侧')] for end in ('in','out')]
    channels=[{'id':s,'name':s,'input_port':s+'_in','output_port':s+'_out','relation':'resistance','solver_model':'generic'} for s in ('hot','cold')]
    variables=[output('effective_ua_w_k','污垢后有效UA','conductance','W/K','kW/K',1000.),
        output('transferred_heat_w','冷侧得热','power','W','kW',1000.),output('state.transferred_energy_j','累计冷侧得热','energy','J','kWh',3600000.),
        *[output(s+'_pressure_drop_pa',s+'压差','pressure','Pa','kPa',1000.) for s in ('hot','cold')]]
    data=base('plate_exchanger','板式换热器（双侧阻力与污垢）',(ROOT/'modules/plate_exchanger/module.py').read_text(encoding='utf-8'),parameters,ports,channels,variables).model_dump(mode='json')
    data['sdk']['capabilities']=[c for c in data['sdk']['capabilities'] if c!='air.pass_through.v1']+['thermal.v1','thermal.conservative.v1']
    data['description']='普通单相双回路显热ε–NTU；独立两侧阻力，总污垢热阻K/W串联。反转一侧变并流，零流无热量；无持液热容，不支持湿空气/风水域。'
    return ModuleDefinition.model_validate(data)


def definitions():
    return [air_branch_box(),fan_performance(),plate_exchanger(),air_recovery_sensible()]


def air_recovery_sensible():
    ports=[{'id':s+'_'+e,'label':label+('入口' if e=='in' else '出口'),'direction':e,'circuit':s}
        for s,label in [('exhaust','排风'),('supply','新风')] for e in ('in','out')]
    channels=[{'id':s,'name':s,'input_port':s+'_in','output_port':s+'_out','relation':'resistance','solver_model':'generic'} for s in ('exhaust','supply')]
    parameters=[number('ua_w_k','清洁显热UA',1000.,'conductance','W/K','kW/K',1000.),
        number('bypass_ratio','等效换热旁通比例',0.,maximum=1.,runtime=True)]
    for side,label in [('exhaust','排风'),('supply','新风')]:
        parameters += [number(side+'_diameter_m',label+'等效内径',.4,'length','m','mm',.001,minimum=.001),
            number(side+'_loss_coefficient',label+'阻力K',2.,minimum=.001)]
    variables=[output('recovered_heat_w','新风所得热量','power','W','kW',1000.),
        output('effective_ua_w_k','等效UA','conductance','W/K','kW/K',1000.),
        output('state.recovered_energy_j','累计新风所得热量','energy','J','kWh',3600000.)]
    data=base('air_recovery_sensible','双风道显热回收器',(ROOT/'modules/air_recovery_sensible/module.py').read_text(encoding='utf-8'),parameters,ports,channels,variables).model_dump(mode='json')
    data['sdk']['capabilities']+=['thermal.v1','thermal.conservative.v1']
    data['applicability'].update(phases=['gas'],fluids=['Air','HEOS::Air'])
    data['description']='两条独立风路显热ε–NTU，无漏风、水分交换和储热；各路湿量透传，凝结/结霜不支持，端口温度须不低于0°C。旁通是UA折减，不隐含额外风路。'
    return ModuleDefinition.model_validate(data)
