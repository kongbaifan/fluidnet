/* Module-author test cases are workspace drafts, independent of published code hashes. */
window.ModuleTestEditor = (() => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = (value, label, minimum = -Infinity, positive = false) => {
    const result = typeof value === 'number' ? value : typeof value === 'string' && value.trim() ? Number(value) : NaN;
    if (!Number.isFinite(result) || result < minimum || positive && result === 0) throw Error(`${label} 必须是${positive ? '大于零的' : minimum === 0 ? '非负' : ''}有限数值。`);
    return result;
  };
  const boundaryFields = [['inlet_pressure_pa','入口压力 · Pa',250000], ['outlet_pressure_pa','出口压力 · Pa',120000],
    ['inlet_temperature_k','入口温度 · K',293.15], ['outlet_temperature_k','出口温度 · K',293.15]];
  function pressureCase(conditions, reverse) {
    const result = clone(conditions);
    const change = boundary => {
      const inlet = boundary.inlet_pressure_pa ?? 250000, outlet = boundary.outlet_pressure_pa ?? 120000;
      boundary.inlet_pressure_pa = reverse ? outlet : inlet;
      boundary.outlet_pressure_pa = inlet;
    };
    change(result);
    for (const boundary of Object.values(result.channel_boundaries || {})) change(boundary);
    return result;
  }
  function cases(module, definition) {
    if (Array.isArray(module.authoringTestCases)) return clone(module.authoringTestCases);
    const conditions = {duration_s:.2, dt_s:.1, inlet_pressure_pa:250000, outlet_pressure_pa:120000, temperature_k:293.15, ...clone(module.testConditions || {})};
    const result = [
      {id:'forward', conditions},
      {id:'reverse', conditions:pressureCase(conditions,true)},
      {id:'zero', conditions:pressureCase(conditions,false)},
    ];
    if (definition.parameters.some(p => p.id === 'opening_ratio')) result.push({id:'closed', conditions:{...clone(conditions), parameters:{...conditions.parameters, opening_ratio:0}}});
    return result;
  }
  function mount(container, initial, definition) {
    const draft = clone(initial).map(c => ({...c, assertions:c.assertions || []}));
    const keys = [...new Set([
      ...(definition.variables || []).map(v => `D1.${v.id}`),
      ...(definition.channels || []).flatMap(c => ['mass_flow_kg_s','pressure_drop_pa','heat_w'].map(v => `D1.${c.id}.${v}`)),
    ])];
    const fields = [['inlet_pressure_pa','入口压力 · Pa',250000], ['outlet_pressure_pa','出口压力 · Pa',120000],
      ['temperature_k','边界温度 · K',293.15], ['duration_s','时长 · s',.2], ['dt_s','步长 · s',.1]];
    const enabledChannels = (definition.channels || []).filter(channel => channel.enabled !== false);
    function boundaryEditor(c, i) {
      const overrides = c.conditions?.channel_boundaries || {};
      const channels = [...new Set([...enabledChannels.map(channel => channel.id), ...Object.keys(overrides)])];
      if (!channels.length) return '';
      return `<div class="stack"><strong>逐通路边界</strong><p class="muted">启用独立边界的通路优先使用下方压力、温度和工质；清除后使用通用边界。</p>${channels.map(id => {
        const channel = enabledChannels.find(channel => channel.id === id), boundary = overrides[id];
        return `<section class="panel" data-suite-channel="${esc(id)}"><div class="panel-head"><strong>${esc(channel?.name || id)} · ${esc(id)}${channel ? '' : '（当前定义无可用通路）'}</strong>
          <button type="button" class="btn small" data-suite-action="${boundary ? 'remove-boundary' : 'add-boundary'}" data-case="${i}" data-boundary="${esc(id)}">${boundary ? '清除独立边界' : '设置独立边界'}</button></div>
          ${boundary ? `<div class="panel-body stack"><p class="muted">此通路使用独立边界，工质：${esc(boundary.fluid?.fluid || 'Water')}。</p><div class="fields">${boundaryFields.map(([key,label,fallback]) => `<label class="field"><span>${label}</span><input type="number" step="any" min="0" required data-case="${i}" data-boundary="${esc(id)}" data-boundary-field="${key}" value="${esc(boundary[key] ?? fallback)}" aria-label="${esc(c.id+' '+id+' '+label)}"></label>`).join('')}</div></div>` : '<div class="panel-body muted">使用通用边界。</div>'}</section>`;
      }).join('')}</div>`;
    }
    function render() {
      container.innerHTML = `<p class="muted">预期值使用引擎单位，检查最终帧。通过条件：绝对误差 ≤ max（绝对容差，相对容差 × |预期值|）。未配置预期值时，只检查网络运行是否有效。</p>
        <datalist id="module-assertion-keys">${keys.map(key => `<option value="${esc(key)}"></option>`).join('')}</datalist>
        <div class="stack">${draft.map((c,i) => `<section class="panel" data-suite-case="${i}"><div class="panel-head">
          <label class="field"><span>工况标识</span><input data-case="${i}" data-case-id value="${esc(c.id)}" required maxlength="81" aria-label="工况 ${i+1} 标识"></label>
          <button type="button" class="btn small" data-suite-action="remove-case" data-case="${i}" ${draft.length === 1 ? 'disabled' : ''}>删除工况</button></div>
          <div class="panel-body stack"><strong>通用边界与运行时间</strong><div class="fields">${fields.map(([key,label,fallback]) => `<label class="field"><span>${label}</span><input type="number" step="any" min="0" ${key === 'duration_s' || key === 'dt_s' ? 'max="60"' : ''} required data-case="${i}" data-condition="${key}" value="${esc(c.conditions?.[key] ?? fallback)}" aria-label="${esc(c.id+' '+label)}"></label>`).join('')}</div>
          ${boundaryEditor(c,i)}
          <label class="field"><span>参数覆盖（JSON 对象）</span><textarea data-case="${i}" data-parameters spellcheck="false" rows="2" aria-label="${esc(c.id)} 参数覆盖">${esc(c.parametersText ?? JSON.stringify(c.conditions?.parameters || {},null,2))}</textarea></label>
          <div class="table-wrap"><table style="table-layout:fixed;width:100%"><colgroup><col style="width:34%"><col style="width:18%"><col style="width:18%"><col style="width:18%"><col style="width:12%"></colgroup><thead><tr><th>结果变量</th><th>预期值</th><th>绝对容差</th><th>相对容差</th><th></th></tr></thead><tbody>${c.assertions.map((a,j) => `<tr data-suite-assertion="${j}">
            <td><input style="min-width:0;width:100%" list="module-assertion-keys" required maxlength="256" data-case="${i}" data-assertion="${j}" data-expectation="key" value="${esc(a.key)}" aria-label="结果变量"></td>
            ${[['expected','预期值'],['absolute_tolerance','绝对容差'],['relative_tolerance','相对容差']].map(([key,label]) => `<td><input style="min-width:0;width:100%" type="number" step="any" ${key === 'expected' ? '' : 'min="0"'} required data-case="${i}" data-assertion="${j}" data-expectation="${key}" value="${esc(a[key] ?? 0)}" aria-label="${label}"></td>`).join('')}
            <td><button type="button" class="btn small" data-suite-action="remove-assertion" data-case="${i}" data-assertion="${j}" aria-label="删除预期值">删除</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted">尚未设置预期值。</td></tr>'}</tbody></table></div>
          <button type="button" class="btn small" data-suite-action="add-assertion" data-case="${i}" ${c.assertions.length >= 256 ? 'disabled' : ''}>添加预期值</button></div></section>`).join('')}</div>
        <button type="button" class="btn" data-suite-action="add-case" ${draft.length >= 64 ? 'disabled' : ''}>添加工况</button>`;
    }
    container.addEventListener('input', event => {
      const d = event.target.dataset, c = draft[Number(d.case)];
      if (!c) return;
      if ('caseId' in d) c.id = event.target.value;
      if (d.condition) { c.conditions ||= {}; c.conditions[d.condition] = event.target.value; }
      if (d.boundaryField) c.conditions.channel_boundaries[d.boundary][d.boundaryField] = event.target.value;
      if ('parameters' in d) c.parametersText = event.target.value;
      if (d.expectation) c.assertions[Number(d.assertion)][d.expectation] = event.target.value;
    });
    container.addEventListener('click', event => {
      const button = event.target.closest('[data-suite-action]');
      if (!button || !container.contains(button)) return;
      event.preventDefault(); event.stopPropagation();
      const d = button.dataset, c = draft[Number(d.case)];
      if (d.suiteAction === 'add-case' && draft.length < 64) {
        let n = draft.length + 1; while (draft.some(c => c.id === `case_${n}`)) n++;
        draft.push({id:`case_${n}`, conditions:{duration_s:.2,dt_s:.1}, assertions:[]});
      }
      if (d.suiteAction === 'remove-case' && draft.length > 1) draft.splice(Number(d.case),1);
      if (d.suiteAction === 'add-boundary' && c) {
        c.conditions ||= {}; c.conditions.channel_boundaries ||= {};
        c.conditions.channel_boundaries[d.boundary] = {
          inlet_pressure_pa:c.conditions.inlet_pressure_pa ?? 250000,
          outlet_pressure_pa:c.conditions.outlet_pressure_pa ?? 120000,
          inlet_temperature_k:c.conditions.temperature_k ?? 293.15,
          outlet_temperature_k:c.conditions.temperature_k ?? 293.15,
          fluid:clone(c.conditions.fluid || {fluid:'Water'}),
        };
      }
      if (d.suiteAction === 'remove-boundary' && c?.conditions?.channel_boundaries) delete c.conditions.channel_boundaries[d.boundary];
      if (d.suiteAction === 'add-assertion' && c.assertions.length < 256) c.assertions.push({key:keys[0] || '', expected:0, absolute_tolerance:0, relative_tolerance:0});
      if (d.suiteAction === 'remove-assertion') c.assertions.splice(Number(d.assertion),1);
      render();
    });
    render();
    return {read() {
      if (draft.length < 1 || draft.length > 64) throw Error('测试组合须包含 1 至 64 个工况。');
      const ids = new Set();
      return draft.map(c => {
        const id = c.id.trim();
        if (!/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id) || ids.has(id)) throw Error('工况标识须以字母开头，最多 81 个字符，仅使用字母、数字、下划线或短横线，不能重复。');
        ids.add(id);
        const conditions = clone(c.conditions || {});
        for (const [key,label,fallback] of fields) conditions[key] = number(conditions[key] ?? fallback, `${id} ${label}`, 0, true);
        if (conditions.duration_s > 60 || conditions.dt_s > 60) throw Error(`${id} 时长和步长最多为 60 秒。`);
        if (conditions.duration_s > 2000 * conditions.dt_s) throw Error(`${id} 独立测试最多 2001 帧，请减小时长或增大步长。`);
        for (const [channel,boundary] of Object.entries(conditions.channel_boundaries || {})) {
          if (!enabledChannels.some(item => item.id === channel)) throw Error(`${id} 独立边界引用了不存在或未启用的通路 ${channel}，请清除该覆盖。`);
          for (const [key,label,fallback] of boundaryFields) boundary[key] = number(boundary[key] ?? fallback, `${id} ${channel} ${label}`, 0, true);
        }
        let parameters;
        try { parameters = JSON.parse(c.parametersText ?? JSON.stringify(conditions.parameters || {})); }
        catch { throw Error(`${id} 参数覆盖必须是有效的 JSON 对象。`); }
        if (!parameters || typeof parameters !== 'object' || Array.isArray(parameters)) throw Error(`${id} 参数覆盖必须是 JSON 对象。`);
        conditions.parameters = parameters;
        const assertionKeys = new Set();
        if (c.assertions.length > 256) throw Error(`${id} 最多配置 256 条预期值。`);
        const assertions = c.assertions.map(a => {
          const key = a.key.trim();
          if (!key || /\s/u.test(key) || [...key].length > 256 || assertionKeys.has(key)) throw Error(`${id} 结果变量须为 1 至 256 个非空白字符，不能重复。`);
          assertionKeys.add(key);
          return {key, expected:number(a.expected,'预期值'), absolute_tolerance:number(a.absolute_tolerance ?? 0,'绝对容差',0), relative_tolerance:number(a.relative_tolerance ?? 0,'相对容差',0)};
        });
        return {id,conditions,assertions};
      });
    }};
  }
  function summary(data) {
    return data.cases.map(c => {
      const lines = [`${c.passed?'✓':'✗'} ${c.id} · ${c.level}${c.passed?' 通过':' 失败'}`];
      for (const a of c.assertions || []) lines.push(`  ${a.passed?'✓':'✗'} ${a.key} · 预期 ${a.expected} · 实际 ${a.actual ?? '不可用'} · 绝对误差 ${a.absolute_error ?? '不可用'} · 允许误差 ${a.allowed_error ?? '不可用'}${a.passed?'':' · '+a.message}`);
      for (const d of c.diagnostics) lines.push(`  ${d.message}`);
      return lines.join('\n');
    }).join('\n');
  }
  return {cases,mount,summary};
})();
