/* Workspace data normalization. No DOM, storage or transport access; callers
 * provide definitions and existing project/model adapters. */
export const FluidNetWorkspaceNormalization = (() => {
  function create({parameterDefinitions: PARAM_DEFS, variablesFor, clone,
    moduleSpecs: MODULE_SPECS, pythonModuleSource, legacyModuleSource,
    defaultGroups, manifestFields, manifestParamSpecs, emptyRun, pinProject,
    normalizeControls, moduleOf, validateInstanceVariableState, ensureInstanceVariables,
    rehome, projectVariables}) {
    function normalizeGroups(data) {
      for (const module of data.modules) if (!module.category) module.category = '自定义模块';
      const groups = [...new Set([...defaultGroups, ...(data.moduleGroups || []),
        ...data.modules.map(module => module.category).filter(name => typeof name === 'string' && name.trim())])]
        .filter(name => !defaultGroups.includes(name));
      if (groups.length > 64) throw Error('最多保留 64 个自建模块分组。');
      data.moduleGroups = groups;
    }
function normalizePythonSource(m) {
  if (m.runtime === 'python' || m.sourceFormat === 'python-v1') return;
  const next = pythonModuleSource(m.kind, m.code);
  const candidates = [m.code, MODULE_SPECS.find(spec => spec[0] === m.kind)?.[2]].filter(Boolean).map(code => legacyModuleSource(m.kind, code));
  const same = (a, b) => typeof a === 'string' && a.replace(/\r\n/g, '\n') === b;
  for (const key of ['runtime', 'header']) if (candidates.some(old => same(m.source[key], old[key]))) m.source[key] = next[key];
  m.source.design = m.source.design.map((source, i) => candidates.some(old => same(source, old.design[i])) ? next.design[i] : source);
  m.sourceFormat = 'python-v1';
}
function backfillBuiltinParams(data) {
  const builtin = (data.modules || []).filter(m => m && m.runtime !== 'python' && PARAM_DEFS[m.kind]);
  // A short-lived pre-catalog editor used 8 g/kg while the source contract stores kg/kg.
  // Repair only that fingerprint and its invalid default, never rescale valid canonical values
  // or frozen manifest snapshots. Older workspaces without this field receive the contract default.
  const repairedHumidity=new Set();
  for(const m of builtin.filter(m=>m.kind==='source'&&!m.manifest)) {
    const v=m.variables?.find(v=>v.id==='param:humidity_ratio_kg_kg');
    if(v?.unit!=='g/kg_da'||v.value!==8)continue;
    v.unit='1';v.value=.008;repairedHumidity.add(m.id);
    for(const bank of [m.values,...(m.banks||[])])if(bank?.[v.id]===8)bank[v.id]=.008;
  }
  const repairHumidity=params=>{if(params?.humidity_ratio_kg_kg===8)params.humidity_ratio_kg_kg=.008;};
  for(const item of data.models||[])if(repairedHumidity.has(item.moduleId)) {
    repairHumidity(item.params);for(const version of item.versions||[])repairHumidity(version.params);
  }
  for(const p of data.projects||[])for(const pg of p.pages||[])for(const n of pg.nodes||[])
    if(!p.moduleSnapshots?.[n.moduleId]&&repairedHumidity.has(n.moduleId)) {
      repairHumidity(n.params);repairHumidity(n.draft);
      for(const bank of n.variableState?.banks||[])if(bank['param:humidity_ratio_kg_kg']===8)bank['param:humidity_ratio_kg_kg']=.008;
    }
  for (const m of builtin) {
    if (!Array.isArray(m.variables)) continue;
    for (const v of variablesFor({kind:m.kind, ports:[]}).filter(v => v.origin === 'parameter' || v.origin === 'runtime')) {
      if (m.variables.some(x => x.id === v.id)) continue;
      const before = m.variables.findIndex(x => x.origin === 'system');
      m.variables.splice(before < 0 ? m.variables.length : before, 0, v);
      if (m.values && !(v.id in m.values)) m.values[v.id] = clone(v.value);
      (m.banks || []).forEach(bank => { if (bank && !(v.id in bank)) bank[v.id] = clone(v.value); });
    }
  }
  const fill = (params, kind) => { if (params && typeof params === 'object') for (const f of PARAM_DEFS[kind]) if (!(f[0] in params)) params[f[0]] = f[6]; };
  const kindOf = id => builtin.find(m => m.id === id)?.kind;
  for (const item of data.models || []) { const kind = kindOf(item?.moduleId); if (kind) { fill(item.params, kind); (item.versions || []).forEach(v => fill(v?.params, kind)); } }
  for (const p of data.projects || []) for (const pg of p?.pages || []) for (const n of pg?.nodes || []) {
    const kind = !p.moduleSnapshots?.[n?.moduleId] && kindOf(n?.moduleId);
    if (kind) { fill(n.params, kind); fill(n.draft, kind); }
  }
}
function normalize(state) {
  normalizeGroups(state);
  state.modules.forEach(m => { m.saving=false; if (m.manifest) PARAM_DEFS[m.kind] = manifestFields(m.manifest); normalizePythonSource(m); });
  backfillBuiltinParams(state);
  state.windowPositions ||= {}; state.charts ||= {}; state.charts.series ||= {q:true,a:true,b:true}; state.charts.extra ||= []; state.charts.range ||= 'window'; state.serial ||= 30; state.messages ||= [];
  // 兼容旧草稿：运行快照/验证台/项目运行可能缺少 history、events、values 等字段（例如被裁剪过的草稿），
  // 补齐默认值后继续打开与保存，而不是让 normalizeState 抛错、整份草稿被内置示例覆盖。
  state.records = Array.isArray(state.records) ? state.records : [];
  for (const record of state.records) { record.history = Array.isArray(record.history) ? record.history : []; record.events = Array.isArray(record.events) ? record.events : []; }
  state.bench ||= {}; state.bench.run ||= emptyRun('bench');
  const benchModule = state.bench && state.modules.find(m => m.id === state.bench.moduleId);
  if (benchModule?.runtime === 'python') { state.bench.params ||= {}; for (const spec of manifestParamSpecs(benchModule.manifest)) if (!(spec.id in state.bench.params)) state.bench.params[spec.id] = clone(spec.default); }
  for (const p of state.projects) {
    p.scenarios ||= [];p.activeScenarioId ||= '';
    pinProject(p, true);
    normalizeControls(p);
    if (!p.run || typeof p.run !== 'object') p.run = emptyRun();
    if (p.run.source !== 'engine') p.run = emptyRun();
    if (p.run.status === 'solving') p.run.status = 'ready';
    p.run.events ||= []; p.run.history ||= []; p.run.values ||= emptyRun().values;
    for (const pg of p.pages) { pg.zoom ||= 1; pg.pan ||= [0, 0]; for (const n of pg.nodes) { const m = moduleOf(n, p, state); if (m.runtime === 'python') for (const spec of manifestParamSpecs(m.manifest)) { if (!(spec.id in n.params)) n.params[spec.id] = clone(spec.default); if (!n.draft || !(spec.id in n.draft)) { n.draft ||= clone(n.params); n.draft[spec.id] = clone(n.params[spec.id]); } } n.draft ||= clone(n.params); validateInstanceVariableState(n, m); ensureInstanceVariables(n, m, p); } }
    rehome(p);
    const variables = projectVariables(p);
    for (const field of ['input', 'output']) if (!variables.some(v => v.id === p.controlConfig[field])) {
      const legacy = variables.find(v => v.legacyId === p.controlConfig[field]); if (legacy) p.controlConfig[field] = legacy.id;
    }
  }
  if (state.bench.run.status === 'solving') state.bench.run.status = 'ready';
  state.bench.run.events ||= []; state.bench.run.history ||= []; state.bench.run.values ||= emptyRun().values;
}
    return {backfillBuiltinParams, normalize, normalizePythonSource, normalizeGroups};
  }
  return {create};
})();

export default FluidNetWorkspaceNormalization;
