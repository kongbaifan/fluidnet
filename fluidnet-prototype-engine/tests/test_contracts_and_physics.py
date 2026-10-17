import math
from copy import deepcopy
from pathlib import Path
import importlib.util
import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project, CompilationError
from fn_engine.models import Connection, Endpoint, ModuleInstance, Project, RunRequest
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
    """双向语义比较：键集双向一致、长度一致、值是同一 JSON 语义（浮点按 1e-9 相对误差）。"""
    if isinstance(expected,dict) and isinstance(actual,dict):
        assert set(expected)==set(actual),f'{path} 键集不一致：缺 {sorted(set(expected)-set(actual))}，多 {sorted(set(actual)-set(expected))}'
        for key in expected:assert_semantic_match(expected[key],actual[key],f'{path}.{key}')
    elif isinstance(expected,list) and isinstance(actual,list):
        assert len(expected)==len(actual),f'{path} 长度不一致：{len(expected)} != {len(actual)}'
        for index,(left,right) in enumerate(zip(expected,actual)):assert_semantic_match(left,right,f'{path}[{index}]')
    elif isinstance(expected,bool) or isinstance(actual,bool):
        assert expected is actual,f'{path}: {expected!r} != {actual!r}'
    elif isinstance(expected,(int,float)) and isinstance(actual,(int,float)):
        assert expected==pytest.approx(actual,rel=1e-9,abs=1e-12),f'{path}: {expected!r} != {actual!r}'
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
        assert generator.diff_contract(data,saved)==[],name


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
