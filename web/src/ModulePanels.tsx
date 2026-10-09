import {useEffect, useRef, useState} from 'react';
import {ArrowLeft, Archive, Download, Edit3, FlaskConical, Library, Package, Play, Plus, Save, SkipForward, Square, Upload, X} from 'lucide-react';
import {api, download} from './api';
import {ParameterInput} from './Inspector';
import {TrendChart} from './Charts';
import {displayValue, numberText, statusLabel, variableUnit} from './format';
import {emptyInterface, inferInterface, interfaceOf, templatePayload} from './modules';
import {blankProject, copy, uid, type Catalog, type Group, type History, type ModuleInterface, type Parameters, type Project, type Run, type Template, type TemplateDraft, type Units} from './types';

function moduleGraph(template:TemplateDraft):Project {
  return template.kind==='group'?template.body as Project:{...blankProject(),elements:[template.body as Project['elements'][number]]};
}

export function InterfaceEditor({project,members,value,onChange,catalog,locked=false}:{project:Project;members:string[];value:ModuleInterface;onChange:(v:ModuleInterface)=>void;catalog:Catalog;locked?:boolean}){
  const inside=new Set(members);
  const used=new Set(project.connections.filter(c=>inside.has(c.source)&&inside.has(c.target)).flatMap(c=>[c.source+':'+c.source_port,c.target+':'+c.target_port]));
  const external=new Set(project.connections.filter(c=>inside.has(c.source)!==inside.has(c.target)).map(c=>inside.has(c.source)?c.source+':'+c.source_port:c.target+':'+c.target_port));
  function toggle(kind:'ports'|'parameters',target:string,label:string){
    const next=copy(value);const mapping=kind==='ports'?next.exposed_ports:next.exposed_parameters,labels=kind==='ports'?next.port_labels:next.parameter_labels;
    const existing=Object.entries(mapping).find(([,v])=>v===target)?.[0];
    if(existing){delete mapping[existing];delete labels[existing];}else{const alias=(kind==='ports'?'port_':'param_')+uid().slice(0,8);mapping[alias]=target;labels[alias]=label;}
    onChange(next);
  }
  function rename(kind:'ports'|'parameters',alias:string,label:string){const next=copy(value);(kind==='ports'?next.port_labels:next.parameter_labels)[alias]=label;onChange(next);}
  return <div className="interface-editor">
    <h3>对外流体端口</h3><p className="muted">内部已连接的端口自动隐藏；已有外部连接的接口会保留。接口 ID 固定，显示名称可修改。</p>
    <div className="module-table-wrap"><table className="module-table"><thead><tr><th>暴露</th><th>内部端口</th><th>接口 ID</th><th>显示名称</th></tr></thead><tbody>
      {project.elements.filter(e=>inside.has(e.id)).flatMap(e=>(catalog.components.find(d=>d.type===e.type)?.ports||[]).filter(port=>!used.has(e.id+':'+port.id)).map(port=>{
        const target=e.id+':'+port.id;const alias=Object.entries(value.exposed_ports).find(([,v])=>v===target)?.[0];
        return <tr key={target}><td><input type="checkbox" aria-label={`暴露端口 ${e.name} ${port.id}`} disabled={locked||external.has(target)} checked={!!alias} onChange={()=>toggle('ports',target,e.name+' · '+port.label)}/></td><td>{e.name}<small>{port.label} · {port.id}{port.required?' · 必需':''}</small></td><td><code>{alias||'—'}</code></td><td>{alias&&<input aria-label={'端口名称 '+alias} disabled={locked} value={value.port_labels[alias]||alias} onChange={event=>rename('ports',alias,event.target.value)}/>}</td></tr>;
      }))}
    </tbody></table></div>
    <h3>对外参数</h3><p className="muted">可选择模型已有参数。单位、数值范围和在线调节能力由原元件定义。</p>
    <div className="module-table-wrap"><table className="module-table"><thead><tr><th>暴露</th><th>内部参数</th><th>接口 ID</th><th>显示名称</th></tr></thead><tbody>
      {project.elements.filter(e=>inside.has(e.id)).flatMap(e=>(catalog.components.find(d=>d.type===e.type)?.parameters||[]).map(parameter=>{
        const target=e.id+'.'+parameter.key;const alias=Object.entries(value.exposed_parameters).find(([,v])=>v===target)?.[0];
        return <tr key={target}><td><input type="checkbox" aria-label={`暴露参数 ${e.name} ${parameter.label}`} disabled={locked} checked={!!alias} onChange={()=>toggle('parameters',target,e.name+' · '+parameter.label)}/></td><td>{e.name}<small>{parameter.label}{parameter.runtime?' · 可在线调节':''}</small></td><td><code>{alias||'—'}</code></td><td>{alias&&<input aria-label={'参数名称 '+alias} disabled={locked} value={value.parameter_labels[alias]||alias} onChange={event=>rename('parameters',alias,event.target.value)}/>}</td></tr>;
      }))}
    </tbody></table></div>
  </div>;
}

export function GroupEditor({project,members,group,catalog,onSave,onClose}:{project:Project;members:string[];group:Group|null;catalog:Catalog;onSave:(name:string,ports:ModuleInterface)=>Promise<void>;onClose:()=>void}){
  const[name,setName]=useState(group?.name||'组合设备');
  const[value,setValue]=useState<ModuleInterface>(()=>group?interfaceOf(group):inferInterface(project,members,catalog));
  const[busy,setBusy]=useState(false),[error,setError]=useState('');
  return <><div className="module-action-row"><label>组合名称<input aria-label="组合名称" maxLength={120} value={name} onChange={e=>setName(e.target.value)} disabled={busy}/></label><span>{members.length} 个内部元件</span></div>
    <InterfaceEditor project={project} members={members} value={value} onChange={setValue} catalog={catalog} locked={busy}/>
    {error&&<p className="inline-warning" role="alert">{error}</p>}
    <div className="module-actions"><button className="secondary-button" disabled={busy} onClick={onClose}>取消</button><button className="primary-button" disabled={busy||!name.trim()} onClick={async()=>{setBusy(true);setError('');try{await onSave(name,value);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}><Package size={15}/>{group?'应用接口配置':'封装为组合设备'}</button></div></>;
}

export function GroupInspector({group,project,catalog,units,active,parameters,onParameter,onName,onEnter,onConfigure,onSave,onLibrary,onDissolve,onExpand,onMember}:{group:Group;project:Project;catalog:Catalog;units:Units;active:boolean;parameters:(e:Project['elements'][number])=>Parameters;onParameter:(id:string,key:string,value:Parameters[string])=>void;onName:(v:string)=>void;onEnter:()=>void;onConfigure:()=>void;onSave:()=>void;onLibrary:()=>void;onDissolve:()=>void;onExpand:()=>void;onMember:(id:string)=>void}){
  return <aside className="inspector module-inspector"><div className="panel-heading"><span><Package size={16}/> 组合设备</span><span className="count-badge">{group.element_ids.length}</span></div>
    <div className="selected-device"><span className="device-icon large"><Package size={26}/></span><div><input aria-label="组合设备名称" value={group.name} disabled={active} onChange={e=>onName(e.target.value)}/><span>{group.template_revision?'来源版本 v'+group.template_revision:'独立组合'} · 单层组合</span></div></div>
    <div className="inspector-scroll"><div className="module-button-grid"><button className="secondary-button" onClick={onEnter}><Edit3 size={14}/> 进入内部</button><button className="secondary-button" disabled={active} onClick={onConfigure}>配置接口</button><button className="secondary-button" disabled={active} onClick={onSave}><Save size={14}/> 保存到型号库</button><button className="secondary-button" disabled={active} onClick={onLibrary}><Library size={14}/> 应用型号版本</button></div>
      <section className="property-section"><h3>对外参数</h3>{Object.entries(group.exposed_parameters).map(([alias,target])=>{
        const[eid,key]=target.split('.');const e=project.elements.find(e=>e.id===eid);const def=e&&catalog.components.find(d=>d.type===e.type)?.parameters.find(p=>p.key===key);
        if(!e||!def)return null;return <ParameterInput key={group.id+alias} def={{...def,label:group.parameter_labels[alias]||def.label}} value={parameters(e)[key]??def.default} units={units} atmosphere={project.atmosphere_pa} disabled={active&&!def.runtime} onCommit={value=>onParameter(eid,key,value)}/>;
      })}{!Object.keys(group.exposed_parameters).length&&<p className="muted">在“配置接口”中选择对外参数。</p>}</section>
      <section className="property-section"><h3>对外端口</h3>{Object.entries(group.exposed_ports).map(([alias,target])=><div className="group-port-item" key={alias}><strong>{group.port_labels[alias]||alias}</strong><small>{alias} → {target}</small></div>)}</section>
      <section className="property-section"><h3>内部元件与结果</h3>{project.elements.filter(e=>group.element_ids.includes(e.id)).map(e=><button className="module-member-button" key={e.id} onClick={()=>onMember(e.id)}>{e.name}<span>{catalog.components.find(d=>d.type===e.type)?.name} ↗</span></button>)}</section>
      <button className="secondary-button full" onClick={onExpand}>{group.collapsed?'在主画布展开成员':'折叠为单个设备'}</button>
      <button className="text-button full" disabled={active} onClick={onDissolve}>解散组合并保留元件</button>
    </div></aside>;
}

export function TemplateLibrary({items,disabled,onEdit,onInsert,onApply,onRefresh,canApply,onError}:{items:Template[];disabled:boolean;onEdit:(t:Template)=>void;onInsert:(t:Template)=>void;onApply:(t:Template)=>void;onRefresh:()=>void;canApply:boolean;onError:(e:unknown)=>void}){
  const[search,setSearch]=useState(''),[archived,setArchived]=useState(false),[all,setAll]=useState<Template[]>([]);
  const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{if(archived)api<Template[]>('/templates?include_archived=true').then(setAll).catch(onError);},[archived,items]);
  const visible=(archived?all:items).filter(t=>t.name.toLowerCase().includes(search.toLowerCase()));
  return <><div className="module-action-row"><input aria-label="搜索型号" placeholder="搜索设备型号或组合…" value={search} onChange={e=>setSearch(e.target.value)}/><label><input type="checkbox" checked={archived} onChange={e=>setArchived(e.target.checked)}/> 显示已归档</label><button className="secondary-button" disabled={disabled} onClick={()=>input.current?.click()}><Upload size={14}/> 导入型号 JSON</button></div>
    <input className="hidden" type="file" accept=".json" ref={input} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;try{const raw=JSON.parse(await file.text());const normalized=await api<TemplateDraft>('/modules/normalize',templatePayload(raw));await api('/templates',{...templatePayload(normalized),revision:0});onRefresh();}catch(error){onError(error);}finally{e.target.value='';}}}/>
    <div className="template-grid">{visible.map(t=><article className={`template-card ${t.archived?'archived':''}`} key={t.id} data-testid={'template-'+t.id}><span className="device-icon"><Package size={24}/></span><h3>{t.name}</h3><p>{t.kind==='group'?`${(t.body as Project)?.elements?.length??0} 个内部元件`:'设备参数型号'} · v{t.revision}{t.archived?' · 已归档':''}</p><p>{Object.keys(t.interface?.exposed_ports||{}).length} 个接口 · {Object.keys(t.interface?.exposed_parameters||{}).length} 个对外参数</p>
      {t.validation_error&&<p className="inline-warning" role="alert">型号定义需要修复：{t.validation_error}。可导出后修正并重新导入。</p>}
      <div className="template-card-actions"><button className="secondary-button" disabled={!!t.validation_error} onClick={()=>onEdit(t)}><Edit3 size={14}/> 编辑与验证</button><button className="primary-button" disabled={disabled||t.archived||!!t.validation_error} onClick={()=>onInsert(t)}><Plus size={14}/> 插入</button><button className="text-button" disabled={disabled||!canApply||t.archived||!!t.validation_error} onClick={()=>onApply(t)}>应用到选中实例</button><button className="text-button" onClick={()=>download(t.name+'.fluidnet-template.json',JSON.stringify({...templatePayload(t),revision:0},null,2))}><Download size={13}/> 导出</button>{!t.archived&&<button className="text-button" disabled={disabled} onClick={async()=>{try{await api('/templates/'+t.id+'?revision='+t.revision,undefined,'DELETE');onRefresh();}catch(e){onError(e);}}}><Archive size={13}/> 归档</button>}</div>
    </article>)}</div>{!visible.length&&<div className="empty-notice">尚无匹配型号。可先在画布中保存设备或封装组合。</div>}
  </>;
}

export function TemplateEditor({initial,catalog,units,onSaved,onInsert,onBack,onApply,canApply}:{initial:TemplateDraft;catalog:Catalog;units:Units;onSaved:(t:Template)=>void;onInsert:(t:TemplateDraft,enter:boolean)=>void;onBack:()=>void;onApply:(t:TemplateDraft)=>void;canApply:boolean}){
  const[draft,setDraft]=useState(()=>copy(initial)),[tab,setTab]=useState<'parameters'|'interface'|'test'>('parameters');
  const[versions,setVersions]=useState<{revision:number;created:number}[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[running,setRunning]=useState(false);
  const[baseline,setBaseline]=useState('updated' in initial?JSON.stringify(templatePayload(initial)):'');
  const graph=moduleGraph(draft);
  useEffect(()=>{if(draft.id)api<typeof versions>('/templates/'+draft.id+'/versions').then(setVersions).catch(e=>setError(e.message));},[draft.id,draft.revision]);
  function parameter(id:string,key:string,value:Parameters[string]){setDraft(current=>{const next=copy(current);const elements=next.kind==='group'?(next.body as Project).elements:[next.body as Project['elements'][number]];elements.find(e=>e.id===id)!.parameters[key]=value;return next;});}
  async function save(asNew=false){setBusy(true);setError('');try{const existing=draft.id&&!asNew;const saved=await api<Template>(existing?'/templates/'+draft.id:'/templates',{...templatePayload(draft),revision:existing?draft.revision:0},existing?'PUT':'POST');setDraft(copy(saved));setBaseline(JSON.stringify(templatePayload(saved)));onSaved(saved);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <div className="template-editor"><div className="module-action-row"><button className="text-button" disabled={running||busy} onClick={onBack}><ArrowLeft size={15}/> 型号库</button><input aria-label="型号名称" value={draft.name} maxLength={120} disabled={running||busy} onChange={e=>setDraft(d=>({...d,name:e.target.value}))}/>{draft.id&&<select aria-label="型号版本" value={draft.revision} disabled={busy||running} onChange={async e=>{setError('');setBusy(true);try{const loaded=await api<Template>('/templates/'+draft.id+'?revision='+e.target.value);setDraft(loaded);setBaseline(JSON.stringify(templatePayload(loaded)));}catch(error){setError((error as Error).message);}finally{setBusy(false);}}}>{versions.map(v=><option key={v.revision} value={v.revision}>v{v.revision} · {new Date(v.created*1000).toLocaleDateString()}</option>)}</select>}</div>
    <div className="module-tabs"><button className={tab==='parameters'?'active':''} onClick={()=>setTab('parameters')}>设备参数</button><button className={tab==='interface'?'active':''} onClick={()=>setTab('interface')}>端口与参数接口</button><button className={tab==='test'?'active':''} onClick={()=>setTab('test')}><FlaskConical size={15}/> 独立验证</button></div>
    {tab==='parameters'&&<div className="module-parameters"><p className="muted">这里编辑型号的基础参数。已有项目实例保持独立，更新后可手动应用版本。</p>{graph.elements.map(element=>{const def=catalog.components.find(d=>d.type===element.type);if(!def)return null;return <details key={element.id} open={graph.elements.length===1}><summary>{element.name||def.name}<span>{def.name}</span></summary><div className="module-parameter-grid">{def.parameters.map(p=><ParameterInput key={element.id+p.key} def={p} value={element.parameters[p.key]??p.default} units={units} atmosphere={graph.atmosphere_pa} disabled={busy||running} onCommit={v=>parameter(element.id,p.key,v)}/>)}</div></details>;})}{draft.kind==='group'&&<button className="secondary-button" disabled={busy||running} onClick={()=>onInsert(draft,true)}><Edit3 size={14}/> 插入副本并编辑内部结构</button>}</div>}
    {tab==='interface'&&<InterfaceEditor project={graph} members={graph.elements.map(e=>e.id)} value={draft.interface} catalog={catalog} locked={busy||running} onChange={value=>setDraft(d=>({...d,interface:value,test_conditions:Object.fromEntries(Object.keys(value.exposed_ports).map((a,i)=>[a,d.test_conditions[a]||{pressure_pa:i%2?101325:301325,temperature_k:293.15}]))}))}/>}
    <div hidden={tab!=='test'}><ModuleBench draft={draft} onConditions={conditions=>setDraft(d=>({...d,test_conditions:conditions}))} catalog={catalog} units={units} onRunning={setRunning}/></div>
    {error&&<p className="inline-warning" role="alert">{error}</p>}
    <div className="module-actions"><button className="text-button" disabled={!canApply||busy||running||!draft.id||baseline!==JSON.stringify(templatePayload(draft))} onClick={()=>onApply(draft)}>应用此版本到选中实例</button><button className="secondary-button" disabled={busy||running} onClick={()=>save(true)}>另存为新型号</button><button className="primary-button" disabled={busy||running||!draft.name.trim()} onClick={()=>save()}><Save size={15}/>{draft.id?'保存新版本':'保存型号'}</button></div>
  </div>;
}

function ModuleBench({draft,onConditions,catalog,units,onRunning}:{draft:TemplateDraft;onConditions:(c:TemplateDraft['test_conditions'])=>void;catalog:Catalog;units:Units;onRunning:(v:boolean)=>void}){
  const[mode,setMode]=useState<'steady'|'dynamic'>('steady'),[dt,setDt]=useState(.1),[duration,setDuration]=useState(10);
  const[run,setRun]=useState<Run|null>(null),[project,setProject]=useState<Project|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const[history,setHistory]=useState<History>({variables:[],rows:[],total_rows:0});
  const terminal=['completed','failed','event','stopped','interrupted'];const active=!!run&&!terminal.includes(run.status);const rid=useRef<string|null>(null);
  const[definitionAtRun,setDefinitionAtRun]=useState('');const changed=!!run&&definitionAtRun!==JSON.stringify(templatePayload(draft));
  useEffect(()=>{onRunning(active);},[active]);
  useEffect(()=>()=>{const id=rid.current;if(id)void api('/runs/'+id+'/commands',{action:'stop'}).catch(()=>{});onRunning(false);},[]);
  useEffect(()=>{if(!run?.id||!active)return;let alive=true;const id=run.id;
    const refresh=async()=>{try{const state=await api<Run>('/runs/'+id);const h=await api<History>('/runs/'+id+'/history');if(alive){setRun(state);setHistory(h);if(terminal.includes(state.status))rid.current=null;}}catch(e){if(alive)setError((e as Error).message);}};
    void refresh();const timer=setInterval(refresh,250);return()=>{alive=false;clearInterval(timer);};
  },[run?.id,active]);
  async function start(paused=false){setBusy(true);setError('');try{const p=await api<Project>('/modules/bench',templatePayload(draft));const check=await api<{valid:boolean;diagnostics:{message:string}[]}>('/validate',p);if(!check.valid)throw Error(check.diagnostics.map(d=>d.message).join('；'));setProject(p);const response=await api<{run_id:string}>('/runs',{project:p,mode,dt_s:dt,duration_s:duration,start_paused:paused,speed:1});rid.current=response.run_id;setDefinitionAtRun(JSON.stringify(templatePayload(draft)));setHistory({variables:p.selected_variables,rows:[],total_rows:0});setRun({id:response.run_id,name:p.name,project_id:p.id,mode,status:'queued',frame:null,started:Date.now()/1000,updated:Date.now()/1000});}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function command(action:string){if(!run)return;try{await api('/runs/'+run.id+'/commands',{action});}catch(e){setError((e as Error).message);}}
  const values=Object.entries(run?.frame?.elements||{}).filter(([id])=>!id.startsWith('bench_'));
  return <div className="module-bench" data-testid="module-bench"><p className="muted">测试边界只加入验证副本。配置以绝对压力 kPa、温度 °C 输入，正式组合保持原样。</p>
    <div className="bench-boundaries">{Object.keys(draft.interface.exposed_ports).map((alias,i)=>{const c=draft.test_conditions[alias]||{pressure_pa:i%2?101325:301325,temperature_k:293.15};return <div key={alias}><strong>{draft.interface.port_labels[alias]||alias}</strong><label>绝压 kPa<input aria-label={alias+' 测试绝压'} type="number" step="any" value={c.pressure_pa/1000} disabled={active||busy} onChange={e=>onConditions({...draft.test_conditions,[alias]:{...c,pressure_pa:Number(e.target.value)*1000}})}/></label><label>温度 °C<input aria-label={alias+' 测试温度'} type="number" step="any" value={Number((c.temperature_k-273.15).toFixed(8))} disabled={active||busy} onChange={e=>onConditions({...draft.test_conditions,[alias]:{...c,temperature_k:Number(e.target.value)+273.15}})}/></label></div>;})}</div>
    {!Object.keys(draft.interface.exposed_ports).length&&<p className="field-help">本模块使用内部边界或水箱状态进行验证。</p>}
    <div className="module-action-row"><select aria-label="验证运行模式" disabled={active||busy} value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="steady">稳态验证</option><option value="dynamic">慢动态验证</option></select>{mode==='dynamic'&&<><label>步长 s<input aria-label="验证步长" type="number" min="0.001" max="60" step="0.1" value={dt} disabled={active||busy} onChange={e=>setDt(+e.target.value)}/></label><label>时长 s<input aria-label="验证时长" type="number" min="0.1" value={duration} disabled={active||busy} onChange={e=>setDuration(+e.target.value)}/></label></>}
      <button className="primary-button" disabled={active||busy} onClick={()=>start()}><Play size={14}/> 开始验证</button>{mode==='dynamic'&&<><button className="secondary-button" disabled={busy||(active&&run?.status!=='paused')} onClick={()=>active?command('step'):start(true)}><SkipForward size={14}/> 验证单步</button>{active&&<button className="secondary-button" onClick={()=>command(run?.status==='paused'?'resume':'pause')}>{run?.status==='paused'?'继续验证':'暂停验证'}</button>}</>}{active&&<button className="secondary-button" onClick={()=>command('stop')}><Square size={14}/> 停止验证</button>}</div>
    <div className="bench-status" data-testid="bench-status">{run?statusLabel[run.status]||run.status:'尚未验证'} · {numberText(run?.frame?.time_s??0)} s{changed&&<strong> · 定义已更改，请重新验证</strong>}</div>
    {error&&<p className="inline-warning" role="alert">{error}</p>}{run?.frame?.diagnostics.map((d,i)=><p className="inline-warning" key={i}>{d.code} · {d.message}</p>)}
    {run?.frame&&<div className="bench-metrics">{[['质量残差','mass_residual_kg_s','kg/s'],['压力残差','pressure_residual_pa','Pa'],['能量残差','energy_residual_w','W']].map(([label,key,unit])=><div key={key}><span>{label}</span><strong>{numberText(run.frame!.metrics[key]??null,5)} <small>{unit}</small></strong></div>)}</div>}
    {project&&<div className="bench-chart"><TrendChart history={history} project={project} catalog={catalog} units={units}/></div>}
    {values.length>0&&<div className="module-table-wrap"><table className="module-table"><thead><tr><th>内部元件</th><th>结果变量</th><th>数值</th><th>单位</th></tr></thead><tbody>{values.flatMap(([id,items])=>Object.entries(items).map(([key,value])=>{const meta=catalog.variables[key.split('.').at(-1)||key]||{label:key,unit:''};return <tr key={id+key}><td>{project?.elements.find(e=>e.id===id)?.name||id}</td><td>{meta.label}</td><td>{numberText(displayValue(value,key,meta.unit,units,project?.atmosphere_pa),6)}</td><td>{variableUnit(key,meta.unit,units)}</td></tr>;}))}</tbody></table></div>}
  </div>;
}
