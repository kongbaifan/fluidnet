import math
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
