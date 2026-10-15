"""Reproducible trial suite: one external snapshot and four repository references."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import zipfile

from fn_engine.compiler import compile_project
from fn_engine.models import CircuitFluid, Endpoint, FluidConfig, Project, RunRequest
from fn_engine.packages import load_module_package
from fn_engine.properties import property_service
from fn_engine.solver import solve_dynamic, solve_steady
from acceptance_cases import assemble

ROOT=Path(__file__).resolve().parents[1]
G=9.80665
WATER=property_service(FluidConfig())
REFERENCE=WATER.state_pt(250000,293.15)


def load(relative):
    return json.loads((ROOT/relative).read_text(encoding='utf-8'))


def fingerprint(relative):
    return {'path':relative,'sha256':hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()}


def check(name,actual,expected,relative=1e-8,absolute=1e-8):
    tolerance=max(absolute,abs(expected)*relative)
    return {'name':name,'actual':actual,'expected':expected,'absolute_error':abs(actual-expected),
            'tolerance':tolerance,'passed':abs(actual-expected)<=tolerance}


def baselu_pump():
    raw=load('tests/fixtures/baselu-test-water.json');v=raw['values']['MOD2']
    rho=REFERENCE.density_kg_m3
    end=(-v['B']-math.sqrt(v['B']**2-4*v['C']*v['A']))/(2*v['C'])
    # Declared mapping: Δp [MPa] = A + B·m + C·m², m in kg/s.
    # Sample the input polynomial independently of the cached operating flow.
    curve=[[m/rho*3600,max(0,(v['A']+v['B']*m+v['C']*m*m)*1e6/(rho*G))]
           for m in [end*i/1000 for i in range(1001)]]
    curve[-1][1]=0
    model=assemble('trial-baselu-pump',[('B1','source',{'pressure_pa':v['IM0_PRE']*1e6}),
        ('P','pump',{'head_curve':curve}),('B2','source',{'pressure_pa':v['EX0_PRE']*1e6})],
        [('B1:out0','P:in0'),('P:out0','B2:out0')])
    model.solver.thermal=False
    return model,{'kind':'external_snapshot_component','source':fingerprint('tests/fixtures/baselu-test-water.json'),
        'scope':'TEST 样例 MOD2 泵，在保存的入口/出口压力下重放；多项式到扬程曲线使用 1000 个区间，不等同完整 TEST 管网。',
        'mapping':'Δp(MPa)=A+B·m+C·m²，m 为 kg/s；本项仅重放水力关系，不验证缓存温度。',
        'reference':'缓存运行质量流量，非通过调整参数拟合。','source_url':raw['source']},None,lambda frames:[
            check('pump_mass_flow_kg_s',frames[-1].variables['P.mass_flow_kg_s'],v['IM0_FLOW'],relative=1e-4)]


def parallel_reference():
    model=Project.model_validate(load('contracts/reference-project.json'))
    expected=load('contracts/reference-result.json')['variables']
    return model,{'kind':'repository_regression','source':fingerprint('contracts/reference-project.json'),
        'reference_file':fingerprint('contracts/reference-result.json'),
        'scope':'仓库固定泵阀并联模型；已有结果用于回归，不作为外部精度证明。'},None,lambda frames:[
            check(key,frames[-1].variables[key],expected[key],relative=1e-7)
            for key in ('P1.mass_flow_kg_s','V1.mass_flow_kg_s','V2.mass_flow_kg_s','P1.out0.temperature_k')]


def mixed_heat():
    model=assemble('trial-water-glycol-hx',[
        ('BH','source',{'pressure_pa':208486.8,'temperature_k':333.15}),
        ('BC','source',{'pressure_pa':208099.8,'temperature_k':263.15}),('HX','exchanger',{'ua_w_k':2000}),
        ('SH','source',{'pressure_pa':201325,'temperature_k':303.15}),
        ('SC','source',{'pressure_pa':201325,'temperature_k':263.15})],
        [('BH:out0','HX:in0'),('HX:out0','SH:out0'),('BC:out0','HX:in1'),('HX:out1','SC:out0')])
    model.circuit_fluids=[CircuitFluid(id='brine',anchor=Endpoint(instance_id='BC',port_id='out0'),fluid=FluidConfig(fluid='INCOMP::MEG[0.3]'))]
    def checks(frames):
        v=frames[-1].variables
        ch=abs(v['HX.ch0.mass_flow_kg_s'])*WATER.state_pt(208486.8,333.15).specific_heat_j_kg_k
        cc=abs(v['HX.ch1.mass_flow_kg_s'])*property_service(FluidConfig(fluid='INCOMP::MEG[0.3]')).state_pt(208099.8,263.15).specific_heat_j_kg_k
        minimum,maximum=min(ch,cc),max(ch,cc);ratio=minimum/maximum;ntu=2000/minimum
        e=math.exp(-ntu*(1-ratio));effectiveness=(1-e)/(1-ratio*e) if abs(1-ratio)>1e-8 else ntu/(1+ntu)
        heat=effectiveness*minimum*70
        return [check('cold_heat_w',v['HX.ch1.heat_w'],heat,relative=1e-8),
                check('hot_heat_w',v['HX.ch0.heat_w'],-heat,relative=1e-8),
                check('energy_residual_w',frames[-1].metrics['energy_residual_w'],0,absolute=1e-3)]
    return model,{'kind':'analytic_thermal_reference','source':fingerprint('tests/test_multifluid.py'),
        'scope':'水/30% 乙二醇双侧换热；在水力流量下独立计算逆流 ε–NTU 热量，边界比热来自各自工质。'},None,checks


def tank_reference():
    pipe={'length_m':10,'diameter_m':.01,'roughness_m':0}
    model=assemble('trial-tank-dynamics',[('B1','source',{'pressure_pa':111500}),('L1','pipe',pipe),
        ('T','tank',{'area_m2':.01,'height_m':3,'level_m':1}),('L2','pipe',pipe),('B2','source',{'pressure_pa':110500})],
        [('B1:out0','L1:in0'),('L1:out0','T:in0'),('T:out0','L2:in0'),('L2:out0','B2:out0')])
    def checks(frames):
        resistance=128*REFERENCE.viscosity_pa_s*10/(math.pi*.01**4*REFERENCE.density_kg_m3)
        mass=REFERENCE.density_kg_m3*.01
        for _ in range(15):mass=WATER.state_pt(101325+G*mass/.01,293.15).density_kg_m3*.01
        a=(111500+110500-2*101325)/resistance;b=2*G/(.01*resistance)
        result=[check('initial_mass_kg',frames[0].variables['T.state.mass_kg'],mass,relative=1e-8)]
        for i,frame in enumerate(frames[1:],1):
            mass=(mass+.5*a)/(1+.5*b)
            result.append(check(f'mass_at_{i*.5:g}_s',frame.variables['T.state.mass_kg'],mass,relative=1e-7))
        return result
    return model,{'kind':'analytic_dynamic_reference','source':fingerprint('tests/test_states.py'),
        'scope':'层流进出水箱；Hagen–Poiseuille 阻力和隐式 Euler 解析递推，检查全部时间步质量。'},(6.,.5),checks


def python_valve():
    module=load_module_package(ROOT/'modules/programmable_valve')
    model=assemble('trial-python-valve',[('B1','source',{'pressure_pa':250000}),
        ('V','programmable_valve',{'opening_ratio':.5,'kv_m3_h':10}),('B2','source',{'pressure_pa':120000})],
        [('B1:out0','V:in0'),('V:out0','B2:out0')],[module])
    expected=10*.5/36000*math.sqrt(130000*REFERENCE.density_kg_m3)
    return model,{'kind':'analytic_module_reference','source':fingerprint('modules/programmable_valve/module.py'),
        'scope':'已发布 Python 阀门；标准 Kv 关系独立计算流量，并检查接受步数和累计质量。'},(1.,.1),lambda frames:[
            check('mass_flow_kg_s',frames[-1].variables['V.mass_flow_kg_s'],expected,relative=1e-8),
            check('throughput_kg',frames[-1].variables['V.state.throughput_kg'],expected,relative=1e-8),
            check('commit_count',frames[-1].variables['V.state.commit_count'],10,absolute=0)]


def main(output):
    if output.exists():raise ValueError('验收输出目录已存在，请选择新目录以保留证据')
    output.mkdir(parents=True)
    report={'created_at':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),'cases':[],
        'limitations':['仅 1 项外部缓存部件参考，其余 4 项为仓库模型回归或解析验证；不代表 5 个现场项目验收。',
                       'CSLG、WSYRB、NH3CO2ZL 含压缩机、节流/两相、冷风机或库房等未支持模型，未冒充通过。',
                       '离线发行包、干净机器安装和 24 小时终态结果需要另外验收。']}
    for make in (baselu_pump,parallel_reference,mixed_heat,tank_reference,python_valve):
        model,basis,dynamic,verify=make();case=output/model.id;case.mkdir()
        (case/'project.json').write_text(model.model_dump_json(indent=2),encoding='utf-8')
        request=RunRequest(project=model,mode='dynamic' if dynamic else 'steady',
                           duration_s=dynamic[0] if dynamic else 1.,dt_s=dynamic[1] if dynamic else .1)
        (case/'run-request.json').write_text(request.model_dump_json(indent=2),encoding='utf-8')
        entry={'id':model.id,'basis':basis,'status':'failed','checks':[]}
        try:
            network=compile_project(model)
            frames=solve_dynamic(network,*dynamic) if dynamic else [solve_steady(network)]
            entry['checks']=verify(frames)
            entry['checks'].append(check('maximum_mass_residual_kg_s',max(f.metrics['mass_residual_kg_s'] for f in frames),0,absolute=1e-6))
            entry['status']='passed' if all(c['passed'] for c in entry['checks']) and all(f.valid for f in frames) else 'failed'
            entry['frames']=len(frames)
            (case/'frames.json').write_text(json.dumps([f.model_dump(mode='json') for f in frames],ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as error:entry['error']=str(error)
        report['cases'].append(entry);print(json.dumps(entry,ensure_ascii=False),flush=True)
    report['status']='passed' if all(c['status']=='passed' for c in report['cases']) else 'failed'
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 样例试用验收','',f"生成时间：{report['created_at']}",'','| 算例 | 参考类型 | 结果 |','| --- | --- | --- |']
    lines.extend(f"| {c['id']} | {c['basis']['kind']} | {c['status']} |" for c in report['cases'])
    for entry in report['cases']:
        lines+=['',f"## {entry['id']}",'',entry['basis']['scope'],'',
                f"来源：`{entry['basis']['source']['path']}`；SHA-256 `{entry['basis']['source']['sha256']}`。",'',
                '| 检查 | 参考值 | 实测值 | 绝对误差 | 允许误差 |','| --- | --- | --- | --- | --- |']
        lines.extend(f"| {c['name']} | {c['expected']:.10g} | {c['actual']:.10g} | {c['absolute_error']:.3g} | {c['tolerance']:.3g} |" for c in entry['checks'])
        if entry.get('error'):lines+=['',entry['error']]
    lines+=['','## 适用范围','']+[f'- {text}' for text in report['limitations']]
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with zipfile.ZipFile(output.with_suffix('.zip'),'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in output.rglob('*'):
            if path.is_file():archive.write(path,path.relative_to(output))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output.resolve())
