/* Multi-device proposals are read-only until one engine transaction accepts the batch. */
window.DeviceBatchEditor = (() => {
  const clone=value=>JSON.parse(JSON.stringify(value));
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function fields(node,moduleOf,engine) {
    const m=moduleOf(node),definition=m.manifest || engine.catalog.modules.find(d=>d.id===m.kind);
    if(!definition)return [];
    const bindings=m.manifest?{}:engine.catalog.prototype_parameter_bindings[m.kind]||{};
    return definition.parameters.map(spec=>({spec,key:Object.keys(bindings).find(k=>bindings[k]===spec.id)||spec.id}));
  }
  function signature(node,moduleOf,engine) {
    const m=moduleOf(node),definition=m.manifest || engine.catalog.modules.find(d=>d.id===m.kind);
    return JSON.stringify({id:definition?.id,version:definition?.version,hash:definition?.definition_hash,content:definition?.content_hash,source:definition?.source,
      parameters:definition?.parameters,bindings:fields(node,moduleOf,engine).map(f=>[f.key,f.spec.id])});
  }
  function snapshot(owner,nodes,moduleOf,engine) {
    return JSON.stringify({run:owner.run.id,live:!!owner.run.live,key:owner.run.parameterKey,
      nodes:nodes.map(n=>({id:n.id,params:n.params,draft:n.draft,modelId:n.modelId,modelVersion:n.modelVersion,
        draftModelId:n.draftModelId,draftModelVersion:n.draftModelVersion,definition:signature(n,moduleOf,engine)}))});
  }
  function controlOwner(owner,node,id) {
    if(!owner.run.live)return '';
    let frozen;
    try{frozen=JSON.parse(owner.run.parameterKey);}catch{/* Legacy state; backend remains authoritative. */}
    const pid=(frozen?.controllers||owner.controllers||[]).find(c=>c.instance_id===node.id&&c.parameter_id===id);
    if(pid)return 'PID '+pid.id;
    const script=(frozen?.controls||owner.controlPrograms||owner.controlScripts||[]).find(s=>s.enabled&&s.language!=='legacy'&&(s.outputs||[]).includes(node.id+'.param.'+id));
    return script?'控制脚本 '+(script.name||script.id):'';
  }
  function parseValue(raw,spec){
    const type=spec.value_type||'number';
    if(type==='boolean'){
      if(!['true','false'].includes(raw))throw Error(spec.label+' 请选择是或否。');
      return raw==='true';
    }
    if(type==='text')return String(raw??'');
    if(type==='curve'){
      let value;try{value=JSON.parse(raw);}catch{throw Error(spec.label+' 必须是JSON点对数组。');}
      if(!Array.isArray(value)||!value.every(row=>Array.isArray(row)&&row.length===2&&row.every(v=>typeof v==='number'&&Number.isFinite(v))))throw Error(spec.label+' 必须是有限数值点对数组。');
      return value;
    }
    if(raw==null||!String(raw).trim()||!Number.isFinite(Number(raw)))throw Error(spec.label+' 必须是有限数值。');
    const value=Number(raw),canonical=window.FluidNetProjectModel.toCanonical(spec,value);
    if(spec.minimum!=null&&canonical<spec.minimum||spec.maximum!=null&&canonical>spec.maximum)throw Error(spec.label+' 超出声明范围。');
    return value;
  }
  function checkEntries(owner,entries,moduleOf,engine) {
    if(!entries.length)throw Error('请至少选择一台设备。');
    if(new Set(entries.map(e=>e.node.id)).size!==entries.length)throw Error('设备选择重复。');
    const first=signature(entries[0].node,moduleOf,engine);
    for(const {node,proposed} of entries){
      if(signature(node,moduleOf,engine)!==first)throw Error('设备模块版本或参数合同不同，请分批编辑。');
      const map=new Map(fields(node,moduleOf,engine).map(f=>[f.key,f.spec]));
      for(const [key,value] of Object.entries(proposed)){
        const spec=map.get(key);if(!spec||spec.writable===false)throw Error(node.id+' 的参数 '+key+' 不可写。');
        if(owner.run.live&&!same(node.params[key],value)){
          if(!spec.runtime)throw Error(node.id+' · '+spec.label+' 不能在运行中修改，请停止后应用。');
          const controller=controlOwner(owner,node,spec.id);
          if(controller)throw Error(node.id+' · '+spec.label+' 由 '+controller+' 接管，整批未应用。');
        }
      }
    }
  }
  function create({getState,project,moduleOf,engine,deviceParamSpecs,openDialog,closeDialog,esc,msg}){
    let serial=0;
    const show=value=>typeof value==='object'?JSON.stringify(value):String(value??'—');
    function open(){
      const owner=project(),state=getState(),run=owner.run;
      const all=owner.pages.flatMap(page=>page.nodes.map(node=>({node,page})));
      const modules=[...new Set(all.filter(({node})=>fields(node,moduleOf,engine).some(f=>f.spec.writable!==false)).map(({node})=>node.moduleId))];
      if(!modules.length)throw Error('项目中没有可批量编辑的设备。');
      const token=++serial;
      const assertProject=()=>{
        window.FluidNetProjectState.assertCurrent(getState(),owner);
        if(getState().activeProject!==owner.id||owner.run!==run||serial!==token)throw Error('项目或运行已变化，请重新打开批量编辑。');
      };
      openDialog('批量编辑设备','先按模块筛选，再选择当前项目各画布上的设备。',
        `<label class="field"><span>设备模块</span><select name="batch-module" aria-label="批量设备模块">${modules.map(id=>{const n=all.find(i=>i.node.moduleId===id).node;return `<option value="${esc(id)}">${esc(moduleOf(n).name)} · ${all.filter(i=>i.node.moduleId===id).length} 台</option>`;}).join('')}</select></label>`,data=>{
          assertProject();const items=all.filter(i=>i.node.moduleId===data['batch-module']);
          if(!items.length)throw Error('请选择有效模块。');
          edit(items);
        },'选择设备与参数',true);
      function edit(items){
        const source=items[0].node,definition=moduleOf(source).manifest||engine.catalog.modules.find(d=>d.id===moduleOf(source).kind);
        const specs=fields(source,moduleOf,engine).filter(f=>f.spec.writable!==false);
        const uiSpecs=deviceParamSpecs(source),baseline=new Map(items.map(({node})=>[node.id,snapshot(owner,[node],moduleOf,engine)]));
        const compatibleModels=state.models.filter(m=>m.moduleId===source.moduleId&&!m.archived);
        const rows=specs.map(({key,spec})=>{
          const display=uiSpecs.find(p=>p.id===key),value=source.draft[key]??source.params[key];
          const attr=`name="batch-value:${esc(key)}" aria-label="批量 ${esc(spec.label)}"`;
          const input=spec.value_type==='boolean'?`<select ${attr}><option value="true" ${value===true?'selected':''}>是</option><option value="false" ${value===false?'selected':''}>否</option></select>`
            :spec.value_type==='curve'?`<textarea ${attr} rows="2">${esc(show(value))}</textarea>`
            :`<input ${attr} type="${spec.value_type==='text'?'text':'number'}" step="any" value="${esc(show(value))}">`;
          return `<tr><td><label class="check-label"><input type="checkbox" name="batch-change:${esc(key)}" aria-label="修改 ${esc(spec.label)}">${esc(spec.label)}</label></td><td>${input}</td><td>${esc(display?.unit?.display_unit||spec.unit?.display_unit||'')}</td></tr>`;
        }).join('');
        openDialog('批量编辑 · '+moduleOf(source).name,'勾选要修改的字段；未勾选字段及其待应用草稿会保留。选择型号时先载入型号参数，再叠加勾选字段；改动型号值后作为自定义参数应用。',
          `<section><h3>选择设备（含跨页）</h3><div class="fields">${items.map(({node,page})=>`<label class="check-label"><input type="checkbox" name="batch-node:${esc(node.id)}" aria-label="选择设备 ${esc(node.id)}" checked>${esc(page.name)} · ${esc(node.id)} · ${esc(node.name)}</label>`).join('')}</div></section>
          <label class="field"><span>统一型号</span><select name="batch-model" aria-label="批量型号"><option value="">保持各自型号</option>${compatibleModels.map(m=>`<option value="${esc(m.id)}">${esc(m.name)} · 型号v${esc(m.version)}</option>`).join('')}</select></label>
          <div class="table-wrap"><table><thead><tr><th>修改字段</th><th>统一值</th><th>显示单位</th></tr></thead><tbody>${rows}</tbody></table></div>`,data=>{
            assertProject();const nodes=items.filter(({node})=>data['batch-node:'+node.id]).map(i=>i.node);
            for(const n of nodes){window.FluidNetProjectState.node(owner,n);if(snapshot(owner,[n],moduleOf,engine)!==baseline.get(n.id))throw Error(n.id+' 的参数、草稿或模块版本已变化，请重新选择。');}
            const selectedSource=data['batch-model']?state.models.find(m=>m.id===data['batch-model']):null;
            const selected=selectedSource?clone(selectedSource):null;
            if(data['batch-model']&&(!selected||selected.archived))throw Error('所选型号已失效。');
            const proposed={};
            if(selected){
              window.EquipmentSelection.assertModelCompatible(selected,definition);
              if(selected.moduleVersion!=null&&selected.moduleVersion!==definition.version)throw Error('型号绑定版本与设备不同。');
              for(const [key,value] of Object.entries(selected.params)){
                if(!specs.some(f=>f.key===key))throw Error('型号包含未声明或不可写参数 '+key+'，请先检查型号。');
                proposed[key]=clone(value);
              }
              if(!Object.keys(proposed).length)throw Error('所选型号没有可应用参数。');
            }
            for(const {key,spec} of specs)if(data['batch-change:'+key]){
              // Legacy built-ins use display aliases; their editor's min/max are already display values.
              const display=uiSpecs.find(p=>p.id===key);
              const parsed=moduleOf(source).manifest?parseValue(data['batch-value:'+key],spec):parseValue(data['batch-value:'+key],{...spec,unit:null,minimum:display?.minimum,maximum:display?.maximum});
              proposed[key]=parsed;
            }
            if(!Object.keys(proposed).length&&!selected)throw Error('请勾选修改字段或选择型号。');
            const exactModel=selected&&same(proposed,selected.params);
            const entries=nodes.map(node=>({node,proposed:clone(proposed),...(exactModel?{model:{id:selected.id,version:selected.version}}:{})}));
            checkEntries(owner,entries,moduleOf,engine);preview(entries,selected);
          },'预览逐台差异',true);
      }
      function preview(entries,selected,error=''){
        const before=snapshot(owner,entries.map(e=>e.node),moduleOf,engine),modelBefore=selected?JSON.stringify(selected):null;
        const lines=entries.flatMap(({node,proposed})=>Object.entries(proposed).map(([key,value])=>{
          const spec=deviceParamSpecs(node).find(p=>p.id===key);
          return `<tr><td>${esc(node.id+' · '+node.name)}</td><td>${esc(spec?.label||key)}</td><td>${esc(show(node.params[key]))}</td><td>${esc(show(node.draft[key]))}</td><td>${esc(show(value))}</td><td>${esc(spec?.unit?.display_unit||'')}</td></tr>`;
        })).join('');
        openDialog('批量应用预览',`${entries.length} 台设备${selected?(entries[0].model?' · 型号 ':' · 自定义参数，基于型号 ')+selected.name:''}。确认后整批应用；任一检查失败则整批保留原值。`,
          `<div data-device-batch-preview>${error?`<p class="notice" role="alert">${esc(error)}</p>`:''}<div class="table-wrap"><table><thead><tr><th>设备</th><th>参数</th><th>已应用</th><th>已有草稿</th><th>本次应用</th><th>单位</th></tr></thead><tbody>${lines}</tbody></table></div></div>`,()=>{
            assertProject();for(const {node} of entries)window.FluidNetProjectState.node(owner,node);
            if(snapshot(owner,entries.map(e=>e.node),moduleOf,engine)!==before)throw Error('预览后设备参数、草稿或运行已变化，请重新编辑。');
            if(selected&&JSON.stringify(state.models.find(m=>m.id===selected.id))!==modelBefore)throw Error('型号已变化，请重新预览。');
            checkEntries(owner,entries,moduleOf,engine);
            openDialog('正在整批应用',`${entries.length} 台设备`, `<p data-device-batch-pending="${token}">正在等待整批应用结果…</p>`);
            const active=()=>document.querySelector(`[data-device-batch-pending="${token}"]`);
            engine.applyParameterBatch(owner,entries).then(()=>{
              if(active())closeDialog();msg(`已整批应用 ${entries.length} 台设备。`);
            }).catch(failure=>{if(active())preview(entries,selected,'整批应用未完成：'+failure.message);});
          },'确认整批应用',true);
      }
    }
    return {open};
  }
  return {fields,signature,snapshot,controlOwner,parseValue,checkEntries,create};
})();
