import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.backup import backup_workspace, restore_workspace
from fn_engine.packages import ModuleStore, load_module_package
from fn_engine.runtime import module_content_hash, module_definition_hash, module_source
from fn_engine.storage import WorkspaceStore
from test_controls_storage import body, workspace
from test_module_versions import save_payload
from test_platform_contracts import custom_module, custom_project

SEED_MODULES = Path(__file__).parents[1] / 'modules'
DESIGN_SOURCE = '''def design(ctx):
    rho = ctx.fluid.state_pt(101325.0, 293.15).density_kg_m3
    ctx.set("kv_m3_h", round(10.0 * (rho / 1000.0) ** 0.5 / ctx.parameter("opening_ratio"), 6))
'''


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


def write_module_version(root, module_id, design=None, version=1):
    """按 ModuleStore.save 的落盘布局构造模块版本目录（含正确 definition_hash）。"""
    module=custom_module().model_copy(deep=True,update={
        'id':module_id,'name':module_id,'version':version,
        'content_hash':None,'definition_hash':None,'package_path':None})
    module.source={'runtime':module_source(module),**({'design':design} if design is not None else {})}
    module.content_hash=module_content_hash(module)
    module.definition_hash=module_definition_hash(module)
    directory=root/f'module-{module.id}'/f'v{version}'
    directory.mkdir(parents=True)
    (directory/'manifest.json').write_text(json.dumps(
        module.model_dump(mode='json',exclude={'source','package_path'}),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (directory/'module.py').write_text(module.source['runtime'],encoding='utf-8',newline='')
    if design is not None:
        (directory/'design.py').write_text(design,encoding='utf-8',newline='')
    (directory/'release.json').write_text(json.dumps(
        {'created_at':'2026-01-01T00:00:00+00:00','release_notes':'备份回归','tested':True},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return directory,load_module_package(directory)


def make_backup(tmp_path):
    """在独立数据目录中生成一次备份，返回 (备份路径, 清单)。"""
    storage=WorkspaceStore(tmp_path/'data')
    store=ModuleStore(SEED_MODULES,tmp_path/'modules')
    try:
        storage.save_workspace(workspace(),0)
        path=tmp_path/'backup.zip'
        return path,backup_workspace(storage,store,path)
    finally:
        storage.close()


def test_backup_copies_design_py_and_restore_keeps_definition_hash(tmp_path):
    package,original=write_module_version(tmp_path/'modules','design_valve',DESIGN_SOURCE)
    backup,manifest=make_backup(tmp_path)
    name='module-packages/module-design_valve/v1/design.py'
    assert name in manifest['files']
    assert manifest['files'][name]=={'sha256':hashlib.sha256(DESIGN_SOURCE.encode('utf-8')).hexdigest(),
                                     'size':(package/'design.py').stat().st_size}
    restored=restore_workspace(backup,tmp_path/'restored')
    assert restored['files']==manifest['files']
    restored_package=tmp_path/'restored'/'module-packages/module-design_valve/v1'
    assert (restored_package/'design.py').read_text(encoding='utf-8')==DESIGN_SOURCE
    reloaded=load_module_package(restored_package)
    assert reloaded.source['design']==DESIGN_SOURCE
    assert reloaded.content_hash==original.content_hash
    assert reloaded.definition_hash==original.definition_hash==module_definition_hash(reloaded)


def test_backup_restores_legacy_module_version_without_design_py(tmp_path):
    package,original=write_module_version(tmp_path/'modules','legacy_valve')
    assert not (package/'design.py').exists()
    backup,manifest=make_backup(tmp_path)
    assert 'module-packages/module-legacy_valve/v1/module.py' in manifest['files']
    assert 'module-packages/module-legacy_valve/v1/design.py' not in manifest['files']
    restore_workspace(backup,tmp_path/'restored')
    restored_package=tmp_path/'restored'/'module-packages/module-legacy_valve/v1'
    assert sorted(p.name for p in restored_package.iterdir())==['manifest.json','module.py','release.json']
    reloaded=load_module_package(restored_package)
    assert 'design' not in reloaded.source
    assert reloaded.definition_hash==original.definition_hash


def test_restore_still_rejects_files_outside_the_fixed_allowlist(tmp_path):
    write_module_version(tmp_path/'modules','legacy_valve')
    backup,manifest=make_backup(tmp_path)
    extra='module-packages/module-legacy_valve/v1/evil.py'
    payload=b'print(1)\n'
    with zipfile.ZipFile(backup) as original:
        members={name:original.read(name) for name in original.namelist()}
    manifest['files'][extra]={'sha256':hashlib.sha256(payload).hexdigest(),'size':len(payload)}
    members['backup.json']=json.dumps(manifest).encode()
    members[extra]=payload
    tampered=tmp_path/'tampered.zip'
    with zipfile.ZipFile(tampered,'w') as archive:
        for name,content in members.items():
            archive.writestr(name,content)
    with pytest.raises(ValueError,match='不允许的文件路径'):
        restore_workspace(tampered,tmp_path/'tampered-target')
    assert not (tmp_path/'tampered-target').exists()
