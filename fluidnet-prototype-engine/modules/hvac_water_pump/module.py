import math
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
