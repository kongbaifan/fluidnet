/* Validate the complete edit before any write; commit all local patches in one turn. */
window.FluidNetParameterBatch = (() => {
  const clone=value=>value===undefined?undefined:JSON.parse(JSON.stringify(value));
  const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function value(spec,input) {
    const type=spec.value_type||'number';
    if(type==='number') {
      if(typeof input!=='number'||!Number.isFinite(input))throw Error(`${spec.label} 必须是有限数值`);
      const canonical=window.FluidNetProjectModel.toCanonical(spec,input);
      if(!Number.isFinite(canonical)||spec.minimum!=null&&canonical<spec.minimum||spec.maximum!=null&&canonical>spec.maximum)throw Error(`${spec.label} 超出范围`);
      return canonical;
    }
    if(type==='boolean'&&typeof input!=='boolean'||type==='text'&&typeof input!=='string'||
       type==='curve'&&(!Array.isArray(input)||!input.every(row=>Array.isArray(row)&&row.length===2&&row.every(Number.isFinite))))throw Error(`${spec.label} 参数类型无效`);
    return clone(input);
  }
  function controller(owner,id,parameter) {
    if(!owner.run.live)return '';
    let frozen;
    try{frozen=JSON.parse(owner.run.parameterKey);}catch{throw Error('当前运行缺少控制归属快照，请停止后编辑');}
    const pid=(frozen.controllers||[]).find(c=>c.instance_id===id&&c.parameter_id===parameter);
    if(pid)return 'PID '+pid.id;
    const script=(frozen.controls||frozen.control_scripts||[]).find(c=>c.enabled&&(c.outputs||[]).includes(`${id}.param.${parameter}`));
    return script?'控制脚本 '+(script.name||script.id):'';
  }
  function prepare(state,owner,entries,describe) {
    window.FluidNetProjectState.assertCurrent(state,owner);
    if(!Array.isArray(entries)||!entries.length)throw Error('请选择设备与修改项');
    const seen=new Set(),values={};
    const items=entries.map(entry=>{
      const node=window.FluidNetProjectState.node(owner,entry.node);
      if(seen.has(node.id))throw Error('批量设备重复');seen.add(node.id);
      const {definition,bindings}=describe(node);
      if(!definition?.parameters)throw Error('设备参数合同不存在');
      if(!entry.proposed||typeof entry.proposed!=='object'||Array.isArray(entry.proposed))throw Error('批量参数格式无效');
      let selected;
      if(entry.model) {
        selected=state.models.find(m=>m.id===entry.model.id);
        if(!selected||selected.archived||selected.version!==entry.model.version||selected.moduleId!==node.moduleId||
          selected.moduleVersion!=null&&selected.moduleVersion!==definition.version)throw Error('型号或模块版本已变化，请重新预览');
        window.EquipmentSelection?.assertModelCompatible(selected,definition);
        if(!Object.entries(selected.params).every(([key,v])=>equal(entry.proposed[key],v)))throw Error('型号参数不完整，请重新选择型号');
      }
      const parameterIds=new Set();
      const edits=Object.entries(entry.proposed).map(([key,input])=>{
        const id=bindings?.[key]||key,spec=definition.parameters.find(p=>p.id===id);
        if(!spec)throw Error(`${node.id}.${key} 不是已声明参数`);
        if(parameterIds.has(id)||Object.keys(node.params).some(other=>other!==key&&(bindings?.[other]||other)===id))throw Error(`${node.id}.${id} 使用了重复的参数别名`);
        parameterIds.add(id);
        const canonical=value(spec,input),changed=!equal(input,node.params[key]);
        if(changed) {
          if(spec.writable===false)throw Error(`${node.id} ${spec.label} 是只读参数`);
          if(owner.run.live&&!spec.runtime)throw Error(`${node.id} ${spec.label} 不能在运行中修改`);
          const owned=controller(owner,node.id,id);if(owned)throw Error(`${node.id} ${spec.label} 由 ${owned} 控制`);
          values[`${node.id}.param.${id}`]=canonical;
        }
        return {key,id,value:clone(input),draft:clone(node.draft?.[key]),changed};
      });
      const performanceData=clone(selected?selected.performanceData||selected.selection?.performanceData||{}:node.performanceData||{});
      if((Object.keys(performanceData).length||node.performanceDataDraft)&&!window.FluidNetPerformanceData?.references)throw Error('性能资料合同未加载，请重新打开后应用');
      return {node,edits,definition:JSON.stringify(definition),selected:clone(selected),performanceData,
        draftModelId:node.draftModelId,draftModelVersion:node.draftModelVersion};
    });
    return {items,values};
  }
  function commit(state,owner,plan,describe) {
    window.FluidNetProjectState.assertCurrent(state,owner);
    // Prepare every object before promotion: a missing/replaced second node cannot leave the first updated.
    const patches=plan.items.map(item=>{
      const n=window.FluidNetProjectState.node(owner,item.node);
      const {definition,bindings}=describe(n);
      if(JSON.stringify(definition)!==item.definition)throw Error('设备绑定版本已变化，请检查运行档案');
      const params=clone(n.params),draft=clone(n.draft||{});
      const display=values=>Object.fromEntries(Object.entries(values).map(([key,value])=>[bindings?.[key]||key,value]));
      const performance=window.FluidNetPerformanceData,protectedDraft=new Set();
      // A pending source owns its matching curve draft, including one staged while waiting for acknowledgement.
      if(n.performanceDataDraft&&performance)for(const [key,entry] of Object.entries(performance.references(n,definition,display(draft)))){
        if(!equal(entry,n.performanceData?.[key]))for(const id of Object.keys(entry.parameterValues))protectedDraft.add(id);
      }
      for(const e of item.edits){
        params[e.key]=clone(e.value);
        if(equal(draft[e.key],e.draft)&&!protectedDraft.has(e.id))draft[e.key]=clone(e.value);
      }
      const patch={params,draft};
      if(performance)patch.performanceData=performance.references({performanceData:item.performanceData},definition,display(params),'current');
      if(item.selected){patch.modelId=item.selected.id;patch.modelVersion=item.selected.version;}
      else if(item.edits.some(e=>e.changed)){patch.modelId=null;patch.modelVersion=1;}
      if(n.draftModelId===item.draftModelId&&n.draftModelVersion===item.draftModelVersion&&
         Object.entries(draft).every(([key,v])=>equal(v,params[key]))){patch.draftModelId=null;patch.draftModelVersion=null;}
      return {n,patch};
    });
    for(const {n,patch} of patches)Object.assign(n,patch);
  }
  return {prepare,commit,controller};
})();
