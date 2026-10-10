/* Adapter for the retained prototype. All calculation values originate in /api/v1. */
window.createEngineClient = function (ui) {
  const queues = new Map(), pending = new Map();
  let catalog = null;
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
    return {format:'fluidnet-studio-prototype',schema:1,activeProject:owner.id,projects:[owner],modules:state.modules};
  }
  function key(owner) {
    return ui.parameterKey(owner) + JSON.stringify(ui.state().modules.filter(m => owner.pages.some(p => p.nodes.some(n => n.moduleId === m.id))).map(m => [m.id,m.version,m.ports,m.channels]));
  }
  async function normalize(owner, signal) { return request('/prototype/normalize',payload(owner),signal); }
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
        const value = v.origin === 'port' ? portValue(n,v,row) : v.origin === 'parameter' ? n.params[v.param] : null;
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
    if (scope !== 'project') { ui.message('独立模块测试尚未接入；请在主系统中配置压力边界后运行。',true); return; }
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
      const data = await request('/runs',{project,mode,duration_s:action === 'step' ? owner.solver.dt : owner.solver.duration,dt_s:owner.solver.dt},controller.signal);
      if (data.status === 'failed') { diagnostics(data.frame.diagnostics); throw Error(data.frame.diagnostics.map(d => d.message).join('；')); }
      const history = await request(`/runs/${data.run_id}/history`,undefined,controller.signal);
      if (before !== key(owner)) throw Error('计算期间项目已变化，请重新运行当前参数。');
      const rows = history.rows.map(f => rowFromFrame(owner,f));
      owner.run.id = data.run_id;
      owner.run.events = data.frame.diagnostics.map(d => ({t:0,text:d.message}));
      owner.run.events.push({t:0,text:`后端计算完成；压力残差 ${data.frame.metrics.pressure_residual_pa.toExponential(2)} Pa，质量残差 ${data.frame.metrics.mass_residual_kg_s.toExponential(2)} kg/s。`});
      if (action === 'step') {
        // Each step is a new immutable solve; keep the sequence with the parameters that produced each row.
        const base = old.source === 'engine' ? old.time : 0;
        owner.run.history = old.source === 'engine' ? old.history : [];
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
      const [health,data] = await Promise.all([request('/health'),request('/catalog')]);
      catalog=data;
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
  return {command,tick,validate,init,portValue,get catalog(){return catalog;}};
};
