/* Project controls and durable workspace operations; all values use engine units. */
window.createProjectServices = function ({request, ui, normalize, health, authHeaders}) {
  // Each page owns its base revision. A different tab saving must never advance it.
  let revision = Number(ui.state().workspaceRevision || 0), ready = false;
  let saves = Promise.resolve();
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
    ui.persist();ui.render();
    return receipt;
  }
  return {prepare,previewControl,loadWorkspace,saveWorkspace,refreshArchives,openArchive,deleteArchive,
    workspaceInfo:()=>Promise.all([request('/workspace/storage'),request('/workspace/revisions')]),
    downloadBackup,
    restoreBackup:async file=> (await backupRequest('restore',file)).json(),restoreRevision};
};
