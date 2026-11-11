export const createSystemInspection = ({engine,project,openDialog,closeDialog=()=>{},esc,btn,locate,download}) => {
  let generation=0;
  const value=v=>v.value==null?'未知':Number(v.value).toLocaleString('zh-CN',{maximumSignificantDigits:8})+' '+v.unit;
  function curve(c){
    if(!c.working_curve?.length||!c.ordinate_unit)return '';
    const xs=c.working_curve.map(p=>p[0]),ys=c.working_curve.map(p=>p[1]);
    const maxX=Math.max(...xs,c.volume_flow_m3_h||0,1),maxY=Math.max(...ys,c.working_ordinate||0,1);
    const x=n=>45+500*n/maxX,y=n=>200-165*n/maxY;
    const path=c.working_curve.map((p,i)=>`${i?'L':'M'}${x(p[0])},${y(p[1])}`).join(' ');
    return `<svg viewBox="0 0 600 240" role="img" aria-label="冻结曲线与实际工作点" style="max-width:600px;width:100%"><path d="M45 20V200H555" fill="none" stroke="currentColor"/><path d="${path}" fill="none" stroke="#3786ad" stroke-width="2"/>${Number.isFinite(c.volume_flow_m3_h)&&Number.isFinite(c.working_ordinate)?`<circle cx="${x(c.volume_flow_m3_h)}" cy="${y(c.working_ordinate)}" r="5" fill="#bf650e"/>`:''}<text x="50" y="15" fill="currentColor">${esc(c.ordinate_unit)}</text><text x="430" y="228" fill="currentColor">Q (m³/h)</text></svg>`;
  }
  const table=values=>`<div class="table-wrap"><table><thead><tr><th>物理量 / 来源键</th><th>采样值</th><th>来源</th></tr></thead><tbody>${values.map(v=>`<tr><td>${esc(v.label)}<small class="mono">${esc(v.key)}</small></td><td>${esc(value(v))}</td><td>${esc(v.source)}</td></tr>`).join('')||'<tr><td colspan="3">该帧未提供账本量，保持未知。</td></tr>'}</tbody></table></div>`;
  function preflightSummary(data){
    const counts={error:0,warning:0,info:0};
    for(const diagnostic of data.diagnostics)counts[diagnostic.severity||'error']++;
    const passed=data.valid&&!counts.error;
    const details=[counts.error&&`${counts.error} 项错误`,counts.warning&&`${counts.warning} 项警告`,counts.info&&`${counts.info} 项提示`].filter(Boolean).join(' · ');
    return `<section class="panel" data-inspection-summary><div class="panel-body"><h3>${passed?'连接与参数检查通过':'连接与参数需要处理'}</h3><p>${passed?'回到工作台后可点击运行。':counts.error?'请先处理下方错误，再重新检查。':'请查看下方诊断，调整后重新检查。'}</p>${details?`<p class="muted">${details}${passed&&counts.warning?'；请确认警告中的适用条件。':''}</p>`:''}<button type="button" class="btn primary" data-inspection-return>返回工作台</button></div></section>`;
  }
  function show(data){
    const html=`<div data-system-inspection>${data.run_id?'<p>冻结运行 '+esc(data.run_id)+' · '+esc(data.status)+' · t='+esc(data.time_s)+' s</p>':preflightSummary(data)}
      ${(data.notes||[]).map(n=>`<p class="muted">${esc(n)}</p>`).join('')}
      <h3>诊断与定位</h3><div class="stack">${data.diagnostics.map(d=>`<div class="list-row"><div class="grow"><strong>${data.run_id?esc(d.code):({error:'错误',warning:'警告',info:'提示'}[d.severity]||'错误')} · ${esc(d.message)}</strong><small>${esc([!data.run_id&&d.code,d.instance_id,d.field,d.phase].filter(Boolean).join(' · '))}</small></div>${d.instance_id?`<button type="button" class="btn small" data-inspection-locate="${esc(d.instance_id)}">定位设备</button>`:''}</div>`).join('')||'<p>没有该次检查的错误或警告。</p>'}</div>
      <h3>回路</h3>${data.circuits.map(c=>`<details><summary>${esc(c.id)} · ${esc(c.fluid?.fluid||'未识别')}</summary><p>${esc(c.basis||'编译器回路')}</p><p class="mono">${esc(c.ports.join('，'))}</p></details>`).join('')||'<p>尚无可用回路。</p>'}
      ${data.run_id?'<h3>系统守恒与库存账本</h3>'+table(data.balances):''}
      ${data.devices.map(d=>`<details class="panel" data-inspection-device="${esc(d.instance_id)}"><summary class="panel-head">${esc(d.instance_id+' · '+d.name)} · v${d.version}</summary><div class="panel-body">${d.assumptions.map(a=>`<p>${esc(a)}</p>`).join('')}${table(d.values)}${d.curves.map(c=>`<h4>${esc(c.key)}</h4><p>${esc(c.note)}</p>${curve(c)}<p>参考曲线 ${esc(JSON.stringify(c.points))}</p><p>当前体积流量 ${esc(c.volume_flow_m3_h??'未知')} m³/h · ${c.ordinate_unit==='Pa'?'压升 '+esc(c.pressure_rise_pa??'未知')+' Pa':'扬程 '+esc(c.head_m??'未知')+' m'} · 转速比 ${esc(c.speed_ratio)}</p>`).join('')}</div></details>`).join('')}
      ${data.run_id?btn('inspection-export','导出诊断 JSON','Download','','small')+btn('inspection-compare','与另一运行比较','ArrowRightLeft','','small'):''}</div>`;
    openDialog(data.run_id?'系统检查与结果解释':'连接与参数检查',data.run_id?data.project_id:'根据当前已应用参数与设备连接检查',html,null,'',true);
    const panel=document.querySelector('[data-system-inspection]');
    panel.addEventListener('click',e=>{
      if(e.target.closest('[data-inspection-return]')){generation++;closeDialog();return;}
      const target=e.target.closest('[data-inspection-locate]');if(target)locate(data.project_id,target.dataset.inspectionLocate);
      if(e.target.closest('[data-action="inspection-compare"]'))compare(data.run_id);
      if(e.target.closest('[data-action="inspection-export"]'))download('inspection-'+data.run_id+'.json',JSON.stringify(data,null,2));
    });
  }
  async function check(){
    const owner=project(),ticket=++generation;
    openDialog('系统预检','正在检查当前已应用设备参数与连接','<p data-inspection-loading>正在检查…</p>');
    try{const canonical=await engine().normalize(owner);const result=await engine().request('/project-inspection',canonical);
      if(generation===ticket&&project()===owner&&document.querySelector('[data-inspection-loading]')){engine().cacheCircuits(owner,result.circuits);show(result);}
    }catch(e){if(generation===ticket&&document.querySelector('[data-inspection-loading]'))openDialog('系统预检未完成','',`<p>${esc(e.message)}</p>`);}
  }
  async function run(id){
    const ticket=++generation;openDialog('系统结果解释','正在读取冻结运行','<p data-inspection-loading>正在读取…</p>');
    try{const data=await engine().request('/runs/'+encodeURIComponent(id)+'/inspection');if(generation===ticket&&document.querySelector('[data-inspection-loading]'))show(data);}
    catch(e){if(generation===ticket&&document.querySelector('[data-inspection-loading]'))openDialog('系统结果未读取','',`<p>${esc(e.message)}</p>`);}
  }
  async function compare(id){
    const ticket=++generation;openDialog('选择对照运行','读取运行目录','<p data-inspection-loading>正在读取…</p>');
    try{const records=await engine().request('/runs');
      if(ticket!==generation||!document.querySelector('[data-inspection-loading]'))return;
      const others=records.runs.filter(r=>r.id!==id&&['completed','failed','cancelled','interrupted'].includes(r.status));
      if(!others.length)throw Error('请先完成另一运行再比较');
      openDialog('选择对照运行','按同一实例变量键和规范单位比较两个末帧；输入条件可能不同。',`<label class="field"><span>右侧运行</span><select name="other">${others.map(r=>`<option value="${esc(r.id)}">${esc(r.name+' · '+r.id)}</option>`).join('')}</select></label>`,values=>{
        openDialog('冻结运行差值','读取两份冻结记录','<p data-inspection-loading>正在比较…</p>');
        engine().request('/inspection/compare?a='+encodeURIComponent(id)+'&b='+encodeURIComponent(values.other)).then(result=>{
          if(ticket!==generation||!document.querySelector('[data-inspection-loading]'))return;
          openDialog('冻结运行差值',id+' → '+values.other,`<div data-system-comparison>${result.notes.map(n=>`<p>${esc(n)}</p>`).join('')}<div class="table-wrap"><table><thead><tr><th>变量</th><th>左侧</th><th>右侧</th><th>差值</th><th>单位</th></tr></thead><tbody>${result.differences.map(r=>`<tr><td>${esc(r.key)}</td><td>${esc(r.left??'未知')}</td><td>${esc(r.right??'未知')}</td><td>${esc(r.difference??r.reason)}</td><td>${esc(r.unit)}</td></tr>`).join('')}</tbody></table></div></div>`,null,'',true);
        }).catch(e=>{if(ticket===generation&&document.querySelector('[data-inspection-loading]'))openDialog('比较未完成','',`<p>${esc(e.message)}</p>`);});
      },'比较',true);
    }catch(e){openDialog('比较未完成','',`<p>${esc(e.message)}</p>`);}
  }
  return {check,run};
};

export default createSystemInspection;
