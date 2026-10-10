// Local interaction model. No solver, user-code execution, network or hardware access.
const uid = prefix => `${prefix}-${++state.serial}`;
const windowKey = id => `${state.activeProject}:${id}`;
const field = (name, label, value = '', attrs = '') => `<label class="field"><span>${esc(label)}</span><input name="${name}" aria-label="${esc(label)}" value="${esc(value)}" ${attrs}></label>`;
const selectField = (name, label, items, value) => `<label class="field"><span>${esc(label)}</span><select name="${name}" aria-label="${esc(label)}">${items.map(([id, text]) => option(id, text, value)).join('')}</select></label>`;
const isIdentifier = value => /^[A-Za-z_][A-Za-z0-9_]{0,47}$/.test(value);
function numeric(value, min = -1e12, max = 1e12, integer = false) {
  if (value === '' || value === null || !Number.isFinite(Number(value))) throw Error('请输入有效数值。');
  const n = Number(value);
  if (n < min || n > max || integer && !Number.isInteger(n)) throw Error(`请输入 ${min} 至 ${max} 之间的${integer ? '整数' : '数值'}。`);
  return n;
}
function readParams(data, kind, prefix = '') {
  return Object.fromEntries((PARAM_DEFS[kind] || []).map(f => [f[0], numeric(data[prefix + f[0]], f[3], f[4])]));
}
function paramsFields(kind, values) {
  return (PARAM_DEFS[kind] || []).map(f => field(f[0], `${f[1]} · ${f[2]}`, values[f[0]] ?? f[6], `type="number" min="${f[3]}" max="${f[4]}" step="any" required`)).join('');
}
function retainFocus(renderFn = render) {
  const el = document.activeElement, selection = el?.selectionStart;
  const attrs = el && [...el.attributes].filter(a => a.name.startsWith('data-') || a.name === 'aria-label' || a.name === 'name');
  const ancestor = el?.closest('[data-float-id]')?.dataset.floatId;
  const scrollKey = e => `${e.closest('[data-float-id]')?.dataset.floatId || ''}:${e.id || e.className}`;
  const scrolls = [...root.querySelectorAll('#page,.editor-content,.table-wrap,.float-body,.instance-table-wrap')].map(e => [scrollKey(e), e.scrollTop, e.scrollLeft]);
  renderFn();
  for (const e of root.querySelectorAll('#page,.editor-content,.table-wrap,.float-body,.instance-table-wrap')) {
    const old = scrolls.find(s => s[0] === scrollKey(e));
    if (old) { e.scrollTop = old[1]; e.scrollLeft = old[2]; }
  }
  if (!attrs?.length) return;
  const scope = ancestor ? root.querySelector(`[data-float-id="${CSS.escape(ancestor)}"]`) : root;
  const next = [...(scope?.querySelectorAll('input,textarea,select,button') || [])].find(e => e.tagName === el.tagName && attrs.every(a => e.getAttribute(a.name) === a.value));
  next?.focus({ preventScroll: true });
  if (typeof selection === 'number' && next?.setSelectionRange) try { next.setSelectionRange(selection, selection); } catch {}
}
function openDialog(title, description, body, onSubmit = null, submitLabel = '确定', wide = false) {
  modal = { title, description, body, onSubmit, submitLabel, wide, returnFocus: document.activeElement };
  renderDialog(true);
}
function renderDialog(focus = false) {
  const layer = document.getElementById('dialog-layer');
  if (!modal) { layer.innerHTML = ''; return; }
  if (!focus && layer.firstElementChild) return;
  layer.innerHTML = `<div class="dialog-backdrop"><form class="dialog${modal.wide ? ' wide' : ''}" id="dialog-form" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><header class="dialog-head"><div class="grow"><h2 id="dialog-title">${esc(modal.title)}</h2><p>${esc(modal.description)}</p></div>${ibtn('close-dialog', '关闭弹窗', 'X')}</header><div class="dialog-body"><div id="dialog-error" class="dialog-error" role="alert" hidden></div>${modal.body}</div><footer class="dialog-footer">${btn('close-dialog', modal.onSubmit ? '取消' : '关闭')}${modal.onSubmit ? `<button class="btn primary" type="submit">${esc(modal.submitLabel)}</button>` : ''}</footer></form></div>`;
  if (focus) requestAnimationFrame(() => (layer.querySelector('input:not([type=hidden]),select,textarea') || layer.querySelector('button'))?.focus());
}
function closeDialog() {
  const returnFocus = modal?.returnFocus;
  modal = null;
  document.getElementById('dialog-layer').innerHTML = '';
  if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
}
function confirmChange(title, text, callback, label = '确认') {
  openDialog(title, text, '', () => { callback(); }, label);
}
function diffMarkup(rows) {
  return `<div class="table-wrap"><table class="diff-table"><thead><tr><th>项目</th><th>当前值</th><th>应用后</th></tr></thead><tbody>${rows.map(([label, before, after]) => `<tr><td>${esc(label)}</td><td class="before">${esc(Array.isArray(before) ? before.join(', ') : before)}</td><td class="after">${esc(Array.isArray(after) ? after.join(', ') : after)}</td></tr>`).join('') || '<tr><td colspan="3">没有参数差异。</td></tr>'}</tbody></table></div>`;
}
function checkChannels(m) {
  const used = new Set(), errors = [];
  for (const c of m.channels.filter(c => c.enabled)) {
    const a = m.ports.find(p => p.id === c.input), b = m.ports.find(p => p.id === c.output);
    if (!a || !b) { errors.push(`${c.name}：请选择完整的入口和出口。`); continue; }
    if (a.direction !== 'in' || b.direction !== 'out') errors.push(`${c.name}：输入输出方向不匹配。`);
    if (a.domain !== b.domain) errors.push(`${c.name}：两端类型不同。`);
    for (const p of [a, b]) { if (used.has(p.id)) errors.push(`${p.name} 重复绑定了启用通路。`); used.add(p.id); }
  }
  return errors;
}
function validateBank(m, bank) {
  for (const v of m.variables.filter(v => v.writable)) {
    const value = bank[v.id], arr = v.type.endsWith('[8]');
    if (arr && (!Array.isArray(value) || value.length !== 8)) throw Error(`${v.name} 必须含 8 项。`);
    for (const n of arr ? value : [value]) numeric(n, -1e12, 1e12, v.type.startsWith('int'));
    const f = (PARAM_DEFS[m.kind] || []).find(f => f[0] === v.param);
    if (f) numeric(value, f[3], f[4]);
  }
  numeric(bank['system:step'], 1, 10000, true);
  const form = bank['system:form'], mix = bank['system:mix'];
  const fluids = form.filter(Boolean);
  if (!fluids.length || new Set(fluids).size !== fluids.length || fluids.some(id => !FLUIDS.some(f => f[2] === id))) throw Error('请选择不重复的示例工质编号；0 表示空项。');
  mix.forEach((n, i) => { numeric(n, 0, 1); if (!form[i] && n !== 0) throw Error('空工质项的质量比例必须为 0。'); });
  if (Math.abs(mix.reduce((a, b) => a + b, 0) - 1) > 1e-6) throw Error('工质质量比例之和必须为 1，可先点击“归一化”。');
}
function refreshPortVariables(m) {
  const generated = variablesFor(m).filter(v => v.origin === 'port');
  const old = new Map(m.variables.map(v => [v.id, v]));
  m.variables = generated.map(v => old.has(v.id) ? { ...old.get(v.id), name: v.name, label: v.label } : v).concat(m.variables.filter(v => v.origin !== 'port'));
  for (const values of [m.values, ...m.banks]) {
    for (const v of m.variables) if (!(v.id in values)) values[v.id] = clone(v.value);
    for (const key of Object.keys(values)) if (!m.variables.some(v => v.id === key)) delete values[key];
  }
}
function showBankApplication() {
  const m = mod(), bank = ui.bank;
  validateBank(m, m.banks[bank]);
  const differences = bankDiff(m, bank);
  openDialog(`应用库值 ${bank + 1} 到模块当前值`, `${m.name} · ${m.bankNames[bank]}。本次修改测试初值，项目实例单独应用型号。`, diffMarkup(differences.map(v => [v.label, m.values[v.id], m.banks[bank][v.id]])), () => {
    validateBank(m, m.banks[bank]);
    for (const v of m.variables.filter(v => v.writable)) m.values[v.id] = clone(m.banks[bank][v.id]);
    markDirty(m); render(); msg('库值已应用到模块当前值。');
  }, '应用到当前值', true);
}
function createModelDialog(existingId) {
  const existing = existingId && model(existingId), m = existing ? mod(existing.moduleId) : mod();
  if (!existing) validateBank(m, m.banks[ui.bank]);
  const values = existing?.params || Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.banks[ui.bank]['param:' + f[0]]]));
  openDialog(existing ? '保存型号新版本' : '保存为设备型号', `${m.name} · ${existing ? '已插入的项目设备不会自动更新。' : `来源：库值 ${ui.bank + 1} · ${m.bankNames[ui.bank]}`}`, `<div class="fields">${field('name', '型号名称', existing?.name || `${m.name} · ${m.bankNames[ui.bank]}`, 'required maxlength="60"')}${field('description', '说明 / 版本备注', existing?.description || '', 'maxlength="160"')}${paramsFields(m.kind, values)}</div>`, data => {
    const name = data.name.trim(); if (!name) throw Error('型号名称不能为空。');
    if (state.models.some(v => v.id !== existingId && v.moduleId === m.id && v.name === name)) throw Error('此模块已有同名型号。');
    const params = readParams(data, m.kind), note = data.description.trim() || '参数更新';
    if (existing) {
      existing.version++; existing.name = name; existing.description = note; existing.params = params;
      if (existing.values) for (const [key, value] of Object.entries(params)) existing.values['param:' + key] = value;
      existing.versions.push({ version: existing.version, note, params: clone(params) });
      state.selectedModel = existing.id;
    } else {
      const id = uid('model');
      state.models.push({ id, moduleId: m.id, name, description: note, version: 1, moduleVersion: m.version, params, values: clone(m.banks[ui.bank]), bank: ui.bank + 1, archived: false, versions: [{ version: 1, note, params: clone(params) }] });
      for (const [key, value] of Object.entries(params)) state.models.at(-1).values['param:' + key] = value;
      state.selectedModel = id;
    }
    markDirty(); navigate('models'); msg(existing ? '新版本已保存到型号草稿。' : '新型号已加入型号库。');
  }, existing ? '保存新版本' : '保存型号');
}
function stageModel(n, id) {
  const item = model(id);
  if (!item || item.archived || item.moduleId !== n.moduleId) throw Error('请选择同一模块的在用型号。');
  n.draft = clone(item.params); n.draftModelId = id; n.draftModelVersion = item.version;
  const data = ensureInstanceVariables(n);
  for (const v of moduleOf(n).variables.filter(v => v.origin === 'custom' && instanceWritable(v))) data.draft[v.id] = clone(item.values?.[v.id] ?? data.values[v.id]);
  markDirty(project());
}
function applyInstanceDialog(n) {
  const values = instanceEdits(n);
  const rows = moduleOf(n).variables.filter(v => instanceWritable(v) && !sameValue(instanceVariableValue(n, v), values[v.id])).map(v => [`${v.label} · ${v.unit}`, instanceVariableValue(n, v), values[v.id]]);
  if (n.draftModelId) rows.unshift(['来源型号', `${model(n.modelId)?.name || '自定义'} v${n.modelVersion || 1}`, `${model(n.draftModelId)?.name} v${n.draftModelVersion}`]);
  openDialog(`应用到 ${n.id} · ${n.name}`, '保存保留草稿；确认应用后参数生效，并在运行事件中记录时间。', diffMarkup(rows), () => {
    validateInstanceEdits(n, values);
    remember(); commitInstanceEdits(n, values);
    if (n.draftModelId) { n.modelId = n.draftModelId; n.modelVersion = n.draftModelVersion; }
    n.draftModelId = null; n.draftModelVersion = null;
    project().run.events.push({ t: project().run.time, kind: 'parameters', text: `${n.id} 参数已应用：${rows.map(([label, , value]) => `${label}=${value}`).join('，')}` });
    markDirty(project()); render(); msg(`${n.id} 参数已应用 · ${clockLabel(project().run.time)}`);
  }, '确认应用', true);
}
function windowBounds(f) {
  const p = page.getBoundingClientRect(), minW = Math.min(320, p.width - 16);
  f.w = clamp(f.w || 440, minW, p.width - 16);
  f.h = clamp(f.h || 520, Math.min(270, p.height - 16), p.height - 16);
  f.x = clamp(f.x ?? p.right - f.w - 20, p.left + 8, p.right - f.w - 8);
  f.y = clamp(f.y ?? p.top + 28, p.top + 8, p.bottom - (f.minimized ? 46 : f.h) - 8);
  return f;
}
function rememberWindow(f) { state.windowPositions ||= {}; state.windowPositions[windowKey(f.id)] = { x: f.x, y: f.y, w: f.w, h: f.h, pinned: f.pinned, docked: !!f.docked }; }
function openDevice(id) {
  if (!instance(id)) return;
  ui.selectedNode = id;
  let f = ui.floats.find(f => f.id === id);
  if (!f) { f = { id, tab: 'parameters', ...(state.windowPositions?.[windowKey(id)] || {}), order: ++ui.floatSerial }; ui.floats.push(f); }
  if (f.docked) for (const other of ui.floats) if (other !== f && other.docked) { other.docked = false; rememberWindow(other); }
  f.minimized = false; f.order = ++ui.floatSerial; ui.frontId = id;
  renderFloats();
}
function floatBody(f, n) {
  const m = moduleOf(n), run = project().run;
  if (f.tab === 'variables') return instanceVariablesBody(f, n);
  if (f.tab === 'results') return `<div class="notice">${icon('Info')}主系统 · ${statusText(run)} · ${clockLabel(run.time)}</div><div class="metric-row"><div class="metric"><span>质量流量 · kg/s</span><strong>${number(flowFor(n), 3)}</strong></div><div class="metric"><span>温度 · °C</span><strong>${number(run.values.temperature, 1)}</strong></div></div>${btn('device-curve', '将流量加入曲线', 'Activity', `data-id="${n.id}"`)}`;
  if (f.tab === 'connections') return `<div class="stack">${m.ports.map(p => { const pg = project().pages.find(pg => pg.nodes.some(x => x.id === n.id)), edge = pg.edges.find(e => e[1] === n.id && e[2] === p.id || e[3] === n.id && e[4] === p.id); return `<div class="list-row" style="padding:10px 0"><div class="grow"><strong>${esc(p.name)} · ${esc(p.label)}</strong><small>${DOMAINS[p.domain].label} · ${edge ? esc(edge[1] + ' ↔ ' + edge[3]) : '未连接'}</small></div>${edge ? btn('delete-edge', '断开', 'X', `data-id="${edge[0]}"`, 'small') : badge('空闲')}</div>`; }).join('')}</div>`;
  return `<label class="field"><span>设备名称</span><input data-instance-name="${n.id}" value="${esc(n.name)}" aria-label="${n.id} 设备名称" maxlength="50"></label><div class="field" style="margin-top:13px"><span>选择型号 → 进入待应用草稿</span><select data-instance-model="${n.id}" aria-label="${n.id} 设备型号">${option('', '自定义参数', n.draftModelId || n.modelId)}${state.models.filter(v => v.moduleId === m.id && !v.archived).map(v => option(v.id, v.name + ' · v' + v.version, n.draftModelId || n.modelId)).join('')}</select></div><div class="row spread" style="margin-top:12px"><strong>常用参数</strong><span class="badge ${pendingCount(n) ? 'warn' : 'good'}" data-pending-for="${n.id}">${pendingCount(n)} 项待应用</span></div>${paramDefs(n).filter(f => m.variables.find(v => v.param === f[0])?.display !== false).map(f => `<div class="parameter-row${n.draft[f[0]] !== n.params[f[0]] ? ' edited' : ''}"><div class="param-title"><strong>${f[1]}</strong><small>当前 ${number(n.params[f[0]], f[0] === 'opening' ? 0 : 2)} ${f[2]}</small>${quickFieldMarkup(n, m, f)}</div><input type="number" step="any" min="${f[3]}" max="${f[4]}" data-instance-param="${f[0]}" data-id="${n.id}" value="${n.draft[f[0]]}" aria-label="${n.id} ${f[1]}草稿" ${m.quickParam === f[0] && m.quickType === "display" ? "readonly" : ""}><span class="muted">${f[2]}</span></div>`).join('') || '<p class="muted" style="margin:14px 0">此模块没有常用可调参数。</p>'}<div class="row wrap" style="margin-top:16px">${btn('edit-module', '完整模块定义', 'Box', `data-id="${m.id}"`, 'small ghost')}</div>`;
}
function quickCanvasMarkup(n, m) {
  const def = paramDefs(n).find(f => f[0] === m.quickParam);
  if (!def || m.variables.find(v => v.param === def[0])?.display === false) return '';
  return `<g data-quick-node="${n.id}" role="button" tabindex="0" aria-label="修改 ${esc(n.name + ' ' + def[1])}"><rect class="quick-param" x="-35" y="68" width="70" height="20" rx="4"/><text class="quick-param-label" x="0" y="82" text-anchor="middle">${number(n.params[def[0]], def[0] === 'opening' ? 0 : 1)} ${esc(def[2])}${m.quickType === 'display' ? '' : ' ▾'}</text></g>`;
}
function portStubs(n) {
  return `<g transform="rotate(${n.rotation || 0})">${moduleOf(n).ports.map(p => { const d = portOffset(n, p); return `<path d="M ${d.x} ${d.y} H 0 V 0" fill="none" stroke="var(--${DOMAINS[p.domain].color})" stroke-width="1.3"/>`; }).join('')}</g>`;
}
function quickFieldMarkup(n, m, f) {
  if (m.quickParam !== f[0]) return '';
  if (m.quickType === 'slider') return `<input type="range" data-instance-param="${f[0]}" data-id="${n.id}" min="${f[3]}" max="${f[4]}" step="${f[5]}" value="${n.draft[f[0]]}" aria-label="${n.id} ${f[1]}滑块">`;
  if (m.quickType === 'switch') return `<label class="check-label" style="margin-top:6px"><input type="checkbox" data-instance-switch="${f[0]}" data-id="${n.id}" ${n.draft[f[0]] > f[3] ? 'checked' : ''}>切换 ${f[3]} / ${f[4]} ${esc(f[2])}</label>`;
  return '';
}
function renderFloats() {
  const layer = document.getElementById('floating-layer');
  syncDockLayout();
  let html = '';
  if (ui.route === 'workbench') html = ui.floats.filter(f => instance(f.id)).map(f => {
    const bounds = isDocked(f) ? dockWindowBounds(f) : windowBounds(f); const n = instance(f.id);
    const bank = f.tab === 'variables' ? variableWindowState(f).source : -1;
    const apply = bank < 0
      ? btn('apply-instance', '预览并应用', 'Check', `data-id="${n.id}" ${pendingCount(n) ? '' : 'disabled'}`, 'primary small')
      : btn('apply-instance-bank', `应用库值 ${bank + 1}`, 'Check', `data-id="${n.id}" data-bank="${bank}" ${instanceBankDiff(n, bank).length ? '' : 'disabled'}`, 'primary small');
    return `<section class="floater${isDocked(f) ? ' docked' : ''}${ui.frontId === f.id ? ' front' : ''}${f.minimized ? ' minimized' : ''}${f.tab === 'variables' ? ' variables-floater' : ''}" role="region" aria-label="${esc(n.id + ' 设备参数')}" data-float-id="${f.id}" style="left:${bounds.x}px;top:${bounds.y}px;width:${bounds.w}px;height:${f.minimized ? 46 : bounds.h}px;z-index:${50 + (f.pinned ? 50 : 0) + f.order % 40}">
      <header class="float-head" data-float-move="${f.id}">${icon('SlidersHorizontal')}<strong class="float-title">${esc(n.id + ' · ' + n.name)}</strong>${ibtn('float-dock', f.docked ? '取消停靠' : '停靠到右侧', f.docked ? 'ExternalLink' : 'Columns2', `data-id="${f.id}" aria-pressed="${!!f.docked}" ${innerWidth < 1000 && !f.docked ? 'hidden' : ''}`)}${ibtn('float-pin', '置顶窗口', 'Pin', `data-id="${f.id}" aria-pressed="${!!f.pinned}"`)}${ibtn('float-max', '最大化或还原', 'Maximize2', `data-id="${f.id}"`)}${ibtn('float-min', f.minimized ? '还原窗口' : '收起窗口', f.minimized ? 'ChevronDown' : 'Minus', `data-id="${f.id}"`)}${ibtn('float-close', '关闭设备窗口', 'X', `data-id="${f.id}"`)}</header>
      ${f.minimized ? '' : `<nav class="tabs float-tabs" aria-label="设备属性页签">${[['parameters', '参数与型号'], ['variables', '全部变量'], ['results', '运行结果'], ['connections', '连接']].map(([id, label]) => `<button type="button" data-action="float-tab" data-id="${f.id}" data-value="${id}" class="${f.tab === id ? 'active' : ''}" aria-pressed="${f.tab === id}">${label}</button>`).join('')}</nav><div class="float-body">${floatBody(f, n)}</div><footer class="float-footer"><div class="float-save-state grow"><small data-float-save>${state.dirty ? '草稿未保存' : '草稿已保存'}</small><small data-device-apply-status="${n.id}"></small></div>${btn('save', '保存草稿', 'Save', 'title="保存整个原型；待应用参数保持草稿状态"', 'small')}${apply}</footer><button class="float-resize" data-float-resize="${f.id}" aria-label="调整窗口大小">${icon('Grip')}</button>`}
    </section>`;
  }).join('');
  if (contextMenu) html += `<div class="context-menu" style="left:${contextMenu.x}px;top:${contextMenu.y}px">${btn('open-device', '参数与型号', 'SlidersHorizontal', `data-id="${contextMenu.id}"`)}${btn('copy-device', '复制设备', 'Copy', `data-id="${contextMenu.id}"`)}${btn('rotate-device', '旋转 90°', 'RotateCw', `data-id="${contextMenu.id}"`)}${btn('delete-node', '删除设备', 'Trash2', `data-id="${contextMenu.id}"`)}</div>`;
  if (ui.taskDrawer) html += `<section class="task-drawer"><div class="panel-head"><h3>运行任务</h3>${ibtn('tasks', '关闭任务列表', 'X')}</div><div class="panel-body stack">${state.projects.filter(p => ['running', 'paused'].includes(p.run.status)).map(p => `<div class="row"><div class="grow"><strong>${esc(p.name)}</strong><small>${statusText(p.run)} · ${clockLabel(p.run.time)}</small></div>${btn('open-project', '查看', '', `data-id="${p.id}"`, 'small')}${btn('stop-task', '停止', '', `data-id="${p.id}"`, 'small')}</div>`).join('')}<small class="muted">切换页面或关闭查看窗口后，任务继续保留。</small></div></section>`;
  layer.innerHTML = html;
  syncWorkbenchStatus();
  requestAnimationFrame(() => { resizeCharts(); restoreChartCursor(); });
}
function updateFloatBodies() { retainFocus(renderFloats); }
function setBench(id, params) {
  if (['running', 'paused'].includes(state.bench.run.status)) throw Error('先停止当前单机测试，再切换被测设备。');
  const m = mod(id);
  state.bench.moduleId = m.id;
  state.bench.params = params ? clone(params) : Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.values['param:' + f[0]] ?? f[6]]));
  state.bench.run = emptyRun('bench');
  state.bench.run.step = Math.max(.01, (m.values['system:step'] || 100) / 1000);
  markDirty(); navigate('bench');
}
function newInstance(moduleId, point, selectedModel) {
  const m = mod(moduleId), pg = activePage();
  if (pg.nodes.length >= 64) throw Error('当前原型每张画布最多演示 64 台设备。');
  remember();
  const node = makeInstance(uid(m.kind === 'valve' ? 'V' : m.kind === 'pump' ? 'P' : 'D'), m.kind, m.name, point?.x ?? 250 + pg.nodes.length % 5 * 110, point?.y ?? 140 + Math.floor(pg.nodes.length / 5) * 100);
  node.moduleId = m.id;
  if (selectedModel) { node.params = clone(selectedModel.params); node.draft = clone(node.params); node.modelId = selectedModel.id; node.modelVersion = selectedModel.version; }
  else if (m.id !== m.kind) { node.modelId = null; node.params = Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.values['param:' + f[0]] ?? f[6]])); node.draft = clone(node.params); }
  ensureInstanceVariables(node, m);
  if (selectedModel?.values) for (const v of m.variables.filter(v => v.origin === 'custom')) {
    const value = clone(selectedModel.values[v.id] ?? node.variableState.values[v.id]);
    node.variableState.values[v.id] = clone(value); node.variableState.draft[v.id] = clone(value); node.variableState.banks[0][v.id] = clone(value);
  }
  pg.nodes.push(node); ui.selectedNode = node.id; ui.placing = null; if (innerWidth <= 500) ui.showLibrary = false;
  markDirty(project()); render(); return node;
}
function validateNetwork(p = project()) {
  const errors = [];
  if (!p.pages.some(pg => pg.nodes.length)) errors.push({ text: '项目没有设备。' });
  for (const pg of p.pages) {
    const used = new Set();
    for (const [id, na, pa, nb, pb] of pg.edges) {
      const a = endpoint(pg, na, pa), b = endpoint(pg, nb, pb);
      if (!a || !b) { errors.push({ text: `${id}：连接端口不存在。`, page: pg.id, node: na }); continue; }
      if (a.port.domain !== b.port.domain) errors.push({ text: `${id}：两端领域不一致。`, page: pg.id, node: na });
      for (const key of [na + ':' + pa, nb + ':' + pb]) { if (used.has(key)) errors.push({ text: `${key}：端口重复连接。`, page: pg.id, node: na }); used.add(key); }
    }
    for (const n of pg.nodes) {
      const m = moduleOf(n);
      for (const p of m.ports) if (!used.has(n.id + ':' + p.id)) errors.push({ text: `${n.id} · ${p.label} 尚未连接。`, page: pg.id, node: n.id });
      for (const text of checkChannels(m)) errors.push({ text: `${n.id} · ${text}`, page: pg.id, node: n.id });
    }
  }
  return errors;
}
function connectPort(nodeId, portId) {
  const pg = activePage(), next = endpoint(pg, nodeId, portId);
  if (!next) return;
  const used = pg.edges.some(e => e[1] === nodeId && e[2] === portId || e[3] === nodeId && e[4] === portId);
  if (used) throw Error('此端口已经连接。请先断开原连接，或使用连接节点分支。');
  if (!ui.connecting) { ui.connecting = { nodeId, portId }; render(); return; }
  const first = ui.connecting;
  if (first.nodeId === nodeId) { ui.connecting = null; render(); return; }
  const previous = endpoint(pg, first.nodeId, first.portId);
  if (previous.port.domain !== next.port.domain) throw Error('两端的物理类型必须相同。');
  if (next.port.domain !== 'fluid' && previous.port.direction === next.port.direction) throw Error('此类端口需要输入与输出相连。');
  remember(); pg.edges.push([uid('edge'), first.nodeId, first.portId, nodeId, portId]); ui.connecting = null;
  markDirty(project()); render(); msg('连接已建立。');
}
function deleteNode(id) {
  const pg = project().pages.find(pg => pg.nodes.some(n => n.id === id)); if (!pg) return;
  remember(); pg.nodes = pg.nodes.filter(n => n.id !== id); pg.edges = pg.edges.filter(e => e[1] !== id && e[3] !== id);
  ui.floats = ui.floats.filter(f => f.id !== id); ui.selectedNode = ''; markDirty(project()); render(); msg('设备与关联连接已删除，可撤销。');
}
function deleteEdge(id) { remember(); project().pages.forEach(pg => pg.edges = pg.edges.filter(e => e[0] !== id)); ui.selectedEdge = ''; markDirty(project()); render(); }
function copyDevice(id = ui.selectedNode) { const n = instance(id); if (n) { ui.clipboard = clone(n); msg(`${n.id} 已复制；Ctrl+V 粘贴。`); } }
function pasteDevice() {
  if (!ui.clipboard) return;
  remember(); const n = clone(ui.clipboard); n.id = uid('D'); n.name += ' 副本'; n.x += 60; n.y += 60;
  activePage().nodes.push(n); ui.selectedNode = n.id; markDirty(project()); render();
}
function sampleStep(run, owner, scope = 'project') {
  const step = scope === 'bench' ? run.step : owner.solver.dt;
  run.time = Number((run.time + step).toFixed(6));
  const t = run.time;
  let target = 3.55, ratio = .59, pressure = 120, temperature = 20;
  if (scope === 'bench') {
    const p = owner.params;
    target = Math.sqrt(Math.max(0, owner.boundary.inlet - owner.boundary.outlet) / 81.325) * (p.kv || 16) / 16 * ((p.opening ?? 80) / 80) * (p.speed || 1) * 2.1;
    pressure = owner.boundary.outlet; temperature = owner.boundary.temperature;
  } else {
    const nodes = owner.pages.flatMap(pg => pg.nodes), valves = nodes.filter(n => moduleOf(n).kind === 'valve');
    const a = (valves[0]?.params.opening ?? 80) * (valves[0]?.params.kv ?? 16), b = (valves[1]?.params.opening ?? 55) * (valves[1]?.params.kv ?? 16);
    const speed = nodes.find(n => moduleOf(n).kind === 'pump')?.params.speed ?? 1;
    ratio = a + b ? a / (a + b) : .5;
    target *= speed * Math.sqrt((a + b) / (135 * 16));
    pressure = nodes.find(n => n.id === 'B2')?.params.pressure ?? 120;
  }
  const alpha = owner.solver?.mode === 'steady' ? 1 : 1 - Math.exp(-step / 1.8);
  const q = run.values.q + (target - run.values.q) * alpha;
  run.values = { q, a: q * ratio, b: q * (1 - ratio), pressure: scope === 'bench' ? pressure : pressure + q * 12, temperature: temperature + 12 * (1 - Math.exp(-t / 7)) };
  const variables = {};
  if (scope === 'project') for (const n of owner.pages.flatMap(pg => pg.nodes)) {
    for (const [k, v] of Object.entries(n.params)) variables[n.id + '.' + k.toUpperCase()] = v;
    variables[n.id + '.OUT_FLOW'] = /[VL]1$/.test(n.id) ? run.values.a : /[VL]2$/.test(n.id) ? run.values.b : q;
    variables[n.id + '.OUT_PRE'] = run.values.pressure; variables[n.id + '.OUT_TEMP'] = run.values.temperature;
  }
  run.history.push({ t, ...run.values, variables });
  if (scope === 'project') run.parameterKey = projectParameterKey(owner);
  if (run.history.length > 1200) run.history.shift();
  state.dirty = true;
  if (scope === 'project' && (owner.solver.mode === 'steady' || t >= owner.solver.duration)) {
    run.status = 'completed'; run.events.push({ t, text: '示例运行已完成。' });
  }
}
function commandRun(scope, command, projectId) {
  const owner = scope === 'bench' ? state.bench : state.projects.find(p => p.id === (projectId || state.activeProject));
  if (!owner) return;
  let run = owner.run;
  if (command === 'pause' && run.status !== 'running' || command === 'step' && run.status === 'running') return;
  if (['run', 'step'].includes(command)) {
    if (scope === 'project') {
      const issues = validateNetwork(owner);
      if (issues.length) { showDiagnostics(issues); return; }
    } else {
      readParams(owner.params, mod(owner.moduleId).kind);
      numeric(owner.boundary.inlet, .001, 100000); numeric(owner.boundary.outlet, .001, 100000); numeric(owner.boundary.temperature, -273, 2000);
    }
    if (['ready', 'stopped', 'completed', 'failed'].includes(run.status)) {
      const step = run.step; owner.run = emptyRun(scope); run = owner.run; run.step = step;
      run.id = uid(scope === 'bench' ? 'TEST' : 'RUN');
      run.events.push({ t: 0, text: `${scope === 'bench' ? '独立测试' : '主系统'}初始化 · 示例响应` });
      run.history.push({ t: 0, ...run.values, variables: {} });
    }
    if (command === 'step') {
      run.status = 'paused'; sampleStep(run, owner, scope); run.events.push({ t: run.time, text: '单步已完成，数值与曲线同步。' });
    } else { run.status = 'running'; run.events.push({ t: run.time, text: '开始 / 继续示例运行。' }); }
  } else if (command === 'pause') { run.status = 'paused'; run.events.push({ t: run.time, text: '运行已暂停。' }); }
  else if (command === 'stop') { run.status = 'stopped'; run.events.push({ t: run.time, text: '运行已停止，保留本次结果。' }); }
  log(`${scope === 'bench' ? mod(owner.moduleId).name + ' · 单机测试' : owner.name}：${statusText(run)}，${clockLabel(run.time)}`);
  markDirty(scope === 'project' ? owner : null); retainFocus();
}
function refreshLive() {
  if (ui.route === 'curves') {
    const run = currentChartRun();
    const items = [['main-chart', ['q', 'a', 'b'], 'main-flow-chart'], ['pressure-chart', ['pressure'], 'pressure-line'], ['temperature-chart', ['temperature'], 'temperature-line']];
    for (const [id, keys, chartId] of items) { const e = document.getElementById(id); if (e) e.innerHTML = chartSvg(run.history, keys, chartId, id === 'main-chart' && state.charts.compare); }
    updateExtraCharts();
    const readout = document.getElementById('main-flow-chart-readout');
    if (readout && !ui.pinnedChart) readout.textContent = `${clockLabel(run.time)} · 主管 ${number(run.values?.q ?? run.history.at(-1)?.q, 3)} kg/s`;
  }
  if (ui.route === 'workbench') refreshWorkbenchChart();
  restoreChartCursor();
  if (ui.route === 'workbench' && !pointer) {
    const svg = document.getElementById('network'); if (svg) svg.innerHTML = networkMarkup(activePage());
    for (const f of ui.floats.filter(f => f.tab === 'results' && !f.minimized)) {
      const body = root.querySelector(`[data-float-id="${f.id}"] .float-body`); if (body) body.innerHTML = floatBody(f, instance(f.id));
    }
    for (const f of ui.floats.filter(f => f.tab === 'variables' && !f.minimized)) if (instance(f.id)) refreshInstanceVariableReadouts(f, instance(f.id));
  }
  root.querySelectorAll('[data-live-time]').forEach(el => el.textContent = clockLabel(project().run.time));
  syncChrome();
}
function recordRun(scope) {
  const owner = scope === 'bench' ? state.bench : project(), run = owner.run;
  if (run.history.length < 2) throw Error('先运行或单步，生成数据后再保存记录。');
  const name = scope === 'bench' ? mod(owner.moduleId).name + ' · 独立测试' : owner.name + ' · ' + clockLabel(run.time);
  const id = uid('RECORD');
  state.records.unshift({ id, name, projectId: scope === 'bench' ? null : owner.id, projectName: scope === 'bench' ? mod(owner.moduleId).name + ' · 单机测试' : owner.name, moduleId: scope === 'bench' ? owner.moduleId : null, scope, status: run.status, mode: scope === 'bench' ? '单机测试' : owner.solver.mode === 'steady' ? '稳态' : '慢动态', time: run.time, history: clone(run.history), events: clone(run.events), params: clone(scope === 'bench' ? owner.params : Object.fromEntries(owner.pages.flatMap(pg => pg.nodes).map(n => [n.id, n.params]))), boundary: scope === 'bench' ? clone(owner.boundary) : null, sample: true });
  state.records = state.records.slice(0, 30); ui.selectedRecord = id; markDirty(); navigate('runs'); msg('运行快照已记录；保存原型后可重新打开。');
}
function showDiagnostics(issues = validateNetwork()) {
  openDialog('连接与定义检查', issues.length ? `${issues.length} 项需要检查，点击可定位设备。` : '结构检查通过。计算结果仍由示例数据演示。', issues.length ? `<div class="stack">${issues.map(x => btn('locate-issue', esc(x.text), 'Info', `data-id="${x.node || ''}" data-page="${x.page || ''}"`, 'ghost')).join('')}</div>` : `<div class="notice good">${icon('CheckCircle2')}端口存在、类型匹配，且没有重复连接。</div>`, null, '', true);
}
function balancedCode(source) {
  const clean = source.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, '');
  const stack = [], pairs = { ')': '(', ']': '[', '}': '{' };
  for (const c of clean) { if ('([{'.includes(c)) stack.push(c); else if (pairs[c] && stack.pop() !== pairs[c]) return false; }
  return stack.length === 0;
}
function previewCode(kind = 'runtime', build = false) {
  const m = mod(), name = { runtime: '运行代码', header: 'Header', design: `设计函数 ${ui.designIndex + 1}` }[kind];
  const sources = build ? [['运行代码', m.source.runtime], ['Header', m.source.header], ...m.source.design.map((code, i) => [`设计函数 ${i + 1}`, code])] : [[name, kind === 'design' ? m.source.design[ui.designIndex] : m.source[kind]]];
  const checks = sources.map(([label, source]) => `${balancedCode(source) ? '✓ ' + label + '：括号结构检查通过' : '× ' + label + '：括号不配对，请检查代码'}`);
  if (build) {
    const errors = checkChannels(m);
    checks.push(errors.length ? '× ' + errors.join('\n') : '✓ 端口与通路检查通过', '编译流程预览：生成接口 → 编译模块 → 项目运行', '未启动编译器，未生成二进制模块。');
  } else checks.push(`检查对象：${m.code} / ${name}。仅做结构检查，不判断算法正确性。`);
  ui.compileOutput = checks.join('\n');
  const out = document.getElementById('code-output');
  if (out) out.textContent = ui.compileOutput;
  else openDialog('检查与编译流程', m.name, `<pre class="code-preview">${esc(ui.compileOutput)}</pre>`);
}
function previewDesign(i = ui.bank) {
  const m = mod();
  ui.compileOutput = `设计函数 ${i + 1} → 库值 ${i + 1} · ${m.bankNames[i]}\n${balancedCode(m.source.design[i]) ? '括号结构正常。' : '请检查括号结构。'}\n这是调用流程预览；库值未被修改，代码未执行。`;
  const out = document.getElementById('code-output');
  if (out) out.textContent = ui.compileOutput;
  else openDialog('设计函数调用预览', m.name, `<pre class="code-preview">${esc(ui.compileOutput)}</pre>`);
}
function bindingsForProject() {
  if (!project().bindings) {
    const variables = projectVariables(), temperature = variables.find(v => v.id === 'P1.OUT_TEMP') || variables.find(v => v.id.endsWith('.OUT_TEMP')), writable = variables.find(v => v.id === 'V1.OPENING') || variables.find(v => v.writable);
    project().bindings = [];
    if (temperature) project().bindings.push({ external: 'Sensor.Temperature', variable: temperature.id, direction: 'read', unit: temperature.unit });
    if (writable) project().bindings.push({ external: 'Control.Parameter', variable: writable.id, direction: 'write', unit: writable.unit });
  }
  return project().bindings;
}
function apiPreview(kind = ui.apiKind || 'read') {
  const value = projectVariables().find(v => v.id === 'V1.OPENING') || projectVariables()[0];
  const info = { project_id: project().id, variable: value?.id || null };
  const out = kind === 'status' ? { run_id: project().run.id || null, status: project().run.status, simulation_time: project().run.time, source: 'prototype' } : kind === 'set' ? { command_id: 'DEMO-CMD-001', variable: value?.id, stages: ['已接收', value?.writable ? '已应用（演示）' : '已拒绝：目标只读'], applied_at: project().run.time, changed_real_value: false } : { ...info, value: value?.value ?? null, unit: value?.unit || '', source: 'prototype' };
  const path = document.getElementById('api-path'); if (path) path.textContent = kind === 'status' ? '/runs/current/status' : kind === 'set' ? '/commands/parameters' : '/variables/' + (value?.id || '{variable}');
  const request = document.getElementById('api-request'); if (request) request.textContent = JSON.stringify(kind === 'set' ? { ...info, value: 65 } : info, null, 2);
  document.getElementById('api-response').textContent = JSON.stringify(out, null, 2);
  const method = path?.previousElementSibling; if (method) method.textContent = kind === 'set' ? 'POST' : 'GET';
}
function addChartVariable(id, label) {
  const v = projectVariables().find(v => v.id === id); if (!v) throw Error('变量不属于当前项目。');
  if (!state.charts.extra.some(x => x.id === id && x.projectId === project().id)) state.charts.extra.push({ id, label: label || `${v.device} · ${v.name}`, unit: v.unit, projectId: project().id });
  state.charts.source = 'live'; markDirty(); navigate('curves');
}
function extraVariableValue(row, id) {
  if (Number.isFinite(row.variables?.[id])) return row.variables[id];
  if (id.endsWith('.OUT_FLOW')) return /^[VL]1\./.test(id) ? row.a : /^[VL]2\./.test(id) ? row.b : row.q;
  if (id.endsWith('.OUT_PRE')) return row.pressure;
  if (id.endsWith('.OUT_TEMP')) return row.temperature;
  return null;
}
function chartSvg(history, keys = ['q', 'a', 'b'], id = 'flow-chart', compare = false, options = {}) {
  const measured = document.getElementById(id)?.getBoundingClientRect().width;
  const w = Math.max(200, Math.round(measured || (ui.route === 'bench' ? page.clientWidth - 390 : page.clientWidth - 125)));
  const h = options.compact ? 168 : 270, left = w < 360 ? 42 : 58, right = w - 20, top = 23, bottom = h - 48;
  const rows = history.length ? history : [{ t: 0, q: 0, a: 0, b: 0, pressure: 0, temperature: 0 }, { t: 10, q: 0, a: 0, b: 0, pressure: 0, temperature: 0 }];
  const minT = rows[0].t, maxT = Math.max(minT + .1, rows.at(-1).t);
  const baseline = compare ? sampleHistory(80).filter(r => r.t >= minT && r.t <= maxT) : [];
  const values = rows.flatMap(r => keys.map(k => Number(r[k]) || 0)).concat(baseline.map(r => r.q));
  const lo = Math.min(0, ...values), hi = Math.max(1, ...values), padding = (hi - lo) * .12;
  const maxY = hi + padding, minY = lo < 0 ? lo - padding : 0;
  const x = t => left + (t - minT) / (maxT - minT) * (right - left), y = n => bottom - (Number(n) - minY) / (maxY - minY) * (bottom - top);
  const unit = SERIES[keys[0]]?.unit || 'kg/s', visible = keys.filter(k => state.charts.series[k] !== false || id === 'bench-chart');
  const path = (rows, key) => rows.map((r, i) => `${i ? 'L' : 'M'} ${x(r.t).toFixed(2)} ${y(r[key] || 0).toFixed(2)}`).join(' ');
  const ticks = w < 420 ? 3 : 4;
  chartRegistry.set(id, { rows, keys: visible, minT, maxT, left, right, top, bottom, y, options });
  return `<svg class="chart" id="${id}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(keys.map(k => SERIES[k]?.name || k).join('、'))}随时间变化，单位 ${esc(unit)}" data-chart="${id}"><text x="5" y="14" class="chart-text">${esc(unit)}</text>${[0, 1, 2, 3, 4].map(i => { const n = minY + (maxY - minY) * i / 4, yy = y(n); return `<line x1="${left}" y1="${yy}" x2="${right}" y2="${yy}" class="chart-grid"/><text x="${left - 9}" y="${yy + 4}" text-anchor="end" class="chart-text">${number(n, maxY > 10 ? 0 : 1)}</text>`; }).join('')}${Array.from({ length: ticks + 1 }, (_, i) => `<text x="${left + i / ticks * (right - left)}" y="${bottom + 20}" text-anchor="${i === 0 ? 'start' : i === ticks ? 'end' : 'middle'}" class="chart-text">${number(minT + (maxT - minT) * i / ticks, 1)}</text>`).join('')}<text x="${right}" y="${h - 6}" text-anchor="end" class="chart-text">时间 · s</text>${visible.map(k => `<path d="${path(rows, k)}" class="chart-line" stroke="var(--${SERIES[k]?.color || 'blue'})"/>`).join('')}${baseline.length ? `<path d="${path(baseline, 'q')}" class="chart-line" stroke="var(--muted)" stroke-dasharray="5 5"/>` : ''}${(options.events || []).filter(e => e.t >= minT && e.t <= maxT).slice(-12).map(e => `<g class="chart-event"><title>${esc(clockLabel(e.t) + ' · ' + e.text)}</title><line x1="${x(e.t)}" x2="${x(e.t)}" y1="${top}" y2="${bottom}" stroke="var(--accent)" stroke-dasharray="3 4" opacity=".65"/><circle cx="${x(e.t)}" cy="${top}" r="3" fill="var(--accent)"/></g>`).join('')}<line data-chart-guide x1="0" x2="0" y1="${top}" y2="${bottom}" stroke="var(--muted)" opacity="0"/>${visible.map(k => `<circle data-hover-mark="${esc(k)}" r="3" fill="var(--${SERIES[k]?.color || 'blue'})" opacity="0"/>`).join('')}<rect x="${left}" y="${top}" width="${right - left}" height="${bottom - top}" fill="transparent" data-chart-hit="${id}" style="cursor:crosshair"/></svg>`;
}
function resizeCharts() {
  for (const svg of root.querySelectorAll('svg[data-chart]')) {
    const data = chartRegistry.get(svg.id); if (!data) continue;
    const html = chartSvg(data.rows, data.keys, svg.id, svg.id === 'main-flow-chart' && state.charts.compare, data.options);
    svg.outerHTML = html;
  }
}
function extraChartsMarkup() {
  const run = currentChartRun(), projectId = state.charts.source === 'live' ? project().id : run.projectId;
  return state.charts.extra.filter(v => v.projectId === projectId).map((v, i) => {
    const key = 'extra:' + v.id;
    const history = run.history.filter(r => extraVariableValue(r, v.id) !== null).map(r => ({ t: r.t, [key]: extraVariableValue(r, v.id) }));
    SERIES[key] = { name: v.label, unit: v.unit, color: 'blue' };
    return `<section class="panel"><div class="chart-panel"><div class="chart-heading"><div class="grow"><h3>${esc(v.label)}</h3><small class="muted">${esc(v.id)} · ${esc(v.unit)}</small></div>${ibtn('remove-chart-var', '移除观察变量', 'X', `data-id="${v.id}"`)}</div>${history.length ? chartSvg(history, [key], 'extra-chart-' + i) : '<div class="empty"><p>此变量尚未采样，运行或单步后查看。</p></div>'}<div class="chart-readout" id="extra-chart-${i}-readout"></div></div></section>`;
  }).join('');
}
function updateExtraCharts() { const e = document.getElementById('extra-charts'); if (e) e.innerHTML = extraChartsMarkup(); }
function downloadFile(name, text, type = 'application/json') {
  const blob = new Blob([text], { type: type + ';charset=utf-8' }), url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 3000); msg('已生成导出文件。');
}
function exportData(format, id) {
  const csvCell = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  if (format === 'csv') {
    const h = currentChartRun().history; if (!h.length) throw Error('当前数据来源没有曲线可导出。');
    downloadFile('fluidnet-curves.csv', '\uFEFF' + [['time_s', 'flow_kg_s', 'a_kg_s', 'b_kg_s', 'pressure_kPa', 'temperature_C'], ...h.map(r => [r.t, r.q, r.a, r.b, r.pressure, r.temperature])].map(r => r.map(csvCell).join(',')).join('\r\n'), 'text/csv'); return;
  }
  let data, name;
  if (format === 'record' || format === 'report') { data = state.records.find(r => r.id === (id || ui.selectedRecord)) || state.records[0]; if (!data) throw Error('没有可导出的记录。'); name = data.id; }
  else if (format === 'models') { data = { format: 'fluidnet-prototype-models', schema: 1, modules: state.modules, models: state.models }; name = 'fluidnet-models'; }
  else if (format === 'variables') { data = { project: project().id, variables: projectVariables() }; name = 'fluidnet-variables'; }
  else if (format === 'messages') { data = state.messages; name = 'fluidnet-messages'; }
  else { data = clone(state); data.format = 'fluidnet-studio-prototype'; name = 'fluidnet-prototype'; }
  downloadFile(name + '.json', JSON.stringify(data, null, 2));
}
function validateImport(data) {
  const safeId = id => typeof id === 'string' && /^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id);
  if (!data || data.schema !== 1 || !Array.isArray(data.modules) || !data.modules.length || !Array.isArray(data.models)) throw Error('不是本版本的原型交换文件。');
  if (data.modules.length > 64 || data.models.length > 500) throw Error('导入数据超出原型演示容量。');
  const unique = values => new Set(values).size === values.length;
  if (!unique(data.modules.map(m => m.id)) || !unique(data.models.map(m => m.id))) throw Error('模块或型号标识重复。');
  for (const m of data.modules) {
    if (!safeId(m.id) || !PARAM_DEFS[m.kind] || !isIdentifier(m.code) || typeof m.name !== 'string' || !Array.isArray(m.ports) || !Array.isArray(m.variables) || !Array.isArray(m.channels) || !m.values || m.banks?.length !== 3 || m.bankNames?.length !== 3 || !m.source || typeof m.source.runtime !== 'string' || typeof m.source.header !== 'string' || m.source.design?.length !== 3 || !m.drawing) throw Error('模块定义不完整。');
    if (m.ports.length > 24 || m.variables.length > 160 || !unique(m.ports.map(p => p.id)) || !unique(m.variables.map(v => v.id))) throw Error('端口 / 变量标识重复或数量超限。');
    if (m.ports.some(p => !safeId(p.id) || !isIdentifier(p.name) || !DOMAINS[p.domain] || !['in', 'out'].includes(p.direction) || !Number.isFinite(p.x) || !Number.isFinite(p.y))) throw Error('端口定义不合法。');
    if (m.variables.some(v => !isIdentifier(v.name) || !['int', 'double', 'int[8]', 'double[8]'].includes(v.type) || v.port && !m.ports.some(p => p.id === v.port))) throw Error('变量定义不合法。');
    if (!m.variables.some(v => v.id === 'system:form') || !m.variables.some(v => v.id === 'system:mix')) throw Error('模块缺少工质字段。');
    if (!Number.isInteger(m.precision) || m.precision < 0 || m.precision > 8) throw Error('显示精度不合法。');
    numeric(m.drawing.width, 15, 60); numeric(m.drawing.height, 15, 55);
    for (const bank of [m.values, ...m.banks]) validateBank(m, bank);
  }
  for (const item of data.models) {
    const m = data.modules.find(m => m.id === item.moduleId);
    if (!safeId(item.id) || !m || typeof item.name !== 'string' || !Array.isArray(item.versions) || !item.versions.length) throw Error('型号引用或版本数据不完整。');
    readParams(item.params, m.kind);
  }
  if (data.format === 'fluidnet-prototype-models') return;
  if (!Array.isArray(data.projects) || !data.projects.length || data.projects.length > 20 || !unique(data.projects.map(p => p.id)) || !data.bench || !data.charts || !Array.isArray(data.records) || !Array.isArray(data.messages) || !Array.isArray(data.connectors) || !Number.isInteger(data.serial)) throw Error('项目、测试或运行数据不完整。');
  for (const p of data.projects) {
    if (!safeId(p.id) || typeof p.name !== 'string' || !p.solver || !Array.isArray(p.pages) || !p.pages.length || p.pages.length > 8 || !p.run?.values || !Array.isArray(p.run.history) || !Array.isArray(p.run.events) || typeof p.control !== 'string') throw Error('项目结构不合法。');
    const ids = p.pages.flatMap(pg => pg.nodes?.map(n => n.id) || []); if (!unique(ids)) throw Error('项目设备标识重复。');
    for (const pg of p.pages) {
      if (!safeId(pg.id) || !Array.isArray(pg.nodes) || pg.nodes.length > 64 || !Array.isArray(pg.edges)) throw Error('画布结构不合法。');
      for (const n of pg.nodes) { const m = data.modules.find(m => m.id === n.moduleId); if (!safeId(n.id) || !m || !Number.isFinite(n.x) || !Number.isFinite(n.y)) throw Error('设备引用不合法。'); readParams(n.params, m.kind); readParams(n.draft, m.kind); validateInstanceVariableState(n, m); }
      for (const e of pg.edges) if (!Array.isArray(e) || e.length !== 5 || !safeId(e[0]) || !pg.nodes.some(n => n.id === e[1] && data.modules.find(m => m.id === n.moduleId).ports.some(p => p.id === e[2])) || !pg.nodes.some(n => n.id === e[3] && data.modules.find(m => m.id === n.moduleId).ports.some(p => p.id === e[4]))) throw Error('连接引用不存在。');
    }
    numeric(p.solver.dt, .01, 10); numeric(p.solver.duration, 1, 3600);
  }
  if (!data.projects.some(p => p.id === data.activeProject) || !data.modules.some(m => m.id === data.bench.moduleId) || !data.bench.run?.values || !Array.isArray(data.bench.run.history) || !Array.isArray(data.bench.run.events)) throw Error('当前项目或测试引用无效。');
}
function importDialog() {
  openDialog('导入原型或型号库', '读取本设计版本的 JSON，先检查完整性，再显式应用。', '<div class="file-drop"><input type="file" name="file" accept=".json,application/json" aria-label="选择原型 JSON" required></div><div id="import-preview" class="notice" style="margin-top:16px">请选择文件。导入前可以取消。</div>', () => {
    const incoming = modal.importData; if (!incoming) throw Error('请先选择并读取有效文件。');
    validateImport(incoming);
    if (incoming.format === 'fluidnet-prototype-models') {
      const conflicts = incoming.models.filter(m => state.models.some(v => v.id === m.id));
      if (conflicts.length) throw Error(`已有 ${conflicts.length} 个相同标识的型号。为避免覆盖，请使用完整原型恢复或导入不同型号。`);
      state.modules.push(...clone(incoming.modules.filter(m => !state.modules.some(v => v.id === m.id)))); state.models.push(...clone(incoming.models));
    } else {
      try { localStorage.setItem(STORAGE_KEY + '-before-import', JSON.stringify(state)); } catch {}
      state = clone(incoming); state.projects.forEach(p => { if (p.run.status === 'running') p.run.status = 'paused'; }); if (state.bench.run.status === 'running') state.bench.run.status = 'paused';
    }
    ui.floats = []; undoStack = []; redoStack = []; ui.selectedNode = ''; normalizeState(); markDirty(); navigate('home'); msg('导入已应用；点击保存原型以保留。');
  }, '应用导入');
}
function pageMap() {
  openDialog('页面导航', '所有页面使用同一份项目、模块和型号数据。', `<div class="page-map">${Object.entries(PAGE_META).map(([id, [name, glyph, desc]]) => `<button class="map-link" data-action="nav" data-route="${id}" type="button">${icon(glyph)}<span>${name}<small>${desc}</small></span></button>`).join('')}</div>`, null, '', true);
}
function chooseChartVariables(control = false) {
  const variables = projectVariables(); if (!variables.length) throw Error('先在项目中放入设备。');
  if (control) {
    const cfg = project().controlConfig;
    openDialog('控制输入与输出', '配置观察变量与可写目标。', `<div class="stack">${selectField('input', '读取变量', variables.map(v => [v.id, v.id + ' · ' + v.name]), cfg.input)}${selectField('output', '设置目标', variables.filter(v => v.writable).map(v => [v.id, v.id + ' · ' + v.name]), cfg.output)}</div>`, data => {
      cfg.input = data.input; cfg.output = data.output; markDirty(project()); render();
    }, '保存绑定');
  } else openDialog('添加观察变量', '选择设备和物理量；曲线采样与主系统的仿真时间一致。', selectField('variable', '项目变量', variables.map(v => [v.id, `${v.id} · ${v.device} · ${v.name} / ${v.unit}`]), variables[0].id), data => addChartVariable(data.variable), '加入曲线');
}
function handleAction(action, el) {
  const d = el.dataset, id = d.id;
  const changes = { 'editor-tab': 'moduleTab', 'project-filter': 'projectFilter', 'project-view': 'projectView', 'module-category': 'category', 'model-filter': 'modelFilter', 'bench-tab': 'benchTab', 'run-filter': 'runFilter', 'settings-tab': 'settingsTab', 'connection-tab': 'connectionTab', 'node-domain': 'nodeDomain' };
  if (changes[action]) { ui[changes[action]] = d.value; saveUI(); render(); return; }
  switch (action) {
    case 'nav': closeDialog(); navigate(d.route, d.sub ? { connectionTab: d.sub } : {}); break;
    case 'page-map': pageMap(); break;
    case 'project-picker': openDialog('切换项目', '任务在后台保留，设备窗口跟随当前项目。', `<div class="stack">${state.projects.map(p => btn('open-project', esc(p.name), 'FolderOpen', `data-id="${p.id}"`)).join('')}</div>`); break;
    case 'close-dialog': closeDialog(); break;
    case 'save': saveAll(); break;
    case 'theme': ui.theme = ui.theme === 'dark' ? 'light' : 'dark'; saveUI(); render(); break;
    case 'open-project': closeDialog(); if (id) openProject(id); break;
    case 'start-modeling': startModeling(); break;
    case 'toggle-chart': ui.showChart = !ui.showChart; ui.pinnedChart = null; saveUI(); retainFocus(); break;
    case 'full-curves': state.charts.source = 'live'; ui.pinnedChart = null; navigate('curves'); break;
    case 'release-cursor': ui.pinnedChart = null; ui.chartCursor = null; refreshWorkbenchChart(); break;
    case 'float-dock': toggleDeviceDock(id); break;
    case 'guided-demo': state.selectedModule = 'valve'; ui.bank = 1; openEditor('valve', 'channels'); msg('从端口与通路开始，再编辑库值、保存型号并应用到项目。'); break;
    case 'new-project':
      openDialog('新建项目', '选择一份示例作为起点，或创建空白画布。', `<div class="stack">${field('name', '项目名称', '新管网项目', 'required maxlength="50"')}${selectField('template', '起始内容', [['blank', '空白画布'], ['water', '泵阀并联管网'], ['heat', '双侧换热机组'], ['tank', '水箱液位调节']], 'blank')}</div>`, data => {
        if (state.projects.length >= 20) throw Error('当前原型最多保存 20 个项目。');
        const name = data.name.trim(); if (!name) throw Error('请输入项目名称。');
        const pg = data.template === 'water' ? waterPage() : data.template === 'heat' ? heatPage() : data.template === 'tank' ? tankPage() : { id: 'main', name: '主系统', nodes: [], edges: [], zoom: 1, pan: [0, 0] };
        const p = makeProject(uid('project'), name, '', pg); state.projects.push(p); normalizeState(); markDirty(p); openProject(p.id);
      }, '创建项目'); break;
    case 'duplicate-project': { const p = clone(state.projects.find(p => p.id === id)); p.id = uid('project'); p.name += ' 副本'; p.run = emptyRun(); p.modified = '本地草稿'; state.projects.push(p); markDirty(p); render(); break; }
    case 'new-canvas':
    case 'rename-canvas': {
      const pg = action === 'rename-canvas' && project().pages.find(pg => pg.id === id);
      openDialog(pg ? '重命名画布' : '新增画布', project().name, field('name', '画布名称', pg?.name || `画布 ${project().pages.length + 1}`, 'required maxlength="40"'), data => {
        const name = data.name.trim(); if (!name) throw Error('请输入画布名称。'); if (!pg && project().pages.length >= 8) throw Error('当前原型每个项目最多演示 8 张画布。');
        remember(); if (pg) pg.name = name; else { const next = { id: uid('canvas'), name, nodes: [], edges: [], zoom: 1, pan: [0, 0] }; project().pages.push(next); project().activePage = next.id; }
        ui.selectedNode = ''; ui.connecting = null; markDirty(project()); render();
      }, pg ? '保存名称' : '新增画布'); break;
    }
    case 'canvas-tab': project().activePage = id; ui.selectedNode = ''; ui.selectedEdge = ''; ui.connecting = null; render(); break;
    case 'new-module':
      openDialog('新建算法模块', '使用已有设备定义作为编辑起点，端口与变量随后可修改。', `<div class="fields">${field('name', '模块名称', '自定义调节阀', 'required maxlength="40"')}${field('code', '模块标识', 'CUSTOM_VALVE', 'required pattern="[A-Za-z_][A-Za-z0-9_]*" maxlength="48"')}${selectField('base', '起始定义', MODULE_SPECS.map(s => [s[0], s[1]]), 'valve')}</div>`, data => {
        if (!isIdentifier(data.code) || state.modules.some(m => m.code === data.code)) throw Error('模块标识需合法且唯一。');
        if (state.modules.length >= 64) throw Error('已达到原型模块数量上限。');
        const m = makeModule(MODULE_SPECS.find(s => s[0] === data.base)); m.id = uid('module'); m.name = data.name.trim(); m.code = data.code; m.category = '自定义模块'; m.drawing.label = m.name; m.description = '用户编辑的模块定义'; state.modules.push(m); markDirty(m); openEditor(m.id);
      }, '创建模块'); break;
    case 'edit-module': openEditor(id || state.selectedModule, d.tab || 'drawing'); break;
    case 'insert-module': navigate('workbench'); newInstance(id); break;
    case 'place-module': ui.placing = ui.placing === id ? null : id; ui.connecting = null; render(); break;
    case 'insert-defaults': remember(); {
      const w = waterPage(), used = project().pages.filter(pg => pg !== activePage()).flatMap(pg => pg.nodes.map(n => n.id));
      const mapping = Object.fromEntries(w.nodes.map(n => [n.id, used.includes(n.id) ? uid(n.id) : n.id]));
      w.nodes.forEach(n => n.id = mapping[n.id]); w.edges = w.edges.map(e => [uid('edge'), mapping[e[1]], e[2], mapping[e[3]], e[4]]);
      activePage().nodes = w.nodes; activePage().edges = w.edges;
    } markDirty(project()); render(); break;
    case 'open-device': openDevice(id); break;
    case 'apply-instance': applyInstanceDialog(instance(id)); break;
    case 'apply-instance-bank': applyInstanceBank(instance(id), Number(d.bank)); break;
    case 'capture-instance-bank': captureInstanceBank(instance(id), Number(d.bank)); break;
    case 'instance-array': editInstanceArray(instance(id), d.instanceValue, Number(d.instanceSource)); break;
    case 'copy-device': copyDevice(id); break;
    case 'rotate-device': remember(); instance(id).rotation = ((instance(id).rotation || 0) + 90) % 360; markDirty(project()); render(); break;
    case 'delete-node': deleteNode(id || ui.selectedNode); break;
    case 'delete-edge': deleteEdge(id || ui.selectedEdge); break;
    case 'undo': undo(); break;
    case 'redo': undo(true); break;
    case 'select-mode': ui.canvasMode = 'select'; ui.connecting = null; ui.placing = null; render(); break;
    case 'connect-mode': ui.canvasMode = 'connect'; ui.placing = null; msg('点击两个空闲端口建立连接，也可以拖动连线。'); break;
    case 'toggle-library': ui.showLibrary = !ui.showLibrary; saveUI(); retainFocus(); break;
    case 'zoom-in': activePage().zoom = clamp(activePage().zoom * 1.2, .35, 3); render(); break;
    case 'zoom-out': activePage().zoom = clamp(activePage().zoom / 1.2, .35, 3); render(); break;
    case 'fit': fitNetwork(); render(); break;
    case 'grid': ui.pageGrid = !ui.pageGrid; saveUI(); render(); break;
    case 'validate': showDiagnostics(); break;
    case 'locate-issue': closeDialog(); if (d.page) project().activePage = d.page; navigate('workbench'); if (id) openDevice(id); break;
    case 'select-picture': ui.editorPort = 'picture'; render(); break;
    case 'draw-center': for (const p of mod().ports) { p.x = p.direction === 'in' ? 20 : 80; p.y = 30 + mod().ports.filter(x => x.direction === p.direction).indexOf(p) * 25; } markDirty(mod()); render(); break;
    case 'edit-drawing-label': ui.editorPort = 'picture'; render(); root.querySelector('[data-drawing-field="label"]')?.focus(); break;
    case 'add-port': {
      const m = mod(); if (m.ports.length >= 24 || m.variables.length + 7 > 160) throw Error('达到本原型的端口或变量容量。');
      const prefix = { fluid: ['IM', 'EX'], info: ['II', 'IO'], power: ['PI', 'PO'], mech: ['MI', 'MO'] }[d.domain][d.direction === 'in' ? 0 : 1];
      let i = 0; while (m.ports.some(p => p.name === prefix + i)) i++;
      const p = port(uid('port'), prefix + i, DOMAINS[d.domain].label + (d.direction === 'in' ? '输入' : '输出'), d.direction, d.domain, d.direction === 'in' ? 20 : 80, 20 + i % 3 * 25);
      m.ports.push(p); refreshPortVariables(m); ui.editorPort = p.id; markDirty(m); render(); break;
    }
    case 'delete-port': {
      const m = mod();
      if (m.channels.some(c => c.input === id || c.output === id)) throw Error('先解除此端口的内部通路绑定，再删除。');
      if (state.projects.some(p => p.pages.some(pg => pg.edges.some(e => [1, 3].some(i => pg.nodes.find(n => n.id === e[i])?.moduleId === m.id && e[i + 1] === id))))) throw Error('项目中仍有连接使用此端口，请先断开连接。');
      m.ports = m.ports.filter(p => p.id !== id); refreshPortVariables(m); ui.editorPort = ''; markDirty(m); render(); break;
    }
    case 'add-channel': {
      const m = mod(), used = m.channels.filter(c => c.enabled).flatMap(c => [c.input, c.output]);
      m.channels.push({ id: uid('channel'), name: '通路 ' + m.channels.length, input: m.ports.find(p => p.direction === 'in' && !used.includes(p.id))?.id || '', output: m.ports.find(p => p.direction === 'out' && !used.includes(p.id))?.id || '', enabled: true, kind: 'resistance' }); markDirty(m); render(); break;
    }
    case 'delete-channel': mod().channels = mod().channels.filter(c => c.id !== id); markDirty(mod()); render(); break;
    case 'check-channels': {
      const errors = checkChannels(mod()), target = document.getElementById('channel-feedback');
      target.innerHTML = `<div class="notice ${errors.length ? 'error' : 'good'}" role="${errors.length ? 'alert' : 'status'}">${icon(errors.length ? 'Info' : 'CheckCircle2')}<span>${errors.length ? errors.map(esc).join('<br>') : '通路检查通过：端口存在、领域一致，且没有重复绑定。'}</span></div>`; break;
    }
    case 'new-variable':
      openDialog('新增自定义变量', '变量标识用于代码、参数方案与曲线。', `<div class="fields">${field('name', '变量标识', 'CUSTOM_VALUE', 'required maxlength="48"')}${field('label', '中文名称', '自定义参数', 'required maxlength="60"')}${selectField('type', '数据类型', ['double', 'int', 'double[8]', 'int[8]'].map(t => [t, t]), 'double')}${field('unit', '单位', '—', 'maxlength="24"')}</div>`, data => {
        const m = mod(); if (!isIdentifier(data.name) || m.variables.some(v => v.name === data.name)) throw Error('变量标识需合法且唯一。');
        if (m.variables.length >= 160) throw Error('变量数量达到原型上限。');
        const value = data.type.endsWith('[8]') ? Array(8).fill(0) : 0, v = { id: uid('var'), name: data.name, label: data.label, unit: data.unit, type: data.type, origin: 'custom', port: '', note: data.label, display: true, writable: true, value };
        m.variables.push(v); [m.values, ...m.banks].forEach(x => x[v.id] = clone(value)); markDirty(m); render();
      }, '新增变量'); break;
    case 'delete-variable': mod().variables = mod().variables.filter(v => v.id !== id); [mod().values, ...mod().banks].forEach(x => delete x[id]); if (ui.arrayVar === id) ui.arrayVar = 'system:form'; markDirty(mod()); render(); break;
    case 'array-select': ui.arrayVar = id; ui.bank = Number(d.bank); render(); break;
    case 'bank-select': ui.bank = Number(d.value); saveUI(); render(); break;
    case 'apply-bank': showBankApplication(); break;
    case 'capture-bank': confirmChange('将当前值存入此库', `用模块当前值替换库值 ${ui.bank + 1} · ${mod().bankNames[ui.bank]}。`, () => { mod().banks[ui.bank] = clone(mod().values); markDirty(mod()); render(); msg('当前值已存入所选库值。'); }, '存入库值'); break;
    case 'normalize-mixture': {
      const bank = mod().banks[ui.bank], form = bank['system:form'], mix = bank['system:mix'];
      mix.forEach((v, i) => mix[i] = form[i] ? Math.max(0, Number(v) || 0) : 0); const sum = mix.reduce((a, b) => a + b, 0);
      if (!form.some(Boolean)) throw Error('请先选择工质。'); if (!sum) form.forEach((v, i) => mix[i] = v ? 1 / form.filter(Boolean).length : 0); else mix.forEach((v, i) => mix[i] = v / sum);
      markDirty(mod()); render(); break;
    }
    case 'new-model': createModelDialog(); break;
    case 'edit-model': createModelDialog(id); break;
    case 'select-model': state.selectedModel = id; navigate('models'); break;
    case 'focus-model': state.selectedModel = id; render(); break;
    case 'archive-model': model(id).archived = !model(id).archived; markDirty(); render(); break;
    case 'insert-model': { const item = model(id); if (item.archived) throw Error('先恢复已归档型号，再插入。'); navigate('workbench'); const n = newInstance(item.moduleId, null, item); openDevice(n.id); break; }
    case 'apply-model-to-instance': {
      const item = model(id), candidates = project().pages.flatMap(pg => pg.nodes).filter(n => n.moduleId === item.moduleId);
      if (!candidates.length) throw Error('当前项目没有兼容设备，可先插入此型号。');
      openDialog('选择应用设备', `${item.name} · v${item.version}。所选型号先进入设备草稿。`, selectField('node', '目标设备', candidates.map(n => [n.id, `${n.id} · ${n.name}`]), candidates[0].id), data => {
        const n = instance(data.node); stageModel(n, id); project().activePage = project().pages.find(pg => pg.nodes.includes(n)).id; navigate('workbench'); openDevice(n.id); msg('型号已进入草稿，预览并应用后生效。');
      }, '进入设备草稿'); break;
    }
    case 'model-version': { const item = model(id), old = item.versions.find(v => v.version === Number(d.version)); openDialog(`型号版本对照 · v${old.version} → v${item.version}`, item.name, diffMarkup(Object.keys(item.params).map(k => [k, old.params[k], item.params[k]])), null, '', true); break; }
    case 'check-code': previewCode(d.kind); break;
    case 'compile-preview': previewCode('runtime', true); break;
    case 'preview-design': previewDesign(d.index === undefined ? ui.bank : Number(d.index)); break;
    case 'insert-code-variable': {
      const area = root.querySelector(`textarea[data-code-kind="${ui.codeKind}"]`), variable = root.querySelector('[data-code-variable]')?.value;
      if (!area || !mod().variables.some(v => v.name === variable)) break;
      area.setRangeText(variable, area.selectionStart, area.selectionEnd, 'end'); area.dispatchEvent(new Event('input', { bubbles: true })); area.focus(); break;
    }
    case 'run-project': commandRun('project', d.command); break;
    case 'stop-task': commandRun('project', 'stop', id); break;
    case 'record-project': recordRun('project'); break;
    case 'tasks': ui.taskDrawer = !ui.taskDrawer; renderFloats(); break;
    case 'select-record': ui.selectedRecord = id; render(); break;
    case 'record-curves': state.charts.source = id; navigate('curves'); break;
    case 'toggle-series': ui.pinnedChart = null; state.charts.series[d.value] = !state.charts.series[d.value]; markDirty(); render(); break;
    case 'add-chart-variable': chooseChartVariables(); break;
    case 'choose-control-vars': chooseChartVariables(true); break;
    case 'add-specific-curve': addChartVariable(id, d.label); break;
    case 'device-curve': addChartVariable(id + '.OUT_FLOW'); break;
    case 'remove-chart-var': state.charts.extra = state.charts.extra.filter(v => v.id !== id || v.projectId !== project().id); markDirty(); render(); break;
    case 'control-template': confirmChange('载入控制示例', '替换当前脚本文本，保留独立的观察变量配置。', () => { project().control = makeProject('', '', '', waterPage()).control; markDirty(project()); render(); }); break;
    case 'preview-control': {
      const cfg = project().controlConfig, input = projectVariables().find(v => v.id === cfg.input), output = projectVariables().find(v => v.id === cfg.output);
      ui.controlOutput = `周期 ${cfg.period} ms · ${clockLabel(project().run.time)}\n观察 ${cfg.input || '未配置'} = ${input ? number(input.value, 3) + ' ' + input.unit : '目标不存在'}\n输出目标 ${cfg.output || '未配置'} · ${output?.writable ? '可写' : '不可写 / 缺失'}\n已读取配置与脚本文本。当前页预览调用顺序，不执行 Lua，也不写入设备参数。`;
      document.getElementById('control-output').textContent = ui.controlOutput; break;
    }
    case 'api-example': ui.apiKind = d.value; apiPreview(d.value); root.querySelectorAll('[data-action="api-example"]').forEach(e => e.classList.toggle('active', e.dataset.value === d.value)); break;
    case 'api-preview': apiPreview(); break;
    case 'copy-var': if (navigator.clipboard?.writeText) navigator.clipboard.writeText(d.value).then(() => msg('变量标识已复制。')).catch(() => openDialog('变量标识', '可选中复制。', field('identifier', '变量标识', d.value, 'readonly'))); else openDialog('变量标识', '可选中复制。', field('identifier', '变量标识', d.value, 'readonly')); break;
    case 'add-connector': { const c = { id: uid('serial'), name: '串口连接 ' + state.connectors.length, kind: 'serial', port: 'COM3', baud: '115200', connected: false }; state.connectors.push(c); ui.selectedConnector = c.id; markDirty(); render(); break; }
    case 'select-connector': ui.selectedConnector = id; render(); break;
    case 'connect-demo': { const c = state.connectors.find(c => c.id === id); c.connected = !c.connected; log(`${c.name}：${c.connected ? '模拟连接成功' : '已断开演示'}`, 'SERIAL'); markDirty(); render(); break; }
    case 'serial-send': {
      const c = state.connectors.find(c => c.id === id); if (!c?.connected) throw Error('先启动连接演示。');
      const text = document.getElementById('serial-message').value.slice(0, 500); log(`${c.name} TX ${text}`, 'SERIAL');
      document.getElementById('serial-output').textContent = `TX > ${text}\nRX < DEMO_ACK（示例回显）\n未访问串口硬件。`; markDirty(); break;
    }
    case 'add-binding':
      openDialog('添加变量映射', '外部写入只能绑定到可设置的参数。', `<div class="stack">${field('external', '外部字段', 'Device.Value', 'required maxlength="80"')}${selectField('variable', '项目变量', projectVariables().map(v => [v.id, v.id + ' · ' + v.name]), projectVariables()[0]?.id)}${selectField('direction', '数据方向', [['read', '项目 → 外部'], ['write', '外部 → 项目']], 'read')}</div>`, data => {
        const v = projectVariables().find(v => v.id === data.variable); if (!v || data.direction === 'write' && !v.writable) throw Error('目标变量不存在或不可写。');
        const bindings = bindingsForProject(); if (bindings.some(b => b.external === data.external)) throw Error('此外部字段已绑定。'); bindings.push({ ...data, unit: v.unit }); markDirty(project()); render();
      }, '添加映射'); break;
    case 'demo-message': log('演示消息：变量快照已更新，原型接口没有外部连接。', 'DEMO'); markDirty(); render(); break;
    case 'export': exportData(d.format, id); break;
    case 'import': importDialog(); break;
    case 'reset-windows': state.windowPositions = {}; ui.floats.forEach(f => { delete f.x; delete f.y; delete f.restore; f.docked = false; f.minimized = false; f.w = 440; f.h = 520; }); markDirty(); render(); msg('窗口位置已恢复。'); break;
    case 'reset-prototype': confirmChange('恢复内置示例', '替换当前原型草稿。可先取消并导出编辑内容。', () => { try { localStorage.setItem(STORAGE_KEY + '-before-reset', JSON.stringify(state)); } catch {} state = initialState(); normalizeState(); ui.floats = []; ui.selectedNode = ''; undoStack = []; redoStack = []; state.dirty = true; navigate('home'); msg('已恢复示例；保存后更新浏览器记录。'); }, '恢复示例'); break;
    case 'float-close': { const f = ui.floats.find(f => f.id === id); rememberWindow(f); ui.floats = ui.floats.filter(f => f.id !== id); renderFloats(); break; }
    case 'float-tab': {
      const f = ui.floats.find(f => f.id === id); f.tab = d.value;
      if (d.value === 'variables' && !f.variablesOpened) {
        const r = page.getBoundingClientRect(); f.variablesOpened = true;
        f.w = Math.min(780, r.width - 16); f.h = Math.min(650, r.height - 16);
        f.x = r.right - f.w - 12; f.y = r.top + 12;
      }
      renderFloats(); break;
    }
    case 'float-pin': { const f = ui.floats.find(f => f.id === id); f.pinned = !f.pinned; rememberWindow(f); renderFloats(); break; }
    case 'float-min': { const f = ui.floats.find(f => f.id === id); f.minimized = !f.minimized; renderFloats(); break; }
    case 'float-max': { const f = ui.floats.find(f => f.id === id), r = page.getBoundingClientRect(); f.docked = false; rememberWindow(f); if (f.restore) { Object.assign(f, f.restore); delete f.restore; } else { f.restore = { x: f.x, y: f.y, w: f.w, h: f.h }; Object.assign(f, { x: r.left + 8, y: r.top + 8, w: r.width - 16, h: r.height - 16 }); } renderFloats(); break; }
    default: throw Error(`尚未识别此操作：${action}`);
  }
}
function handleInput(el) {
  const d = el.dataset, value = el.value;
  if (d.instanceSearch) {
    const f = ui.floats.find(f => f.id === d.instanceSearch); variableWindowState(f).search = value;
    const table = root.querySelector(`[data-instance-table="${f.id}"]`); table.innerHTML = instanceVariableRows(f, instance(f.id)); return;
  }
  if (d.instanceValue) { updateInstanceVariableInput(el); return; }
  if (d.filter) {
    if (d.filter === 'canvasModuleSearch') document.getElementById('canvas-library-list').innerHTML = libraryMarkup(value);
    else { ui[d.filter] = value; retainFocus(); }
    return;
  }
  if (d.codeKind) {
    if (d.codeKind === 'design') mod().source.design[Number(d.designIndex)] = value; else mod().source[d.codeKind] = value;
    const lines = el.previousElementSibling;
    if (lines) { lines.textContent = value.split('\n').map((_, i) => i + 1).join('\n'); lines.scrollTop = el.scrollTop; }
    markDirty(mod()); return;
  }
  if ('controlCode' in d) { project().control = value; el.previousElementSibling.textContent = value.split('\n').map((_, i) => i + 1).join('\n'); markDirty(project()); return; }
  if ('controlName' in d) { project().controlConfig.name = value; markDirty(project()); return; }
  if (d.varNote) { mod().variables.find(v => v.id === d.varNote).note = value; markDirty(mod()); return; }
  if (d.instanceParam) {
    const n = instance(d.id); n.draft[d.instanceParam] = value === '' ? '' : Number(value);
    const row = el.closest('.parameter-row'); row?.classList.toggle('edited', n.draft[d.instanceParam] !== n.params[d.instanceParam]);
    row?.querySelectorAll('input').forEach(other => { if (other !== el) other.value = value; });
    const float = el.closest('.floater'), pending = float?.querySelector('[data-pending-for]');
    if (pending) { pending.textContent = `${pendingCount(n)} 项待应用`; pending.className = `badge ${pendingCount(n) ? 'warn' : 'good'}`; }
    const apply = float?.querySelector('[data-action="apply-instance"]'); if (apply) apply.disabled = !pendingCount(n);
    markDirty(project()); return;
  }
  if (d.instanceName) { const n = instance(d.instanceName); if (value.trim()) n.name = value; markDirty(project()); return; }
  if (d.valueId) {
    const v = mod().variables.find(v => v.id === d.valueId); if (Number(d.bank) < 0 || !v.writable) return;
    mod().banks[Number(d.bank)][d.valueId] = value === '' ? '' : Number(value); el.closest('td')?.classList.add('edited'); markDirty(mod()); return;
  }
  if ('bankName' in d) { mod().bankNames[Number(d.bankName)] = value; markDirty(mod()); return; }
  if (d.projectField && ['name', 'description'].includes(d.projectField)) { if (d.projectField !== 'name' || value.trim()) project()[d.projectField] = value; markDirty(project()); }
}
function handleChange(el) {
  const d = el.dataset, value = el.value; let redraw = true;
  if ('workbenchChart' in d) { ui.workbenchChart = value; ui.pinnedChart = null; saveUI(); retainFocus(); return; }
  if (el.type === 'file' && modal && el.name === 'file') {
    const file = el.files[0], current = modal; if (!file) return;
    if (file.size > 5_000_000) throw Error('请使用小于 5 MB 的原型 JSON。');
    file.text().then(text => {
      if (modal !== current) return;
      try { const data = JSON.parse(text); validateImport(data); current.importData = data; document.getElementById('import-preview').textContent = `${data.projects?.length || 0} 个项目 · ${data.modules.length} 个模块 · ${data.models.length} 个型号。确认后${data.format === 'fluidnet-prototype-models' ? '合并型号库' : '替换当前原型草稿'}。`; }
      catch (err) { current.importData = null; document.getElementById('import-preview').textContent = '检查失败：' + err.message; document.getElementById('import-preview').className = 'notice error'; }
    }); return;
  }
  if (d.instanceSourceSelect || d.instanceGroup || d.instanceToggle) {
    const f = ui.floats.find(f => f.id === (d.instanceSourceSelect || d.instanceGroup || d.id)), config = variableWindowState(f);
    if (d.instanceSourceSelect) config.source = Number(value);
    else if (d.instanceGroup) config.group = value;
    else config[d.instanceToggle] = el.checked;
    retainFocus(renderFloats); return;
  }
  if (d.uiToggle) { ui[d.uiToggle] = el.checked; saveUI(); }
  else if ('themeSelect' in d) { ui.theme = value; saveUI(); }
  else if (d.moduleField) { mod()[d.moduleField] = d.moduleField === 'precision' ? numeric(value, 0, 8, true) : value; markDirty(mod()); }
  else if (d.drawingField) { mod().drawing[d.drawingField] = ['width', 'height'].includes(d.drawingField) ? numeric(value, 15, d.drawingField === 'width' ? 60 : 55) : value; markDirty(mod()); }
  else if (d.portField) {
    const m = mod(), p = m.ports.find(p => p.id === d.id);
    if (d.portField === 'name' && (!isIdentifier(value) || m.ports.some(x => x.id !== p.id && x.name === value))) throw Error('端口标识需合法且唯一。');
    p[d.portField] = ['x', 'y'].includes(d.portField) ? numeric(value, d.portField === 'x' ? 5 : 10, d.portField === 'x' ? 95 : 85) : value;
    refreshPortVariables(m); markDirty(m);
  }
  else if (d.channelField) { const c = mod().channels.find(c => c.id === d.channelId); c[d.channelField] = el.type === 'checkbox' ? el.checked : value; markDirty(mod()); }
  else if (d.varDisplay) { mod().variables.find(v => v.id === d.varDisplay).display = el.checked; markDirty(mod()); redraw = false; }
  else if ('arrayVar' in d) ui.arrayVar = value;
  else if ('arrayIndex' in d) { const v = mod().variables.find(v => v.id === d.id); mod().banks[ui.bank][d.id][Number(d.arrayIndex)] = numeric(value, -1e12, 1e12, v.type.startsWith('int')); markDirty(mod()); }
  else if ('mixtureIndex' in d) { mod().banks[ui.bank]['system:mix'][Number(d.mixtureIndex)] = numeric(value, 0, 1); markDirty(mod()); }
  else if (d.fluidId) {
    const bank = mod().banks[ui.bank], form = bank['system:form'], mix = bank['system:mix'], fid = Number(d.fluidId), old = form.indexOf(fid);
    if (el.checked && old < 0) { const i = form.indexOf(0); if (i < 0) throw Error('最多选择 8 个工质组分。'); form[i] = fid; mix[i] = form.filter(Boolean).length === 1 ? 1 : 0; }
    else if (!el.checked && old >= 0) { if (form.filter(Boolean).length === 1) { el.checked = true; throw Error('至少保留一种工质。'); } form[old] = 0; mix[old] = 0; }
    markDirty(mod());
  }
  else if ('codeTarget' in d) { selectCodeTarget(value); return; }
  else if ('codeVariable' in d) { ui.codeVariable = value; return; }
  else if ('designSelect' in d) {
    ui.designIndex = Number(value); selectCodeTarget('design');
    root.querySelector('[data-code-pane="design"]').outerHTML = renderCodePane('design');
    root.querySelector('[data-design-select]').focus({ preventScroll: true }); return;
  }
  else if (d.instanceModel) {
    const n = instance(d.instanceModel); if (value) stageModel(n, value); else { n.draftModelId = null; n.draftModelVersion = null; markDirty(project()); }
  }
  else if (d.instanceSwitch) { const n = instance(d.id), f = paramDefs(n).find(f => f[0] === d.instanceSwitch); n.draft[f[0]] = el.checked ? f[4] : f[3]; markDirty(project()); }
  else if ('benchModule' in d) { setBench(value); return; }
  else if (d.benchParam) { if (state.bench.run.status === 'running') throw Error('暂停后编辑测试参数。'); const f = (PARAM_DEFS[mod(state.bench.moduleId).kind] || []).find(f => f[0] === d.benchParam); state.bench.params[d.benchParam] = numeric(value, f[3], f[4]); markDirty(); }
  else if (d.benchBoundary) { if (state.bench.run.status === 'running') throw Error('暂停后编辑测试边界。'); state.bench.boundary[d.benchBoundary] = numeric(value, d.benchBoundary === 'temperature' ? -273 : .001, 100000); markDirty(); }
  else if ('benchStep' in d) { state.bench.run.step = numeric(value, .01, 10); markDirty(); }
  else if ('chartSource' in d) { ui.pinnedChart = null; state.charts.source = value; markDirty(); }
  else if ('chartCompare' in d) { state.charts.compare = el.checked; markDirty(); }
  else if (d.projectField) { project()[d.projectField] = value; markDirty(project()); }
  else if (d.solverField) {
    const bounds = { duration: [1, 3600], dt: [.01, 10], massAtol: [1e-12, 1], pressureAtol: [1e-12, 100000], maxIter: [5, 500] };
    project().solver[d.solverField] = d.solverField === 'mode' ? value : numeric(value, ...bounds[d.solverField], d.solverField === 'maxIter'); markDirty(project());
  }
  else if (d.controlSetting) { project().controlConfig[d.controlSetting] = d.controlSetting === 'period' ? numeric(value, 10, 60000, true) : value; markDirty(project()); redraw = false; }
  else if (d.connectorField) { state.connectors.find(c => c.id === d.connectorId)[d.connectorField] = value; markDirty(); }
  else if ('bindingIndex' in d) { const b = bindingsForProject()[Number(d.bindingIndex)], v = projectVariables().find(v => v.id === value); if (b.direction === 'write' && !v.writable) throw Error('外部写入只能绑定可设置参数。'); b.variable = v.id; b.unit = v.unit; markDirty(project()); }
  else redraw = false;
  if (redraw) retainFocus();
}
function svgPoint(svg, e) { return new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse()); }
function setPointer(e, data) { pointer = { ...data, startX: e.clientX, startY: e.clientY, pointerId: e.pointerId, moved: false }; }
root.addEventListener('pointerdown', e => {
  if (e.button !== 0 || modal) return;
  const target = e.target, resize = target.closest('[data-float-resize]'), move = target.closest('[data-float-move]'), draw = target.closest('[data-draw-id]'), portEl = target.closest('[data-port-node]'), node = target.closest('[data-node]');
  if (resize || move && !target.closest('button,input,select')) {
    const f = ui.floats.find(f => f.id === (resize ? resize.dataset.floatResize : move.dataset.floatMove)); if (isDocked(f)) return; ui.frontId = f.id; f.order = ++ui.floatSerial;
    setPointer(e, { kind: resize ? 'resize' : 'window', id: f.id, original: { x: f.x, y: f.y, w: f.w, h: f.h } }); e.preventDefault(); return;
  }
  if (draw && draw.dataset.drawId !== 'picture') {
    const p = mod().ports.find(p => p.id === draw.dataset.drawId); ui.editorPort = p.id;
    setPointer(e, { kind: 'draw-port', id: p.id, original: { x: p.x, y: p.y }, origin: svgPoint(document.getElementById('module-drawing'), e) }); e.preventDefault(); return;
  }
  if (portEl) { setPointer(e, { kind: 'port', nodeId: portEl.dataset.portNode, portId: portEl.dataset.portId }); e.preventDefault(); return; }
  if (node && !target.closest('[data-quick-node]')) { const n = instance(node.dataset.node); ui.selectedNode = n.id; setPointer(e, { kind: 'node', id: n.id, original: { x: n.x, y: n.y }, origin: svgPoint(document.getElementById('network'), e) }); e.preventDefault(); return; }
  if (target.closest('#network') && !target.closest('[data-edge]') && !ui.placing) setPointer(e, { kind: 'pan', original: [...activePage().pan], origin: svgPoint(document.getElementById('network'), e), matrix: document.getElementById('network').getScreenCTM().inverse() });
});
root.addEventListener('pointermove', e => {
  if (!pointer || pointer.pointerId !== e.pointerId) { chartHover(e); return; }
  const dx = e.clientX - pointer.startX, dy = e.clientY - pointer.startY;
  if (!pointer.moved && Math.hypot(dx, dy) > 4) { pointer.moved = true; root.setPointerCapture(e.pointerId); if (pointer.kind === 'node') remember(); }
  if (!pointer.moved) return;
  if (pointer.kind === 'window' || pointer.kind === 'resize') {
    const f = ui.floats.find(f => f.id === pointer.id);
    if (pointer.kind === 'window') { f.x = pointer.original.x + dx; f.y = pointer.original.y + dy; } else { f.w = pointer.original.w + dx; f.h = pointer.original.h + dy; }
    windowBounds(f); const el = root.querySelector(`[data-float-id="${f.id}"]`); Object.assign(el.style, { left: f.x + 'px', top: f.y + 'px', width: f.w + 'px', height: (f.minimized ? 46 : f.h) + 'px' });
  } else if (pointer.kind === 'node') {
    const svg = document.getElementById('network'), p = svgPoint(svg, e), n = instance(pointer.id);
    n.x = Math.round(pointer.original.x + p.x - pointer.origin.x); n.y = Math.round(pointer.original.y + p.y - pointer.origin.y); svg.innerHTML = networkMarkup(activePage());
  } else if (pointer.kind === 'pan') {
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(pointer.matrix); activePage().pan = [pointer.original[0] + p.x - pointer.origin.x, pointer.original[1] + p.y - pointer.origin.y];
    const pg = activePage(); document.getElementById('network').setAttribute('viewBox', networkViewBox(pg));
  } else if (pointer.kind === 'draw-port') {
    const svg = document.getElementById('module-drawing'), p = svgPoint(svg, e), port = mod().ports.find(p => p.id === pointer.id);
    port.x = Math.round(clamp(pointer.original.x + (p.x - pointer.origin.x) / 7.2, 5, 95)); port.y = Math.round(clamp(pointer.original.y + (p.y - pointer.origin.y) / 4.3, 10, 85)); svg.innerHTML = drawingSVG(mod());
  }
});
root.addEventListener('pointerup', e => {
  if (!pointer) return; const completed = pointer; pointer = null;
  try { root.releasePointerCapture(e.pointerId); } catch {}
  if (!completed.moved) return;
  ui.ignoreClickUntil = Date.now() + 100;
  if (completed.kind === 'port') {
    const hit = document.elementFromPoint(e.clientX, e.clientY)?.closest('[data-port-node]');
    if (hit) try { ui.connecting = null; connectPort(completed.nodeId, completed.portId); connectPort(hit.dataset.portNode, hit.dataset.portId); } catch (err) { msg(err.message, true); }
  } else if (['window', 'resize'].includes(completed.kind)) { rememberWindow(ui.floats.find(f => f.id === completed.id)); markDirty(); renderFloats(); }
  else { markDirty(completed.kind === 'draw-port' ? mod() : project()); render(); }
});
root.addEventListener('pointercancel', () => { pointer = null; render(); });
root.addEventListener('click', e => {
  const target = e.target, action = target.closest('[data-action]');
  if (Date.now() < (ui.ignoreClickUntil || 0) && !action) return;
  try {
    if (action && !action.disabled) { contextMenu = null; handleAction(action.dataset.action, action); return; }
    if (modal) return;
    const port = target.closest('[data-port-node]'), quick = target.closest('[data-quick-node]'), node = target.closest('[data-node]'), edge = target.closest('[data-edge]'), draw = target.closest('[data-draw-id]');
    if (port) connectPort(port.dataset.portNode, port.dataset.portId);
    else if (quick) openDevice(quick.dataset.quickNode);
    else if (node) { ui.selectedNode = node.dataset.node; ui.selectedEdge = ''; document.getElementById('selected-properties').innerHTML = propertiesMarkup(instance(ui.selectedNode)); root.querySelectorAll('#network [data-node]').forEach(el => el.classList.toggle('selected', el.dataset.node === ui.selectedNode)); }
    else if (edge) { ui.selectedEdge = edge.dataset.edge; ui.selectedNode = ''; render(); }
    else if (draw) { ui.editorPort = draw.dataset.drawId; render(); }
    else if (target.closest('#network') && ui.placing) newInstance(ui.placing, svgPoint(document.getElementById('network'), e));
    else if (target.closest('[data-chart-hit]')) { ui.pinnedChart = ui.pinnedChart ? null : target.closest('svg').id; chartHover(e, true); }
    else if (contextMenu) { contextMenu = null; renderFloats(); }
  } catch (err) { msg(err.message, true); }
});
root.addEventListener('dblclick', e => { const n = e.target.closest('[data-node]'); if (n && !e.target.closest('[data-port-node]')) openDevice(n.dataset.node); });
root.addEventListener('contextmenu', e => {
  const n = e.target.closest('[data-node]'); if (!n) return; e.preventDefault(); ui.selectedNode = n.dataset.node;
  contextMenu = { id: n.dataset.node, x: clamp(e.clientX, 70, innerWidth - 202), y: clamp(e.clientY, 60, innerHeight - 210) }; renderFloats();
});
function selectCodeTarget(kind) {
  if (!['runtime', 'header', 'design'].includes(kind)) return;
  ui.codeKind = kind;
  const picker = root.querySelector('[data-code-target]'); if (picker) picker.value = kind;
  saveUI();
}
root.addEventListener('focusin', e => { if (e.target.matches('textarea[data-code-kind]')) selectCodeTarget(e.target.dataset.codeKind); });
root.addEventListener('scroll', e => { if (e.target.matches?.('textarea[data-code-kind]')) e.target.previousElementSibling.scrollTop = e.target.scrollTop; }, true);
root.addEventListener('input', e => { try { handleInput(e.target); } catch (err) { msg(err.message, true); } });
root.addEventListener('change', e => { try { handleChange(e.target); } catch (err) { e.target.setAttribute('aria-invalid', 'true'); msg(err.message, true); } });
root.addEventListener('submit', e => {
  if (e.target.id !== 'dialog-form') return; e.preventDefault();
  const current = modal; if (!current?.onSubmit) return;
  try { current.onSubmit(Object.fromEntries(new FormData(e.target))); if (modal === current) closeDialog(); }
  catch (err) { const target = document.getElementById('dialog-error'); if (target) { target.hidden = false; target.textContent = err.message; } }
});
root.addEventListener('dragstart', e => { const el = e.target.closest('[data-drag-module]'); if (el) { e.dataTransfer.setData('text/plain', el.dataset.dragModule); e.dataTransfer.effectAllowed = 'copy'; } });
root.addEventListener('dragover', e => { if (e.target.closest('#network-area')) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; } });
root.addEventListener('drop', e => {
  if (!e.target.closest('#network-area')) return; e.preventDefault();
  const id = e.dataTransfer.getData('text/plain'); if (state.modules.some(m => m.id === id)) try { newInstance(id, svgPoint(document.getElementById('network'), e)); } catch (err) { msg(err.message, true); }
});
function chartHover(e, force = false) {
  const svg = e.target.closest?.('svg[data-chart]'); if (!svg || ui.pinnedChart && !force) return;
  const data = chartRegistry.get(svg.id); if (!data?.rows.length) return;
  const p = svgPoint(svg, e), x = clamp(p.x, data.left, data.right), t = data.minT + (x - data.left) / (data.right - data.left) * (data.maxT - data.minT);
  ui.chartCursor = { id: svg.id, time: t };
  paintChartCursor(svg.id, t, ui.pinnedChart === svg.id);
  restoreChartCursor();
}
document.addEventListener('keydown', e => {
  const edit = e.target.matches('input,textarea,select,[contenteditable=true]');
  if (modal && e.key === 'Tab') {
    const items = [...document.getElementById('dialog-form').querySelectorAll('button:not(:disabled),input:not(:disabled),textarea,select')].filter(e => e.getClientRects().length);
    if (!e.shiftKey && e.target === items.at(-1)) { e.preventDefault(); items[0].focus(); } else if (e.shiftKey && e.target === items[0]) { e.preventDefault(); items.at(-1).focus(); } return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveAll(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); pageMap(); return; }
  if (e.key === 'Escape') { closeDialog(); contextMenu = null; ui.connecting = null; ui.placing = null; ui.pinnedChart = null; render(); return; }
  if (edit) {
    if (e.key === 'Tab' && e.target.tagName === 'TEXTAREA' && (e.target.dataset.codeKind || 'controlCode' in e.target.dataset)) { e.preventDefault(); const el = e.target; el.setRangeText('  ', el.selectionStart, el.selectionEnd, 'end'); el.dispatchEvent(new Event('input', { bubbles: true })); }
    return;
  }
  if (modal) return;
  if (e.key === 'Enter' || e.key === ' ') {
    const p = e.target.closest('[data-port-node]'), n = e.target.closest('[data-node]'), draw = e.target.closest('[data-draw-id]');
    if (p || n || draw) { e.preventDefault(); if (p) { try { connectPort(p.dataset.portNode, p.dataset.portId); } catch (err) { msg(err.message, true); } } else if (n) openDevice(n.dataset.node); else { ui.editorPort = draw.dataset.drawId; render(); } return; }
  }
  if (ui.route === 'workbench') {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(e.shiftKey); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); undo(true); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') copyDevice();
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') { e.preventDefault(); pasteDevice(); }
    else if (e.key === 'Delete') { if (ui.selectedNode) deleteNode(ui.selectedNode); else if (ui.selectedEdge) deleteEdge(ui.selectedEdge); }
  }
  if (ui.route === 'editor' && ui.moduleTab === 'drawing' && e.key.startsWith('Arrow')) {
    const p = mod().ports.find(p => p.id === ui.editorPort); if (!p) return;
    e.preventDefault(); p.x = clamp(p.x + (e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0), 5, 95); p.y = clamp(p.y + (e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0), 10, 85); markDirty(mod()); render();
  }
});
function normalizeState() {
  state.windowPositions ||= {}; state.charts.extra ||= []; state.serial ||= 30;
  for (const p of state.projects) {
    p.controlConfig ||= { name: '供水温度调节', when: 'accepted', period: 100, input: p.pages.flatMap(pg => pg.nodes).some(n => n.id === 'P1') ? 'P1.OUT_TEMP' : '', output: p.pages.flatMap(pg => pg.nodes).some(n => n.id === 'V1') ? 'V1.OPENING' : '' };
    p.run.events ||= []; p.run.history ||= [];
    for (const pg of p.pages) { pg.zoom ||= 1; pg.pan ||= [0, 0]; for (const n of pg.nodes) { n.draft ||= clone(n.params); validateInstanceVariableState(n, moduleOf(n)); ensureInstanceVariables(n, moduleOf(n), p); } }
  }
  state.bench.run.events ||= []; state.bench.run.history ||= [];
}
const chartRegistry = new Map();
try { normalizeState(); } catch { state = initialState(); normalizeState(); recovery = '原型记录不完整，已恢复内置示例。'; }
function routeFromLocation() {
  const route = location.hash.slice(1);
  if (PAGE_META[route]) return route;
  if (route) history.replaceState(null, '', '#home');
  return 'home';
}
ui.route = routeFromLocation();
render();
window.addEventListener('hashchange', () => { ui.route = routeFromLocation(); render(); });
let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { renderFloats(); if (['curves', 'workbench'].includes(ui.route)) refreshLive(); }, 120); });
runInterval = setInterval(() => {
  let active = false, finished = false;
  for (const p of state.projects) if (p.run.status === 'running') { sampleStep(p.run, p); active = true; if (p.run.status === 'completed') finished = true; }
  if (finished && !modal) retainFocus(); else if (active) refreshLive();
}, 200);
