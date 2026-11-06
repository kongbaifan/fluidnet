"""Immutable user-supplied performance curves, explicit units and source provenance."""
import base64
import binascii
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
import math
import sqlite3
import zlib
from threading import RLock
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field, model_validator

from .errors import protected_error_responses
from .models import FluidConfig, ModuleDefinition, StrictModel
from .properties import _parse_fluid
from .storage import StorageError, pack, unpack

MAX_FILE_BYTES = 2 * 1024 * 1024
FLOW_SCALES = {'m3/h': 1., 'm3/s': 3600., 'L/s': 3.6}
VALUE_SCALES = {'m': 1., 'Pa': 1., 'kPa': 1000., '1': 1., '%': .01}


class PerformanceImport(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,79}$')
    name: str = Field(min_length=1, max_length=120)
    kind: Literal['pump_head', 'fan_pressure', 'efficiency']
    format: Literal['csv', 'json']
    file_name: str = Field(default='curve.csv', min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=4 * MAX_FILE_BYTES // 3 + 8)
    flow_unit: Literal['m3/h', 'm3/s', 'L/s']
    value_unit: Literal['m', 'Pa', 'kPa', '1', '%']
    flow_column: str = Field(default='flow', min_length=1, max_length=80)
    value_column: str = Field(default='value', min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=2000)
    manufacturer: str = Field(default='', max_length=200)
    model_name: str = Field(default='', max_length=200)
    reference_fluid: str = Field(default='Water', min_length=1, max_length=200)
    reference_density_kg_m3: float = Field(gt=0, allow_inf_nan=False, strict=True)
    reference_speed_rpm: float = Field(gt=0, allow_inf_nan=False, strict=True)
    valid_flow_min: float | None = Field(default=None, ge=0, allow_inf_nan=False, strict=True)
    valid_flow_max: float | None = Field(default=None, gt=0, allow_inf_nan=False, strict=True)
    expected_latest_version: int = Field(default=0, ge=0, strict=True)

    @model_validator(mode='after')
    def explicit_units(self):
        if self.value_unit not in {'pump_head':{'m'}, 'fan_pressure':{'Pa','kPa'}, 'efficiency':{'1','%'}}[self.kind]:
            raise ValueError('纵轴单位与性能资料类型不匹配')
        if not self.source.strip() or not self.name.strip() or not self.reference_fluid.strip():
            raise ValueError('名称、来源和参考工质必须明确填写')
        if self.flow_column == self.value_column:
            raise ValueError('流量列与数值列必须不同')
        if any(c in self.file_name for c in ('\r','\n','\x00')):
            raise ValueError('文件名不合法')
        _parse_fluid(FluidConfig(fluid=self.reference_fluid))
        return self


class PerformancePreview(StrictModel):
    id: str
    name: str
    kind: str
    source_points: list[list[float]]
    points_m3_h: list[list[float]]
    canonical_value_unit: str
    valid_flow_m3_h: list[float]
    source_hash: str
    content_hash: str
    warnings: list[str]


class PerformanceVersion(PerformancePreview):
    version: int
    created_at: str
    import_data: PerformanceImport


class PerformanceSummary(StrictModel):
    id: str
    name: str
    kind: str
    version: int
    created_at: str
    source: str
    manufacturer: str
    model_name: str
    reference_fluid: str
    reference_density_kg_m3: float
    reference_speed_rpm: float
    source_hash: str
    content_hash: str
    point_count: int
    valid_flow_m3_h: list[float]
    canonical_value_unit: str


class PerformanceList(StrictModel):
    persistent: bool
    items: list[PerformanceSummary]


class PerformanceReference(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,79}$')
    version: int = Field(ge=1, strict=True)
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class PerformanceProposalRequest(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,79}$')
    version: int = Field(ge=1, strict=True)
    module: ModuleDefinition
    parameter_id: str
    fluid: FluidConfig | None = None
    parameters: dict = Field(default_factory=dict)
    references: dict[str, PerformanceReference] = Field(default_factory=dict)


class PerformanceProposal(StrictModel):
    parameters: dict
    provenance: dict
    warnings: list[str]


class PerformanceComparison(StrictModel):
    left: PerformanceVersion
    right: PerformanceVersion
    comparable: bool
    reason: str
    samples: list[dict] = Field(default_factory=list)


def _raw(request):
    try:
        raw = base64.b64decode(request.content_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('文件内容必须是有效base64') from error
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('性能资料文件最多2MiB')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('请先将曲线文件保存为UTF-8编码') from error
    return raw, text


def preview(request: PerformanceImport):
    raw, text = _raw(request)
    if request.format == 'csv':
        rows = list(csv.reader(StringIO(text), strict=True))
        if not rows or len(rows[0]) != 2 or len(set(rows[0])) != 2 or set(rows[0]) != {request.flow_column, request.value_column}:
            raise ValueError('CSV必须只有声明的流量列和数值列，首行为唯一列名')
        if any(h[:1] in '=+-@\t' for h in rows[0]):
            raise ValueError('CSV列名不能是电子表格公式')
        xi, yi = rows[0].index(request.flow_column), rows[0].index(request.value_column)
        if any(len(row) != 2 for row in rows[1:]):
            raise ValueError('CSV每行必须恰有两个值，不忽略空行或额外列')
        points = [[row[xi], row[yi]] for row in rows[1:]]
    else:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:raise ValueError('JSON对象包含重复字段')
                result[key] = value
            return result
        payload = json.loads(text, object_pairs_hook=pairs)
        if isinstance(payload, dict):
            if set(payload) != {'points'}:raise ValueError('JSON对象只接受points字段，元数据在导入表填写')
            points = payload['points']
        else:
            points = payload
    if not isinstance(points, list) or not 2 <= len(points) <= 20000:
        raise ValueError('曲线需要2至20000个点')
    source_points: list[list[float]]=[]
    for row in points:
        if not isinstance(row,(list,tuple)) or len(row)!=2:
            raise ValueError('曲线每点必须为[流量,数值]')
        numbers=[]
        for item in row:
            if isinstance(item,bool) or not isinstance(item,(str,int,float)) or isinstance(item,str) and not item.strip():
                raise ValueError('曲线值必须是有限数值')
            try:number=float(item)
            except (ValueError,OverflowError) as error:raise ValueError('曲线值必须是有限数值，不接受公式') from error
            if not math.isfinite(number):raise ValueError('曲线值必须是有限数值')
            numbers.append(number)
        source_points.append(numbers)
    canonical=[[x*FLOW_SCALES[request.flow_unit],y*VALUE_SCALES[request.value_unit]] for x,y in source_points]
    if any(not math.isfinite(x+y) or x<0 or y<0 or i and x<=canonical[i-1][0] for i,(x,y) in enumerate(canonical)):
        raise ValueError('流量必须非负、严格递增，不允许乱序/重复点；数值必须非负有限')
    if request.kind == 'efficiency' and any(not 0<y<=1 for _,y in canonical):
        raise ValueError('规范效率必须大于0且不超过1')
    low=canonical[0][0] if request.valid_flow_min is None else request.valid_flow_min*FLOW_SCALES[request.flow_unit]
    high=canonical[-1][0] if request.valid_flow_max is None else request.valid_flow_max*FLOW_SCALES[request.flow_unit]
    if not canonical[0][0]<=low<high<=canonical[-1][0]:
        raise ValueError('有效流量区间须位于数据范围内，且下限小于上限')
    data=request.model_dump(mode='json', exclude={'expected_latest_version'})
    content_hash=hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    warnings=['数据来源为用户声明；导入和单位校验不代表厂家标定或现场验证。']
    if request.kind!='efficiency' and any(y>=canonical[i-1][1] for i,(_,y) in enumerate(canonical) if i):
        warnings.append('性能纵轴非严格递减；可保存原始资料，但当前单调选型模块不能直接应用。')
    return PerformancePreview(id=request.id,name=request.name,kind=request.kind,source_points=source_points,
        points_m3_h=canonical,canonical_value_unit={'pump_head':'m','fan_pressure':'Pa','efficiency':'1'}[request.kind],
        valid_flow_m3_h=[low,high],source_hash=hashlib.sha256(raw).hexdigest(),content_hash=content_hash,warnings=warnings)


class PerformanceConflict(ValueError):pass


class PerformanceStore:
    """Stored in the workspace database, so transactional ZIP backups include every version."""
    def __init__(self, archive=None):
        self.archive=archive;self.lock=RLock()
        self.memory=sqlite3.connect(':memory:',check_same_thread=False) if archive is None else None
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS performance_versions(id TEXT NOT NULL,version INTEGER NOT NULL,data BLOB NOT NULL,PRIMARY KEY(id,version))')

    @contextmanager
    def transaction(self):
        if self.archive:
            with self.archive.transaction() as db:yield db
        else:
            with self.lock,self.memory:yield self.memory

    def close(self):
        if self.memory:self.memory.close()

    @staticmethod
    def verified(payload):
        try:
            item=PerformanceVersion.model_validate(unpack(payload));expected=preview(item.import_data)
            if any(getattr(item,key)!=value for key,value in expected.model_dump().items()):
                raise ValueError('原文件、元数据或规范曲线不一致')
            return item
        except (ValueError,TypeError,KeyError,zlib.error,csv.Error) as error:
            raise StorageError('性能资料完整性校验失败：'+str(error)) from error

    def get(self,identifier,version):
        with self.transaction() as db:
            row=db.execute('SELECT data FROM performance_versions WHERE id=? AND version=?',(identifier,version)).fetchone()
        if not row:raise KeyError('性能资料版本不存在')
        item=self.verified(row[0])
        if item.id!=identifier or item.version!=version:raise StorageError('性能资料键与内容不一致')
        return item

    def save(self,request):
        checked=preview(request)
        with self.transaction() as db:
            latest=db.execute('SELECT MAX(version) FROM performance_versions WHERE id=?',(request.id,)).fetchone()[0] or 0
            if latest!=request.expected_latest_version:raise PerformanceConflict('性能资料版本已变化，请刷新后再保存')
            if latest:
                row=db.execute('SELECT data FROM performance_versions WHERE id=? AND version=?',(request.id,latest)).fetchone()
                previous=self.verified(row[0])
                if previous.id!=request.id or previous.version!=latest:raise StorageError('性能资料键与内容不一致')
                if previous.kind!=request.kind:raise ValueError('同一资料ID的类型不能改变，请使用新ID')
            item=PerformanceVersion(**checked.model_dump(),version=latest+1,created_at=datetime.now(timezone.utc).isoformat(),import_data=request)
            db.execute('INSERT INTO performance_versions(id,version,data) VALUES(?,?,?)',(item.id,item.version,pack(item.model_dump(mode='json'))))
        return item

    def catalog(self):
        with self.transaction() as db:rows=db.execute('SELECT id,version,data FROM performance_versions ORDER BY id,version DESC').fetchall()
        result=[]
        for row in rows:
            item=self.verified(row[2]);meta=item.import_data
            if item.id!=row[0] or item.version!=row[1]:raise StorageError('性能资料键与内容不一致')
            result.append(PerformanceSummary(**{key:getattr(item,key) for key in ('id','name','kind','version','created_at','source_hash','content_hash','valid_flow_m3_h','canonical_value_unit')},
                **{key:getattr(meta,key) for key in ('source','manufacturer','model_name','reference_fluid','reference_density_kg_m3','reference_speed_rpm')},point_count=len(item.points_m3_h)))
        return PerformanceList(persistent=self.archive is not None,items=result)


CURVE_RUNTIME_HASHES={
    'design_pump':'c9b76de43ade5c63dddeb6ed0121c629c19fa5a1dbeee736952ce386abe5fefa',
    'design_fan':'540cb733a2cf961a114251a74e8af3f721413b6c7d8567de5a5ca0f9513bfcaf',
    'fan_performance':'fc6869a0e675b71a49106ab062b96d0175b9081e84a4e0e1ae1f2a49f488db15',
    'pump_variable_speed':'a9b7a501b73a8f669ab45efea95d8245381eb6a803c0564b8835ed6258dd13ea',
}


def _target_curve(points,efficiency=False):
    if not isinstance(points,list) or len(points)<2:
        raise ValueError('目标曲线至少需要两个有限数值点')
    for i,p in enumerate(points):
        if not isinstance(p,(list,tuple)) or len(p)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in p):
            raise ValueError('目标曲线每点必须为非负有限数值对')
        x,y=p
        if (i and x<=points[i-1][0]) or (efficiency and not 0<y<=1) or (not efficiency and i and y>=points[i-1][1]):
            raise ValueError('目标效率曲线或性能曲线不满足严格横轴排序及纵轴约束')
    if points[0][0]!=0 or not efficiency and points[-1][1]!=0:
        raise ValueError('目标曲线须从零流量开始，性能曲线须以零扬程/压升结束')


def proposal(request,store):
    item=store.get(request.id,request.version);module=request.module
    target={'pump_head':'head_curve','fan_pressure':'pressure_curve','efficiency':'efficiency_curve'}[item.kind]
    spec=next((p for p in module.parameters if p.id==request.parameter_id),None)
    if request.parameter_id!=target or spec is None or spec.value_type!='curve' or not spec.writable:
        raise ValueError('资料类型与目标可写曲线参数不兼容')
    # These devices declare the reviewed flow-axis and density convention; arbitrary curves lack units in v1 contracts.
    compatible={'pump_head':{'design_pump','pump_variable_speed'},'fan_pressure':{'design_fan','fan_performance'},'efficiency':{'design_pump','design_fan','fan_performance'}}
    if module.id not in compatible[item.kind]:raise ValueError('该模块尚未声明支持本资料的曲线单位约定')
    runtime=module.source.get('runtime','')
    if not isinstance(runtime,str) or hashlib.sha256(runtime.encode()).hexdigest()!=CURVE_RUNTIME_HASHES.get(module.id):
        raise ValueError('目标模块算法不是已核对的曲线单位合同，不能只凭同名参数自动转换')
    from .compiler import validated_parameters
    from .models import ModuleInstance
    points=item.points_m3_h
    current=validated_parameters(ModuleInstance(id='CurveTarget',module_id=module.id,name='curve target',parameters=request.parameters|{target:points}),module)
    if item.valid_flow_m3_h!=[points[0][0],points[-1][0]]:
        raise ValueError('目标模块不能表达比数据更窄的有效区间，请先提供仅含有效范围的适用曲线')
    if item.kind!='efficiency' and (points[0][0]!=0 or points[-1][1]!=0 or any(y>=points[i-1][1] for i,(_,y) in enumerate(points) if i)):
        raise ValueError('当前选型要求性能图从零流量至零扬程/压升，纵轴严格递减，不做外推或多解推断')
    if request.fluid and _parse_fluid(request.fluid)!=_parse_fluid(FluidConfig(fluid=item.import_data.reference_fluid)):
        raise ValueError('资料参考工质与设备设计工质不同，请明确转换后再应用')
    if module.id=='fan_performance' and item.kind=='fan_pressure':
        raise ValueError('此风机未声明资料参考密度修正参数，请使用design_fan或先做明确密度转换')
    proposed=current|{target:points}
    for key in ('head_curve','pressure_curve','efficiency_curve'):
        if key in proposed:_target_curve(proposed[key],efficiency=key=='efficiency_curve')
    other_target='efficiency_curve' if target!='efficiency_curve' else 'head_curve' if 'head_curve' in current else 'pressure_curve'
    other_ref=request.references.get(other_target)
    if other_ref:
        try:
            companion=store.get(other_ref.id,other_ref.version)
        except (KeyError,TypeError) as error:raise ValueError('配套性能资料引用已失效，请重新选择') from error
        if other_ref.content_hash!=companion.content_hash:raise ValueError('配套性能资料版本哈希不一致')
        companion_target={'pump_head':'head_curve','fan_pressure':'pressure_curve','efficiency':'efficiency_curve'}[companion.kind]
        if companion_target!=other_target or current.get(other_target)!=companion.points_m3_h:
            raise ValueError('配套资料引用与当前草稿曲线不一致，请重新预览应用后再引用')
        if (_parse_fluid(FluidConfig(fluid=companion.import_data.reference_fluid))!=_parse_fluid(FluidConfig(fluid=item.import_data.reference_fluid))
            or companion.import_data.reference_speed_rpm!=item.import_data.reference_speed_rpm
            or companion.import_data.reference_density_kg_m3!=item.import_data.reference_density_kg_m3):
            raise ValueError('配套性能与效率资料的参考工质、密度或转速不一致；请先选用同基准资料')
    if 'efficiency_curve' in proposed:
        efficiency=proposed['efficiency_curve'];performance=proposed.get('head_curve',proposed.get('pressure_curve'))
        if not efficiency or efficiency[0][0]!=0 or efficiency[-1][0]<performance[-1][0]:
            raise ValueError('效率曲线必须从零流量覆盖性能曲线全范围；请先应用覆盖更广的效率资料')
        if any(x<0 or not 0<y<=1 or i and x<=efficiency[i-1][0] for i,(x,y) in enumerate(efficiency)):
            raise ValueError('目标效率曲线不合法')
    parameters={target:points}
    declared={p.id for p in module.parameters}
    if 'data_source' in declared:parameters['data_source']=item.import_data.source
    if 'design_fluid_note' in declared:parameters['design_fluid_note']=f'{item.import_data.reference_fluid}; reference {item.import_data.reference_speed_rpm:g} rpm'
    if item.kind=='fan_pressure' and 'reference_density_kg_m3' in declared:parameters['reference_density_kg_m3']=item.import_data.reference_density_kg_m3
    provenance={'id':item.id,'version':item.version,'name':item.name,'kind':item.kind,'parameter_id':target,
        'source_hash':item.source_hash,'content_hash':item.content_hash,'source':item.import_data.source,
        'manufacturer':item.import_data.manufacturer,'model_name':item.import_data.model_name,
        'reference_fluid':item.import_data.reference_fluid,'reference_density_kg_m3':item.import_data.reference_density_kg_m3,
        'reference_speed_rpm':item.import_data.reference_speed_rpm,'valid_flow_m3_h':item.valid_flow_m3_h,
        'canonical_value_unit':item.canonical_value_unit,'points_m3_h':points}
    return PerformanceProposal(parameters=parameters,provenance=provenance,warnings=item.warnings+[
        '资料的参考转速定义speed_ratio=1；数据替换仅进入草稿，须重新选型并核对配套效率曲线覆盖范围。'])


def compare(left,right):
    a,b=left.import_data,right.import_data
    comparable=(left.kind==right.kind and left.canonical_value_unit==right.canonical_value_unit
        and _parse_fluid(FluidConfig(fluid=a.reference_fluid))==_parse_fluid(FluidConfig(fluid=b.reference_fluid))
        and a.reference_density_kg_m3==b.reference_density_kg_m3 and a.reference_speed_rpm==b.reference_speed_rpm)
    low=max(left.valid_flow_m3_h[0],right.valid_flow_m3_h[0]);high=min(left.valid_flow_m3_h[1],right.valid_flow_m3_h[1])
    comparable=comparable and low<high
    reason='同类型/工质/密度/转速；只在共同有效区间作分段线性插值对照，不外推' if comparable else '类型、参考条件或有效范围不一致，只并列查看原资料，不计算差值'
    samples=[]
    if comparable:
        def interpolate(points,x):
            for (x0,y0),(x1,y1) in zip(points,points[1:]):
                if x==x0:return y0
                if x==x1:return y1
                if x0<=x<=x1:return y0+(y1-y0)*(x-x0)/(x1-x0)
            raise ValueError('比较点超出资料范围')
        grid=sorted({low,high,*[p[0] for p in left.points_m3_h+right.points_m3_h if low<=p[0]<=high]})
        for x in grid:
            av,bv=interpolate(left.points_m3_h,x),interpolate(right.points_m3_h,x)
            samples.append({'flow_m3_h':x,'left':av,'right':bv,'difference':bv-av,'value_unit':left.canonical_value_unit})
    return PerformanceComparison(left=left,right=right,comparable=comparable,reason=reason,samples=samples)


def performance_router(store):
    router=APIRouter(prefix='/api/v1/performance-data',tags=['performance-data'])
    def guarded(fn,*args):
        try:return fn(*args)
        except PerformanceConflict as error:raise HTTPException(409,detail={'code':'PERFORMANCE_VERSION_CONFLICT','message':str(error)}) from error
        except KeyError as error:raise HTTPException(404,detail={'code':'PERFORMANCE_NOT_FOUND','message':str(error)}) from error
        except (ValueError,csv.Error) as error:raise HTTPException(422,detail={'code':'PERFORMANCE_INVALID','message':str(error)}) from error
    @router.get('',response_model=PerformanceList,responses=protected_error_responses('STORAGE_FAILED'))
    def listing():return guarded(store.catalog)
    @router.post('/preview',response_model=PerformancePreview,responses=protected_error_responses('PERFORMANCE_INVALID'))
    def preview_file(request:PerformanceImport):return guarded(preview,request)
    @router.post('/versions',response_model=PerformanceVersion,status_code=201,responses=protected_error_responses('PERFORMANCE_VERSION_CONFLICT','PERFORMANCE_INVALID','STORAGE_FAILED'))
    def save(request:PerformanceImport):return guarded(store.save,request)
    @router.post('/proposal',response_model=PerformanceProposal,responses=protected_error_responses('PERFORMANCE_NOT_FOUND','PERFORMANCE_INVALID','STORAGE_FAILED'))
    def propose(request:PerformanceProposalRequest):return guarded(proposal,request,store)
    @router.get('/compare',response_model=PerformanceComparison,responses=protected_error_responses('PERFORMANCE_NOT_FOUND','PERFORMANCE_INVALID','STORAGE_FAILED'))
    def compare_versions(left_id:str,left_version:int,right_id:str,right_version:int):
        return guarded(compare,guarded(store.get,left_id,left_version),guarded(store.get,right_id,right_version))
    @router.get('/{identifier}/versions/{version}',response_model=PerformanceVersion,responses=protected_error_responses('PERFORMANCE_NOT_FOUND','STORAGE_FAILED'))
    def get(identifier:str,version:int):return guarded(store.get,identifier,version)
    @router.get('/{identifier}/versions/{version}/export',response_class=Response,responses={
        200:{'description':'原始性能资料文件，按导入格式逐字节下载', 'content':{
            'text/csv':{'schema':{'type':'string','format':'binary'}},
            'application/json':{'schema':{'type':'string','format':'binary'}}}},
        **protected_error_responses('PERFORMANCE_NOT_FOUND','STORAGE_FAILED')})
    def export(identifier:str,version:int):
        item=guarded(store.get,identifier,version);raw,_=_raw(item.import_data)
        return Response(raw,media_type='text/csv; charset=utf-8' if item.import_data.format=='csv' else 'application/json',
            headers={'Content-Disposition':f'attachment; filename="{item.id}-v{item.version}.{item.import_data.format}"'})
    return router
