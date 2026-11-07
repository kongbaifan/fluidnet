"""Basic HVAC equipment and frozen compositions; all quantities use engine SI units."""
from pathlib import Path

from .catalog import catalog_map
from .composites import module_from_group
from .model_types.module import ModuleDefinition
from .model_types.domain import Project

ROOT = Path(__file__).resolve().parents[2]
CATEGORY = '暖通基础设备'


def number(key, label, default, quantity='ratio', unit='1', display=None, scale=1., minimum=0., maximum=None, runtime=False):
    return {'id':key,'label':label,'default':default,'minimum':minimum,'maximum':maximum,'runtime':runtime,
            'unit':{'quantity':quantity,'canonical_unit':unit,'display_unit':display or unit,'display_scale':scale}}


def output(key, label, quantity='ratio', unit='1', display=None, scale=1.):
    return {'id':key,'label':label,'source':'state' if key.startswith('state.') else 'derived','quantity':quantity,
            'unit':{'quantity':quantity,'canonical_unit':unit,'display_unit':display or unit,'display_scale':scale}}


def base(identifier, name, source, parameters, ports=None, channels=None, variables=None):
    return ModuleDefinition.model_validate({'schema_version':3,'id':identifier,'name':name,'category':CATEGORY,
        'version':1,'runtime':'python','entrypoint':'module:Module','solver_model':'generic','source_format':'python-v1',
        'description':name+'：单相基础设备，型号参数须按工程资料填写。',
        'ports':ports or [{'id':'in0','label':'入口','direction':'in'},{'id':'out0','label':'出口','direction':'out'}],
        'channels':channels if channels is not None else [{'id':'main','name':'主通路','input_port':'in0','output_port':'out0','relation':'resistance','solver_model':'generic'}],
        'parameters':parameters,'variables':variables or [],'source':{'runtime':source},
        'sdk':{'api_version':'0.6.0','capabilities':['net.resistance','net.valve','state.transactions.v1','observe.v1','evaluate.pure.v1','hydraulic.signed_start.v1','air.pass_through.v1']},
        'pure_evaluate':True,'applicability':{'phases':['liquid','gas'],'assumptions':['单相、无独立物理储量；设备默认参数为演示参数。']}})


VALVE_SOURCE = '''import math
def fraction(curve, position):
    if len(curve)<2 or curve[0][0]!=0 or curve[-1][0]!=1:
        raise ValueError('特性曲线必须覆盖 0 到 1 的位置')
    previous=-1.
    last=-1.
    for x,y in curve:
        if not all(math.isfinite(v) for v in (x,y)) or not previous<x<=1 or not last<=y<=1 or y<0:
            raise ValueError('位置必须递增，流通能力必须非递减且在 0 到 1 之间')
        previous,last=x,y
    for (x0,y0),(x1,y1) in zip(curve,curve[1:]):
        if position<=x1:
            return y0+(y1-y0)*(position-x0)/(x1-x0)
    return curve[-1][1]
class Module:
    def initialize(self,ctx):
        fraction(ctx.parameters['characteristic_curve'],0.)
        mode=ctx.parameters['operation_mode']
        if mode not in ('modulating','on_off'):
            raise ValueError('操作方式只能为 modulating 或 on_off')
        ctx.state.setdefault('throughput_kg',0.)
    def evaluate(self,ctx):
        position=ctx.parameters['opening_ratio']
        if ctx.parameters['operation_mode']=='on_off': position=1. if position>=.5 else 0.
        effective=0. if position==0 else fraction(ctx.parameters['characteristic_curve'],position)
        ctx.net.valve(channel='main',kv=ctx.parameters['kv_m3_h'],opening=effective,density_kg_m3=ctx.port('in0').density_kg_m3)
        ctx.var('effective_opening',effective)
    def observe(self,ctx):
        ctx.var('actual_drop_pa',ctx.channel('main').pressure_drop_pa)
        ctx.var('actual_volume_flow_m3_h',ctx.channel('main').mass_flow_kg_s/ctx.port('in0').density_kg_m3*3600.)
    def commit_step(self,ctx,dt_s): ctx.state['throughput_kg']+=abs(ctx.channel('main').mass_flow_kg_s)*dt_s
    def finalize(self,ctx): pass
'''

RESISTANCE_SOURCE = '''class Module:
    def initialize(self,ctx): ctx.state.setdefault('throughput_kg',0.)
    def evaluate(self,ctx):
        ctx.net.resistance(channel='main',diameter_m=ctx.parameters['diameter_m'],loss_coefficient=ctx.parameters['loss_coefficient'],density_kg_m3=ctx.port('in0').density_kg_m3)
    def observe(self,ctx): ctx.var('actual_drop_pa',ctx.channel('main').pressure_drop_pa)
    def commit_step(self,ctx,dt_s): ctx.state['throughput_kg']+=abs(ctx.channel('main').mass_flow_kg_s)*dt_s
    def finalize(self,ctx): pass
'''

FILTER_SOURCE = '''import math
class Module:
    def initialize(self,ctx): ctx.state.setdefault('throughput_kg',0.)
    def evaluate(self,ctx):
        p=ctx.parameters
        density=ctx.port('in0').density_kg_m3
        area=math.pi*p['diameter_m']**2/4.
        speed=p['rated_flow_m3_h']/3600./area
        coefficient=2*p['clean_pressure_drop_pa']*(1+p['loading_ratio']*(p['loaded_multiplier']-1))/(density*speed**2)
        ctx.net.resistance(channel='main',diameter_m=p['diameter_m'],loss_coefficient=coefficient,density_kg_m3=density)
        ctx.var('loss_coefficient',coefficient)
    def observe(self,ctx): ctx.var('actual_drop_pa',ctx.channel('main').pressure_drop_pa)
    def commit_step(self,ctx,dt_s): ctx.state['throughput_kg']+=abs(ctx.channel('main').mass_flow_kg_s)*dt_s
    def finalize(self,ctx): pass
'''

THREE_WAY_SOURCE = '''class Module:
    def initialize(self,ctx): ctx.state.setdefault('throughput_kg',0.)
    def evaluate(self,ctx):
        p=ctx.parameters
        for channel,port,opening in [('a','a_in',p['opening_ratio']),('b','b_in',1-p['opening_ratio'])]:
            ctx.net.valve(channel=channel,kv=p['kv_m3_h'],opening=opening,density_kg_m3=ctx.port(port).density_kg_m3)
    def observe(self,ctx):
        ctx.var('a_flow_kg_s',ctx.channel('a').mass_flow_kg_s)
        ctx.var('b_flow_kg_s',ctx.channel('b').mass_flow_kg_s)
    def commit_step(self,ctx,dt_s): ctx.state['throughput_kg']+=(abs(ctx.channel('a').mass_flow_kg_s)+abs(ctx.channel('b').mass_flow_kg_s))*dt_s
    def finalize(self,ctx): pass
'''

PUMP_SOURCE = '''import math
def validate(curve):
    if len(curve)<2 or curve[0][0]!=0 or curve[-1][1]!=0:
        raise ValueError('泵曲线须从零流量开始并以零扬程结束')
    for a,b in zip(curve,curve[1:]):
        if not all(math.isfinite(v) and v>=0 for v in (*a,*b)) or b[0]<=a[0] or b[1]>=a[1]:
            raise ValueError('泵曲线流量须递增，扬程须递减')
def inverse(curve,head):
    for (q0,h0),(q1,h1) in zip(curve,curve[1:]):
        if head>=h1: return max(0.,q0+(q1-q0)*(h0-head)/(h0-h1))
    return curve[-1][0]
class Module:
    def initialize(self,ctx):
        validate(ctx.parameters['head_curve'])
        ctx.state.setdefault('electric_energy_j',0.)
        ctx.state.setdefault('throughput_kg',0.)
    def evaluate(self,ctx):
        p=ctx.parameters
        density=ctx.port('in0').density_kg_m3
        active=p['running']>=.5
        if active:
            rise=max(0.,ctx.port('out0').pressure_pa-ctx.port('in0').pressure_pa)
            flow=inverse(p['head_curve'],rise/(density*9.80665*p['speed_ratio']**2))*p['speed_ratio']/3600.
            loss=rise*flow*(1/p['efficiency_ratio']-1)
            ctx.net.pump(channel='main',head_curve=p['head_curve'],speed_ratio=p['speed_ratio'],density_kg_m3=density,heat_w=loss)
        else:
            ctx.net.resistance(channel='main',diameter_m=p['diameter_m'],loss_coefficient=p['stopped_loss_coefficient'],density_kg_m3=density)
        ctx.var('is_running',int(active))
    def observe(self,ctx):
        c=ctx.channel('main'); p=ctx.parameters
        hydraulic=max(0.,-c.pressure_drop_pa*c.mass_flow_kg_s/ctx.port('in0').density_kg_m3) if p['running']>=.5 else 0.
        shaft=hydraulic/p['efficiency_ratio']
        ctx.var('pump_shaft_power_w',shaft)
        ctx.var('electric_power_w',shaft/p['motor_efficiency'])
    def commit_step(self,ctx,dt_s):
        c=ctx.channel('main'); p=ctx.parameters
        power=max(0.,-c.pressure_drop_pa*c.mass_flow_kg_s/ctx.port('in0').density_kg_m3)/(p['efficiency_ratio']*p['motor_efficiency']) if p['running']>=.5 else 0.
        ctx.state['electric_energy_j']+=power*dt_s
        ctx.state['throughput_kg']+=abs(c.mass_flow_kg_s)*dt_s
    def finalize(self,ctx): pass
'''

CHECK_SOURCE = '''import math
class Module:
    def initialize(self,ctx):
        p=ctx.parameters
        if p['closing_pressure_pa']>p['opening_pressure_pa']:
            raise ValueError('关闭压差不能大于开启压差')
        ctx.state.setdefault('is_open',False)
        ctx.state.setdefault('throughput_kg',0.)
    def opening(self,ctx):
        p=ctx.parameters
        delta=ctx.port('in0').pressure_pa-ctx.port('out0').pressure_pa
        threshold=p['closing_pressure_pa'] if ctx.state['is_open'] else p['opening_pressure_pa']
        return math.sqrt(1-threshold/delta) if delta>threshold and delta>0 else 0.
    def evaluate(self,ctx):
        ctx.net.valve(channel='main',kv=ctx.parameters['kv_m3_h'],opening=self.opening(ctx),density_kg_m3=ctx.port('in0').density_kg_m3)
        ctx.var('flowing',int(self.opening(ctx)>0))
    def observe(self,ctx):
        ctx.var('flowing',int(self.opening(ctx)>0 and ctx.channel('main').mass_flow_kg_s>1e-8))
    def commit_step(self,ctx,dt_s):
        ctx.state['is_open']=self.opening(ctx)>0
        ctx.state['throughput_kg']+=abs(ctx.channel('main').mass_flow_kg_s)*dt_s
    def finalize(self,ctx): pass
'''


def valve_module(identifier='water_balancing_valve', name='手动平衡阀', on_off=False):
    parameters=[number('opening_ratio','预设／开度',1.,display='%',scale=.01,maximum=1.,runtime=True),
        number('kv_m3_h','全开 Kv',16.,'flow_coefficient','m³/h',minimum=.001),
        {'id':'characteristic_curve','label':'位置—相对流通能力曲线','value_type':'curve','default':[[0,0],[.25,.15],[.5,.4],[.75,.7],[1,1]]},
        {'id':'operation_mode','label':'操作方式（modulating／on_off）','value_type':'text','default':'on_off' if on_off else 'modulating'}]
    if on_off:
        parameters.append({'id':'valve_type','label':'阀型／型号备注','value_type':'text','default':'蝶阀'})
    return base(identifier,name,VALVE_SOURCE,parameters,variables=[output('effective_opening','有效流通比例'),
        output('actual_drop_pa','实测压差','pressure','Pa','kPa',1000.),
        output('actual_volume_flow_m3_h','实际体积流量','volume_flow','m³/h'),output('state.throughput_kg','累计通过质量','mass','kg')])


def resistance_module():
    return base('hvac_branch_resistance','管路局部阻力',RESISTANCE_SOURCE,
        [number('diameter_m','通路内径',.05,'length','m','mm',.001,minimum=.001),
         number('loss_coefficient','基准阻力系数 K',.2,runtime=True)],
        variables=[output('actual_drop_pa','通路压差','pressure','Pa','kPa',1000.),output('state.throughput_kg','累计通过质量','mass','kg')])


def filter_module():
    return base('water_strainer','Y 型过滤器／除污器',FILTER_SOURCE,
        [number('diameter_m','通路内径',.05,'length','m','mm',.001,minimum=.001),
         number('rated_flow_m3_h','额定流量',10.,'volume_flow','m³/h',minimum=.001),
         number('clean_pressure_drop_pa','干净时额定压降',5000.,'pressure','Pa','kPa',1000.,minimum=.001),
         number('loading_ratio','污堵比例',0.,display='%',scale=.01,maximum=1.,runtime=True),
         number('loaded_multiplier','完全污堵压降倍数',3.,minimum=1.)],
        variables=[output('loss_coefficient','等效阻力 K'),output('actual_drop_pa','实测压差','pressure','Pa','kPa',1000.),
                   output('state.throughput_kg','累计通过质量','mass','kg')])


def junction_module(count):
    reference=catalog_map()['junction'].model_dump(mode='json')
    reference.update(id='hvac_junction_'+str(count),name='理想汇合节点',variables=[],ports=[
        {'id':'p'+str(i),'label':'连接 '+str(i),'direction':'in' if i==0 else 'out'} for i in range(count)])
    return ModuleDefinition.model_validate(reference)


def compose(identifier,name,definitions,instances,connections,port_names,description=None):
    project=Project(id='hvac-composition',name=name,modules=definitions,instances=instances,connections=connections)
    module=module_from_group(project,[i.id for i in project.instances],identifier,name)
    data=module.model_dump(mode='json')
    rename={port['id']:port_names[port['id']][0] for port in data['ports']}
    data['category']=CATEGORY
    data['description']=(description or name+'：内部展开为固定版本部件，按节点质量与焓守恒求解。')
    for port in data['ports']:
        old=port['id']; port['id'],port['label']=port_names[old]
    data['composite']['external_ports']={rename[key]:value for key,value in data['composite']['external_ports'].items()}
    data['channels']=[]
    data['source']={'runtime':data['source']['runtime']}
    expose_static_parameters(data,project,definitions)
    return ModuleDefinition.model_validate(data)


def expose_static_parameters(data,project,definitions):
    """Composition authoring normally exposes runtime controls only. Equipment also
    needs its static geometry, curves, Kv and efficiency editable from Studio."""
    for instance in project.instances:
        definition = next(m for m in definitions if m.id == instance.module_id)
        for spec in definition.parameters:
            public = instance.id + '_' + spec.id
            if not spec.writable or any(p['id'] == public for p in data['parameters']):
                continue
            parameter = spec.model_dump(mode='json')
            parameter.update(id=public, label=instance.name + ' · ' + spec.label,
                             default=instance.parameters.get(spec.id, spec.default))
            data['parameters'].append(parameter)
            data['composite']['parameter_maps'][public] = [{'instance_id':instance.id, 'parameter_id':spec.id}]


def air_terminal(identifier,name,mixing,defaults,ports,description):
    """空调箱／新风机组／风机盘管：固定版本部件组合，风侧与水侧各自成通路。"""
    from .packages import load_module_package
    catalog=catalog_map()
    fan=load_module_package(ROOT/'modules'/'fan')
    definitions=[catalog['air_filter'],catalog['water_coil'],fan]
    instances=[{'id':'Filter','module_id':'air_filter','name':'过滤器','parameters':defaults.get('Filter',{})},
               {'id':'Coil','module_id':'water_coil','name':'盘管','parameters':defaults.get('Coil',{})},
               {'id':'Fan','module_id':'fan','name':'风机','parameters':defaults.get('Fan',{})}]
    connections=[{'id':'filter-coil','source':{'instance_id':'Filter','port_id':'out0'},'target':{'instance_id':'Coil','port_id':'in0'}},
                 {'id':'coil-fan','source':{'instance_id':'Coil','port_id':'out0'},'target':{'instance_id':'Fan','port_id':'in0'}}]
    if mixing:
        # 新风与回风先混合，再依次经过滤器、水盘管和风机。
        definitions.insert(0,catalog['air_mixing_box'])
        instances.insert(0,{'id':'Mix','module_id':'air_mixing_box','name':'混风箱'})
        connections.insert(0,{'id':'mix-filter','source':{'instance_id':'Mix','port_id':'supply_out'},
                              'target':{'instance_id':'Filter','port_id':'in0'}})
    return compose(identifier,name,definitions,instances,connections,ports,description)


def ahu_module():
    return air_terminal('ahu_standard','空调箱（混风＋过滤＋盘管＋风机）',True,
        {'Filter':{'rated_volume_flow_m3_s':1.2,'clean_pressure_drop_pa':120.},
         'Coil':{'air_side_ua_w_k':2000.,'water_side_ua_w_k':4000.},
         'Fan':{'speed_ratio':1.,'nominal_flow_m3_h':4000.,
                'pressure_curve':[[0.,450.],[2000.,360.],[4000.,180.],[5000.,0.]]}},
        {'Mix_fresh_in':('fresh_in','新风进口'),'Mix_return_in':('return_in','回风进口'),
         'Fan_out0':('supply_out','送风出口'),'Coil_in1':('water_in','冷冻水进口'),'Coil_out1':('water_out','冷冻水出口')},
        '空调箱（混风箱＋过滤器＋水盘管＋风机）：新风与回风混合后处理并加压送出；水侧为独立液体回路。')


def fahu_module():
    """新风机组：只处理新风，不含混风箱。"""
    return air_terminal('fahu_standard','新风机组（过滤＋盘管＋风机）',False,
        {'Filter':{'rated_volume_flow_m3_s':.35,'clean_pressure_drop_pa':100.},
         'Coil':{'air_side_ua_w_k':900.,'water_side_ua_w_k':2400.},
         'Fan':{'speed_ratio':1.,'nominal_flow_m3_h':1200.,
                'pressure_curve':[[0.,300.],[800.,220.],[1600.,80.],[2000.,0.]]}},
        {'Filter_in0':('air_in','新风进口'),'Fan_out0':('air_out','处理后送风'),
         'Coil_in1':('water_in','冷冻水进口'),'Coil_out1':('water_out','冷冻水出口')},
        '新风机组（过滤器＋水盘管＋风机）：只处理新风，风侧与水侧各自成通路。')


def fcu_module():
    """风机盘管末端：室内回风经盘管处理后送回房间。"""
    return air_terminal('fcu_terminal','风机盘管末端（过滤＋盘管＋风机）',False,
        {'Filter':{'rated_volume_flow_m3_s':.25,'clean_pressure_drop_pa':60.},
         'Coil':{'air_side_ua_w_k':700.,'water_side_ua_w_k':1800.},
         'Fan':{'speed_ratio':1.,'nominal_flow_m3_h':900.,
                'pressure_curve':[[0.,90.],[600.,60.],[1200.,20.],[1600.,0.]]}},
        {'Filter_in0':('return_in','回风口'),'Fan_out0':('supply_out','送风口'),
         'Coil_in1':('water_in','冷冻水进口'),'Coil_out1':('water_out','冷冻水出口')},
        '风机盘管末端（过滤器＋水盘管＋风机）：室内回风经处理后送回房间；水侧为独立液体回路。')


def makeup_module():
    """定压补水装置：止回阀、过滤器与平衡阀成套；补水压力边界保留在组合外部。"""
    check,strainer,balance=check_module(),filter_module(),valve_module()
    return compose('makeup_water_unit','定压补水装置（止回阀＋过滤器＋平衡阀）',
        [check,strainer,balance],
        [{'id':'Strainer','module_id':'water_strainer','name':'补水过滤器'},
         {'id':'Check','module_id':'hvac_check_valve','name':'补水止回阀','parameters':{'kv_m3_h':20.,'opening_pressure_pa':500.,'closing_pressure_pa':200.}},
         {'id':'Balance','module_id':'water_balancing_valve','name':'补水调节阀','parameters':{'kv_m3_h':8.,'opening_ratio':.5}}],
        [{'id':'strainer-check','source':{'instance_id':'Strainer','port_id':'out0'},'target':{'instance_id':'Check','port_id':'in0'}},
         {'id':'check-balance','source':{'instance_id':'Check','port_id':'out0'},'target':{'instance_id':'Balance','port_id':'in0'}}],
        {'Strainer_in0':('makeup_in','补水进口（接定压边界）'),'Balance_out0':('supply_out','补入回路')},
        '定压补水装置（过滤器＋止回阀＋调节阀）：补水边界固定在组合外部，'
        '回路压力低于定压设定时止回阀自动导通；补水量看 state.Check.throughput_kg。')


def header_module(branches=4, collector=False, tee=False):
    if branches not in range(2,9): raise ValueError('分集水器支路数须为 2 到 8')
    resistance,junction=resistance_module(),junction_module(branches+1)
    instances=[{'id':'Node','module_id':junction.id,'name':'汇合节点'},
               {'id':'Common','module_id':resistance.id,'name':'公共通路','parameters':{'loss_coefficient':0.}}]
    links=[{'id':'common','source':{'instance_id':'Common','port_id':'out0'},'target':{'instance_id':'Node','port_id':'p0'}}]
    ports={'Common_in0':('common','公共口（总管）')}
    for index in range(1,branches+1):
        key='Branch'+str(index)
        instances.append({'id':key,'module_id':resistance.id,'name':'支路 '+str(index),
                          'parameters':{'loss_coefficient':1. if tee and index==2 else .2}})
        links.append({'id':'branch'+str(index),'source':{'instance_id':'Node','port_id':'p'+str(index)},'target':{'instance_id':key,'port_id':'in0'}})
        ports[key+'_out0']=('branch'+str(index),('汇入' if collector else '分出')+'口 '+str(index))
    identifier='water_tee' if tee else ('water_collector_' if collector else 'water_header_')+str(branches)
    name='水侧三通' if tee else ('集水器' if collector else '分水器')+'（'+str(branches)+'支路）'
    module=compose(identifier,name,[resistance,junction],instances,links,ports)
    data=module.model_dump(mode='json')
    if collector:
        for port in data['ports']: port['direction']='out' if port['id']=='common' else 'in'
    # Geometry and K are public, static-editable parameters; zero K selects ideal legs.
    for child in data['composite']['children']:
        for parameter in resistance.parameters if child['id']!='Node' else []:
            if any(p['id']==child['id']+'_'+parameter.id for p in data['parameters']): continue
            payload=parameter.model_dump(mode='json'); payload.update(id=child['id']+'_'+parameter.id,label=child['id']+' · '+parameter.label,
                default=child['parameters'].get(parameter.id,parameter.default))
            data['parameters'].append(payload)
            data['composite']['parameter_maps'][payload['id']]=[{'instance_id':child['id'],'parameter_id':parameter.id}]
    return ModuleDefinition.model_validate(data)


def three_way_module():
    ports=[{'id':side+'_'+end,'label':side+' '+end,'direction':'in' if end=='in' else 'out'}
           for side in ('a','b') for end in ('in','out')]
    channels=[{'id':side,'name':side,'input_port':side+'_in','output_port':side+'_out','relation':'resistance','solver_model':'valve'} for side in ('a','b')]
    core=base('hvac_three_way_core','三通阀双通路',THREE_WAY_SOURCE,
        [number('opening_ratio','A 路开度（B 路为互补）',.5,display='%',scale=.01,maximum=1.,runtime=True),
         number('kv_m3_h','两通路全开 Kv',16.,'flow_coefficient','m³/h',minimum=.001)],ports=ports,channels=channels,
        variables=[output('a_flow_kg_s','A 路流量','mass_flow','kg/s'),output('b_flow_kg_s','B 路流量','mass_flow','kg/s'),
                   output('state.throughput_kg','两通路累计通过质量','mass','kg')])
    resistance,junction=resistance_module(),junction_module(3)
    return compose('water_three_way_valve','三通调节阀（分流／混流）',[core,resistance,junction],
        [{'id':'Common','module_id':resistance.id,'name':'公共通路','parameters':{'loss_coefficient':0.}},
         {'id':'Node','module_id':junction.id,'name':'内部汇合'}, {'id':'Valve','module_id':core.id,'name':'阀芯'}],
        [{'id':'c','source':{'instance_id':'Common','port_id':'out0'},'target':{'instance_id':'Node','port_id':'p0'}},
         {'id':'a','source':{'instance_id':'Node','port_id':'p1'},'target':{'instance_id':'Valve','port_id':'a_in'}},
         {'id':'b','source':{'instance_id':'Node','port_id':'p2'},'target':{'instance_id':'Valve','port_id':'b_in'}}],
        {'Common_in0':('common','公共口'),'Valve_a_out':('a','A 口'),'Valve_b_out':('b','B 口')})


def pump_module():
    module=base('hvac_water_pump','循环水泵（含停机阻力）',PUMP_SOURCE,
        [number('running','启停（0／1）',1.,maximum=1.,runtime=True),
         number('speed_ratio','转速比',1.,minimum=.05,maximum=2.,runtime=True),
         {'id':'head_curve','label':'流量 m³/h—扬程 m','value_type':'curve','default':[[0,20],[10,18],[20,12],[30,0]]},
         number('efficiency_ratio','水泵效率',.75,minimum=.05,maximum=1.),
         number('motor_efficiency','电机效率',.9,minimum=.05,maximum=1.),
         number('diameter_m','停机通路内径',.05,'length','m','mm',.001,minimum=.001),
         number('stopped_loss_coefficient','停机被动阻力 K',20.,minimum=.001)],
        variables=[output('is_running','实际启停'),output('pump_shaft_power_w','轴功率','power','W','kW',1000.),
                   output('electric_power_w','电功率','power','W','kW',1000.),output('state.electric_energy_j','累计耗电','energy','J','kWh',3600000.),
                   output('state.throughput_kg','累计通过质量','mass','kg')])
    data=module.model_dump(mode='json')
    data['sdk']['capabilities'].append('net.pump')
    # This module's bench uses low inlet/high outlet pressure (like the pump template).
    data['channels'][0]['solver_model']='pump_curve'
    return ModuleDefinition.model_validate(data)


def check_module():
    return base('hvac_check_valve','止回阀（开启／关闭压差）',CHECK_SOURCE,
        [number('kv_m3_h','全开 Kv',50.,'flow_coefficient','m³/h',minimum=.001),
         number('opening_pressure_pa','开启压差',1000.,'pressure','Pa','kPa',1000.),
         number('closing_pressure_pa','关闭压差',500.,'pressure','Pa','kPa',1000.)],
        variables=[output('flowing','当前导通'),output('state.is_open','接受状态导通'),
                   output('state.throughput_kg','累计正向通过质量','mass','kg')])


def equipment_definitions():
    return [valve_module(),valve_module('water_shutoff_valve','蝶阀／球阀（关断阀）',True),filter_module(),pump_module(),check_module(),
            header_module(2,tee=True),three_way_module(),
            *[header_module(count,collector) for collector in (False,True) for count in (2,4,6,8)],
            ahu_module(),fahu_module(),fcu_module(),makeup_module()]


def equipment(identifier):
    return next(module for module in equipment_definitions() if module.id==identifier)
