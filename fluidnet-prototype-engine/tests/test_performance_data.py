import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.backup import backup_workspace, restore_workspace
from fn_engine.models import FluidConfig
from fn_engine.packages import ModuleStore, load_module_package
from fn_engine.performance_data import (PerformanceImport,PerformanceStore,PerformanceConflict,
    PerformanceProposalRequest,preview,proposal,compare)
from fn_engine.storage import WorkspaceStore, StorageError, pack, unpack

ROOT=Path(__file__).resolve().parents[1]


def payload(**changes):
    data={'id':'pump-chart','name':'用户泵数据','kind':'pump_head','format':'csv','file_name':'泵资料.csv',
        'content_base64':base64.b64encode(b'flow,value\n0,30\n2,20\n4,0\n').decode(),
        'flow_unit':'L/s','value_unit':'m','source':'test data only; independent reference input',
        'reference_fluid':'Water','reference_density_kg_m3':998.2,'reference_speed_rpm':1450.}
    data.update(changes)
    return data


def imported(**changes):return PerformanceImport.model_validate(payload(**changes))


def test_csv_preserves_source_bytes_and_converts_volume_units_exactly():
    p=imported();v=preview(p)
    assert v.source_points==[[0.,30.],[2.,20.],[4.,0.]]
    assert v.points_m3_h==[[0.,30.],[7.2,20.],[14.4,0.]]
    assert v.source_hash==hashlib.sha256(base64.b64decode(p.content_base64)).hexdigest()
    assert v.valid_flow_m3_h==[0.,14.4]


@pytest.mark.parametrize('kind,value_unit,points,expected',[
    ('fan_pressure','kPa',[[0,.4],[.5,.3],[1,0]],[[0,400],[1800,300],[3600,0]]),
    ('efficiency','%',[[0,30],[.5,70],[1,40]],[[0,.3],[1800,.7],[3600,.4]]),
])
def test_json_converts_pressure_efficiency_and_m3s(kind,value_unit,points,expected):
    p=imported(kind=kind,format='json',flow_unit='m3/s',value_unit=value_unit,
        content_base64=base64.b64encode(json.dumps({'points':points}).encode()).decode())
    for actual,reference in zip(preview(p).points_m3_h,expected):assert actual==pytest.approx(reference,abs=1e-12)


@pytest.mark.parametrize('text',[
    'flow,value\n1,2\n1,1\n', 'flow,value\n2,2\n1,1\n',
    'flow,value\n0,=1+1\n1,0\n', 'flow,value\n0,NaN\n1,0\n',
    'flow,value\n0,1e999\n1,0\n', 'flow,flow\n0,2\n1,0\n',
    'flow,value,unexpected\n0,2,3\n1,0,3\n',
])
def test_invalid_csv_never_sorts_deduplicates_evaluates_or_accepts_nonfinite(text):
    with pytest.raises(ValueError):preview(imported(content_base64=base64.b64encode(text.encode()).decode()))


def test_unit_kind_and_validity_range_are_explicit_and_bounded():
    with pytest.raises(ValueError):imported(value_unit='kPa')
    with pytest.raises(ValueError):preview(imported(valid_flow_min=0,valid_flow_max=5))
    with pytest.raises(ValueError):preview(imported(valid_flow_min=3,valid_flow_max=2))
    with pytest.raises(ValueError):imported(source='   ')
    with pytest.raises(ValueError):imported(reference_speed_rpm=0)
    with pytest.raises(ValueError):imported(reference_density_kg_m3=True)
    with pytest.raises(ValueError):preview(imported(kind='efficiency',value_unit='1'))
    nonmono=preview(imported(content_base64=base64.b64encode(b'flow,value\n0,2\n1,3\n2,0\n').decode()))
    assert len(nonmono.warnings)==2


def test_versions_survive_restart_export_exact_bytes_and_compare(tmp_path):
    request=payload()
    with TestClient(create_app(data_root=tmp_path)) as client:
        response=client.post('/api/v1/performance-data/versions',json=request)
        assert response.status_code==201,response.text
        first=response.json();assert first['version']==1
        request['expected_latest_version']=1
        request['content_base64']=base64.b64encode(b'flow,value\n0,32\n2,22\n4,0\n').decode()
        second=client.post('/api/v1/performance-data/versions',json=request)
        assert second.status_code==201 and second.json()['version']==2
        assert client.post('/api/v1/performance-data/versions',json=request).status_code==409
        compared=client.get('/api/v1/performance-data/compare',params={'left_id':'pump-chart','left_version':1,'right_id':'pump-chart','right_version':2}).json()
        assert compared['comparable'] and compared['samples'][0]['difference']==2.
        assert compared['samples'][-1]['left']==compared['samples'][-1]['right']==compared['samples'][-1]['difference']==0.
        assert client.get('/api/v1/performance-data/pump-chart/versions/1').json()==first
    with TestClient(create_app(data_root=tmp_path)) as client:
        listing=client.get('/api/v1/performance-data').json()
        assert listing['persistent'] and [i['version'] for i in listing['items']]==[2,1]
        assert client.get('/api/v1/performance-data/pump-chart/versions/1').json()==first
        assert client.get('/api/v1/performance-data/pump-chart/versions/1/export').content==base64.b64decode(first['import_data']['content_base64'])
        assert client.get('/api/v1/performance-data/missing/versions/1').status_code==404


def test_concurrent_save_same_expected_version_only_one_commits(tmp_path):
    workspace=WorkspaceStore(tmp_path);store=PerformanceStore(workspace)
    try:
        def save(_):
            try:return store.save(imported()).version
            except PerformanceConflict:return 'conflict'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(save,range(2)))
        assert sorted(results,key=str)==[1,'conflict']
        assert len(store.catalog().items)==1
    finally:workspace.close()


def test_database_rejection_leaves_no_half_version_and_can_retry(tmp_path):
    workspace=WorkspaceStore(tmp_path);store=PerformanceStore(workspace)
    try:
        with workspace.transaction() as db:db.execute("CREATE TRIGGER fail_performance BEFORE INSERT ON performance_versions BEGIN SELECT RAISE(ABORT,'injected write failure'); END")
        with pytest.raises(StorageError,match='injected write failure'):store.save(imported())
        assert store.catalog().items==[]
        with workspace.transaction() as db:db.execute('DROP TRIGGER fail_performance')
        assert store.save(imported()).version==1
    finally:workspace.close()


def test_tampered_stored_points_are_rejected_not_silently_rehashed(tmp_path):
    workspace=WorkspaceStore(tmp_path);store=PerformanceStore(workspace)
    try:
        store.save(imported())
        with workspace.transaction() as db:
            raw=db.execute('SELECT data FROM performance_versions').fetchone()[0];data=unpack(raw);data['points_m3_h'][1][1]=999
            db.execute('UPDATE performance_versions SET data=?',(pack(data),))
        with pytest.raises(StorageError,match='完整性'):store.get('pump-chart',1)
        with pytest.raises(StorageError):store.catalog()
    finally:workspace.close()


def test_performance_library_is_in_existing_database_backup(tmp_path):
    workspace=WorkspaceStore(tmp_path/'original');store=PerformanceStore(workspace)
    modules=ModuleStore(tmp_path/'no-seeds',tmp_path/'modules')
    try:
        first=store.save(imported());backup_workspace(workspace,modules,tmp_path/'copy.zip')
    finally:workspace.close()
    restore_workspace(tmp_path/'copy.zip',tmp_path/'restored')
    restored=WorkspaceStore(tmp_path/'restored')
    try:assert PerformanceStore(restored).get(first.id,1)==first
    finally:restored.close()


def test_proposal_is_pure_and_checks_algorithm_reference_efficiency_and_range():
    store=PerformanceStore();module=load_module_package(ROOT/'modules/design_pump')
    try:
        first=store.save(imported());before=module.model_dump(mode='json')
        request=PerformanceProposalRequest(id=first.id,version=1,module=module,parameter_id='head_curve',fluid=FluidConfig(fluid='Water'))
        result=proposal(request,store)
        assert result.parameters['head_curve']==first.points_m3_h
        assert result.provenance['content_hash']==first.content_hash and module.model_dump(mode='json')==before
        with pytest.raises(ValueError,match='工质'):proposal(request.model_copy(update={'fluid':FluidConfig(fluid='Air')}),store)
        changed=module.model_copy(deep=True);changed.source['runtime']+='\n# changed algorithm\n'
        with pytest.raises(ValueError,match='算法'):proposal(request.model_copy(update={'module':changed}),store)
        with pytest.raises(ValueError,match='效率曲线'):proposal(request.model_copy(update={'parameters':{'efficiency_curve':[[0,.3],[10,.7]]}}),store)
        narrow=store.save(imported(id='narrow',valid_flow_min=1))
        with pytest.raises(ValueError,match='有效区间'):proposal(request.model_copy(update={'id':narrow.id}),store)
    finally:store.close()


def test_fan_proposal_moves_reference_density_with_pressure_curve():
    store=PerformanceStore();module=load_module_package(ROOT/'modules/design_fan')
    try:
        saved=store.save(imported(kind='fan_pressure',value_unit='kPa',reference_fluid='Air',reference_density_kg_m3=1.08))
        result=proposal(PerformanceProposalRequest(id=saved.id,version=1,module=module,parameter_id='pressure_curve',fluid=FluidConfig(fluid='HEOS::Air')),store)
        assert result.parameters['reference_density_kg_m3']==1.08
        assert result.parameters['pressure_curve'][0][1]==30000.
    finally:store.close()


def test_companion_reference_and_comparison_do_not_mix_speed_or_fluid():
    store=PerformanceStore();module=load_module_package(ROOT/'modules/design_pump')
    try:
        a=store.save(imported())
        b=store.save(imported(id='speed2',reference_speed_rpm=2900))
        assert not compare(a,b).comparable and compare(a,b).samples==[]
        eff=store.save(imported(id='eff',kind='efficiency',value_unit='%',reference_speed_rpm=2900,
            content_base64=base64.b64encode(b'flow,value\n0,30\n10,70\n20,50\n').decode()))
        request=PerformanceProposalRequest(id=a.id,version=1,module=module,parameter_id='head_curve',parameters={'efficiency_curve':eff.points_m3_h},references={
            'efficiency_curve':{'id':eff.id,'version':1,'content_hash':eff.content_hash}})
        with pytest.raises(ValueError,match='参考'):proposal(request,store)
    finally:store.close()


def test_companion_reference_must_match_current_curve_and_immutable_version():
    store=PerformanceStore();module=load_module_package(ROOT/'modules/design_pump')
    try:
        a=store.save(imported())
        eff=store.save(imported(id='eff',kind='efficiency',value_unit='%',
            content_base64=base64.b64encode(b'flow,value\n0,30\n10,70\n20,50\n').decode()))
        request=PerformanceProposalRequest(id=a.id,version=1,module=module,parameter_id='head_curve',parameters={'efficiency_curve':eff.points_m3_h},references={
            'efficiency_curve':{'id':eff.id,'version':1,'content_hash':eff.content_hash}})
        assert proposal(request,store).parameters['head_curve']==a.points_m3_h
        with pytest.raises(ValueError,match='当前草稿'):proposal(request.model_copy(update={'parameters':{}}),store)
        changed=request.model_dump();changed['references']['efficiency_curve']['content_hash']='0'*64
        with pytest.raises(ValueError,match='哈希'):proposal(PerformanceProposalRequest.model_validate(changed),store)
    finally:store.close()


def test_proposal_rejects_malformed_companion_curve_with_structured_422(tmp_path):
    module=load_module_package(ROOT/'modules/design_fan')
    with TestClient(create_app(data_root=tmp_path)) as client:
        saved=client.post('/api/v1/performance-data/versions',json=payload(kind='fan_pressure',value_unit='Pa')).json()
        request={'id':saved['id'],'version':1,'module':module.model_dump(mode='json'),'parameter_id':'pressure_curve','parameters':{'efficiency_curve':'not a curve'}}
        response=client.post('/api/v1/performance-data/proposal',json=request)
        assert response.status_code==422 and response.json()['detail']['code']=='PERFORMANCE_INVALID'
        request['parameters']['efficiency_curve']=[[0,.3],[20,True]]
        assert client.post('/api/v1/performance-data/proposal',json=request).status_code==422
