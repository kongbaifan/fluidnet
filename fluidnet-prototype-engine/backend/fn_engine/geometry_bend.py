"""Circular bend driven by declared geometry coefficient tables, not an undocumented correlation."""
from .hvac_basic import base, number, output

SOURCE='''import math

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
'''


def definition():
    p=[number('diameter_m','圆管内径',.1,'length','m','mm',.001,minimum=.001),
       number('radius_diameter_ratio','中心曲率半径/内径',1.5,minimum=.5,maximum=3.),
       number('angle_deg','转弯角度',90.,'angle','degree',minimum=0.,maximum=180.),
       number('maximum_velocity_m_s','系数表最大适用速度',10.,'velocity','m/s',minimum=.01),
       {'id':'radius_coefficient_curve','label':'R/D—90度K表（教学，请按来源替换）','value_type':'curve','default':[[.5,1.5],[1,.5],[1.5,.3],[3,.2]]},
       {'id':'angle_factor_curve','label':'角度—K倍率表（教学）','value_type':'curve','default':[[0,0],[45,.5],[90,1],[180,1.5]]},
       {'id':'data_source','label':'系数数据来源','value_type':'text','default':'教学假设，不是标准关联式或厂家数据'}]
    m=base('geometry_bend','圆弯头（几何系数表）',SOURCE,p,variables=[output('loss_coefficient','实际局部阻力系数'),
        output('velocity_m_s','截面平均速度','velocity','m/s'),output('actual_pressure_drop_pa','压差','pressure','Pa','kPa',1000.),
        output('state.throughput_kg','累计通过质量','mass','kg')])
    m.description='圆截面局部阻力：K=用户R/D表×角度倍率表，按本设备截面平均速度；分段线性禁止外推。无内置全Re经验式，不含沿程摩擦、矩形变径或导流叶片。'
    return m
