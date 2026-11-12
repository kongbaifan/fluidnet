/* Module authoring and released definitions. Run transport and parameter transactions remain in the engine client. */
export const createModuleService = function ({request, modules, getBench, parameterDefinitions, normalizeProject,
  model, moduleFromManifest, testFlow, copyPanel, copyPresentation, output, dirty, render, persist, message}) {
  const clone = value => JSON.parse(JSON.stringify(value));
  function manifestPayload(m) {
    if (m.manifest) {
      const {package:ref, validation_evidence:evidence, ...definition} = m.manifest;
      if (m.frozen) return clone(definition);
      let contract = {};
      if (m.contractDraft !== undefined) {
        contract = JSON.parse(m.contractDraft);
        if (!contract || Array.isArray(contract) || typeof contract !== 'object') throw Error('模块契约必须是 JSON 对象');
        const invalid = Object.keys(contract).filter(k => !contractFields.includes(k));
        if (invalid.length) throw Error('契约中不能编辑字段：' + invalid.join('、'));
      }
      return {...definition, id:m.id, name:m.name, version:m.version, category:m.category,
        parameters:m.parameters, description:m.description, bank_names:m.bankNames,
        ports:m.ports.map(p => { const original=m.manifest.ports.find(item => item.id===p.id); return {id:p.id,label:p.label,domain:p.domain,direction:original?.direction === 'bidirectional' ? original.direction : p.direction,required:original?.required ?? true,circuit:original?.circuit || 'fluid'}; }),
        channels:m.channels.map(c => ({id:c.id,name:c.name,input_port:c.input,output_port:c.output,relation:c.kind,solver_model:m.manifest.channels.find(item=>item.id===c.id)?.solver_model || m.manifest.solver_model,enabled:c.enabled})),
        entrypoint:m.entrypoint, ...contract, source:{runtime:m.source.runtime, ...(m.designSource?.trim() ? {design:m.designSource} : {})}, runtime:'python',
        content_hash:null, definition_hash:null, package_path:null};
    }
    return m;
  }
  const contractFields = ['schema_version','sdk','applicability','execution_role','hydraulic_dependencies','dependency_mode','pure_evaluate','composite','name','category','description','entrypoint','solver_model','state_model','thermal_model','ports','channels','parameters','variables','bank_names'];
  function contractText(m) {
    if (m.contractDraft !== undefined) return m.contractDraft;
    const definition=manifestPayload(m);
    return JSON.stringify(Object.fromEntries(contractFields.filter(k=>definition[k] !== undefined).map(k=>[k,definition[k]])),null,2);
  }
  function moduleForInsert(id) {
    const draft=modules().find(m=>m.id===id);
    if (draft?.runtime !== 'python') return draft;
    if (!draft.publishedManifest) throw Error('请先校验并保存模块版本，再插入项目。');
    const target={...moduleFromManifest(clone(draft.publishedManifest)),frozen:true};
    copyPanel?.(draft,target);copyPresentation?.(draft,target);return target;
  }
  function insertionPlan(owner,id,pageId) {
    const page=owner.pages.find(item=>item.id===pageId);
    if(!page)throw Error('目标画布已不存在，请重新选择。');
    if(owner.run?.live || ['running','solving','paused'].includes(owner.run?.status))
      throw Error('请先停止目标项目的运行，再添加设备。');
    if(page.nodes.length>=64)throw Error('目标画布已达到 64 台设备，请选择其他画布。');
    const pinned=owner.moduleSnapshots?.[id],draft=modules().find(m=>m.id===id);
    // Imported projects may retain a usable snapshot without a published library copy.
    const available=pinned&&(!draft||(draft.runtime==='python'&&!draft.publishedManifest))?pinned:moduleForInsert(id);
    if(!available)throw Error('模块已不存在，请重新选择。');
    const bound=pinned || available;
    return {page,module:bound,availableVersion:available.version,
      usesPinnedVersion:!!owner.moduleSnapshots?.[id] && bound.runtime==='python' &&
        (bound.version!==available.version || bound.manifest?.definition_hash!==available.manifest?.definition_hash)};
  }
  function bindModule(owner, id, legacy=false) {
    owner.moduleSnapshots ||= {};
    if (owner.moduleSnapshots[id]) return owner.moduleSnapshots[id];
    const m=modules().find(item=>item.id===id);
    if (m?.runtime !== 'python') {
      if(m?.panelLayout||m?.drawing) {owner.moduleSnapshots[id]={...clone(m),parameterDefs:clone(m.parameterDefs||parameterDefinitions[m.kind]||[]),frozen:true};return owner.moduleSnapshots[id];}
      return m;
    }
    const source=m.publishedManifest || (legacy ? m.manifest : null);
    if (!source) throw Error('请先保存模块版本，再用于项目。');
    const snapshot={...moduleFromManifest(clone(source)),frozen:true};
    copyPanel?.(m,snapshot);
    copyPresentation?.(m,snapshot);
    owner.moduleSnapshots[id]=snapshot;
    return snapshot;
  }
  function pinProject(owner, legacy=false) {
    for (const n of owner.pages.flatMap(p=>p.nodes)) {
      const m=bindModule(owner,n.moduleId,legacy);
      if (m?.frozen && m.runtime==='python') n.package={module_id:m.id,version:`${m.version}.0.0`,content_hash:m.manifest.content_hash,definition_hash:m.manifest.definition_hash || null};
    }
  }
  function applyManifest(m, definition) {
    const keep={publishedManifest:m.publishedManifest,latestVersion:m.latestVersion,versions:m.versions,releaseNotes:m.releaseNotes};
    if(m.testConditions)keep.testConditions=clone(m.testConditions);
    if(m.panelLayout)keep.panelLayout=clone(m.panelLayout);
    const updated=moduleFromManifest(definition);copyPresentation?.(m,updated);
    Object.assign(m,updated,keep);
    parameterDefinitions[m.kind]=m.parameterDefs;
    delete m.contractDraft;
    m.dirty=true;
  }
  async function checkModule(m, apply=false) {
    try {
      const definition=manifestPayload(m);
      const before=JSON.stringify(definition);
      output(m,'正在校验契约、Python 语法和生命周期入口…');
      const result=await request('/modules/validate',definition);
      m.authoringDiagnostics=result.diagnostics;
      if (before!==JSON.stringify(manifestPayload(m))) { output(m,'校验期间草稿已变化，请重新校验当前内容。'); return false; }
      output(m,result.valid ? '✓ Pydantic 契约与默认值通过\n✓ Python 语法通过\n✓ Worker 入口与四阶段方法通过\n'+(definition.source.design ? '✓ design.py 的 design(ctx) 通过\n' : '')+'下一步：独立验证算法或保存新版本。' :result.diagnostics.map(d=>`${d.field || d.code}：${d.message}`).join('\n'));
      if (apply && result.valid) { applyManifest(m,definition); dirty(m); render(); }
      return result.valid;
    } catch(error) { m.authoringDiagnostics=error.detail?.diagnostics || (error.detail?.source_line ? [error.detail] : []); m.authoringReplay=error.detail?.replay; output(m,'校验失败：'+error.message); return false; }
  }
  // design.py on one library-value set. Returns display-unit proposals; the caller confirms.
  async function runDesign(m, bank) {
    const values=m.banks[bank], before=JSON.stringify(values), definition=manifestPayload(m);
    const parameters={};
    for (const spec of definition.parameters || []) {
      const value=values['param:'+spec.id];
      if (spec.value_type==='number' && value!==undefined) parameters[spec.id]=model.canonicalParameters(definition,{[spec.id]:value})[spec.id];
    }
    const result=await request('/modules/design',{module:definition,parameters});
    if (JSON.stringify(m.banks[bank])!==before) throw Error('计算期间库值已变化，请重新执行设计函数。');
    const changes=result.changes.map(change => {
      const spec=definition.parameters.find(p=>p.id===change.id);
      const display=value => model.toDisplay(spec,value);
      const variable=m.variables.find(v=>v.id==='param:'+change.id);
      return {...change, label:spec?.label || change.id, before:display(change.before), after:display(change.after), variableId:variable && spec.value_type==='number' ? variable.id : null};
    });
    return {changes, diagnostics:result.diagnostics, designHash:result.design_hash};
  }
  async function versions(m) {
    try { const result=await request(`/modules/${encodeURIComponent(m.id)}/versions`); m.versions=result.versions; m.latestVersion=result.versions.length ? Number(result.versions[0].package.version.split('.')[0]) : 0; render(); }
    catch(error) { output(m,'读取版本失败：'+error.message); }
  }
  async function loadVersion(m,version) {
    try {
      const result=await request(`/modules/${encodeURIComponent(m.id)}/versions/${version}`);
      applyManifest(m,result.module); m.publishedManifest=clone(result.module); m.dirty=false;
      if(result.module.sdk?.capabilities?.includes('composite.refrigeration.open.v1') && result.test_conditions?.host_project)m.testConditions=clone(result.test_conditions);
      persist(); render(); message(`已载入 v${version}；现有项目继续使用已绑定快照。`);
    } catch(error) { output(m,'载入失败：'+error.message); }
  }
  async function saveModule(m) {
    if (m.saving) return;
    m.saving=true; render();
    try {
      const definition=manifestPayload(m), before=JSON.stringify(definition);
      const test=clone(m.testConditions || {});
      if(definition.sdk?.capabilities?.includes('composite.refrigeration.open.v1') && !test.host_project)throw Error('开放设备组缺少宿主工况，请在已连接的制冷项目中重新封装后发布。');
      // Test the declared defaults on every save; prior bench results cannot authorize changed code.
      const bench=getBench();
      if (bench?.moduleId===m.id) Object.assign(test,test.host_project ? {dt_s:bench.run.step,duration_s:bench.run.step} : {inlet_pressure_pa:bench.boundary.inlet*1000,outlet_pressure_pa:bench.boundary.outlet*1000,temperature_k:bench.boundary.temperature+273.15,dt_s:bench.run.step,duration_s:bench.run.step});
      if(definition.execution_role && bench?.moduleId===m.id)test.fluid={fluid:bench.boundary.fluid || test.fluid?.fluid || 'Ammonia',phase_policy:'any'};
      output(m,test.host_project?'正在校验并代入原宿主网络试算，通过后写入新版本…':'正在校验并进行 Worker 试算，通过后写入新版本…');
      const release=await request('/modules/versions',{module:definition,expected_latest_version:m.latestVersion ?? (m.publishedManifest?.version || 0),release_notes:m.releaseNotes || '',test});
      let unchanged=false;
      try { unchanged=before===JSON.stringify(manifestPayload(m)); } catch { /* Keep incomplete JSON edited during the save. */ }
      m.latestVersion=release.module.version;
      m.publishedManifest=clone(release.module);
      if (unchanged) { applyManifest(m,release.module); m.dirty=false;m.authoringDiagnostics=[];delete m.authoringReplay; }
      output(m,`✓ v${release.module.version} 已保存到后端\n✓ ${test.host_project?'宿主网络试算通过，工况来源：'+test.host_project.name:'Worker 试算通过'+(testFlow(m,release.test_result.frame.variables)===null?'':'，流量 '+testFlow(m,release.test_result.frame.variables)+' kg/s')}\n源码 SHA-256：${release.package.content_hash}\n契约 SHA-256：${release.package.definition_hash}`+(unchanged?'':'\n保存期间的新编辑已保留为草稿。'));
      await versions(m);
      if (!persist()) { message(`后端 v${release.module.version} 已保存，浏览器草稿存储失败（存储空间不足），请导出工作区；内存中的修改未丢失。`,true); return; }
      message(`模块 v${release.module.version} 已保存；已有项目版本保持绑定。`);
    } catch(error) { m.authoringDiagnostics=error.detail?.diagnostics || (error.detail?.source_line ? [error.detail] : []);m.authoringReplay=error.detail?.replay;output(m,'版本未保存：'+error.message); message('版本保存失败，草稿已保留。',true); }
    finally { m.saving=false; render(); }
  }
  function newModule(id,name,category,baseId) {
    const base=modules().find(m=>m.id===baseId && m.manifest);
    if (!base) throw Error('请等待 Python 模块模板加载完成。');
    const definition={...clone(manifestPayload(base)),id,name,category,version:1,content_hash:null,definition_hash:null,package_path:null};
    const m=moduleFromManifest(definition); m.latestVersion=0; m.dirty=true;
    parameterDefinitions[m.kind]=m.parameterDefs;
    return m;
  }
  async function newTemplate(id,name,category,template) {
    const definition=await request('/modules/from-template',{id,name,category,template});
    const m=moduleFromManifest(definition);m.latestVersion=0;m.dirty=true;
    m.template=template;parameterDefinitions[m.kind]=m.parameterDefs;
    if(template==='pump')m.testConditions={inlet_pressure_pa:120000,outlet_pressure_pa:250000};
    if(template==='heat_exchanger')m.testConditions={channel_boundaries:{hot:{inlet_temperature_k:320,outlet_temperature_k:320},cold:{inlet_temperature_k:290,outlet_temperature_k:290}}};
    return m;
  }
  async function newComposite(owner,ids,id,name) {
    const sourceProject=await normalizeProject(owner);
    const definition=await request('/modules/composites/from-group',{project:sourceProject,instance_ids:ids,id,name});
    const m=moduleFromManifest(definition);m.latestVersion=0;m.dirty=true;
    if(definition.sdk?.capabilities?.includes('composite.refrigeration.open.v1'))m.testConditions=await request('/modules/composites/test-context',{project:sourceProject,instance_ids:ids,module:definition});
    else if(definition.sdk?.capabilities?.includes('composite.refrigeration.v1'))m.testConditions={fluid:clone(sourceProject.fluid),duration_s:.1,dt_s:.1};
    parameterDefinitions[m.kind]=m.parameterDefs;return m;
  }
  function updateContractItem(m,section,oldId,item,preserveValues=false) {
    const definition=manifestPayload(m), list=definition[section] || [];
    if (list.some(v=>v.id!==oldId && v.id===item.id)) throw Error('契约标识重复');
    const index=list.findIndex(v=>v.id===oldId);
    const previous=preserveValues?clone([m.values,...m.banks]):null;
    if(index<0) list.push(item); else list[index]=item;
    definition[section]=list; applyManifest(m,definition);
    if(previous)[m.values,...m.banks].forEach((values,i)=>{
      for(const [key,value] of Object.entries(previous[i]||{}))
        if(key!=='param:'+item.id&&Object.hasOwn(values,key))values[key]=clone(value);
    });
    dirty(m); render();
  }
  const displayUnits=[
    ['length','m','m',1],['length','m','mm',.001],['length','m','cm',.01],
    ['pressure','Pa','Pa',1],['pressure','Pa','kPa',1000],['pressure','Pa','MPa',1e6],['pressure','Pa','bar',1e5],
    ['temperature','K','K',1],['temperature','K','°C',1,-273.15],
    ['power','W','W',1],['power','W','kW',1000],
    ['mass_flow','kg/s','kg/s',1],['mass_flow','kg/s','kg/h',1/3600],
    ['dimensionless','1','1',1],['dimensionless','1','%',.01]
  ].map(([quantity,canonical_unit,display_unit,display_scale,display_offset=0])=>({quantity,canonical_unit,display_unit,display_scale,display_offset}));
  function parameterEditor(m,id) {
    if(m.runtime!=='python')throw Error('内置设备的参数请在项目设备窗口调整，或保存为型号复用。');
    const definition=manifestPayload(m),spec=definition.parameters.find(p=>p.id===id);
    if(id&&!spec)throw Error('参数已不存在，请重新打开。');
    const current=spec || {id:'',label:'',value_type:'number',default:0,minimum:null,maximum:null,writable:true,runtime:false,unit:null};
    const unit=current.unit,units=[unit?clone(unit):null];
    for(const choice of displayUnits){
      if(unit&&(choice.canonical_unit!==unit.canonical_unit || (choice.canonical_unit==='K'&&unit.quantity!=='temperature')))continue;
      const candidate={...choice,...(unit?{quantity:unit.quantity||choice.quantity}:{})};
      if(!units.some(item=>item&&item.display_unit===candidate.display_unit&&(item.display_scale??1)===candidate.display_scale&&(item.display_offset??0)===candidate.display_offset))units.push(candidate);
    }
    return {spec:clone(current),units};
  }
  function updateDisplayParameter(m,id,data) {
    const {spec,units}=parameterEditor(m,id),type=(id?spec.value_type:data.value_type)||'number';
    const item={...spec,id:id||String(data.id??'').trim(),label:String(data.label??'').trim(),value_type:type};
    if(!/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(item.id))throw Error('参数标识需以字母开头，仅包含字母、数字、下划线或连字符。');
    if(!item.label)throw Error('请输入参数名称。');
    if(type==='number'){
      const index=Number(data.unit);if(!Number.isInteger(index)||!Object.hasOwn(units,index))throw Error('请选择有效的单位。');
      item.unit=clone(units[index]);
      const convert=(value,optional=false)=>{
        if(String(value??'').trim()===''){if(optional)return null;throw Error('请填写默认值。');}
        const converted=model.toCanonical(item,Number(value));
        if(!Number.isFinite(converted))throw Error('默认值和范围必须是有限数值。');return converted;
      };
      item.default=convert(data.default);item.minimum=convert(data.minimum,true);item.maximum=convert(data.maximum,true);
      if(item.minimum!==null&&item.maximum!==null&&item.minimum>item.maximum)throw Error('最小值不能大于最大值。');
      if(item.minimum!==null&&item.default<item.minimum||item.maximum!==null&&item.default>item.maximum)throw Error('默认值必须在最小值和最大值之间。');
    }else if(type==='boolean'){
      if(!['true','false'].includes(data.default))throw Error('请选择是或否。');
      Object.assign(item,{default:data.default==='true',unit:null,minimum:null,maximum:null});
    }else if(type==='text')Object.assign(item,{default:String(data.default??''),unit:null,minimum:null,maximum:null});
    else throw Error('曲线参数请通过高级定义编辑。');
    updateContractItem(m,'parameters',id,item,true);
  }
  function updateMetadata(m,data) {
    const name=String(data.name??'').trim(),description=String(data.description??'').trim();
    if(!name)throw Error('请输入设备名称。');
    const previous=m.name;
    if(m.runtime==='python'){
      manifestPayload(m); // Validate any pending JSON before changing either representation.
      if(m.contractDraft!==undefined)m.contractDraft=JSON.stringify({...JSON.parse(m.contractDraft),name,description},null,2);
    }
    m.name=name;m.description=description;
    if(m.drawing?.label===previous)m.drawing.label=name;
    dirty(m);render();
  }
  return {manifestPayload,contractText,moduleForInsert,insertionPlan,bindModule,pinProject,applyManifest,checkModule,
    runDesign,versions,loadVersion,saveModule,newModule,newTemplate,newComposite,updateContractItem,parameterEditor,updateDisplayParameter,updateMetadata};
};

export default createModuleService;
