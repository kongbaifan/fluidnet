"""Gas fan with a declared Q/n efficiency curve and passive stopped resistance."""
import math


def curve(points, efficiency=False):
    if len(points) < 2 or points[0][0] != 0:
        raise ValueError('FAN_CURVE_RANGE: 曲线至少两点，首点流量须为0')
    for i, (x, y) in enumerate(points):
        if not math.isfinite(x) or not math.isfinite(y) or x < 0 or (i and x <= points[i-1][0]):
            raise ValueError('FAN_CURVE_RANGE: 流量轴须有限非负并严格递增')
        if efficiency and not 0 < y <= 1:
            raise ValueError('FAN_EFFICIENCY_RANGE: 效率须大于0且不大于1')
        if not efficiency and (y < 0 or i and y >= points[i-1][1]):
            raise ValueError('FAN_CURVE_RANGE: 风压须非负且严格递减')
    if not efficiency and points[-1][1] != 0:
        raise ValueError('FAN_CURVE_RANGE: 风压末点须为0；不裁剪或外推')


def interpolate(points, x):
    if x < -1e-8 or x > points[-1][0] * (1+1e-6):
        raise ValueError('FAN_EFFICIENCY_RANGE: 工作点超出效率曲线有效范围')
    for (x0,y0),(x1,y1) in zip(points,points[1:]):
        if x <= x1:
            return y0+(y1-y0)*(max(x,x0)-x0)/(x1-x0)
    return points[-1][1]


class Module:
    def initialize(self, ctx):
        p=ctx.parameters
        curve(p['pressure_curve']);curve(p['efficiency_curve'],True)
        if p['efficiency_curve'][-1][0] < p['pressure_curve'][-1][0]:
            raise ValueError('FAN_EFFICIENCY_RANGE: 效率曲线须覆盖完整额定风量范围')
        ctx.state.setdefault('electric_energy_j',0.)
        ctx.state.setdefault('shaft_energy_j',0.)

    def active(self,ctx):
        return ctx.parameters['running']>=.5 and ctx.parameters['speed_ratio']>0

    def evaluate(self,ctx):
        p=ctx.parameters
        upstream=ctx.port('in0')
        if self.active(ctx):
            ctx.net.pump(channel='main',head_curve=[[q,dp/(upstream.density_kg_m3*9.80665)] for q,dp in p['pressure_curve']],
                         speed_ratio=p['speed_ratio'],density_kg_m3=upstream.density_kg_m3)
        else:
            # Standard pressure relations have no trial channel flow; passive flow follows delta-p.
            inlet=ctx.port('in0');outlet=ctx.port('out0')
            density=(inlet if inlet.pressure_pa>=outlet.pressure_pa else outlet).density_kg_m3
            ctx.net.resistance(channel='main',diameter_m=p['diameter_m'],loss_coefficient=p['stopped_loss_coefficient'],density_kg_m3=density)

    def point(self,ctx):
        c,p=ctx.channel('main'),ctx.parameters
        if not self.active(ctx):
            return 0.,0.,0.
        if c.mass_flow_kg_s < -1e-8:
            raise ValueError('FAN_REVERSE_RUNNING: 运行风机不支持反转流动')
        volume=max(c.mass_flow_kg_s,0.)/ctx.port('in0').density_kg_m3
        eta=interpolate(p['efficiency_curve'],volume*3600./p['speed_ratio'])
        hydraulic=max(0.,-c.pressure_drop_pa)*volume
        return hydraulic,hydraulic/eta,eta

    def thermal(self,ctx):
        hydraulic,shaft,_=self.point(ctx)
        # The engine already adds hydraulic work. Add only fan dissipation; motor loss stays outside.
        ctx.heat('main',shaft-hydraulic)

    def observe(self,ctx):
        hydraulic,shaft,eta=self.point(ctx)
        ctx.var('pressure_rise_pa',-ctx.channel('main').pressure_drop_pa)
        ctx.var('hydraulic_power_w',hydraulic);ctx.var('shaft_power_w',shaft)
        ctx.var('electric_power_w',shaft/ctx.parameters['motor_efficiency'])
        ctx.var('efficiency_ratio',eta);ctx.var('is_running',float(self.active(ctx)))

    def commit_step(self,ctx,dt_s):
        _,shaft,_=self.point(ctx)
        ctx.state['shaft_energy_j']+=shaft*dt_s
        ctx.state['electric_energy_j']+=shaft/ctx.parameters['motor_efficiency']*dt_s

    def finalize(self,ctx):
        pass
