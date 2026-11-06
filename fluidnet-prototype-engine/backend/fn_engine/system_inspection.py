"""Read-only project checks and frozen run explanations; no report-time device execution."""
import math
import hashlib
from collections import defaultdict
from typing import Any

from pydantic import Field

from .models import Diagnostic, Project, StrictModel


class InspectionValue(StrictModel):
    key: str
    label: str
    value: float | None = None
    unit: str = ''
    source: str
    status: str = 'observed'


class InspectionDevice(StrictModel):
    instance_id: str
    module_id: str
    name: str
    version: int
    assumptions: list[str] = Field(default_factory=list)
    values: list[InspectionValue] = Field(default_factory=list)
    curves: list[dict[str, Any]] = Field(default_factory=list)


class SystemInspection(StrictModel):
    project_id: str
    run_id: str | None = None
    status: str
    time_s: float | None = None
    valid: bool
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    circuits: list[dict[str, Any]] = Field(default_factory=list)
    devices: list[InspectionDevice] = Field(default_factory=list)
    balances: list[InspectionValue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InspectionComparison(StrictModel):
    left_run_id: str
    right_run_id: str
    same_project: bool
    differences: list[dict[str,Any]]
    notes: list[str]


def compare_runs(left,right):
    a,b=run_inspection(left),run_inspection(right)
    def rows(r):return {v.key:v for d in r.devices for v in d.values}|{v.key:v for v in r.balances}
    ar,br=rows(a),rows(b);differences=[]
    for key in sorted(ar.keys()|br.keys()):
        x,y=ar.get(key),br.get(key)
        comparable=x is not None and y is not None and x.unit==y.unit and x.value is not None and y.value is not None
        differences.append({'key':key,'label':(x or y).label,'unit':x.unit if x else y.unit,
            'left':x.value if x else None,'right':y.value if y else None,
            'difference':y.value-x.value if comparable else None,
            'reason':None if comparable else '采样或单位不一致，不计算差值'})
    return InspectionComparison(left_run_id=left['id'],right_run_id=right['id'],same_project=a.project_id==b.project_id,
        differences=differences,notes=['差值为右侧末帧减左侧末帧；不假设两个运行具有相同边界/时长或模型版本。',
        '仅按相同实例变量键与规范单位对齐，未知值不补零；性能因果须结合两份冻结输入判断。'])


def project_check(project: Project):
    from .compiler import validate_project_details
    definitions = {m.id: m for m in project.modules}
    instances = {n.id: n for n in project.instances}
    connected: dict[tuple[str,str],int] = defaultdict(int)
    issues = []
    for c in project.connections:
        for endpoint in (c.source, c.target):
            connected[(endpoint.instance_id, endpoint.port_id)] += 1
    for node in project.instances:
        definition = definitions.get(node.module_id)
        if definition is None:
            issues.append(Diagnostic(code='INSPECT_MODULE_MISSING', message='设备缺少冻结模块定义',instance_id=node.id))
            continue
        for port in definition.ports:
            count = connected[(node.id, port.id)]
            if port.required and count == 0:
                issues.append(Diagnostic(code='INSPECT_PORT_OPEN',message=f'{port.label}（{port.id}）为必接端口，尚未连接',instance_id=node.id,field=port.id))
            if count > 1:
                issues.append(Diagnostic(code='INSPECT_PORT_REUSED',message=f'端口 {port.id} 被多次连接，请使用节点或分集设备',instance_id=node.id,field=port.id))
    for edge in project.connections:
        for e in (edge.source, edge.target):
            n=instances.get(e.instance_id)
            if n is None or n.module_id not in definitions or e.port_id not in {p.id for p in definitions[n.module_id].ports}:
                issues.append(Diagnostic(code='INSPECT_ENDPOINT_MISSING',message=f'连接 {edge.id} 引用了失效端点',instance_id=e.instance_id,field=e.port_id))
    # Keep compiler's domain, pressure, phase, parameter, schedule and version checks authoritative.
    diagnostics,circuits = validate_project_details(project)
    keys={(d.code,d.instance_id,d.field) for d in issues}
    issues.extend(d for d in diagnostics if (d.code,d.instance_id,d.field) not in keys)
    return SystemInspection(project_id=project.id,status='preflight',valid=not any(d.severity=='error' for d in issues),
        diagnostics=issues,circuits=circuits,notes=['预检检查连接与合同，不运行设备代码，也不保证运行中一定收敛。'])


METRICS = {
    'pressure_residual_pa':('最大压力方程残差','Pa'), 'mass_residual_kg_s':('最大质量方程残差','kg/s'),
    'energy_residual_w':('能量方程残差','W'), 'energy_residual_j':('累计能量残差','J'),
    'moisture_residual_kg_s':('水分方程残差','kg/s'), 'dry_air_mass_residual_kg_s':('干空气质量残差','kg_da/s'),
    'liquid_mass_residual_kg_s':('液体质量残差','kg/s'), 'storage_power_w':('储能变化率','W'),
}
PORT_UNITS={'pressure_pa':('绝压','Pa'),'temperature_k':('温度','K'), 'mass_flow_kg_s':('质量流量','kg/s'),
    'enthalpy_j_kg':('比焓','J/kg'),'density_kg_m3':('密度','kg/m3')}
# Only these reviewed runtime algorithms have the similarity/units used in our plot.
# A new user release with the same module ID must not inherit an assumed curve law.
CURVE_RUNTIME_HASHES={
    'design_pump':'c9b76de43ade5c63dddeb6ed0121c629c19fa5a1dbeee736952ce386abe5fefa',
    'design_fan':'540cb733a2cf961a114251a74e8af3f721413b6c7d8567de5a5ca0f9513bfcaf',
    'fan_performance':'fc6869a0e675b71a49106ab062b96d0175b9081e84a4e0e1ae1f2a49f488db15',
}


def finite(value):
    return float(value) if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) else None


def frozen_circuits(project):
    """Connectivity by declared port circuits, independent of pressure levels and current catalogs."""
    if any(m.get('composite') for m in project['modules']):
        from .composites import expand_composites
        try:
            project=expand_composites(Project.model_validate(project))[0].model_dump(mode='json')
        except ValueError:
            return []  # A failed frozen definition may be unexpandable; do not invent connectivity.
    parent={}
    def root(key):
        parent.setdefault(key,key)
        while parent[key]!=key:
            parent[key]=parent[parent[key]];key=parent[key]
        return key
    def join(a,b):parent[root(b)]=root(a)
    definitions={m['id']:m for m in project['modules']}
    for n in project['instances']:
        groups=defaultdict(list)
        for p in definitions[n['module_id']]['ports']:
            if p.get('domain','fluid') not in {'fluid','refrigerant'}:continue
            key=n['id']+':'+p['id'];root(key);groups[(p.get('domain','fluid'),p.get('circuit','fluid'))].append(key)
        for group in groups.values():
            for key in group[1:]:join(group[0],key)
    for c in project['connections']:
        a=c['source']['instance_id']+':'+c['source']['port_id'];b=c['target']['instance_id']+':'+c['target']['port_id']
        if a in parent and b in parent:join(a,b)
    groups=defaultdict(list)
    for key in parent:groups[root(key)].append(key)
    result=[]
    for i,ports in enumerate(sorted(groups.values())):
        selected=[c for c in project.get('circuit_fluids',[]) if c['anchor']['instance_id']+':'+c['anchor']['port_id'] in ports]
        result.append({'id':f'circuit-{i+1}','ports':sorted(ports),'instance_ids':sorted({p.split(':')[0] for p in ports}),
            'fluid': selected[0]['fluid'] if selected else project['fluid'], 'source':selected[0]['id'] if selected else 'project',
            'basis':'冻结端口回路声明与连接；不等于压力等级或当前流向'})
    return result


def run_inspection(record):
    project=record['request']['project'];frame=record.get('frame') or {};raw=frame.get('variables',{});metrics=frame.get('metrics',{})
    definitions={m['id']:m for m in project['modules']}
    diagnostics=[Diagnostic.model_validate(d) for d in frame.get('diagnostics',[])]
    balances=[]
    for key,(label,unit) in METRICS.items():
        v=finite(metrics.get(key));source='metrics.'+key
        if v is None and finite(raw.get(source)) is not None:v=finite(raw[source])
        if v is not None:balances.append(InspectionValue(key=source,label=label,value=v,unit=unit,source='求解器该帧账本'))
    for key,v in metrics.items():
        if key.startswith('mass_residual_kg_circuit'):
            balances.append(InspectionValue(key='metrics.'+key,label='制冷回路质量库存残差',value=finite(v),unit='kg',source='求解器该帧账本'))
    devices=[]
    for n in project['instances']:
        d=definitions[n['module_id']];iid=n['id'];specs={v['id']:v for v in d.get('variables',[])}
        for p in d['ports']:
            for suffix,(label,unit) in PORT_UNITS.items():
                key=p['id']+'.'+suffix
                specs.setdefault(key,{'label':p['label']+' · '+label,'unit':{'canonical_unit':unit}})
        # Fields explicitly produced by core channels; avoid counting the single-channel alias twice.
        for c in d.get('channels',[]):
            if not c.get('enabled',True):continue
            for key,label,unit in [('mass_flow_kg_s','质量流量','kg/s'),('heat_w','进入流体热量','W'),('shaft_power_w','进入流体轴功','W'),('pressure_drop_pa','压降','Pa')]:
                specs.setdefault(c['id']+'.'+key,{'label':c['name']+' · '+label,'unit':{'canonical_unit':unit}})
        values=[]
        for key,spec in specs.items():
            full=iid+'.'+key;unit=spec.get('unit') or {};v=finite(raw.get(full))
            if v is not None or unit.get('quantity') in {'power','energy'}:
                values.append(InspectionValue(key=full,label=spec.get('label',key),value=v,unit=unit.get('canonical_unit',''),
                    source='冻结变量合同/该帧采样',status='observed' if v is not None else 'missing'))
        params={p['id']:p.get('default') for p in d.get('parameters',[])}|n.get('parameters',{})
        for key in list(params):
            if iid+'.param.'+key in raw:params[key]=raw[iid+'.param.'+key]
        curves=[]
        for key in ('pressure_curve','head_curve'):
            points=params.get(key)
            if isinstance(points,list):
                q=finite(raw.get(iid+'.volume_flow_m3_h'));head=finite(raw.get(iid+'.head_m'))
                if q is None:
                    for c in d.get('channels',[]):
                        q=finite(raw.get(iid+'.'+c['id']+'.volume_flow_m3_h'))
                        if q is not None:break
                rise=finite(raw.get(iid+'.pressure_rise_pa'))
                source=d.get('source',{}).get('runtime','')
                known=isinstance(source,str) and hashlib.sha256(source.encode()).hexdigest()==CURVE_RUNTIME_HASHES.get(d['id'])
                density=finite(raw.get(iid+'.in0.density_kg_m3'))
                mass=finite(raw.get(iid+'.mass_flow_kg_s'))
                if mass is None:
                    mass=next((finite(raw.get(iid+'.'+c['id']+'.mass_flow_kg_s')) for c in d.get('channels',[]) if finite(raw.get(iid+'.'+c['id']+'.mass_flow_kg_s')) is not None),None)
                if known and density and mass is not None:q=mass/density*3600.
                speed=finite(params.get('speed_ratio'))
                scale=(density/params['reference_density_kg_m3'] if d['id']=='design_fan' and density and params.get('reference_density_kg_m3') else 1.)
                projected=[[x*speed,y*speed**2*scale] for x,y in points] if known and speed is not None and params.get('running',1)>=.5 else None
                curves.append({'key':key,'points':points,'speed_ratio':params.get('speed_ratio',1),
                    'volume_flow_m3_h':q,'head_m':head,'pressure_rise_pa':rise,
                    'working_curve':projected,'ordinate_unit':'m' if key=='head_curve' else 'Pa' if known else None,
                    'working_ordinate':head if key=='head_curve' else rise,
                    'note':'冻结参考曲线；仅已核对源码且运行中的模块按转速/密度投影，流量按入口密度取值。停机或改写算法仅列参考点。'})
        for threshold,key,label in [('max_pressure_ratio','pressure_ratio','压比'),('maximum_outlet_temperature_k','out0.temperature_k','出水温度')]:
            limit=finite(params.get(threshold));v=finite(raw.get(iid+'.'+key))
            if limit is not None and v is not None and v>limit:
                diagnostics.append(Diagnostic(code='INSPECT_LIMIT_EXCEEDED',severity='warning',instance_id=iid,field=threshold,message=f'{label} {v:g} 超过本次设置上限 {limit:g}'))
        devices.append(InspectionDevice(instance_id=iid,module_id=d['id'],name=n.get('name',iid),version=d.get('version',1),
            assumptions=[d.get('description',''),*(d.get('applicability') or {}).get('assumptions',[])],values=values,curves=curves))
    return SystemInspection(project_id=project['id'],run_id=record['id'],status=record['status'],time_s=frame.get('time_s'),
        valid=bool(frame.get('valid')),diagnostics=diagnostics,circuits=frozen_circuits(project),devices=devices,balances=balances,
        notes=['只读取本次运行的冻结定义与末帧，未重编译或执行设备。',
            '不同设备的轴功、电功、传热和储能可能描述同一能量路径，因此逐设备展示，不盲目求和。',
            '缺失/未声明量保持未知；失败运行的末帧可能是最后接受点，失败回调输入通过单独入口查看。'])
