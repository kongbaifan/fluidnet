import math
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
