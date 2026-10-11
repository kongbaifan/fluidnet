import {copy, uid, type Catalog, type ComponentDef, type ElementModel, type Group, type ModuleInterface, type Project, type TemplateDraft} from './types';

export const groupNodeId=(id:string)=>'group:'+id;
export const isGroupNode=(id:string)=>id.startsWith('group:');
export const emptyInterface=():ModuleInterface=>({exposed_ports:{},exposed_parameters:{},port_labels:{},parameter_labels:{}});
export function interfaceOf(group:ModuleInterface):ModuleInterface {
  return copy({exposed_ports:group.exposed_ports,exposed_parameters:group.exposed_parameters,port_labels:group.port_labels,parameter_labels:group.parameter_labels});
}
export function templatePayload(template:TemplateDraft) {
  return {name:template.name,kind:template.kind,body:template.body,interface:template.interface,test_conditions:template.test_conditions,revision:template.revision};
}
export function realEndpoint(project:Project,id:string,port:string):[string,string] {
  if(!isGroupNode(id))return [id,port];
  const target=project.groups.find(g=>g.id===id.slice(6))?.exposed_ports[port];
  if(!target)throw Error('组合端口不存在，请重新打开组合配置');
  const split=target.indexOf(':');return [target.slice(0,split),target.slice(split+1)];
}
export function visualEndpoint(project:Project,id:string,port:string,scope:string|null):[string,string] {
  const group=project.groups.find(g=>g.collapsed&&g.element_ids.includes(id));
  if(scope||!group)return [id,port];
  const alias=Object.entries(group.exposed_ports).find(([,target])=>target===id+':'+port)?.[0];
  return [groupNodeId(group.id),alias||port];
}
export function selectedElements(project:Project,ids:string[]) {
  return [...new Set(ids.flatMap(id=>isGroupNode(id)?project.groups.find(g=>g.id===id.slice(6))?.element_ids||[]:[id]))];
}
export function inferInterface(project:Project,members:string[],catalog:Catalog) {
  const result=emptyInterface();const selected=new Set(members);
  const internal=new Set(project.connections.filter(c=>selected.has(c.source)&&selected.has(c.target)).flatMap(c=>[c.source+':'+c.source_port,c.target+':'+c.target_port]));
  for(const element of project.elements.filter(e=>selected.has(e.id))){
    const definition=catalog.components.find(d=>d.type===element.type);if(!definition)continue;
    for(const port of definition.ports)if(!internal.has(element.id+':'+port.id)){
      const alias='P'+(Object.keys(result.exposed_ports).length+1);
      result.exposed_ports[alias]=element.id+':'+port.id;result.port_labels[alias]=element.name+' · '+port.label;
    }
    for(const parameter of definition.parameters)if(parameter.runtime){
      const alias='param_'+(Object.keys(result.exposed_parameters).length+1);
      result.exposed_parameters[alias]=element.id+'.'+parameter.key;result.parameter_labels[alias]=element.name+' · '+parameter.label;
    }
  }
  return result;
}
export function groupDefinition(project:Project,group:Group,definitions:Map<string,ComponentDef>):ComponentDef {
  return {type:'group',name:'组合设备',category:'组合',icon:'group',description:'双击进入内部画布',version:1,supported_media:['water'],parameters:[],
    ports:Object.entries(group.exposed_ports).map(([id,target])=>{
      const[eid,port]=target.split(':');const e=project.elements.find(e=>e.id===eid);const original=e&&definitions.get(e.type)?.ports.find(p=>p.id===port);
      return {id,label:group.port_labels[id]||id,group:original?.group||'fluid',side:original?.side||'left',required:original?.required??true};
    })};
}
export function ensureExternalPort(project:Project,id:string,port:string) {
  const group=project.groups.find(g=>g.element_ids.includes(id));if(!group)return;
  const address=id+':'+port;if(Object.values(group.exposed_ports).includes(address))return;
  let i=1;while(group.exposed_ports['P'+i])i++;
  group.exposed_ports['P'+i]=address;group.port_labels['P'+i]=(project.elements.find(e=>e.id===id)?.name||id)+' · '+port;
}
export function removeInternalInterfaces(project:Project,source:string,sourcePort:string,target:string,targetPort:string) {
  const group=project.groups.find(g=>g.element_ids.includes(source)&&g.element_ids.includes(target));if(!group)return;
  const addresses=new Set([source+':'+sourcePort,target+':'+targetPort]);
  for(const [alias,address] of Object.entries(group.exposed_ports))if(addresses.has(address)){delete group.exposed_ports[alias];delete group.port_labels[alias];}
}
export function selectionProject(project:Project,selection:string[]):Project {
  const ids=new Set(selectedElements(project,selection));const source=copy(project);
  source.id=uid();source.revision=0;source.elements=source.elements.filter(e=>ids.has(e.id));
  source.connections=source.connections.filter(c=>ids.has(c.source)&&ids.has(c.target));
  source.groups=source.groups.filter(g=>g.element_ids.every(id=>ids.has(id)));
  for(const e of source.elements)if(!source.groups.some(g=>g.id===e.group_id))e.group_id=null;
  source.selected_variables=source.selected_variables.filter(path=>ids.has(path.split('.')[0]));
  source.scenarios=[];return source;
}
export function pasteSelection(project:Project,source:Project,page:number,scope:string|null):string[] {
  if(project.elements.length+source.elements.length>1000)throw Error('超过 1000 元件限制');
  if(scope&&source.groups.length)throw Error('组合内部不支持嵌套组合，请返回主画布后粘贴');
  const ids=Object.fromEntries(source.elements.map(e=>[e.id,uid()]));
  const groups=Object.fromEntries(source.groups.map(g=>[g.id,uid()]));
  const media:Record<string,string>={};
  for(const medium of source.media){
    const same=project.media.find(m=>JSON.stringify({...m,id:''})===JSON.stringify({...medium,id:''}));
    if(same){media[medium.id]=same.id;continue;}
    const clone=copy(medium);if(project.media.some(m=>m.id===clone.id))clone.id='medium_'+uid();
    media[medium.id]=clone.id;project.media.push(clone);
  }
  const ref=(path:string,separator:string)=>{const i=path.indexOf(separator),id=path.slice(0,i);return ids[id]?ids[id]+path.slice(i):path;};
  const added=source.elements.map(e=>{const n=copy(e);n.id=ids[e.id];n.page=page;n.position={x:e.position.x+60,y:e.position.y+60};n.group_id=scope||(e.group_id?groups[e.group_id]||null:null);
    if(typeof n.parameters.target_element==='string')n.parameters.target_element=ids[n.parameters.target_element]||n.parameters.target_element;
    if(typeof n.parameters.measurement==='string')n.parameters.measurement=ref(n.parameters.measurement,'.');
    n.media=Object.fromEntries(Object.entries(n.media).map(([key,value])=>[key,media[value]]));
    // Preserve implicit defaults when copying between projects with different water configurations.
    if(e.type==='heat_exchanger'){n.media.a||=media[source.default_medium_id];n.media.b||=media[source.default_medium_id];}
    else if(!['pid','timer'].includes(e.type))n.media.fluid||=media[source.default_medium_id];
    return n;});
  project.elements.push(...added);
  project.connections.push(...source.connections.map(c=>({...c,id:uid(),source:ids[c.source],target:ids[c.target]})));
  project.groups.push(...source.groups.map(g=>({...copy(g),id:groups[g.id],page,position:{x:g.position.x+60,y:g.position.y+60},
    element_ids:g.element_ids.map(id=>ids[id]),member_keys:Object.fromEntries(Object.entries(g.member_keys).map(([key,id])=>[key,ids[id]])),
    exposed_ports:Object.fromEntries(Object.entries(g.exposed_ports).map(([key,path])=>[key,ref(path,':')])),
    exposed_parameters:Object.fromEntries(Object.entries(g.exposed_parameters).map(([key,path])=>[key,ref(path,'.')]))})));
  if(scope){const group=project.groups.find(g=>g.id===scope)!;group.element_ids.push(...added.map(e=>e.id));for(const e of added)group.member_keys[e.id]=e.id;}
  project.selected_variables=[...new Set([...project.selected_variables,...source.selected_variables.map(path=>ref(path,'.'))])].slice(0,64);
  return [...source.groups.map(g=>groupNodeId(groups[g.id])),...added.filter(e=>!e.group_id||scope).map(e=>e.id)];
}
