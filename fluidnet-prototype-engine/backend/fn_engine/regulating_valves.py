"""Reusable liquid regulating valves; immutable v1 seed contracts, not implicit controllers."""
from pathlib import Path

from .hvac_basic import base, number, output

ROOT = Path(__file__).resolve().parents[2]


SOURCE = '''import math
MODE = '__MODEL__'

class Module:
    def initialize(self,ctx):
        p=ctx.parameters
        if p['maximum_pressure_drop_pa'] <= p['minimum_pressure_drop_pa']:
            raise ValueError('最大允许压差必须大于起调压差')
        ctx.state.setdefault('throughput_kg',0.)
    def operating(self,ctx):
        p=ctx.parameters
        drop=ctx.port('in0').pressure_pa-ctx.port('out0').pressure_pa
        density=(ctx.fluid.state_pt(ctx.port('in0').pressure_pa,ctx.port('in0').temperature_k).density_kg_m3
                 if ctx.port('in0').temperature_k is not None else ctx.port('in0').density_kg_m3)
        if density is None or density<=0: raise ValueError('入口液体密度必须为正')
        if MODE=='bypass':
            opening=min(1.,max(0.,(drop-p['minimum_pressure_drop_pa'])/p['proportional_band_pa']))
            kv=p['kv_m3_h']
        else:
            # Finite maximum Kv: below minimum dp the regulator runs out of authority.
            kv=p['rated_volume_flow_m3_h']/math.sqrt(p['minimum_pressure_drop_pa']/1e5/(density/1000.))
            opening=p['opening_ratio']*min(1.,math.sqrt(p['minimum_pressure_drop_pa']/drop)) if drop>0 else 0.
        return drop,density,kv,opening
    def evaluate(self,ctx):
        drop,density,kv,opening=self.operating(ctx)
        ctx.net.valve(channel='main',kv=kv,opening=opening,density_kg_m3=density)
    def observe(self,ctx):
        p=ctx.parameters
        drop,density,kv,opening=self.operating(ctx)
        if drop>p['maximum_pressure_drop_pa']:
            ctx.diagnostic('REGULATING_VALVE_RANGE',f"压差 {drop:g} Pa 超过允许值 {p['maximum_pressure_drop_pa']:g} Pa",severity='error')
        flow=ctx.channel('main').mass_flow_kg_s
        ctx.var('effective_opening',opening)
        ctx.var('effective_kv_m3_h',kv*opening)
        ctx.var('actual_pressure_drop_pa',drop)
        ctx.var('actual_volume_flow_m3_h',flow/density*3600.)
        ctx.var('regulating',int(MODE=='picv' and p['opening_ratio']>0 and drop>=p['minimum_pressure_drop_pa']))
    def commit_step(self,ctx,dt_s):
        ctx.state['throughput_kg']+=abs(ctx.channel('main').mass_flow_kg_s)*dt_s
    def finalize(self,ctx): pass
'''


def valve_definition(picv=False):
    model = 'picv' if picv else 'bypass'
    identifier = 'pressure_independent_valve' if picv else 'differential_bypass_valve'
    label = '压差无关控制阀（理想稳态调节区）' if picv else '自力式压差旁通阀（比例式）'
    parameters = [
        number('minimum_pressure_drop_pa','最小工作压差' if picv else '开启压差',20000.,'pressure','Pa','kPa',1000.,minimum=1.),
        number('maximum_pressure_drop_pa','最大允许压差',300000.,'pressure','Pa','kPa',1000.,minimum=1.),
    ]
    if picv:
        parameters += [number('rated_volume_flow_m3_h','额定调节流量',5.,'volume_flow','m³/h',minimum=.001),
                       number('opening_ratio','流量设定比例',1.,display='%',scale=.01,maximum=1.,runtime=True)]
    else:
        parameters += [number('kv_m3_h','最大 Kv',16.,'flow_coefficient','m³/h',minimum=.001),
                       number('proportional_band_pa','全开压差增量',30000.,'pressure','Pa','kPa',1000.,minimum=1.)]
    module = base(identifier,label,SOURCE.replace('__MODEL__',model),parameters,variables=[
        output('effective_opening','内部有效开度'), output('effective_kv_m3_h','有效 Kv','flow_coefficient','m³/h'),
        output('actual_pressure_drop_pa','压差','pressure','Pa','kPa',1000.),
        output('actual_volume_flow_m3_h','实际体积流量','volume_flow','m³/h'),
        output('regulating','处于恒流调节区'),output('state.throughput_kg','累计通过质量','mass','kg')])
    payload = module.model_dump(mode='json')
    payload['sdk']['capabilities'].remove('air.pass_through.v1')
    payload['sdk']['capabilities'].append('properties.v1')
    payload['applicability']={'execution_domains':['fluid'],'phases':['liquid'],
        'assumptions':['单相液体、无储量、稳态机械平衡、正向通流；不含动作时间、回差、汽蚀或厂家标定。']}
    payload['description'] = (label+'。反压关闭，超出允许压差拒绝最终结果。'+
        ('达到最小压差时调节到设定体积流量，低压差受最大Kv限制；无无限压差工作假设。' if picv else
         '开启阈值以上内部开度随压差线性上升，达到比例带末端后全开，不保证压差严格恒定。'))
    return type(module).model_validate(payload)


def definitions():
    return [valve_definition(False),valve_definition(True)]


def example(identifier='pressure_independent_valve'):
    from .catalog import catalog_map
    from .models import Project
    module=next(m for m in definitions() if m.id==identifier)
    return Project(id='example-'+identifier,name=module.name+' · 水回路',
        description='教学参数：入口250kPa、出口200kPa、20°C水；关闭/压差及流量用设备参数设置。',
        modules=[catalog_map()['source'],module],instances=[
            {'id':'Supply','name':'入口','module_id':'source','parameters':{'pressure_pa':250000.},'position':{'x':150,'y':200}},
            {'id':'Regulator','name':module.name,'module_id':module.id,'position':{'x':500,'y':200}},
            {'id':'Return','name':'出口','module_id':'source','parameters':{'pressure_pa':200000.},'position':{'x':850,'y':200}}],
        connections=[{'id':'in','source':{'instance_id':'Supply','port_id':'out0'},'target':{'instance_id':'Regulator','port_id':'in0'}},
                     {'id':'out','source':{'instance_id':'Regulator','port_id':'out0'},'target':{'instance_id':'Return','port_id':'out0'}}],
        solver={'thermal':True,'property_coupling':'node'})
