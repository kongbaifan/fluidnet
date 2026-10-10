// 曲线绑定稳定的变量 ID，采样使用变量表中的单位；旧曲线仍可读取旧采样格式。
function variableObservation(n, v, owner = ownerOfInstance(n)) {
  if (v.type.endsWith('[8]')) return null;
  let legacyId = v.origin === 'parameter' ? n.id + '.' + v.param.toUpperCase() : null, factor = 1;
  if (v.origin === 'port') {
    const outlets = moduleOf(n).ports.filter(p => p.domain === 'fluid' && p.direction === 'out');
    const suffix = { FLOW: 'OUT_FLOW', PRE: 'OUT_PRE', TEMP: 'OUT_TEMP' }[v.id.split(':').at(-1)];
    if (outlets.length !== 1 || v.port !== outlets[0].id || !suffix) return null;
    legacyId = n.id + '.' + suffix; factor = suffix === 'OUT_PRE' ? .001 : 1;
  } else if (!['parameter', 'custom', 'system'].includes(v.origin)) return null;
  return { id: n.id + '.' + v.name, legacyId, nodeId: n.id, variableId: v.id, identifier: n.id + '.' + v.name,
    name: v.label, device: n.name, unit: v.unit, value: instanceVariableValue(n, v, owner), writable: instanceWritable(v),
    origin: v.origin, sampleKey: n.id + ':' + v.id, legacyFactor: factor };
}
function projectVariables(owner = project()) {
  return owner.pages.flatMap(pg => pg.nodes).flatMap(n => moduleOf(n).variables.map(v => variableObservation(n, v, owner)).filter(Boolean));
}
function sampleVariableValues(owner, legacyValues) {
  return Object.fromEntries(projectVariables(owner).map(v => [v.sampleKey,
    v.origin === 'port'
      ? Number.isFinite(legacyValues[v.legacyId]) ? legacyValues[v.legacyId] * v.legacyFactor : null : clone(v.value)]));
}
function observeInstanceVariable(id, variableId) {
  const n = instance(id), v = n && moduleOf(n).variables.find(v => v.id === variableId), binding = v && variableObservation(n, v);
  if (!binding) throw Error('此变量暂不提供曲线采样；数组和未采样端口可在表格中查看。');
  const f = ui.floats.find(f => f.id === id);
  if (f) {
    if (innerWidth >= 1000) {
      for (const other of ui.floats) if (other !== f && other.docked) { other.docked = false; rememberWindow(other); }
      f.docked = true; f.minimized = false; rememberWindow(f);
    } else f.minimized = true;
  }
  addChartVariable(binding.id, undefined, true);
}
function variableObservationButton(n, v) {
  const binding = variableObservation(n, v), observed = binding && state.charts.extra.some(item => item.projectId === project().id && item.nodeId === n.id && item.variableId === v.id);
  const unavailable = v.type.endsWith('[8]') ? '数组暂不支持曲线' : '此端口变量尚未提供采样';
  return ibtn('observe-instance-variable', binding ? `同屏观察 ${n.id}.${v.name}` : unavailable, 'Activity', `data-id="${n.id}" data-variable="${esc(v.id)}" ${binding ? `aria-pressed="${!!observed}"` : 'disabled'}`);
}
function instanceModelValues(n, source) {
  const data = ensureInstanceVariables(n);
  if (!['current', 'draft', 'bank:0', 'bank:1', 'bank:2'].includes(source)) throw Error('请选择有效的数据来源。');
  return Object.fromEntries(moduleOf(n).variables.filter(instanceWritable).map(v => [v.id,
    clone(source === 'current' ? instanceVariableValue(n, v) : source === 'draft' ? instanceDraftValue(n, v) : data.banks[Number(source.slice(-1))][v.id]) ]));
}
function instanceModelPreview(n, source) {
  const values = instanceModelValues(n, source);
  return `<div class="table-wrap"><table class="model-source-table"><thead><tr><th>变量</th><th>保存值</th><th>单位</th></tr></thead><tbody>${moduleOf(n).variables.filter(instanceWritable).map(v => `<tr><td>${esc(v.label)}<small>${esc(v.name)}</small></td><td class="mono">${esc(variableDisplay(values[v.id], v, moduleOf(n).precision))}</td><td>${esc(v.unit)}</td></tr>`).join('')}</tbody></table></div>`;
}
function saveInstanceModel(id) {
  const n = instance(id); if (!n) return;
  const m = moduleOf(n), config = ui.floats.find(f => f.id === id), source = config?.tab === 'variables' && variableWindowState(config).source >= 0 ? 'bank:' + variableWindowState(config).source : 'current';
  const sources = [['current', '当前已生效值'], ['draft', '待应用草稿'], ...ensureInstanceVariables(n).bankNames.map((name, i) => ['bank:' + i, `库值 ${i + 1} · ${name}`])];
  if (!m.variables.some(instanceWritable)) throw Error('此模块没有可保存的设备参数或自定义变量。');
  openDialog(`保存设备型号 · ${n.id}`, '选择数据来源，将参数和自定义变量保存为可复用型号。端口结果与项目系统设置不写入型号。',
    `<div class="fields">${field('name', '型号名称', n.name + ' · 参数方案', 'required maxlength="60"')}<label class="field"><span>数据来源</span><select name="source" aria-label="型号数据来源" data-device-model-source="${n.id}">${sources.map(([key, label]) => option(key, label, source)).join('')}</select></label></div><div class="model-source-preview" id="device-model-preview">${instanceModelPreview(n, source)}</div>`, fields => {
      const name = fields.name.trim(), values = instanceModelValues(n, fields.source);
      if (!name) throw Error('请输入型号名称。');
      if (state.models.some(item => item.moduleId === m.id && item.name === name)) throw Error('同一模块已有此型号名称，请换一个名称。');
      if (state.models.length >= 500) throw Error('已达到型号数量上限。');
      validateInstanceEdits(n, values);
      const params = Object.fromEntries(m.variables.filter(v => v.origin === 'parameter').map(v => [v.param, values[v.id]]));
      const sourceLabel = `${n.id} · ${sources.find(([key]) => key === fields.source)[1]}`, note = `从 ${project().name} / ${sourceLabel} 保存`;
      state.models.push({ id: uid('model'), moduleId: m.id, name, description: note, sourceLabel, version: 1, moduleVersion: m.version,
        params, values: clone(values), bank: fields.source.startsWith('bank:') ? Number(fields.source.slice(-1)) + 1 : 1, archived: false,
        versions: [{ version: 1, note, params: clone(params), values: clone(values) }] });
      markDirty(); retainFocus(renderFloats); msg('型号已保存，可在当前设备或同模块设备中选择应用。');
    }, '保存型号', true);
}
function modelVariableSummary(item) {
  const variables = mod(item.moduleId).variables.filter(v => v.origin === 'custom' && item.values?.[v.id] !== undefined);
  return `${item.sourceLabel ? `<small class="muted">来源：${esc(item.sourceLabel)}</small>` : ''}${variables.length ? `<div class="model-variable-summary"><h3>自定义变量</h3><dl>${variables.map(v => `<dt>${esc(v.label)} <small>${esc(v.unit)}</small></dt><dd class="mono">${esc(variableDisplay(item.values[v.id], v, mod(item.moduleId).precision))}</dd>`).join('')}</dl></div>` : ''}`;
}
function validateModelVariables(item, m) {
  if (item.values !== undefined && (!item.values || typeof item.values !== 'object' || Array.isArray(item.values))) throw Error('型号变量数据不完整。');
  const values = Object.fromEntries(m.variables.filter(instanceWritable).map(v => [v.id, v.origin === 'parameter' ? item.params[v.param]
    : item.values && v.id in item.values ? item.values[v.id] : m.values[v.id]]));
  validateInstanceEdits(null, values, m);
}
