/* Pure conversions between module contracts, project documents and display values. */
export const FluidNetProjectModel = (() => {
  const clone=value=>value===undefined?undefined:JSON.parse(JSON.stringify(value));
  function workspaceContentEqual(left,right) {
    if(!left||!right||typeof left!=='object'||typeof right!=='object')return false;
    // These top-level fields are receipt metadata/cache rebuilt after a workspace save/load.
    // Every project, draft, layout, code, run and dirty marker still participates.
    const metadata=new Set(['savedAt','workspaceRevision','projectRevisions','projectSavedKeys']);
    const stable=(value,root=false)=>Array.isArray(value)?value.map(v=>stable(v))
      :value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().filter(k=>!root||!metadata.has(k)).map(k=>[k,stable(value[k])])):value;
    return JSON.stringify(stable(left,true))===JSON.stringify(stable(right,true));
  }
  function toDisplay(spec,value) {
    if(value==null)return value;
    return spec?.unit && (!spec.value_type || spec.value_type==='number')
      ? Number(value)/Number(spec.unit.display_scale || 1)+Number(spec.unit.display_offset || 0) : clone(value);
  }
  function toCanonical(spec,value) {
    if(spec?.value_type && spec.value_type!=='number')return clone(value);
    return spec?.unit ? (Number(value)-Number(spec.unit.display_offset || 0))*Number(spec.unit.display_scale || 1) : Number(value);
  }
  function displayParameters(definition,values,partial=true) {
    const specs=new Map((definition.parameters || []).map(p=>[p.id,p]));
    const entries=partial?Object.entries(values):(definition.parameters || []).map(p=>[p.id,values[p.id]]);
    return Object.fromEntries(entries.map(([id,value])=>[id,toDisplay(specs.get(id),value)]));
  }
  function canonicalParameters(definition,values) {
    const specs=new Map((definition.parameters || []).map(p=>[p.id,p]));
    return Object.fromEntries(Object.entries(values).map(([id,value])=>[id,toCanonical(specs.get(id),value)]));
  }
  function manifestParamDef(spec) {
    const unit = spec.unit || {};
    const display = unit.display_unit || '';
    const displayValue = value => toDisplay(spec,value);
    const minimum = spec.minimum === null || spec.minimum === undefined ? -1e12 : displayValue(spec.minimum);
    const maximum = spec.maximum === null || spec.maximum === undefined ? 1e12 : displayValue(spec.maximum);
    const step = spec.value_type === 'boolean' ? 1 : (Math.abs(maximum - minimum) > 100 ? 1 : .01);
    return [spec.id, spec.label, display, minimum, maximum, step, displayValue(spec.default)];
  }
  function catalogPresentationIndex(response) {
    const index=Object.create(null);
    if(response?.version!==1||!Array.isArray(response.devices))return index;
    for(const item of response.devices){
      if(!item||typeof item.module_id!=='string'||item.runtime!=='builtin'||typeof item.icon!=='string'||
        !/^\w+$/.test(item.icon)||typeof item.canvas_family!=='string')continue;
      index[item.module_id]={module_id:item.module_id,runtime:item.runtime,icon:item.icon,canvas_family:item.canvas_family};
    }
    return index;
  }
  function applyCatalogPresentation(module, presentation) {
    if(module.runtime!=='builtin'||presentation?.runtime!=='builtin'||presentation.module_id!==module.id)return module;
    if(typeof presentation.icon!=='string'||!/^\w+$/.test(presentation.icon)||typeof presentation.canvas_family!=='string')return module;
    module.presentation={icon:presentation.icon,canvas_family:presentation.canvas_family};
    module.icon=presentation.icon;
    return module;
  }
  // Compatibility only: old backends and Python packages do not carry built-in metadata.
  function legacyCatalogIcon(id) {
    return {coupled_tower_pool:'Droplets',enthalpy_recovery:'ArrowRightLeft',hydronic_boiler:'Flame',geometry_bend:'CornerDownRight',gas_expansion_tank:'Database',tower_pool:'Database',air_source_heat_pump:'Flame',air_recovery_sensible:'ArrowRightLeft',enthalpy_compressor:'Gauge',enthalpy_valve:'SlidersHorizontal',refrigerant_line:'Minus',refrigerant_subcooler:'Snowflake',refrigerant_recuperator:'ArrowRightLeft',dx_expansion_valve:'SlidersHorizontal',dx_evaporator:'Snowflake',dx_compressor:'Gauge',air_cooled_chiller:'Snowflake',closed_buffer_tank:'Database',performance_compressor:'Gauge',cold_room_multi:'Home',defrost_air_cooler:'Snowflake',air_branch_box:'GitBranch',fan_performance:'Wind',plate_exchanger:'ArrowRightLeft',differential_bypass_valve:'SlidersHorizontal',pressure_independent_valve:'SlidersHorizontal',horizontal_receiver:'Database',horizontal_drum:'Database',air_cooled_condenser:'Wind',cold_room:'Home',storage_room:'Home',lp_drum:'Database',hp_receiver:'Database',pumped_drum:'Database',cascade_exchanger:'ArrowRightLeft',refrigerant_compressor:'Gauge',evaporative_condenser:'Wind',expansion_valve:'SlidersHorizontal',refrigerant_pump:'Gauge',air_cooler:'Snowflake',refrigerant_header:'GitMerge',water_coil:'Snowflake',water_chiller:'Snowflake',duct:'Wind',cooling_coil:'Snowflake',humidifier:'Droplets',air_mixing_box:'GitMerge',air_filter:'Filter',air_room:'Home',cooling_tower_moist:'Wind',pipe_fitting:'GitBranch',pipe_reducer:'GitBranch',check_valve:'ArrowRightLeft',fan_coil_unit:'Wind',cooling_tower:'Sun',fan:'Wind',pump_variable_speed:'Gauge',capillary_tube:'Minus',valve_equal_percentage:'SlidersHorizontal'}[id] || 'Box';
  }
  const LEGACY_VISIBLE_BUILTINS = new Set(['duct','cooling_coil','humidifier','air_mixing_box','air_filter','air_room','cooling_tower_moist','water_coil','water_chiller','air_cooled_chiller','air_source_heat_pump','enthalpy_recovery','closed_buffer_tank','hydronic_buffer_tank','gas_expansion_tank','tower_pool','coupled_tower_pool']);
  function installBuiltinCatalog({catalog,presentations,modules,parameterDefinitions,defaultConditions}) {
    for(const manifest of catalog.modules || []) {
      const metadata=presentations[manifest.id];
      if(!metadata && !(manifest.ports||[]).some(port=>['thermal','refrigerant'].includes(port.domain)) && !LEGACY_VISIBLE_BUILTINS.has(manifest.id))continue;
      let module=modules.find(item=>item.id===manifest.id);
      if(!module){module=moduleFromManifest(manifest,defaultConditions,metadata);modules.push(module);}
      else if(!module.presentation){
        if(!module.manifest && module.runtime===undefined && metadata?.runtime==='builtin'){
          const presented=applyCatalogPresentation({...module,runtime:'builtin'},metadata);
          if(presented.presentation){module.presentation=presented.presentation;module.icon=presented.icon;}
        }else applyCatalogPresentation(module,metadata);
      }
      // Prototype-era modules retain their display aliases and library values.
      // Only canonical manifest-backed devices own canonical parameter definitions.
      if(module.manifest && module.runtime==='builtin')parameterDefinitions[module.kind]=manifest.parameters.filter(p=>p.value_type==='number').map(manifestParamDef);
    }
  }
  function moduleFromManifest(manifest, defaultConditions, presentation) {
    const icon = manifest.runtime==='builtin' && presentation?.runtime==='builtin' && presentation.module_id===manifest.id && /^\w+$/.test(presentation.icon||'')
      ? presentation.icon : legacyCatalogIcon(manifest.id);
    const parameterDefs = (manifest.parameters || []).filter(p => p.value_type === 'number').map(manifestParamDef);
    const ports = (manifest.ports || []).map((p, index) => ({
      id:p.id, name:p.id.toUpperCase(), label:p.label || p.id, direction:p.direction === 'bidirectional' ? (index ? 'out' : 'in') : p.direction,
      domain:p.domain || 'fluid', required:p.required !== false, x:p.direction === 'in' ? 20 : 80,
      y:['water_coil','water_chiller'].includes(manifest.id) ? (index<2?30:70) : manifest.ports.length > 2 ? (index % 2 ? 70 : 30) : 50
    }));
    const variables = [];
    for (const p of ports) {
      if (p.domain === 'fluid') for (const [suffix,label,unit,value] of [['FLOW','质量流量','kg/s',0],['PRE','绝对压力','MPa',0],['TEMP','温度','°C',20]]) {
        variables.push({id:p.id + ':' + suffix,name:p.name + '_' + suffix,label:p.label + ' · ' + label,unit,type:'double',port:p.id,origin:'port',display:['FLOW','PRE'].includes(suffix),writable:p.direction === 'in',value});
      }
    }
    for (const f of parameterDefs) variables.push({id:'param:' + f[0],name:f[0].toUpperCase(),label:f[1],unit:f[2],type:'double',port:'',origin:'parameter',param:f[0],display:true,writable:true,value:f[6]});
    variables.push({id:'system:step',name:'S_T',label:'时间步长',unit:'ms',type:'int',port:'',origin:'system',display:false,writable:true,value:100},
      {id:'system:run',name:'RUN_S',label:'运行状态',unit:'—',type:'int',port:'',origin:'system',display:false,writable:false,value:0},
      {id:'system:mix',name:'MIX',label:'工质质量比例',unit:'—',type:'double[8]',port:'',origin:'system',display:false,writable:true,value:[1,0,0,0,0,0,0,0]},
      {id:'system:form',name:'FORM',label:'工质编号',unit:'—',type:'int[8]',port:'',origin:'system',display:false,writable:true,value:[125,0,0,0,0,0,0,0]});
    for (const v of manifest.variables || []) {
      if (!['derived','state'].includes(v.source)) continue;
      variables.push({id:'runtime:' + v.id,name:v.id.replace(/[^A-Za-z0-9_]/g,'_').toUpperCase(),label:v.label,
        unit:v.unit?.display_unit || '',type:'double',port:'',origin:'runtime',canonicalId:v.id,unitSpec:v.unit,
        note:manifest.runtime==='builtin'?'引擎计算值':'Worker 返回值',display:true,writable:false,value:null});
    }
    for (const v of variables) v.note ||= v.label;
    const values = Object.fromEntries(variables.map(v => [v.id,clone(v.value)]));
    const m = {id:manifest.id,kind:manifest.id,name:manifest.name,code:manifest.id.toUpperCase(),category:manifest.category || '自定义模块',icon,description:manifest.description || '',version:manifest.version || 1,
      runtime:manifest.runtime || 'python',entrypoint:manifest.entrypoint || '',contentHash:manifest.content_hash || '',packagePath:manifest.package_path || '',manifest,
      ports,channels:(manifest.channels || []).map(c => ({id:c.id,name:c.name,input:c.input_port,output:c.output_port,kind:c.relation,enabled:c.enabled !== false})),
      parameters:manifest.parameters || [],parameterDefs,variables,customVars:[],quickParam:parameterDefs[0]?.[0] || '',quickType:'number',drawing:{shape:'rectangle',width:32,height:30,label:manifest.name},step:100,precision:4,dirty:false,
      source:{runtime:manifest.source?.runtime || '',header:'',design:['','','']},designSource:typeof manifest.source?.design === 'string' ? manifest.source.design : '',sourceFormat:'python-v1',values,banks:[clone(values),clone(values),clone(values)],bankNames:manifest.bank_names || ['额定工况','部分负荷','调试备份']};
    if(manifest.execution_role)m.testConditions=defaultConditions(manifest);
    return applyCatalogPresentation(m,presentation);
  }
function manifestFields(manifest) {
  return manifest.parameters.filter(p => p.value_type === 'number').map(p => {
    const display = value => toDisplay(p,value);
    return [p.id,p.label,p.unit?.display_unit || '',p.minimum == null ? -1e12 : display(p.minimum),p.maximum == null ? 1e12 : display(p.maximum),'any',display(p.default)];
  });
}
function manifestParamSpecs(manifest) {
  return (manifest?.parameters || []).map(p => {
    const display=value=>value==null?null:toDisplay(p,value);
    return {id:p.id,label:p.label,value_type:p.value_type || 'number',unit:p.unit || null,
      minimum:display(p.minimum),maximum:display(p.maximum),default:display(p.default),writable:p.writable!==false,runtime:!!p.runtime};
  });
}
function manifestParamDefaults(manifest) {
  return Object.fromEntries(manifestParamSpecs(manifest).map(p => [p.id, clone(p.default)]));
}
  function projectDocument(owner, state) {
    const p=clone(owner),used=new Set(p.pages.flatMap(pg=>pg.nodes.map(n=>n.moduleId)));
    p.moduleSnapshots=Object.fromEntries([...used].map(id=>[id,clone(p.moduleSnapshots?.[id]||state.modules.find(m=>m.id===id))]));
    return {format:'fluidnet-project',schema:1,project:p,modules:Object.values(p.moduleSnapshots),
      models:clone(state.models.filter(m=>used.has(m.moduleId))),charts:clone(state.charts.extra.filter(c=>c.projectId===p.id))};
  }
  function exchangeDocument(data, {makeProject, moduleFromManifest, replaceScripts}) {
    if(data.format==='fluidnet-project' && data.schema===1)return clone(data);
    if(data.format==='fluidnet-studio-prototype') {
      const p=data.projects.find(p=>p.id===data.activeProject)||data.projects[0];
      return {format:'fluidnet-project',schema:1,project:clone(p),modules:clone(data.modules),
        models:clone(data.models||[]),charts:clone((data.charts?.extra||[]).filter(c=>c.projectId===p.id))};
    }
    if(data.schema_version!==1 || !Array.isArray(data.instances) || !Array.isArray(data.modules))
      throw Error('请选择单项目、完整原型或规范 Project JSON 文件。');
    const definitions=new Map(data.modules.map(m=>[m.id,m]));
    const snapshots=Object.fromEntries(data.modules.map(m=>[m.id,{...moduleFromManifest(clone(m)),frozen:true}]));
    const display=displayParameters;
    const pages=new Map(),nodes=new Map(),pageIds=new Map();
    const safePage=id=>/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id);
    const reserved=new Set(data.instances.map(n=>n.page_id||'main').filter(safePage));
    for(const n of data.instances){
      const original=n.page_id||'main';if(pageIds.has(original))continue;
      let id=original;
      if(!safePage(id)){let serial=pageIds.size+1;do{id='page-'+serial++;}while(reserved.has(id));reserved.add(id);}
      pageIds.set(original,id);
    }
    for(const n of data.instances) {
      const definition=definitions.get(n.module_id),pageName=n.page_id||'main',pageId=pageIds.get(pageName);
      if(!pages.has(pageId))pages.set(pageId,{id:pageId,name:pageName,zoom:1,pan:[0,0],nodes:[],edges:[]});
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
      pages.get(pageId).edges.push([c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id]);
    }
    if(!pages.size)throw Error('规范项目没有设备。');
    const p=makeProject(data.id,data.name,data.description||'',[...pages.values()][0]);
    Object.assign(p,{pages:[...pages.values()],activePage:pages.keys().next().value,moduleSnapshots:snapshots,
      fluid:data.fluid?.fluid||'Water',fluidConfig:clone(data.fluid||{}),fluidReference:data.fluid?.reference||'mass',
      circuitFluids:(data.circuit_fluids||[]).map(c=>({id:c.id,anchor:clone(c.anchor),fluid:c.fluid.fluid,fluidConfig:clone(c.fluid),fluidReference:c.fluid.reference})),
      solverOptions:clone(data.solver||{}),controllers:clone(data.controllers||[]),events:clone(data.events||[]),
      couplingMode:data.coupling_mode||'legacy',thermalCouplings:clone(data.thermal_couplings||[]),selectedVariables:clone(data.selected_variables||[]),measurements:clone(data.measurements||[]),
      controlPrograms:[],controlScripts:[],controlEnabled:false,controlInputs:'',controlOutputs:'',
      scenarios:(data.scenarios||[]).map(s=>({...clone(s),overrides:Object.fromEntries(Object.entries(s.overrides).map(([id,values])=>
        [id,display(definitions.get(nodes.get(id).node.moduleId),values)]))}))});
    const solver=data.solver||{};
    p.solver={mode:'dynamic',duration:60,dt:Math.min(10,solver.dynamic_step_s||.1),
      dynamicStep:solver.dynamic_step_s||.1,pressureAtol:solver.pressure_tolerance_pa??1,massAtol:solver.mass_tolerance_kg_s??1e-8,
      maxIter:solver.max_iterations??80,hydraulicMethod:solver.hydraulic_method||'dense',moduleMixedJacobian:Boolean(solver.module_mixed_jacobian)};
    replaceScripts(p,data.control_scripts||[]);
    return {format:'fluidnet-project',schema:1,project:p,modules:Object.values(snapshots),models:[],charts:[]};
  }
  function upgradeDocument(owner,preview, options) {
    const {moduleFromManifest,replaceScripts,emptyRun}=options;
    const document=clone(options.document),snapshot={...moduleFromManifest(clone(preview.module)),frozen:true};
    document.project.moduleSnapshots[snapshot.id]=snapshot;
    document.modules=document.modules.map(m=>m.id===snapshot.id?snapshot:m);
    const canonical=new Map(preview.project.instances.map(n=>[n.id,n]));
    const display=(values,partial=false)=>displayParameters(preview.module,values,partial);
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
    document.project.measurements=clone(preview.project.measurements||[]);
    replaceScripts(document.project,preview.project.control_scripts);
    for(const chart of document.charts || []){
      if(chart.canonicalKey)chart.canonicalKey=reference(chart.canonicalKey);
      if(chart.identifier)chart.identifier=reference(chart.identifier);
      if(affected.has(chart.nodeId) && chart.variableId){const old=chart.variableId;chart.variableId=migration.variables?.[old] || old;chart.sampleKey=chart.nodeId+':'+chart.variableId;}
    }
    for(const model of document.models || [])if(model.moduleId===snapshot.id){
      const before=owner.moduleSnapshots[snapshot.id].manifest.parameters;
      const values={};for(const spec of before){const target=migration.parameters?.[spec.id] ?? (preview.module.parameters.some(p=>p.id===spec.id)?spec.id:null);if(target&&spec.id in model.params){const canonical=toCanonical(spec,model.params[spec.id]);const conversion=migration.unit_conversions?.[spec.id];values[target]=conversion?canonical*conversion.scale+conversion.offset:canonical;}}
      model.params=display(Object.fromEntries(preview.module.parameters.map(p=>[p.id,p.id in values?values[p.id]:p.default])));model.sourceModuleVersion=preview.to_version;
    }
    document.project.run=emptyRun();return document;
  }
function parameterKey(owner,modules,controlKey) {
  const usedModules=new Set(owner.pages.flatMap(pg=>pg.nodes.map(n=>n.moduleId)));
  return JSON.stringify({scenarios:owner.scenarios||[],events:owner.events||[],activeScenarioId:owner.activeScenarioId||'',medium:owner.medium,fluid:owner.fluid,fluidReference:owner.fluidReference,fluidConfig:owner.fluidConfig,circuitFluids:owner.circuitFluids,couplingMode:owner.couplingMode,thermalCouplings:owner.thermalCouplings,solverOptions:owner.solverOptions,controllers:owner.controllers||[],controls:controlKey(owner), solver: owner.solver, modules: modules.filter(m => usedModules.has(m.id)).map(m => {const bound=owner.moduleSnapshots?.[m.id]||m;return {id:bound.id,kind:bound.kind,version:bound.version,definitionHash:bound.manifest?.definition_hash,ports:bound.ports.map(({id,domain,direction,required,circuit})=>({id,domain,direction,required,circuit})),channels:bound.channels};}), pages: owner.pages.map(pg => ({
    nodes: pg.nodes.map(n => ({ id: n.id, moduleId: n.moduleId, params: n.params, values: n.variableState?.values })),
    edges: pg.edges,
  })) });
}

  return {parameterKey,workspaceContentEqual,toDisplay,toCanonical,displayParameters,canonicalParameters,manifestParamDef,moduleFromManifest,applyCatalogPresentation,installBuiltinCatalog,catalogPresentationIndex,
    manifestFields,manifestParamSpecs,manifestParamDefaults,projectDocument,exchangeDocument,upgradeDocument};
})();

export default FluidNetProjectModel;
