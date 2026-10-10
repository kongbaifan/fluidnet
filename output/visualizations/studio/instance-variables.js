// Device data is independent of the module's test values and other instances.
const sameValue = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const instanceWritable = v => v.writable && ['parameter', 'custom'].includes(v.origin);
const ownerOfInstance = n => state.projects.find(p => p.pages.some(pg => pg.nodes.includes(n))) || project();
function ensureInstanceVariables(n, m = moduleOf(n), owner = ownerOfInstance(n)) {
  n.variableState ||= { schema: 1, values: {}, draft: {}, banks: [{}, {}, {}], bankNames: clone(m.bankNames) };
  const data = n.variableState;
  for (const v of m.variables) {
    if (v.origin === 'custom') {
      if (!(v.id in data.values)) data.values[v.id] = clone(m.values[v.id] ?? v.value);
      if (!(v.id in data.draft)) data.draft[v.id] = clone(data.values[v.id]);
    }
    data.banks.forEach((bank, i) => {
      if (!(v.id in bank)) bank[v.id] = v.origin === 'port' ? null
        : v.origin === 'parameter' ? (i === 0 ? n.params[v.param] : m.banks[i][v.id] ?? n.params[v.param])
        : v.id === 'system:step' ? owner.solver.dt * 1000
        : v.id === 'system:run' ? 0
        : v.id === 'system:form' ? [125, 0, 0, 0, 0, 0, 0, 0]
        : v.id === 'system:mix' ? [1, 0, 0, 0, 0, 0, 0, 0] : clone(m.banks[i][v.id] ?? v.value);
    });
  }
  return data;
}
function instanceVariableValue(n, v, owner = ownerOfInstance(n)) {
  if (v.origin === 'parameter') return n.params[v.param];
  if (v.origin === 'custom') return ensureInstanceVariables(n).values[v.id];
  if (v.id === 'system:step') return owner.solver.dt * 1000;
  if (v.id === 'system:run') return owner.run.status === 'running' ? 1 : 0;
  if (v.id === 'system:form') return [125, 0, 0, 0, 0, 0, 0, 0];
  if (v.id === 'system:mix') return [1, 0, 0, 0, 0, 0, 0, 0];
  // The existing demo samples one outlet per device. Do not fabricate inlet,
  // thermodynamic or dual-circuit results from module initial values.
  const m = moduleOf(n), fluidOutlets = m.ports.filter(p => p.domain === 'fluid' && p.direction === 'out');
  if (v.origin === 'port' && fluidOutlets.length === 1 && v.port === fluidOutlets[0].id) {
    const key = { FLOW: 'OUT_FLOW', PRE: 'OUT_PRE', TEMP: 'OUT_TEMP' }[v.id.split(':').at(-1)];
    const value = key && owner.run.history.at(-1)?.variables?.[n.id + '.' + key];
    if (Number.isFinite(value)) return key === 'OUT_PRE' ? value / 1000 : value;
  }
  return null;
}
function instanceDraftValue(n, v) {
  return v.origin === 'parameter' ? n.draft[v.param] : ensureInstanceVariables(n).draft[v.id];
}
function instanceCustomPending(n) {
  const data = ensureInstanceVariables(n);
  return moduleOf(n).variables.filter(v => v.origin === 'custom' && instanceWritable(v) && !sameValue(data.values[v.id], data.draft[v.id])).length;
}
function instanceEdits(n, bank = -1) {
  const data = ensureInstanceVariables(n);
  return Object.fromEntries(moduleOf(n).variables.filter(instanceWritable).map(v => [v.id, clone(bank < 0 ? instanceDraftValue(n, v) : data.banks[bank][v.id])]));
}
function validateInstanceEdits(n, values, m = moduleOf(n)) {
  for (const v of m.variables.filter(instanceWritable)) {
    const value = values[v.id], array = v.type.endsWith('[8]');
    if (array && (!Array.isArray(value) || value.length !== 8)) throw Error(`${v.label}必须包含 8 项。`);
    try {
      for (const item of array ? value : [value]) numeric(item, -1e12, 1e12, v.type.startsWith('int'));
      const def = (PARAM_DEFS[m.kind] || []).find(f => f[0] === v.param);
      if (def) numeric(value, def[3], def[4]);
    } catch (error) { throw Error(`${v.label}：${error.message}`); }
  }
}
function commitInstanceEdits(n, values) {
  const data = ensureInstanceVariables(n);
  for (const v of moduleOf(n).variables.filter(instanceWritable)) {
    if (v.origin === 'parameter') n.params[v.param] = n.draft[v.param] = values[v.id];
    else { data.values[v.id] = clone(values[v.id]); data.draft[v.id] = clone(values[v.id]); }
  }
}
function instanceBankDiff(n, bank) {
  const data = ensureInstanceVariables(n);
  return moduleOf(n).variables.filter(v => instanceWritable(v) && !sameValue(instanceVariableValue(n, v), data.banks[bank][v.id]));
}
function applyInstanceBank(n, bank) {
  const values = instanceEdits(n, bank), differences = instanceBankDiff(n, bank);
  validateInstanceEdits(n, values);
  const owner = ownerOfInstance(n);
  openDialog(`库值 ${bank + 1} → ${n.id} · ${n.name}`, `仅应用可编辑参数与自定义变量，端口结果和项目系统设置保持只读。${pendingCount(n) ? '确认后会替换这台设备已有的待应用草稿。' : ''}`,
    diffMarkup(differences.map(v => [`${v.label} · ${v.unit}`, instanceVariableValue(n, v), values[v.id]])), () => {
      validateInstanceEdits(n, values); remember(); commitInstanceEdits(n, values);
      n.draftModelId = null; n.draftModelVersion = null;
      owner.run.events.push({ t: owner.run.time, kind: 'parameters', text: `${n.id} 应用库值 ${bank + 1}：${differences.map(v => `${v.name}=${values[v.id]}`).join('，')}` });
      markDirty(owner); render(); msg(`${n.id} 的库值 ${bank + 1} 已应用`);
    }, '确认应用', true);
}
function captureInstanceBank(n, bank) {
  const data = ensureInstanceVariables(n);
  confirmChange(`当前值 → ${n.id} 库值 ${bank + 1}`, '保存这台设备已生效的参数和当前结果。未应用草稿不会被存入；未采样的端口值保留为空。', () => {
    data.banks[bank] = Object.fromEntries(moduleOf(n).variables.map(v => [v.id, clone(instanceVariableValue(n, v))]));
    markDirty(ownerOfInstance(n)); renderFloats(); msg(`${n.id} 当前值已存入库值 ${bank + 1}`);
  }, '存入此库');
}
function variableWindowState(f) {
  return f.variables ||= { source: -1, search: '', group: 'all', onlyDiff: false, allBanks: false };
}
function variableDisplay(value, v, precision) {
  if (value === null || value === undefined) return '—';
  if (value === '') return '未填写';
  return Array.isArray(value) ? value.map(n => number(n, v.type.startsWith('int') ? 0 : 3)).join(', ') : number(value, v.type === 'int' ? 0 : precision);
}
function instanceValueCell(n, v, source, editable, value) {
  const m = moduleOf(n), text = variableDisplay(value, v, m.precision);
  const label = `${n.id} ${v.name} ${source < 0 ? '待应用' : '库值' + (source + 1)}`;
  const attrs = `data-id="${n.id}" data-instance-value="${esc(v.id)}" data-instance-source="${source}" aria-label="${esc(label)}"`;
  if (editable && v.type.endsWith('[8]')) return `<button type="button" class="instance-array" data-action="instance-array" ${attrs} title="${esc(text)}">${esc(text)} ${icon('Pencil')}</button>`;
  if (editable) {
    const def = paramDefs(n).find(f => f[0] === v.param);
    return `<input type="number" step="${v.type === 'int' ? '1' : 'any'}" ${def ? `min="${def[3]}" max="${def[4]}"` : ''} ${attrs} value="${esc(value)}">`;
  }
  return `<span class="instance-readonly" title="${esc(Array.isArray(value) ? value.join(', ') : value ?? '未采样')}">${esc(text)}</span>`;
}
function instanceVariableRows(f, n) {
  const m = moduleOf(n), data = ensureInstanceVariables(n), config = variableWindowState(f);
  const columns = config.allBanks ? [-1, 0, 1, 2] : [config.source];
  const groups = [
    ['parameter', '设备参数', m.variables.filter(v => v.origin === 'parameter')],
    ...m.ports.map(p => [p.id, `${p.label} · ${p.name} / ${DOMAINS[p.domain].label}`, m.variables.filter(v => v.port === p.id)]),
    ['custom', '自定义变量', m.variables.filter(v => v.origin === 'custom')],
    ['system', '系统变量 · 项目设置', m.variables.filter(v => v.origin === 'system')]
  ];
  let count = 0;
  const rows = groups.map(([group, title, variables]) => {
    const shown = variables.filter(v => {
      if (config.group !== 'all' && config.group !== v.origin) return false;
      if (!(n.id + ' ' + v.name + ' ' + v.label + ' ' + v.note).toLowerCase().includes(config.search.toLowerCase())) return false;
      if (!config.onlyDiff) return true;
      return instanceWritable(v) && columns.some(c => !sameValue(instanceVariableValue(n, v), c < 0 ? instanceDraftValue(n, v) : data.banks[c][v.id]));
    });
    if (!shown.length) return '';
    count += shown.length;
    return `<tr class="instance-group"><th colspan="${5 + columns.length}" scope="rowgroup">${esc(title)}<span>${shown.length}</span></th></tr>` + shown.map(v => {
      const current = instanceVariableValue(n, v);
      return `<tr data-instance-row="${esc(v.id)}"><th scope="row" title="${esc(n.id + '.' + v.name)}${instanceWritable(v) ? '' : ' · 只读'}"><span class="mono">${esc(n.id + '.' + v.name)}</span><small class="docked-variable-label" title="${esc(v.label + ' · ' + v.unit)}">${esc(v.label)} · ${esc(v.unit)}</small></th><td class="instance-variable-name" title="${esc(v.label)}">${esc(v.label)}</td><td class="instance-unit">${esc(v.unit)}</td><td class="num" data-instance-live="${esc(v.id)}">${instanceValueCell(n, v, -1, false, current)}</td>${columns.map(c => {
        const value = c < 0 ? (instanceWritable(v) ? instanceDraftValue(n, v) : null) : data.banks[c][v.id];
        const changed = instanceWritable(v) && !sameValue(current, value);
        return `<td class="num${changed ? ' edited' : ''}" data-instance-cell="${c}">${c < 0 && !instanceWritable(v) ? '<span class="muted">只读</span>' : instanceValueCell(n, v, c, c === config.source && instanceWritable(v), value)}</td>`;
      }).join('')}<td class="variable-actions">${variableObservationButton(n, v)}${ibtn('device-definition', `查看 ${v.name} 的变量定义`, 'ArrowUpRight', `data-id="${n.id}" data-variable="${esc(v.id)}"`)}</td></tr>`;
    }).join('');
  }).join('');
  return `<table class="instance-value-table"><thead><tr><th>变量标识</th><th>中文名称</th><th>单位</th><th class="num">当前值</th>${columns.map(c => `<th class="num${c === config.source ? ' editing-column' : ''}">${c < 0 ? '待应用草稿' : '库值 ' + (c + 1)}${c === config.source ? '<small>编辑此列</small>' : ''}</th>`).join('')}<th class="variable-actions">观察 / 定义</th></tr></thead><tbody>${rows || `<tr><td colspan="${5 + columns.length}" class="instance-empty">没有符合条件的变量</td></tr>`}</tbody></table><span class="instance-row-count">显示 ${count} / ${m.variables.length} 个变量</span>`;
}
function instanceVariablesBody(f, n) {
  const config = variableWindowState(f), data = ensureInstanceVariables(n), owner = ownerOfInstance(n);
  return `<div class="instance-variables">
    <div class="instance-source"><strong>${esc(n.id)} · ${esc(owner.name)}</strong><span data-instance-run>${statusText(owner.run)} · ${clockLabel(owner.run.time)}</span></div>
    <div class="instance-filters"><label class="search">${icon('Search')}<input data-instance-search="${n.id}" aria-label="${n.id} 搜索全部变量" value="${esc(config.search)}" placeholder="中文名称、变量标识"></label><select data-instance-group="${n.id}" aria-label="${n.id} 变量分组">${[['all', '全部分组'], ['parameter', '设备参数'], ['port', '端口变量'], ['custom', '自定义变量'], ['system', '系统变量']].map(([key, label]) => option(key, label, config.group)).join('')}</select><label class="instance-edit-source">编辑<select data-instance-source-select="${n.id}" aria-label="${n.id} 编辑目标">${option(-1, '待应用草稿', config.source)}${data.bankNames.map((name, i) => option(i, '库值 ' + (i + 1) + ' · ' + name, config.source)).join('')}</select></label></div>
    <div class="instance-bank-actions"><label class="check-label"><input type="checkbox" data-instance-toggle="allBanks" data-id="${n.id}" ${config.allBanks ? 'checked' : ''}>三组对照</label><label class="check-label"><input type="checkbox" data-instance-toggle="onlyDiff" data-id="${n.id}" ${config.onlyDiff ? 'checked' : ''}>仅可写差异</label>${config.source < 0 ? `<span>草稿 → ${esc(n.id)}</span><span class="badge ${pendingCount(n) ? 'warn' : 'good'}" data-pending-for="${n.id}">${pendingCount(n)} 项待应用</span>` : `<span>库值 ${config.source + 1} → ${esc(n.id)}</span><span class="badge warn" data-bank-diff>${instanceBankDiff(n, config.source).length} 项差异</span>${btn('capture-instance-bank', '当前值存入此库', 'Copy', `data-id="${n.id}" data-bank="${config.source}"`, 'small ghost')}`}</div>
    <div class="instance-table-wrap" data-instance-table="${n.id}">${instanceVariableRows(f, n)}</div>
    <div class="instance-footnote">${btn('save-instance-model', '保存为型号', 'Database', `data-id="${n.id}"`, 'small ghost')}<span>曲线记录已生效值。端口“—”表示未采样；保存保留草稿，确认应用后生效。</span></div>
  </div>`;
}
function editInstanceArray(n, id, source) {
  const v = moduleOf(n).variables.find(v => v.id === id);
  if (!v || !instanceWritable(v) || !v.type.endsWith('[8]')) return;
  const data = ensureInstanceVariables(n), value = source < 0 ? instanceDraftValue(n, v) : data.banks[source][id];
  openDialog(`${n.id} · ${v.label}`, source < 0 ? '编辑待应用草稿，确认应用后才改变当前值。' : `编辑这台设备的库值 ${source + 1}。`, `<div class="fields">${value.map((n, i) => field('item' + i, `[${i}]`, n, `type="number" step="${v.type.startsWith('int') ? '1' : 'any'}" required`)).join('')}</div>`, fields => {
    const result = value.map((_, i) => numeric(fields['item' + i], -1e12, 1e12, v.type.startsWith('int')));
    if (source < 0) data.draft[id] = result; else data.banks[source][id] = result;
    markDirty(ownerOfInstance(n)); renderFloats();
  }, '保存到草稿');
}
function updateInstanceVariableInput(el) {
  const n = instance(el.dataset.id), v = moduleOf(n).variables.find(v => v.id === el.dataset.instanceValue);
  if (!v || !instanceWritable(v) || v.type.endsWith('[8]')) return;
  const source = Number(el.dataset.instanceSource), data = ensureInstanceVariables(n), value = el.value === '' ? '' : Number(el.value);
  if (source < 0) { if (v.origin === 'parameter') n.draft[v.param] = value; else data.draft[v.id] = value; }
  else data.banks[source][v.id] = value;
  el.closest('td').classList.toggle('edited', !sameValue(instanceVariableValue(n, v), value));
  const shell = el.closest('.floater');
  const pending = shell.querySelector('[data-pending-for]'); if (pending) pending.textContent = `${pendingCount(n)} 项待应用`;
  const difference = shell.querySelector('[data-bank-diff]'); if (difference) difference.textContent = `${instanceBankDiff(n, source).length} 项差异`;
  const apply = shell.querySelector('[data-action="apply-instance"]'); if (apply) apply.disabled = !pendingCount(n);
  const bankApply = shell.querySelector('[data-action="apply-instance-bank"]'); if (bankApply) bankApply.disabled = !instanceBankDiff(n, source).length;
  markDirty(ownerOfInstance(n));
}
function refreshInstanceVariableReadouts(f, n) {
  const shell = root.querySelector(`[data-float-id="${f.id}"]`); if (!shell) return;
  const owner = ownerOfInstance(n), m = moduleOf(n);
  const runLabel = shell.querySelector('[data-instance-run]'); if (runLabel) runLabel.textContent = `${statusText(owner.run)} · ${clockLabel(owner.run.time)}`;
  for (const cell of shell.querySelectorAll('[data-instance-live]')) {
    const v = m.variables.find(v => v.id === cell.dataset.instanceLive);
    if (v) cell.innerHTML = instanceValueCell(n, v, -1, false, instanceVariableValue(n, v, owner));
  }
}
function validateInstanceVariableState(n, m) {
  const data = n.variableState; if (!data) return; // Older saved prototypes.
  const valueMap = value => value && typeof value === 'object' && !Array.isArray(value);
  if (data.schema !== 1 || !valueMap(data.values) || !valueMap(data.draft) || !Array.isArray(data.banks) || data.banks.length !== 3 || data.banks.some(bank => !valueMap(bank)) || !Array.isArray(data.bankNames) || data.bankNames.length !== 3 || data.bankNames.some(name => typeof name !== 'string')) throw Error('设备变量与三组库值数据不完整。');
  const validDraftNumber = x => x === '' || typeof x === 'number' && Number.isFinite(x);
  for (const v of m.variables) {
    const values = [...data.banks.map(b => b?.[v.id]), ...(v.origin === 'custom' ? [data.values[v.id], data.draft[v.id]] : [])];
    for (const value of values) {
      if (value === undefined || value === null && v.origin === 'port') continue;
      if (v.type.endsWith('[8]') ? !Array.isArray(value) || value.length !== 8 || value.some(x => !validDraftNumber(x)) : !validDraftNumber(value)) throw Error(`${n.id} 的 ${v.name} 数据格式不合法。`);
    }
  }
}
