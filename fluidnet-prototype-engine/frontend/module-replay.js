/* Isolated failure inspection. Snapshots stay outside project and library drafts. */
export const createModuleReplayUI = ({request,render,navigate,download,message,route=()=>null}) => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let current=null, generation=0, archiveGeneration=0;
  function load(snapshot,diagnostics=[]) {
    if(!snapshot?.module || !snapshot.execution)throw Error('此错误没有完整的失败回调输入，无法精确复现。');
    current={snapshot:clone(snapshot),diagnostics:clone(diagnostics),result:null,busy:false,error:''};
    generation++;archiveGeneration++;navigate('bench');
  }
  const button=(action,label,disabled=false)=>`<button type="button" class="btn small" data-action="${action}" ${disabled?'disabled':''}>${label}</button>`;
  const values=(title,data)=>`<details class="panel" open><summary class="panel-head">${esc(title)}</summary><div class="table-wrap"><table><thead><tr><th>字段（引擎单位）</th><th>捕获值</th></tr></thead><tbody>${Object.entries(data||{}).map(([key,value])=>`<tr><td class="mono">${esc(key)}</td><td class="mono" style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(typeof value==='object'?JSON.stringify(value,null,2):value)}</td></tr>`).join('')||'<tr><td colspan="2">无捕获字段</td></tr>'}</tbody></table></div></details>`;
  function body(){
    if(!current)return '';
    const {snapshot:s,diagnostics,result,busy,error}=current,info=s.execution;
    const line=(result?.diagnostics||diagnostics).find(d=>d.source_line)?.source_line;
    return `<div class="page-shell" data-module-replay><div class="row spread"><h1>失败回调复现</h1>${button('close-module-replay','返回普通验证台')}</div>
      <p>在独立 Worker 中执行捕获时的回调。使用下列冻结代码和输入；仅恢复受管理输入，self、全局变量与外部副作用不在恢复范围。</p>
      <section class="panel"><div class="panel-body stack"><strong>${esc(s.module.name||s.module.id)} · v${esc(s.module.version)} · ${esc(info.instance_id)}</strong>
      <span>阶段 ${esc(info.phase)} · 失败试算 t = ${esc(info.time_s)} s · 最近接受 ${info.accepted_time_s==null?'时刻未记录':'t = '+esc(info.accepted_time_s)+' s'}</span>
      <small class="mono" style="overflow-wrap:anywhere">定义哈希 ${esc(s.definition_hash)}<br>源码哈希 ${esc(s.content_hash)}</small>
      <div class="row">${button('run-module-replay',busy?'正在复现…':'执行冻结回调',busy)}${button('download-module-replay','导出失败输入')}</div>
      <output data-replay-result role="status">${esc(error || (result ? result.status==='failed'?(result.matched_failure?'已复现同一回调错误':'本次触发了不同错误，请检查诊断'):'本次回调完成；不代表原网络已修复' : '尚未执行；检查输入后点击执行。'))}</output>
      ${(result?.diagnostics||diagnostics).map(d=>`<p>${esc(d.source_file||'')}${d.source_line?':'+esc(d.source_line):''} · ${esc(d.phase||info.phase)} · ${esc(d.message)}</p>`).join('')}
      </div></section><div class="stack" style="margin-top:16px">${values('参数',s.parameters)}${values('调用前状态副本',s.state)}${values('失败端口输入',s.ports)}${values('失败通路输入',s.channels)}${values('工质与执行上下文',{fluid:s.fluid,port_fluids:s.port_fluids,execution:info,dt_s:s.dt_s,iteration_id:s.iteration_id})}
      ${s.refrigeration?values('制冷边界',s.refrigeration):''}${result?.result?values('本次回调输出',result.result):''}
      <details class="panel" open><summary class="panel-head">冻结 module.py · 只读</summary><pre data-replay-source style="margin:0;padding:16px;overflow:auto;max-height:480px">${String(s.module.source?.runtime||'').split('\n').map((text,i)=>`<span ${i+1===line?'data-replay-error-line style="background:var(--orange-soft);display:block"':''}>${i+1}: ${esc(text)}</span>`).join('\n')}</pre></details></div></div>`;
  }
  async function run(){
    if(!current||current.busy)return;
    const owner=current,ticket=generation;owner.busy=true;owner.error='';render();
    try{const result=await request('/modules/replay',{replay:clone(owner.snapshot)});if(ticket===generation)owner.result=result;}
    catch(error){if(ticket===generation)owner.error=error.message;}
    finally{owner.busy=false;if(current===owner&&(route()===null||route()==='bench'))render();}
  }
  async function archive(id){
    // Loading another archive does not own or invalidate the currently running replay.
    const ticket=++archiveGeneration,origin=route();
    const active=()=>ticket===archiveGeneration&&route()===origin;
    try{const result=await request('/runs/'+encodeURIComponent(id)+'/module-failure');if(active())load(result.replay,result.diagnostics||[]);}
    catch(error){if(active())message(error.message,true);}
  }
  function navigationChanged(){archiveGeneration++;}
  function close(){current=null;generation++;archiveGeneration++;render();}
  function exportInput(){if(current)download('module-failure.json',JSON.stringify(current.snapshot,null,2));}
  return {load,body,run,archive,close,exportInput,navigationChanged,get active(){return !!current;}};
};

export default createModuleReplayUI;
