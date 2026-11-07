import {FluidNetCanvasSymbols} from './canvas-symbols.js';
import {FluidNetPanelLayout} from './panel-layout.js';
import {FluidNetParameterBatch} from './parameter-batch.js';
import {FluidNetProjectModel} from './project-model.js';
import {FluidNetProjectRunState} from './project-run-state.js';
import {FluidNetProjectState} from './project-state.js';
import {FluidNetRunCommands} from './run-commands.js';
import {ModuleTestEditor} from './module-test-editor.js';
import {createModuleService} from './module-service.js';
import {createProjectServices} from './project-services.js';
/* Adapter for the retained prototype. All calculation values originate in /api/v1. */
export const createEngineClient = function (ui) {
  const clone = value => JSON.parse(JSON.stringify(value));
  const queues = new Map(), pending = new Map();
  const controllerWrites = new Map();
  const parameterWrites = new WeakSet();
  const circuitsByProject = new Map();  // project id -> circuits of the last successful check
  const runState=FluidNetProjectRunState;
  const archiveCacheMetadata=runState.archiveCacheMetadata;
  async function confirmArchiveCache(owner, run, record, historyRows, refresh, signal) {
    let metadata = archiveCacheMetadata(run.id,record,historyRows);
    if (!metadata && refresh && run.id) {
      // The record may precede the final asynchronous archive write. One fresh
      // receipt is enough; an unavailable receipt keeps the full local cache.
      try { metadata=archiveCacheMetadata(run.id,await request('/runs/'+encodeURIComponent(run.id),undefined,signal),historyRows); }
      catch (error) { if(signal?.aborted)throw error;metadata=null; }
    }
    if (owner.run !== run || !ui.state().projects.includes(owner)) return;
    runState.setArchiveCache(run,metadata);
  }
  let catalog = null, moduleCatalog = null, health = null;
  let catalogPresentation = Object.create(null);
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
  // Access token for a server started with authentication; kept for this browser tab only.
  const TOKEN_KEY = 'fluidnet-access-token';
  const authHeaders = () => { const token = sessionStorage.getItem(TOKEN_KEY); return token ? {Authorization: 'Bearer ' + token} : {}; };
  let askingToken = false;
  function askToken(reason) {
    if (askingToken) return;
    askingToken = true;
    ui.askToken(reason, token => { sessionStorage.setItem(TOKEN_KEY, token.trim()); location.reload(); });
  }
  async function request(path, body, signal) {
    const response = await fetch('/api/v1' + path, {method: body === undefined ? 'GET' : 'POST',
      headers: {'Content-Type':'application/json', ...authHeaders()}, body: body === undefined ? undefined : JSON.stringify(body), signal});
    const data = await response.json();
    if (response.status === 401) { sessionStorage.removeItem(TOKEN_KEY); askToken('令牌无效或已撤销，请重新输入。'); }
    if (!response.ok) {
      const detail = data.detail;
      const error = Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(x => x.loc.join('.') + '：' + x.msg).join('；') : detail?.message || JSON.stringify(detail));
      error.status = response.status; error.code = detail?.code; error.detail = detail; throw error;
    }
    return data;
  }
  function payload(owner) {
    services.prepare(owner);
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
  // Failed dynamic runs whose history up to the stop is still valid (SolveFailed in the engine).
  const STOP_CODES = new Set(['TANK_EMPTY','TANK_FULL','STEP_NOT_CONVERGED']);
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
  const model=FluidNetProjectModel;
  const manifestParamDef=model.manifestParamDef;
  const moduleFromManifest=manifest=>model.moduleFromManifest(manifest,ModuleTestEditor?.defaultConditions,catalogPresentation[manifest.id]);
  const moduleService=createModuleService({request,model,moduleFromManifest,testFlow:traceFlow,
    modules:()=>ui.state().modules,getBench:()=>ui.state().bench,parameterDefinitions:ui.parameterDefinitions,
    normalizeProject:normalize,copyPanel:(source,target)=>FluidNetPanelLayout?.copy(source,target),
    copyPresentation:(source,target)=>FluidNetCanvasSymbols?.copyPresentation(source,target),
    output:ui.moduleOutput,dirty:ui.dirty,render:ui.render,persist:ui.persist,message:ui.message});
  const {manifestPayload,contractText,moduleForInsert,bindModule,pinProject,applyManifest,checkModule,
    runDesign,versions,loadVersion,saveModule,newModule,newTemplate,newComposite,updateContractItem}=moduleService;
  // A module may drive several internal channels; the single-instance short form only
  // exists for one branch, so fall back to summing the per-channel flows.
  function traceFlow(module, variables) {
    if (!variables) return null;
    if (Number.isFinite(variables['D1.mass_flow_kg_s'])) return variables['D1.mass_flow_kg_s'];
    const channels = (module?.manifest?.channels || module?.channels || []).filter(c => c.enabled !== false);
    if (!channels.length) return null;
    return channels.reduce((sum, c) => sum + (Number(variables[`D1.${c.id}.mass_flow_kg_s`]) || 0), 0);
  }
  const testParameters=model.canonicalParameters;
  function rowFromModuleTest(owner, body) {
    const vars = body.evaluation?.variables || {}, state = body.committed?.state || body.state || {};
    return {t:body.frame.time_s, canonical:body.frame.variables, variables:vars, variableValues:{}, diagnostics:body.frame.diagnostics,metrics:body.frame.metrics,q:traceFlow(owner.module, body.frame.variables),a:null,b:null,pressure:owner.boundary.outlet,temperature:owner.boundary.temperature,state,relations:body.evaluation?.relations || []};
  }
  function diagnostics(items, metrics) {
    ui.diagnostics(items.map(d => ({text:(d.severity === 'warning' ? '提示：' : '') + d.message,node:d.instance_id,
      page:d.instance_id && ui.project().pages.find(p => p.nodes.some(n => n.id === d.instance_id))?.id})), metrics);
  }
  // Prototype port-variable slot -> canonical port variable suffix (X/composition has no engine value).
  const PORT_SUFFIX = {FLOW:'mass_flow_kg_s',PRE:'pressure_pa',TEMP:'temperature_k',ENTHALPY:'enthalpy_j_kg',
    VOLUME:'density_kg_m3',Q:'quality'};
  // Canonical frame key behind a prototype variable; shared by rowFromFrame and the trend request.
  // Custom/system variables remain local; parameters use their actual runtime values.
  function canonicalKeyOf(n, v, m=ui.moduleOf(n)) {
    if (v.origin === 'port') { const suffix = PORT_SUFFIX[v.id.split(':').at(-1)]; return suffix ? `${n.id}.${v.port}.${suffix}` : null; }
    if (v.origin === 'runtime' && v.canonicalId) return `${n.id}.${v.canonicalId}`;
    if (v.origin === 'parameter') {
      const id=m.manifest ? v.param : catalog?.prototype_parameter_bindings[m.kind]?.[v.param];
      return id ? `${n.id}.param.${id}` : null;
    }
    return null;
  }
  function observation(n,v,m=ui.moduleOf(n)) {
    const canonicalKey=canonicalKeyOf(n,v,m);
    if (!canonicalKey) return {};
    let scale=1,offset=0;
    if (v.origin==='port') {
      const suffix=PORT_SUFFIX[v.id.split(':').at(-1)];
      if(suffix==='pressure_pa')scale=v.unit==='MPa'?1e6:v.unit==='kPa'?1000:1;
      if(suffix==='temperature_k' && v.unit==='°C')offset=-273.15;
      if(suffix==='enthalpy_j_kg' && v.unit==='kJ/kg')scale=1000;
      if(suffix==='mass_flow_kg_s' && m.ports.find(p=>p.id===v.port)?.direction==='out')scale=-1;
    } else {
      const spec=v.origin==='parameter' ? (m.manifest || catalog?.modules.find(d=>d.id===m.kind))?.parameters.find(p=>p.id===canonicalKey.split('.').at(-1)) : null;
      const unit=spec?.unit || v.unitSpec;
      if(unit){scale=unit.display_scale;offset=unit.display_offset;}
    }
    return {canonicalKey,canonicalScale:scale,canonicalOffset:offset};
  }
  // Canonical keys a trend-history run must keep on every frame: the overview series and the
  // project's extra chart variables. Only keys the frame will contain are sent; the backend fails
  // the run (TREND_VARIABLE_UNKNOWN) on anything else, and the run is then retried with full history.
  const TREND_LIMIT = 256;
  function overviewBindings(owner) {
    const canonical = Array.isArray(owner.instances);
    const nodes = canonical ? owner.instances : owner.pages.flatMap(page => page.nodes);
    const entries = nodes.map(node => ({node, module:canonical
      ? owner.modules.find(module => module.id === node.module_id) : ui.moduleOf(node)}));
    const channels = entries.flatMap(({node,module}) => {
      // The prototype's saved channel overrides are authoritative for its UI;
      // archived canonical projects already carry the effective contract.
      const definition = module;
      const enabled = (definition?.channels || []).filter(channel => channel.enabled !== false);
      const model = definition?.solver_model || module?.manifest?.solver_model || module?.kind;
      const role=definition.execution_role || definition.manifest?.execution_role;
      if(role && definition.ports?.some(p=>p.id==='out0'&&p.domain==='refrigerant'))
        return [{node,output:'out0',priority:0,label:`${node.id} · ${node.name}`,key:`${node.id}.mass_flow_kg_s`}];
      const priority = ['pump','pump_curve','pump_variable_speed','fan'].includes(model) ? 0
        : ['valve','valve_equal_percentage'].includes(model) ? 1 : 2;
      return enabled.flatMap(channel => {
        const output = channel.output_port || channel.output;
        const port = definition.ports?.find(port => port.id === output);
        if (!port || (port.domain || 'fluid') !== 'fluid') return [];
        return [{node,output,priority,label:`${node.id} · ${node.name}${enabled.length > 1 ? ' · '+channel.name : ''}`,
          key:`${node.id}.${enabled.length === 1 ? '' : channel.id+'.'}mass_flow_kg_s`}];
      });
    }).sort((a,b) => a.priority - b.priority);
    const bindings = {};
    channels.slice(0,3).forEach((entry,index) => {
      bindings[['q','a','b'][index]] = {key:entry.key,label:entry.label+' · 流量',short:entry.node.id,unit:'kg/s',scale:1,offset:0};
    });
    const primary = channels[0];
    if (primary) for (const [key,suffix,label,unit,scale,offset] of [
      ['pressure','pressure_pa','出口压力','kPa',1000,0], ['temperature','temperature_k','出口温度','°C',1,-273.15]]) {
      bindings[key] = {key:`${primary.node.id}.${primary.output}.${suffix}`,label:`${primary.label} · ${label}`,
        short:primary.node.id,unit,scale,offset};
    }
    return bindings;
  }
  function refrigerationReportAvailable(record) {
    const p=record?.request?.project;
    if(!p || !['completed','failed','cancelled','interrupted'].includes(record.status))return false;
    const definitions=new Map(p.modules.map(m=>[m.id,m]));
    const domains=new Set(p.instances.flatMap(n=>(definitions.get(n.module_id)?.ports||[]).map(port=>port.domain)));
    return domains.has('refrigerant') && (p.thermal_couplings?.length ? domains.has('fluid') : !domains.has('fluid'))
      || domains.has('fluid') && !domains.has('refrigerant') && !domains.has('thermal') && !p.thermal_couplings?.length;
  }
  function overviewValues(bindings, canonical) {
    return Object.fromEntries(['q','a','b','pressure','temperature'].map(key => {
      const binding = bindings[key], value = binding && canonical[binding.key];
      return [key,Number.isFinite(value) ? value / binding.scale + binding.offset : null];
    }));
  }
  function trendVariables(owner) {
    const nodes = new Map(owner.pages.flatMap(p => p.nodes).map(n => [n.id, n]));
    const keys = new Set();
    const flowKey = id => {
      // `<id>.mass_flow_kg_s` is the unprefixed alias that only single-channel devices get.
      const n = nodes.get(id), m = n && ui.moduleOf(n);
      if (m && (m.channels || []).filter(c => c.enabled !== false).length === 1) keys.add(`${id}.mass_flow_kg_s`);
    };
    const portKey = (id, port, suffix) => {
      const n = nodes.get(id), m = n && ui.moduleOf(n);
      if (m?.ports?.some(p => p.id === port && (p.domain || 'fluid') === 'fluid')) keys.add(`${id}.${port}.${suffix}`);
    };
    for (const binding of Object.values(overviewBindings(owner))) keys.add(binding.key);
    for (const binding of ui.state().charts?.extra || []) {
      if (binding.projectId !== owner.id) continue;
      if (binding.canonicalKey) { keys.add(binding.canonicalKey); continue; }
      const n = nodes.get(binding.nodeId);
      if (n && binding.variableId) {
        const v = ui.moduleOf(n)?.variables?.find(x => x.id === binding.variableId);
        const key = v && canonicalKeyOf(n, v);
        if (key) keys.add(key);
        continue;
      }
      // Legacy overview bindings such as `V1.OUT_FLOW` (no nodeId/variableId).
      const legacy = /^([^.]+)\.OUT_(FLOW|PRE|TEMP)$/.exec(binding.id || '');
      if (legacy) legacy[2] === 'FLOW' ? flowKey(legacy[1]) : portKey(legacy[1], 'out0', legacy[2] === 'PRE' ? 'pressure_pa' : 'temperature_k');
    }
    return [...keys].slice(0, TREND_LIMIT);
  }
  function portValue(n,v,row) {
    const suffix = PORT_SUFFIX[v.id.split(':').at(-1)];
    const value = suffix && row?.canonical?.[canonicalKeyOf(n,v)];
    if (!Number.isFinite(value)) return null;
    if (suffix === 'pressure_pa') return value / (v.unit === 'MPa' ? 1e6 : v.unit === 'kPa' ? 1000 : 1);
    if (suffix === 'temperature_k') return v.unit === '°C' ? value - 273.15 : value;
    if (suffix === 'enthalpy_j_kg') return v.unit === 'kJ/kg' ? value / 1000 : value;
    // Density and quality are state properties: no flow-direction sign.
    if (suffix === 'density_kg_m3' || suffix === 'quality') return value;
    const port = ui.moduleOf(n).ports.find(p => p.id === v.port);
    return value * (port?.direction === 'out' ? -1 : 1);
  }
  function rowFromFrame(owner,frame) {
    const canonical = frame.variables;
    const bindings = owner.run.overviewBindings || overviewBindings(owner);
    // partial: a trend-history frame (RunFrame.full=false) that only carries the trend variables.
    // Curves and the overview read it as usual; device panels use the latest full row (studio panelRow).
    const row = {t:frame.time_s,canonical,valid:frame.valid,partial:frame.full === false,variables:{},variableValues:{},diagnostics:frame.diagnostics,metrics:frame.metrics,
      ...overviewValues(bindings,canonical)};
    for (const n of owner.pages.flatMap(p => p.nodes)) {
      const m = owner.moduleSnapshots?.[n.moduleId] || ui.moduleOf(n);
      for (const v of m.variables) {
        const sample=observation(n,v,m), raw=canonical[sample.canonicalKey];
        const value=raw===undefined || raw===null ? v.origin==='parameter'?n.params[v.param]:null : typeof raw==='number'?raw/sample.canonicalScale+sample.canonicalOffset:raw;
        row.variableValues[n.id + ':' + v.id] = value;
      }
      for (const [k,v] of Object.entries(n.params)) row.variables[n.id + '.' + k.toUpperCase()] = v;
      const pressure = canonical[`${n.id}.out0.pressure_pa`];
      row.variables[n.id + '.OUT_FLOW'] = canonical[`${n.id}.mass_flow_kg_s`] ?? null;
      row.variables[n.id + '.OUT_PRE'] = Number.isFinite(pressure) ? pressure / 1000 : null;
      const temperature = canonical[`${n.id}.out0.temperature_k`];
      row.variables[n.id + '.OUT_TEMP'] = Number.isFinite(temperature) ? temperature - 273.15 : null;
    }
    return row;
  }
  function prepareRun(owner) {
    runState.prepare(owner.run,{overviewBindings:owner.run.overviewBindings || overviewBindings(owner),
      chartBindings:owner.run.chartBindings || (ui.state().charts?.extra||[]).filter(binding=>binding.projectId===owner.id),parameterKey:ui.parameterKey(owner)});
  }
  function applyRow(owner,row) { prepareRun(owner);runState.append(owner.run,row); }
  async function command(scope, action, projectId) {
    if(scope!=='bench')projectId ||= ui.state().activeProject;
    if (initializing) await initializing;
    if (scope !== 'bench' && health?.capabilities?.live_runs) {
      const owner = ui.state().projects.find(p => p.id === (projectId || ui.state().activeProject));
      if (owner && (owner.solver.mode === 'dynamic' || owner.run.live || action === 'step')) return liveCommand(owner, action);
    }
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
      owner.run.failureReplay=null;owner.run.diagnostics=[];
      owner.run.status = 'solving'; owner.run.source = 'engine'; ui.render();
      try {
        const parameters = testParameters(module, owner.params);
        const definition=manifestPayload(module);
        const host=definition.sdk?.capabilities?.includes('composite.refrigeration.open.v1');
        if(host && !module.testConditions?.host_project)throw Error('开放设备组缺少宿主工况，请在已连接的制冷项目中重新封装，或载入含宿主工况的模块草稿。');
        const conditions=host ? clone(module.testConditions) : {inlet_pressure_pa:Number(owner.boundary.inlet)*1000,outlet_pressure_pa:Number(owner.boundary.outlet)*1000,temperature_k:Number(owner.boundary.temperature)+273.15,...(module.testConditions?.fluid ? {fluid:clone(module.testConditions.fluid)} : {})};
        if(definition.execution_role)conditions.fluid={fluid:owner.boundary.fluid || module.testConditions?.fluid?.fluid || 'Ammonia',phase_policy:'any'};
        const body = await request('/modules/test',{...conditions,module:definition,parameters,dt_s:owner.run.step,duration_s:owner.run.step},controller.signal);
        const row = {...rowFromModuleTest(owner, body),...(host?{pressure:null,temperature:null}:{})};
        owner.run.history = body.history.map(f => ({...row,t:f.time_s,canonical:f.variables,q:traceFlow(module, f.variables)}));
        owner.run.time = row.t; owner.run.values = {q:row.q,a:null,b:null,pressure:host?null:owner.boundary.outlet,temperature:host?null:body.execution_domain==='refrigeration' ? body.frame.variables['D1.in0.temperature_k']-273.15 : owner.boundary.temperature};
        owner.run.worker = {status:'completed',contentHash:body.content_hash,version:module.version,evaluation:body.evaluation,initialState:body.state,committed:body.committed,executionDomain:body.execution_domain,refrigeration:body.refrigeration_evaluation,hostProject:host?conditions.host_project.name:null};
        owner.run.events = [{t:owner.run.time,text:host?`宿主网络试算完成：${conditions.host_project.name}。`:`Worker evaluate 完成，${body.evaluation.relations.length} 条关系已注册。`},{t:owner.run.time,text:host?`返回 ${Object.keys(body.evaluation.variables).length} 个设备组公开变量。`:`commit_step 完成，状态提交 ${Object.keys(body.committed.state || {}).length} 项。`}]; owner.run.id = body.content_hash; owner.run.status = action === 'step' ? 'paused' : 'completed'; ui.dirty(); ui.render(); ui.message(host?'开放设备组宿主网络测试完成。':'Python 模块 Worker 测试完成。');
      } catch (error) { if(error.name !== 'AbortError') { owner.run.status='failed'; owner.run.failureReplay=error.detail?.replay||null;owner.run.diagnostics=error.detail?.diagnostics||(error.detail?.message?[error.detail]:[{message:error.message}]);owner.run.events=[{t:owner.run.time,text:error.message}]; ui.message('模块测试失败：' + error.message,true); } ui.render(); }
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
    owner.run = {...ui.emptyRun(),status:'solving',source:'engine',parameterKey:ui.parameterKey(owner)};
    const ticket=runState.capture(ui.state(),owner);
    ui.render();
    try {
      const project = await normalize(owner,controller.signal);
      const mode = action === 'step' ? 'dynamic' : owner.solver.mode;
      const body = {project,mode,duration_s:action === 'step' ? owner.solver.dt : owner.solver.duration,dt_s:owner.solver.dt,...services.runMetadata(owner)};
      // A full dynamic run keeps all variables only on key frames (history slimming); single
      // steps are two frames and steady runs one, so they stay full.
      if (mode === 'dynamic' && action !== 'step') Object.assign(body,{history:'trend',trend_variables:trendVariables(owner)});
      const submit = async payload => {
        let data = await request('/runs' + (mode === 'dynamic' ? '?background=true' : ''),payload,controller.signal);
        // Publish the backend id immediately so a stop pressed while this run is still being
        // polled can cancel the real task instead of only aborting the local request.
        runState.assertCurrent(ui.state(),ticket);
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
        return data;
      };
      const trendRejected = error => error?.code === 'TREND_VARIABLE_UNKNOWN';
      let data;
      try { data = await submit(body); }
      catch (error) { if (body.history !== 'trend' || !trendRejected(error)) throw error; data = null; }
      if (body.history === 'trend' && (!data || data.status === 'failed' && (data.frame?.diagnostics || []).some(trendRejected))) {
        // A chart variable the frame does not contain: keep the run, just without history slimming.
        delete body.history; delete body.trend_variables;
        data = await submit(body);
      }
      runState.assertCurrent(ui.state(),ticket);
      if (data.status === 'cancelled') {
        owner.run.runId = null; owner.run.status='stopped';
        owner.run.events.push({t:owner.run.time,text:'后端运行已取消,本地回放同步停止。'});
        ui.render(); return;
      }
      // Terminal either way past this point: nothing is left for stop to cancel.
      owner.run.runId = null;
      owner.run.diagnostics=clone(data.frame?.diagnostics||[]);
      owner.run.diagnosticTime=data.frame?.time_s??owner.run.time;
      // A run that stopped at a tank limit or an unsolvable step keeps the frames before it; play those back.
      const stopped = data.status === 'failed' ? (data.frame?.diagnostics || []).find(d => STOP_CODES.has(d.code)) : null;
      if (data.status === 'failed' && !stopped) throw Error(await failureDetail(data,controller.signal));
      const history = await request(`/runs/${data.run_id}/history`,undefined,controller.signal);
      runState.assertCurrent(ui.state(),ticket);
      if (before !== key(owner)) throw Error('计算期间项目已变化，请重新运行当前参数。');
      if (!history.rows.length) throw Error(stopped.message);
      const rows = history.rows.map(f => rowFromFrame(owner,f));
      const metrics = stopped ? history.rows.at(-1).metrics : data.frame.metrics;
      owner.run.id = data.run_id;
      owner.run.events = (stopped ? history.rows.at(-1).diagnostics : data.frame.diagnostics).map(d => ({t:0,text:d.message}));
      owner.run.events.push({t:0,text:`后端计算完成；压力残差 ${metrics.pressure_residual_pa.toExponential(2)} Pa，质量残差 ${metrics.mass_residual_kg_s.toExponential(2)} kg/s。`});
      // S1/J2：把“请求方法 → 实际方法、Jacobian 模式”记进运行事件，便于对照报告与复现。
      const summary = (stopped ? history.rows.at(-1) : data.frame).solve_summary;
      if (summary) {
        const method = summary.effective_method === 'sparse' ? '稀疏' : '稠密';
        const requested = summary.requested_method === 'auto' ? '自动→' : '';
        const jacobian = summary.jacobian_mode === 'analytic' ? '解析' : '有限差分';
        owner.run.events.push({t:0,text:`求解：${requested}${method}，未知量 ${summary.matrix_size}，Jacobian ${jacobian}。`});
      }
      // A4：误差接受控制开启时才展示内部步长/拒绝数/局部误差范数（不可称为全局误差）。
      if (metrics.timestep_adaptive) {
        owner.run.events.push({t:0,text:`内部步长 ${metrics.internal_step_s} s；本帧接受 ${metrics.internal_steps} 步、拒绝 ${metrics.internal_rejections} 次，局部时间离散误差范数最大 ${Number(metrics.local_error_norm_max).toExponential(2)}。`});
      }
      if (stopped) owner.run.events.push({t:rows.at(-1).t,text:stopped.message});
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
      // Legacy single-step playback can concatenate several immutable run IDs;
      // its combined local history is not backed by this one archived request.
      if (action !== 'step') await confirmArchiveCache(owner,owner.run,data,history.total_rows,true,controller.signal);
      ui.dirty(owner); ui.render();
      ui.message(mode === 'steady' ? '真实稳态求解完成。' : stopped ? '运行在事件处停止：' + stopped.message
        : (history.rows[0]?.diagnostics || []).some(d => d.code === 'DYNAMIC_IMPLICIT_EULER')
          ? '动态结果已更新；水箱与管道热容按隐式 Euler 积分。' : '准稳态结果已更新；未包含热惯性和液位变化。');
    } catch (error) {
      if(!runState.isCurrent(ui.state(),ticket))return;
      if (error.name !== 'AbortError') {
        owner.run.status='failed';
        owner.run.events.push({t:0,text:error.message});
        ui.message('计算失败：' + error.message,true);
      }
      ui.render();
    } finally { if (pending.get(owner.id) === controller) pending.delete(owner.id); }
  }
  function tick() {
    for (const owner of ui.state().projects) if (owner.run.live && owner.run.runId) pollLive(owner);
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
    try {
      const owner = ui.project(), project = await normalize(owner), result = await request('/projects/validate',project);
      circuitsByProject.set(owner.id, result.circuits || []);
      diagnostics(result.diagnostics);
      ui.render();
    }
    catch (error) { diagnostics([{message:error.message,severity:'error'}]); }
  }
  // Run commands read `health` to choose live vs. legacy paths; a click right after page load
  // must wait for init, or a paused live run would be replaced by a fresh POST /runs.
  let initializing=null;
  function init(forceWorkspace=false) { return initializing=initialize(forceWorkspace); }
  async function initialize(forceWorkspace) {
    try {
      const probe = await request('/health');
      if (probe.auth?.required && !sessionStorage.getItem(TOKEN_KEY)) { health = probe; askToken('此计算服务要求访问令牌。'); return; }
      const [service,data,packages,presentation] = await Promise.all([request('/health'),request('/catalog'),request('/modules'),
        request('/catalog/presentation').catch(error=>({devices:[],warning:[404,501].includes(error.status)?'':`设备展示目录读取失败，使用兼容图标：${error.message}`}))]);
      health = service;
      catalogPresentation=model.catalogPresentationIndex(presentation);
      // Restore validation must use backend bounds, including atmospheric-pressure air sources.
      for (const [kind,bindings] of Object.entries(data.prototype_parameter_bindings)) {
        const m = data.modules.find(m => m.id === kind);
        if(!m)continue;
        // Existing built-in display aliases remain stable; expose missing declared numeric fields.
        const fields=ui.parameterDefinitions[kind];
        if(fields)for(const spec of m.parameters.filter(p=>p.value_type==='number')) {
          const displayKey=Object.keys(bindings).find(k=>bindings[k]===spec.id)||spec.id;
          if(!fields.some(f=>f[0]===displayKey)){const field=manifestParamDef(spec);field[0]=displayKey;fields.push(field);}
        }
        for (const field of fields || []) {
          const spec=m.parameters.find(p => p.id === bindings[field[0]]);
          if (!spec?.unit) continue;
          const display = value => model.toDisplay(spec,value);
          field[2]=spec.unit.display_unit; field[6]=display(spec.default);
          if (spec.minimum !== null) field[3]=display(spec.minimum);
          if (spec.maximum !== null) field[4]=display(spec.maximum);
        }
      }
      const workspaceWarning=await services.loadWorkspace(forceWorkspace);
      catalog=data;
      moduleCatalog=packages;
      model.installBuiltinCatalog({catalog:data,presentations:catalogPresentation,modules:ui.state().modules,
        parameterDefinitions:ui.parameterDefinitions,defaultConditions:ModuleTestEditor?.defaultConditions});
      for (const manifest of packages.modules || []) {
        if (manifest.runtime !== 'python') continue;
        const existing=ui.state().modules.find(m => m.id === manifest.id);
        if (!existing) {
          const m=moduleFromManifest(manifest); m.publishedManifest=clone(manifest); m.latestVersion=manifest.version;
          ui.state().modules.push(m); ui.parameterDefinitions[m.kind]=m.parameterDefs;
        } else if (existing.manifest) {
          // Preserve local drafts. Catalog refresh only advances the available release.
          if (!existing.dirty && existing.contractDraft===undefined && existing.source.runtime===existing.manifest.source.runtime && (existing.designSource || '')===(existing.manifest.source.design || '')) {
            applyManifest(existing,manifest); existing.dirty=false;
          }
          existing.publishedManifest=clone(manifest); existing.latestVersion=manifest.version; existing.saving=false;
          ui.parameterDefinitions[existing.kind] = existing.manifest.parameters.filter(p => p.value_type === 'number').map(manifestParamDef);
        }
      }
      ui.state().bench ||= {moduleId:'valve',params:{},boundary:{inlet:201.325,outlet:120,temperature:20},run:ui.emptyRun('bench')};
      ui.state().modules.forEach(m => { if (m.runtime === 'python' && !m.manifest) { const manifest = (packages.modules || []).find(item => item.id === m.id); if (manifest) Object.assign(m, moduleFromManifest(manifest)); } });
      // Expose new legacy numeric catalog fields before freezing presentation snapshots.
      // Otherwise old sample instances can miss a field now required by their frozen editor.
      ui.prepareLegacyParameters?.();
      for (const owner of ui.state().projects) pinProject(owner,true);
      ui.state().bench.params ||= {};
      const benchModule = ui.state().modules.find(m => m.id === ui.state().bench.moduleId) || ui.state().modules.find(m => m.runtime === 'python' && m.manifest);
      if (benchModule && !Object.keys(ui.state().bench.params).length) ui.state().bench.params = Object.fromEntries((ui.parameterDefinitions[benchModule.kind] || []).map(f => [f[0], f[6]]));
      if (!benchModule?.manifest && !ui.state().bench.run.history.length) {
        const pythonModule=ui.state().modules.find(m=>m.runtime==='python' && m.manifest);
        if (pythonModule) { ui.state().bench.moduleId=pythonModule.id; ui.state().bench.params=Object.fromEntries(ui.parameterDefinitions[pythonModule.kind].map(f=>[f[0],f[6]])); }
      }
      ui.message(workspaceWarning || presentation?.warning || `计算服务 v${health.version} 已连接：稳态水力${health.capabilities?.tank_state ? '、水箱隐式积分' : ''}与准稳态时间序列可用。`,!!(workspaceWarning||presentation?.warning));
      ui.render();
      await services.refreshArchives();
    } catch (error) { const local=/^本地草稿/.test(error.message||''); ui.message((local ? '' : '计算服务未连接，请通过启动脚本打开此页面。') + error.message,true); }
  }
  let runCommands;
  function liveRuns() {
    return runCommands ||= FluidNetRunCommands.create({state:ui.state,request,runState,pending,key,parameterKey:ui.parameterKey,
      normalize,runMetadata:owner=>services.runMetadata(owner),trendVariables,emptyRun:ui.emptyRun,prepareRun,rowFromFrame,
      confirmArchiveCache,persist:ui.persist,render:ui.refreshRun||ui.render,refresh:ui.refresh,message:ui.message});
  }
  const pollLive=owner=>liveRuns().pollLive(owner);
  const confirmedCommand=(owner,body)=>liveRuns().confirmedCommand(owner,body);
  const liveCommand=(owner,action)=>liveRuns().liveCommand(owner,action);
  const loadOverview=owner=>liveRuns().loadOverview(owner);
  function applyController(owner,controllerId,field,value) {
    const ticket=runState.capture(ui.state(),owner);
    const job=(controllerWrites.get(owner) || Promise.resolve()).catch(()=>{}).then(async()=>{
      const beforeKey=ui.parameterKey(owner);
      runState.assertCurrent(ui.state(),ticket);
      const controller=owner.controllers.find(c=>c.id===controllerId);
      if(!controller)throw Error('控制器已不存在，请重新选择。');
      await confirmedCommand(owner,{action:'controller',controller_id:controllerId,parameter_id:field,value});
      runState.assertCurrent(ui.state(),ticket);
      if(owner.controllers.find(c=>c.id===controllerId)!==controller)throw Error('控制器已被替换。');
      const currentKey=ui.parameterKey(owner);
      controller[field]=value;
      runState.advanceParameterKey(owner.run,beforeKey,currentKey,ui.parameterKey(owner));
      ui.dirty(owner);ui.persist();
    });
    controllerWrites.set(owner,job);
    return job.finally(()=>{if(controllerWrites.get(owner)===job)controllerWrites.delete(owner);});
  }
  async function applyParameters(owner,node,proposed=node.draft,onAccepted) {
    if(parameterWrites.has(node))throw Error('设备参数正在应用，请等待确认后再提交。');
    parameterWrites.add(node);
    try{return await applySingleParameters(owner,node,proposed,onAccepted);}
    finally{parameterWrites.delete(node);}
  }
  async function applySingleParameters(owner,node,proposed=node.draft,onAccepted) {
    const ticket=runState.capture(ui.state(),owner),beforeKey=ui.parameterKey(owner);
    FluidNetProjectState.assertCurrent(ui.state(),owner);
    FluidNetProjectState.node(owner,node);
    const m=ui.moduleOf(node), definition=m.manifest || catalog.modules.find(d=>d.id===m.kind);
    const bindings=m.manifest ? null : catalog.prototype_parameter_bindings[m.kind];
    const edits=Object.entries(proposed).filter(([key,value])=>JSON.stringify(value)!==JSON.stringify(node.params[key])).map(([key,value])=>{
      const id=bindings?.[key] || key, spec=definition.parameters.find(p=>p.id===id);
      if(!spec?.runtime || !spec.writable) throw Error(`${spec?.label || key} 不能在运行中修改，请停止后应用。`);
      const canonical=spec.unit ? model.toCanonical(spec,value) : value;
      return {key,value:clone(value),id,canonical:clone(canonical)};
    });
    if (!edits.length && !onAccepted) return;
    // One device-panel apply is one frame-boundary transaction. Keep every draft
    // and applied value intact until the whole batch has been acknowledged.
    if(edits.length)await confirmedCommand(owner,{action:'write',values:Object.fromEntries(edits.map(edit=>[
      `${node.id}.param.${edit.id}`,edit.canonical]))});
    runState.assertCurrent(ui.state(),ticket);
    FluidNetProjectState.assertCurrent(ui.state(),owner);
    FluidNetProjectState.node(owner,node);
    const currentKey=ui.parameterKey(owner);
    FluidNetProjectState.applyParameters(owner,node,Object.fromEntries(edits.map(edit=>[edit.key,edit.value])));
    onAccepted?.();
    runState.advanceParameterKey(owner.run,beforeKey,currentKey,ui.parameterKey(owner));ui.persist();ui.render();
  }
  async function applyParameterBatch(owner,entries) {
    const ticket=runState.capture(ui.state(),owner),beforeKey=ui.parameterKey(owner),live=!!owner.run.live;
    if(pending.has(owner.id)||!live&&['running','solving','paused'].includes(owner.run.status))throw Error('请先停止当前计算或回放，再批量编辑。');
    const describe=node=>{
      const m=ui.moduleOf(node);
      return {definition:m.manifest||catalog?.modules.find(d=>d.id===m.kind),
        bindings:m.manifest?null:catalog?.prototype_parameter_bindings[m.kind]};
    };
    const plan=FluidNetParameterBatch.prepare(ui.state(),owner,entries,describe);
    for(const item of plan.items)if(parameterWrites.has(item.node))throw Error('设备参数正在应用，请等待确认后再提交。');
    for(const item of plan.items)parameterWrites.add(item.node);
    try {
      let receipt;
      if(live&&Object.keys(plan.values).length)receipt=await confirmedCommand(owner,{action:'write',values:plan.values});
      runState.assertCurrent(ui.state(),ticket);
      const currentKey=ui.parameterKey(owner);
      FluidNetParameterBatch.commit(ui.state(),owner,plan,describe);
      if(live)runState.advanceParameterKey(owner.run,beforeKey,currentKey,ui.parameterKey(owner));
      owner.run.events ||= [];
      owner.run.events.push({t:receipt?.time_s??owner.run.time,kind:'parameters',text:`批量应用 ${plan.items.length} 台设备、${Object.keys(plan.values).length} 项参数`});
      ui.dirty(owner);ui.persist();ui.render();
      return receipt;
    } finally {for(const item of plan.items)parameterWrites.delete(item.node);}
  }
  const services=createProjectServices({request,ui,normalize,health:()=>health,authHeaders,pinProject,moduleFromManifest});
  return {...services,cacheCircuits:(owner,items)=>{circuitsByProject.set(owner.id,items||[]);ui.render();},archiveCacheMetadata,overviewBindings,overviewValues,refrigerationReportAvailable,request,normalize,moduleFromManifest,whenReady:()=>initializing || Promise.resolve(),command,tick,validate,init,applyController,applyParameters,applyParameterBatch,isApplyingParameters:node=>parameterWrites.has(node),loadOverview,authHeaders,signOut:()=>{sessionStorage.removeItem(TOKEN_KEY);location.reload();},overview:id=>runCommands?.overview(id),circuits:id=>circuitsByProject.get(id)||[],confirmedCommand,portValue,observation,manifestPayload,contractText,checkModule,saveModule,runDesign,versions,loadVersion,newModule,newTemplate,newComposite,updateContractItem,bindModule,pinProject,moduleForInsert,get catalog(){return catalog;},get health(){return health;}};
};

export default createEngineClient;
