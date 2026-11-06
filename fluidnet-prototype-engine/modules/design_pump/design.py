import math

def design(ctx):
    p=ctx.parameters
    points=p['head_curve']; efficiency=p['efficiency_curve']
    if len(points)<2 or points[0][0]!=0 or points[-1][1]!=0:
        raise ValueError('曲线须从零流量到零压升，至少两个点，禁止外推')
    if any(x<0 or y<0 or not math.isfinite(x+y) or i and (x<=points[i-1][0] or y>=points[i-1][1]) for i,(x,y) in enumerate(points)):
        raise ValueError('性能曲线须流量严格递增、压升严格递减；非单调多解曲线不支持')
    if len(efficiency)<2 or efficiency[0][0]!=0 or efficiency[-1][0]<points[-1][0] or any(not 0<y<=1 or i and x<=efficiency[i-1][0] for i,(x,y) in enumerate(efficiency)):
        raise ValueError('效率曲线须递增流量轴、覆盖性能图且效率在(0,1]')
    if not p['data_source'].strip() or not p['design_fluid_note'].strip():raise ValueError('请填写数据来源和参考工质说明')
    q=p['design_flow_m3_s']*3600.;target=p['design_head_m']
    if q<=0 or target<=0:raise ValueError('目标流量和扬程/压差须大于零')
    inlet=ctx.fluid.state_pt(p['design_inlet_pressure_pa'],p['design_temperature_k'])
    if 'liquid' not in inlet.phase.lower():raise ValueError('设计工质相态不适用')
    factor=1.
    lo=max(p['minimum_speed_ratio'],q/points[-1][0]);hi=p['maximum_speed_ratio']
    def interp(curve,x):
        for (x0,y0),(x1,y1) in zip(curve,curve[1:]):
            if x<=x1:return y0+(y1-y0)*(x-x0)/(x1-x0)
        raise ValueError('工作点越出曲线')
    def available(n):return factor*n*n*interp(points,q/n)
    if not 0<lo<=hi or available(lo)>target+1e-8 or available(hi)<target-1e-8:raise ValueError('指定转速范围内无合法工作点')
    for _ in range(70):
        mid=(lo+hi)/2
        if available(mid)<target:lo=mid
        else:hi=mid
    speed=(lo+hi)/2;eta=interp(efficiency,q/speed)
    ctx.set('speed_ratio',speed)
    ctx.log(f'设计结果：转速比 {speed:.9g}；效率 {eta:.6g}；参考密度 {inlet.density_kg_m3:.6g} kg/m³。')
    ctx.log('只改变转速建议，实际流量仍由网络曲线交点求解；不含失速/气蚀/可压缩修正。')
