/* Project controls and durable workspace operations; all values use engine units. */
window.createProjectServices = function ({request, ui, normalize, health, authHeaders, pinProject, moduleFromManifest}) {
  // Each page owns its base revision. A different tab saving must never advance it.
  let revision = Number(ui.state().workspaceRevision || 0), ready = false;
  let saves = Promise.resolve();
  let projectRevisions={...(ui.state().projectRevisions||{})};
  const clone=value=>JSON.parse(JSON.stringify(value));
  const controls = window.FluidNetControls;
  function prepare(owner) { controls.normalize(owner); }
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
    const definition=controls.selectedScript(owner);
    // Preview must also work for preserved legacy text after selecting Python,
    // without requiring that the control be enabled on the project.
    const candidate=clone(owner);
    candidate.controlPrograms.forEach(program=>program.enabled=false);
    const project=await normalize(candidate);
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
  async function exportRunReport(id,format) {
    if(!['html','csv'].includes(format))throw Error('未知报告格式');
    const response=await fetch('/api/v1/runs/'+encodeURIComponent(id)+'/report.'+format,{headers:authHeaders()});
    if(!response.ok){const body=await response.json();throw Error(body.detail?.message || body.detail || '报告读取失败');}
    return response.blob();
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
  async function previewUpgrade(owner,id,version,migration=null) {
    return request('/project-upgrades/preview',{project:await normalize(owner),module_id:id,target_version:version,migration});
  }
  async function exchangeDocument(data) {
    if(data.format==='fluidnet-project' && data.schema===1)return clone(data);
    if(data.format==='fluidnet-studio-prototype') {
      const p=data.projects.find(p=>p.id===data.activeProject)||data.projects[0];
      return {format:'fluidnet-project',schema:1,project:clone(p),modules:clone(data.modules),
        models:clone(data.models||[]),charts:clone((data.charts?.extra||[]).filter(c=>c.projectId===p.id))};
    }
    if(data.schema_version!==1 || !Array.isArray(data.instances) || !Array.isArray(data.modules))
      throw Error('请选择单项目、完整原型或规范 Project JSON 文件。');
    const validation=await request('/projects/validate',data);
    if(!validation.valid)throw Error(validation.diagnostics.map(d=>d.message).join('；'));
    const definitions=new Map(data.modules.map(m=>[m.id,m]));
    const snapshots=Object.fromEntries(data.modules.map(m=>[m.id,{...moduleFromManifest(clone(m)),frozen:true}]));
    const display=(definition,values)=>Object.fromEntries(Object.entries(values).map(([id,value])=>{
      const spec=definition.parameters.find(p=>p.id===id);
      return [id,spec?.unit ? value/(spec.unit.display_scale ?? 1)+(spec.unit.display_offset ?? 0) : clone(value)];
    }));
    const pages=new Map(),nodes=new Map();
    for(const n of data.instances) {
      const definition=definitions.get(n.module_id),pageId=n.page_id || 'main';
      if(!pages.has(pageId))pages.set(pageId,{id:pageId,name:pageId,zoom:1,pan:[0,0],nodes:[],edges:[]});
      const defaults=Object.fromEntries(definition.parameters.map(p=>[p.id,clone(p.default)]));
      const params=display(definition,{...defaults,...n.parameters});
      const node={id:n.id,moduleId:n.module_id,name:n.name,x:n.position?.x ?? 100+nodes.size%5*180,
        y:n.position?.y ?? 150+Math.floor(nodes.size/5)*130,rotation:n.rotation||0,params,
        draft:display(definition,{...defaults,...n.parameters,...n.draft_parameters}),modelId:n.model_id||null,
        modelVersion:n.model_version||1,draftModelId:null,package:clone(n.package||null)};
      if((n.banks||[]).length>3)throw Error('当前画布最多支持三组设备库值。');
      if(n.banks?.length) {
        const banks=[0,1,2].map(i=>Object.fromEntries(Object.entries(display(definition,{...defaults,...n.banks[i]?.values})).map(([k,v])=>['param:'+k,v])));
        node.variableState={schema:1,values:{},draft:{},banks,bankNames:[0,1,2].map(i=>n.banks[i]?.name || snapshots[n.module_id].bankNames[i])};
      }
      nodes.set(n.id,{node,pageId});pages.get(pageId).nodes.push(node);
    }
    for(const c of data.connections||[]) {
      const pageId=nodes.get(c.source.instance_id).pageId;
      if(pageId!==nodes.get(c.target.instance_id).pageId)throw Error('跨画布连接暂不能导入，请先将相连设备放到同一页。');
      pages.get(pageId).edges.push([c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id]);
    }
    if(!pages.size)throw Error('规范项目没有设备。');
    const p=ui.makeProject(data.id,data.name,data.description||'',[...pages.values()][0]);
    Object.assign(p,{pages:[...pages.values()],activePage:pages.keys().next().value,moduleSnapshots:snapshots,
      fluid:data.fluid?.fluid||'Water',fluidConfig:clone(data.fluid||{}),fluidReference:data.fluid?.reference||'mass',
      circuitFluids:(data.circuit_fluids||[]).map(c=>({id:c.id,anchor:clone(c.anchor),fluid:c.fluid.fluid,fluidConfig:clone(c.fluid),fluidReference:c.fluid.reference})),
      solverOptions:clone(data.solver||{}),controllers:clone(data.controllers||[]),events:clone(data.events||[]),
      thermalCouplings:clone(data.thermal_couplings||[]),selectedVariables:clone(data.selected_variables||[]),
      controlPrograms:[],controlScripts:[],controlEnabled:false,controlInputs:'',controlOutputs:'',
      scenarios:(data.scenarios||[]).map(s=>({...clone(s),overrides:Object.fromEntries(Object.entries(s.overrides).map(([id,values])=>
        [id,display(definitions.get(nodes.get(id).node.moduleId),values)]))}))});
    const solver=data.solver||{};
    p.solver={mode:'dynamic',duration:60,dt:Math.min(10,solver.dynamic_step_s||.1),
      dynamicStep:solver.dynamic_step_s||.1,pressureAtol:solver.pressure_tolerance_pa??1,massAtol:solver.mass_tolerance_kg_s??1e-8,
      maxIter:solver.max_iterations??80,hydraulicMethod:solver.hydraulic_method||'dense',moduleMixedJacobian:Boolean(solver.module_mixed_jacobian)};
    controls.replaceScripts(p,data.control_scripts||[]);
    return {format:'fluidnet-project',schema:1,project:p,modules:Object.values(snapshots),models:[],charts:[]};
  }
  function upgradeDocument(owner,preview) {
    const document=projectDocument(owner),snapshot={...moduleFromManifest(clone(preview.module)),frozen:true};
    document.project.moduleSnapshots[snapshot.id]=snapshot;
    document.modules=document.modules.map(m=>m.id===snapshot.id?snapshot:m);
    const canonical=new Map(preview.project.instances.map(n=>[n.id,n]));
    const display=(values,partial=false)=>Object.fromEntries(preview.module.parameters.filter(p=>!partial || p.id in values)
      .map(p=>[p.id,p.unit?values[p.id]/p.unit.display_scale+p.unit.display_offset:clone(values[p.id])]));
    for(const pg of document.project.pages)for(const n of pg.nodes)if(n.moduleId===snapshot.id){
      const node=canonical.get(n.id);n.params=display(node.parameters);n.draft=display(node.draft_parameters);n.package=node.package;
      for(const [index,bank] of (n.variableState?.banks || []).entries()){
        for(const key of Object.keys(bank))if(key.startsWith('param:'))delete bank[key];
        const values=display(node.banks[index]?.values || node.parameters);
        for(const spec of preview.module.parameters)bank['param:'+spec.id]=clone(values[spec.id]);
      }
      for(const [field,values] of [['values',n.params],['draft',n.draft]])if(n.variableState?.[field]){
        for(const key of Object.keys(n.variableState[field]))if(key.startsWith('param:'))delete n.variableState[field][key];
        for(const [key,value] of Object.entries(values))n.variableState[field]['param:'+key]=clone(value);
      }
    }
    const affected=new Set(owner.pages.flatMap(pg=>pg.nodes).filter(n=>n.moduleId===snapshot.id).map(n=>n.id));
    const migration=preview.migration || {};
    const reference=key=>{
      const dot=key.indexOf('.');if(dot<0||!affected.has(key.slice(0,dot)))return key;
      const id=key.slice(0,dot),suffix=key.slice(dot+1);
      if(suffix in (migration.variables || {}))return id+'.'+migration.variables[suffix];
      const parts=suffix.split('.');if(parts[0]==='param')parts[1]=migration.parameters?.[parts[1]] || parts[1];else parts[0]=migration.ports?.[parts[0]] || migration.channels?.[parts[0]] || parts[0];
      return id+'.'+parts.join('.');
    };
    for(const pg of document.project.pages)for(const edge of pg.edges){
      if(affected.has(edge[1]))edge[2]=migration.ports?.[edge[2]] || edge[2];
      if(affected.has(edge[3]))edge[4]=migration.ports?.[edge[4]] || edge[4];
    }
    document.project.scenarios=clone(preview.project.scenarios);
    for(const scenario of document.project.scenarios || [])for(const id of Object.keys(scenario.overrides)) {
      scenario.overrides[id]=affected.has(id) ? display(scenario.overrides[id],true)
        : clone(owner.scenarios.find(s=>s.id===scenario.id).overrides[id]);
    }
    document.project.controllers=clone(preview.project.controllers);
    document.project.selectedVariables=clone(preview.project.selected_variables||[]);
    controls.replaceScripts(document.project,preview.project.control_scripts);
    for(const chart of document.charts || []){
      if(chart.canonicalKey)chart.canonicalKey=reference(chart.canonicalKey);
      if(chart.identifier)chart.identifier=reference(chart.identifier);
      if(affected.has(chart.nodeId) && chart.variableId){const old=chart.variableId;chart.variableId=migration.variables?.[old] || old;chart.sampleKey=chart.nodeId+':'+chart.variableId;}
    }
    for(const model of document.models || [])if(model.moduleId===snapshot.id){
      const before=owner.moduleSnapshots[snapshot.id].manifest.parameters;
      const values={};for(const spec of before){const target=migration.parameters?.[spec.id] ?? (preview.module.parameters.some(p=>p.id===spec.id)?spec.id:null);if(target&&spec.id in model.params){const canonical=spec.unit?(model.params[spec.id]-spec.unit.display_offset)*spec.unit.display_scale:model.params[spec.id];const conversion=migration.unit_conversions?.[spec.id];values[target]=conversion?canonical*conversion.scale+conversion.offset:canonical;}}
      model.params=display(Object.fromEntries(preview.module.parameters.map(p=>[p.id,p.id in values?values[p.id]:p.default])));model.sourceModuleVersion=preview.to_version;
    }
    document.project.run=ui.emptyRun();return document;
  }
  return {prepare,previewControl,loadWorkspace,saveWorkspace,refreshArchives,openArchive,deleteArchive,exportRunReport,
    projectDocument,exchangeDocument,saveProject,restoreProject,deleteProject,previewUpgrade,upgradeDocument,
    batchOptions:(id,revision)=>request('/projects/'+encodeURIComponent(id)+'/batch-options?revision='+revision),
    previewBatch:(id,body)=>request('/projects/'+encodeURIComponent(id)+'/batches/preview',body),
    createBatch:(id,body)=>request('/projects/'+encodeURIComponent(id)+'/batches',body),
    listBatches:(projectId,offset=0)=>request('/batches?'+new URLSearchParams({offset,...(projectId?{project_id:projectId}:{})})),
    readBatch:id=>request('/batches/'+encodeURIComponent(id)),
    startBatch:id=>request('/batches/'+encodeURIComponent(id)+'/start',{}),
    cancelBatch:id=>request('/batches/'+encodeURIComponent(id)+'/cancel',{}),
    deleteBatch:id=>request('/batches/'+encodeURIComponent(id)+'/delete',{}),
    batchCurve:(id,item,key)=>request('/batches/'+encodeURIComponent(id)+'/items/'+encodeURIComponent(item)+'/curve?'+new URLSearchParams({key})),
    stopBatchRun:id=>request('/runs/'+encodeURIComponent(id)+'/command',{action:'stop',command_id:crypto.randomUUID()}),
    exportBatch:async id=>{const response=await fetch('/api/v1/batches/'+encodeURIComponent(id)+'/export',{headers:authHeaders()});
      if(!response.ok){const result=await response.json();throw Error(result.detail?.message||result.detail||'导出失败');}return response.blob();},
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
