/* 风系统：服务器负责物性和求解；页面只作单位转换与同一运行帧的展示。 */
window.createAirSideUI = function (ui) {
  const {esc, btn, msg} = ui, clone = value => JSON.parse(JSON.stringify(value));
  const examples = [['air-coil-wet','湿盘管除湿'],['air-mixing','新回风混合'],['ahu-wet','空气处理机组'],
    ['ahu-room','房间送回风热湿系统'],['air-parallel-wet','并联风侧设备'],['cooling-tower-moist','冷却塔水耗']];
  const colors = ['#147d88','#e09339','#6372ba','#a5558a'];
  const model = {signature:'',epoch:0,record:null,catalog:[],grid:null,runs:[],selectedRunId:'',loading:false,error:'',
    curves:[],curveKey:'',comparisonIds:[],search:''};
  let controller, timer;
  const engine = ui.engine, state = ui.state, project = ui.project;
  const active = () => ui.ui().route === 'air';
  const supported = () => engine().health?.capabilities?.moist_air_contract_version === 1;
  const isAir = p => p.solverOptions?.moist_air || p.pages.some(pg=>pg.nodes.some(n=>ui.moduleOf(n).kind==='cooling_tower_moist'));
  function view(p) {
    p.airSideView ||= {schema:1,selected_instance_ids:[],observed_keys:[],active_tab:'distribution',reference_pressure_pa:101325,comparison_run_ids:[]};
    const ids = new Set(p.pages.flatMap(pg=>pg.nodes.map(n=>n.id)));
    p.airSideView.selected_instance_ids = (p.airSideView.selected_instance_ids || []).filter(id=>ids.has(id)).slice(0,100);
    return p.airSideView;
  }
  const option = (value,label,selected) => `<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`;
  const field = (name,label,value,attrs='') => `<label class="field"><span>${esc(label)}</span><input name="${name}" aria-label="${esc(label)}" value="${esc(value ?? '')}" ${attrs}></label>`;
  const raw = (key,frame=model.record?.frame) => key.startsWith('metrics.') ? frame?.metrics?.[key.slice(8)] : frame?.variables?.[key];
  function display(key,value=raw(key)) {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? '是' : '否';
    const spec=model.catalog.find(v=>v.key===key);
    if (typeof value === 'number') {
      const converted=spec?.unit ? value/spec.unit.display_scale+spec.unit.display_offset : value;
      if(converted!==0 && Math.abs(converted)<1e-5)return converted.toExponential(2);
      return Number(converted.toPrecision(7)).toLocaleString('zh-CN',{maximumFractionDigits:7});
    }
    return String(value);
  }
  const stale = p => !model.selectedRunId && p.run.parameterKey && p.run.parameterKey !== ui.projectKey(p);
  function invalidate() {model.signature='';controller?.abort();clearTimeout(timer);model.epoch++;}
  function forgetProject() {
    invalidate();Object.assign(model,{record:null,catalog:[],selectedRunId:'',comparisonIds:[],curves:[],runs:[],error:''});
  }
  function persistView(p) {ui.markDirty(p);ui.persist();}

  async function load() {
    const p=project(),runId=model.selectedRunId || (p.run.source==='engine'?p.run.id:'');
    if (!active() || !supported() || !isAir(p)) return;
    const signature=[p.id,runId,ui.projectKey(p),view(p).reference_pressure_pa].join('|');
    if (signature===model.signature) return;
    controller?.abort();controller=new AbortController();const signal=controller.signal,ticket=++model.epoch;
    model.signature=signature;model.loading=true;model.error='';
    try {
      const catalogPromise=runId ? engine().request(`/runs/${encodeURIComponent(runId)}/air-variables`,undefined,signal)
        : engine().normalize(p,signal).then(body=>engine().request('/air/variables/preview',body,signal));
      const [record,catalog,grid,runs]=await Promise.all([
        runId?engine().request('/runs/'+encodeURIComponent(runId),undefined,signal):null,catalogPromise,
        engine().request('/air/psychrometric-grid?pressure_pa='+view(p).reference_pressure_pa,undefined,signal),
        engine().request('/runs',undefined,signal)]);
      if(ticket!==model.epoch || project().id!==p.id || !active()) return;
      Object.assign(model,{record,catalog:catalog.variables,grid,runs:runs.runs.filter(r=>r.name===p.name)});
      if(record?.frame && !record.frame.valid) {
        const history=await engine().request(`/runs/${encodeURIComponent(runId)}/overview`,undefined,signal);
        if(ticket!==model.epoch || project().id!==p.id || !active())return;
        const last=history.rows.filter(row=>row.valid).at(-1);
        if(last)model.record={...record,frame:last};
      }
    } catch(error) {if(error.name!=='AbortError' && ticket===model.epoch)model.error=error.message;}
    finally {
      if(ticket===model.epoch){model.loading=false;if(active())ui.render();}
    }
    if(ticket===model.epoch && active() && ['queued','running'].includes(model.record?.status))
      timer=setTimeout(()=>{model.signature='';load();},1000);
  }

  function ports() {
    const map=new Map();
    for(const v of model.catalog)if(v.port_id){const key=v.instance_id+'.'+v.port_id;map.set(key,{key,id:v.instance_id,port:v.port_id});}
    const selected=view(project()).selected_instance_ids;
    return [...map.values()].filter(p=>(!selected.length||selected.includes(p.id))&&(!model.search||p.key.toLowerCase().includes(model.search.toLowerCase())));
  }
  function distribution() {
    const headers=[['mass_flow_kg_s','湿空气流量','kg/s'],['dry_air_mass_flow_kg_s','干空气流量','kg_da/s'],
      ['temperature_k','温度','°C'],['relative_humidity','相对湿度','%'],['humidity_ratio_kg_kg','含湿量','g/kg_da'],
      ['enthalpy_j_kg_dry_air','比焓','kJ/kg_da']];
    return `<div class="air-table-wrap"><table><thead><tr><th>设备 · 端口</th>${headers.map(([,label,unit])=>`<th>${label}<small>${unit}</small></th>`).join('')}</tr></thead><tbody>${ports().map(p=>
      `<tr data-air-port="${esc(p.key)}"><th>${esc(p.id)}<small>${esc(p.port)}</small></th>${headers.map(([suffix])=>`<td data-air-value="${esc(p.key+'.'+suffix)}">${esc(display(p.key+'.'+suffix))}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="air-footnote">端口流量以流入设备为正。加湿、除湿设备进出口的湿空气总流量可以不同；干空气流量保持守恒。</p>`;
  }
  function psychrometrics() {
    if(!model.grid)return '<p class="muted">正在读取湿空气状态图网格…</p>';
    const {temperature_min_k:lo,temperature_max_k:hi,humidity_max_kg_kg:max}=model.grid;
    const x=t=>65+(t-lo)/(hi-lo)*730,y=w=>350-w/max*300;
    const lines=model.grid.lines.flatMap(line=>line.segments.map(points=>`<polyline points="${points.map(p=>`${x(p.temperature_k)},${y(p.humidity_ratio_kg_kg)}`).join(' ')}" fill="none" stroke="${line.relative_humidity===1?'#498895':'#c9dee3'}" stroke-width="${line.relative_humidity===1?2:1}"/>`)).join('');
    const points=ports().filter(p=>Number.isFinite(raw(p.key+'.temperature_k'))&&Number.isFinite(raw(p.key+'.humidity_ratio_kg_kg')));
    const dots=points.map((p,i)=>{const t=raw(p.key+'.temperature_k'),w=raw(p.key+'.humidity_ratio_kg_kg');
      if(t<lo||t>hi||w>max)return '';
      return `<circle cx="${x(t)}" cy="${y(w)}" r="5" fill="${colors[i%4]}" stroke="white" tabindex="0"><title>${esc(p.key)} · ${display(p.key+'.temperature_k')} °C · ${display(p.key+'.humidity_ratio_kg_kg')} g/kg_da</title></circle>`;}).join('');
    const mismatch=points.some(p=>Math.abs(raw(p.key+'.pressure_pa')-view(project()).reference_pressure_pa)>1000);
    return `<div class="air-psych"><svg viewBox="0 0 850 405" role="img" aria-label="湿空气状态图：干球温度与含湿量">${[0,10,20,30,40,50].map(t=>`<path d="M${x(t+273.15)} 50V350" stroke="#edf2f3"/><text x="${x(t+273.15)}" y="374" text-anchor="middle">${t}</text>`).join('')}${[0,5,10,15,20,25,30].map(w=>`<path d="M65 ${y(w/1000)}H795" stroke="#edf2f3"/><text x="53" y="${y(w/1000)+4}" text-anchor="end">${w}</text>`).join('')}${lines}${dots}<text x="430" y="398" text-anchor="middle">干球温度 / °C</text><text x="14" y="32">g/kg_da</text></svg><aside><h3>运行状态点</h3><p class="muted">参考压力 ${(view(project()).reference_pressure_pa/1000).toFixed(3)} kPa；曲线表示 10%–100% 相对湿度。悬停状态点查看设备。</p>${mismatch?'<p class="notice">部分状态点实际压力与图参考压力相差超过 1 kPa，请分别解释。</p>':''}<div class="air-point-list">${points.map(p=>`<div><strong>${esc(p.key)}</strong><span>${display(p.key+'.temperature_k')} °C · ${display(p.key+'.relative_humidity')}%</span></div>`).join('')}</div></aside></div>`;
  }
  function moisture() {
    const groups=new Map();
    for(const v of model.catalog){if(v.port_id||v.channel_id||!['state','derived'].includes(v.source)||v.instance_id==='metrics')continue;
      if(!groups.has(v.instance_id))groups.set(v.instance_id,[]);groups.get(v.instance_id).push(v);}
    return `<div class="air-device-grid">${[...groups].map(([id,variables])=>`<section class="air-device"><h3>${esc(id)}</h3>${variables.map(v=>`<div><span>${esc(v.label.replace(/^.* · /,''))}</span><strong>${esc(display(v.key))} <small>${esc(v.unit?.display_unit||'')}</small></strong></div>`).join('')}</section>`).join('')}</div>`;
  }
  function curveSvg() {
    const series=model.curves, values=series.flatMap(s=>s.points.map(p=>p[1]));
    if(!values.length)return '<p class="muted">选择同一变量和最多四次运行后读取曲线。</p>';
    const xmax=Math.max(1,...series.flatMap(s=>s.points.map(p=>p[0]))),lo=Math.min(...values),hi=Math.max(...values),span=Math.max(hi-lo,Math.abs(hi)*.05,1e-6);
    const x=t=>75+t/xmax*790,y=v=>280-(v-lo)/span*220;
    return `<svg viewBox="0 0 900 330" role="img" aria-label="同变量运行对比曲线"><path d="M75 45V280H865" stroke="#9cb5be" fill="none"/>${[0,.25,.5,.75,1].map(f=>`<text x="64" y="${y(lo+span*f)+4}" text-anchor="end">${Number((lo+span*f).toPrecision(5))}</text>`).join('')}${series.map((s,i)=>`<polyline fill="none" stroke="${colors[i]}" stroke-width="2.5" points="${s.points.map(([t,v])=>`${x(t)},${y(v)}`).join(' ')}"/>${s.points.length===1?`<circle cx="${x(s.points[0][0])}" cy="${y(s.points[0][1])}" r="5" fill="${colors[i]}"/>`:''}`).join('')}<text x="470" y="321" text-anchor="middle">仿真时间 / s（0–${xmax}）</text></svg>`;
  }
  function comparison() {
    const choices=model.catalog.filter(v=>v.value_type==='number'&&v.source!=='parameter');
    model.curveKey ||= choices.find(v=>v.key.endsWith('state.humidity_ratio_kg_kg'))?.key || choices[0]?.key || '';
    return `<div class="air-compare"><div class="air-comparison-input"><label class="field"><span>对比变量</span><select data-air-curve-key aria-label="对比变量">${choices.map(v=>option(v.key,v.label+' · '+(v.unit?.display_unit||''),model.curveKey)).join('')}</select></label><p class="muted">选择最多四次运行；合同、变量和质量基准必须一致。</p><div class="air-run-choices">${model.runs.slice(0,20).map(r=>`<label><input type="checkbox" data-air-compare-id="${esc(r.id)}" ${model.comparisonIds.includes(r.id)?'checked':''}> ${esc(r.name)} · ${esc(r.id.slice(0,8))} · ${r.time_s}s</label>`).join('')||'<p>尚无已保存运行。</p>'}</div>${btn('air-compare','读取对比曲线','Activity','','primary')}</div><div class="air-curve">${curveSvg()}<div class="air-legend">${model.curves.map((s,i)=>`<span><i style="background:${colors[i]}"></i>${esc(s.id.slice(0,8))} · ${esc(s.unit)}${s.stride>1?' · 抽稀概览':''}</span>`).join('')}</div></div></div>`;
  }
  function markup(p) {
    const v=view(p),tabs=[['distribution','风量与状态'],['psychrometrics','湿空气状态图'],['moisture','设备与水耗'],['compare','运行对比']];
    const enabled=supported(),air=isAir(p),record=model.record, frame=record?.frame;
    const selected=model.selectedRunId || '',source=record ? `${record.id.slice(0,12)} · 帧 ${frame?.sequence??'—'} · 参数修订 ${frame?.parameter_revision??'—'}`:'尚未运行';
    const ids=[...new Set(model.catalog.map(d=>d.instance_id).filter(id=>id!=='metrics'))];
    const content={distribution,psychrometrics,moisture,compare:comparison};
    return `<div class="page-shell air-page" id="air-page">${ui.heading('风系统','风量分配、热湿状态与水耗，从同一次运行查看。',btn('air-create','创建风侧示例','Plus',enabled?'':'disabled','primary')+btn('air-config','湿空气设置','Settings2',enabled?'':'disabled')+(p.solverOptions?.moist_air&&!p.solverOptions?.moist_air_options?btn('air-migrate','升级旧项目','ArrowUpRight'):'')+btn('air-humidity','相对湿度换算','Droplets',air?'':'disabled')+btn('nav','批量方案','ListChecks','data-route="batches"'))}
      <div class="air-toolbar"><label class="field"><span>当前项目</span><select data-air-project aria-label="风侧当前项目">${state().projects.map(item=>option(item.id,item.name,p.id)).join('')}</select></label><label class="field"><span>结果来源</span><select data-air-source aria-label="风侧结果来源">${option('','当前运行',selected)}${model.runs.map(r=>option(r.id,`${r.name} · ${r.id.slice(0,8)}`,selected)).join('')}</select></label><span class="push"></span>${btn('air-run','运行计算','Play',air&&!model.creating?'':'disabled','primary')}${btn('air-stop','停止','Square',p.run.live?'':'disabled')}${btn('air-save','保存项目','Save')}${btn('nav','编辑拓扑','Network','data-route="workbench"')}</div>
      ${!enabled?'<p class="notice">请连接支持风侧合同 1 的计算服务。</p>':''}${!air?'<div class="air-empty"><h2>从一个可复算的风系统开始</h2><p>选择盘管、混合箱、完整空气处理机组、房间或冷却塔示例，再调整设备参数。</p></div>':''}
      ${air?`<div class="air-provenance ${stale(p)?'is-stale':''}" data-air-provenance><strong>${stale(p)?'参数或拓扑已改变，当前结果已过期':model.selectedRunId?'正在查看历史运行':'当前运行结果'}</strong><span>${esc(source)}${frame?' · '+frame.time_s+' s':''}</span>${record?.air_metadata?`<small>CoolProp ${esc(record.air_metadata.property_version)} · ${esc(record.status)} · ${esc(record.air_metadata.project_snapshot_hash.slice(0,16))}</small>`:''}</div>
      ${record?.status==='failed'?'<p class="notice">运行失败，保留最后有效帧；请查看诊断后调整参数。</p>':''}
      ${model.error?`<p role="alert" class="notice">${esc(model.error)}</p>`:''}
      <div class="air-summary"><div><span>端口状态</span><strong>${ports().length}</strong><small>按实际设备生成</small></div><div><span>干空气质量残差</span><strong>${display('metrics.dry_air_mass_residual_kg_s')}</strong><small>kg_da/s</small></div><div><span>水分残差</span><strong>${display('metrics.moisture_residual_kg_s')}</strong><small>kg/s</small></div><div><span>能量残差</span><strong>${display('metrics.energy_residual_w')}</strong><small>kW</small></div></div>
      <section class="panel air-results"><div class="air-results-head"><div class="segmented">${tabs.map(([key,label])=>btn('air-tab',label,'',`data-value="${key}" aria-pressed="${v.active_tab===key}"`,v.active_tab===key?'active':'')).join('')}</div><span class="push"></span>${model.loading?'<span class="muted">读取中…</span>':''}${btn('air-report','CSV','Download',`data-format="csv" ${record?'':'disabled'}`,'small')}${btn('air-report','HTML 报告','FileText',`data-format="html" ${record?'':'disabled'}`,'small')}</div>
      ${v.active_tab==='distribution'?`<div class="air-filters"><label class="field"><span>筛选设备</span><select data-air-device aria-label="筛选风侧设备">${option('','全部设备',v.selected_instance_ids[0]||'')}${ids.map(id=>option(id,id,v.selected_instance_ids[0])).join('')}</select></label><label class="field"><span>检索端口</span><input data-air-search aria-label="检索风侧端口" value="${esc(model.search)}" placeholder="设备或端口编号"></label></div>`:''}
      ${(content[v.active_tab]||distribution)()}</section><p class="air-footnote">湿盘管为外部规定冷源；房间使用固定有效干空气存量；冷却塔为空气规定流股的教学模型。</p>`:''}</div>`;
  }

  async function createExample(name) {
    if(!supported())throw Error('请先连接支持湿空气合同 1 的服务');
    if(state().projects.length>=20)throw Error('最多保存 20 个项目');
    model.creating=true;ui.render();
    try {
    const canonical=await engine().request('/examples/'+name),snapshots={};
    for(const definition of canonical.modules){
      const m=engine().moduleFromManifest(definition);m.frozen=definition.runtime==='python';
      if(m.frozen){m.publishedManifest=clone(definition);m.latestVersion=definition.version;}
      snapshots[m.id]=m;
      if(!state().modules.some(item=>item.id===m.id))state().modules.push(clone(m));
    }
    const nodes=canonical.instances.map((n,i)=>{
      const definition=canonical.modules.find(m=>m.id===n.module_id),params=Object.fromEntries(definition.parameters.map(spec=>{
        const value=n.parameters[spec.id]??spec.default;
        return [spec.id,spec.unit?(value/spec.unit.display_scale+spec.unit.display_offset):clone(value)];
      }));
      const item=ui.makeInstance(n.id,n.module_id,n.name,110+(i%5)*220,100+Math.floor(i/5)*180,params);
      Object.assign(item,{params,draft:clone(params),modelId:null});return item;
    });
    const pg={id:'main',name:canonical.name,zoom:1,pan:[0,0],nodes,edges:canonical.connections.map(c=>[c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id])};
    const p=ui.makeProject(ui.uid('air-project'),canonical.name,'风侧教学算例，可调整参数并独立复算。',pg);
    Object.assign(p,{medium:canonical.solver.moist_air?'air':'water',fluid:canonical.fluid.fluid,fluidConfig:canonical.fluid,
      moduleSnapshots:snapshots,solverOptions:canonical.solver,controlEnabled:false,controlScripts:[],caseId:name});
    p.solver={...p.solver,mode:name==='ahu-room'?'dynamic':'steady',duration:name==='ahu-room'?120:10,dt:2,
      executionMode:'fast',moduleMixedJacobian:false,pressureAtol:1,massAtol:1e-8};
    state().projects.push(p);ui.normalizeState();view(p);persistView(p);forgetProject();ui.openProject(p.id);ui.navigate('air');ui.persist();
    msg('风侧示例已创建，可运行计算并保存项目。');
    } finally {model.creating=false;ui.render();}
  }
  function configure() {
    const p=project();if(p.solverOptions?.moist_air&&!p.solverOptions?.moist_air_options)throw Error('请先使用“升级旧项目”查看迁移预览。');if(p.run.live&&['running','paused','solving'].includes(p.run.status))throw Error('请先停止运行再修改物理配置');
    ui.openDialog('湿空气设置','含湿量是保存和计算的唯一湿度输入。湿空气采用 Air 气相、节点物性耦合。',
      `<label class="check-label"><input name="enabled" type="checkbox" ${p.solverOptions?.moist_air?'checked':''}>启用湿空气（Air 气相）</label>${field('pressure','状态图参考压力 / kPa',view(p).reference_pressure_pa/1000,'type="number" min="60" max="120" step="any"')}${field('duration','动态运行时长 / s',p.solver.duration,'type="number" min="1" max="86400"')}${field('dt','时间步长 / s',p.solver.dt,'type="number" min="0.01" max="60" step="any"')}<label class="field"><span>运行模式</span><select name="mode">${option('steady','稳态',p.solver.mode)}${option('dynamic','动态',p.solver.mode)}</select></label>`,data=>{
        const enabled=!!data.enabled;p.solverOptions={...p.solverOptions,moist_air:enabled,moist_air_options:enabled?{contract_version:1}:null};
        if(enabled){p.medium='air';p.fluid='Air';p.fluidConfig={backend:'coolprop',fluid:'Air',phase_policy:'gas',composition:{},reference:'mass'};
          Object.assign(p.solverOptions,{thermal:true,property_coupling:'node',series_compression:false,hydraulic_blocks:false,module_mixed_jacobian:false,thermal_acceleration:'none',coupling_acceleration:'none'});p.solver.moduleMixedJacobian=false;}
        Object.assign(p.solver,{duration:Number(data.duration),dt:Number(data.dt),mode:data.mode});
        view(p).reference_pressure_pa=Number(data.pressure)*1000;persistView(p);invalidate();ui.render();
      },'应用设置');
  }
  function humidityInput() {
    const p=project(),nodes=p.pages.flatMap(pg=>pg.nodes).filter(n=>ui.moduleOf(n).kind==='source');
    if(!nodes.length)throw Error('当前项目没有压力边界');
    ui.openDialog('由相对湿度生成含湿量草稿','按所选边界已应用的温度和压力换算；结果写入含湿量草稿，需在设备面板应用。',
      `<label class="field"><span>压力边界</span><select name="instance">${nodes.map(n=>option(n.id,n.name,nodes[0].id)).join('')}</select></label>${field('rh','相对湿度 / %',50,'type="number" min="0" max="100" step="any"')}`,async data=>{
        const n=nodes.find(item=>item.id===data.instance),canonical=await engine().normalize(p);
        const input=canonical.instances.find(item=>item.id===n.id).parameters;
        const response=await engine().request('/air/properties',{input_mode:'ptrh',pressure_pa:input.pressure_pa,temperature_k:input.temperature_k,relative_humidity:Number(data.rh)/100});
        const m=ui.moduleOf(n),spec=(m.manifest||engine().catalog.modules.find(d=>d.id==='source')).parameters.find(s=>s.id==='humidity_ratio_kg_kg');
        const w=response.state.humidity_ratio_kg_kg;n.draft.humidity_ratio_kg_kg=spec?.unit?w/spec.unit.display_scale+spec.unit.display_offset:w;
        persistView(p);msg('含湿量草稿已生成，请在建模设备面板应用。');ui.render();
      },'生成草稿');
  }
  async function compare() {
    if(!model.comparisonIds.length||model.comparisonIds.length>4)throw Error('请选择 1–4 次运行');
    const descriptor=model.catalog.find(v=>v.key===model.curveKey);if(!descriptor)throw Error('请选择对比变量');
    const key=model.curveKey,pid=project().id,ticket=++model.epoch;
    controller?.abort();controller=new AbortController();const signal=controller.signal;
    const results=await Promise.all(model.comparisonIds.map(async id=>{
      const [catalog,data]=await Promise.all([engine().request(`/runs/${id}/air-variables`,undefined,signal),engine().request(`/runs/${id}/overview`,undefined,signal)]);
      const other=catalog.variables.find(v=>v.key===key);
      if(!other||JSON.stringify([other.contract_version,other.unit,other.mass_basis])!==JSON.stringify([descriptor.contract_version,descriptor.unit,descriptor.mass_basis]))throw Error('运行变量、单位或质量基准不兼容');
      return {id,stride:data.stride,unit:descriptor.unit?.display_unit||'',points:data.rows.map(frame=>[frame.time_s,raw(key,frame)]).filter(([,v])=>Number.isFinite(v)).map(([t,v])=>[t,v/descriptor.unit.display_scale+descriptor.unit.display_offset])};
    }));
    if(ticket!==model.epoch||project().id!==pid||!active())return;
    model.curves=results;view(project()).comparison_run_ids=[...model.comparisonIds];view(project()).observed_keys=[key];persistView(project());ui.render();
  }
  async function migrateLegacy() {
    const p=project(),key=ui.projectKey(p);
    if(p.run.live)throw Error('请先停止旧运行再迁移');
    const canonical=await engine().normalize(p);
    const preview=await engine().request('/air/migrations/preview',{project:canonical,upgrade_official_modules:true});
    const backup=clone(engine().projectDocument(p));
    ui.openDialog('湿空气项目迁移预览','原始项目将先下载备份，应用后保存为新修订；历史运行保持原始口径。',
      '<ul>'+preview.changes.map(text=>'<li>'+esc(text)+'</li>').join('')+'</ul>'+preview.diagnostics.map(d=>'<p>'+esc(d.message)+'</p>').join(''),()=>{
        if(ui.projectKey(p)!==key)throw Error('预览期间项目已改变，请重新预览');
        if(!preview.valid)throw Error('请先处理预览中的模块或参数问题');
        ui.download('湿空气迁移前-'+p.id+'.json',JSON.stringify(backup,null,2));
        const next=preview.project;p.solverOptions=next.solver;p.solver.moduleMixedJacobian=false;p.moduleSnapshots ||= {};
        for(const definition of next.modules){const m=engine().moduleFromManifest(definition);m.frozen=definition.runtime==='python';p.moduleSnapshots[m.id]=m;}
        for(const node of p.pages.flatMap(pg=>pg.nodes)){
          const inst=next.instances.find(i=>i.id===node.id),definition=next.modules.find(m=>m.id===inst.module_id);
          node.params=Object.fromEntries(definition.parameters.map(spec=>{const value=inst.parameters[spec.id]??spec.default;return [spec.id,spec.unit?value/spec.unit.display_scale+spec.unit.display_offset:value];}));
          node.draft=clone(node.params);
        }
        persistView(p);invalidate();ui.render();msg('迁移已应用到草稿，请保存新修订并重新计算。');
      },'备份并应用迁移');
  }
  async function action(action,el) {
    const p=project();
    if(action==='air-create'){ui.openDialog('创建风侧示例','选择一个规范算例作为起点。',`<label class="field"><span>示例</span><select name="example" aria-label="风侧示例">${examples.map(([key,label])=>option(key,label,examples[0][0])).join('')}</select></label>`,data=>createExample(data.example),'创建项目');return;}
    if(action==='air-config'){configure();return;}
    if(action==='air-migrate'){await migrateLegacy();return;}
    if(action==='air-humidity'){humidityInput();return;}
    if(action==='air-run'){model.selectedRunId='';await engine().command('project','run',p.id);invalidate();ui.render();return;}
    if(action==='air-stop'){await engine().command('project','stop',p.id);invalidate();ui.render();return;}
    if(action==='air-save'){await engine().saveProject(p);msg('风侧项目已保存');return;}
    if(action==='air-tab'){view(p).active_tab=el.dataset.value;persistView(p);ui.render();return;}
    if(action==='air-compare'){await compare();return;}
    if(action==='air-report'){
      const id=model.record?.id;if(!id)throw Error('请先选择运行');
      const type=el.dataset.format,response=await fetch(`/api/v1/runs/${id}/report.${type}`,{headers:engine().authHeaders()});
      if(!response.ok){const error=await response.json();throw Error(error.detail?.message||error.detail||'报告读取失败');}
      ui.download(`风侧报告-${id.slice(0,8)}.${type}`,await response.text(),type==='csv'?'text/csv;charset=utf-8':'text/html;charset=utf-8');
    }
  }
  function afterRender() {
    if(!active()){controller?.abort();clearTimeout(timer);model.signature='';return;}
    const root=document.getElementById('air-page');if(!root)return;
    root.onchange=event=>{
      const target=event.target,p=project();
      if(target.matches('[data-air-project]')){forgetProject();ui.openProject(target.value);ui.navigate('air');ui.persist();return;}
      if(target.matches('[data-air-source]')){model.selectedRunId=target.value;invalidate();ui.render();return;}
      if(target.matches('[data-air-device]')){view(p).selected_instance_ids=target.value?[target.value]:[];persistView(p);ui.render();}
      if(target.matches('[data-air-search]')){model.search=target.value;ui.render();}
      if(target.matches('[data-air-curve-key]')){model.curveKey=target.value;model.curves=[];}
      if(target.matches('[data-air-compare-id]')){const ids=model.comparisonIds.filter(id=>id!==target.dataset.airCompareId);if(target.checked)ids.push(target.dataset.airCompareId);if(ids.length>4){target.checked=false;msg('最多叠加四次运行',true);return;}model.comparisonIds=ids;}
    };
    load();
  }
  return {markup,afterRender,action,refresh:()=>{if(active())load();},createExample};
};
