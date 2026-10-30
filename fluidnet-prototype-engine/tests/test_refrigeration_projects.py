"""RF-4: public project/version/archive/report/batch operations retain the executed author code."""
from copy import deepcopy
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.models import Project
from fn_engine.module_templates import create_template
from fn_engine.runtime import module_definition_hash
from test_continuous import wait
from test_batches import create as create_batch, start as start_batch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from generate_refrigeration_author_example import author_station, VALVE, CONDENSER  # noqa: E402


def workspace(project):
    definitions={m.id:m for m in project.modules}
    def display(iid,values):
        module=definitions[next(n.module_id for n in project.instances if n.id==iid)]
        specs={p.id:p for p in module.parameters}
        return {k:specs[k].unit.from_canonical(v) if specs[k].unit else v for k,v in values.items()}
    raw={'id':project.id,'name':project.name,'solverOptions':project.solver.model_dump(mode='json'),
        'fluidConfig':project.fluid.model_dump(mode='json'),'medium':'water',
        'circuitFluids':[{'id':c.id,'anchor':c.anchor.model_dump(),'fluidConfig':c.fluid.model_dump()} for c in project.circuit_fluids],
        'controllers':[c.model_dump() for c in project.controllers],'controlScripts':[s.model_dump() for s in project.control_scripts],
        'events':[e.model_dump() for e in project.events],
        'scenarios':[{'id':s.id,'name':s.name,'overrides':{k:display(k,v) for k,v in s.overrides.items()},
                      'events':None if s.events is None else [e.model_dump() for e in s.events]} for s in project.scenarios],
        'moduleSnapshots':{m.id:m.model_dump(mode='json') for m in project.modules},
        'pages':[{'id':'main','nodes':[{'id':n.id,'name':n.name,'moduleId':n.module_id,'x':n.position.x,'y':n.position.y,
            'params':display(n.id,n.parameters),'draft':display(n.id,n.draft_parameters),
            'package':n.package.model_dump(mode='json') if n.package else None} for n in project.instances],
            'edges':[[c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id] for c in project.connections]}]}
    return {'format':'fluidnet-studio-prototype','schema':1,'activeProject':project.id,'projects':[raw],
            'modules':[m.model_dump(mode='json') for m in project.modules],'models':[],'charts':{'extra':[]}}


def publish(client,module,version):
    response=client.post('/api/v1/modules/versions',json={'module':module.model_dump(mode='json'),'expected_latest_version':version})
    assert response.status_code==201,response.text
    return type(module).model_validate(response.json()['module'])


def run(client,project=None,pid=None,revision=None):
    options={'mode':'dynamic','duration_s':.2,'dt_s':.1}
    response=client.post(f'/api/v1/projects/{pid}/runs' if pid else '/api/v1/runs',json=
        {**options,**({'revision':revision} if pid else {'project':project.model_dump(mode='json')})})
    assert response.status_code in {201,202},response.text
    record=wait(client,response.json()['run_id'],lambda r:r['status'] in {'failed','completed'})
    assert record['status']=='completed',record
    return record


def test_project_versions_reports_and_batches_keep_frozen_sources_across_restart(tmp_path,monkeypatch):
    config={'data_root':tmp_path/'data','module_storage_root':tmp_path/'modules'}
    with TestClient(create_app(**config)) as client:
        module=publish(client,create_template('refrigeration_throttle','author_rf4','作者项目设备'),0)
        project=author_station(module)
        payload=workspace(project);pid=project.id
        response=client.post('/api/v1/workspace',json={'data':payload,'expected_revision':0})
        assert response.status_code==200,response.text
        normalized=normalize_prototype_export(payload)
        assert next(m for m in normalized.modules if m.id==module.id).definition_hash==module.definition_hash
        first=run(client,pid=pid,revision=1)
        old_frame=deepcopy(first['frame'])
        body={'revision':1,'sweep':{'instance_id':VALVE,'parameter_id':'kv_m3_h','values':[.3,.6]},
            'variables':[VALVE+'.mass_flow_kg_s',VALVE+'.state.transferred_mass_kg'],
            'options':{'mode':'dynamic','duration_s':.2,'dt_s':.1}}
        batch,_=create_batch(client,pid,body)
        # Change the algorithm while leaving the explicit project parameter defaults intact.
        changed=module.model_copy(deep=True)
        changed.source['runtime']=changed.source['runtime'].replace('fraction = opening','fraction = opening * .5',1)
        new=publish(client,changed,1)
        preview=client.post('/api/v1/project-upgrades/preview',json={'project':normalized.model_dump(mode='json'),
            'module_id':module.id,'target_version':2}).json()
        assert preview['compatible'],preview
        upgraded=Project.model_validate(preview['project'])
        assert upgraded.controllers==normalized.controllers and upgraded.scenarios==normalized.scenarios
        doc={'format':'fluidnet-project','schema':1,'project':workspace(upgraded)['projects'][0],
             'modules':workspace(upgraded)['modules'],'models':[],'charts':[]}
        response=client.post(f'/api/v1/projects/{pid}',json={'document':doc,'expected_revision':1})
        assert response.status_code==200,response.text
        second=run(client,pid=pid,revision=2)
        assert second['frame']['variables'][VALVE+'.mass_flow_kg_s']<first['frame']['variables'][VALVE+'.mass_flow_kg_s']*.6
        completed=start_batch(client,batch['id']);assert completed['status']=='completed',completed
        saved_module=next(m for m in completed['source']['modules'] if m['id']==module.id)
        assert saved_module['version']==1 and saved_module['definition_hash']==module.definition_hash
        csv=client.get(f"/api/v1/batches/{batch['id']}/export").text
        assert completed['snapshot_hash'] in csv and '累计通过质量/kg' in csv
        restore=client.post(f'/api/v1/projects/{pid}/restore',json={'revision':1,'expected_revision':2})
        assert restore.status_code==200,restore.text
        restored=run(client,pid=pid,revision=3)
        assert restored['frame']['variables'][VALVE+'.mass_flow_kg_s']==pytest.approx(old_frame['variables'][VALVE+'.mass_flow_kg_s'],rel=1e-12)
        assert next(m for m in second['request']['project']['modules'] if m['id']==module.id)['definition_hash']==new.definition_hash
        # Report generation must not start a Worker, including after a module update.
        from fn_engine.runtime import WorkerProcess
        monkeypatch.setattr(WorkerProcess,'__init__',lambda *a,**kw:pytest.fail('report executed author code'))
        html=client.get('/api/v1/runs/'+first['id']+'/report.html')
        assert html.status_code==200,html.text
        assert module.definition_hash in html.text and new.definition_hash not in html.text
        assert VALVE in html.text and CONDENSER in html.text
        assert 'EV1' not in html.text and 'EC1' not in html.text
        assert VALVE+'.state.transferred_mass_kg' in html.text
        report_csv=client.get('/api/v1/runs/'+first['id']+'/report.csv').text
        assert VALVE+'.state.transferred_mass_kg [kg]' in report_csv
    with TestClient(create_app(**config)) as client:
        assert client.get('/api/v1/runs/'+first['id']).json()['frame']==old_frame
        assert client.get('/api/v1/runs/'+first['id']+'/report.html').text==html.text
        assert client.get(f"/api/v1/batches/{batch['id']}").json()['source']==completed['source']


def test_same_frozen_module_runs_in_a_second_station_and_canonical_json_roundtrip(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        module=create_template('refrigeration_throttle','portable_author','跨项目设备')
        for compact in [False,True]:
            project=author_station(module,compact)
            restored=Project.model_validate_json(project.model_dump_json())
            frame=run(client,restored)['frame']
            assert frame['variables'][VALVE+'.state.transferred_mass_kg']>0
            assert module_definition_hash(next(m for m in restored.modules if m.id==module.id))==module_definition_hash(module)
