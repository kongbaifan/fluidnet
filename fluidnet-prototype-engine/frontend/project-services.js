/* Project controls and durable workspace operations; all values use engine units. */
window.createProjectServices = function ({request, ui, normalize, health, authHeaders, pinProject, moduleFromManifest}) {
  // Each page owns its base revision. A different tab saving must never advance it.
  let revision = Number(ui.state().workspaceRevision || 0), ready = false;
  let saves = Promise.resolve();
  let projectRevisions={...(ui.state().projectRevisions||{})};
  const clone=value=>JSON.parse(JSON.stringify(value));
  function script(owner) {
    if (owner.controlLanguage !== 'python') throw Error('请先将旧脚本迁移为 Python，再启用控制。');
    const names = value => [...new Set((value || '').split(/[\s,，]+/).filter(Boolean))];
    return {id:'control', language:'python', enabled:!!owner.controlEnabled, source:owner.control,
      sample_s:Number(owner.controlConfig.period)/1000, inputs:names(owner.controlInputs), outputs:names(owner.controlOutputs)};
  }
  function prepare(owner) { owner.controlScripts = owner.controlEnabled ? [script(owner)] : []; }
  async function loadWorkspace(force=false) {
    if (!health()?.capabilities?.persistent_workspace) return;
    const remote = await request('/workspace');
    if (remote.data && (force || !ui.state().dirty)) {
      ui.restoreWorkspace(remote.data);
      revision=remote.revision;
      projectRevisions={...(remote.project_revisions||{})};ui.state().projectRevisions=projectRevisions;
      ui.state().projectSavedKeys=Object.fromEntries(ui.state().projects.map(p=>[p.id,ui.parameterKey(p)]));
      ui.state().workspaceRevision=revision;
      ui.persist();
    } else if (!remote.data) {
      revision=0;
    } else {
      ui.message('已保留本地未保存草稿；可导出草稿或载入服务器工作区。',true);
    }
    ready=true;
  }
  function saveWorkspace(data) {
    if (!health()?.capabilities?.persistent_workspace || !ready) return Promise.reject(Error('工作区尚未连接，当前草稿仅保存在浏览器；请重试或导出备份。'));
    const job = saves.catch(()=>{}).then(async()=>{
      const result=await request('/workspace',{data,expected_revision:revision});
      revision=result.revision;
      projectRevisions={...(result.project_revisions||{})};ui.state().projectRevisions=projectRevisions;
      ui.state().projectSavedKeys=Object.fromEntries(data.projects.map(p=>[p.id,ui.parameterKey(p)]));
      ui.state().workspaceRevision=revision;
      return result;
    });
    saves=job;
    return job;
  }
  async function previewControl(owner) {
    const definition=script(owner);
    // Preview must also work for preserved legacy text after selecting Python,
    // without requiring that the control be enabled on the project.
    const project=await normalize({...owner,controlEnabled:false});
    return request('/controls/preview',{project,script:definition});
  }
  async function refreshArchives() {
    if (!health()) return;
    try { const result=await request('/runs'); ui.archives(result.runs || []); }
    catch(error) { ui.message('运行档案读取失败：'+error.message,true); }
  }
  async function openArchive(id) {
    const record=await request('/runs/'+encodeURIComponent(id));
    const overview=await request(`/runs/${encodeURIComponent(id)}/overview`);
    ui.showArchive(record,overview);
  }
  async function deleteArchive(id) {
    await request('/runs/'+encodeURIComponent(id)+'/delete',{});
    await refreshArchives();
  }
  async function backupRequest(path,body) {
    const response=await fetch('/api/v1/workspace/'+path,{method:'POST',headers:authHeaders(),body});
    if(!response.ok){const data=await response.json();throw Error(typeof data.detail==='string'?data.detail:data.detail?.message||'工作区操作失败');}
    return response;
  }
  async function downloadBackup() {
    const response=await backupRequest('backup');
    if(response.status!==200 || response.headers.get('Content-Type')?.split(';')[0]!=='application/zip')throw Error('备份下载未返回 ZIP 文件，请重试。');
    const blob=await response.blob();
    const signature=new Uint8Array(await blob.slice(0,4).arrayBuffer());
    if(signature.length!==4 || ![0x50,0x4b,0x03,0x04].every((value,index)=>signature[index]===value))throw Error('备份文件为空或格式不正确，请重试。');
    return blob;
  }
  async function restoreRevision(number) {
    const remote=await request('/workspace?revision='+number);
    ui.validateWorkspace(remote.data);
    const receipt=await saveWorkspace(remote.data);
    ui.restoreWorkspace(remote.data);
    ui.state().workspaceRevision=receipt.revision;ui.state().savedAt=receipt.saved_at;
    ui.state().projectRevisions={...projectRevisions};
    ui.persist();ui.render();
    return receipt;
  }
  function projectDocument(owner) {
    prepare(owner);
    pinProject(owner);
    const p=clone(owner),used=new Set(p.pages.flatMap(pg=>pg.nodes.map(n=>n.moduleId)));
    p.moduleSnapshots=Object.fromEntries([...used].map(id=>[id,clone(p.moduleSnapshots?.[id]||ui.state().modules.find(m=>m.id===id))]));
    return {format:'fluidnet-project',schema:1,project:p,modules:Object.values(p.moduleSnapshots),
      models:clone(ui.state().models.filter(m=>used.has(m.moduleId))),charts:clone(ui.state().charts.extra.filter(c=>c.projectId===p.id))};
  }
  function projectReceipt(id,receipt) {
    projectRevisions[id]=receipt.revision;ui.state().projectRevisions={...projectRevisions};
    // A project save merges into the server's latest workspace. Do not authorize a
    // later whole-workspace overwrite if this page never saw concurrent changes.
    if(revision===receipt.previous_workspace_revision){revision=receipt.workspace_revision;ui.state().workspaceRevision=revision;}
  }
  async function saveProject(owner,document=projectDocument(owner)) {
    if(!ready)throw Error('工作区尚未连接');
    if(revision===0)await saveWorkspace(clone(ui.state()));
    const base=ui.parameterKey(owner),data=clone(document);data.project.dirty=false;
    const receipt=await request('/projects/'+encodeURIComponent(owner.id),{document:data,expected_revision:projectRevisions[owner.id]||0});
    projectReceipt(owner.id,receipt);
    if(base===ui.parameterKey(owner)){
      owner.dirty=false;ui.state().projectSavedKeys||={};ui.state().projectSavedKeys[owner.id]=base;
    }
    ui.persist();return receipt;
  }
  async function restoreProject(id,number) {
    const receipt=await request('/projects/'+encodeURIComponent(id)+'/restore',{revision:number,expected_revision:projectRevisions[id]||0});
    projectReceipt(id,receipt);return receipt;
  }
  async function deleteProject(id) {
    if(!projectRevisions[id])return;
    const receipt=await request('/projects/'+encodeURIComponent(id)+'/delete',{expected_revision:projectRevisions[id]});
    projectReceipt(id,receipt);return receipt;
  }
  async function previewUpgrade(owner,id,version) {
    return request('/project-upgrades/preview',{project:await normalize(owner),module_id:id,target_version:version});
  }
  function upgradeDocument(owner,preview) {
    const document=projectDocument(owner),snapshot={...moduleFromManifest(clone(preview.module)),frozen:true};
    document.project.moduleSnapshots[snapshot.id]=snapshot;
    document.modules=document.modules.map(m=>m.id===snapshot.id?snapshot:m);
    const canonical=new Map(preview.project.instances.map(n=>[n.id,n]));
    const display=values=>Object.fromEntries(preview.module.parameters.map(p=>[p.id,p.unit?values[p.id]/p.unit.display_scale+p.unit.display_offset:clone(values[p.id])]));
    for(const pg of document.project.pages)for(const n of pg.nodes)if(n.moduleId===snapshot.id){
      const node=canonical.get(n.id);n.params=display(node.parameters);n.draft=display(node.draft_parameters);n.package=node.package;
      for(const bank of n.variableState?.banks||[])for(const spec of preview.module.parameters){
        const k='param:'+spec.id;if(!(k in bank))bank[k]=clone(n.params[spec.id]);
      }
    }
    document.project.run=ui.emptyRun();return document;
  }
  return {prepare,previewControl,loadWorkspace,saveWorkspace,refreshArchives,openArchive,deleteArchive,
    projectDocument,saveProject,restoreProject,deleteProject,previewUpgrade,upgradeDocument,
    projectHistory:id=>request('/projects/'+encodeURIComponent(id)+'/revisions'),
    listProjects:()=>request('/projects'),readProject:async id=>{const result=await request('/projects/'+encodeURIComponent(id));projectRevisions[id]=result.revision;ui.state().projectRevisions={...projectRevisions};return result;},
    validateCandidate:async owner=>request('/projects/validate',await normalize(owner)),
    moduleReleases:id=>request('/modules/'+encodeURIComponent(id)+'/versions'),
    runMetadata:owner=>({scenario_id:owner.activeScenarioId||null,project_revision:ui.state().projectSavedKeys?.[owner.id]===ui.parameterKey(owner)?projectRevisions[owner.id]||null:null}),
    comparison:async(left,right)=>Promise.all([left,right].map(async id=>({record:await request('/runs/'+id),overview:await request('/runs/'+id+'/overview')}))),
    workspaceInfo:()=>Promise.all([request('/workspace/storage'),request('/workspace/revisions')]),
    downloadBackup,
    restoreBackup:async file=> (await backupRequest('restore',file)).json(),restoreRevision};
};
