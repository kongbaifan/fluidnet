// 建模工作区：布局偏好只影响查看方式，参数仍通过显式应用生效。
function currentProjectPending() {
  return project().pages.flatMap(p => p.nodes).reduce((sum, n) => sum + pendingCount(n), 0);
}

function fitNetwork(pg = activePage()) {
  if (!pg.nodes.length) { pg.viewBounds = [-35, -5, 1140, 510]; }
  else {
    const xs = pg.nodes.map(n => n.x), ys = pg.nodes.map(n => n.y);
    pg.viewBounds = [Math.min(...xs) - 65, Math.min(...ys) - 65,
      Math.max(240, Math.max(...xs) - Math.min(...xs) + 130),
      Math.max(240, Math.max(...ys) - Math.min(...ys) + 170)];
  }
  pg.zoom = 1; pg.pan = [0, 0];
}

function networkViewBox(pg) {
  const valid = Array.isArray(pg.viewBounds) && pg.viewBounds.length === 4 && pg.viewBounds.every(Number.isFinite) && pg.viewBounds[2] > 0 && pg.viewBounds[3] > 0;
  const [x, y, width, height] = valid ? pg.viewBounds : [-35, -5, 1140, 510], zoom = pg.zoom || 1;
  return `${x + (width - width / zoom) / 2 - pg.pan[0]} ${y + (height - height / zoom) / 2 - pg.pan[1]} ${width / zoom} ${height / zoom}`;
}

function projectParameterKey(owner = project()) {
  return JSON.stringify({ solver: owner.solver, pages: owner.pages.map(pg => ({
    nodes: pg.nodes.map(n => ({ id: n.id, moduleId: n.moduleId, params: n.params, values: n.variableState?.values })),
    edges: pg.edges,
  })) });
}

function workbenchResultState() {
  const run = project().run;
  if (run.history.length < 2) return { text: '尚未采样 · 运行或单步查看结果', tone: '' };
  if (!run.parameterKey) return { text: '已有结果 · 请单步核对当前参数', tone: 'warn' };
  if (run.parameterKey !== projectParameterKey()) return { text: '参数已变更 · 等待重新采样', tone: 'warn' };
  return { text: `结果已更新 · ${clockLabel(run.history.at(-1).t)}`, tone: 'good' };
}

function entryPathsMarkup() {
  return `<div class="entry-paths">
    <section class="entry-path primary-path"><span class="entry-icon">${icon('Network')}</span><div class="grow"><h2>先把系统跑起来</h2><p>打开泵阀示例，调整阀门，在同一屏观察支路流量。</p></div>${btn('start-modeling', '打开示例调参', 'ArrowRight', '', 'primary')}</section>
    <section class="entry-path"><span class="entry-icon">${icon('Code2')}</span><div class="grow"><h2>制作自己的模块</h2><p>配置端口、变量与代码，保存型号后用于项目。</p></div>${btn('guided-demo', '进入模块开发', 'ArrowRight')}</section>
  </div>`;
}

function startModeling() {
  let p = state.projects.find(p => p.id === 'water-net');
  if (!p) {
    if (state.projects.length >= 20) throw Error('项目数量已达上限，请从项目管理打开已有项目。');
    p = makeProject(uid('project'), '泵阀并联管网', '调参并观察两条支路的流量。', waterPage());
    state.projects.push(p); normalizeState(); markDirty(p);
  }
  ui.showChart = true; ui.showLibrary = false; ui.workbenchChart = 'flow'; ui.pinnedChart = null;
  openProject(p.id);
  const n = p.pages.flatMap(pg => pg.nodes).find(n => moduleOf(n).kind === 'valve');
  if (n) {
    p.activePage = p.pages.find(pg => pg.nodes.includes(n)).id;
    openDevice(n.id);
    const f = ui.floats.find(f => f.id === n.id);
    f.docked = innerWidth >= 1000; rememberWindow(f);
  }
  fitNetwork();
  saveUI(); render();
  msg('先运行或单步，再修改开度、应用参数，观察底部两条支路的曲线。');
}

function isDocked(f) {
  return !!f.docked && !f.minimized && innerWidth >= 1000;
}

function syncDockLayout() {
  const workbench = root.querySelector('.workbench');
  if (!workbench) return;
  const active = ui.floats.find(f => instance(f.id) && isDocked(f));
  workbench.classList.toggle('has-docked', !!active);
}

function dockWindowBounds(f) {
  const rect = document.getElementById('inspector-dock').getBoundingClientRect();
  return { x: rect.left, y: rect.top, w: rect.width, h: rect.height };
}

function toggleDeviceDock(id) {
  const f = ui.floats.find(f => f.id === id);
  if (!f) return;
  if (innerWidth < 1000 && !f.docked) { msg('较宽的窗口可将参数停靠到右侧；当前使用浮窗。'); return; }
  const next = !f.docked;
  for (const other of ui.floats) if (other.docked && other !== f) { other.docked = false; rememberWindow(other); }
  f.docked = next; f.minimized = false; delete f.restore;
  rememberWindow(f); markDirty(); renderFloats();
}

function chartDockChoices() {
  return [['flow', '主管与 A / B 支路流量'], ['pressure', '泵出口压力'], ['temperature', '泵出口温度']]
    .concat(state.charts.extra.filter(v => v.projectId === project().id).map(v => [v.id, v.label]));
}

function workbenchChartData() {
  const run = project().run;
  if (!chartDockChoices().some(([id]) => id === ui.workbenchChart)) ui.workbenchChart = 'flow';
  const key = ui.workbenchChart;
  if (key === 'flow') return { history: run.history, keys: ['q', 'a', 'b'] };
  if (key === 'pressure' || key === 'temperature') return { history: run.history, keys: [key] };
  const variable = state.charts.extra.find(v => v.projectId === project().id && v.id === key);
  const seriesKey = 'extra:' + key;
  SERIES[seriesKey] = { name: variable.label, unit: variable.unit, color: 'blue' };
  return { history: run.history.filter(r => extraVariableValue(r, key) !== null).map(r => ({ t: r.t, [seriesKey]: extraVariableValue(r, key) })), keys: [seriesKey] };
}

function parameterEvents() {
  return project().run.events.filter(e => e.kind === 'parameters' || /参数已应用|应用库值/.test(e.text));
}

function workbenchChartMarkup() {
  const { history, keys } = workbenchChartData();
  if (history.length < 2) return `<div class="dock-empty">${icon('Activity')}<strong>还没有可观察的曲线</strong><span>点击右侧“运行”或“单步”，这里将同步显示当前项目的示例结果。</span></div>`;
  return chartSvg(history, keys, 'workbench-flow-chart', false, { compact: true, events: parameterEvents() });
}

function workbenchChartReadout() {
  const { history, keys } = workbenchChartData(), last = history.at(-1);
  return history.length > 1 ? `${clockLabel(last.t)} · ` + keys.filter(k => state.charts.series[k] !== false).map(k => `${SERIES[k].short || SERIES[k].name} ${number(last[k], 3)} ${SERIES[k].unit}`).join(' · ') : '当前项目 · 等待采样';
}

function renderWorkbenchChart() {
  if (!ui.showChart) return '';
  workbenchChartData();
  const event = parameterEvents().at(-1);
  return `<section class="workbench-chart" aria-label="同屏曲线">
    <header class="dock-chart-head"><strong>${icon('Activity')} 同屏观察</strong><label class="sr-only" for="workbench-chart-source">同屏观察变量</label><select id="workbench-chart-source" data-workbench-chart>${chartDockChoices().map(([id, label]) => option(id, label, ui.workbenchChart)).join('')}</select><span class="dock-source" title="${esc(project().name)}">当前项目 · 示例数据</span><span class="push"></span>${ibtn('full-curves', '打开完整曲线页', 'Maximize2')}${ibtn('toggle-chart', '收起同屏曲线', 'X')}</header>
    <div class="dock-chart-meta"><span data-result-status></span><div class="chart-legend">${(ui.workbenchChart === 'flow' ? ['q', 'a', 'b'] : []).map(k => `<button data-action="toggle-series" data-value="${k}" aria-pressed="${state.charts.series[k] !== false}" class="${state.charts.series[k] === false ? 'off' : ''}"><span class="series-key ${SERIES[k].color}"></span>${SERIES[k].short}</button>`).join('')}</div></div>
    <div id="workbench-chart-plot">${workbenchChartMarkup()}</div>
    <div class="dock-readout"><span id="workbench-flow-chart-readout">${workbenchChartReadout()}</span>${btn('release-cursor', '恢复实时读数', 'RefreshCw', `${ui.pinnedChart === 'workbench-flow-chart' ? '' : 'hidden'}`, 'ghost small')}</div>
    <div class="dock-event" data-workbench-event title="${esc(event?.text || '')}">${event ? `${clockLabel(event.t)} · ${esc(event.text)}` : '点击曲线可固定读数；参数应用时刻会显示为竖向虚线。'}</div>
  </section>`;
}

function refreshWorkbenchChart() {
  const plot = document.getElementById('workbench-chart-plot');
  if (!plot) return;
  plot.innerHTML = workbenchChartMarkup();
  const readout = document.getElementById('workbench-flow-chart-readout');
  if (readout) readout.textContent = workbenchChartReadout();
  restoreChartCursor();
}

function syncWorkbenchStatus() {
  const result = workbenchResultState();
  root.querySelectorAll('[data-result-status]').forEach(el => { el.textContent = result.text; el.className = 'result-status ' + result.tone; });
  root.querySelectorAll('[data-float-save]').forEach(el => el.textContent = state.dirty ? '草稿未保存' : '草稿已保存');
  root.querySelectorAll('[data-device-apply-status]').forEach(el => {
    const n = instance(el.dataset.deviceApplyStatus);
    if (n) { const count = pendingCount(n); el.textContent = count ? `${count} 项待应用 · 保存不会使其生效` : '参数已生效'; el.className = count ? 'pending-note' : 'applied-note'; }
  });
}

// 重绘与实时采样后保留固定游标的仿真时间，不保留失效的屏幕坐标。
function paintChartCursor(id, requestedTime, pinned = false) {
  const svg = document.getElementById(id), data = chartRegistry.get(id);
  if (!svg || !data?.rows.length) return;
  const t = clamp(requestedTime, data.minT, data.maxT), x = data.left + (t - data.minT) / (data.maxT - data.minT) * (data.right - data.left);
  let i = data.rows.findIndex(r => r.t >= t); if (i < 0) i = data.rows.length - 1;
  const a = data.rows[Math.max(0, i - 1)], b = data.rows[i], fraction = b.t === a.t ? 0 : clamp((t - a.t) / (b.t - a.t), 0, 1);
  const value = k => Number(a[k] || 0) + (Number(b[k] || 0) - Number(a[k] || 0)) * fraction;
  const guide = svg.querySelector('[data-chart-guide]');
  if (guide) { guide.setAttribute('x1', x); guide.setAttribute('x2', x); guide.setAttribute('opacity', '1'); }
  for (const marker of svg.querySelectorAll('[data-hover-mark]')) { marker.setAttribute('cx', x); marker.setAttribute('cy', data.y(value(marker.dataset.hoverMark))); marker.setAttribute('opacity', '1'); }
  const readout = document.getElementById(id + '-readout');
  if (readout) readout.textContent = `${pinned ? '已固定 · ' : ''}${clockLabel(t)} · ` + data.keys.map(k => `${SERIES[k]?.name || k} ${number(value(k), 3)} ${SERIES[k]?.unit || ''}`).join(' · ');
}

function restoreChartCursor() {
  if (ui.pinnedChart && ui.chartCursor?.id === ui.pinnedChart) paintChartCursor(ui.pinnedChart, ui.chartCursor.time, true);
  root.querySelectorAll('[data-action="release-cursor"]').forEach(el => el.hidden = ui.pinnedChart !== 'workbench-flow-chart');
}
