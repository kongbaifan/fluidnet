import math
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
