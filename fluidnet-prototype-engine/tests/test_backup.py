import io
import json
from pathlib import Path
import zipfile

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.backup import backup_workspace, restore_workspace
from fn_engine.packages import ModuleStore
from fn_engine.storage import WorkspaceStore
from test_controls_storage import body, workspace
from test_module_versions import save_payload
from test_platform_contracts import custom_project


def test_online_snapshot_restores_drafts_runs_and_module_hashes(tmp_path):
    source, target = tmp_path/'source', tmp_path/'restored'
    with TestClient(create_app(data_root=source, module_storage_root=tmp_path/'modules')) as client:
        client.post('/api/v1/workspace',json={'data':workspace(),'expected_revision':0}).raise_for_status()
        result=client.post('/api/v1/runs',json=body()).json()
        published=client.post('/api/v1/modules/versions',json=save_payload())
        published.raise_for_status();release=published.json()
        project=custom_project().model_dump(mode='json')
        project['modules'][-1]=release['module']
        project['instances'][1].update(module_id='saved_valve',package=release['package'])
        expected=client.post('/api/v1/runs',json={'project':project}).json()
        assert expected['status']=='completed'
        backup=client.post('/api/v1/workspace/backup')
        assert backup.status_code==200 and backup.headers['content-type']=='application/zip'
        archive=zipfile.ZipFile(io.BytesIO(backup.content))
        manifest=json.loads(archive.read('backup.json'))
        assert manifest['revision']==1
        assert 'module-packages/module-programmable_valve/v1/module.py' in manifest['files']
        # Restore while the original remains live, then independently open the clone.
        restored=client.post('/api/v1/workspace/restore',content=backup.content)
        assert restored.status_code==200,restored.text
        target=Path(restored.json()['directory'])
        assert target!=source and client.get('/api/v1/workspace').json()['revision']==1
    with TestClient(create_app(data_root=target)) as client:
        assert client.get('/api/v1/workspace').json()['data']==workspace()
        record=client.get('/api/v1/runs/'+result['run_id']).json()
        assert record['status']=='completed' and record['frame']['variables']['script.control.state.count']==3
        modules=client.get('/api/v1/modules').json()['modules']
        refs=[m for m in modules if m['id']=='programmable_valve']
        assert len(refs)==1 and refs[0]['package_path'].startswith(str(target))
        saved=client.get('/api/v1/modules/saved_valve/versions/1').json()
        assert saved['package']==release['package']
        assert saved['module']['package_path'].startswith(str(target))
        project['modules'][-1]=saved['module']
        replay=client.post('/api/v1/runs',json={'project':project}).json()
        assert replay['status']=='completed'
        assert replay['frame']['variables']['V1.mass_flow_kg_s']==pytest.approx(expected['frame']['variables']['V1.mass_flow_kg_s'])


def test_restore_rejects_corruption_and_never_overwrites(tmp_path):
    storage=WorkspaceStore(tmp_path/'data')
    storage.save_workspace(workspace(),0)
    store=ModuleStore(Path(__file__).parents[1]/'modules',tmp_path/'modules')
    path=tmp_path/'good.zip'
    try:
        backup_workspace(storage,store,path)
        with pytest.raises(ValueError,match='已存在'):
            restore_workspace(path,tmp_path/'data')
        with pytest.raises(ValueError,match='已存在'):
            backup_workspace(storage,store,path)
    finally:
        storage.close()
    with zipfile.ZipFile(path) as original,zipfile.ZipFile(tmp_path/'bad.zip','w') as modified:
        for name in original.namelist():
            modified.writestr(name,b'corrupt' if name=='workspace.sqlite3' else original.read(name))
    with pytest.raises(ValueError,match='校验失败'):
        restore_workspace(tmp_path/'bad.zip',tmp_path/'bad-target')
    assert not (tmp_path/'bad-target').exists()


def test_restore_rejects_unlisted_files_and_path_traversal(tmp_path):
    path=tmp_path/'bad.zip'
    manifest={'format':'fluidnet-backup','version':1,'revision':0,
              'files':{'../outside':{'size':1,'sha256':''},'workspace.sqlite3':{'size':0,'sha256':''}}}
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('backup.json',json.dumps(manifest))
        archive.writestr('../outside',b'x')
        archive.writestr('workspace.sqlite3',b'')
    with pytest.raises(ValueError,match='不允许的文件路径'):restore_workspace(path,tmp_path/'restored')
    assert not (tmp_path/'outside').exists()


@pytest.mark.parametrize('manifest', [[], {'format':'fluidnet-backup','version':1}])
def test_restore_returns_validation_error_for_invalid_manifest(tmp_path, manifest):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as archive:
        archive.writestr('backup.json',json.dumps(manifest))
    with TestClient(create_app(data_root=tmp_path/'data')) as client:
        response=client.post('/api/v1/workspace/restore',content=data.getvalue())
        assert response.status_code==422
    assert not list(tmp_path.glob('restored-*'))


def test_restore_rejects_revision_mismatch_before_publishing(tmp_path):
    with TestClient(create_app(data_root=tmp_path/'data')) as client:
        backup=client.post('/api/v1/workspace/backup')
        original=zipfile.ZipFile(io.BytesIO(backup.content))
        modified=io.BytesIO()
        with zipfile.ZipFile(modified,'w') as archive:
            for name in original.namelist():
                payload=original.read(name)
                if name=='backup.json':
                    manifest=json.loads(payload);manifest['revision']=99
                    payload=json.dumps(manifest).encode()
                archive.writestr(name,payload)
        response=client.post('/api/v1/workspace/restore',content=modified.getvalue())
        assert response.status_code==422 and '修订号与数据库不一致' in response.text
    assert not list(tmp_path.glob('restored-*'))


def test_usage_reports_window_capacity_and_revisions_remain_readable(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        original=workspace()
        client.post('/api/v1/workspace',json={'data':original,'expected_revision':0}).raise_for_status()
        edited=workspace();edited['projects'][0]['control']='new draft'
        client.post('/api/v1/workspace',json={'data':edited,'expected_revision':1}).raise_for_status()
        old=client.get('/api/v1/workspace?revision=1').json()['data']
        assert client.post('/api/v1/workspace',json={'data':old,'expected_revision':2}).json()['revision']==3
        assert client.get('/api/v1/workspace').json()['data']==original
        usage=client.get('/api/v1/workspace/storage').json()
        assert usage['database_bytes']>0 and usage['free_disk_bytes']>0 and usage['revision_retention']==5


def test_cli_backup_restore_with_unicode_paths_and_live_directory_lock(tmp_path):
    from fn_engine.cli import main
    source=tmp_path/'原工作区 space';target=tmp_path/'恢复 space';backup=tmp_path/'备份 file.zip'
    storage=WorkspaceStore(source)
    storage.save_workspace(workspace(),0)
    args=['workspace','backup','--data-dir',str(source),'--output',str(backup)]
    try:
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code==1 and not backup.exists()
    finally:
        storage.close()
    main(args)
    main(['workspace','restore',str(backup),'--destination',str(target)])
    restored=WorkspaceStore(target)
    try:
        assert restored.workspace()['data']==workspace()
    finally:
        restored.close()
