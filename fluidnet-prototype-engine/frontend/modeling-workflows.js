/* Project revisions, module upgrades, scenarios and archived-run comparison. */
window.createModelingWorkflows = function (ui) {
  const {esc,btn,openDialog,closeDialog,msg,clone,uid}=ui;
  const state=ui.state,engine=ui.engine;
  let scenarioDraft=null,upgradePlan=null,comparison=null,compareKey='';
  const owner=id=>state().projects.find(p=>p.id===id)||ui.project();
  const option=(value,label,selected)=>`<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`;
  const input=(name,label,value)=>`<label class="field"><span>${esc(label)}</span><input name="${name}" aria-label="${esc(label)}" value="${esc(value??'')}" required></label>`;
  function idle(p){if(['running','solving'].includes(p.run.status)||(p.run.live&&p.run.runId&&p.run.status==='paused'))throw Error('请先停止项目运行，再更改项目、模块版本或工况。');}
  const nodes=p=>p.pages.flatMap(pg=>pg.nodes);
  function applyDocument(document,receipt){
    const current=state(),next=clone(current),p=clone(document.project);
    localStorage.setItem('fluidnet-prototype-engine-v1-before-project',JSON.stringify(current));
    p.moduleSnapshots={...Object.fromEntries(document.modules.map(m=>[m.id,clone(m)])),...(p.moduleSnapshots||{})};
    p.run=ui.emptyRun();
    const index=next.projects.findIndex(item=>item.id===p.id);
    if(index<0)next.projects.push(p);else next.projects[index]=p;
    if(next.projects.length>20)throw Error('最多保存 20 个项目');
    for(const field of ['modules','models']){
      const ids=new Set(next[field].map(m=>m.id));next[field].push(...clone(document[field].filter(m=>!ids.has(m.id))));
    }
    next.charts.extra=next.charts.extra.filter(c=>c.projectId!==p.id).concat(clone(document.charts));
    next.activeProject=p.id;
    if(receipt){next.projectRevisions||={};next.projectRevisions[p.id]=receipt.revision;}
    ui.replaceState(next);ui.dirty(ui.project());ui.persist();ui.render();
  }
  function manage(p){
    openDialog('管理项目',p.name,`<div class="stack"><p>项目修订 ${state().projectRevisions?.[p.id]||'尚未保存'}</p><div class="row wrap">${btn('wf-save','保存此项目','Save',`data-id="${p.id}"`,'primary')}${btn('wf-rename','重命名','Pencil',`data-id="${p.id}"`)}${btn('wf-export','导出此项目','Download',`data-id="${p.id}"`)}${btn('wf-export-canonical','导出计算项目','FileJson',`data-id="${p.id}"`)}${btn('wf-history','项目修订','History',`data-id="${p.id}"`)}${btn('wf-upgrades','模块版本','Box',`data-id="${p.id}"`)}${btn('create-composite','封装设备组','Network')}${btn('wf-scenarios','工况','SlidersHorizontal',`data-id="${p.id}"`)}${btn('wf-delete','删除项目','Trash2',`data-id="${p.id}"`)}</div></div>`);
  }
  function scenarioList(p){
    openDialog('项目工况',p.name,`<div class="stack">${btn('wf-new-scenario','新建工况','Plus',`data-id="${p.id}"`,'primary')}<p>覆盖值使用参数面板的显示单位，基础模型参数保持独立。</p>${(p.scenarios||[]).map(s=>`<div class="row spread"><span>${esc(s.name)} · ${Object.keys(s.overrides).length} 个设备</span><div class="row">${btn('wf-edit-scenario','编辑','Pencil',`data-id="${p.id}" data-scenario="${esc(s.id)}"`)}${btn('wf-copy-scenario','复制','Copy',`data-id="${p.id}" data-scenario="${esc(s.id)}"`)}${btn('wf-delete-scenario','删除','Trash2',`data-id="${p.id}" data-scenario="${esc(s.id)}"`)}</div></div>`).join('')||'<p>暂无工况，运行时使用基础模型。</p>'}</div>`,null,'',true);
  }
  function overrideRows(){
    return Object.entries(scenarioDraft.value.overrides).flatMap(([id,values])=>Object.entries(values).map(([key,value])=>`<div class="row spread"><span>${esc(id)} · ${esc(key)} = ${esc(typeof value==='object'?JSON.stringify(value):String(value))}</span>${btn('wf-remove-override','移除','X',`data-node="${esc(id)}" data-param="${esc(key)}"`)}</div>`)).join('')||'<p class="muted">尚无覆盖值。</p>';
  }
  function overrideEditor(){
    const p=owner(scenarioDraft.projectId),node=nodes(p).find(n=>n.id===scenarioDraft.node)||nodes(p)[0];
    const select=document.getElementById('wf-param');if(!select||!node)return;
    scenarioDraft.node=node.id;const specs=ui.paramSpecs(node);
    select.innerHTML=specs.map(s=>option(s.id,`${s.label}${s.unit?.display_unit?' / '+s.unit.display_unit:''}`,scenarioDraft.param)).join('');
    scenarioDraft.param=select.value;
    const spec=specs.find(s=>s.id===select.value),field=document.getElementById('wf-value');
    field.value=JSON.stringify(scenarioDraft.value.overrides[node.id]?.[select.value]??node.params[select.value]??spec?.default);
    if(spec?.value_type==='text')field.value=scenarioDraft.value.overrides[node.id]?.[select.value]??node.params[select.value]??'';
    document.getElementById('wf-value-hint').textContent=spec?.value_type==='curve'?'输入 [流量, 扬程] 点对数组':spec?.value_type==='boolean'?'输入 true 或 false':`类型：${spec?.value_type||'number'}；单位：${spec?.unit?.display_unit||'无量纲'}`;
  }
  function scenarioEditor(p,s){
    idle(p);scenarioDraft={projectId:p.id,value:clone(s),node:nodes(p)[0]?.id,param:''};
    openDialog('编辑工况',p.name,`<div class="stack">${input('scenario-name','工况名称',s.name)}<div id="wf-overrides">${overrideRows()}</div><div class="fields"><label class="field"><span>设备</span><select id="wf-node" data-wf-node aria-label="工况设备">${nodes(p).map(n=>option(n.id,n.id+' · '+n.name)).join('')}</select></label><label class="field"><span>参数</span><select id="wf-param" data-wf-param aria-label="工况参数"></select></label>${input('override-value','覆盖值','')}<p id="wf-value-hint" class="muted"></p></div>${btn('wf-add-override','加入或更新覆盖值','Plus')}</div>`,data=>{
      const draft=clone(scenarioDraft.value);draft.name=data['scenario-name'].trim();
      if(!draft.name)throw Error('请输入工况名称');
      const candidate=clone(p);candidate.scenarios=(candidate.scenarios||[]).filter(v=>v.id!==draft.id).concat(draft);
      const key=ui.projectKey(p);
      engine().validateCandidate(candidate).then(result=>{
        if(!result.valid)throw Error(result.diagnostics.filter(d=>d.severity==='error').map(d=>d.message).join('；'));
        idle(p);if(key!==ui.projectKey(p))throw Error('校验期间项目发生变化，请重新编辑工况');
        p.scenarios=candidate.scenarios;p.activeScenarioId=draft.id;ui.dirty(p);ui.persist();ui.render();msg('工况已应用，保存项目后可在重启后继续使用。');
      }).catch(error=>msg(error.message,true));
    },'校验并应用',true);
    const field=document.querySelector('[name="override-value"]');field.id='wf-value';field.required=false;
    overrideEditor();
  }
  async function moduleVersions(p,id){
    idle(p);const result=await engine().moduleReleases(id),bound=p.moduleSnapshots[id];
    openDialog('选择模块版本',`${p.name} · ${id} 当前 v${bound.version}`,`<div class="stack">${result.versions.map(v=>`<div class="row spread"><span>v${esc(v.package.version)} · ${esc(v.release_notes||'示例版本')}</span>${btn('wf-preview-upgrade','预览变更','Eye',`data-id="${p.id}" data-module="${id}" data-version="${parseInt(v.package.version)}" ${parseInt(v.package.version)===bound.version?'disabled':''}`)}</div>`).join('')}<label class="field"><span>显式映射 JSON（可留空）</span><textarea id="wf-migration-json" aria-label="显式迁移映射" placeholder="参数、端口、通路和变量映射"></textarea></label></div>`);
  }
  async function previewUpgrade(p,id,version,migration=null){
    idle(p);const original=JSON.stringify(engine().projectDocument(p));
    const result=await engine().previewUpgrade(p,id,version,migration);
    if(original!==JSON.stringify(engine().projectDocument(p)))throw Error('项目已发生变化，请重新预览');
    upgradePlan={original,result,document:result.compatible?engine().upgradeDocument(p,result):null};
    openDialog('模块版本变更预览',`${id} · v${result.from_version} → v${result.to_version}`,`<div class="stack"><p>${result.compatible?'兼容检查通过；应用前保存当前项目修订。':'此变更不兼容，保留当前项目。'}</p>${result.reasons.map(r=>`<div class="notice">${esc(r)}</div>`).join('')}<p>源码哈希：${esc(result.from_hashes.content_hash)} → ${esc(result.to_hashes.content_hash)}</p><p>定义哈希：${esc(result.from_hashes.definition_hash)} → ${esc(result.to_hashes.definition_hash)}</p>${result.changes.map(c=>`<details><summary>${esc(c.field+'.'+c.id)}</summary><pre class="code-preview">${esc(JSON.stringify({原定义:c.before,新定义:c.after},null,2))}</pre></details>`).join('')}<details><summary>查看源码前后版本</summary><h4>原版本</h4><pre class="code-preview">${esc(result.source_before)}</pre><h4>目标版本</h4><pre class="code-preview">${esc(result.source_after)}</pre></details></div>`,result.compatible?()=>{
      const plan=upgradePlan;
      (async()=>{idle(p);if(plan.original!==JSON.stringify(engine().projectDocument(p)))throw Error('项目已变化，请重新预览');
        const inputKey=ui.projectKey(p);await engine().saveProject(p);idle(p);
        if(inputKey!==ui.projectKey(p))throw Error('保存期间项目已变化，已保留当前草稿，请重新预览');
        const receipt=await engine().saveProject(p,plan.document);
        if(inputKey!==ui.projectKey(p)){ui.persist();throw Error('升级已在服务器保存，当前新草稿已保留；请导出草稿或载入服务器项目。');}
        applyDocument(plan.document,receipt);msg('模块版本已更新并保存，可从项目修订回退。');
      })().catch(error=>msg(error.message,true));
    }:null,'保存修订并应用',true);
  }
  function comparisonPlot(data,key){
    const series=data.map(item=>item.overview.rows.filter(row=>Number.isFinite(row.variables[key])).map(row=>[row.time_s,row.variables[key]]));
    const points=series.flat();if(!points.length)return '<p>所选变量没有可用曲线。</p>';
    const x0=Math.min(...points.map(p=>p[0])),x1=Math.max(x0+1,...points.map(p=>p[0]));
    const y0=Math.min(...points.map(p=>p[1])),y1=Math.max(...points.map(p=>p[1])),span=Math.max(y1-y0,Math.abs(y0)*.01,1e-8);
    return `<svg data-comparison-chart style="width:100%;height:300px;display:block" viewBox="0 0 680 250" role="img" aria-label="两次运行变量曲线"><path d="M 60 15 V 220 H 660" fill="none" stroke="currentColor"/>${series.map((rows,i)=>`<path data-comparison-series="${i}" d="${rows.map(([x,y],j)=>`${j?'L':'M'} ${60+(x-x0)/(x1-x0)*590} ${200-(y-y0)/span*170}`).join(' ')}" fill="none" stroke="${i?'#ce6b13':'#2279bd'}" stroke-width="2.5"/>${rows.length===1?`<circle cx="60" cy="${200-(rows[0][1]-y0)/span*170}" r="4" fill="${i?'#ce6b13':'#2279bd'}"/>`:''}`).join('')}<text x="60" y="244" fill="currentColor">${x0.toFixed(2)} s</text><text x="595" y="244" fill="currentColor">${x1.toFixed(2)} s</text><text x="5" y="28" fill="currentColor" font-size="11">${(y0+span).toPrecision(4)}</text><text x="5" y="205" fill="currentColor" font-size="11">${y0.toPrecision(4)}</text></svg>`;
  }
  function variableInfo(record,key){
    const [id,...parts]=key.split('.'),rest=parts.join('.');
    const node=record.request.project.instances.find(n=>n.id===id),module=record.request.project.modules.find(m=>m.id===node?.module_id);
    const spec=rest.startsWith('param.')?module?.parameters.find(p=>p.id===rest.slice(6)):module?.variables.find(v=>v.id===rest);
    const fallback={mass_flow_kg_s:['质量流量','kg/s'],pressure_pa:['压力','Pa'],temperature_k:['温度','K'],enthalpy_j_kg:['比焓','J/kg'],density_kg_m3:['密度','kg/m³']};
    const suffix=parts.at(-1),entry=fallback[suffix],unit=spec?.unit?.canonical_unit||entry?.[1]||'1';
    return {unit,label:`${node?.name||id} · ${spec?.label||entry?.[0]||rest} (${key}) / ${unit}`};
  }
  function comparisonResult(){
    if(!comparison)return '<p class="muted">选择同一项目的两次已完成运行，查看指标差异和变量曲线。</p>';
    const [a,b]=comparison.map(v=>v.record),keys=Object.keys(a.frame.variables).filter(k=>typeof a.frame.variables[k]==='number'&&typeof b.frame.variables[k]==='number'&&variableInfo(a,k).unit===variableInfo(b,k).unit);
    if(!keys.length)return '<p>两次运行没有单位一致的公共数值变量。</p>';
    if(!keys.includes(compareKey))compareKey=keys.find(k=>k.split('.').length===2&&k.endsWith('.mass_flow_kg_s'))||keys[0];
    const label=r=>`${r.request.project.name} · ${r.request.project.scenarios.find(s=>s.id===r.request.scenario_id)?.name||'基础模型'} · ${r.request.project_revision?'修订 '+r.request.project_revision:'未保存草稿'} · ${r.id.slice(0,8)}`;
    const metrics=Object.keys(a.frame.metrics).filter(k=>typeof a.frame.metrics[k]==='number'&&typeof b.frame.metrics[k]==='number');
    const valueA=a.frame.variables[compareKey],valueB=b.frame.variables[compareKey];
    return `<div class="stack"><p style="color:#2279bd">A：${esc(label(a))}</p><p style="color:#ce6b13">B：${esc(label(b))}</p><details><summary>查看模块版本</summary>${[a,b].map((r,i)=>`<p>${i?'B':'A'}：${r.request.project.modules.map(m=>`${esc(m.name)} v${m.version}${m.content_hash?' · '+esc(m.content_hash.slice(0,12)):''}`).join('；')}</p>`).join('')}</details><label class="field"><span>比较变量</span><select data-wf-compare-key aria-label="比较变量">${keys.map(k=>option(k,variableInfo(a,k).label,compareKey)).join('')}</select></label><p data-comparison-delta>${esc(variableInfo(a,compareKey).unit)} · A ${Number(valueA).toPrecision(6)} · B ${Number(valueB).toPrecision(6)} · 差值 ${(valueB-valueA).toPrecision(6)}${valueA?' · 变化 '+((valueB-valueA)/Math.abs(valueA)*100).toFixed(2)+'%':''}</p>${comparisonPlot(comparison,compareKey)}<p class="muted">按仿真时间绘制各自已保存的采样点；抽稀步幅 A=${comparison[0].overview.stride}、B=${comparison[1].overview.stride}。</p><table class="data-table"><thead><tr><th>指标</th><th>A</th><th>B</th><th>B − A</th></tr></thead><tbody>${metrics.map(k=>`<tr><td>${esc(k)}</td><td>${a.frame.metrics[k].toPrecision(5)}</td><td>${b.frame.metrics[k].toPrecision(5)}</td><td>${(b.frame.metrics[k]-a.frame.metrics[k]).toPrecision(5)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function comparisonMarkup(){
    const runs=(ui.ui().archivedRuns||[]).filter(r=>r.status==='completed');
    return `<section class="panel" style="margin:18px 0"><div class="panel-head"><h2>两次运行对照</h2>${btn('wf-refresh-runs','刷新档案','RefreshCw')}</div><div class="panel-body stack"><div class="fields"><label class="field"><span>运行 A</span><select id="wf-compare-a" aria-label="运行 A">${runs.map((r,i)=>option(r.id,r.name+' · '+r.id.slice(0,8),comparison?.[0]?.record.id||runs[0]?.id)).join('')}</select></label><label class="field"><span>运行 B</span><select id="wf-compare-b" aria-label="运行 B">${runs.map(r=>option(r.id,r.name+' · '+r.id.slice(0,8),comparison?.[1]?.record.id||runs[1]?.id)).join('')}</select></label></div>${btn('wf-compare','加载对照','ArrowRightLeft','','primary')}<div id="wf-comparison-result">${comparisonResult()}</div></div></section>`;
  }
  async function action(name,el){
    const d=el.dataset,p=owner(d.id);
    switch(name){
      case 'wf-manage':manage(p);break;
      case 'wf-save':await engine().saveProject(p);ui.persist();manage(p);ui.render();msg('项目已保存');break;
      case 'wf-rename':idle(p);openDialog('重命名项目','修改名称后保存此项目。',input('name','项目名称',p.name),data=>{p.name=data.name.trim();ui.dirty(p);ui.render();});break;
      case 'wf-export':ui.download(p.id+'.json',JSON.stringify(engine().projectDocument(p),null,2));break;
      case 'wf-export-canonical':ui.download(p.id+'.engine.json',JSON.stringify(await engine().normalize(p),null,2));break;
      case 'wf-server-projects':{const result=await engine().listProjects();openDialog('服务器项目','载入所选项目，保留其他本地项目。',`<div class="stack">${result.projects.map(v=>`<div class="row spread"><span>${esc(v.name)} · 修订 ${v.revision}</span>${btn('wf-load','载入','FolderOpen',`data-id="${esc(v.id)}"`)}</div>`).join('')||'<p>尚无已保存项目。</p>'}</div>`);break;}
      case 'wf-load':{if(state().projects.some(v=>v.id===d.id))idle(p);const result=await engine().readProject(d.id);applyDocument(result.document,result);closeDialog();msg('项目已载入');break;}
      case 'wf-history':{const data=await engine().projectHistory(p.id);openDialog('项目修订',p.name,`<div class="stack">${data.revisions.map(v=>`<div class="row spread"><span>修订 ${v.revision} · ${esc(v.saved_at)}</span>${btn('wf-restore','恢复','History',`data-id="${p.id}" data-revision="${v.revision}" ${v.deleted?'disabled':''}`)}</div>`).join('')||'<p>请先保存此项目。</p>'}</div>`);break;}
      case 'wf-restore':idle(p);ui.confirm('恢复项目修订','当前项目草稿先保留到浏览器，其他项目和运行档案保留。',()=>{localStorage.setItem('fluidnet-prototype-engine-v1-before-project',JSON.stringify(state()));engine().restoreProject(p.id,Number(d.revision)).then(r=>{applyDocument(r.document,r);msg('项目修订已恢复');}).catch(e=>msg(e.message,true));});break;
      case 'wf-delete':idle(p);if(state().projects.length===1)throw Error('至少保留一个项目');ui.confirm('删除项目',p.name+'；已保存运行档案保留。',()=>{engine().deleteProject(p.id).then(()=>{state().projects=state().projects.filter(v=>v.id!==p.id);state().charts.extra=state().charts.extra.filter(v=>v.projectId!==p.id);if(state().activeProject===p.id)state().activeProject=state().projects[0].id;ui.dirty();ui.persist();ui.render();}).catch(e=>msg(e.message,true));});break;
      case 'wf-import':openDialog('导入单个项目','支持单项目、完整原型和规范 Project JSON，保留固定模块快照。',`<div class="stack"><input type="file" id="wf-import-file" accept=".json,application/json" required aria-label="单项目文件"><label class="field"><span>导入方式</span><select name="mode">${option('copy','创建项目副本','copy')}${option('replace','替换同 ID 项目')}</select></label></div>`,data=>{const file=document.getElementById('wf-import-file').files[0];file.text().then(async text=>{const doc=await engine().exchangeDocument(JSON.parse(text));if(data.mode==='copy'){const old=doc.project.id;doc.project.id=uid('project');doc.project.name+=' 导入';doc.charts.forEach(c=>{if(c.projectId===old)c.projectId=doc.project.id;});}else if(state().projects.some(p=>p.id===doc.project.id))idle(owner(doc.project.id));applyDocument(doc);msg('项目已导入，请保存');}).catch(e=>msg(e.message,true));},'导入');break;
      case 'wf-scenarios':scenarioList(p);break;
      case 'wf-new-scenario':scenarioEditor(p,{id:uid('scenario'),name:'新工况',overrides:{}});break;
      case 'wf-edit-scenario':scenarioEditor(p,p.scenarios.find(s=>s.id===d.scenario));break;
      case 'wf-copy-scenario':{const s=clone(p.scenarios.find(s=>s.id===d.scenario));s.id=uid('scenario');s.name+=' 副本';scenarioEditor(p,s);break;}
      case 'wf-delete-scenario':idle(p);p.scenarios=p.scenarios.filter(s=>s.id!==d.scenario);if(p.activeScenarioId===d.scenario)p.activeScenarioId='';ui.dirty(p);ui.persist();scenarioList(p);ui.render();break;
      case 'wf-add-override':{const p=owner(scenarioDraft.projectId),node=nodes(p).find(n=>n.id===document.getElementById('wf-node').value),key=document.getElementById('wf-param').value,spec=ui.paramSpecs(node).find(s=>s.id===key);if(!spec)throw Error('请选择参数');const raw=document.getElementById('wf-value').value;const value=spec.value_type==='text'?raw:JSON.parse(raw);if(spec.value_type==='number'&&(typeof value!=='number'||!Number.isFinite(value)))throw Error('请输入有限数值');if(spec.value_type==='boolean'&&typeof value!=='boolean')throw Error('请输入 true 或 false');scenarioDraft.value.overrides[node.id]||={};scenarioDraft.value.overrides[node.id][key]=value;document.getElementById('wf-overrides').innerHTML=overrideRows();break;}
      case 'wf-remove-override':delete scenarioDraft.value.overrides[d.node][d.param];if(!Object.keys(scenarioDraft.value.overrides[d.node]).length)delete scenarioDraft.value.overrides[d.node];document.getElementById('wf-overrides').innerHTML=overrideRows();break;
      case 'wf-upgrades':{idle(p);engine().pinProject(p);const modules=Object.values(p.moduleSnapshots||{}).filter(m=>m.runtime==='python');openDialog('项目模块版本',p.name,`<div class="stack">${modules.map(m=>`<div class="row spread"><span>${esc(m.name)} · 绑定 v${m.version}</span>${btn('wf-module-versions','查看可用版本','Box',`data-id="${p.id}" data-module="${esc(m.id)}"`)}</div>`).join('')||'<p>此项目没有绑定 Python 模块。</p>'}</div>`);break;}
      case 'wf-module-versions':await moduleVersions(p,d.module);break;
      case 'wf-preview-upgrade':{const text=document.getElementById('wf-migration-json')?.value.trim();await previewUpgrade(p,d.module,Number(d.version),text?JSON.parse(text):null);break;}
      case 'wf-refresh-runs':await engine().refreshArchives();ui.render();break;
      case 'wf-compare':{const a=document.getElementById('wf-compare-a').value,b=document.getElementById('wf-compare-b').value;if(!a||!b||a===b)throw Error('请选择两次不同的已完成运行');const data=await engine().comparison(a,b);if(data.some(v=>v.record.status!=='completed'))throw Error('只支持已完成运行');if(data[0].record.request.project.id!==data[1].record.request.project.id)throw Error('请选择同一项目的两次运行');comparison=data;document.getElementById('wf-comparison-result').innerHTML=comparisonResult();break;}
    }
  }
  document.getElementById('fn-studio').addEventListener('change',event=>{
    const el=event.target;try{
      if(el.matches('[data-wf-scenario]')){const p=owner(el.dataset.id);idle(p);p.activeScenarioId=el.value;ui.dirty(p);ui.persist();ui.render();}
      if(el.matches('[data-wf-node]')){scenarioDraft.node=el.value;scenarioDraft.param='';overrideEditor();}
      if(el.matches('[data-wf-param]')){scenarioDraft.param=el.value;overrideEditor();}
      if(el.matches('[data-wf-compare-key]')){compareKey=el.value;document.getElementById('wf-comparison-result').innerHTML=comparisonResult();}
    }catch(error){msg(error.message,true);ui.render();}
  });
  return {action,comparisonMarkup,
    projectActions:p=>btn('wf-manage','管理','Settings2',`data-id="${p.id}"`,'small'),
    projectToolbar:()=>btn('wf-server-projects','服务器项目','FolderOpen')+btn('wf-import','导入单项目','Upload'),
    scenarioToolbar:p=>`<label class="row gap-6"><span>工况</span><select data-wf-scenario data-id="${p.id}" aria-label="运行工况">${option('','基础模型',p.activeScenarioId||'')}${(p.scenarios||[]).map(s=>option(s.id,s.name,p.activeScenarioId)).join('')}</select></label>${btn('wf-scenarios','编辑工况','SlidersHorizontal',`data-id="${p.id}"`)}${btn('wf-upgrades','模块版本','Box',`data-id="${p.id}"`)}${btn('nav','批量工况','ListChecks','data-route="batches"')}${btn('create-composite','封装设备组','Network')}`};
};
