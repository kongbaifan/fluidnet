/* Cold-storage case: creation, indicators, scenarios, schedule, unit bench and reports.
   All result values come from the shared engine run; this file only arranges inputs and views. */
window.createColdStorageUI = function (ui) {
  const state=ui.state, engine=ui.engine, {esc,btn,openDialog,msg}=ui;
  const IDEAL='cold-room-ideal-v1', ROOM='cold-room-minus18-v1';
  // Mirrors refrigeration/examples.py ROOM_SCENARIO_DURATIONS (cases/cold-storage/single-room-minus18/scenarios.json).
  const DURATIONS={'A-S01':21600,'A-S02':21600,'A-S03':28800,'A-S04':28800,'A-S05-onoff':86400,'A-S05-variable':86400,'A-S06':86400,'A-S07':21600};
  const MODES=['制冷','融霜加热','滴水'];
  const EVENT_TYPES=[['door_heat','开门热负荷'],['goods_addition','货物入库'],['ambient_temperature','室外温度变化'],['electric_defrost','电融霜']];
  let eventDraft=null;
  const raw=(p,key)=>{const rows=p.run.history;for(let i=rows.length-1;i>=0;i--){const v=rows[i].canonical?.[key];if(v!==undefined)return v;}return undefined;};
  const fmt=(p,key,scale=1,offset=0,digits=3)=>{const v=raw(p,key);return typeof v==='number'?(v/scale+offset).toFixed(digits):'—';};
  const lastRun=p=>p.run.source==='engine'&&p.run.id&&['completed','failed','stopped'].includes(p.run.status)?p.run.id:null;
  const idle=p=>{if(['running','solving'].includes(p.run.status)||p.run.live&&p.run.runId)throw Error('请先停止当前运行。');};
  const display=(spec,value)=>spec?.unit?value/spec.unit.display_scale+spec.unit.display_offset:value;
  const option=(value,label,selected)=>`<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`;
  const field=(name,label,value,attrs='')=>`<label class="field"><span>${esc(label)}</span><input name="${name}" aria-label="${esc(label)}" value="${esc(value??'')}" ${attrs}></label>`;

  async function fetchExample(name){
    const response=await fetch('/api/v1/examples/'+name,{headers:engine().authHeaders()});
    if(!response.ok)throw Error('无法读取冷库案例');
    return response.json();
  }
  function nodesOf(model,positions){
    return model.instances.map(n=>{
      const definition=model.modules.find(m=>m.id===n.module_id);
      const params=Object.fromEntries(definition.parameters.map(spec=>[spec.id,display(spec,n.parameters[spec.id]??spec.default)]));
      const [x,y]=positions[n.id]||[430,215];
      return ui.makeInstance(n.id,n.module_id,n.name,x,y,params);
    });
  }
  function charts(p,bindings){
    for(const [nodeId,variableId,label,unit,canonicalKey,canonicalScale,canonicalOffset] of bindings)
      state().charts.extra.push({id:ui.uid('cold-chart'),projectId:p.id,nodeId,variableId,label,unit,canonicalKey,canonicalScale,canonicalOffset});
    ui.ui().showChart=true;ui.ui().workbenchChart=state().charts.extra.find(c=>c.projectId===p.id).id;
  }
  async function create(){
    if(!engine().catalog||!engine().health?.capabilities?.cold_store_cycle)throw Error('请等待支持冷库案例的计算服务连接。');
    if(state().projects.length>=20)throw Error('最多保存 20 个项目');
    const model=await fetchExample('cold-storage-room');
    const pg={id:'main',name:'库房 · 冷风机 · 机组',zoom:1,pan:[0,0],nodes:nodesOf(model,{CU1:[250,215],AC1:[520,215],ROOM1:[790,215]}),
      edges:model.connections.map(c=>[c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id])};
    const p=ui.makeProject(ui.uid('project'),model.name,model.description,pg);
    const script=model.control_scripts[0], specs=id=>model.modules.find(m=>m.id===model.instances.find(n=>n.id===id).module_id).parameters;
    Object.assign(p,{caseId:ROOM,fluid:model.fluid.fluid,events:model.events,control:script.source,controlLanguage:'python',controlEnabled:true,
      controlInputs:script.inputs.join(', '),controlOutputs:script.outputs.join(', ')});
    p.controlConfig={...(p.controlConfig||{}),name:'库温温控（回差启停 / PI 容量）',period:script.sample_s*1000};
    p.scenarios=model.scenarios.map(s=>({id:s.id,name:s.name,events:s.events,overrides:Object.fromEntries(Object.entries(s.overrides).map(([id,values])=>
      [id,Object.fromEntries(Object.entries(values).map(([key,value])=>[key,display(specs(id).find(x=>x.id===key),value)]))]))}));
    p.activeScenarioId='A-S01';
    p.solver={...p.solver,mode:'dynamic',duration:DURATIONS['A-S01'],dt:30,executionMode:'fast',historyWindow:DURATIONS['A-S01']/30+1};
    state().projects.push(p);ui.normalizeState();
    charts(p,[['ROOM1','runtime:state.temperature_k','库温','°C','ROOM1.state.temperature_k',1,-273.15],
      ['ROOM1','runtime:state.goods_temperature_k','货温','°C','ROOM1.state.goods_temperature_k',1,-273.15],
      ['CU1','runtime:cooling_power_w','机组制冷量','kW','CU1.cooling_power_w',1000,0],
      ['CU1','runtime:electric_power_w','压缩机电功率','kW','CU1.electric_power_w',1000,0],
      ['CU1','runtime:evaporating_temperature_k','蒸发温度','°C','CU1.evaporating_temperature_k',1,-273.15],
      ['CU1','runtime:condensing_temperature_k','冷凝温度','°C','CU1.condensing_temperature_k',1,-273.15],
      ['CU1','runtime:state.electric_energy_j','累计压缩机电量','kWh','CU1.state.electric_energy_j',3600000,0]]);
    ui.markDirty(p);ui.persist();ui.openProject(p.id);
    msg('冷库案例已创建：选择工况后运行，结果可导出报告与 CSV。');
  }
  // [selector key, label, canonical key, scale, offset, digits]
  const METRICS=[['temperature','库温 · °C','ROOM1.state.temperature_k',1,-273.15,2],['goods','货温 · °C','ROOM1.state.goods_temperature_k',1,-273.15,2],
    ['running','机组 · 运行','CU1.state.running',1,0,0],['capacity','实际容量 · %','CU1.actual_capacity_ratio',.01,0,0],
    ['cooling','制冷量 · kW','CU1.cooling_power_w',1000,0,2],['power','压缩机电功率 · kW','CU1.electric_power_w',1000,0,2],
    ['evaporating','蒸发温度 · °C','CU1.evaporating_temperature_k',1,-273.15,1],['condensing','冷凝温度 · °C','CU1.condensing_temperature_k',1,-273.15,1],
    ['cop','系统 COP','CU1.system_cop',1,0,2],['energy','累计压缩机电量 · kWh','CU1.state.electric_energy_j',3600000,0,2],
    ['starts','开机次数','CU1.state.starts',1,0,0],['above','保温期超温 · min','ROOM1.state.service_time_above_alarm_s',60,0,1]];
  const modeText=p=>{const v=raw(p,'AC1.state.mode');return typeof v==='number'?MODES[v]||'—':'—';};
  function warnings(p){
    const seen=new Map();
    for(const row of p.run.history.slice(-60))for(const d of row.diagnostics||[])if(d.severity!=='info'&&!seen.has(d.code))seen.set(d.code,d.message);
    return [...seen.values()].slice(0,3);
  }
  function scenarioName(p){return (p.scenarios||[]).find(s=>s.id===p.activeScenarioId)?.name||'基础模型';}
  function markupIdeal(p){
    return `<section class="panel cold-storage-summary" aria-label="冷库运行指标"><div class="panel-head"><strong>−18°C 单库房 · A1</strong><span>理想冷源</span></div><div class="panel-body"><p>库房热容、围护漏热与温度控制。冷源按指定容量供冷；完整制冷循环案例请在项目页重新创建“−18°C 冷库案例”。</p><div class="metric-row"><div class="metric"><span>库温 · °C</span><strong data-cold-temperature>${fmt(p,'ROOM1.state.temperature_k',1,-273.15)}</strong></div><div class="metric"><span>冷却功率 · kW</span><strong data-cold-power>${fmt(p,'COLD1.cooling_power_w',1000)}</strong></div><div class="metric"><span>累计冷量 · kWh</span><strong data-cold-energy>${fmt(p,'COLD1.state.cooling_energy_j',3600000)}</strong></div></div></div></section>`;
  }
  function markup(p){
    if(p.caseId===IDEAL)return markupIdeal(p);
    if(p.caseId!==ROOM)return '';
    const run=lastRun(p), disabled=run?'':'disabled';
    return `<section class="panel cold-storage-summary cold-room" aria-label="冷库运行指标"><div class="panel-head"><strong>−18°C 冻结物储藏库</strong><span data-cold-scenario>${esc(scenarioName(p))}</span><span class="push"></span>${btn('cs-scenarios','工况','ListChecks','','small')}${btn('cs-schedule','负荷日程','Clock3','','small')}${btn('cs-bench','机组工作点','Gauge','','small')}${btn('cs-report','运行报告','FileText',disabled,'small')}${btn('cs-csv','CSV','Download',disabled,'small')}${btn('cs-compare','策略对照','ArrowRightLeft','','small')}</div><div class="panel-body"><div class="metric-row cold-metrics">${METRICS.map(([id,label,key,scale,offset,digits])=>`<div class="metric"><span>${label}</span><strong data-cold-${id}>${fmt(p,key,scale,offset,digits)}</strong></div>`).join('')}<div class="metric"><span>冷风机</span><strong data-cold-mode>${modeText(p)}</strong></div></div><div data-cold-warnings>${warnings(p).map(w=>`<div class="notice warn">${esc(w)}</div>`).join('')}</div></div></section>`;
  }
  function refresh(p){
    if(p.caseId===IDEAL){
      for(const [selector,key,scale,offset] of [['[data-cold-temperature]','ROOM1.state.temperature_k',1,-273.15],
        ['[data-cold-power]','COLD1.cooling_power_w',1000,0],['[data-cold-energy]','COLD1.state.cooling_energy_j',3600000,0]]){
        const element=document.querySelector(selector);if(element)element.textContent=fmt(p,key,scale,offset);
      }
      return;
    }
    if(p.caseId!==ROOM)return;
    for(const [id,,key,scale,offset,digits] of METRICS){const element=document.querySelector(`[data-cold-${id}]`);if(element)element.textContent=fmt(p,key,scale,offset,digits);}
    const mode=document.querySelector('[data-cold-mode]');if(mode)mode.textContent=modeText(p);
    const box=document.querySelector('[data-cold-warnings]');if(box)box.innerHTML=warnings(p).map(w=>`<div class="notice warn">${esc(w)}</div>`).join('');
    const run=lastRun(p);for(const action of ['cs-report','cs-csv']){const b=document.querySelector(`[data-action="${action}"]`);if(b)b.disabled=!run;}
  }
  function scenarios(p){
    const rows=(p.scenarios||[]).map(s=>`<tr><td>${esc(s.name)}</td><td>${DURATIONS[s.id]?(DURATIONS[s.id]/3600)+' h':'—'}</td><td>${s.events?s.events.length:'沿用项目'}</td><td>${btn('cs-run-scenario','运行','Play',`data-scenario="${esc(s.id)}"`,'small primary')}</td></tr>`).join('');
    openDialog('冷库工况','选择工况运行：时长按案例设定，后台快算并保留全部帧以便导出报告。',`<table class="data-table cold-table"><thead><tr><th>工况</th><th>时长</th><th>事件</th><th></th></tr></thead><tbody>${rows}</tbody></table><p class="muted">A-S05 的两种控制方式使用同一日程；运行后用“策略对照”生成公平性检查与对照报告。</p>`,null,'',true);
  }
  function runScenario(p,id){
    idle(p);
    const duration=DURATIONS[id]||p.solver.duration;
    p.activeScenarioId=id;p.solver={...p.solver,mode:'dynamic',duration,executionMode:'fast',historyWindow:Math.min(20001,Math.ceil(duration/p.solver.dt)+1)};
    ui.markDirty(p);ui.persist();ui.closeDialog();ui.render();
    return engine().command('project','run',p.id);
  }
  // The schedule edited is the active scenario's own list when it has one, otherwise the project's.
  function scheduleOwner(p){const s=(p.scenarios||[]).find(s=>s.id===p.activeScenarioId);return s&&Array.isArray(s.events)?{label:'工况 '+s.name,list:s.events,scenario:s}:{label:'项目基础日程',list:p.events||=[],scenario:null};}
  const describe=e=>({door_heat:`${(e.heat_w/1000).toFixed(2)} kW × ${(e.duration_s/60).toFixed(1)} min`,goods_addition:`${e.mass_kg} kg · ${(e.temperature_k-273.15).toFixed(2)} °C`,
    ambient_temperature:`${(e.temperature_k-273.15).toFixed(2)} °C`,electric_defrost:'按冷风机融霜参数'})[e.type];
  function eventRows(){
    return eventDraft.list.map((e,i)=>`<tr><td>${esc(e.id)}</td><td>${esc(EVENT_TYPES.find(t=>t[0]===e.type)[1])}</td><td>${(e.time_s/3600).toFixed(3)} h</td><td>${esc(describe(e))}</td><td>${btn('cs-remove-event','删除','Trash2',`data-index="${i}"`,'small')}</td></tr>`).join('')||'<tr><td colspan="5" class="muted">没有事件。</td></tr>';
  }
  function schedule(p){
    idle(p);
    const owner=scheduleOwner(p);eventDraft={projectId:p.id,list:JSON.parse(JSON.stringify(owner.list))};
    openDialog('负荷日程',`编辑：${owner.label}。事件按仿真时间执行，同一时刻先执行事件、再控制采样、再推进物理。`,
      `<table class="data-table cold-table"><thead><tr><th>ID</th><th>类型</th><th>时刻</th><th>数值</th><th></th></tr></thead><tbody id="cs-events">${eventRows()}</tbody></table>
      <div class="fields"><label class="field"><span>类型</span><select id="cs-event-type" aria-label="事件类型">${EVENT_TYPES.map(([v,l])=>option(v,l,'door_heat')).join('')}</select></label>
      ${field('cs-time','时刻 · h','2','id="cs-time" type="number" step="any" min="0"')}${field('cs-duration','开门时长 · min','10','id="cs-duration" type="number" step="any" min="0"')}
      ${field('cs-heat','开门热负荷 · kW','5','id="cs-heat" type="number" step="any" min="0"')}${field('cs-mass','入库质量 · kg','500','id="cs-mass" type="number" step="any" min="0"')}
      ${field('cs-temperature','货温或室外温度 · °C','-12','id="cs-temperature" type="number" step="any"')}</div>
      <p class="muted">开门用时长与热负荷；入库用质量与货温（须在冻结货物模型范围内）；室外温度变化用温度；电融霜按冷风机参数执行。</p>${btn('cs-add-event','加入事件','Plus')}`,
      ()=>{
        const target=state().projects.find(x=>x.id===eventDraft.projectId);idle(target);
        const candidate=JSON.parse(JSON.stringify(target)),list=eventDraft.list,current=scheduleOwner(target);
        if(current.scenario)candidate.scenarios.find(s=>s.id===current.scenario.id).events=list;else candidate.events=list;
        const key=ui.projectKey(target);
        engine().validateCandidate(candidate).then(result=>{
          if(!result.valid)throw Error(result.diagnostics.filter(d=>d.severity==='error').map(d=>d.message).join('；'));
          if(key!==ui.projectKey(target))throw Error('校验期间项目发生变化，请重新编辑日程');
          if(current.scenario)current.scenario.events=list;else target.events=list;
          ui.markDirty(target);ui.persist();ui.render();msg('日程已校验并应用，保存项目后保留。');
        }).catch(error=>msg(error.message,true));
      },'校验并应用',true);
  }
  function addEvent(){
    const value=id=>Number(document.getElementById(id).value),type=document.getElementById('cs-event-type').value;
    const event={id:ui.uid('event'),type,time_s:value('cs-time')*3600};
    if(type==='door_heat')Object.assign(event,{duration_s:value('cs-duration')*60,heat_w:value('cs-heat')*1000});
    if(type==='goods_addition')Object.assign(event,{mass_kg:value('cs-mass'),temperature_k:value('cs-temperature')+273.15});
    if(type==='ambient_temperature')event.temperature_k=value('cs-temperature')+273.15;
    if(!Object.values(event).every(v=>typeof v!=='number'||Number.isFinite(v))||event.time_s<0)throw Error('请输入有效数值');
    eventDraft.list.push(event);eventDraft.list.sort((a,b)=>a.time_s-b.time_s);
    document.getElementById('cs-events').innerHTML=eventRows();
  }
  function bench(p){
    openDialog('机组工作点验证台','给定蒸发/冷凝温度与容量，用与项目运行相同的循环函数计算四个状态点（参数取 CU1 已应用值）。',
      `<div class="fields">${field('cs-te','蒸发温度 · °C','-28','id="cs-te" type="number" step="any"')}${field('cs-tc','冷凝温度 · °C','40','id="cs-tc" type="number" step="any"')}${field('cs-cap','容量 · %','100','id="cs-cap" type="number" step="any" min="1" max="100"')}</div>${btn('cs-bench-run','计算工作点','Gauge','','primary')}<div id="cs-bench-result" class="stack"></div>`,null,'',true);
  }
  function canonicalUnit(p){
    const node=p.pages.flatMap(pg=>pg.nodes).find(n=>n.moduleId==='condensing_unit');
    const definition=engine().catalog.modules.find(m=>m.id==='condensing_unit');
    return Object.fromEntries(definition.parameters.map(spec=>[spec.id,spec.unit?(Number(node.params[spec.id])-spec.unit.display_offset)*spec.unit.display_scale:node.params[spec.id]]));
  }
  async function benchRun(p){
    const value=id=>Number(document.getElementById(id).value);
    const body={parameters:canonicalUnit(p),fluid:{fluid:p.fluid||'HEOS::R290'},evaporating_temperature_k:value('cs-te')+273.15,
      condensing_temperature_k:value('cs-tc')+273.15,capacity_ratio:value('cs-cap')/100};
    const response=await fetch('/api/v1/cold-store/workpoint',{method:'POST',headers:{'Content-Type':'application/json',...engine().authHeaders()},body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail?.message||JSON.stringify(data.detail));
    const r=data.point,c=k=>(r[k]-273.15).toFixed(2),kw=k=>(r[k]/1000).toFixed(3);
    const states=[1,2,3,4].map(i=>`<tr><td>${i}</td><td>${(r[`state${i}.pressure_pa`]/1000).toFixed(2)}</td><td>${c(`state${i}.temperature_k`)}</td><td>${(r[`state${i}.enthalpy_j_kg`]/1000).toFixed(2)}</td><td>${r[`state${i}.quality`]===null?'—':r[`state${i}.quality`].toFixed(4)}</td></tr>`).join('');
    document.getElementById('cs-bench-result').innerHTML=`${data.diagnostics.map(d=>`<div class="notice warn">${esc(d.message)}</div>`).join('')}
      <table class="data-table cold-table" data-cold-bench><tbody><tr><td>制冷量</td><td data-bench-cooling>${kw('cooling_power_w')} kW</td><td>压缩机电功率</td><td>${kw('electric_power_w')} kW</td></tr>
      <tr><td>冷凝排热</td><td>${kw('condenser_heat_w')} kW</td><td>质量流量</td><td>${r.mass_flow_kg_s.toFixed(5)} kg/s</td></tr>
      <tr><td>机组 COP</td><td data-bench-cop>${r.cop.toFixed(4)}</td><td>含冷凝风机 COP</td><td>${data.unit_cop.toFixed(4)}</td></tr>
      <tr><td>压比</td><td>${r.pressure_ratio.toFixed(3)}</td><td>排气温度</td><td>${c('discharge_temperature_k')} °C</td></tr>
      <tr><td>额定点反算排量</td><td>${(data.design.displacement_m3_s*3600).toFixed(4)} m³/h</td><td>冷凝器 UA</td><td>${data.design.condenser_ua_w_k.toFixed(2)} W/K</td></tr></tbody></table>
      <table class="data-table cold-table"><thead><tr><th>状态点</th><th>压力 kPa</th><th>温度 °C</th><th>比焓 kJ/kg</th><th>干度</th></tr></thead><tbody>${states}</tbody></table>`;
  }
  async function download(path,name){
    const response=await fetch('/api/v1'+path,{headers:engine().authHeaders()});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw Error(typeof data.detail==='string'?data.detail:data.detail?.message||'报告生成失败');}
    ui.download(name,await response.blob());
  }
  async function compare(){
    await engine().refreshArchives();
    const runs=(ui.ui().archivedRuns||[]).filter(r=>['completed','failed'].includes(r.status));
    if(runs.length<2)throw Error('需要至少两次已结束的运行');
    openDialog('控制策略对照','选择两次运行（例如 A-S05 定容量与变容量），生成含公平性检查的对照报告。',
      `<div class="fields"><label class="field"><span>运行 A</span><select name="a" aria-label="运行 A">${runs.map((r,i)=>option(r.id,`${r.name} · ${r.id.slice(0,8)}`,runs[1]?.id)).join('')}</select></label><label class="field"><span>运行 B</span><select name="b" aria-label="运行 B">${runs.map(r=>option(r.id,`${r.name} · ${r.id.slice(0,8)}`,runs[0].id)).join('')}</select></label></div><p class="muted">节电率只在两方案满足同一温度约束、末态储能可比时给出。</p>`,
      data=>{if(data.a===data.b)throw Error('请选择两次不同的运行');download(`/runs/compare/report.html?a=${encodeURIComponent(data.a)}&b=${encodeURIComponent(data.b)}`,`cold-store-compare.html`).catch(error=>msg(error.message,true));},'下载对照报告');
  }
  async function action(name,el){
    const p=ui.project();
    switch(name){
      case 'cs-create':await create();break;
      case 'cs-scenarios':scenarios(p);break;
      case 'cs-run-scenario':await runScenario(p,el.dataset.scenario);break;
      case 'cs-schedule':schedule(p);break;
      case 'cs-add-event':addEvent();break;
      case 'cs-remove-event':eventDraft.list.splice(Number(el.dataset.index),1);document.getElementById('cs-events').innerHTML=eventRows();break;
      case 'cs-bench':bench(p);break;
      case 'cs-bench-run':await benchRun(p);break;
      case 'cs-report':await download(`/runs/${encodeURIComponent(lastRun(p))}/report.html`,`cold-store-${lastRun(p).slice(0,8)}.html`);break;
      case 'cs-csv':await download(`/runs/${encodeURIComponent(lastRun(p))}/report.csv`,`cold-store-${lastRun(p).slice(0,8)}.csv`);break;
      case 'cs-compare':await compare();break;
    }
  }
  return {markup,refresh,action};
};
