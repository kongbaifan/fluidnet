/* Adapter for the retained prototype. All calculation values originate in /api/v1. */
window.createEngineClient = function (ui) {
  const clone = value => JSON.parse(JSON.stringify(value));
  const queues = new Map(), pending = new Map();
  let catalog = null, moduleCatalog = null, health = null;
  async function request(path, body, signal) {
    const response = await fetch('/api/v1' + path, {method: body === undefined ? 'GET' : 'POST',
      headers: {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), signal});
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail;
      throw Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(x => x.msg).join('；') : detail?.message || JSON.stringify(detail));
    }
    return data;
  }
  function payload(owner) {
    const state = ui.state();
    return {format:'fluidnet-studio-prototype',schema:1,activeProject:owner.id,projects:[owner],modules:state.modules.map(m => m.runtime === 'python' ? manifestPayload(m) : m)};
  }
  function key(owner) {
    return ui.parameterKey(owner) + JSON.stringify(ui.state().modules.filter(m => owner.pages.some(p => p.nodes.some(n => n.moduleId === m.id))).map(m => [m.id,m.version,m.ports,m.channels,m.source,m.manifest]));
  }
  async function normalize(owner, signal) { return request('/prototype/normalize',payload(owner),signal); }
  function manifestParamDef(spec) {
    const unit = spec.unit || {};
    const display = unit.display_unit || '';
    const scale = Number(unit.display_scale || 1);
    const offset = Number(unit.display_offset || 0);
    const toDisplay = value => Number(value) / scale + offset;
    const minimum = spec.minimum === null || spec.minimum === undefined ? -1e12 : toDisplay(spec.minimum);
    const maximum = spec.maximum === null || spec.maximum === undefined ? 1e12 : toDisplay(spec.maximum);
    const step = spec.value_type === 'boolean' ? 1 : (Math.abs(maximum - minimum) > 100 ? 1 : .01);
    return [spec.id, spec.label, display, minimum, maximum, step, toDisplay(spec.default)];
  }
  function moduleFromManifest(manifest) {
    const parameterDefs = (manifest.parameters || []).filter(p => p.value_type === 'number').map(manifestParamDef);
    ui.parameterDefinitions[manifest.id] = parameterDefs;
    const ports = (manifest.ports || []).map((p, index) => ({
      id:p.id, name:p.id.toUpperCase(), label:p.label || p.id, direction:p.direction === 'bidirectional' ? (index ? 'out' : 'in') : p.direction,
      domain:p.domain || 'fluid', x:p.direction === 'in' ? 20 : 80, y: manifest.ports.length > 2 ? (index % 2 ? 70 : 30) : 50
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
        note:'Worker 返回值',display:true,writable:false,value:null});
    }
    for (const v of variables) v.note ||= v.label;
    const values = Object.fromEntries(variables.map(v => [v.id,clone(v.value)]));
    const m = {id:manifest.id,kind:manifest.id,name:manifest.name,code:manifest.id.toUpperCase(),category:manifest.category || '自定义模块',icon:'Box',description:manifest.description || '',version:manifest.version || 1,
      runtime:manifest.runtime || 'python',entrypoint:manifest.entrypoint || '',contentHash:manifest.content_hash || '',packagePath:manifest.package_path || '',manifest,
      ports,channels:(manifest.channels || []).map(c => ({id:c.id,name:c.name,input:c.input_port,output:c.output_port,kind:c.relation,enabled:c.enabled !== false})),
      parameters:manifest.parameters || [],variables,customVars:[],quickParam:parameterDefs[0]?.[0] || '',quickType:'number',drawing:{shape:'rectangle',width:32,height:30,label:manifest.name},step:100,precision:4,dirty:false,
      source:{runtime:manifest.source?.runtime || '',header:'',design:['','','']},sourceFormat:'python-v1',values,banks:[clone(values),clone(values),clone(values)],bankNames:manifest.bank_names || ['额定工况','部分负荷','调试备份']};
    return m;
  }
  function manifestPayload(m) {
    if (m.manifest) {
      const {package:ref, ...definition} = m.manifest;
      return {...definition, id:m.id, name:m.name, version:m.version, category:m.category,
        ports:m.ports.map(p => { const original=m.manifest.ports.find(item => item.id===p.id); return {id:p.id,label:p.label,domain:p.domain,direction:original?.direction === 'bidirectional' ? original.direction : p.direction,required:original?.required ?? true,circuit:original?.circuit || 'fluid'}; }),
        channels:m.channels.map(c => ({id:c.id,name:c.name,input_port:c.input,output_port:c.output,relation:c.kind,solver_model:m.manifest.channels.find(item=>item.id===c.id)?.solver_model || m.manifest.solver_model,enabled:c.enabled})),
        source:{runtime:m.source.runtime}, runtime:'python', entrypoint:m.entrypoint,
        content_hash:m.source.runtime === m.manifest.source.runtime ? m.contentHash : null};
    }
    return m;
  }
  function rowFromModuleTest(owner, body) {
    const vars = body.evaluation?.variables || {}, state = body.committed?.state || body.state || {};
    return {t:body.frame.time_s, canonical:body.frame.variables, variables:vars, variableValues:{}, diagnostics:body.frame.diagnostics,metrics:body.frame.metrics,q:body.frame.variables['D1.mass_flow_kg_s'],a:null,b:null,pressure:owner.boundary.outlet,temperature:owner.boundary.temperature,state,relations:body.evaluation?.relations || []};
  }
  function diagnostics(items, metrics) {
    ui.diagnostics(items.map(d => ({text:(d.severity === 'warning' ? '提示：' : '') + d.message,node:d.instance_id,
      page:d.instance_id && ui.project().pages.find(p => p.nodes.some(n => n.id === d.instance_id))?.id})), metrics);
  }
  function portValue(n,v,row) {
    const suffix = {FLOW:'mass_flow_kg_s',PRE:'pressure_pa',TEMP:'temperature_k'}[v.id.split(':').at(-1)];
    const value = suffix && row?.canonical?.[`${n.id}.${v.port}.${suffix}`];
    if (!Number.isFinite(value)) return null;
    if (suffix === 'pressure_pa') return value / (v.unit === 'MPa' ? 1e6 : v.unit === 'kPa' ? 1000 : 1);
    if (suffix === 'temperature_k') return v.unit === '°C' ? value - 273.15 : value;
    const port = ui.moduleOf(n).ports.find(p => p.id === v.port);
    return value * (port?.direction === 'out' ? -1 : 1);
  }
  function rowFromFrame(owner,frame) {
    const canonical = frame.variables;
    const row = {t:frame.time_s,canonical,variables:{},variableValues:{},diagnostics:frame.diagnostics,metrics:frame.metrics,
      q:canonical['P1.mass_flow_kg_s'] ?? null,a:canonical['V1.mass_flow_kg_s'] ?? null,b:canonical['V2.mass_flow_kg_s'] ?? null,
      pressure:Number.isFinite(canonical['P1.out0.pressure_pa']) ? canonical['P1.out0.pressure_pa'] / 1000 : null,temperature:null};
    for (const n of owner.pages.flatMap(p => p.nodes)) {
      const m = ui.moduleOf(n);
      for (const v of m.variables) {
        const raw = v.canonicalId ? canonical[`${n.id}.${v.canonicalId}`] : null;
        const value = v.origin === 'port' ? portValue(n,v,row) : v.origin === 'parameter' ? n.params[v.param] : raw === null || raw === undefined ? null : v.unitSpec ? raw / v.unitSpec.display_scale + v.unitSpec.display_offset : raw;
        row.variableValues[n.id + ':' + v.id] = value;
      }
      for (const [k,v] of Object.entries(n.params)) row.variables[n.id + '.' + k.toUpperCase()] = v;
      const pressure = canonical[`${n.id}.out0.pressure_pa`];
      row.variables[n.id + '.OUT_FLOW'] = canonical[`${n.id}.mass_flow_kg_s`] ?? null;
      row.variables[n.id + '.OUT_PRE'] = Number.isFinite(pressure) ? pressure / 1000 : null;
      row.variables[n.id + '.OUT_TEMP'] = null;
    }
    return row;
  }
  function applyRow(owner,row) {
    const run = owner.run;
    run.time = row.t;
    run.values = {q:row.q,a:row.a,b:row.b,pressure:row.pressure,temperature:row.temperature};
    run.history.push(row);
    run.parameterKey = ui.parameterKey(owner);
  }
  async function command(scope, action, projectId) {
    if (scope === 'bench') {
      const owner = ui.state().bench, module = ui.state().modules.find(m => m.id === owner.moduleId);
      if (!module?.manifest) { ui.message('当前模块没有可执行的版本化 Python 模块包。', true); return; }
      if (action === 'pause' || action === 'stop') { pending.get('__bench')?.abort(); owner.run.status = action === 'pause' ? 'paused' : 'stopped'; ui.render(); return; }
      if (['running','solving'].includes(owner.run.status)) return;
      const controller=new AbortController(); pending.set('__bench',controller);
      owner.run.status = 'solving'; owner.run.source = 'engine'; ui.render();
      try {
        const parameters = Object.fromEntries(Object.entries(owner.params).map(([key,value]) => {
          const spec = module.parameters.find(p => p.id === key); const unit = spec?.unit; return [key, unit ? (Number(value) - Number(unit.display_offset || 0)) * Number(unit.display_scale || 1) : Number(value)];
        }));
        const body = await request('/modules/test',{module:manifestPayload(module),parameters,inlet_pressure_pa:Number(owner.boundary.inlet) * 1000,outlet_pressure_pa:Number(owner.boundary.outlet) * 1000,temperature_k:Number(owner.boundary.temperature) + 273.15,dt_s:owner.run.step,duration_s:owner.run.step},controller.signal);
        const row = rowFromModuleTest(owner, body);
        owner.run.history = body.history.map(f => ({...row,t:f.time_s,canonical:f.variables,q:f.variables['D1.mass_flow_kg_s']}));
        owner.run.time = row.t; owner.run.values = {q:row.q,a:null,b:null,pressure:owner.boundary.outlet,temperature:owner.boundary.temperature};
        owner.run.worker = {status:'completed',contentHash:body.content_hash,version:module.version,evaluation:body.evaluation,initialState:body.state,committed:body.committed};
        owner.run.events = [{t:owner.run.time,text:`Worker evaluate 完成，${body.evaluation.relations.length} 条关系已注册。`},{t:owner.run.time,text:`commit_step 完成，状态提交 ${Object.keys(body.committed.state || {}).length} 项。`}]; owner.run.id = body.content_hash; owner.run.status = action === 'step' ? 'paused' : 'completed'; ui.dirty(); ui.render(); ui.message('Python 模块 Worker 测试完成。');
      } catch (error) { if(error.name !== 'AbortError') { owner.run.status='failed'; owner.run.events=[{t:owner.run.time,text:error.message}]; ui.message('模块测试失败：' + error.message,true); } ui.render(); }
      finally { if(pending.get('__bench') === controller) pending.delete('__bench'); }
      return;
    }
    const owner = ui.state().projects.find(p => p.id === (projectId || ui.state().activeProject));
    if (!owner) return;
    if (action === 'pause' || action === 'stop') {
      pending.get(owner.id)?.abort(); pending.delete(owner.id);
      owner.run.status = action === 'pause' ? 'paused' : 'stopped';
      if (action === 'stop') queues.delete(owner.id);
      owner.run.events.push({t:owner.run.time,text:action === 'pause' ? '已暂停结果回放。' : '已停止结果回放。'});
      ui.render(); return;
    }
    if (pending.has(owner.id)) return;
    const existing = queues.get(owner.id);
    if (existing && existing.key === key(owner) && owner.run.status === 'paused') {
      if (action === 'step') {
        const row = existing.rows.shift(); if (row) applyRow(owner,row);
        if (!existing.rows.length) { owner.run.status='completed'; queues.delete(owner.id); }
      } else { owner.run.status='running'; existing.wall = performance.now(); existing.sim = owner.run.time; }
      ui.render(); return;
    }
    queues.delete(owner.id);
    const controller = new AbortController(); pending.set(owner.id,controller);
    const before = key(owner);
    const old = owner.run;
    owner.run = {...ui.emptyRun(),status:'solving',source:'engine'};
    ui.render();
    try {
      const project = await normalize(owner,controller.signal);
      const mode = action === 'step' ? 'dynamic' : owner.solver.mode;
      let data = await request('/runs' + (mode === 'dynamic' ? '?background=true' : ''),{project,mode,duration_s:action === 'step' ? owner.solver.dt : owner.solver.duration,dt_s:owner.solver.dt},controller.signal);
      while (['queued','running'].includes(data.status)) {
        await new Promise((resolve,reject)=>{
          const abort=()=>{clearTimeout(timer);reject(new DOMException('请求已取消','AbortError'));};
          const timer=setTimeout(()=>{controller.signal.removeEventListener('abort',abort);resolve();},100);
          controller.signal.addEventListener('abort',abort,{once:true});
          if(controller.signal.aborted) abort();
        });
        const record=await request('/runs/'+data.run_id,undefined,controller.signal);
        data={...record,run_id:data.run_id};
      }
      if (data.status === 'failed') { diagnostics(data.frame.diagnostics); throw Error(data.frame.diagnostics.map(d => d.message).join('；')); }
      const history = await request(`/runs/${data.run_id}/history`,undefined,controller.signal);
      if (before !== key(owner)) throw Error('计算期间项目已变化，请重新运行当前参数。');
      const rows = history.rows.map(f => rowFromFrame(owner,f));
      owner.run.id = data.run_id;
      owner.run.events = data.frame.diagnostics.map(d => ({t:0,text:d.message}));
      owner.run.events.push({t:0,text:`后端计算完成；压力残差 ${data.frame.metrics.pressure_residual_pa.toExponential(2)} Pa，质量残差 ${data.frame.metrics.mass_residual_kg_s.toExponential(2)} kg/s。`});
      if (action === 'step') {
        // Each step is a new immutable solve; keep the sequence with the parameters that produced each row.
        const stateful = project.modules.some(m=>m.runtime === 'python');
        const base = old.source === 'engine' && !stateful ? old.time : 0;
        owner.run.history = old.source === 'engine' && !stateful ? old.history : [];
        if (!owner.run.history.length) applyRow(owner,rows[0]);
        const row = rows.at(-1); row.t += base;
        applyRow(owner,row); owner.run.status='paused';
      } else {
        applyRow(owner,rows[0]);
        if (rows.length > 1) {
          owner.run.status='running';
          queues.set(owner.id,{rows:rows.slice(1),key:before,wall:performance.now(),sim:0});
        } else owner.run.status='completed';
      }
      ui.dirty(owner); ui.render();
      ui.message(mode === 'steady' ? '真实稳态求解完成。' : '准稳态结果已更新；未包含热惯性和液位变化。');
    } catch (error) {
      if (error.name !== 'AbortError') {
        owner.run.status='failed';
        owner.run.events.push({t:0,text:error.message});
        ui.message('计算失败：' + error.message,true);
      }
      ui.render();
    } finally { if (pending.get(owner.id) === controller) pending.delete(owner.id); }
  }
  function tick() {
    let changed=false, ended=false;
    for (const owner of ui.state().projects) {
      const queue = queues.get(owner.id);
      if (!queue || owner.run.status !== 'running') continue;
      if (queue.key !== key(owner)) {
        queues.delete(owner.id); owner.run.status='paused';
        ui.message('项目参数或定义已变更；点击运行以重新计算。'); changed=true; ended=true; continue;
      }
      const target = queue.sim + (performance.now() - queue.wall) / 1000;
      while (queue.rows.length && queue.rows[0].t <= target) { applyRow(owner,queue.rows.shift()); changed=true; }
      if (!queue.rows.length) { owner.run.status='completed'; queues.delete(owner.id); ended=true; }
    }
    if (ended) ui.render(); else if (changed) ui.refresh();
  }
  async function validate() {
    try { const project = await normalize(ui.project()); const result = await request('/projects/validate',project); diagnostics(result.diagnostics); }
    catch (error) { diagnostics([{message:error.message,severity:'error'}]); }
  }
  async function init() {
    try {
      const [service,data,packages] = await Promise.all([request('/health'),request('/catalog'),request('/modules')]);
      health = service;
      catalog=data;
      moduleCatalog=packages;
      for (const manifest of packages.modules || []) {
        if (manifest.runtime !== 'python') continue;
        const existing=ui.state().modules.find(m => m.id === manifest.id);
        if (!existing) ui.state().modules.push(moduleFromManifest(manifest));
        else if (existing.manifest) ui.parameterDefinitions[existing.kind] = existing.manifest.parameters.filter(p => p.value_type === 'number').map(manifestParamDef);
      }
      ui.state().bench ||= {moduleId:'valve',params:{},boundary:{inlet:201.325,outlet:120,temperature:20},run:ui.emptyRun('bench')};
      ui.state().modules.forEach(m => { if (m.runtime === 'python' && !m.manifest) { const manifest = (packages.modules || []).find(item => item.id === m.id); if (manifest) Object.assign(m, moduleFromManifest(manifest)); } });
      ui.state().bench.params ||= {};
      const benchModule = ui.state().modules.find(m => m.id === ui.state().bench.moduleId) || ui.state().modules.find(m => m.manifest);
      if (benchModule && !Object.keys(ui.state().bench.params).length) ui.state().bench.params = Object.fromEntries((ui.parameterDefinitions[benchModule.kind] || []).map(f => [f[0], f[6]]));
      if (!benchModule?.manifest && !ui.state().bench.run.history.length) {
        const pythonModule=ui.state().modules.find(m=>m.manifest);
        if (pythonModule) { ui.state().bench.moduleId=pythonModule.id; ui.state().bench.params=Object.fromEntries(ui.parameterDefinitions[pythonModule.kind].map(f=>[f[0],f[6]])); }
      }
      for (const [kind,bindings] of Object.entries(data.prototype_parameter_bindings)) {
        const m = data.modules.find(m => m.id === kind);
        for (const field of ui.parameterDefinitions[kind] || []) {
          const spec=m.parameters.find(p => p.id === bindings[field[0]]);
          if (!spec?.unit) continue;
          const display = value => value / spec.unit.display_scale + spec.unit.display_offset;
          field[2]=spec.unit.display_unit; field[6]=display(spec.default);
          if (spec.minimum !== null) field[3]=display(spec.minimum);
          if (spec.maximum !== null) field[4]=display(spec.maximum);
        }
      }
      ui.message(`计算服务 v${health.version} 已连接：稳态水力与准稳态时间序列可用。`);
      ui.render();
    } catch (error) { ui.message('计算服务未连接，请通过启动脚本打开此页面。' + error.message,true); }
  }
  return {command,tick,validate,init,portValue,manifestPayload,get catalog(){return catalog;},get health(){return health;}};
};
