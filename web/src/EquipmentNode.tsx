import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { Activity, ArrowDownToLine, ArrowRightLeft, CircleGauge, CircleDot, Container, Droplets, Fan, Flame, Gauge, GitBranch, Pipette, SlidersHorizontal, Thermometer, Timer, Waves, Wind, Package } from 'lucide-react';
import type { ComponentDef, ElementModel, Group } from './types';

const icons:Record<string,typeof Droplets>={reservoir:Waves,flow:ArrowRightLeft,demand:ArrowDownToLine,
  junction:GitBranch,pipe:Pipette,resistance:SlidersHorizontal,valve:SlidersHorizontal,check:ArrowRightLeft,
  pump:Fan,heater:Flame,thermal:Thermometer,exchanger:ArrowRightLeft,tank:Container,gas_tank:Container,
  sensor:Gauge,pid:Activity,timer:Timer,threeway:GitBranch};
export function EquipmentIcon({name,size=20}:{name:string;size?:number}) {const Icon=icons[name]||Droplets;return <Icon size={size} strokeWidth={1.8}/>;}
export type EquipmentData={element:ElementModel;definition:ComponentDef;primary:string;unit:string;
  hasResult:boolean;error:boolean;stale:boolean;groupName?:string;closed?:boolean;group?:Group;portBadges?:Record<string,string>};
const positions={left:Position.Left,right:Position.Right,top:Position.Top,bottom:Position.Bottom};

export const EquipmentNode=memo(function EquipmentNode({data,selected}:NodeProps<Node<EquipmentData>>) {
  const e=data.element,d=data.definition;
  const thermal=d.category==='热设备';
  const control=!!d.control;
  const color=thermal?'orange':control?'purple':d.boundary?'blue':'teal';
  const junction=e.type==='junction';
  return <div className={`equipment-node ${color} ${junction?'junction-node':''} ${selected?'is-selected':''} ${data.error?'is-error':''} ${data.stale?'is-stale':''} ${data.closed?'is-closed':''}`} data-testid={`equipment-${e.id}`}>
    {d.ports.map(p=>{const sidePorts=d.ports.filter(x=>x.side===p.side);const i=sidePorts.findIndex(x=>x.id===p.id);
      const offset=`${(i+1)*100/(sidePorts.length+1)}%`;
      return <Handle key={p.id} id={p.id} type={p.side==='left'||p.side==='top'?'target':'source'} position={positions[p.side]}
        title={`${p.label} · ${p.id}${data.portBadges?.[p.id]?' · 对外接口 '+data.portBadges[p.id]:''}`} style={p.side==='left'||p.side==='right'?{top:offset}:{left:offset}}/>;})}
    {junction?<><div className="junction-mark"><CircleDot size={22}/></div><span className="junction-title">{e.name||d.name}</span>{data.hasResult&&<span className="junction-value">{data.primary} <small>{data.unit}</small></span>}</>:
      <><div className="equipment-top"><span className={`device-icon ${color}`}><EquipmentIcon name={d.icon}/></span><div className="equipment-title"><strong>{e.name||d.name}</strong><span>{d.name}</span></div><span className="node-indicator"/></div>
      <div className="equipment-reading">{data.hasResult?<><strong>{data.primary}</strong><span>{data.unit}</span></>:<span className="awaiting-label">{control?'控制逻辑':'等待求解'}</span>}
      {data.closed&&<span className="closed-label">关闭</span>}</div>
      {data.groupName&&<div className="equipment-group">{data.groupName}</div>}</>}
    {data.portBadges&&Object.keys(data.portBadges).length>0&&<div className="interface-badges">{Object.entries(data.portBadges).map(([port,label])=><span key={port} title={port}>↗ {label}</span>)}</div>}
  </div>;
},(a,b)=>a.selected===b.selected&&a.data.element===b.data.element&&a.data.primary===b.data.primary&&a.data.unit===b.data.unit&&a.data.error===b.data.error&&a.data.stale===b.data.stale&&a.data.closed===b.data.closed&&a.data.hasResult===b.data.hasResult&&a.data.groupName===b.data.groupName&&JSON.stringify(a.data.portBadges)===JSON.stringify(b.data.portBadges));

export const GroupNode=memo(function GroupNode({data,selected}:NodeProps<Node<EquipmentData>>){
  const group=data.group!;
  return <div className={`equipment-node group-node ${selected?'is-selected':''} ${data.error?'is-error':''}`} data-testid={'group-'+group.id}>
    {data.definition.ports.map(p=>{const siblings=data.definition.ports.filter(x=>x.side===p.side);const offset=(siblings.findIndex(x=>x.id===p.id)+1)*100/(siblings.length+1)+'%';
      return <Handle key={p.id} id={p.id} type={p.side==='left'||p.side==='top'?'target':'source'} position={positions[p.side]} title={p.label+' · '+p.id} style={p.side==='left'||p.side==='right'?{top:offset}:{left:offset}}/>;})}
    <div className="equipment-top"><span className="device-icon"><Package size={22}/></span><div className="equipment-title"><strong>{group.name}</strong><span>组合设备 · {group.element_ids.length} 元件</span></div></div>
    <div className="group-node-meta"><span>{Object.keys(group.exposed_ports).length} 个接口</span>{group.template_revision&&<span>v{group.template_revision}</span>}</div>
    <div className="equipment-group">双击进入内部画布</div>
  </div>;
});
