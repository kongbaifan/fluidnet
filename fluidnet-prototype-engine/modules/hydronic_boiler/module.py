class Module:
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
