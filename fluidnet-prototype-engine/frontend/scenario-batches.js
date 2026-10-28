/* Saved-input batches: the server owns snapshots, execution and result retention. */
window.createScenarioBatchesUI = function (ui) {
  const {esc, btn, heading, msg} = ui;
  const engine = ui.engine;
  const labels = {ready: '待启动', pending: '待运行', running: '运行中', completed: '已完成',
    completed_with_errors: '已结束 · 部分失败', failed: '失败', cancelled: '已取消', interrupted: '已中断'};
  const colors = ['#2778a9', '#d67818', '#24977c', '#9566bd'];
  const model = {projectId: '', epoch: 0, setup: null, form: {}, preview: null, request: null, requestId: null,
    batches: [], total: 0, selectedId: '', detail: null, busy: false, loading: false, loaded: false,
    error: '', allProjects: false, curveKey: '', curveItems: [], curves: [], curveTicket: 0, curveLoading: false,
    curveError: '', lastCurveSignature: '', filter: '', historyHtml: '', detailHtml: '', curveTouched: false};
  let timer;
  const root = () => document.getElementById('batch-page');
  const option = (value, label, selected) => `<option value="${esc(value)}" ${value === selected ? 'selected' : ''}>${esc(label)}</option>`;
  const field = (key, label, value, type = 'text', attrs = '') => `<label class="field"><span>${esc(label)}</span><input type="${type}" data-batch-field="${key}" aria-label="${esc(label)}" value="${esc(value ?? '')}" ${attrs}></label>`;
  const badge = status => `<span class="badge ${status === 'completed' ? 'good' : ['failed', 'interrupted'].includes(status) ? 'warn' : ''}" data-batch-status>${esc(labels[status] || status)}</span>`;
  const format = value => Number.isFinite(value) ? Number(value.toPrecision(7)).toLocaleString('zh-CN', {maximumFractionDigits: 9}) : '—';
  const display = (value, variable) => Number.isFinite(value) ? value / variable.unit.display_scale + variable.unit.display_offset : null;
  const selectedParameter = () => model.setup?.parameters.find(p => p.instance_id === model.form.instanceId && p.parameter_id === model.form.parameterId);
  const selectionKey = () => 'fluidnet-batch-selected:' + model.projectId;
  function rememberSelection() {try {localStorage.setItem(selectionKey(), model.selectedId);} catch {}}
  function render() {if (ui.ui().route === 'batches') ui.render();}
  function invalidate() {model.preview = null; model.request = null; model.requestId = null; model.error = '';}
  function resetProject(project) {
    clearTimeout(timer);
    model.curveTicket++;
    Object.assign(model, {projectId: project.id, epoch: model.epoch + 1, setup: null, form: {}, preview: null,
      request: null, requestId: null, detail: null, batches: [], total: 0, loaded: false, loading: false,
      busy: false, error: '', curves: [], curveItems: [], curveKey: '', lastCurveSignature: '', filter: '',
      historyHtml: '', detailHtml: '', curveTouched: false});
    try {model.selectedId = localStorage.getItem(selectionKey()) || '';} catch {model.selectedId = '';}
  }
  function chooseParameter() {
    const parameter = selectedParameter();
    if (!parameter) return;
    model.form.values = String(parameter.value);
    model.form.start = String(parameter.minimum ?? parameter.value);
    model.form.stop = String(parameter.maximum ?? parameter.value);
    model.form.count = '5';
    if (parameter.parameter_id === 'opening_ratio' && parameter.unit.display_unit === '%') {
      Object.assign(model.form, {seriesType: 'range', values: '20, 40, 60, 80, 100', start: '20', stop: '100'});
    }
  }
  function variableChoices() {
    const query = model.filter.trim().toLowerCase();
    const choices = model.setup.variables.filter(v => !query || (v.label + ' ' + v.key).toLowerCase().includes(query));
    return choices.map(v => `<label class="batch-check"><input type="checkbox" data-batch-variable="${esc(v.key)}" ${model.form.variables.includes(v.key) ? 'checked' : ''}><span>${esc(v.label)}<small>${esc(v.key)} · ${esc(v.unit.display_unit)}</small></span></label>`).join('') || '<p class="muted">没有匹配变量。</p>';
  }
  function configMarkup() {
    const p = ui.project();
    if (!engine().health?.capabilities?.scenario_batches)
      return '<p class="notice">请连接启用持久工作区的计算服务。</p>';
    const reload = btn('batch-prepare', model.setup ? '重新保存并读取项目' : '保存项目并准备工况', 'Save', model.busy ? 'disabled' : '', model.setup ? 'small' : 'primary');
    if (!model.setup) return `<div class="stack"><p>${esc(p.name)}</p><p class="muted">使用已应用的设备参数建立批次。每个工况独立运行，结果随批次保存。</p>${reload}</div>`;
    const {form, setup} = model;
    const nodes = [...new Map(setup.parameters.map(p => [p.instance_id, p.instance_name])).entries()];
    const parameters = setup.parameters.filter(p => p.instance_id === form.instanceId);
    const parameter = selectedParameter();
    const source = form.sourceType === 'scenarios'
      ? `<div class="batch-choices" aria-label="选择已有工况">${setup.scenarios.map(s => `<label class="batch-check"><input type="checkbox" data-batch-scenario="${esc(s.id)}" ${form.scenarioIds.includes(s.id) ? 'checked' : ''}><span>${esc(s.name)}</span></label>`).join('') || '<p class="muted">当前项目尚无工况，可切换为参数扫描。</p>'}</div>`
      : `<div class="fields"><label class="field"><span>扫描设备</span><select data-batch-field="instanceId" aria-label="扫描设备">${nodes.map(([id, name]) => option(id, id + ' · ' + name, form.instanceId)).join('')}</select></label><label class="field"><span>扫描参数</span><select data-batch-field="parameterId" aria-label="扫描参数">${parameters.map(p => option(p.parameter_id, p.label, form.parameterId)).join('')}</select></label></div>
        <p class="batch-unit" data-batch-unit>输入单位：<strong>${esc(parameter?.unit.display_unit || '—')}</strong> · 当前 ${format(parameter?.value)}${parameter?.minimum != null ? ' · 最小 ' + format(parameter.minimum) : ''}${parameter?.maximum != null ? ' · 最大 ' + format(parameter.maximum) : ''}</p>
        <label class="field"><span>取值方式</span><select data-batch-field="seriesType" aria-label="取值方式">${option('range', '等间距序列', form.seriesType)}${option('values', '显式值列表', form.seriesType)}</select></label>
        ${form.seriesType === 'range' ? `<div class="batch-range">${field('start', '起始值', form.start, 'number', 'step="any"')}${field('stop', '结束值', form.stop, 'number', 'step="any"')}${field('count', '工况数量', form.count, 'number', 'min="2" max="20" step="1"')}</div>`
          : field('values', '扫描值列表', form.values, 'text', 'placeholder="例如 20, 40, 60"')}
        <p class="muted small">最多 20 个工况。输入采用上方显示单位。</p>`;
    return `<div class="stack">
      <div class="row spread"><span class="batch-source-label">${esc(setup.project_name)} · 修订 ${setup.revision}</span>${reload}</div>
      <fieldset class="batch-form stack" ${model.busy ? 'disabled' : ''}>
        ${field('name', '批次名称', form.name, 'text', 'maxlength="120"')}
        <label class="field"><span>工况来源</span><select data-batch-field="sourceType" aria-label="工况来源">${option('sweep', '生成参数工况', form.sourceType)}${option('scenarios', '使用已有工况', form.sourceType)}</select></label>
        ${source}
        <label class="field"><span>计算方式</span><select data-batch-field="runMode" aria-label="批次计算方式">${option('steady', '稳态', form.runMode)}${option('dynamic', '动态 · 顺序快速计算', form.runMode)}</select></label>
        ${form.runMode === 'dynamic' ? `<div class="fields">${field('duration', '仿真时长 · s', form.duration, 'number', 'min="0.001" step="any"')}${field('dt', '输出步长 · s', form.dt, 'number', 'min="0.001" max="60" step="any"')}</div>` : ''}
        <div class="row spread"><strong>观察与比较变量</strong><span class="muted" data-batch-variable-count>${form.variables.length} / 16</span></div>
        <input class="batch-filter" type="search" data-batch-filter aria-label="筛选批次变量" placeholder="按设备、变量名筛选" value="${esc(model.filter)}">
        <div class="batch-choices" id="batch-variable-choices">${variableChoices()}</div>
      </fieldset>
    </div>`;
  }
  function previewValue(item) {
    if (item.parameter_value != null) return format(item.parameter_value);
    const parts = [];
    for (const [id, values] of Object.entries(item.scenario.overrides)) {
      for (const [key, value] of Object.entries(values)) {
        const spec = model.setup?.parameters.find(p => p.instance_id === id && p.parameter_id === key);
        const shown = Number.isFinite(value) && spec ? format(display(value, spec)) : JSON.stringify(value);
        parts.push(id + ' · ' + (spec?.label || key) + ' = ' + shown + (spec ? ' ' + spec.unit.display_unit : ''));
      }
    }
    return esc(parts.join('；') || '基础参数');
  }
  function previewMarkup() {
    if (!model.preview) return model.detail
      ? '<p class="muted">批次输入和结果独立保存。可在左侧修改参数，预览新的工况。</p>'
      : '<div class="batch-empty"><strong>先预览，再开始计算</strong><p>在左侧选择参数和观察变量，核对生成的工况。</p></div>';
    const preview = model.preview;
    return `<div class="row spread"><div><h3>工况预览</h3><p class="muted">${esc(preview.source.project_name)} · 修订 ${preview.source.revision} · ${preview.items.length} 个工况</p></div>${btn('batch-create', '保存并运行批次', 'Play', model.busy ? 'disabled' : '', 'primary')}</div>
      <div class="batch-table-scroll"><table class="data-table"><thead><tr><th>工况</th><th>扫描值 / 参数覆盖</th><th>单位</th></tr></thead><tbody>${preview.items.map(item => `<tr><td>${esc(item.name)}</td><td>${previewValue(item)}</td><td>${esc(item.parameter_unit || '按原工况')}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function historyMarkup() {
    const listed = [...model.batches];
    if (model.detail && !listed.some(b => b.id === model.detail.id)) listed.unshift(model.detail);
    return `<div class="row gap-12 wrap"><label class="field grow"><span>已保存批次</span><select data-batch-history aria-label="已保存批次">${option('', '请选择批次', model.selectedId)}${listed.map(b => option(b.id, b.project_name + ' · ' + b.name + ' · ' + (labels[b.status] || b.status), model.selectedId)).join('')}</select></label>
      <label class="batch-check"><input type="checkbox" data-batch-all ${model.allProjects ? 'checked' : ''}><span>全部项目</span></label>${btn('batch-refresh', '刷新', 'RefreshCw', model.loading ? 'disabled' : '', 'small')}
      ${model.batches.length < model.total ? btn('batch-more', '更早批次', 'History', '', 'small') : ''}</div>`;
  }
  function diagnosticMarkup(item) {
    const diagnostics = item.diagnostics.filter(d => d.severity !== 'info' && d.code !== 'DYNAMIC_QUASI_STEADY');
    if (!diagnostics.length) return '<span class="muted">—</span>';
    return diagnostics.map(d => '<details class="batch-' + (d.severity === 'error' ? 'error' : 'warning') +
      '"><summary>' + esc(d.severity === 'error' ? '错误详情' : '计算提示') + '</summary><p>' +
      esc(d.message) + '</p></details>').join('');
  }
  function detailMarkup() {
    const detail = model.detail;
    if (!detail) return '<div class="batch-empty"><p>运行后可在这里查看进度、比较结果，或选择一个历史批次。</p></div>';
    const canStart = detail.status !== 'running' && detail.items.some(i => ['pending', 'interrupted'].includes(i.status));
    const canCancel = detail.status === 'running' || detail.items.some(i => ['pending', 'interrupted'].includes(i.status));
    const running = detail.items.find(i => i.status === 'running');
    const quasiSteady = detail.items.some(i => i.diagnostics.some(d => d.code === 'DYNAMIC_QUASI_STEADY'));
    return `<div class="row spread wrap"><div><h2>${esc(detail.name)}</h2><p class="muted">${esc(detail.project_name)} · 来源修订 ${detail.project_revision} · ${detail.completed} / ${detail.total} 完成</p></div>
      <div class="row wrap gap-6">${badge(detail.status)}
      ${canStart ? btn('batch-start', detail.status === 'ready' ? '启动批次' : '继续未完成项', 'Play', model.busy ? 'disabled' : '', 'primary small') : ''}
      ${canCancel ? btn('batch-cancel', '取消剩余工况', 'Square', model.busy ? 'disabled' : '', 'small') : ''}
      ${running?.run_id ? btn('batch-stop-current', '停止当前工况', 'Square', model.busy ? 'disabled' : '', 'small') : ''}
      ${btn('batch-export', '导出 CSV', 'Download', model.busy ? 'disabled' : '', 'small')}
      ${detail.status !== 'running' ? btn('batch-delete', '删除批次', 'Trash2', model.busy ? 'disabled' : '', 'small') : ''}</div></div>
      ${detail.error ? `<p class="notice error">${esc(detail.error)}</p>` : ''}
      ${detail.status === 'interrupted' ? '<p class="notice">服务已中断。继续时从批次保存的输入新建运行，保留已完成项。</p>' : ''}
      ${quasiSteady ? '<p class="batch-model-note">模型说明：当前管网采用准稳态时间序列，每个时刻求解水力与热力平衡。</p>' : ''}
      <div class="batch-table-scroll"><table class="data-table batch-result-table"><thead><tr><th>工况</th><th>状态</th>${detail.variables.map(v => `<th title="${esc(v.key)}">${esc(v.label)}<small>${esc(v.unit.display_unit)}</small></th>`).join('')}<th>诊断</th></tr></thead><tbody>
      ${detail.items.map(item => `<tr data-batch-item="${esc(item.id)}" data-status="${item.status}"><td>${esc(item.name)}${item.attempts.length > 1 ? `<small>第 ${item.attempts.length} 次运行</small>` : ''}</td><td>${badge(item.status)}</td>
      ${detail.variables.map(v => `<td data-batch-value="${esc(v.key)}">${item.status === 'completed' ? format(display(item.values[v.key], v)) : '—'}</td>`).join('')}
      <td class="batch-diagnostic">${diagnosticMarkup(item)}</td></tr>`).join('')}</tbody></table></div>
      <div class="batch-comparison"><div class="row spread"><h3>工况曲线</h3><span class="muted">同一变量 · 最多叠加 4 个已完成工况</span></div>
      <label class="field"><span>比较变量</span><select data-batch-curve-key aria-label="批次比较变量">${detail.variables.map(v => option(v.key, v.label + ' / ' + v.unit.display_unit, model.curveKey)).join('')}</select></label>
      <div class="batch-series-choices">${detail.items.filter(i => i.status === 'completed').map(item => `<label class="batch-check"><input type="checkbox" data-batch-curve-item="${esc(item.id)}" ${model.curveItems.includes(item.id) ? 'checked' : ''}><span>${esc(item.name)}</span></label>`).join('') || '<span class="muted">完成工况后显示曲线。</span>'}</div>
      <div id="batch-curve">${chartMarkup()}</div></div>
      <details class="batch-provenance"><summary>查看输入来源与运行记录</summary><p>输入快照：<code>${esc(detail.snapshot_hash)}</code></p>
      <p>模块：${detail.source.modules.map(m => esc(m.name) + ' v' + m.version + ' · ' + esc((m.content_hash || m.definition_hash).slice(0, 12))).join('；')}</p>
      <p>控制脚本：${detail.source.controls.map(c => esc(c.id) + ' · ' + (c.enabled ? '启用' : '禁用') + ' · ' + esc(c.content_hash.slice(0, 12))).join('；') || '无'}</p>
      ${detail.items.map(item => `<p>${esc(item.name)}：${item.attempts.map(a => esc(a.run_id) + '（' + esc(labels[a.status]) + '）').join(' → ') || '尚未启动'}</p>`).join('')}</details>`;
  }
  function chartMarkup() {
    if (model.curveLoading) return '<p class="batch-empty">正在读取保存的曲线…</p>';
    if (model.curveError) return `<p class="notice error">${esc(model.curveError)}</p>`;
    const series = model.curves.map((entry, i) => ({...entry, color: colors[i],
      name: model.detail?.items.find(item => item.id === entry.item_id)?.name || entry.item_id,
      points: entry.points.map(([t, value]) => [t, display(value, entry.variable)])}));
    const points = series.flatMap(s => s.points).filter(p => Number.isFinite(p[1]));
    if (!points.length) return '<p class="batch-empty">选择已完成工况和有可用数据的变量。</p>';
    const x0 = Math.min(...points.map(p => p[0])), x1 = Math.max(x0 + 1e-9, ...points.map(p => p[0]));
    const low = Math.min(...points.map(p => p[1])), high = Math.max(...points.map(p => p[1]));
    const pad = Math.max((high - low) * .08, Math.abs(low) * .01, 1e-8), y0 = low - pad, y1 = high + pad;
    const x = t => 78 + (t - x0) / (x1 - x0) * 900, y = v => 247 - (v - y0) / (y1 - y0) * 220;
    const grid = Array.from({length: 5}, (_, i) => {const value = y0 + (y1 - y0) * i / 4;
      return `<path d="M78 ${y(value)} H978" stroke="var(--border)" fill="none"/><text x="68" y="${y(value) + 4}" text-anchor="end">${esc(format(value))}</text>`;}).join('');
    const paths = series.map(s => {
      let active = false;
      const path = s.points.map(([t, v]) => {if (!Number.isFinite(v)) {active = false; return '';}
        const command = active ? 'L' : 'M'; active = true; return command + x(t) + ' ' + y(v);}).join(' ');
      return `<path data-batch-series="${esc(s.item_id)}" d="${path}" fill="none" stroke="${s.color}" stroke-width="2"/>
        ${s.points.length <= 30 ? s.points.filter(p => Number.isFinite(p[1])).map(([t, v]) => `<circle cx="${x(t)}" cy="${y(v)}" r="2" fill="${s.color}"/>`).join('') : ''}`;
    }).join('');
    return `<svg class="batch-plot" viewBox="0 0 1010 290" role="img" aria-label="批次工况曲线">${grid}${paths}
      <text x="78" y="280">${esc(format(x0))} s</text><text x="978" y="280" text-anchor="end">${esc(format(Math.max(...points.map(p => p[0]))))} s</text>
      <text x="78" y="16">${esc(series[0].variable.unit.display_unit)}</text></svg>
      <div class="batch-legend">${series.map(s => `<span><i style="background:${s.color}"></i>${esc(s.name)} · ${s.points.length} 点 · 抽样步幅 ${s.stride}</span>`).join('')}</div>`;
  }
  function markup(project) {
    if (project.id !== model.projectId) resetProject(project);
    return `<div class="page-shell batch-page" id="batch-page">
      ${heading('批量工况与方案比较', '固定一次输入，依次运行多个工况，并保存可重复查看的结果。',
        btn('nav', '返回建模', 'Network', 'data-route="workbench"', 'small'), 'SCENARIO STUDY')}
      <div id="batch-error" class="notice error" role="alert" ${model.error ? '' : 'hidden'}>${esc(model.error)}</div>
      <div class="batch-layout"><section class="panel batch-config"><div class="panel-head"><h2>生成工况</h2></div><div class="panel-body">${configMarkup()}</div>
      ${model.setup ? `<footer class="batch-config-footer">${btn('batch-preview', model.busy ? '处理中…' : '预览工况', 'Eye', model.busy ? 'disabled' : '', 'primary')}</footer>` : ''}</section>
      <div class="batch-results"><section class="panel"><div class="panel-body" id="batch-preview">${previewMarkup()}</div></section>
      <section class="panel"><div class="panel-body stack"><div id="batch-history">${historyMarkup()}</div><div id="batch-detail" class="stack">${detailMarkup()}</div></div></section></div></div></div>`;
  }
  function paint() {
    if (!root()) return;
    const history = historyMarkup(), detail = detailMarkup();
    if (history !== model.historyHtml) {document.getElementById('batch-history').innerHTML = history; model.historyHtml = history;}
    if (detail !== model.detailHtml) {document.getElementById('batch-detail').innerHTML = detail; model.detailHtml = detail;}
    document.getElementById('batch-preview').innerHTML = previewMarkup();
    const error = document.getElementById('batch-error'); error.textContent = model.error; error.hidden = !model.error;
  }
  async function loadCurves() {
    const detail = model.detail, key = model.curveKey, ticket = ++model.curveTicket;
    if (!detail || !key) return;
    const ids = model.curveItems.filter(id => detail.items.some(i => i.id === id && i.status === 'completed')).slice(0, 4);
    const signature = JSON.stringify([detail.id, key, ids]);
    if (signature === model.lastCurveSignature) return;
    model.curveLoading = true; model.curveError = ''; model.curves = []; paint();
    try {
      const rows = await Promise.all(ids.map(id => engine().batchCurve(detail.id, id, key)));
      if (ticket !== model.curveTicket || model.detail?.id !== detail.id || model.curveKey !== key) return;
      model.curves = rows; model.lastCurveSignature = signature;
    } catch (error) {if (ticket === model.curveTicket) model.curveError = error.message;}
    finally {if (ticket === model.curveTicket) {model.curveLoading = false; paint();}}
  }
  function acceptDetail(detail) {
    if (detail && detail.id === model.detail?.id && detail.updated_at < model.detail.updated_at) return;
    if (detail?.id !== model.detail?.id) {
      model.curveKey = detail?.variables[0]?.key || ''; model.curveItems = [];
      model.curves = []; model.lastCurveSignature = ''; model.curveTicket++; model.curveTouched = false;
    }
    model.detail = detail;
    if (detail && !model.curveTouched)
      model.curveItems = detail.items.filter(i => i.status === 'completed').slice(0, 3).map(i => i.id);
    paint(); if (detail) void loadCurves();
  }
  function schedule() {
    clearTimeout(timer);
    if (root() && (model.detail?.status === 'running' || model.detail?.items.some(i => i.status === 'running')
        || model.batches.some(b => b.status === 'running')))
      timer = setTimeout(() => void refresh(), 500);
  }
  async function refresh(more = false) {
    if (model.loading || !engine().health?.capabilities?.scenario_batches) return;
    const epoch = model.epoch;
    model.loading = true;
    try {
      const response = await engine().listBatches(model.allProjects ? null : model.projectId, more ? model.batches.length : 0);
      if (epoch !== model.epoch) return;
      model.batches = more ? [...model.batches, ...response.batches] : response.batches;
      model.total = response.total; model.loaded = true;
      if (!model.selectedId) model.selectedId = model.batches[0]?.id || '';
      const selected = model.selectedId;
      if (selected) {
        try {
          const detail = await engine().readBatch(selected);
          if (epoch === model.epoch && model.selectedId === selected) {acceptDetail(detail); rememberSelection();}
        } catch (error) {
          if (epoch !== model.epoch) return;
          model.selectedId = ''; model.detail = null; model.error = error.message; rememberSelection();
        }
      } else acceptDetail(null);
    } catch (error) {if (epoch === model.epoch) model.error = error.message;}
    finally {if (epoch === model.epoch) {model.loading = false; paint(); schedule();}}
  }
  function requestBody() {
    const form = model.form;
    if (!model.setup) throw Error('请先保存项目并准备工况');
    const body = {revision: model.setup.revision, variables: [...form.variables],
      options: {mode: form.runMode, duration_s: Number(form.duration), dt_s: Number(form.dt)}};
    if (!body.variables.length || body.variables.length > 16) throw Error('请选择 1–16 个观察变量');
    if (form.sourceType === 'scenarios') {
      body.scenario_ids = [...form.scenarioIds];
      if (!body.scenario_ids.length || body.scenario_ids.length > 20) throw Error('请选择 1–20 个工况');
    } else {
      body.sweep = {instance_id: form.instanceId, parameter_id: form.parameterId};
      if (form.seriesType === 'range') {
        const range = {start: Number(form.start), stop: Number(form.stop), count: Number(form.count)};
        if (!form.start.trim() || !form.stop.trim() || !Number.isFinite(range.start) || !Number.isFinite(range.stop)
          || !Number.isInteger(range.count) || range.count < 2 || range.count > 20) throw Error('请填写有限的起止值和 2–20 个工况');
        body.sweep.range = range;
      } else {
        const value = form.values.trim();
        const values = value.startsWith('[') ? JSON.parse(value) : value.split(/[\s,，;；]+/).filter(Boolean).map(Number);
        if (!Array.isArray(values) || !values.length || values.length > 20 || values.some(v => typeof v !== 'number' || !Number.isFinite(v)))
          throw Error('扫描值须为 1–20 个有限数值');
        body.sweep.values = values;
      }
    }
    if (!Number.isFinite(body.options.duration_s) || body.options.duration_s <= 0 || !Number.isFinite(body.options.dt_s)
      || body.options.dt_s <= 0 || body.options.dt_s > 60) throw Error('请填写有效的仿真时长与输出步长');
    return body;
  }
  async function task(fn) {
    if (model.busy) return;
    const epoch = model.epoch; model.busy = true; model.error = ''; render();
    try {await fn(epoch);} catch (error) {if (epoch === model.epoch) {model.error = error.message; msg(error.message, true);}}
    finally {if (epoch === model.epoch) {model.busy = false; render(); schedule();}}
  }
  async function action(name) {
    if (name === 'batch-refresh' || name === 'batch-more') return refresh(name === 'batch-more');
    if (name === 'batch-delete') {
      const id = model.selectedId;
      ui.confirm('删除批次', '删除这个批次的结果、曲线和固定输入。原项目和其他批次保留。', () => {
        void task(async () => {await engine().deleteBatch(id); model.selectedId = ''; acceptDetail(null); await refresh();});
      }, '删除批次');
      return;
    }
    return task(async epoch => {
      if (name === 'batch-prepare') {
        const project = ui.project(), key = ui.projectKey(project);
        const saved = await engine().saveProject(project);
        if (epoch !== model.epoch) return;
        if (key !== ui.projectKey(project)) throw Error('保存期间项目已变化，请重新准备工况');
        const setup = await engine().batchOptions(project.id, saved.revision);
        if (epoch !== model.epoch) return;
        model.setup = setup;
        const first = setup.parameters.find(p => p.instance_id === 'V1' && p.parameter_id === 'opening_ratio') || setup.parameters[0];
        const preferred = ['V1.mass_flow_kg_s', 'P1.shaft_power_w', 'H1.heat_w'].filter(key => setup.variables.some(v => v.key === key));
        model.form = {name: project.name + ' · 参数工况', sourceType: 'sweep', seriesType: 'values',
          instanceId: first?.instance_id || '', parameterId: first?.parameter_id || '', variables: preferred.slice(0, 2),
          scenarioIds: setup.scenarios.slice(0, 20).map(s => s.id), runMode: project.solver.mode === 'dynamic' ? 'dynamic' : 'steady',
          duration: String(project.solver.duration || 60), dt: String(project.solver.dt || .1)};
        if (!model.form.variables.length) model.form.variables = setup.variables.filter(v => !v.key.includes('.param.')).slice(0, 2).map(v => v.key);
        chooseParameter(); invalidate();
      } else if (name === 'batch-preview') {
        const body = requestBody(), preview = await engine().previewBatch(model.projectId, body);
        if (epoch !== model.epoch) return;
        model.preview = preview; model.request = body; model.requestId = crypto.randomUUID();
        msg('工况预览已更新。');
      } else if (name === 'batch-create') {
        if (!model.preview || !model.request) throw Error('请先预览当前工况');
        const detail = await engine().createBatch(model.projectId, {...model.request, request_id: model.requestId,
          preview_hash: model.preview.preview_hash, name: model.form.name.trim()});
        if (epoch !== model.epoch) return;
        model.preview = null; model.request = null; model.requestId = null;
        model.selectedId = detail.id; rememberSelection(); acceptDetail(detail);
        const running = await engine().startBatch(detail.id);
        if (epoch !== model.epoch) return;
        acceptDetail(running); await refresh(); msg('批次已保存，工况依次运行。');
      } else if (name === 'batch-start') {
        const id = model.selectedId, detail = await engine().startBatch(id);
        if (epoch !== model.epoch || model.selectedId !== id) return;
        acceptDetail(detail); await refresh();
      } else if (name === 'batch-cancel') {
        const id = model.selectedId, detail = await engine().cancelBatch(id);
        if (epoch !== model.epoch || model.selectedId !== id) return;
        acceptDetail(detail); await refresh();
      } else if (name === 'batch-stop-current') {
        const item = model.detail?.items.find(i => i.status === 'running' && i.run_id);
        if (item) await engine().stopBatchRun(item.run_id); await refresh();
      } else if (name === 'batch-export') {
        const id = model.selectedId, blob = await engine().exportBatch(id);
        ui.download('batch-' + id + '.csv', blob); msg('批次比较表已导出。');
      }
    });
  }
  function input(event) {
    event.stopPropagation();
    const el = event.target, fieldName = el.dataset.batchField;
    if (el.matches('[data-batch-filter]')) {
      model.filter = el.value; document.getElementById('batch-variable-choices').innerHTML = variableChoices(); return;
    }
    if (!fieldName || el.tagName === 'SELECT') return;
    model.form[fieldName] = el.value; invalidate();
    const preview = document.getElementById('batch-preview'); if (preview) preview.innerHTML = previewMarkup();
  }
  function change(event) {
    event.stopPropagation();
    const el = event.target, data = el.dataset;
    if (data.batchField && el.tagName === 'SELECT') {
      model.form[data.batchField] = el.value;
      if (data.batchField === 'instanceId') model.form.parameterId = model.setup.parameters.find(p => p.instance_id === el.value)?.parameter_id || '';
      if (['instanceId', 'parameterId'].includes(data.batchField)) chooseParameter();
      invalidate(); render();
    } else if ('batchVariable' in data || 'batchScenario' in data) {
      const isVariable = 'batchVariable' in data, key = isVariable ? 'variables' : 'scenarioIds';
      const value = isVariable ? data.batchVariable : data.batchScenario;
      const values = model.form[key].filter(v => v !== value);
      if (el.checked) values.push(value);
      if (values.length > (isVariable ? 16 : 20)) {el.checked = false; msg('已达到可选数量上限', true); return;}
      model.form[key] = values; invalidate();
      if (isVariable) document.querySelector('[data-batch-variable-count]').textContent = values.length + ' / 16';
      document.getElementById('batch-preview').innerHTML = previewMarkup();
    } else if ('batchHistory' in data) {
      model.selectedId = el.value; model.lastCurveSignature = ''; rememberSelection(); void refresh();
    } else if ('batchAll' in data) {
      model.allProjects = el.checked; model.selectedId = ''; acceptDetail(null); void refresh();
    } else if ('batchCurveKey' in data) {
      model.curveKey = el.value; model.lastCurveSignature = ''; void loadCurves();
    } else if ('batchCurveItem' in data) {
      const ids = model.curveItems.filter(id => id !== data.batchCurveItem);
      if (el.checked) ids.push(data.batchCurveItem);
      if (ids.length > 4) {el.checked = false; msg('同一图最多叠加 4 个工况', true); return;}
      model.curveItems = ids; model.lastCurveSignature = ''; void loadCurves();
      model.curveTouched = true;
    }
  }
  function afterRender() {
    clearTimeout(timer);
    const element = root();
    if (!element) return;
    model.historyHtml = historyMarkup(); model.detailHtml = detailMarkup();
    element.addEventListener('input', input);
    element.addEventListener('change', change);
    if (!model.loaded && !model.loading) void refresh(); else schedule();
  }
  return {markup, afterRender, action};
};
