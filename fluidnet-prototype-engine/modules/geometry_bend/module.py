import math

def interpolate(points,x):
    if len(points)<2 or any(len(row)!=2 or any(not math.isfinite(v) for v in row) or row[1]<0 for row in points):
        raise ValueError('系数表须有两个以上有限非负系数点')
    if any(a[0]>=b[0] for a,b in zip(points,points[1:])) or not points[0][0]<=x<=points[-1][0]:
        raise ValueError('系数表横坐标须递增，几何必须落在表范围内，禁止外推')
    for a,b in zip(points,points[1:]):
        if x<=b[0]:return a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0])

class Module:
    def coefficient(self,p):
        return interpolate(p['radius_coefficient_curve'],p['radius_diameter_ratio'])*interpolate(p['angle_factor_curve'],p['angle_deg'])
    def initialize(self,ctx):
        self.coefficient(ctx.parameters)
        ctx.state.setdefault('throughput_kg',0.)
    def evaluate(self,ctx):
        p=ctx.parameters
        port=ctx.port('in0' if ctx.port('in0').pressure_pa>=ctx.port('out0').pressure_pa else 'out0')
        ctx.net.resistance(channel='main',diameter_m=p['diameter_m'],loss_coefficient=self.coefficient(p),density_kg_m3=port.density_kg_m3)
    def observe(self,ctx):
        p=ctx.parameters;c=ctx.channel('main');port=ctx.port('in0' if c.mass_flow_kg_s>=0 else 'out0')
        rho=port.density_kg_m3; area=math.pi*p['diameter_m']**2/4
        velocity=abs(c.mass_flow_kg_s)/(rho*area)
        if velocity>p['maximum_velocity_m_s']:
            ctx.diagnostic('BEND_TABLE_RANGE','弯头速度超过用户声明系数表适用范围',severity='error')
        ctx.var('loss_coefficient',self.coefficient(p));ctx.var('velocity_m_s',velocity)
        ctx.var('actual_pressure_drop_pa',c.pressure_drop_pa)
    def commit_step(self,ctx,dt_s):ctx.state['throughput_kg']+=abs(ctx.channel('main').mass_flow_kg_s)*dt_s
    def finalize(self,ctx):pass
