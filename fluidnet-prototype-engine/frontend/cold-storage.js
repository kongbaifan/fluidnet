/* Cold-storage case: creation, indicators, scenarios, schedule, unit bench and reports.
   All result values come from the shared engine run; this file only arranges inputs and views. */
window.createColdStorageUI = function (ui) {
  const state=ui.state, engine=ui.engine, {esc,btn,openDialog,msg}=ui;
  const IDEAL='cold-room-ideal-v1', ROOM='cold-room-minus18-v1', STATION='cold-storage-nh3co2-v2', COUPLED='thermal-coupling-nh3-glycol-v1';
  // Mirrors refrigeration/examples.py ROOM_SCENARIO_DURATIONS (cases/cold-storage/single-room-minus18/scenarios.json).
  const DURATIONS={'A-S01':21600,'A-S02':21600,'A-S03':28800,'A-S04':28800,'A-S05-onoff':86400,'A-S05-variable':86400,'A-S06':86400,'A-S07':21600,
    // Mirrors refrigeration/examples.py STATION_SCENARIO_DURATIONS.
    'B-S01':86400,'B-S02':86400,'B-S03':64800,'B-S04':72000};
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
    if(!response.ok)throw Error('无法读取案例');
    return response.json();
  }
  function nodesOf(model,positions){
    return model.instances.map(n=>{
      const definition=model.modules.find(m=>m.id===n.module_id);
      const params=prototypeParameters(definition,Object.fromEntries(definition.parameters.map(spec=>[spec.id,n.parameters[spec.id]??spec.default])));
      const [x,y]=positions[n.id]||[n.position?.x??430,n.position?.y??215];
      return ui.makeInstance(n.id,n.module_id,n.name,x,y,params);
    });
  }
  function prototypeParameters(definition,values){
    const bindings=engine().catalog.prototype_parameter_bindings[definition.id]||{};
    const names=Object.fromEntries(Object.entries(bindings).map(([name,key])=>[key,name]));
    return Object.fromEntries(Object.entries(values).map(([key,value])=>
      [names[key]||key,display(definition.parameters.find(spec=>spec.id===key),value)]));
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
  // --- case B: NH3/CO2 lumped station ------------------------------------------------------------
  const STATION_LAYOUT={LP1:[190,330],SH1:[330,330],K1:[470,120],K2:[470,250],K3:[470,380],K4:[470,510],DH1:[610,330],EC1:[750,330],
    HP1:[890,330],EV1:[890,470],RH1:[610,520],HX1:[330,560],CD1:[190,640],PU1:[330,720],FH1:[470,720],AC1:[610,640],AC2:[610,800],
    BH1:[190,800],ROOM1:[790,640],ROOM2:[790,800]};
  async function createStation(){
    if(!engine().catalog||!engine().health?.capabilities?.refrigeration_station)throw Error('请等待支持制冷站的计算服务连接。');
    if(state().projects.length>=20)throw Error('最多保存 20 个项目');
    const model=await fetchExample('cold-storage-nh3co2');
    const pg={id:'main',name:'制冷站总览',zoom:.8,pan:[0,0],nodes:nodesOf(model,STATION_LAYOUT),
      edges:model.connections.map(c=>[c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id])};
    const p=ui.makeProject(ui.uid('project'),model.name,model.description,pg);
    const script=model.control_scripts[0];
    Object.assign(p,{caseId:STATION,controllers:model.controllers,events:model.events,control:script.source,controlLanguage:'python',controlEnabled:true,
      controlInputs:script.inputs.join(', '),controlOutputs:script.outputs.join(', '),
      circuitFluids:model.circuit_fluids.map(c=>({id:c.id,anchor:c.anchor,medium:'',fluid:c.fluid.fluid,fluidReference:'mass'})),
      scenarios:model.scenarios.map(s=>({id:s.id,name:s.name,events:s.events,overrides:{}})),activeScenarioId:'B-S01'});
    p.controlConfig={...(p.controlConfig||{}),name:'上层启停 · 液泵 · 满足度',period:script.sample_s*1000};
    p.solver={...p.solver,mode:'dynamic',duration:DURATIONS['B-S01'],dt:30,executionMode:'fast',historyWindow:DURATIONS['B-S01']/30+1};
    state().projects.push(p);ui.normalizeState();
    charts(p,[['ROOM1','runtime:state.temperature_k','库房 1 库温','°C','ROOM1.state.temperature_k',1,-273.15],
      ['ROOM2','runtime:state.temperature_k','库房 2 库温','°C','ROOM2.state.temperature_k',1,-273.15],
      ['LP1','runtime:state.pressure_pa','低压桶压力','MPa','LP1.state.pressure_pa',1e6,0],
      ['HP1','runtime:state.pressure_pa','贮液器压力','MPa','HP1.state.pressure_pa',1e6,0],
      ['HP1','runtime:state.level_ratio','贮液器液位','%','HP1.state.level_ratio',.01,0],
      ['K1','runtime:electric_power_w','压缩机 1 电功率','kW','K1.electric_power_w',1000,0]]);
    ui.markDirty(p);ui.persist();ui.openProject(p.id);
    msg('NH₃/CO₂ 制冷站已创建：输入目标蒸发/冷凝压力即可自运行；选工况运行或修改目标压力。');
  }
  const STATION_METRICS=[['room1','库房 1 · °C','ROOM1.state.temperature_k',1,-273.15,2],['room2','库房 2 · °C','ROOM2.state.temperature_k',1,-273.15,2],
    ['lp','低压桶 · MPa','LP1.state.pressure_pa',1e6,0,4],['lp-target','目标蒸发 · MPa','controller.suction.setpoint',1e6,0,4],
    ['hp','贮液器 · MPa','HP1.state.pressure_pa',1e6,0,4],['hp-target','目标冷凝 · MPa','controller.head.setpoint',1e6,0,4],
    ['hp-level','贮液器液位 · %','HP1.state.level_ratio',.01,0,1],['lp-level','低压桶液位 · %','LP1.state.level_ratio',.01,0,1],
    ['running','压缩机台数','script.control.state.running',1,0,0],['load','载量 · %','K1.param.load_ratio',.01,0,1],
    ['fans','冷凝器风机','EC1.param.fan_ratio',1,0,2],['satisfaction','需求满足度 · %','script.control.state.satisfaction',.01,0,2]];
  function stationPower(p){const v=p.run.history.at(-1)?.metrics?.electric_power_w;return typeof v==='number'?(v/1000).toFixed(1):'—';}
  function stationEnergy(p){
    const row=p.run.history.at(-1)?.canonical;if(!row)return '—';
    const keys=Object.keys(row).filter(k=>/\.state\.(electric|fan)_energy_j$/.test(k));
    return keys.length?(keys.reduce((s,k)=>s+row[k],0)/3.6e6).toFixed(1):'—';
  }
  function stationMarkup(p){
    const run=lastRun(p),disabled=run?'':'disabled';
    return `<section class="panel cold-storage-summary cold-room" aria-label="制冷站运行指标"><div class="panel-head"><strong>NH₃/CO₂ 两库房冷库</strong><span data-cold-scenario>${esc(scenarioName(p))}</span><span class="push"></span>${btn('cs-scenarios','工况','ListChecks','','small')}${btn('cs-targets','目标压力','Gauge','','small')}${btn('cs-report','运行报告','FileText',disabled,'small')}${btn('cs-csv','CSV','Download',disabled,'small')}</div><div class="panel-body"><div class="metric-row cold-metrics">${STATION_METRICS.map(([id,label,key,scale,offset,digits])=>`<div class="metric"><span>${label}</span><strong data-station-${id}>${fmt(p,key,scale,offset,digits)}</strong></div>`).join('')}<div class="metric"><span>电功率 · kW</span><strong data-station-power>${stationPower(p)}</strong></div><div class="metric"><span>累计电量 · kWh</span><strong data-station-energy>${stationEnergy(p)}</strong></div></div><div data-cold-warnings>${warnings(p).map(w=>`<div class="notice warn">${esc(w)}</div>`).join('')}</div></div></section>`;
  }
  function stationRefresh(p){
    for(const [id,,key,scale,offset,digits] of STATION_METRICS){const e=document.querySelector(`[data-station-${id}]`);if(e)e.textContent=fmt(p,key,scale,offset,digits);}
    const power=document.querySelector('[data-station-power]');if(power)power.textContent=stationPower(p);
    const energy=document.querySelector('[data-station-energy]');if(energy)energy.textContent=stationEnergy(p);
    const box=document.querySelector('[data-cold-warnings]');if(box)box.innerHTML=warnings(p).map(w=>`<div class="notice warn">${esc(w)}</div>`).join('');
    const run=lastRun(p);for(const action of ['cs-report','cs-csv']){const b=document.querySelector(`[data-action="${action}"]`);if(b)b.disabled=!run;}
  }
  function targets(p){
    const c=id=>(p.controllers||[]).find(c=>c.id===id);
    openDialog('目标蒸发 / 冷凝压力',p.run.live&&p.run.runId?'运行中修改：作为 PID 设定值命令在下一帧边界生效并记入运行事件。':'修改项目中的 PID 设定值，下次运行生效。',
      `<div class="fields">${field('evaporating','目标蒸发压力 · kPa',(c('suction').setpoint/1000).toFixed(1),'type="number" step="any" min="50" max="400"')}${field('condensing','目标冷凝压力 · kPa',(c('head').setpoint/1000).toFixed(1),'type="number" step="any" min="800" max="1800"')}</div><p class="muted">冷凝目标低于当时冷凝能力（湿球温度高、风机已全开）时达不到，控制脚本会记录“目标冷凝压力不可达”。</p>`,
      data=>{
        const values={suction:Number(data.evaporating)*1000,head:Number(data.condensing)*1000};
        if(!Object.values(values).every(Number.isFinite))throw Error('请输入有效数值');
        if(p.run.live&&p.run.runId){
          (async()=>{for(const [id,value] of Object.entries(values))await engine().confirmedCommand(p,{action:'controller',controller_id:id,parameter_id:'setpoint',value});
            msg('目标压力已在运行中生效。');})().catch(error=>msg(error.message,true));
          return;
        }
        for(const [id,value] of Object.entries(values))c(id).setpoint=value;
        ui.markDirty(p);ui.persist();ui.render();msg('目标压力已写入项目，下次运行生效。');
      },'应用');
  }
  async function createCoupled(topology='single'){
    if(!engine().catalog||!engine().health?.capabilities?.thermal_coupling)throw Error('请等待支持热耦合的计算服务连接。');
    if(state().projects.length>=20)throw Error('最多保存 20 个项目');
    const model=await fetchExample('thermal-coupling?topology='+encodeURIComponent(topology));
    const pg={id:'main',name:model.name,zoom:.8,pan:[0,0],nodes:nodesOf(model,{}),
      edges:model.connections.map(c=>[c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id])};
    ui.fitNetwork(pg);
    const p=ui.makeProject(ui.uid('project'),model.name,model.description,pg);
    const definition=id=>model.modules.find(m=>m.id===model.instances.find(n=>n.id===id).module_id);
    Object.assign(p,{caseId:topology==='single'?COUPLED:model.id,fluid:model.fluid.fluid,fluidReference:model.fluid.reference,fluidConfig:model.fluid,
      thermalCouplings:model.thermal_couplings,solverOptions:model.solver,events:model.events,controllers:model.controllers,
      circuitFluids:model.circuit_fluids.map(c=>({id:c.id,anchor:c.anchor,fluid:c.fluid.fluid,fluidReference:c.fluid.reference,fluidConfig:c.fluid})),
      scenarios:model.scenarios.map(s=>({...s,overrides:Object.fromEntries(Object.entries(s.overrides).map(([id,values])=>
        [id,prototypeParameters(definition(id),values)]))})),activeScenarioId:'rated'});
    p.solver={...p.solver,mode:'dynamic',duration:60,dt:5,dynamicStep:model.solver.dynamic_step_s,
      pressureAtol:model.solver.pressure_tolerance_pa,massAtol:model.solver.mass_tolerance_kg_s,maxIter:model.solver.max_iterations,
      hydraulicMethod:model.solver.hydraulic_method,moduleMixedJacobian:model.solver.module_mixed_jacobian,
      executionMode:'fast',historyWindow:2001};
    state().projects.push(p);ui.normalizeState();
    syncCouplingCharts(p);
    ui.ui().showChart=true;
    ui.ui().workbenchChart=state().charts.extra.find(c=>c.projectId===p.id&&c.couplingId)?.id;
    ui.markDirty(p);ui.persist();ui.openProject(p.id);
    msg('热耦合案例已创建：可在“盘管换热”分别管理关系和 UA，选择工况后运行。');
  }
  function dualExampleDialog(){
    openDialog('双盘管参考系统','两根盘管向同一个氨侧低压容器传热，液体侧无储量。',
      `<label class="field"><span>双盘管拓扑</span><select name="topology" aria-label="双盘管拓扑">${option('parallel','同回路双支路','parallel')}${option('independent','水与乙二醇独立回路','parallel')}</select></label>`,
      values=>createCoupled(values.topology),'创建双盘管项目');
  }
  const COUPLED_METRICS=[['heat','盘管换热量','heat_w','kW',1000,0,3],
    ['inlet','盘管进液','fluid_inlet_temperature_k','°C',1,-273.15,2],
    ['outlet','盘管出液','fluid_outlet_temperature_k','°C',1,-273.15,2],
    ['saturation','制冷剂饱和温度','refrigerant_temperature_k','°C',1,-273.15,2],
    ['flow','二次侧流量','mass_flow_kg_s','kg/s',1,0,3],
    ['energy','累计传热量','state.heat_energy_j','kWh',3600000,0,4]];
  const couplingLinks=p=>Array.isArray(p.thermalCouplings)?p.thermalCouplings:[];
  const couplingNodes=p=>p.pages.flatMap(pg=>pg.nodes);
  const couplingReferences=(p,nodeIds)=>{
    const ids=new Set(Array.isArray(nodeIds)?nodeIds:[nodeIds]);
    return couplingLinks(p).filter(link=>ids.has(link.fluid_instance_id)||ids.has(link.refrigerant_vessel_id));
  };
  const assertCouplingIdle=p=>{
    if(['running','solving','paused'].includes(p.run.status)||p.run.live&&p.run.runId)throw Error('请先停止当前运行，再修改热耦合关系。');
  };
  function couplingDefinition(p,node){
    const m=p.moduleSnapshots?.[node.moduleId]||ui.moduleOf?.(node)||state().modules.find(m=>m.id===node.moduleId);
    if(m?.manifest)return m.manifest;
    const definition=engine().catalog?.modules.find(d=>d.id===(m?.kind||node.moduleId));
    return definition?{...definition,ports:m?.ports||definition.ports,channels:m?.channels||definition.channels}:undefined;
  }
  function couplingParameter(node,definition,key){
    const spec=definition.parameters?.find(x=>x.id===key);
    const bindings=engine().catalog?.prototype_parameter_bindings?.[definition.id]||{};
    const name=Object.keys(bindings).find(name=>bindings[name]===key)||key;
    const value=node.params?.[name];
    if(value===undefined)return spec?.default;
    return spec?.unit?(Number(value)-spec.unit.display_offset)*spec.unit.display_scale:value;
  }
  function couplingCandidates(p){
    const pipes=[],vessels=[],excluded=[];
    for(const node of couplingNodes(p)){
      const definition=couplingDefinition(p,node);if(!definition)continue;
      const domains=new Set((definition.ports||[]).map(port=>port.domain||'fluid'));
      if(definition.runtime==='builtin'&&definition.solver_model==='saturated_vessel'&&domains.size&&[...domains].every(d=>['refrigerant','thermal'].includes(d)))vessels.push({node,definition});
      if(definition.solver_model!=='pipe'||!domains.size||[...domains].some(d=>d!=='fluid'))continue;
      const channels=definition.channels||[];
      const reason=definition.runtime!=='builtin'||definition.state_model?'须使用无储量内置圆管':
        channels.length!==1||channels[0].enabled===false?'须只有一条启用通路':
        Number(couplingParameter(node,definition,'thermal_cells')||0)!==0?'热容分段数须为零':
        Number(couplingParameter(node,definition,'heat_loss_ua_w_k')||0)!==0?'原环境散热 UA 须为零':'';
      if(reason)excluded.push(`${node.id}：${reason}`);else pipes.push({node,definition,channel:channels[0]});
    }
    return {pipes,vessels,excluded};
  }
  function couplingToolbar(p){
    return btn('cs-coupling',couplingLinks(p).length?'盘管换热':'建立热耦合','Thermometer','','small');
  }
  function couplingChartBindings(p){
    const links=couplingLinks(p);
    const bindings=links.flatMap(link=>COUPLED_METRICS.map(([,label,suffix,unit,canonicalScale,canonicalOffset])=>({
      id:`coupling-chart:${p.id}:${link.id}:${suffix}`,projectId:p.id,nodeId:link.fluid_instance_id,
      variableId:`runtime:coupling.${suffix}`,label:`${link.id} · ${label}`,unit,
      canonicalKey:`coupling.${link.id}.${suffix}`,canonicalScale,canonicalOffset,
      couplingId:link.id,couplingBindingKey:JSON.stringify(link)
    })));
    if(links.length>1)for(const [suffix,label,unit,scale] of [['coupling_heat_w','总传热量','kW',1000],['coupling_heat_energy_j','累计总传热量','kWh',3600000]])
      bindings.push({id:`coupling-total:${p.id}:${suffix}`,projectId:p.id,nodeId:links[0].fluid_instance_id,
        variableId:`runtime:metrics.${suffix}`,label,unit,canonicalKey:`metrics.${suffix}`,canonicalScale:scale,canonicalOffset:0,
        couplingTotal:true,couplingBindingKey:JSON.stringify(links)});
    return bindings;
  }
  function syncCouplingCharts(p){
    const store=state().charts;
    const managed=c=>c.projectId===p.id&&(c.couplingId||c.couplingTotal||c.canonicalKey?.startsWith('coupling.')||c.canonicalKey?.startsWith('metrics.coupling_'));
    const previous=store.extra.filter(managed),kept=store.extra.filter(c=>!managed(c));
    for(const binding of couplingChartBindings(p)){
      const old=previous.find(c=>c.canonicalKey===binding.canonicalKey);
      kept.push({...binding,id:old?.id||binding.id});
    }
    store.extra=kept;
    if(previous.some(c=>c.id===ui.ui().workbenchChart)&&!kept.some(c=>c.id===ui.ui().workbenchChart))
      ui.ui().workbenchChart=kept.find(c=>c.projectId===p.id)?.id||'';
  }
  function couplingResultCurrent(p){
    return Boolean(p.run.history.length&&p.run.parameterKey&&p.run.parameterKey===ui.projectKey(p));
  }
  function coupledValue(p,link,suffix,scale,offset,digits){
    return couplingResultCurrent(p)?fmt(p,`coupling.${link.id}.${suffix}`,scale,offset,digits):'—';
  }
  function coupledMarkup(p){
    const links=couplingLinks(p);if(!links.length)return '';
    const nodes=couplingNodes(p),name=id=>{const n=nodes.find(n=>n.id===id);return n?`${n.name} (${id})`:`${id}（设备不存在）`;};
    const total=links.length>1?`<section class="panel" aria-label="双盘管汇总"><div class="panel-head"><strong>双盘管汇总</strong><span>${esc(name(links[0].refrigerant_vessel_id))}</span></div><div class="panel-body metric-row cold-metrics"><div class="metric"><span>总传热量 · kW</span><strong data-coupled-total-heat>${couplingResultCurrent(p)?fmt(p,'metrics.coupling_heat_w',1000,0,3):'—'}</strong></div><div class="metric"><span>累计总传热量 · kWh</span><strong data-coupled-total-energy>${couplingResultCurrent(p)?fmt(p,'metrics.coupling_heat_energy_j',3600000,0,4):'—'}</strong></div></div></section>`:'';
    const panels=links.map((link,index)=>`<section class="panel cold-storage-summary thermal-coupling" aria-label="${esc(link.id)} 热耦合运行指标" data-coupling-id="${esc(link.id)}">
      <div class="panel-head"><strong>${esc(link.id)} · 制冷站与二次液体回路</strong><span>${esc(scenarioName(p))}</span></div>
      <div class="panel-body"><p>${esc(name(link.fluid_instance_id))} · ${esc(link.fluid_channel_id||'ch0')} → ${esc(name(link.refrigerant_vessel_id))}；UA ${esc(link.ua_w_k)} W/K。正换热量表示二次液体向制冷剂放热，液体回路无储热。</p>
      <p data-coupled-result-status>${p.run.history.length&&!couplingResultCurrent(p)?'结果已过期，请重新运行。':'当前关系的计算结果'}</p>
      <div class="metric-row cold-metrics">${COUPLED_METRICS.map(([id,label,suffix,unit,scale,offset,digits])=>`<div class="metric"><span>${esc(label)} · ${esc(unit)}</span><strong data-coupled-${id}>${coupledValue(p,link,suffix,scale,offset,digits)}</strong></div>`).join('')}</div>
      ${index===0?`<div data-cold-warnings>${warnings(p).map(w=>`<div class="notice warn">${esc(w)}</div>`).join('')}</div>`:''}</div></section>`).join('');
    return links.length>1?`<div class="dual-coupling-results" aria-label="盘管运行结果" tabindex="0">${total}${panels}</div>`:panels;
  }
  function couplingList(p){
    assertCouplingIdle(p);
    const links=couplingLinks(p);
    openDialog('热耦合关系','两根不同液体通路的盘管可关联同一个饱和制冷剂容器。',
      `<div class="stack">${links.map(link=>`<div class="panel" data-coupling-row="${esc(link.id)}"><div class="panel-body"><strong>${esc(link.id)}</strong><p>${esc(link.fluid_instance_id)} · ${esc(link.fluid_channel_id)} → ${esc(link.refrigerant_vessel_id)}；UA ${esc(link.ua_w_k)} W/K</p><div class="row gap-6">${btn('cs-edit-coupling','编辑','Pencil',`data-coupling="${esc(link.id)}"`,'small')}${btn('cs-remove-coupling','移除','Trash2',`data-coupling="${esc(link.id)}"`,'small')}</div></div></div>`).join('')}
      ${btn('cs-add-coupling','新增关系','Plus',links.length>=2?'disabled title="最多支持两条关系"':'','small')}<p class="muted">${links.length} / 2 条关系</p></div>`);
  }
  function couplingSettings(p,identifier=undefined){
    assertCouplingIdle(p);
    if(!engine().catalog||!engine().health?.capabilities?.thermal_coupling)throw Error('请等待支持热耦合的计算服务连接。');
    const links=couplingLinks(p);if(links.length>2||identifier===null&&links.length>=2)throw Error('当前最多支持两条热耦合关系。');
    if(identifier===undefined&&links.length>1){couplingList(p);return;}
    const link=identifier===null?undefined:identifier===undefined?links[0]:links.find(item=>item.id===identifier);
    if(identifier!==undefined&&identifier!==null&&!link)throw Error('热耦合关系已不存在，请重新选择。');
    const others=links.filter(item=>item!==link),candidates=couplingCandidates(p),{excluded}=candidates;
    const pipes=candidates.pipes.filter(item=>!others.some(other=>other.fluid_instance_id===item.node.id&&other.fluid_channel_id===item.channel.id));
    const vessels=candidates.vessels.filter(item=>!others.length||item.node.id===others[0].refrigerant_vessel_id);
    const name=n=>`${n.name} (${n.id})`;
    const missing=[!pipes.length?'请添加一根无储量内置圆管：启用唯一通路，原环境散热 UA 和热容分段数均为零。':'',
      !vessels.length?'请添加一个制冷站饱和制冷剂容器（例如低压循环桶或高压贮液器）。':''].filter(Boolean);
    const pipeId=link?.fluid_instance_id||pipes[0]?.node.id||'',vesselId=link?.refrigerant_vessel_id||vessels[0]?.node.id||'';
    const pipe=pipes.find(x=>x.node.id===pipeId),channelId=link?.fluid_channel_id||pipe?.channel.id||'ch0';
    const stale=(value,entries)=>value&&!entries.some(x=>x.node.id===value)?option(value,`${value}（不再是合法端点，请重新选择）`,value):'';
    const key=ui.projectKey(p);
    let newId='HX1';for(let index=1;links.some(item=>item.id===newId);index++)newId='HX'+(index+1);
    openDialog('热耦合关系','一根内置液体盘管与一个饱和制冷剂容器交换热量；关系修改在下次运行生效。',
      `${others.length?`<p class="muted">${esc(others[0].id)} 已绑定 ${esc(others[0].fluid_instance_id)}；当前关系须使用另一液体通路并关联同一容器。</p>`:''}${missing.map(t=>`<p class="notice warn">${esc(t)}</p>`).join('')}${excluded.length?`<p class="muted">${excluded.map(esc).join('；')}</p>`:''}
      <div class="fields">${field('id','关系标识',link?.id||newId,'required maxlength="81" pattern="[A-Za-z][A-Za-z0-9_\\-]*"')}
      <label class="field"><span>液体管段</span><select id="cs-fluid-pipe" name="fluid_instance_id" aria-label="液体管段" required>${option('','请选择合法管段',pipeId)}${stale(pipeId,pipes)}${pipes.map(x=>option(x.node.id,name(x.node),pipeId)).join('')}</select></label>
      <label class="field"><span>通路</span><select id="cs-fluid-channel" name="fluid_channel_id" aria-label="通路" required>${pipe?option(pipe.channel.id,pipe.channel.name||pipe.channel.id,channelId):option('','请先选择合法管段','')}</select></label>
      <label class="field"><span>饱和制冷剂容器</span><select name="refrigerant_vessel_id" aria-label="饱和制冷剂容器" required>${option('','请选择合法容器',vesselId)}${stale(vesselId,vessels)}${vessels.map(x=>option(x.node.id,name(x.node),vesselId)).join('')}</select></label>
      ${field('ua','换热能力 UA · W/K',link?.ua_w_k??1800,'type="number" min="0" step="any" required')}</div>
      <div class="row gap-6">${link?btn('cs-remove-coupling','移除热耦合','Trash2',`data-coupling="${esc(link.id)}"`,'small'):''}${link&&links.length<2?btn('cs-add-coupling','新增关系','Plus','','small'):''}${links.length>1?btn('cs-list-couplings','返回关系列表','ListChecks','','small'):''}</div>`,
      values=>{
        assertCouplingIdle(p);if(ui.projectKey(p)!==key)throw Error('编辑期间项目发生变化，请重新打开热耦合关系。');
        const id=values.id?.trim(),ua=String(values.ua??'').trim()?Number(values.ua):NaN;
        if(!/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id||''))throw Error('关系标识须以字母开头，仅含字母、数字、下划线和连字符，最多 81 个字符。');
        if(!Number.isFinite(ua)||ua<0)throw Error('UA 必须为非负有限数值。');
        if(others.some(item=>item.id===id))throw Error('关系标识已被另一条热耦合使用。');
        if(others.some(item=>item.fluid_instance_id===values.fluid_instance_id&&item.fluid_channel_id===values.fluid_channel_id))throw Error('同一液体通路只能绑定一条热耦合关系。');
        if(others.some(item=>item.refrigerant_vessel_id!==values.refrigerant_vessel_id))throw Error('当前双盘管须关联同一个饱和制冷剂容器。');
        const current=couplingCandidates(p),selected=current.pipes.find(x=>x.node.id===values.fluid_instance_id);
        if(!selected||selected.channel.id!==values.fluid_channel_id)throw Error('请选择合法的无储量内置圆管及其唯一通路。');
        if(!current.vessels.some(x=>x.node.id===values.refrigerant_vessel_id))throw Error('请选择合法的饱和制冷剂容器。');
        const next={id,fluid_instance_id:values.fluid_instance_id,fluid_channel_id:values.fluid_channel_id,
          refrigerant_vessel_id:values.refrigerant_vessel_id,ua_w_k:ua};
        if(JSON.stringify(next)===JSON.stringify(link))return;
        ui.remember?.();p.thermalCouplings=link?links.map(item=>item===link?next:item):[...links,next];syncCouplingCharts(p);
        if(!link){ui.ui().showChart=true;ui.ui().workbenchChart=state().charts.extra.find(c=>c.projectId===p.id&&c.couplingId===id)?.id;}
        ui.markDirty(p);ui.persist();ui.render();msg('热耦合关系已应用，请重新运行。');
      },'应用关系');
    document.getElementById('cs-fluid-pipe').addEventListener('change',event=>{
      const selected=pipes.find(x=>x.node.id===event.target.value);
      document.getElementById('cs-fluid-channel').innerHTML=selected?option(selected.channel.id,selected.channel.name||selected.channel.id,selected.channel.id):option('','请先选择合法管段','');
    });
  }
  function removeCoupling(p,identifier){
    assertCouplingIdle(p);const links=couplingLinks(p);
    if(!identifier&&links.length>1)throw Error('请选择要移除的热耦合关系。');
    const link=identifier?links.find(item=>item.id===identifier):links[0];if(!link)return;
    const key=ui.projectKey(p);
    openDialog('移除热耦合',`解除 ${link.id}：${link.fluid_instance_id} → ${link.refrigerant_vessel_id}。设备保留，当前耦合曲线移除，历史运行保留。`,'',()=>{
      assertCouplingIdle(p);if(ui.projectKey(p)!==key)throw Error('确认期间项目发生变化，请重新操作。');
      ui.remember?.();p.thermalCouplings=links.filter(item=>item!==link);syncCouplingCharts(p);ui.markDirty(p);ui.persist();ui.render();msg('热耦合关系已解除。');
    },'解除关系');
  }
  function markup(p){
    if(couplingLinks(p).length)return coupledMarkup(p);
    if(p.caseId===IDEAL)return markupIdeal(p);
    if(p.caseId===STATION)return stationMarkup(p);
    if(p.caseId!==ROOM)return '';
    const run=lastRun(p), disabled=run?'':'disabled';
    return `<section class="panel cold-storage-summary cold-room" aria-label="冷库运行指标"><div class="panel-head"><strong>−18°C 冻结物储藏库</strong><span data-cold-scenario>${esc(scenarioName(p))}</span><span class="push"></span>${btn('cs-scenarios','工况','ListChecks','','small')}${btn('cs-schedule','负荷日程','Clock3','','small')}${btn('cs-bench','机组工作点','Gauge','','small')}${btn('cs-report','运行报告','FileText',disabled,'small')}${btn('cs-csv','CSV','Download',disabled,'small')}${btn('cs-compare','策略对照','ArrowRightLeft','','small')}</div><div class="panel-body"><div class="metric-row cold-metrics">${METRICS.map(([id,label,key,scale,offset,digits])=>`<div class="metric"><span>${label}</span><strong data-cold-${id}>${fmt(p,key,scale,offset,digits)}</strong></div>`).join('')}<div class="metric"><span>冷风机</span><strong data-cold-mode>${modeText(p)}</strong></div></div><div data-cold-warnings>${warnings(p).map(w=>`<div class="notice warn">${esc(w)}</div>`).join('')}</div></div></section>`;
  }
  function refresh(p){
    if(couplingLinks(p).length){
      for(const link of couplingLinks(p)){
        const panel=[...document.querySelectorAll('[data-coupling-id]')].find(item=>item.dataset.couplingId===link.id);if(!panel)continue;
        for(const [id,,suffix,,scale,offset,digits] of COUPLED_METRICS){const e=panel.querySelector(`[data-coupled-${id}]`);if(e)e.textContent=coupledValue(p,link,suffix,scale,offset,digits);}
        const status=panel.querySelector('[data-coupled-result-status]');if(status)status.textContent=p.run.history.length&&!couplingResultCurrent(p)?'结果已过期，请重新运行。':'当前关系的计算结果';
      }
      for(const [selector,key,scale,digits] of [['[data-coupled-total-heat]','metrics.coupling_heat_w',1000,3],['[data-coupled-total-energy]','metrics.coupling_heat_energy_j',3600000,4]]){
        const element=document.querySelector(selector);if(element)element.textContent=couplingResultCurrent(p)?fmt(p,key,scale,0,digits):'—';
      }
      const box=document.querySelector('[data-cold-warnings]');if(box)box.innerHTML=warnings(p).map(w=>`<div class="notice warn">${esc(w)}</div>`).join('');
      return;
    }
    if(p.caseId===IDEAL){
      for(const [selector,key,scale,offset] of [['[data-cold-temperature]','ROOM1.state.temperature_k',1,-273.15],
        ['[data-cold-power]','COLD1.cooling_power_w',1000,0],['[data-cold-energy]','COLD1.state.cooling_energy_j',3600000,0]]){
        const element=document.querySelector(selector);if(element)element.textContent=fmt(p,key,scale,offset);
      }
      return;
    }
    if(p.caseId===STATION)return stationRefresh(p);
    if(p.caseId!==ROOM)return;
    for(const [id,,key,scale,offset,digits] of METRICS){const element=document.querySelector(`[data-cold-${id}]`);if(element)element.textContent=fmt(p,key,scale,offset,digits);}
    const mode=document.querySelector('[data-cold-mode]');if(mode)mode.textContent=modeText(p);
    const box=document.querySelector('[data-cold-warnings]');if(box)box.innerHTML=warnings(p).map(w=>`<div class="notice warn">${esc(w)}</div>`).join('');
    const run=lastRun(p);for(const action of ['cs-report','cs-csv']){const b=document.querySelector(`[data-action="${action}"]`);if(b)b.disabled=!run;}
  }
  function scenarios(p){
    const rows=(p.scenarios||[]).map(s=>`<tr><td>${esc(s.name)}</td><td>${DURATIONS[s.id]?(DURATIONS[s.id]/3600)+' h':'—'}</td><td>${s.events?s.events.length:'沿用项目'}</td><td>${btn('cs-run-scenario','运行','Play',`data-scenario="${esc(s.id)}"`,'small primary')}</td></tr>`).join('');
    openDialog('冷库工况','选择工况运行：时长按案例设定，后台快算并保留全部帧以便导出报告。',`<table class="data-table cold-table"><thead><tr><th>工况</th><th>时长</th><th>事件</th><th></th></tr></thead><tbody>${rows}</tbody></table><p class="muted">${p.caseId===STATION?'B-S01～B-S04 对应 B 版验收场景：额定负荷、负荷阶跃、改目标压力、湿球温度变化。':'A-S05 的两种控制方式使用同一日程；运行后用“策略对照”生成公平性检查与对照报告。'}</p>`,null,'',true);
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
      case 'cs-create-station':await createStation();break;
      case 'cs-create-coupled':await createCoupled();break;
      case 'cs-create-dual':dualExampleDialog();break;
      case 'cs-coupling':couplingSettings(p);break;
      case 'cs-edit-coupling':couplingSettings(p,el.dataset.coupling);break;
      case 'cs-add-coupling':couplingSettings(p,null);break;
      case 'cs-list-couplings':couplingList(p);break;
      case 'cs-remove-coupling':removeCoupling(p,el.dataset.coupling);break;
      case 'cs-targets':targets(p);break;
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
  return {markup,refresh,action,couplingToolbar,couplingSettings,couplingReferences,assertCouplingIdle,syncCouplingCharts,couplingChartBindings};
};
