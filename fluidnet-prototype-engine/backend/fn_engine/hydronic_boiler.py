"""Capacity-limited fuel-to-liquid heat source; no combustion/flue or thermal storage model."""
from .hvac_basic import base, number, output

SOURCE='''class Module:
    def initialize(self,ctx):
        ctx.state.setdefault('heat_energy_j',0.)
        ctx.state.setdefault('fuel_energy_j',0.)
    def evaluate(self,ctx):
        p=ctx.parameters
        a,b=ctx.port('in0'),ctx.port('out0')
        inlet=a if a.pressure_pa>=b.pressure_pa else b
        ctx.net.resistance(channel='main',diameter_m=p['diameter_m'],loss_coefficient=p['loss_coefficient'],density_kg_m3=inlet.density_kg_m3)
    def thermal(self,ctx):
        p=ctx.parameters
        m=abs(ctx.channel('main').mass_flow_kg_s)
        active=p['running']>=.5 and p['capacity_ratio']>0
        power=p['rated_heat_w']*p['capacity_ratio'] if active and m>=p['minimum_mass_flow_kg_s'] else 0.
        ctx.heat('main',power)
    def observe(self,ctx):
        p=ctx.parameters;c=ctx.channel('main')
        requested=p['running']>=.5 and p['capacity_ratio']>0
        if requested and abs(c.mass_flow_kg_s)<p['minimum_mass_flow_kg_s']:
            ctx.diagnostic('BOILER_LOW_FLOW','锅炉供热请求时流量不足，拒绝当前运行点',severity='error')
        expected=p['rated_heat_w']*p['capacity_ratio'] if requested else 0.
        if requested and abs(c.heat_w-expected)>1e-6+1e-6*expected:
            ctx.diagnostic('BOILER_HEAT_NOT_SOLVED','锅炉供热请求未完成热联算，请启用热力求解',severity='error')
        outlet=ctx.port('out0' if c.mass_flow_kg_s>=0 else 'in0')
        if outlet.temperature_k>p['maximum_outlet_temperature_k']:
            ctx.diagnostic('BOILER_TEMPERATURE','锅炉出口超过温度上限',severity='error')
        ctx.var('delivered_heat_w',c.heat_w)
        ctx.var('fuel_power_w',c.heat_w/p['thermal_efficiency'])
        ctx.var('flue_loss_w',c.heat_w*(1/p['thermal_efficiency']-1))
    def commit_step(self,ctx,dt_s):
        power=ctx.channel('main').heat_w
        ctx.state['heat_energy_j']+=power*dt_s
        ctx.state['fuel_energy_j']+=power/ctx.parameters['thermal_efficiency']*dt_s
    def finalize(self,ctx): pass
'''


def definition():
    parameters=[number('rated_heat_w','额定供热能力',20000.,'power','W','kW',1000.,minimum=1.),
        number('capacity_ratio','供热比例',1.,display='%',scale=.01,maximum=1.,runtime=True),
        number('running','燃烧启停',1.,maximum=1.,runtime=True),
        number('thermal_efficiency','热效率（低位热值口径）',.9,display='%',scale=.01,minimum=.01,maximum=1.),
        number('minimum_mass_flow_kg_s','最小液体质量流量',.05,'mass_flow','kg/s',minimum=1e-9),
        number('maximum_outlet_temperature_k','最高出水温度',363.15,'temperature','K',minimum=274.15),
        number('diameter_m','水侧口径',.05,'length','m','mm',.001,minimum=.001),
        number('loss_coefficient','水侧阻力K',5.,minimum=.001)]
    parameters[5]['unit'].update(display_unit='°C',display_offset=-273.15)
    variables=[output(k,label,'power','W','kW',1000.) for k,label in [('delivered_heat_w','实际供热'),('fuel_power_w','燃料低位热输入'),('flue_loss_w','未进入水侧的热损')]]
    variables += [output(k,label,'energy','J','kWh',3600000.) for k,label in [('state.heat_energy_j','累计供热'),('state.fuel_energy_j','累计燃料输入')]]
    m=base('hydronic_boiler','热水锅炉（容量与效率）',SOURCE,parameters,variables=variables)
    data=m.model_dump(mode='json')
    data['sdk']['capabilities']=[c for c in data['sdk']['capabilities'] if c!='air.pass_through.v1']+['thermal.v1']
    data['applicability']={'execution_domains':['fluid'],'phases':['liquid'],
        'assumptions':['普通单相液体；额定能力与固定低位热值效率，锅炉本体无储热；不模拟燃烧、排烟、冷凝或启停损失。']}
    data['description']='额定供热×负荷比例进入水侧，按固定热效率统计燃料输入；最小流量/出水超温拒绝最终运行点，停炉水侧保留阻力。'
    return type(m).model_validate(data)
