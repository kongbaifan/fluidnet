/* Device detail presentation. Drafts and apply transactions stay in project-state / engine-client. */
window.createDevicePanel = deps => {
  const {moduleOf,ownerOfInstance,instanceVariablesBody,esc,icon,btn,ibtn,badge,number,option,
    pendingCount,model,paramDefs,deviceParamSpecs,sameValue,parameterValueText,PARAM_TYPE_LABELS,
    DOMAINS,links,project,getState,panelRow,parameterKey,observation,observationButton} = deps;
function deviceExtraParamRows(n, m, selected=null, readonly=false) {
  const specs = (selected||deviceParamSpecs(n)).filter(p => p.value_type !== 'number');
  if (!specs.length) return '';
  const rows = specs.map(p => {
    const draft = n.draft[p.id]===undefined?p.default:n.draft[p.id], current = n.params[p.id]===undefined?p.default:n.params[p.id], edited = !sameValue(draft, current);
    const text = parameterValueText(draft, p.value_type);
    const editor = p.value_type === 'boolean'
      ? `<label class="check-label"><input type="checkbox" data-instance-param="${esc(p.id)}" data-config-readonly="${readonly}" data-param-type="boolean" data-id="${n.id}" aria-label="${esc(n.id)} ${esc(p.label)}草稿" ${draft === true ? 'checked' : ''}>启用</label>`
      : p.value_type === 'curve'
        ? `<textarea class="cell-input mono" rows="3" data-instance-param="${esc(p.id)}" data-config-readonly="${readonly}" data-param-type="curve" data-id="${n.id}" aria-label="${esc(n.id)} ${esc(p.label)}草稿">${esc(text)}</textarea>`
        : `<input type="text" data-instance-param="${esc(p.id)}" data-config-readonly="${readonly}" data-param-type="text" data-id="${n.id}" value="${esc(text)}" aria-label="${esc(n.id)} ${esc(p.label)}草稿" maxlength="200">`;
    return `<div class="parameter-row${edited ? ' edited' : ''}"><div class="param-title"><div class="parameter-label-actions"><strong>${esc(p.label)}</strong>${badge(PARAM_TYPE_LABELS[p.value_type] || p.value_type)}</div><small>当前 ${esc(parameterValueText(current, p.value_type)) || '—'}</small></div>${editor}</div>`;
  }).join('');
  if(selected)return rows;
  return `<div class="row spread" style="margin-top:18px"><strong>其他参数</strong>${badge('非数值类型')}</div><p class="muted" style="font-size:12px;margin:0 0 10px">布尔、文本和曲线参数按各自类型编辑；曲线使用 JSON 点对数组。</p>${rows}`;
}
function panelConfig(n,m) {return window.FluidNetPanelLayout?.resolved(m,deviceParamSpecs(n))||{layout:null,warning:''};}
function configuredFields(n,m,overview=false) {
  const {layout}=panelConfig(n,m);if(!layout)return null;
  const specs=deviceParamSpecs(n),selected=new Set(layout.parameters.map(p=>p.id));
  const rows=[...layout.parameters];
  if(!overview)for(const spec of specs)if(!selected.has(spec.id))rows.push({id:spec.id,widget:window.FluidNetPanelLayout.widgets(spec)[0],group:'其他参数',order:1000});
  return window.FluidNetPanelLayout.groups(rows).map(group=>`<section data-panel-parameter-group="${esc(group.name)}"><h3>${esc(group.name||'参数')}</h3>${group.items.map(item=>{
    const spec=specs.find(p=>p.id===item.id),f=paramDefs(n).find(f=>f[0]===item.id);
    return f?parameterRow(n,m,f,item.widget):deviceExtraParamRows(n,m,[spec],item.widget==='display');
  }).join('')}</section>`).join('');
}
function floatBody(f, n) {
  const m = moduleOf(n);
  if (f.tab === 'variables') return instanceVariablesBody(f, n);
  if (f.tab === 'overview' || f.tab === 'results') return overview(n);
  if (f.tab === 'connections') return `<div class="stack">${m.ports.map(port => {
    const edge=links.atPort(project(),n.id,port.id),remote=edge&&(edge[1]===n.id?edge.slice(3,5):edge.slice(1,3)),destination=remote&&links.locate(project(),remote[0]);
    const cross=destination&&destination.page.id!==links.locate(project(),n.id).page.id;
    return `<div class="list-row" style="padding:10px 0"><div class="grow"><strong>${esc(port.label)}</strong><small>${esc(DOMAINS[port.domain].label)} · ${edge?esc((cross?destination.page.name+' · ':'')+remote.join(':')):'未连接'}</small></div>${cross?ibtn('jump-page-link','跳到连接设备','ArrowUpRight',`data-id="${esc(edge[0])}" data-node="${esc(remote[0])}"`)+btn('edit-page-link','修改','Pencil',`data-id="${esc(edge[0])}"`,'small'):''}${edge?btn('delete-edge','断开','X',`data-id="${esc(edge[0])}"`,'small'):btn('add-page-link','跨页连接','ArrowRightLeft',`data-node="${esc(n.id)}" data-port="${esc(port.id)}"`,'small')}</div>`;
  }).join('')}</div>`;
  return `<label class="field"><span>设备名称</span><input data-instance-name="${n.id}" value="${esc(n.name)}" aria-label="${n.id} 设备名称" maxlength="50"></label><div class="field" style="margin-top:13px"><span>选择型号 → 进入待应用草稿</span><select data-instance-model="${n.id}" aria-label="${n.id} 设备型号">${option('', '自定义参数', n.draftModelId || n.modelId)}${getState().models.filter(v => v.moduleId === m.id && !v.archived).map(v => option(v.id, v.name + ' · v' + v.version, n.draftModelId || n.modelId)).join('')}</select></div><div class="row spread" style="margin-top:12px"><strong>常用参数</strong><span class="badge ${pendingCount(n) ? 'warn' : 'good'}" data-pending-for="${n.id}">${pendingCount(n)} 项待应用</span></div>${configuredFields(n,m)??(paramDefs(n).filter(f => m.variables.find(v => v.param === f[0])?.display !== false).map(f => parameterRow(n,m,f)).join('')+deviceExtraParamRows(n,m))}${panelConfig(n,m).warning?`<p class="notice">${esc(panelConfig(n,m).warning)}</p>`:''}<div class="row wrap" style="margin-top:16px">${btn('device-definition', '完整模块定义', 'Box', `data-id="${n.id}"`, 'small ghost')}${btn('configure-device-panel','配置此项目面板','Settings2',`data-id="${n.id}"`,'small')}${btn('equipment-selection', '设备选型', 'SlidersHorizontal', `data-id="${n.id}"`, 'small')}${btn('equipment-provenance','型号设计资料','FileText',`data-id="${n.id}"`,'small')}${deviceParamSpecs(n).some(p=>/^(Coil_)?air_side_ua_w_k$/.test(p.id))?btn('coil-geometry-design','盘管几何设计','Ruler',`data-id="${n.id}"`,'small'):''}${btn('save-instance-model', '保存为型号', 'Database', `data-id="${n.id}"`, 'small')}</div>`;
}
function quickFieldMarkup(n, m, f, widget) {
  if (!widget && m.quickParam !== f[0]) return '';
  const kind=widget||m.quickType;
  if (kind === 'slider') return `<input type="range" data-instance-param="${f[0]}" data-id="${n.id}" min="${f[3]}" max="${f[4]}" step="${f[5]}" value="${n.draft[f[0]]}" aria-label="${n.id} ${f[1]}滑块">`;
  if (kind === 'switch') return `<label class="check-label" style="margin-top:6px"><input type="checkbox" data-instance-switch="${f[0]}" data-id="${n.id}" ${n.draft[f[0]] > f[3] ? 'checked' : ''}>切换 ${f[3]} / ${f[4]} ${esc(f[2])}</label>`;
  return '';
}
function parameterRow(n,m,f,widget) { return `<div class="parameter-row${n.draft[f[0]] !== n.params[f[0]] ? ' edited' : ''}"><div class="param-title"><div class="parameter-label-actions"><strong>${f[1]}</strong>${ibtn('device-variables', '查看 ' + f[1] + ' 的全部变量', 'Table2', `data-id="${n.id}" data-variable="param:${f[0]}"`)}</div><small>已应用设置 ${number(n.params[f[0]], f[0] === 'opening' ? 0 : 2)} ${f[2]}</small><small data-device-actual-param="${esc(f[0])}"></small>${quickFieldMarkup(n, m, f, widget)}</div><input type="number" step="any" min="${f[3]}" max="${f[4]}" data-config-readonly="${widget==='display'}" data-instance-param="${f[0]}" data-id="${n.id}" value="${n.draft[f[0]]}" aria-label="${n.id} ${f[1]}草稿" ${widget==='display'||(!widget && m.quickParam===f[0] && m.quickType==='display')?'readonly':''}><span class="muted">${f[2]}</span></div>`; }

function controlOwner(n, id) {
  const owner=ownerOfInstance(n), variable=moduleOf(n).variables.find(v=>v.param===id);
  // Script edits apply to the next run; ownership belongs to the accepted run snapshot.
  let frozen;
  if(owner.run.live && owner.run.parameterKey) { try { frozen=JSON.parse(owner.run.parameterKey); } catch { /* Legacy run without a snapshot. */ } }
  const key=variable && observation(n,variable).canonicalKey;
  const parameter=key?.split('.param.')[1] || id;
  const pid=(frozen?.controllers||owner.controllers||[]).find(c=>c.instance_id===n.id && c.parameter_id===parameter);
  if(pid)return `PID ${pid.id} · ${pid.mode==='manual'?'手动输出':'自动控制'}`;
  const script=(frozen?.controls||owner.controlPrograms||owner.controlScripts||[]).find(p=>p.enabled && p.language!=='legacy' && (p.outputs||[]).includes(`${n.id}.param.${parameter}`));
  return script ? `控制脚本 ${script.name||script.id}` : '';
}
function source(n) {
  const owner=ownerOfInstance(n),run=owner.run,row=panelRow(run);
  if(!row)return {text:'尚未计算 · 运行或单步查看结果',tone:''};
  const stale=!run.parameterKey || run.parameterKey!==parameterKey(owner);
  const title=stale?'上次计算结果 · 已过期':'当前计算结果';
  return {text:`${title} · t = ${number(row.t,2)} s${row.partial?' · 部分采样':''}${row.t!==run.time?' · 最近完整帧':''}`,tone:stale?'warn':'good'};
}
function metrics(n) {
  const m=moduleOf(n),variables=m.variables,layout=panelConfig(n,m).layout;
  if(layout)return [...layout.results].sort((a,b)=>a.order-b.order).map(item=>variables.find(v=>v.id===item.id)).filter(Boolean);
  const rank=v=>/cooling_power|heating_power/.test(v.canonicalId||'')?0:/power_w|head_m|mass_flow/.test(v.canonicalId||'')?1:v.origin==='runtime'?2:v.id.endsWith(':FLOW')?3:4;
  const seen=new Set();
  return variables.filter(v=>v.origin==='runtime'&&v.display!==false || v.origin==='port'&&/:(FLOW|TEMP)$/.test(v.id))
    .sort((a,b)=>rank(a)-rank(b)).filter(v=>{const key=observation(n,v).canonicalKey;if(!key||seen.has(key))return false;seen.add(key);return true;}).slice(0,4);
}
function metricValue(n,v) {
  const row=panelRow(ownerOfInstance(n).run),binding=observation(n,v);
  if(!row)return '—';
  const raw=row.canonical?.[binding.canonicalKey];
  const value=row.canonical ? (typeof raw==='boolean'?raw:Number.isFinite(raw)?raw/(binding.canonicalScale||1)+(binding.canonicalOffset||0):null)
    : row.variableValues?.[n.id+':'+v.id];
  return typeof value==='boolean'?(value?'是':'否'):Number.isFinite(value)?number(value,3):'—';
}
function metricMarkup(n,v) {return `<div class="device-metric" data-device-metric="${esc(v.id)}"><div class="row spread"><small>${esc(v.label)}</small>${observationButton(n,v)}</div><strong>${metricValue(n,v)}</strong><span>${esc(v.unit)}</span></div>`;}
function resultMarkup(n,m) {
  const {layout,warning}=panelConfig(n,m);
  if(!layout)return `${warning?`<p class="notice">${esc(warning)}</p>`:''}<div class="device-metrics">${metrics(n).map(v=>metricMarkup(n,v)).join('')||'<p class="muted">此设备没有可显示的计算变量。</p>'}</div>`;
  return window.FluidNetPanelLayout.groups(layout.results).map(g=>`<section data-panel-result-group="${esc(g.name)}"><h3>${esc(g.name||'运行结果')}</h3><div class="device-metrics">${g.items.map(item=>metricMarkup(n,m.variables.find(v=>v.id===item.id))).join('')}</div></section>`).join('');
}
function overview(n) {
  const m=moduleOf(n),result=source(n),defs=paramDefs(n).filter(f=>m.variables.find(v=>v.param===f[0])?.display!==false);
  const preferred=defs.find(f=>/setpoint|opening|speed|power/.test(f[0])) || defs.find(f=>f[0]===m.quickParam) || defs[0];
  return `<div class="device-overview" data-device-overview="${esc(n.id)}"><div class="device-identity"><span class="object-icon">${icon(m.icon)}</span><div><strong>${esc(m.name)}</strong><small>${esc(model(n.modelId)?.name||'自定义参数')} · v${esc(m.version||1)}</small></div></div>
    <div class="device-result-source ${result.tone}" data-device-result-source>${esc(result.text)}</div>
    ${resultMarkup(n,m)}
    <div class="device-operation"><div class="row spread"><h3>常用操作</h3>${btn('device-panel-tab','全部参数','SlidersHorizontal',`data-id="${n.id}" data-value="parameters"`,'small ghost')}</div>${configuredFields(n,m,true)??(preferred?parameterRow(n,m,preferred):'<p class="muted">此设备没有可调参数。</p>')}<small class="muted">修改保留为草稿，预览确认后生效。</small></div>
    <div class="device-port-summary"><h3>端口连接</h3>${m.ports.map(p=>{const e=links.atPort(ownerOfInstance(n),n.id,p.id);return `<div class="row spread"><span>${esc(p.label)}</span><small>${e?'已连接':'未连接'}</small></div>`;}).join('')}${btn('device-panel-tab','查看连接','Cable',`data-id="${n.id}" data-value="connections"`,'small ghost')}</div></div>`;
}
function refresh(shell,n) {
  const result=source(n);
  for(const el of shell.querySelectorAll('[data-device-result-source]')){el.textContent=result.text;el.className='device-result-source '+result.tone;}
  for(const el of shell.querySelectorAll('[data-device-metric]')){const v=moduleOf(n).variables.find(v=>v.id===el.dataset.deviceMetric);if(v)el.querySelector('strong').textContent=metricValue(n,v);}
  const live=!!ownerOfInstance(n).run.live;
  for(const el of shell.querySelectorAll('[data-device-actual-param]')) {
    const v=moduleOf(n).variables.find(v=>v.param===el.dataset.deviceActualParam);
    el.textContent=panelRow(ownerOfInstance(n).run) && v ? `采样值 ${metricValue(n,v)} ${v.unit||''}` : '';
  }
  for(const row of shell.querySelectorAll('.parameter-row')) {
    const input=row.querySelector('[data-instance-param],[data-instance-switch]');if(!input)continue;
    const id=input.dataset.instanceParam||input.dataset.instanceSwitch,owner=controlOwner(n,id);
    let note=row.querySelector('[data-parameter-owner]');
    if(!note){note=document.createElement('small');note.dataset.parameterOwner='';row.querySelector('.param-title')?.append(note);}
    note.textContent=owner ? (live?'由 ':'下次运行由 ')+owner+' 接管' : '';
    const spec=deviceParamSpecs(n).find(p=>p.id===id);
    for(const field of row.querySelectorAll('[data-instance-param],[data-instance-switch]'))field.disabled=field.dataset.configReadonly==='true'||field.readOnly===true||spec?.writable===false||live&&(!!owner||spec?.runtime===false);
  }
}
  return {body:floatBody, refresh};
};
