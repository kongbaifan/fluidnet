"""S1 independent design-enabled equipment. No changes to existing published IDs."""
from pathlib import Path
from .model_types.module import ModuleDefinition
from .hvac_basic import number
from .hvac_expansion import fan_performance, plate_exchanger

ROOT=Path(__file__).resolve().parents[2]

CURVE_DESIGN = r'''import math

def design(ctx):
    p=ctx.parameters
    points=p['CURVE_KEY']; efficiency=p['efficiency_curve']
    if len(points)<2 or points[0][0]!=0 or points[-1][1]!=0:
        raise ValueError('曲线须从零流量到零压升，至少两个点，禁止外推')
    if any(x<0 or y<0 or not math.isfinite(x+y) or i and (x<=points[i-1][0] or y>=points[i-1][1]) for i,(x,y) in enumerate(points)):
        raise ValueError('性能曲线须流量严格递增、压升严格递减；非单调多解曲线不支持')
    if len(efficiency)<2 or efficiency[0][0]!=0 or efficiency[-1][0]<points[-1][0] or any(not 0<y<=1 or i and x<=efficiency[i-1][0] for i,(x,y) in enumerate(efficiency)):
        raise ValueError('效率曲线须递增流量轴、覆盖性能图且效率在(0,1]')
    if not p['data_source'].strip() or not p['design_fluid_note'].strip():raise ValueError('请填写数据来源和参考工质说明')
    q=p['design_flow_m3_s']*3600.;target=p['TARGET_KEY']
    if q<=0 or target<=0:raise ValueError('目标流量和扬程/压差须大于零')
    inlet=ctx.fluid.state_pt(p['design_inlet_pressure_pa'],p['design_temperature_k'])
    if 'PHASE' not in inlet.phase.lower():raise ValueError('设计工质相态不适用')
    factor=FACTOR
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
'''

PLATE_DESIGN = r'''import math

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
'''

def text(key,label,value):return {'id':key,'label':label,'value_type':'text','default':value}

def curve_machine(pump=False):
    data=fan_performance().model_dump(mode='json')
    data.update(id='design_pump' if pump else 'design_fan',name='多点曲线选型泵' if pump else '多点曲线选型风机',category='设备选型')
    params=data['parameters']
    if pump:
        for p in params:
            if p['id']=='pressure_curve':p.update(id='head_curve',label='额定流量m³/h—扬程m',default=[[0.,30.],[10.,25.],[20.,12.],[25.,0.]])
            elif p['id']=='efficiency_curve':p['default']=[[0.,.3],[10.,.72],[20.,.65],[25.,.3]]
            elif p['id']=='diameter_m':p['default']=.05
        data['source']['runtime']=data['source']['runtime'].replace("head_curve=[[q,dp/(upstream.density_kg_m3*9.80665)] for q,dp in p['pressure_curve']]", "head_curve=p['head_curve']").replace("p['pressure_curve']","p['head_curve']")
        data['applicability'].update(phases=['liquid'],fluids=[])
        data['sdk']['capabilities']=[c for c in data['sdk']['capabilities'] if c!='air.pass_through.v1']
    else:
        data['source']['runtime']=data['source']['runtime'].replace("dp/(upstream.density_kg_m3*9.80665)","dp/(p['reference_density_kg_m3']*9.80665)")
        params.append(number('reference_density_kg_m3','曲线参考空气密度',1.2,'density','kg/m3',minimum=.1))
    params += [number('design_flow_m3_s','设计目标体积流量',10/3600 if pump else 2000/3600,'volume_flow','m3/s','m3/h',1/3600),
        number('design_head_m' if pump else 'design_pressure_rise_pa','设计目标扬程' if pump else '设计目标压升',25. if pump else 250.,'length' if pump else 'pressure','m' if pump else 'Pa'),
        number('design_inlet_pressure_pa','设计入口绝压',250000. if pump else 101325.,'pressure','Pa','kPa',1000.,minimum=1.),
        number('design_temperature_k','设计入口温度',293.15,'temperature','K','°C'),
        number('minimum_speed_ratio','最低设计转速比',.2,minimum=.01,maximum=2.),number('maximum_speed_ratio','最高设计转速比',1.5,minimum=.01,maximum=2.),
        text('data_source','性能数据来源','教学分段线性曲线，未经厂家标定'),text('design_fluid_note','设计参考工质说明','水/乙二醇单相液体' if pump else 'Air；参考密度1.2 kg/m³')]
    next(p for p in params if p['id']=='design_temperature_k')['unit']['display_offset']=-273.15
    # Final engineering envelope, never reject intermediate Newton states solely for a design limit.
    data['source']['runtime']=data['source']['runtime'].replace("def observe(self,ctx):", "def observe(self,ctx):\n        if self.active(ctx) and not ctx.parameters['minimum_speed_ratio'] <= ctx.parameters['speed_ratio'] <= ctx.parameters['maximum_speed_ratio']:\n            raise ValueError('转速超出声明的性能范围')")
    data['source']['design']=CURVE_DESIGN.replace('CURVE_KEY','head_curve' if pump else 'pressure_curve').replace('TARGET_KEY','design_head_m' if pump else 'design_pressure_rise_pa').replace('PHASE','liquid' if pump else 'gas').replace('FACTOR','1.' if pump else "inlet.density_kg_m3/p['reference_density_kg_m3']")
    data['source']['runtime']=data['source']['runtime'].replace("ctx.var('pressure_rise_pa',-ctx.channel('main').pressure_drop_pa)", "ctx.var('pressure_rise_pa',-ctx.channel('main').pressure_drop_pa)\n        ctx.var('head_m',-ctx.channel('main').pressure_drop_pa/(ctx.port('in0').density_kg_m3*9.80665))")
    from .hvac_basic import output
    data['variables'] += [output('volume_flow_m3_h','实际体积流量','volume_flow','m3/h'),output('head_m','实际扬程','length','m')]
    data['description']='单相多点性能/效率图与相似律设计；转速为建议值，实际流量由网络求解；数据来源与范围须用户确认。'
    return ModuleDefinition.model_validate(data)

def design_plate():
    data=plate_exchanger().model_dump(mode='json');data.update(id='design_plate_exchanger',name='双侧参考物性板换选型',category='设备选型')
    data['parameters'] += [number('design_heat_w','设计目标换热量',10000.,'power','W','kW',1000.)]
    for side,temp,cp in [('hot',333.15,4180.),('cold',293.15,3800.)]:
        data['parameters'] += [number('design_'+side+'_mass_flow_kg_s',side+'侧设计质量流量',.5,'mass_flow','kg/s'),number('design_'+side+'_cp_j_kg_k',side+'侧设计比热',cp,'specific_heat','J/(kg K)',minimum=1.),number('design_'+side+'_temperature_k',side+'侧设计进口温度',temp,'temperature','K','°C'),text('design_'+side+'_fluid_note',side+'侧工质/比热来源','独立参考比热；运行回路须另行指定工质')]
        next(p for p in data['parameters'] if p['id']=='design_'+side+'_temperature_k')['unit']['display_offset']=-273.15
    data['source']['design']=PLATE_DESIGN
    data['description']='逆流ε–NTU设计，分别输入两侧有来源的比热；运行复用板换真实双回路物性，不自动替换项目工质。'
    return ModuleDefinition.model_validate(data)

def definitions():return [curve_machine(True),curve_machine(),design_plate()]
