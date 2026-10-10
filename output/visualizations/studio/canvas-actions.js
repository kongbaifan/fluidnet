// 画布操作与模块定义共用端口 / 通路，不根据图形猜测内部连接。
function deviceToolsMarkup(n) {
  if (!n) return '';
  return `<div class="device-tools" role="toolbar" aria-label="选中设备操作"><strong>${esc(n.id)} · ${esc(n.name)}</strong>${ibtn('open-device', '参数与型号', 'SlidersHorizontal', `data-id="${n.id}"`)}${ibtn('device-variables', '查看全部变量', 'Table2', `data-id="${n.id}"`)}${ibtn('choose-device-model', '选择设备型号', 'Database', `data-id="${n.id}"`)}${ibtn('rotate-device', '顺时针旋转 90° · R', 'RotateCw', `data-id="${n.id}"`)}${ibtn('rotate-device', '逆时针旋转 90° · Shift+R', 'RotateCcw', `data-id="${n.id}" data-direction="-1"`)}${ibtn('device-definition', '查看模块定义', 'Box', `data-id="${n.id}"`)}</div>`;
}
function syncDeviceSelection() {
  if (ui.route !== 'workbench') return;
  const n = activePage().nodes.find(n => n.id === ui.selectedNode);
  const props = document.getElementById('selected-properties'), tools = document.getElementById('canvas-device-tools');
  if (props) props.innerHTML = propertiesMarkup(n);
  if (tools) tools.innerHTML = deviceToolsMarkup(n);
  root.querySelectorAll('#network [data-node]').forEach(el => el.classList.toggle('selected', el.dataset.node === n?.id));
}
function rotateDevice(id, direction = 1) {
  const n = activePage().nodes.find(n => n.id === id); if (!n) return;
  remember(); n.rotation = ((n.rotation || 0) + direction * 90 + 360) % 360;
  ui.selectedNode = n.id; markDirty(project()); render();
  root.querySelector(`#network [data-node="${n.id}"]`)?.focus({ preventScroll: true });
}
function setDeviceTab(f, tab) {
  f.tab = tab;
  if (tab === 'variables' && !f.variablesOpened) {
    const r = page.getBoundingClientRect(); f.variablesOpened = true;
    f.w = Math.min(780, r.width - 16); f.h = Math.min(650, r.height - 16);
    f.x = r.right - f.w - 12; f.y = r.top + 12;
  }
}
function openDeviceVariables(id, variableId) {
  const n = instance(id); if (!n) return;
  openDevice(id);
  const f = ui.floats.find(f => f.id === id); setDeviceTab(f, 'variables');
  if (variableId) {
    const v = moduleOf(n).variables.find(v => v.id === variableId);
    if (v) Object.assign(variableWindowState(f), { search: v.name, group: 'all', onlyDiff: false, source: -1 });
  }
  renderFloats();
}
function chooseDeviceModel(id) {
  const n = instance(id); if (!n) return;
  const items = state.models.filter(item => item.moduleId === n.moduleId && !item.archived);
  if (!items.length) { openDevice(id); msg('此模块还没有型号，可从设备当前值或库值保存型号。'); return; }
  openDialog(`选择型号 · ${n.id}`, '所选型号进入设备草稿，预览并应用后生效。', selectField('model', '设备型号', items.map(item => [item.id, `${item.name} · v${item.version}`]), n.draftModelId || n.modelId || items[0].id), data => {
    stageModel(n, data.model); openDevice(id); setDeviceTab(ui.floats.find(f => f.id === id), 'parameters'); renderFloats();
    msg('型号已进入设备草稿。');
  }, '进入设备草稿');
}
function openDeviceDefinition(id, variableId) {
  const n = instance(id); if (!n) return;
  const origin = { projectId: project().id, pageId: activePage().id, nodeId: id, variableId };
  if (variableId) ui.variableSearch = moduleOf(n).variables.find(v => v.id === variableId)?.name || '';
  openEditor(n.moduleId, variableId ? 'attributes' : 'drawing', origin);
}
function returnToDevice() {
  const origin = ui.editorOrigin; if (!origin) return;
  const owner = state.projects.find(p => p.id === origin.projectId), pg = owner?.pages.find(pg => pg.id === origin.pageId);
  if (!pg?.nodes.some(n => n.id === origin.nodeId)) { ui.editorOrigin = null; navigate('modules'); return; }
  if (state.activeProject !== owner.id) openProject(owner.id);
  owner.activePage = pg.id; navigate('workbench');
  if (origin.variableId) openDeviceVariables(origin.nodeId, origin.variableId); else openDevice(origin.nodeId);
}
function deviceContextMarkup(id) {
  return `${btn('open-device', '参数与型号', 'SlidersHorizontal', `data-id="${id}"`)}${btn('device-variables', '全部变量', 'Table2', `data-id="${id}"`)}${btn('choose-device-model', '选择设备型号', 'Database', `data-id="${id}"`)}${btn('device-definition', '查看模块定义', 'Box', `data-id="${id}"`)}<div class="spacer"></div>${btn('rotate-device', '顺时针旋转 · R', 'RotateCw', `data-id="${id}"`)}${btn('rotate-device', '逆时针旋转 · Shift+R', 'RotateCcw', `data-id="${id}" data-direction="-1"`)}${btn('copy-device', '复制设备', 'Copy', `data-id="${id}"`)}${btn('delete-node', '删除设备', 'Trash2', `data-id="${id}"`)}`;
}
function internalChannels(n) {
  const m = moduleOf(n);
  return m.channels.filter(c => c.enabled && m.ports.some(p => p.id === c.input) && m.ports.some(p => p.id === c.output));
}
function internalChannelsMarkup(n) {
  const m = moduleOf(n);
  return `<g transform="rotate(${n.rotation || 0})" class="internal-channels" aria-hidden="true">${internalChannels(n).map(c => {
    const a = portOffset(n, m.ports.find(p => p.id === c.input)), b = portOffset(n, m.ports.find(p => p.id === c.output)), mid = (a.x + b.x) / 2;
    return `<path class="internal-channel" data-channel-id="${esc(c.id)}" data-channel-input="${esc(c.input)}" data-channel-output="${esc(c.output)}" d="M ${a.x} ${a.y} C ${mid} ${a.y}, ${mid} ${b.y}, ${b.x} ${b.y}"/>`;
  }).join('')}</g>`;
}
function showCanvasInspection(target) {
  const node = target?.closest?.('#network [data-node]'), port = target?.closest?.('[data-port-node]');
  ui.canvasInspection = node ? { id: node.dataset.node, portId: port?.dataset.portId } : null;
  paintCanvasInspection();
}
function paintCanvasInspection() {
  const hint = document.getElementById('canvas-inspection'); if (!hint) return;
  const selected = ui.canvasInspection, n = activePage().nodes.find(n => n.id === selected?.id), m = n && moduleOf(n), p = m?.ports.find(p => p.id === selected.portId);
  root.querySelectorAll('#network .inspecting,#network .channel-active').forEach(el => el.classList.remove('inspecting', 'channel-active'));
  hint.hidden = !n;
  if (!n) return;
  const node = root.querySelector(`#network [data-node="${n.id}"]`); node?.classList.add('inspecting');
  const channels = internalChannels(n).filter(c => !p || c.input === p.id || c.output === p.id);
  node?.querySelectorAll('[data-channel-id]').forEach(el => el.classList.toggle('channel-active', channels.some(c => c.id === el.dataset.channelId)));
  const edge = p && activePage().edges.find(e => e[1] === n.id && e[2] === p.id || e[3] === n.id && e[4] === p.id);
  const connected = edge ? `已连接 ${edge[1] === n.id ? edge[3] : edge[1]}` : '未连接';
  hint.textContent = p ? `${n.id} · ${p.label} (${p.name}) · ${DOMAINS[p.domain].label}${p.direction === 'in' ? '入口' : '出口'} · ${channels.map(c => c.name).join(' / ') || '未绑定内部通路'} · ${connected}` : `${n.id} · ${n.name} · ${channels.length ? channels.map(c => c.name).join(' / ') : '未设置内部通路'} · 双击参数，R 旋转`;
}
