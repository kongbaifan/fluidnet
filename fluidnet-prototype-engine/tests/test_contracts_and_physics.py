import math
from copy import deepcopy
from pathlib import Path
import importlib.util
import json
import re
import subprocess
import sys

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from fn_engine import errors
from fn_engine.api import RUN_NOT_FOUND, create_app
from fn_engine.auth import AuthConfig, TokenStore
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project, CompilationError
from fn_engine.models import Connection, Endpoint, ModuleInstance, Project
from fn_engine.solver import solve_steady, pipe_drop, RHO_WATER, MU_WATER
from fn_engine.bridge import normalize_prototype_export


def simple(kind='valve',params=None, inlet=250000.,outlet=120000.):
    definitions = catalog_map()
    return Project(id='simple',name='two boundaries',modules=[definitions['source'],definitions[kind]],instances=[
        ModuleInstance(id='B1',module_id='source',name='in',parameters={'pressure_pa':inlet}),
        ModuleInstance(id='D1',module_id=kind,name='device',parameters=params or {}),
        ModuleInstance(id='B2',module_id='source',name='out',parameters={'pressure_pa':outlet})], connections=[
        Connection(id='e1',source=Endpoint(instance_id='B1',port_id='out0'),target=Endpoint(instance_id='D1',port_id='in0')),
        Connection(id='e2',source=Endpoint(instance_id='D1',port_id='out0'),target=Endpoint(instance_id='B2',port_id='out0'))])


def test_unit_roundtrips():
    catalog=catalog_map()
    for kind,key,canonical,display in [('valve','opening_ratio',.65,65),('pipe','diameter_m',.04,40),
        ('source','temperature_k',293.15,20),('source','pressure_pa',201325,201.325)]:
        unit=next(p.unit for p in catalog[kind].parameters if p.id==key)
        assert unit.from_canonical(canonical)==pytest.approx(display)
        assert unit.to_canonical(display)==pytest.approx(canonical)


@pytest.mark.parametrize('drop',[100000.,-100000.])
def test_kv_analytic_solution_and_flow_sign(drop):
    frame=solve_steady(compile_project(simple(params={'opening_ratio':.5,'kv_m3_h':10},inlet=200000+drop,outlet=200000)))
    expected=math.copysign(5*math.sqrt(abs(drop)/100000/(RHO_WATER/1000))*RHO_WATER/3600,drop)
    assert frame.variables['D1.mass_flow_kg_s']==pytest.approx(expected,rel=1e-7)
    assert frame.variables['D1.in0.mass_flow_kg_s']==pytest.approx(expected)
    assert frame.variables['D1.out0.mass_flow_kg_s']==pytest.approx(-expected)
    assert frame.variables['B1.out0.mass_flow_kg_s']==pytest.approx(-expected)
    # The throttled stream keeps its enthalpy, so it stays at the 20 °C boundary temperature.
    assert frame.variables['D1.out0.temperature_k']==pytest.approx(293.15,abs=.05)
    assert frame.variables['D1.out0.enthalpy_j_kg']==pytest.approx(frame.variables['D1.in0.enthalpy_j_kg'],rel=1e-12)


def test_closed_valve_is_exact_no_flow():
    frame=solve_steady(compile_project(simple(params={'opening_ratio':0})))
    assert abs(frame.variables['D1.mass_flow_kg_s'])<1e-10


def test_pipe_poiseuille_and_roughness():
    params={'length_m':12.,'diameter_m':.04,'roughness_m':0.}
    mass=.0001
    expected=128*MU_WATER*params['length_m']*(mass/RHO_WATER)/(math.pi*params['diameter_m']**4)
    assert pipe_drop(params,mass)==pytest.approx(expected,rel=1e-12)
    assert pipe_drop(params,-mass)==pytest.approx(-expected)
    assert pipe_drop(params|{'roughness_m':.0005},2.)>pipe_drop(params,2.)


@pytest.mark.parametrize('params',[{'opening_ratio':-1},{'opening_ratio':2},{'kv_m3_h':0},{'kv_m3_h':float('nan')},{'typo':1}])
def test_bad_parameters_rejected(params):
    with pytest.raises(CompilationError): compile_project(simple(params=params))


def test_pressure_conflict_rejected():
    p=simple()
    p.instances=p.instances[:1]+p.instances[2:]
    p.connections=[Connection(id='e',source=Endpoint(instance_id='B1',port_id='out0'),target=Endpoint(instance_id='B2',port_id='out0'))]
    with pytest.raises(CompilationError,match='冲突'):compile_project(p)


def test_isolated_loop_rejected_even_if_other_component_has_boundary():
    p=simple()
    p.instances += [ModuleInstance(id=x,module_id='valve',name=x) for x in ('V2','V3')]
    p.connections += [Connection(id='loop1',source=Endpoint(instance_id='V2',port_id='out0'),target=Endpoint(instance_id='V3',port_id='in0')),
                      Connection(id='loop2',source=Endpoint(instance_id='V3',port_id='out0'),target=Endpoint(instance_id='V2',port_id='in0'))]
    with pytest.raises(CompilationError,match='缺少压力边界'):compile_project(p)


def test_unknown_algorithm_and_state_model_are_rejected():
    p=simple();p.modules[-1].channels[0].solver_model='unknown'
    with pytest.raises(CompilationError,match='未注册'):compile_project(p)
    p=simple('tank');p.modules[-1].state_model='closed_gas_cushion'
    with pytest.raises(CompilationError,match='尚未实现'):compile_project(p)
    p=simple('valve');p.modules[-1].state_model='well_mixed_volume'
    with pytest.raises(CompilationError,match='尚未实现'):compile_project(p)


def test_iteration_exhaustion_is_not_valid_result():
    p=simple();p.solver.max_iterations=1
    with pytest.raises(ValueError,match='未收敛'):solve_steady(compile_project(p))


def test_run_api_and_failure_contract():
    client=TestClient(create_app())
    assert client.get('/api/v1/health').json()['capabilities']['steady_hydraulics']
    p=simple().model_dump(mode='json')
    r=client.post('/api/v1/runs',json={'project':p,'mode':'dynamic','duration_s':.25,'dt_s':.1})
    assert r.status_code==201,r.text
    data=r.json();assert data['status']=='completed'
    history=client.get('/api/v1/runs/'+data['run_id']+'/history').json()
    assert [f['time_s'] for f in history['rows']]==pytest.approx([0,.1,.2,.25])
    assert any(d['code']=='DYNAMIC_QUASI_STEADY' for d in history['rows'][0]['diagnostics'])
    assert history['rows'][0]['variables']==history['rows'][-1]['variables']
    assert client.get('/api/v1/runs/'+data['run_id']+'/history?offset=1&limit=1').json()['total_rows']==4
    p['instances'][1]['parameters']={'opening_ratio':2}
    failed=client.post('/api/v1/runs',json={'project':p}).json()
    assert failed['status']=='failed'
    assert failed['frame']['valid'] is False
    assert failed['frame']['diagnostics'][0]['code']=='PARAMETER_RANGE'
    assert client.post('/api/v1/solve',json=p).status_code==422
    assert client.get('/api/v1/runs/missing').status_code==404


def test_selection_and_scenario():
    client=TestClient(create_app());p=simple().model_dump(mode='json')
    p['scenarios']=[{'id':'closed','name':'Closed','overrides':{'D1':{'opening_ratio':0}}}]
    data=client.post('/api/v1/runs',json={'project':p,'scenario_id':'closed','selected_variables':['D1.mass_flow_kg_s']}).json()
    assert data['status']=='completed'
    assert data['frame']['variables']==pytest.approx({'D1.mass_flow_kg_s':0},abs=1e-9)
    assert client.post('/api/v1/runs',json={'project':p,'selected_variables':['wrong']}).json()['status']=='failed'
    assert client.post('/api/v1/runs',json={'project':p,'mode':'dynamic','duration_s':9999,'dt_s':.001}).status_code==422


def prototype():
    return json.loads((Path(__file__).parent/'fixtures'/'prototype.json').read_text(encoding='utf-8'))


def test_real_prototype_and_parameter_response():
    raw=prototype();p=normalize_prototype_export(raw)
    frame=solve_steady(compile_project(p))
    q,a,b=[frame.variables[f'{id}.mass_flow_kg_s'] for id in ['P1','V1','V2']]
    assert q==pytest.approx(a+b,abs=1e-8)
    assert frame.metrics['mass_residual_kg_s']<p.solver.mass_tolerance_kg_s
    next(n for n in p.instances if n.id=='V1').parameters['opening_ratio']=.4
    modified=solve_steady(compile_project(p))
    assert modified.variables['V1.mass_flow_kg_s']<a
    assert modified.variables['V2.mass_flow_kg_s']>b


def test_exchanger_sides_have_separate_outputs():
    raw=prototype();raw['activeProject']='heat-loop'
    p=normalize_prototype_export(raw);frame=solve_steady(compile_project(p))
    assert frame.variables['HX1.ch0.mass_flow_kg_s']>0
    assert frame.variables['HX1.ch1.mass_flow_kg_s']>0
    assert 'HX1.mass_flow_kg_s' not in frame.variables
    # ch0 carries the 65 °C side, ch1 the 25 °C side: the hot side cools, the cold side warms by the same duty.
    v=frame.variables
    assert v['HX1.ch0.outlet_temperature_k']<v['HX1.ch0.inlet_temperature_k']
    assert v['HX1.ch1.outlet_temperature_k']>v['HX1.ch1.inlet_temperature_k']
    assert v['HX1.ch0.heat_w']==pytest.approx(-v['HX1.ch1.heat_w'],rel=1e-9)
    assert not any(d.code=='THERMAL_NOT_SOLVED' for d in frame.diagnostics)
    p.solver.thermal=False
    assert any(d.code=='THERMAL_NOT_SOLVED' for d in solve_steady(compile_project(p)).diagnostics)


def test_prototype_mutations_are_not_silently_ignored():
    raw=prototype()
    next(m for m in raw['modules'] if m['id']=='valve')['channels'][0]['enabled']=False
    with pytest.raises(CompilationError,match='通路'):compile_project(normalize_prototype_export(raw))
    # Known media (water, air, ammonia, ...) map to a CoolProp fluid since v0.3.1; unknown ones still fail.
    raw=prototype();raw['projects'][0]['medium']='steam-table-x'
    with pytest.raises(ValueError,match='介质'):normalize_prototype_export(raw)
    raw=prototype();raw['activeProject']='missing'
    with pytest.raises(ValueError,match='activeProject'):normalize_prototype_export(raw)

def test_catalog_variables_match_reference_frame():
    from fn_engine.solver import THERMAL_ONLY_SUFFIXES
    p=normalize_prototype_export(prototype())
    frame=solve_steady(compile_project(p))
    modules={m.id:m for m in p.modules}
    # Pipe state variables are conditional: they exist only when the pipe has thermal_cells > 0.
    declared={f'{i.id}.{v.id}' for i in p.instances for v in modules[i.module_id].variables
              if not (modules[i.module_id].solver_model=='pipe' and v.source=='state' and not i.parameters.get('thermal_cells'))}
    assert set(frame.variables)==declared
    # thermal off: exactly the declared variables minus the thermal-only ones (pre-0.3 key set).
    p.solver.thermal=False
    frame=solve_steady(compile_project(p))
    assert set(frame.variables)=={k for k in declared if not k.endswith(THERMAL_ONLY_SUFFIXES)}


ROOT=Path(__file__).parents[1]
CONTRACTS=ROOT/'contracts'


def contract_generator():
    """按路径加载生成脚本，避免依赖 scripts/ 是包，也避免导入即写文件。"""
    spec=importlib.util.spec_from_file_location('fn_generate_contracts',ROOT/'scripts'/'generate_contracts.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_semantic_match(expected,actual,path='$'):
    """双向语义比较：键集双向一致、长度一致、值是同一 JSON 语义（浮点按 1e-9 相对误差，近零值按 1e-9 绝对误差）。"""
    if isinstance(expected,dict) and isinstance(actual,dict):
        assert set(expected)==set(actual),f'{path} 键集不一致：缺 {sorted(set(expected)-set(actual))}，多 {sorted(set(actual)-set(expected))}'
        for key in expected:assert_semantic_match(expected[key],actual[key],f'{path}.{key}')
    elif isinstance(expected,list) and isinstance(actual,list):
        assert len(expected)==len(actual),f'{path} 长度不一致：{len(expected)} != {len(actual)}'
        for index,(left,right) in enumerate(zip(expected,actual)):assert_semantic_match(left,right,f'{path}[{index}]')
    elif isinstance(expected,bool) or isinstance(actual,bool):
        assert expected is actual,f'{path}: {expected!r} != {actual!r}'
    elif isinstance(expected,(int,float)) and isinstance(actual,(int,float)):
        assert expected==pytest.approx(actual,rel=1e-9,abs=1e-9),f'{path}: {expected!r} != {actual!r}'
    else:assert type(expected) is type(actual) and expected==actual,f'{path}: {expected!r} != {actual!r}'


def test_generated_contracts_are_current():
    generator=contract_generator()
    expected=generator.contract_files()
    # 名单来自生成脚本本身：全部 schema（含 4 个历史遗漏的）与 openapi、两个参考文件都要覆盖。
    assert {name+'.schema.json' for name,_ in generator.models}<=set(expected)
    assert {'openapi.json','reference-project.json','reference-result.json'}<=set(expected)
    assert len(expected)==len(generator.models)+3
    on_disk={path.name for path in CONTRACTS.glob('*.json')}
    assert on_disk==set(expected),f'契约文件集合漂移：缺 {sorted(set(expected)-on_disk)}，多 {sorted(on_disk-set(expected))}'
    for name,data in expected.items():
        saved=json.loads((CONTRACTS/name).read_text(encoding='utf-8'))
        assert_semantic_match(data,saved,f'{name}:')
        # 门禁脚本自己的比较逻辑也必须判定一致，避免检查实现与测试口径脱节。
        # 必须与 check() 使用同一组容差（参考结果对近零残差与末位浮点差异有绝对/相对容差）。
        assert generator.diff_contract(
            data,saved,
            rel_tolerance=generator.rel_tolerances.get(name,0.),
            abs_tolerance=generator.abs_tolerances.get(name,0.))==[],name


def test_contract_check_detects_drift(tmp_path,monkeypatch,capsys):
    generator=contract_generator()
    expected=generator.contract_files()
    monkeypatch.setattr(generator,'output',tmp_path)
    # 目录为空时全部文件缺失，必须判定漂移。
    assert generator.check(expected)==1
    report=capsys.readouterr().out
    assert 'contracts out of date' in report and 'module.schema.json' in report
    # 正确写入后必须通过，并报告准确文件数。
    generator.write(expected)
    assert generator.check(expected)==0
    assert f'contracts up to date: {len(expected)} files' in capsys.readouterr().out
    # 值漂移：篡改单个 schema 字段时必须退出 1，并定位到文件与字段路径。
    drifted=deepcopy(expected);drifted['module.schema.json']['title']='DriftedTitle'
    assert generator.check(drifted)==1
    report=capsys.readouterr().out
    assert 'module.schema.json' in report and '$.title' in report
    # 键集漂移：源码多出一个键时同样必须被发现（双向比较，不能只看已有键）。
    drifted=deepcopy(expected);drifted['module.schema.json']['unexpected_field']=1
    assert generator.check(drifted)==1
    assert 'unexpected_field' in capsys.readouterr().out
    # 生成清单之外的多余 JSON 文件也算漂移。
    stale=tmp_path/'stale.schema.json';stale.write_text('{}',encoding='utf-8')
    assert generator.check(expected)==1
    assert 'stale.schema.json' in capsys.readouterr().out
    stale.unlink()
    # --check 必须只读：文件内容与修改时间都不能变化。
    before={path.name:(path.read_bytes(),path.stat().st_mtime_ns) for path in tmp_path.glob('*')}
    assert generator.check(expected)==0
    capsys.readouterr()
    after={path.name:(path.read_bytes(),path.stat().st_mtime_ns) for path in tmp_path.glob('*')}
    assert before==after


def test_contract_check_cli_passes_without_writing():
    before={path.name:(path.read_bytes(),path.stat().st_mtime_ns) for path in CONTRACTS.glob('*')}
    result=subprocess.run([sys.executable,'scripts/generate_contracts.py','--check'],cwd=ROOT,capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'contracts up to date:' in result.stdout
    after={path.name:(path.read_bytes(),path.stat().st_mtime_ns) for path in CONTRACTS.glob('*')}
    assert before==after


# ---- 契约完整性（v0.4.10，task-3）：所有路由有响应模型，错误包络与错误码集中登记 ----

API_PREFIX='/api/'
# 二进制下载没有 JSON response_model；OpenAPI 里已显式声明 application/zip 的 content schema。
RESPONSE_MODEL_EXCEPTIONS={
    '/api/v1/workspace/backup': 'application/zip 二进制下载（FileResponse），由 responses= 声明二进制 schema',
    '/api/v1/runs/{run_id}/report.csv': 'text/csv 下载（冷库运行曲线数据）',
    '/api/v1/runs/{run_id}/report.html': 'text/html 下载（冷库运行报告）',
    '/api/v1/runs/compare/report.html': 'text/html 下载（两次运行对照报告）',
}
# 白名单路由的成功响应媒体类型。
EXCEPTION_MEDIA={'/api/v1/workspace/backup': 'application/zip', '/api/v1/runs/{run_id}/report.csv': 'text/csv',
                 '/api/v1/runs/{run_id}/report.html': 'text/html', '/api/v1/runs/compare/report.html': 'text/html'}
# 运行时由 api.py 写进 detail.code 的静态错误码；诊断码（编译/求解/物性）另行透传，见 errors.DIAGNOSTIC_CODES。
EXPECTED_ERROR_CODES={
    'AUTH_REQUIRED', 'AUTH_SCOPE', 'RUN_NOT_FOUND', 'PROJECT_CONFLICT', 'WORKSPACE_CONFLICT',
    'MODULE_VERSION_CONFLICT', 'RUN_ALREADY_FINISHED', 'COMMAND_ID_CONFLICT', 'NO_FRAME',
    'MODULE_SAVE_INVALID', 'MODULE_WORKER_IO_ERROR', 'RUN_LIMIT', 'RUN_TOO_LONG',
    'VARIABLE_UNKNOWN', 'MODULE_STORAGE_ERROR', 'INTERNAL_ERROR', 'STORAGE_FAILED',
}


def api_http_routes():
    return [route for route in create_app().routes
            if isinstance(route, APIRoute) and route.path.startswith(API_PREFIX)]


def test_every_api_route_has_response_model_or_whitelist():
    routes=api_http_routes()
    # 冷库 A 增加运行报告（CSV/HTML/对照）与机组工作点 4 条路由。
    assert len(routes)==44,f'HTTP 路由数量变化：{len(routes)}'
    missing=[f'{sorted(route.methods)} {route.path}' for route in routes
             if route.response_model is None and route.path not in RESPONSE_MODEL_EXCEPTIONS]
    assert missing==[],f'以下路由缺少 response_model 且不在白名单：{missing}'
    # 白名单必须真实存在，避免名单腐化成“永远为空”的豁免。
    assert {route.path for route in routes} >= set(RESPONSE_MODEL_EXCEPTIONS)


def test_every_success_response_has_openapi_schema():
    spec=create_app().openapi()
    missing=[]
    for path,operations in spec['paths'].items():
        if not path.startswith(API_PREFIX):
            continue
        for method,operation in operations.items():
            for status,response in operation['responses'].items():
                if not status.startswith('2'):
                    continue
                content=response.get('content') or {}
                if path in RESPONSE_MODEL_EXCEPTIONS:
                    assert 'schema' in content.get(EXCEPTION_MEDIA[path],{}),f'{method.upper()} {path} 缺少下载内容 schema'
                    continue
                if 'schema' not in (content.get('application/json') or {}):
                    missing.append(f'{method.upper()} {path} {status}')
    assert missing==[],f'以下成功响应没有 JSON schema：{missing}'


def test_error_code_registry_is_consistent_with_routes():
    # 1) 注册表覆盖运行时静态错误码；状态级描述覆盖无 code 的纯文本错误。
    known_statuses=set(errors.STATUS_ERRORS)|{item.status for item in errors.ERROR_CODES.values()}
    assert EXPECTED_ERROR_CODES <= set(errors.ERROR_CODES), \
        f'注册表缺少错误码：{sorted(EXPECTED_ERROR_CODES - set(errors.ERROR_CODES))}'
    for code,spec in errors.ERROR_CODES.items():
        assert spec.status in known_statuses,f'{code} 的状态 {spec.status} 未登记'
        assert spec.description.strip(),code
    assert {404, 409, 413, 422, 500, 503, 507} <= set(errors.STATUS_ERRORS)
    assert errors.ERROR_CODES['AUTH_REQUIRED'].status==401
    assert errors.ERROR_CODES['AUTH_SCOPE'].status==403
    assert errors.ERROR_CODES['STORAGE_FAILED'].status==507
    # 2) api.py 里写死的 detail.code 必须全部登记（诊断码单独登记）。
    source=(ROOT/'backend'/'fn_engine'/'api.py').read_text(encoding='utf-8')
    literals=set(re.findall(r"'code'\s*:\s*'([A-Z][A-Z0-9_]*)'",source))
    assert literals,'未能从 api.py 扫描到错误码字面量'
    unknown=literals-set(errors.ERROR_CODES)-set(errors.DIAGNOSTIC_CODES)
    assert unknown==set(),f'api.py 使用了未登记的错误码：{sorted(unknown)}'
    # 3) 路由声明与注册表一致：错误状态都已登记；受保护路由统一声明 401/403 并引用 ErrorResponse。
    spec=create_app().openapi()
    for path,operations in spec['paths'].items():
        if not path.startswith(API_PREFIX):
            continue
        for method,operation in operations.items():
            declared={int(status) for status in operation['responses'] if not status.startswith('2')}
            assert declared <= known_statuses, \
                f'{method.upper()} {path} 声明了未登记的错误状态：{sorted(declared-known_statuses)}'
            if path=='/api/v1/health':
                continue
            for status in ('401','403'):
                response=operation['responses'].get(status)
                assert response,f'{method.upper()} {path} 缺少 {status} 错误声明'
                ref=response['content']['application/json']['schema']['$ref']
                assert ref.endswith('/ErrorResponse'),ref


def test_error_response_model_is_documented():
    spec=create_app().openapi()
    schemas=spec['components']['schemas']
    assert 'ErrorResponse' in schemas
    # 运行时统一是 {"detail": …} 包络；detail 可为结构化错误、纯文本或请求校验问题列表。
    assert 'detail' in schemas['ErrorResponse']['properties']
    contract=json.loads((CONTRACTS/'error-response.schema.json').read_text(encoding='utf-8'))
    assert 'detail' in contract['properties'],'contracts/error-response.schema.json 不是错误包络'
    # 新补的响应模型都已进入 contracts/，且 --check 生成的 openapi 里可解析。
    for name in ('health-response','workspace-response','project-detail-response','run-list-response'):
        assert (CONTRACTS/f'{name}.schema.json').is_file(),f'缺少契约文件 {name}.schema.json'


def test_runtime_error_envelope_stays_compatible():
    with TestClient(create_app()) as client:
        # 404：纯文本 detail（不是结构化对象）——前端与测试依赖这一形状。
        missing=client.get('/api/v1/runs/deadbeef')
        assert missing.status_code==404
        assert missing.json()=={'detail':RUN_NOT_FOUND}
        # 503：未启用持久化时同样是纯文本 detail。
        no_storage=client.get('/api/v1/workspace')
        assert no_storage.status_code==503
        assert set(no_storage.json())=={'detail'} and isinstance(no_storage.json()['detail'],str)
        # 422：请求校验失败仍是 FastAPI 的 detail 问题列表。
        invalid=client.post('/api/v1/solve',json={'id':'x'})
        assert invalid.status_code==422
        detail=invalid.json()['detail']
        assert isinstance(detail,list) and detail and {'type','loc','msg'} <= set(detail[0])


def test_runtime_coded_error_keeps_detail_envelope(tmp_path):
    data={'schema':1,'projects':[{'id':'p','name':'P'}],'modules':[{'id':'m'}],'models':[],'activeProject':'p'}
    with TestClient(create_app(data_root=tmp_path/'data')) as client:
        assert client.post('/api/v1/workspace',json={'data':data,'expected_revision':0}).status_code==200
        conflict=client.post('/api/v1/workspace',json={'data':data,'expected_revision':0})
        assert conflict.status_code==409
        assert set(conflict.json())=={'detail'}
        assert conflict.json()['detail']['code']=='WORKSPACE_CONFLICT'
        assert conflict.json()['detail']['message']
        assert errors.ERROR_CODES['WORKSPACE_CONFLICT'].status==409


def test_runtime_auth_error_envelope(tmp_path):
    store=TokenStore(tmp_path/'tokens.json')
    _,read_secret=store.create('reader','read')
    with TestClient(create_app(auth=AuthConfig(required=True,store=store))) as client:
        assert client.get('/api/v1/health').status_code==200
        anonymous=client.get('/api/v1/catalog')
        assert anonymous.status_code==401
        assert anonymous.headers['www-authenticate']=='Bearer'
        assert anonymous.json()['detail']['code']=='AUTH_REQUIRED'
        denied=client.post('/api/v1/projects/validate',headers={'Authorization':f'Bearer {read_secret}'},json={})
        assert denied.status_code==403
        assert denied.json()['detail']['code']=='AUTH_SCOPE'


def test_route_error_declarations_cover_registered_codes():
    """业务错误码在对应路由上必须声明为 OpenAPI responses（注册表与路由一致的第二层校验）。"""
    spec=create_app().openapi()
    expectations={
        ('post','/api/v1/workspace'): {409, 507},
        ('post','/api/v1/modules/versions'): {409, 422, 500},
        ('post','/api/v1/runs/{run_id}/command'): {404, 409, 422},
        ('get','/api/v1/runs/{run_id}/variables'): {404, 409, 422},
        ('get','/api/v1/runs/{run_id}'): {404},
        ('post','/api/v1/runs'): {422},
        ('get','/api/v1/workspace'): {404, 503, 507},
    }
    for (method,path),statuses in expectations.items():
        declared={int(status) for status in spec['paths'][path][method]['responses'] if not status.startswith('2')}
        assert statuses <= declared,f'{method.upper()} {path} 缺少错误状态声明：{sorted(statuses-declared)}'


def test_error_responses_rejects_unregistered_entries():
    with pytest.raises(KeyError):
        errors.error_responses('NOT_A_REAL_CODE')
    with pytest.raises(KeyError):
        errors.error_responses(418)
    with pytest.raises(TypeError):
        errors.error_responses(1.5)
