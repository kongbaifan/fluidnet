/* Adapter for the retained prototype. All calculation values originate in /api/v1. */
window.createEngineClient = function (ui) {
  const clone = value => JSON.parse(JSON.stringify(value));
  const queues = new Map(), pending = new Map();
  let catalog = null, moduleCatalog = null, health = null;
  // Polling a backgrounded run is bounded twice on purpose: a backend that never leaves
  // queued/running must not spin the UI forever, and an iteration cap alone would not hold
  // if each request itself is slow. Whichever bound trips first fails the run with an
  // explanation instead of leaving a spinner that can never resolve. The two agree by
  // construction (3000 polls x 100 ms = 300 s). A legal run cannot be cut off: the backend
  // caps a dynamic run at 2001 frames (max_frames) and such a worst-case run measured ~8 s
  // of hydraulics here, plus at most one Worker RPC per frame for Python modules - far
  // inside 300 s.
  const RUN_POLL_INTERVAL_MS = 100, RUN_POLL_MAX_ITERATIONS = 3000, RUN_POLL_DEADLINE_MS = 300000;
  const waitLabel = ms => `${(ms / 1000).toFixed(1)} 秒`;
  async function request(path, body, signal) {
    const response = await fetch('/api/v1' + path, {method: body === undefined ? 'GET' : 'POST',
      headers: {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), signal});
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail;
      const error = Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(x => x.loc.join('.') + '：' + x.msg).join('；') : detail?.message || JSON.stringify(detail));
      error.status = response.status; throw error;
    }
    return data;
  }
  function payload(owner) {
    const state = ui.state();
    pinProject(owner);
    const used=new Set(owner.pages.flatMap(p=>p.nodes.map(n=>n.moduleId)));
    const definitions=[...used].map(id=>owner.moduleSnapshots?.[id] || state.modules.find(m=>m.id===id));
    return {format:'fluidnet-studio-prototype',schema:1,activeProject:owner.id,projects:[owner],modules:definitions.map(m => m.runtime === 'python' ? manifestPayload(m) : m)};
  }
  function key(owner) {
    return ui.parameterKey(owner) + JSON.stringify(owner.moduleSnapshots || {});
  }
  async function normalize(owner, signal) { return request('/prototype/normalize',payload(owner),signal); }
  function frameFailure(data) {
    const diagnostics = data.frame?.diagnostics || [];
    return diagnostics.map(d => d.message).filter(Boolean).join(';');
  }
  // Point every "the server side did not finish" path at the same human-readable reason.
  function stallReason(data, timedOut, ms, polls) {
    const detail = frameFailure(data);
    const bound = timedOut ? `等待超过 ${waitLabel(RUN_POLL_DEADLINE_MS)}` : `轮询超过 ${RUN_POLL_MAX_ITERATIONS} 次`;
    return `后端运行 ${data.status} 超过 ${waitLabel(ms)}(${bound},共 ${polls} 次查询)仍未结束,已停止等待;`
      + `最后一次后端状态:${data.status}${data.run_id ? ',run_id ' + data.run_id : ''}。` + (detail ? `后端诊断:${detail}` : '');
  }
  // Abort whichever HTTP request is in flight for this scope; the pending key differs
  // between the bench ('__bench') and a project (its id).
  function abortPending(key) {
    const controller = pending.get(key);
    if (!controller) return false;
    pending.delete(key);
    controller.abort();
    return true;
  }
  // The record and its failure frame are separate requests; the frame exists only once the
  // run has finished, so a failed run without one (or with an empty one) still needs a reason.
  async function failureDetail(data, signal) {
    let detail = frameFailure(data);
    if (!detail) {
      try { detail = frameFailure(await request('/runs/' + data.run_id, undefined, signal)); } catch { /* Keep the status-only reason. */ }
    }
    return detail || '后端未提供失败诊断';
  }
  // Newer backends accept POST /runs/{id}/command with a RunCommand body; older ones 404.
  // Only an explicit 501/404 means "unsupported" - a network error or 5xx must not be
  // reported as missing backend support, or stop would silently pretend nothing failed.
  async function runCommand(runId, command) {
    try {
      return { record: await request(`/runs/${encodeURIComponent(runId)}/command`, command) };
    } catch (error) {
      // A 404/501 on this route means the backend does not implement run control yet. Match on
      // the status code request() attaches, not on the message text: the message is whatever the
      // backend chose to say and need not contain the number.
      const unsupported = error.status === 404 || error.status === 501;
      return { error, unsupported };
    }
  }
  async function cancelBackend(owner, action) {
    const runId = owner.run.runId;
    if (!runId) return { local: true };
    const result = await runCommand(runId, action === 'pause' ? {action:'pause'} : {action:'stop'});
    if (result.error) return { error: result.error, unsupported: result.unsupported };
    return { status: result.record?.status, cancelled: result.record?.status === 'cancelled' };
  }
  // One place decides what a pause/stop actually achieved, so the bench and project paths
  // cannot drift apart in what they claim. 'local' means there was no backend run to cancel
  // (nothing was in flight), which is a success, not a failure.
  function cancelText(cancel, action, what) {
    const verb = action === 'pause' ? '暂停' : '停止';
    if (cancel.cancelled) return `已${verb}后端${what},并${verb}本地结果回放。`;
    if (!cancel.error) return `已${verb}本地结果回放(后端无进行中的任务,无需取消)。`;
    if (cancel.unsupported) return `已${verb}本地结果回放(后端未实现任务${verb},服务端任务未被中断)。`;
    return `已${verb}本地结果回放(服务端任务未能确认${verb}:${cancel.error.message || '未知原因'})。`;
  }
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
      parameters:manifest.parameters || [],parameterDefs,variables,customVars:[],quickParam:parameterDefs[0]?.[0] || '',quickType:'number',drawing:{shape:'rectangle',width:32,height:30,label:manifest.name},step:100,precision:4,dirty:false,
      source:{runtime:manifest.source?.runtime || '',header:'',design:['','','']},sourceFormat:'python-v1',values,banks:[clone(values),clone(values),clone(values)],bankNames:manifest.bank_names || ['额定工况','部分负荷','调试备份']};
    return m;
  }
  function manifestPayload(m) {
    if (m.manifest) {
      const {package:ref, ...definition} = m.manifest;
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
        entrypoint:m.entrypoint, ...contract, source:{runtime:m.source.runtime}, runtime:'python',
        content_hash:null, definition_hash:null, package_path:null};
    }
    return m;
  }
  const contractFields = ['name','category','description','entrypoint','solver_model','state_model','thermal_model','ports','channels','parameters','variables','bank_names'];
  function contractText(m) {
    if (m.contractDraft !== undefined) return m.contractDraft;
    const definition=manifestPayload(m);
    return JSON.stringify(Object.fromEntries(contractFields.filter(k=>definition[k] !== undefined).map(k=>[k,definition[k]])),null,2);
  }
  function moduleForInsert(id) {
    const draft=ui.state().modules.find(m=>m.id===id);
    if (draft?.runtime !== 'python') return draft;
    if (!draft.publishedManifest) throw Error('请先校验并保存模块版本，再插入项目。');
    return {...moduleFromManifest(clone(draft.publishedManifest)),frozen:true};
  }
  function bindModule(owner, id, legacy=false) {
    owner.moduleSnapshots ||= {};
    if (owner.moduleSnapshots[id]) return owner.moduleSnapshots[id];
    const m=ui.state().modules.find(item=>item.id===id);
    if (m?.runtime !== 'python') return m;
    const source=m.publishedManifest || (legacy ? m.manifest : null);
    if (!source) throw Error('请先保存模块版本，再用于项目。');
    const snapshot={...moduleFromManifest(clone(source)),frozen:true};
    owner.moduleSnapshots[id]=snapshot;
    return snapshot;
  }
  function pinProject(owner, legacy=false) {
    for (const n of owner.pages.flatMap(p=>p.nodes)) {
      const m=bindModule(owner,n.moduleId,legacy);
      if (m?.frozen) n.package={module_id:m.id,version:`${m.version}.0.0`,content_hash:m.manifest.content_hash,definition_hash:m.manifest.definition_hash || null};
    }
  }
  function applyManifest(m, definition) {
    const keep={publishedManifest:m.publishedManifest,latestVersion:m.latestVersion,versions:m.versions,releaseNotes:m.releaseNotes};
    Object.assign(m,moduleFromManifest(definition),keep);
    ui.parameterDefinitions[m.kind]=m.parameterDefs;
    delete m.contractDraft;
    m.dirty=true;
  }
  async function checkModule(m, apply=false) {
    try {
      const definition=manifestPayload(m);
      const before=JSON.stringify(definition);
      ui.moduleOutput(m,'正在校验契约、Python 语法和生命周期入口…');
      const result=await request('/modules/validate',definition);
      if (before!==JSON.stringify(manifestPayload(m))) { ui.moduleOutput(m,'校验期间草稿已变化，请重新校验当前内容。'); return false; }
      ui.moduleOutput(m,result.valid ? '✓ Pydantic 契约与默认值通过\n✓ Python 语法通过\n✓ Worker 入口与四阶段方法通过\n下一步：独立验证算法或保存新版本。' : result.diagnostics.map(d=>`${d.field || d.code}：${d.message}`).join('\n'));
      if (apply && result.valid) { applyManifest(m,definition); ui.dirty(m); ui.render(); }
      return result.valid;
    } catch(error) { ui.moduleOutput(m,'校验失败：'+error.message); return false; }
  }
  async function versions(m) {
    try { const result=await request(`/modules/${encodeURIComponent(m.id)}/versions`); m.versions=result.versions; m.latestVersion=result.versions.length ? Number(result.versions[0].package.version.split('.')[0]) : 0; ui.render(); }
    catch(error) { ui.moduleOutput(m,'读取版本失败：'+error.message); }
  }
  async function loadVersion(m,version) {
    try {
      const result=await request(`/modules/${encodeURIComponent(m.id)}/versions/${version}`);
      applyManifest(m,result.module); m.publishedManifest=clone(result.module); m.dirty=false;
      ui.persist(); ui.render(); ui.message(`已载入 v${version}；现有项目继续使用已绑定快照。`);
    } catch(error) { ui.moduleOutput(m,'载入失败：'+error.message); }
  }
  async function saveModule(m) {
    if (m.saving) return;
    m.saving=true; ui.render();
    try {
      const definition=manifestPayload(m), before=JSON.stringify(definition);
      const test={};
      // Test the declared defaults on every save; prior bench results cannot authorize changed code.
      const bench=ui.state().bench;
      if (bench?.moduleId===m.id) Object.assign(test,{inlet_pressure_pa:bench.boundary.inlet*1000,outlet_pressure_pa:bench.boundary.outlet*1000,temperature_k:bench.boundary.temperature+273.15,dt_s:bench.run.step,duration_s:bench.run.step});
      ui.moduleOutput(m,'正在校验并进行 Worker 试算，通过后写入新版本…');
      const release=await request('/modules/versions',{module:definition,expected_latest_version:m.latestVersion ?? (m.publishedManifest?.version || 0),release_notes:m.releaseNotes || '',test});
      let unchanged=false;
      try { unchanged=before===JSON.stringify(manifestPayload(m)); } catch { /* Keep incomplete JSON edited during the save. */ }
      m.latestVersion=release.module.version;
      m.publishedManifest=clone(release.module);
      if (unchanged) { applyManifest(m,release.module); m.dirty=false; }
      ui.moduleOutput(m,`✓ v${release.module.version} 已保存到后端\n✓ Worker 试算通过，流量 ${traceFlow(m, release.test_result.frame.variables)} kg/s\n源码 SHA-256：${release.package.content_hash}\n契约 SHA-256：${release.package.definition_hash}`+(unchanged?'':'\n保存期间的新编辑已保留为草稿。'));
      await versions(m);
      try { ui.persist(); } catch { ui.message(`后端 v${release.module.version} 已保存，浏览器草稿存储失败，请导出原型。`,true); return; }
      ui.message(`模块 v${release.module.version} 已保存；已有项目版本保持绑定。`);
    } catch(error) { ui.moduleOutput(m,'版本未保存：'+error.message); ui.message('版本保存失败，草稿已保留。',true); }
    finally { m.saving=false; ui.render(); }
  }
  function newModule(id,name,category,baseId) {
    const base=ui.state().modules.find(m=>m.id===baseId && m.manifest);
    if (!base) throw Error('请等待 Python 模块模板加载完成。');
    const definition={...clone(manifestPayload(base)),id,name,category,version:1,content_hash:null,definition_hash:null,package_path:null};
    const m=moduleFromManifest(definition); m.latestVersion=0; m.dirty=true;
    ui.parameterDefinitions[m.kind]=m.parameterDefs;
    return m;
  }
  function updateContractItem(m,section,oldId,item) {
    const definition=manifestPayload(m), list=definition[section] || [];
    if (list.some(v=>v.id!==oldId && v.id===item.id)) throw Error('契约标识重复');
    const index=list.findIndex(v=>v.id===oldId);
    if(index<0) list.push(item); else list[index]=item;
    definition[section]=list; applyManifest(m,definition); ui.dirty(m); ui.render();
  }
  // A module may drive several internal channels; the single-instance short form only
  // exists for one branch, so fall back to summing the per-channel flows.
  function traceFlow(module, variables) {
    if (!variables) return null;
    if (Number.isFinite(variables['D1.mass_flow_kg_s'])) return variables['D1.mass_flow_kg_s'];
    const channels = (module?.manifest?.channels || module?.channels || []).filter(c => c.enabled !== false);
    if (!channels.length) return null;
    return channels.reduce((sum, c) => sum + (Number(variables[`D1.${c.id}.mass_flow_kg_s`]) || 0), 0);
  }
  function testParameters(module, values) {
    return Object.fromEntries(Object.entries(values).map(([key, value]) => {
      const spec = (module.parameters || []).find(p => p.id === key);
      if (spec && spec.value_type && spec.value_type !== 'number') return [key, value];
      const unit = spec?.unit;
      return [key, unit ? (Number(value) - Number(unit.display_offset || 0)) * Number(unit.display_scale || 1) : Number(value)];
    }));
  }
  function rowFromModuleTest(owner, body) {
    const vars = body.evaluation?.variables || {}, state = body.committed?.state || body.state || {};
    return {t:body.frame.time_s, canonical:body.frame.variables, variables:vars, variableValues:{}, diagnostics:body.frame.diagnostics,metrics:body.frame.metrics,q:traceFlow(owner.module, body.frame.variables),a:null,b:null,pressure:owner.boundary.outlet,temperature:owner.boundary.temperature,state,relations:body.evaluation?.relations || []};
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
      if (action === 'pause' || action === 'stop') {
        const cancel = await cancelBackend(owner, action);
        abortPending('__bench');
        // A stop really did cancel the backend run, so drop its id: keeping it would let a
        // later pause/stop aim at a run that is already gone. A pause keeps the id, because
        // 继续 has to be able to resume that same backend run.
        if (action === 'stop') owner.run.runId = null;
        owner.run.status = action === 'pause' ? 'paused' : 'stopped';
        owner.run.events ||= [];
        owner.run.events.push({t:owner.run.time,text:cancelText(cancel, action, 'Worker 计算')});
        if (cancel.error && !cancel.unsupported) ui.message('服务端任务未能确认停止,已在本地停止回放。',true);
        ui.render(); return;
      }
      if (['running','solving'].includes(owner.run.status)) return;
      const controller=new AbortController(); pending.set('__bench',controller);
      owner.run.status = 'solving'; owner.run.source = 'engine'; ui.render();
      try {
        const parameters = testParameters(module, owner.params);
        const body = await request('/modules/test',{module:manifestPayload(module),parameters,inlet_pressure_pa:Number(owner.boundary.inlet) * 1000,outlet_pressure_pa:Number(owner.boundary.outlet) * 1000,temperature_k:Number(owner.boundary.temperature) + 273.15,dt_s:owner.run.step,duration_s:owner.run.step},controller.signal);
        const row = rowFromModuleTest(owner, body);
        owner.run.history = body.history.map(f => ({...row,t:f.time_s,canonical:f.variables,q:traceFlow(module, f.variables)}));
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
      const cancel = await cancelBackend(owner, action);
      abortPending(owner.id);
      // Same as the bench path: a stop releases the backend id, a pause keeps it for 继续.
      if (action === 'stop') owner.run.runId = null;
      owner.run.status = action === 'pause' ? 'paused' : 'stopped';
      if (action === 'stop') queues.delete(owner.id);
      const cancelNote = cancelText(cancel, action, '运行');
      owner.run.events.push({t:owner.run.time,text:cancelNote});
      if (cancel.error && !cancel.unsupported) ui.message('服务端任务未能确认停止,已在本地停止回放。',true);
      ui.render(); return;
    }
    if (pending.has(owner.id)) return;
    const existing = queues.get(owner.id);
    if (existing && existing.key === key(owner) && owner.run.status === 'paused') {
      if (action === 'step') {
        const row = existing.rows.shift(); if (row) applyRow(owner,row);
        if (!existing.rows.length) { owner.run.status='completed'; queues.delete(owner.id); }
      } else {
        owner.run.status='running'; existing.wall = performance.now(); existing.sim = owner.run.time;
        // These rows are already held locally, so resuming is a replay of them; tell the
        // backend to resume too, but never let a missing/failed resume block the local restart.
        if (owner.run.runId) { const resumed = await runCommand(owner.run.runId, {action:'resume'}); if (resumed.error) owner.run.events.push({t:owner.run.time,text:'本机继续为本地结果回放;服务端恢复失败:' + resumed.error.message + '。'}); }
      }
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
      // Publish the backend id immediately so a stop pressed while this run is still being
      // polled can cancel the real task instead of only aborting the local request.
      owner.run.runId = data.run_id;
      const pollStarted = performance.now();
      let polls = 0;
      while (['queued','running'].includes(data.status)) {
        const waited = performance.now() - pollStarted;
        if (polls >= RUN_POLL_MAX_ITERATIONS || waited >= RUN_POLL_DEADLINE_MS) {
          throw Error(stallReason(data, waited >= RUN_POLL_DEADLINE_MS, waited, polls));
        }
        await new Promise((resolve,reject)=>{
          const abort=()=>{clearTimeout(timer);reject(new DOMException('请求已取消','AbortError'));};
          const timer=setTimeout(()=>{controller.signal.removeEventListener('abort',abort);resolve();},RUN_POLL_INTERVAL_MS);
          controller.signal.addEventListener('abort',abort,{once:true});
          if(controller.signal.aborted) abort();
        });
        polls += 1;
        const record=await request('/runs/'+data.run_id,undefined,controller.signal);
        data={...record,run_id:data.run_id};
      }
      if (data.status === 'cancelled') {
        owner.run.runId = null; owner.run.status='stopped';
        owner.run.events.push({t:owner.run.time,text:'后端运行已取消,本地回放同步停止。'});
        ui.render(); return;
      }
      // Terminal either way past this point: nothing is left for stop to cancel.
      owner.run.runId = null;
      if (data.status === 'failed') throw Error(await failureDetail(data,controller.signal));
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
        if (!existing) {
          const m=moduleFromManifest(manifest); m.publishedManifest=clone(manifest); m.latestVersion=manifest.version;
          ui.state().modules.push(m); ui.parameterDefinitions[m.kind]=m.parameterDefs;
        } else if (existing.manifest) {
          // Preserve local drafts. Catalog refresh only advances the available release.
          if (!existing.dirty && existing.contractDraft===undefined && existing.source.runtime===existing.manifest.source.runtime) {
            applyManifest(existing,manifest); existing.dirty=false;
          }
          existing.publishedManifest=clone(manifest); existing.latestVersion=manifest.version; existing.saving=false;
          ui.parameterDefinitions[existing.kind] = existing.manifest.parameters.filter(p => p.value_type === 'number').map(manifestParamDef);
        }
      }
      ui.state().bench ||= {moduleId:'valve',params:{},boundary:{inlet:201.325,outlet:120,temperature:20},run:ui.emptyRun('bench')};
      ui.state().modules.forEach(m => { if (m.runtime === 'python' && !m.manifest) { const manifest = (packages.modules || []).find(item => item.id === m.id); if (manifest) Object.assign(m, moduleFromManifest(manifest)); } });
      for (const owner of ui.state().projects) pinProject(owner,true);
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
  return {command,tick,validate,init,portValue,manifestPayload,contractText,checkModule,saveModule,versions,loadVersion,newModule,updateContractItem,bindModule,pinProject,moduleForInsert,get catalog(){return catalog;},get health(){return health;}};
};
