import math

def design(ctx):
    p=ctx.parameters
    for s in ('hot','cold'):
        if not p['design_'+s+'_fluid_note'].strip():raise ValueError('两侧工质与比热来源须分别声明')
    mh,mc=p['design_hot_mass_flow_kg_s'],p['design_cold_mass_flow_kg_s']
    ch,cc=mh*p['design_hot_cp_j_kg_k'],mc*p['design_cold_cp_j_kg_k']
    dt=p['design_hot_temperature_k']-p['design_cold_temperature_k'];power=p['design_heat_w']
    if min(ch,cc,dt,power)<=0:raise ValueError('两侧热容率、温差与目标热量须大于零')
    small,large=min(ch,cc),max(ch,cc);eps=power/(small*dt)
    if not 0<eps<1:raise ValueError('目标能力达到或超过无限UA极限，夹点不可行')
    ratio=small/large
    ntu=eps/(1-eps) if abs(ratio-1)<1e-9 else math.log((1-eps*ratio)/(1-eps))/(1-ratio)
    effective=ntu*small
    resistance=p['hot_fouling_resistance_k_w']+p['cold_fouling_resistance_k_w']
    if resistance*effective>=1:raise ValueError('污垢热阻使目标能力不可达')
    clean=1/(1/effective-resistance)
    ctx.set('clean_ua_w_k',clean)
    ctx.log(f'逆流设计：有效UA {effective:.8g} W/K，清洁UA {clean:.8g} W/K；热侧出口 {p["design_hot_temperature_k"]-power/ch:.6g} K，冷侧出口 {p["design_cold_temperature_k"]+power/cc:.6g} K。')
    ctx.log('设计分别使用两侧用户提供的参考比热；运行按各自回路实际物性计算，变化比热工况须再复核。')
