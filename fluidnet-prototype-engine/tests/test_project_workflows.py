from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app, apply_scenario
from fn_engine.bridge import normalize_prototype_export
from fn_engine.models import ParameterSpec, Scenario, UnitSpec, Connection, Endpoint
from fn_engine.projects import upgrade_project
from fn_engine.runtime import module_content_hash, module_definition_hash
from fn_engine.storage import WorkspaceStore, StorageError
from test_controls_storage import workspace
from test_platform_contracts import custom_project


def two_projects():
    data=workspace()
    other=deepcopy(data['projects'][0]);other['id']='q';data['projects'].append(other)
    return data


def test_project_save_conflict_and_restore_leave_other_projects_unchanged(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        client.post('/api/v1/workspace',json={'data':two_projects(),'expected_revision':0}).raise_for_status()
        first=client.get('/api/v1/projects/p').json()
        second=client.get('/api/v1/projects/q').json()
        second['document']['project']['control']='changed other project'
        response=client.post('/api/v1/projects/q',json={'document':second['document'],'expected_revision':1})
        assert response.status_code==200 and response.json()['revision']==2
        first['document']['project']['control']='changed first project'
        response=client.post('/api/v1/projects/p',json={'document':first['document'],'expected_revision':1})
        assert response.status_code==200 and response.json()['revision']==2
        assert client.post('/api/v1/projects/p',json={'document':first['document'],'expected_revision':1}).status_code==409
        response=client.post('/api/v1/projects/p/restore',json={'revision':1,'expected_revision':2})
        assert response.status_code==200 and response.json()['revision']==3
        assert response.json()['document']['project']['control']==workspace()['projects'][0]['control']
        assert client.get('/api/v1/projects/q').json()['document']['project']['control']=='changed other project'
        assert client.get('/api/v1/projects/q').json()['revision']==2
        assert len(client.get('/api/v1/projects').json()['projects'])==2
        assert client.post('/api/v1/projects/p/delete',json={'expected_revision':3}).status_code==200
        assert client.get('/api/v1/projects/p').status_code==404
        assert len(client.get('/api/v1/projects').json()['projects'])==1
        assert client.post('/api/v1/projects/q/delete',json={'expected_revision':2}).status_code==422


def test_v1_database_migration_and_project_history_are_durable(tmp_path):
    store=WorkspaceStore(tmp_path);store.save_workspace(two_projects(),0);store.close()
    with sqlite3.connect(tmp_path/'workspace.sqlite3') as db:
        db.execute('DROP TABLE project_history');db.execute('PRAGMA user_version=1')
    store=WorkspaceStore(tmp_path)
    assert store.project('p')['revision']==1
    document=store.project('p')['document'];document['project']['name']='migrated project'
    store.save_project(document,1);store.close()
    store=WorkspaceStore(tmp_path)
    try:
        assert store.project('p')['revision']==2
        assert store.project('p')['document']['project']['name']=='migrated project'
        assert store.db.execute('PRAGMA user_version').fetchone()[0]==2
    finally:store.close()


def test_project_and_workspace_revisions_rollback_together(tmp_path):
    store=WorkspaceStore(tmp_path);store.save_workspace(two_projects(),0)
    try:
        store.db.execute("CREATE TRIGGER disk_error BEFORE INSERT ON project_history BEGIN SELECT RAISE(ABORT,'disk error'); END")
        document=store.project('p')['document'];document['project']['control']='new'
        with pytest.raises(StorageError):store.save_project(document,1)
        assert store.workspace()['revision']==1
        assert store.project('p')['revision']==1
        assert store.workspace()['data']==two_projects()
    finally:store.close()


def target(project, mutate=lambda m:None):
    module=project.modules[-1].model_copy(deep=True)
    module.version+=1;mutate(module)
    module.content_hash=module_content_hash(module)
    module.definition_hash=module_definition_hash(module)
    return module


def test_compatible_upgrade_preserves_values_and_pins_all_instances():
    project=custom_project()
    second=project.instances[1].model_copy(deep=True);second.id='V2';project.instances.append(second)
    project.connections[1].target=Endpoint(instance_id='V2',port_id='in0')
    project.connections.append(Connection(id='last',source=Endpoint(instance_id='V2',port_id='out0'),target=Endpoint(instance_id='B2',port_id='out0')))
    original=project.model_dump()
    new=target(project,lambda m:m.parameters.append(ParameterSpec(id='gain',label='gain',default=2.)))
    result=upgrade_project(project,new)
    assert result['compatible'],result['reasons']
    node=result['project']['instances'][1]
    assert node['parameters']['opening_ratio']==.5 and node['parameters']['gain']==2
    assert node['package']['version']=='2.0.0'
    assert result['project']['instances'][-1]['package']['version']=='2.0.0'
    assert result['from_hashes']['definition_hash']!=result['to_hashes']['definition_hash']
    assert project.model_dump()==original


@pytest.mark.parametrize('kind',['parameter','port','unit','scenario'])
def test_incompatible_upgrade_is_rejected_without_mutation(kind):
    project=custom_project();project.scenarios=[Scenario(id='high',name='high',overrides={'V1':{'opening_ratio':.9}})]
    original=project.model_dump()
    def mutate(module):
        if kind=='parameter':module.parameters=[p for p in module.parameters if p.id!='opening_ratio']
        if kind=='port':module.ports[0].id='new_inlet'
        if kind=='unit':module.parameters[0].unit=UnitSpec(quantity='ratio',canonical_unit='1',display_unit='%',display_scale=.01)
        if kind=='scenario':
            p=next(p for p in module.parameters if p.id=='opening_ratio');p.maximum=.8;p.default=.5
    result=upgrade_project(project,target(project,mutate))
    assert not result['compatible'] and result['reasons']
    assert project.model_dump()==original


def test_prototype_scenarios_convert_units_without_changing_base():
    data=json.loads((Path(__file__).parent/'fixtures/prototype.json').read_text(encoding='utf-8'))
    raw=data['projects'][0];data['activeProject']=raw['id']
    raw['scenarios']=[{'id':'throttle','name':'节流工况','overrides':{'V1':{'opening':25}}}]
    project=normalize_prototype_export(data)
    assert project.scenarios[0].overrides['V1']['opening_ratio']==.25
    before=next(n for n in project.instances if n.id=='V1').parameters['opening_ratio']
    selected=apply_scenario(project,'throttle')
    assert next(n for n in selected.instances if n.id=='V1').parameters['opening_ratio']==.25
    assert next(n for n in project.instances if n.id=='V1').parameters['opening_ratio']==before
    raw['scenarios'][0]['overrides']={'gone':{'opening':25}}
    with pytest.raises(ValueError,match='gone'):normalize_prototype_export(data)
