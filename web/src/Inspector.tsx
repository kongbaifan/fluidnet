import { useEffect, useState } from 'react';
import { Box, ChevronDown, CircleHelp, Copy, Crosshair, Droplets, Gauge, Library, SlidersHorizontal, Thermometer, TrendingUp } from 'lucide-react';
import { EquipmentIcon } from './EquipmentNode';
import { displayValue, numberText, parameterDisplay, parameterParse, variableUnit } from './format';
import type { Catalog, ComponentDef, ElementModel, ParameterDef, Parameters, Project, Snapshot, Units } from './types';

export function ParameterInput({def,value,units,atmosphere,disabled,onCommit}:{def:ParameterDef;value:Parameters[string];units:Units;atmosphere:number;disabled:boolean;onCommit:(value:Parameters[string])=>void}) {
  const display=typeof value==='number'?parameterDisplay(def,value,units,atmosphere):{value,unit:def.unit||''};
  const serialize=(v:unknown)=>typeof v==='object'?JSON.stringify(v,null,2):typeof v==='number'?String(Number(v.toPrecision(10))):String(v);
  const [draft,setDraft]=useState(serialize(display.value));
  const [error,setError]=useState('');
  useEffect(()=>{setDraft(serialize(display.value));setError('');},[value,units,atmosphere]);
  function commit() {
    try {
      let result:Parameters[string];
      if(def.kind==='number') {
        if(draft.trim()==='') throw new Error('请输入数值');
        result=parameterParse(def,Number(draft),units,atmosphere);
        if(!Number.isFinite(result)) throw new Error('请输入有效数值');
        if(def.positive&&result<=0) throw new Error('数值必须大于零');
        if(def.min!=null&&result<def.min) throw new Error('低于允许下限');
        if(def.max!=null&&result>def.max) throw new Error('超过允许上限');
      } else if(def.kind==='curve') {
        result=JSON.parse(draft);
        if(!Array.isArray(result)||result.length<2)throw new Error('至少输入两个曲线点');
      } else result=draft;
      setError('');if(JSON.stringify(result)!==JSON.stringify(value))onCommit(result);
    }catch(e){setError((e as Error).message);}
  }
  return <div className={`parameter-field ${error?'field-error':''}`}>
    <label>{def.label}{def.runtime&&<span className="runtime-dot" title="支持运行时调节"/>}</label>
    {def.kind==='boolean'?<button type="button" role="switch" aria-label={def.label} aria-checked={!!value} disabled={disabled} className={`switch ${value?'on':''}`} onClick={()=>onCommit(!value)}><span/></button>:
      def.kind==='select'?<select aria-label={def.label} disabled={disabled} value={String(value)} onChange={e=>onCommit(e.target.value)}>{def.choices?.map(x=><option key={x} value={x}>{x==='linear'?'线性':x==='equal_percentage'?'等百分比':x}</option>)}</select>:
      def.kind==='curve'?<><textarea aria-label={def.label} className="curve-input" rows={4} disabled={disabled} value={draft} onChange={e=>setDraft(e.target.value)}/><button className="text-button" disabled={disabled} onClick={commit}>应用曲线</button></>:
      <div className="input-with-unit"><input aria-label={def.label} disabled={disabled} type={def.kind==='number'?'number':'text'} step="any" value={draft} onChange={e=>setDraft(e.target.value)} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();}}/><span>{display.unit}</span></div>}
    {def.key==='opening'&&typeof value==='number'&&<input aria-label="阀门开度滑块" className="opening-slider" type="range" min="0" max="1" step="0.01" disabled={disabled} value={Number(draft)} onChange={e=>setDraft(e.target.value)} onPointerUp={commit} onKeyUp={commit}/>}
    {error&&<small className="field-error-text">{error}</small>}
  </div>;
}

type Props={element:ElementModel|null;definition:ComponentDef|undefined;project:Project;parameters:Parameters;catalog:Catalog;frame:Snapshot|null;active:boolean;stale:boolean;units:Units;
  onParameter:(key:string,value:Parameters[string])=>void;onName:(name:string)=>void;onMedium:(group:string,id:string)=>void;
  onCurve:(path:string)=>void;onSaveModel:()=>void;onMedia:()=>void;onSettings:()=>void};
export function Inspector(p:Props) {
  const [tab,setTab]=useState<'parameters'|'results'>('parameters');
  const e=p.element,d=p.definition;
  if(!e||!d)return <aside className="inspector project-inspector">
    <div className="panel-heading"><span><SlidersHorizontal size={16}/> 项目概览</span><button className="icon-button" title="项目设置" onClick={p.onSettings}><CircleHelp size={16}/></button></div>
    <div className="project-summary"><div className="summary-icon"><GitIcon/></div><span className="eyebrow">NETWORK OVERVIEW</span><h2>{p.project.name}</h2><p>{p.project.description||'用模块定义系统，用计算连接每一条通路。'}</p></div>
    <div className="summary-grid"><div><strong>{p.project.elements.length}</strong><span>设备元件</span></div><div><strong>{p.project.connections.length}</strong><span>连接通路</span></div><div><strong>{p.frame?.circuits?.length??'—'}</strong><span>流体回路</span></div><div><strong>{p.project.scenarios.length||1}</strong><span>保存工况</span></div></div>
    <button className="medium-summary" onClick={p.onMedia}><span className="medium-icon"><Droplets size={20}/></span><div><strong>{p.project.media.find(m=>m.id===p.project.default_medium_id)?.name}</strong><small>介质与回路配置</small></div><ChevronDown size={16}/></button>
    <div className="inspector-note"><Crosshair size={19}/><div><strong>选择元件，查看详细信息</strong><p>点击画布中的元件编辑参数、介质和性能曲线。运行后可以在这里选择记录变量。</p></div></div>
    <div className="model-scope"><span className="eyebrow">当前计算能力</span><div><span className="tiny-dot"/> 单相液态水</div><div><span className="tiny-dot"/> 稳态水力与热力</div><div><span className="tiny-dot"/> 设备慢动态与控制</div><p>气体、蒸汽、制冷剂与混合物接口已预留。首版不计算水锤与相变。</p></div>
  </aside>;
  const values=p.frame?.elements[e.id]||{};
  const groups=[...new Set(d.ports.map(x=>x.group))];
  return <aside className="inspector">
    <div className="panel-heading"><span><SlidersHorizontal size={16}/> 元件属性</span><button className="icon-button" title="保存为设备型号" onClick={p.onSaveModel} disabled={p.active}><Library size={16}/></button></div>
    <div className="selected-device"><span className="device-icon large"><EquipmentIcon name={d.icon} size={26}/></span><div><input aria-label="元件名称" value={e.name} placeholder={d.name} onChange={event=>p.onName(event.target.value)} disabled={p.active}/><span>{d.name} <i>·</i> {e.id.slice(0,14)}</span></div></div>
    <div className="inspector-tabs"><button className={tab==='parameters'?'active':''} onClick={()=>setTab('parameters')}>参数配置</button><button className={tab==='results'?'active':''} onClick={()=>setTab('results')}>运行结果 <span>{Object.keys(values).length}</span></button></div>
    <div className="inspector-scroll">{tab==='parameters'?<>
      <p className="device-description">{d.description}</p>
      {groups.length>0&&<section className="property-section"><h3><Droplets size={13}/> 介质归属</h3>{groups.map(group=><label className="media-select" key={group}><span>{group==='fluid'?'流体通路':`${group.toUpperCase()} 侧`}</span><select aria-label={`${group} 通路介质`} disabled={p.active} value={e.media[group]||''} onChange={event=>p.onMedium(group,event.target.value)}><option value="">继承所在回路</option>{p.project.media.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>)}</section>}
      <section className="property-section"><h3><SlidersHorizontal size={13}/> 模型参数{p.active&&<small>绿点参数可在线调节</small>}</h3>
      {d.parameters.length?d.parameters.map(def=><ParameterInput key={e.id+def.key} def={def} value={p.parameters[def.key]??def.default} units={p.units} atmosphere={p.project.atmosphere_pa} disabled={p.active&&!def.runtime} onCommit={value=>p.onParameter(def.key,value)}/>):<p className="muted">此元件没有需要设置的模型参数。</p>}</section>
      {d.ports.length>0&&<section className="property-section"><h3>流体端口</h3>{d.ports.map(port=><div className="port-row" key={port.id}><span className="port-dot"/><code>{port.id}</code><span>{port.label}</span></div>)}</section>}
      <button className="secondary-button full" disabled={p.active} onClick={p.onSaveModel}><Library size={14}/> 保存设备型号</button>
    </>:<>{p.stale&&<div className="inline-warning">模型已变更，下方为上次有效结果。</div>}
      {!Object.keys(values).length?<div className="empty-inspector"><Gauge size={30}/><p>计算后显示此元件的结果</p></div>:
      <div className="variable-list">{Object.entries(values).map(([key,value])=>{const meta=p.catalog.variables[key.split('.').at(-1)||key]||{label:key,unit:''};const path=e.id+'.'+key;return <label className="variable-row" key={key}>
        <input aria-label={`记录 ${e.name} ${key}`} type="checkbox" checked={p.project.selected_variables.includes(path)} disabled={p.active} onChange={()=>p.onCurve(path)}/>
        <div><span>{key.includes('.')?key.split('.')[0].toUpperCase()+' · ':''}{meta.label}</span><small>{key}</small></div>
        <strong>{numberText(displayValue(value,key,meta.unit,p.units,p.project.atmosphere_pa),6)}<small>{variableUnit(key,meta.unit,p.units)}</small></strong>
      </label>;})}</div>}
      <p className="field-help"><TrendingUp size={13}/> 勾选变量，将在下次运行中记录曲线。</p>
    </>}</div>
  </aside>;
}
function GitIcon(){return <Box size={29} strokeWidth={1.5}/>;}
