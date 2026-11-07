from copy import deepcopy
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.hvac_expansion_examples import example as hvac_example
from fn_engine.regulating_valves import example
from fn_engine.system_inspection import project_check, run_inspection, frozen_circuits, compare_runs


def test_preflight_accumulates_unconnected_ports_and_preserves_compile_diagnostics():
    p=example();p.connections=[]
    result=project_check(p)
    assert not result.valid
    assert sum(d.code=='INSPECT_PORT_OPEN' for d in result.diagnostics)>=4
    assert any(d.code!='INSPECT_PORT_OPEN' for d in result.diagnostics)


def test_frozen_two_fluid_circuits_do_not_mix_at_heat_exchanger():
    p=hvac_example('plate-water-glycol').model_dump(mode='json')
    groups=frozen_circuits(p)
    assert len(groups)==2
    assert {g['fluid']['fluid'] for g in groups}=={'Water','INCOMP::MEG[0.3]'}
    hot=next(g for g in groups if 'HotIn:out0' in g['ports'])
    assert 'Plate-Own:cold_in' not in hot['ports']


def test_frozen_inspection_is_stable_after_restart_and_does_not_compile(tmp_path):
    p=example()
    with TestClient(create_app(data_root=tmp_path)) as client:
        check=client.post('/api/v1/project-inspection',json=p.model_dump(mode='json'))
        assert check.status_code==200 and check.json()['valid'],check.text
        run=client.post('/api/v1/runs',json={'project':p.model_dump(mode='json')}).json()
        rid=run['run_id']
        with patch('fn_engine.api.compile_project',side_effect=AssertionError('inspection must not compile')):
            data=client.get(f'/api/v1/runs/{rid}/inspection').json()
        assert data['run_id']==rid and data['valid']
        assert any(v['key']=='metrics.mass_residual_kg_s' for v in data['balances'])
        assert any(d['instance_id']=='Regulator' for d in data['devices'])
    with TestClient(create_app(data_root=tmp_path)) as client:
        with patch('fn_engine.api.compile_project',side_effect=AssertionError('inspection must not compile')):
            assert client.get(f'/api/v1/runs/{rid}/inspection').json()==data


def test_missing_values_remain_unknown_and_power_aliases_are_not_summed():
    p=hvac_example('air-cooled-chiller').model_dump(mode='json')
    record={'id':'old-run','status':'failed','request':{'project':p},'frame':{
        'valid':False,'time_s':3.,'variables':{'Chiller.electric_power_w':300.,'Chiller.compressor_electric_power_w':250.},'metrics':{},'diagnostics':[]}}
    before=deepcopy(record);data=run_inspection(record)
    assert record==before and data.balances==[]
    chiller=next(d for d in data.devices if d.instance_id=='Chiller')
    assert any(v.value is None and v.status=='missing' for v in chiller.values)
    assert next(v for v in chiller.values if v.key=='Chiller.electric_power_w').value==300.
    assert not hasattr(data,'total_electric_power_w')


def test_failure_diagnostic_keeps_instance_and_field_location():
    p=example().model_dump(mode='json')
    d={'code':'LIMIT','message':'pressure','instance_id':'Regulator','field':'maximum_differential_pressure_pa'}
    data=run_inspection({'id':'failed','status':'failed','request':{'project':p},'frame':{'diagnostics':[d]}})
    assert data.diagnostics[0].field==d['field'] and data.time_s is None and not data.valid


def test_comparison_uses_same_key_and_unit_and_leaves_missing_unknown():
    p=example().model_dump(mode='json')
    left={'id':'a','status':'completed','request':{'project':p},'frame':{'variables':{'Regulator.actual_volume_flow_m3_h':2.},'metrics':{'energy_residual_w':.01},'valid':True}}
    right=deepcopy(left);right['id']='b';right['frame']['variables']['Regulator.actual_volume_flow_m3_h']=3.
    right['frame']['metrics']={}
    result=compare_runs(left,right)
    row=next(r for r in result.differences if r['key']=='Regulator.actual_volume_flow_m3_h')
    assert row['difference']==1.
    residual=next(r for r in result.differences if r['key']=='metrics.energy_residual_w')
    assert residual['right'] is None and residual['difference'] is None


def test_design_curve_projects_actual_density_and_speed_without_changing_inputs():
    from fn_engine.equipment_library import group_example
    p=group_example('design_fan').model_dump(mode='json')
    device=next(i for i in p['instances'] if i['id']=='Equipment');device['parameters'].update(speed_ratio=.5,reference_density_kg_m3=1.2)
    record={'id':'fan','status':'completed','request':{'project':p},'frame':{'valid':True,'variables':{
        'Equipment.volume_flow_m3_h':1000.,'Equipment.mass_flow_kg_s':1.,'Equipment.pressure_rise_pa':50.,'Equipment.in0.density_kg_m3':1.08}}}
    row=next(d for d in run_inspection(record).devices if d.instance_id=='Equipment').curves[0]
    assert row['working_curve'][0][1]==pytest.approx(row['points'][0][1]*.25*.9)
    assert row['working_ordinate']==50. and row['ordinate_unit']=='Pa'
    assert row['volume_flow_m3_h']==pytest.approx(3600/1.08)
    device['parameters']['running']=0.
    assert next(d for d in run_inspection(record).devices if d.instance_id=='Equipment').curves[0]['working_curve'] is None
    device['parameters']['running']=1.
    next(m for m in p['modules'] if m['id']=='design_fan')['source']['runtime']+='\n# modified algorithm\n'
    assert next(d for d in run_inspection(record).devices if d.instance_id=='Equipment').curves[0]['working_curve'] is None


def test_closed_composites_have_separate_frozen_circuits_without_worker_execution():
    from fn_engine.composites import module_from_group
    from fn_engine.refrigeration.forward_examples import headed_example
    from fn_engine.models import Project, ModuleInstance
    source=headed_example();group=module_from_group(source,[i.id for i in source.instances],'closed_group','closed')
    p=Project(id='two',name='two',fluid=source.fluid,modules=[group],connections=[],instances=[
        ModuleInstance(id=i,module_id=group.id,name=i) for i in ('A','B')])
    circuits=frozen_circuits(p.model_dump(mode='json'))
    assert len(circuits)==2
    assert not any(any(x.startswith('A__') for x in c['instance_ids']) and any(x.startswith('B__') for x in c['instance_ids']) for c in circuits)
