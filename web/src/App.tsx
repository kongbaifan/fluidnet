import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ReactFlow, Background, BackgroundVariant, Controls, MiniMap, ConnectionMode, MarkerType,
  applyNodeChanges, useReactFlow, type Node, type Edge, type NodeChange, type EdgeChange, type OnSelectionChangeParams, type Connection as FlowConnection } from '@xyflow/react';
import { Activity, AlertCircle, ArrowDownToLine, ArrowRight, BookOpen, Check, CheckCircle2, ChevronDown,
  Clock3, Copy, Download, Droplets, FilePlus2, FolderOpen, GitBranch, Layers3, Library, Maximize2, MoreHorizontal,
  Pause, Play, Plus, Redo2, RotateCcw, Save, Search, Settings2, SkipForward, Square, Trash2, TrendingUp,
  Undo2, Upload, X, Zap, SlidersHorizontal, FlaskConical, CircleHelp, PanelRightClose, Package, RefreshCw } from 'lucide-react';
import { api, ApiError, download } from './api';
import { EquipmentIcon, EquipmentNode, GroupNode, type EquipmentData } from './EquipmentNode';
import { GroupEditor, GroupInspector, TemplateEditor, TemplateLibrary } from './ModulePanels';
import { emptyInterface, ensureExternalPort, groupDefinition, groupNodeId, interfaceOf, isGroupNode, pasteSelection, realEndpoint, removeInternalInterfaces, selectedElements, selectionProject, templatePayload, visualEndpoint } from './modules';
import { Inspector, ParameterInput } from './Inspector';
import { TrendChart } from './Charts';
import { displayValue, numberText, statusLabel, variableUnit } from './format';
import { blankProject, copy, DEFAULT_WATER, uid, type Catalog, type Circuit, type ComponentDef,
  type Diagnostic, type ElementModel, type Group, type History, type Parameters, type Project,
  type ProjectInfo, type Run, type Snapshot, type Template, type Units, type ModuleInterface, type ModuleResult, type TemplateDraft, type TemplatePreview } from './types';

const nodeTypes={equipment:EquipmentNode,groupDevice:GroupNode};
const terminal=new Set(['completed','failed','stopped','event','interrupted']);
type Modal='projects'|'examples'|'media'|'settings'|'cases'|'history'|'equipment'|'group'|'compare'|'versions'|'help'|'library'|'template'|'apply'|null;
type UndoEntry={project:Project;physics:boolean};
const baseUnits:Units={flow:'volume',pressure:'gauge',temperature:'celsius'};

function ModalBox({title,subtitle,onClose,children,wide=false}:{title:string;subtitle?:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}) {
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}><section role="dialog" aria-modal="true" aria-label={title} className={`modal ${wide?'wide':''}`}><header><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button className="icon-button" aria-label="关闭窗口" onClick={onClose}><X size={20}/></button></header><div className="modal-body">{children}</div></section></div>;
}

export default function App() {
  const flow=useReactFlow();
  const [catalog,setCatalog]=useState<Catalog|null>(null);
  const [project,setProject]=useState<Project|null>(null);
  const projectRef=useRef<Project|null>(null);
  const [projectList,setProjectList]=useState<ProjectInfo[]>([]);
  const [examples,setExamples]=useState<Project[]>([]);
  const [templates,setTemplates]=useState<Template[]>([]);
  const [health,setHealth]=useState<{version:string;versions:Record<string,string>;workspace:string}|null>(null);
  const [loadError,setLoadError]=useState('');
  const [dirty,setDirty]=useState(false);
  const [stale,setStale]=useState(false);
  const [frame,setFrame]=useState<Snapshot|null>(null);
  const [diagnostics,setDiagnostics]=useState<Diagnostic[]>([]);
  const [circuits,setCircuits]=useState<Circuit[]>([]);
  const [runId,setRunId]=useState<string|null>(null);
  const [run,setRun]=useState<Run|null>(null);
  const [history,setHistory]=useState<History>({variables:[],rows:[],total_rows:0});
  const [runList,setRunList]=useState<Run[]>([]);
  const [compareIds,setCompareIds]=useState<string[]>([]);
  const [comparison,setComparison]=useState<Run[]>([]);
  const [selectedIds,setSelectedIds]=useState<string[]>([]);
  const [selectedEdgeIds,setSelectedEdgeIds]=useState<string[]>([]);
  const [nodes,setNodes]=useState<Node<EquipmentData>[]>([]);
  const [page,setPage]=useState(0);
  const [scopeGroupId,setScopeGroupId]=useState<string|null>(null);
  const [editingGroupId,setEditingGroupId]=useState<string|null>(null);
  const [templateDraft,setTemplateDraft]=useState<TemplateDraft|null>(null);
  const [draftGroupId,setDraftGroupId]=useState<string|null>(null);
  const [preview,setPreview]=useState<TemplatePreview|null>(null);
  const previewBase=useRef<Project|null>(null);
  const [search,setSearch]=useState('');
  const [libraryTab,setLibraryTab]=useState<'components'|'templates'>('components');
  const [overlay,setOverlay]=useState<'flow'|'pressure'|'temperature'>('flow');
  const [bottomTab,setBottomTab]=useState<'trends'|'diagnostics'|'results'>('trends');
  const [mode,setMode]=useState<'steady'|'dynamic'>('steady');
  const [duration,setDuration]=useState(60);
  const [dt,setDt]=useState(0.1);
  const [speed,setSpeed]=useState(1);
  const [scenarioId,setScenarioId]=useState('');
  const [units,setUnits]=useState<Units>(()=>{try{return {...baseUnits,...JSON.parse(localStorage.getItem('fluidnet:units')||'{}')};}catch{return baseUnits;}});
  const [modal,setModal]=useState<Modal>(null);
  const [modalName,setModalName]=useState('');
  const [versions,setVersions]=useState<{revision:number;created:number}[]>([]);
  const [toast,setToast]=useState<{message:string;error:boolean}|null>(null);
  const [busy,setBusy]=useState(false);
  const [recovery,setRecovery]=useState<Project|null>(null);
  const [showInspector,setShowInspector]=useState(true);
  const undo=useRef<UndoEntry[]>([]),redo=useRef<UndoEntry[]>([]),clipboard=useRef<Project|null>(null);
  const [,refreshUndo]=useState(0);
  const inputFile=useRef<HTMLInputElement>(null);
  const lastFrameTime=useRef(-1);
  const finishedHistory=useRef<string|null>(null);
  const defs=useMemo(()=>new Map(catalog?.components.map(d=>[d.type,d])||[]),[catalog]);
  const active=!!run&&!terminal.has(run.status)&&!!runId;
  const selected=project?.elements.find(e=>selectedIds.includes(e.id))||null;
  const selectedDef=selected?defs.get(selected.type):undefined;
  const scopeGroup=project?.groups.find(g=>g.id===scopeGroupId)||null;
  const selectedGroup=selectedIds.length===1&&isGroupNode(selectedIds[0])?project?.groups.find(g=>g.id===selectedIds[0].slice(6))||null:null;
  const inspectorGroup=selectedGroup||(!selected?scopeGroup:null);

  function focusElement(id:string){const p=projectRef.current;const e=p?.elements.find(e=>e.id===id);if(!e)return;setPage(e.page);const g=p?.groups.find(g=>g.element_ids.includes(id));setScopeGroupId(g?.collapsed?g.id:null);setSelectedIds([id]);setSelectedEdgeIds([]);}
  function enterGroup(group:Group){setPage(group.page);setScopeGroupId(group.id);setSelectedIds([]);setSelectedEdgeIds([]);}
  useEffect(()=>{if(scopeGroupId&&project&&!project.groups.some(g=>g.id===scopeGroupId))setScopeGroupId(null);},[project,scopeGroupId]);

  const notify=useCallback((message:string,error=false)=>{setToast({message,error});},[]);
  useEffect(()=>{if(!toast)return;const t=setTimeout(()=>setToast(null),toast.error?7000:3500);return()=>clearTimeout(t);},[toast]);
  function reportError(error:unknown) {
    const err=error as ApiError;notify(err.message||String(error),true);
    if(err.diagnostic){setDiagnostics([{...err.diagnostic,code:err.diagnostic.code||'ERROR',severity:'error'}]);setBottomTab('diagnostics');if(err.diagnostic.element_id)focusElement(err.diagnostic.element_id);}
  }
  function installProject(p:Project,saved=true) {
    if(projectRef.current&&dirty&&projectRef.current.id!==p.id){try{localStorage.setItem('fluidnet:draft:'+projectRef.current.id,JSON.stringify(projectRef.current));}catch{}}
    projectRef.current=p;setProject(p);setDirty(!saved);setFrame(null);setStale(false);setRunId(null);setRun(null);
    setHistory({variables:[],rows:[],total_rows:0});setDiagnostics([]);setCircuits([]);setSelectedIds([]);setSelectedEdgeIds([]);setPage(0);setScopeGroupId(null);setScenarioId('');
    undo.current=[];redo.current=[];refreshUndo(x=>x+1);setRecovery(null);
    localStorage.setItem('fluidnet:last-project',p.id);
  }
  function editProject(change:(p:Project)=>void,physics=true,remember=true) {
    const current=projectRef.current;if(!current)return;
    const next=copy(current);change(next);
    if(remember){undo.current.push({project:current,physics});if(undo.current.length>80)undo.current.shift();redo.current=[];refreshUndo(x=>x+1);}
    projectRef.current=next;setProject(next);setDirty(true);if(physics){setStale(true);setCircuits([]);}
  }
  function undoEdit() {
    if(active)return;const entry=undo.current.pop();if(!entry||!projectRef.current)return;
    // Undo changes model content; the persisted revision must keep moving forward.
    const restored={...entry.project,revision:projectRef.current.revision};
    redo.current.push({project:projectRef.current,physics:entry.physics});projectRef.current=restored;setProject(restored);setDirty(true);if(entry.physics){setStale(true);setCircuits([]);}refreshUndo(x=>x+1);
  }
  function redoEdit() {
    if(active)return;const entry=redo.current.pop();if(!entry||!projectRef.current)return;
    const restored={...entry.project,revision:projectRef.current.revision};
    undo.current.push({project:projectRef.current,physics:entry.physics});projectRef.current=restored;setProject(restored);setDirty(true);if(entry.physics){setStale(true);setCircuits([]);}refreshUndo(x=>x+1);
  }
  async function refreshProjects(){setProjectList(await api<ProjectInfo[]>('/projects'));}
  async function saveProject() {
    const current=projectRef.current;if(!current)return null;
    const saved=await api<Project>('/projects',current);
    const latest=projectRef.current;
    let pendingChanges=false;
    if(latest?.id===saved.id&&latest.revision<=saved.revision){
      pendingChanges=latest!==current;
      const next=pendingChanges?{...latest,revision:saved.revision}:saved;
      projectRef.current=next;setProject(next);setDirty(pendingChanges);
      if(!pendingChanges)localStorage.removeItem('fluidnet:draft:'+saved.id);
    }
    await refreshProjects();notify(`${saved.name} · 已保存版本 ${saved.revision}${pendingChanges?'，后续修改尚未保存':''}`);return saved;
  }
  async function openSaved(id:string) {
    const p=await api<Project>('/projects/'+id);installProject(p);setModal(null);
    restoreDraft(p);
  }
  function restoreDraft(p:Project){try{const raw=JSON.parse(localStorage.getItem('fluidnet:draft:'+p.id)||'null');if(raw)api<Project>('/projects/upgrade',raw).then(draft=>{if(projectRef.current?.id===p.id&&JSON.stringify(draft)!==JSON.stringify(p))setRecovery(draft);}).catch(()=>{});}catch{}}
  useEffect(()=>{
    let alive=true;
    Promise.all([api<Catalog>('/catalog'),api<ProjectInfo[]>('/projects'),api<Project[]>('/examples'),api<Template[]>('/templates'),api<{version:string;versions:Record<string,string>;workspace:string}>('/health')]).then(async([cat,list,samples,models,healthInfo])=>{
      if(!alive)return;setCatalog(cat);setProjectList(list);setExamples(samples);setTemplates(models);setHealth(healthInfo);
      const last=localStorage.getItem('fluidnet:last-project');const target=list.find(p=>p.id===last)||list.find(p=>p.id==='example_parallel')||list[0];
      const initial=target?await api<Project>('/projects/'+target.id):blankProject();
      if(!alive)return;installProject(initial,!!target);
      restoreDraft(initial);
    }).catch(error=>{if(alive)setLoadError((error as Error).message);});return()=>{alive=false;};
  },[]);
  useEffect(()=>{if(!project||!dirty)return;const timeout=setTimeout(()=>{try{localStorage.setItem('fluidnet:draft:'+project.id,JSON.stringify(project));}catch{notify('浏览器草稿空间不足，请保存项目。',true);}},700);return()=>clearTimeout(timeout);},[project,dirty,notify]);
  useEffect(()=>{localStorage.setItem('fluidnet:units',JSON.stringify(units));},[units]);
  useEffect(()=>{
    if(!project)return;
    if(!project.elements.some(e=>e.page===page)){
      void flow.setViewport({x:0,y:0,zoom:1});
      return;
    }
    const timer=setTimeout(()=>flow.fitView({padding:0.22,maxZoom:1,duration:250}),100);
    return()=>clearTimeout(timer);
  },[project?.id,page,scopeGroupId,flow]);

  function effectiveParameters(e:ElementModel):Parameters {
    const defaults=Object.fromEntries((defs.get(e.type)?.parameters||[]).map(p=>[p.key,copy(p.default)]));
    const scenario=project?.scenarios.find(s=>s.id===scenarioId);
    return {...defaults,...e.parameters,...scenario?.overrides[e.id]};
  }
  function primary(e:ElementModel) {
    const v=frame?.elements[e.id]||{};
    const prefix=e.type==='heat_exchanger'?'a.':e.type==='three_way'?'a.':'';
    let key=overlay==='flow'?(units.flow==='volume'?'volume_flow_m3_h':'mass_flow_kg_s'):overlay==='pressure'?'pressure_pa':'temperature_k';
    if(!(key in v)&&((prefix+key) in v))key=prefix+key;
    if(!(key in v)&&overlay==='pressure')key=prefix+'inlet_pressure_pa';
    if(!(key in v)&&e.type==='junction')key='pressure_pa';
    if(!(key in v)&&defs.get(e.type)?.control)key='output';
    const meta=catalog?.variables[key.split('.').at(-1)||'']||{label:key,unit:''};
    return {hasResult:v[key]!=null,primary:numberText(v[key]==null?null:displayValue(v[key],key,meta.unit,units,project?.atmosphere_pa),5),unit:variableUnit(key,meta.unit,units)};
  }
  useEffect(()=>{
    if(!project||!catalog)return;
    const errors=new Set(diagnostics.filter(d=>d.severity==='error').map(d=>d.element_id));
    const next:Node<EquipmentData>[]=[];
    const hidden=new Set(project.groups.filter(g=>g.collapsed).flatMap(g=>g.element_ids));
    for(const e of project.elements.filter(e=>e.page===page&&(scopeGroup?scopeGroup.element_ids.includes(e.id):!hidden.has(e.id)))){
      const d=defs.get(e.type);if(!d)continue;
      next.push({id:e.id,type:'equipment',position:e.position,selected:selectedIds.includes(e.id),
        data:{element:e,definition:d,...primary(e),error:errors.has(e.id),stale,
          groupName:project.groups.find(g=>g.id===e.group_id)?.name,closed:!!frame?.elements[e.id]?.closed,
          portBadges:scopeGroup?Object.fromEntries(Object.entries(scopeGroup.exposed_ports).filter(([,target])=>target.startsWith(e.id+':')).map(([alias,target])=>[target.split(':')[1],scopeGroup.port_labels[alias]||alias])):undefined},
        draggable:!active,connectable:!active});
    }
    if(!scopeGroup)for(const g of project.groups.filter(g=>g.page===page&&g.collapsed)){
      const element:ElementModel={id:groupNodeId(g.id),type:'group',name:g.name,parameters:{},media:{},position:g.position,page:g.page,group_id:null,version:1};
      next.push({id:element.id,type:'groupDevice',position:g.position,selected:selectedIds.includes(element.id),draggable:!active,connectable:!active,
        data:{element,definition:groupDefinition(project,g,defs),group:g,primary:'',unit:'',hasResult:false,stale,error:g.element_ids.some(id=>errors.has(id))}});
    }
    setNodes(next);
  },[project,catalog,frame,overlay,units,selectedIds,page,scopeGroupId,diagnostics,stale,active]);
  const edges=useMemo<Edge[]>(()=>{
    if(!project)return[];const shown=new Set(project.elements.filter(e=>e.page===page&&(!scopeGroup||scopeGroup.element_ids.includes(e.id))).map(e=>e.id));
    function outflow(id:string,port:string):number|undefined {
      const e=project?.elements.find(e=>e.id===id);if(!e)return;
      const v=frame?.elements[id];if(!v)return;
      const prefix=e.type==='heat_exchanger'?port.slice(0,1)+'.':e.type==='three_way'?(port==='common'?'':port+'.'):'';
      const q=v[prefix+'mass_flow_kg_s'];if(q==null)return;
      if(port==='in'||port.endsWith('_in'))return -q;
      if(port==='out'||port.endsWith('_out')||port==='a'||port==='b')return q;
      return undefined;
    }
    return project.connections.filter(c=>shown.has(c.source)&&shown.has(c.target)).flatMap(c=>{
      const [source,sourceHandle]=visualEndpoint(project,c.source,c.source_port,scopeGroupId),[target,targetHandle]=visualEndpoint(project,c.target,c.target_port,scopeGroupId);
      if(source===target&&isGroupNode(source))return [];
      const q=outflow(c.source,c.source_port)??(outflow(c.target,c.target_port)==null?undefined:-outflow(c.target,c.target_port)!);
      const has=q!=null&&frame?.valid&&!stale;const reverse=has&&q!<0;const still=has&&Math.abs(q!)<1e-9;
      const color=stale?'#adb9c0':still?'#b8c4ca':has?'#1b9c9b':'#93a9b3';
      return [{id:c.id,source,sourceHandle,target,targetHandle,type:'smoothstep',
        animated:active&&!!has&&!still,style:{stroke:color,strokeWidth:has?2:1.7},
        markerEnd:reverse?undefined:{type:MarkerType.ArrowClosed,color,width:15,height:15},markerStart:reverse?{type:MarkerType.ArrowClosed,color,width:15,height:15}:undefined,
        selected:selectedEdgeIds.includes(c.id)}];
    });
  },[project,page,scopeGroupId,frame,stale,active,selectedEdgeIds]);
  const onNodeChanges=useCallback((changes:NodeChange<Node<EquipmentData>>[])=>setNodes(previous=>applyNodeChanges(changes,previous)),[]);
  const onEdgeChanges=useCallback((changes:EdgeChange[])=>{
    setSelectedEdgeIds(previous=>{
      const next=new Set(previous);
      for(const change of changes)if(change.type==='select'){
        if(change.selected)next.add(change.id);else next.delete(change.id);
      }
      return previous.length===next.size&&previous.every(id=>next.has(id))?previous:[...next];
    });
  },[]);
  // React Flow also emits the current selection when this callback changes.
  // Keep it stable so it cannot feed an old selection back into newly added nodes.
  const onSelectionChange=useCallback(({nodes}:OnSelectionChangeParams)=>{
    const next=nodes.map(n=>n.id);
    setSelectedIds(previous=>previous.length===next.length&&previous.every(id=>next.includes(id))?previous:next);
  },[]);
  function onConnect(c:FlowConnection) {
    if(active||!c.sourceHandle||!c.targetHandle)return;
    if(c.source===c.target){notify('请通过管路连接不同元件。',true);return;}
    if(!project)return;
    const [source,sourcePort]=realEndpoint(project,c.source,c.sourceHandle),[target,targetPort]=realEndpoint(project,c.target,c.targetHandle);
    c={...c,source,target,sourceHandle:sourcePort,targetHandle:targetPort};
    if(project?.connections.some(x=>(x.source===c.source&&x.source_port===c.sourceHandle)||(x.target===c.source&&x.target_port===c.sourceHandle)||(x.source===c.target&&x.source_port===c.targetHandle)||(x.target===c.target&&x.target_port===c.targetHandle))){notify('端口已连接，请使用连接节点分支。',true);return;}
    editProject(p=>{p.connections.push({id:uid(),source:c.source,source_port:c.sourceHandle!,target:c.target,target_port:c.targetHandle!});
      if(p.elements.find(e=>e.id===source)?.group_id===p.elements.find(e=>e.id===target)?.group_id)removeInternalInterfaces(p,source,sourcePort,target,targetPort);
      else{ensureExternalPort(p,source,sourcePort);ensureExternalPort(p,target,targetPort);}});
  }
  function addElement(type:string,position?:{x:number;y:number},template?:ElementModel) {
    if(active)return;const definition=defs.get(type);if(!definition)return;
    if((project?.elements.length||0)>=1000){notify('首版最多支持 1000 个元件。',true);return;}
    const canvas=document.querySelector('.canvas-area')?.getBoundingClientRect();
    const base=canvas?flow.screenToFlowPosition({x:canvas.x+canvas.width/2,y:canvas.y+canvas.height/2}):{x:200,y:200};
    const offset=((project?.elements.length||0)%5)*32;
    const center=position||{x:base.x-88+offset,y:base.y-45+offset};
    const item:ElementModel=template?{...copy(template),id:uid(),position:center,page,group_id:null}:{id:uid(),type,name:definition.name,parameters:Object.fromEntries(definition.parameters.map(p=>[p.key,copy(p.default)])),media:{},position:center,page,group_id:null,version:1};
    editProject(p=>{p.elements.push(item);if(scopeGroupId){const g=p.groups.find(g=>g.id===scopeGroupId)!;item.group_id=g.id;g.element_ids.push(item.id);g.member_keys[item.id]=item.id;}});setSelectedIds([item.id]);setSelectedEdgeIds([]);
  }
  function deleteSelection() {
    if(active||!project)return;const removed=new Set(selectedElements(project,selectedIds)),removedEdges=new Set(selectedEdgeIds);if(!removed.size&&!removedEdges.size)return;
    editProject(p=>{p.elements=p.elements.filter(e=>!removed.has(e.id));p.connections=p.connections.filter(c=>!removed.has(c.source)&&!removed.has(c.target)&&!removedEdges.has(c.id));
      p.groups=p.groups.map(g=>({...g,element_ids:g.element_ids.filter(id=>!removed.has(id)),member_keys:Object.fromEntries(Object.entries(g.member_keys).filter(([,v])=>!removed.has(v))),exposed_ports:Object.fromEntries(Object.entries(g.exposed_ports).filter(([,v])=>!removed.has(v.split(':')[0]))),exposed_parameters:Object.fromEntries(Object.entries(g.exposed_parameters).filter(([,v])=>!removed.has(v.split('.')[0])))})).filter(g=>g.element_ids.length);
      p.selected_variables=p.selected_variables.filter(v=>!removed.has(v.split('.')[0]));for(const s of p.scenarios)for(const id of removed)delete s.overrides[id];});setSelectedIds([]);setSelectedEdgeIds([]);
  }
  function selectedProject():Project|null {
    if(!project||!selectedIds.length)return null;return selectionProject(project,selectedIds);
  }
  function pasteProject(source:Project) {
    if(active||!project)return;try{let ids:string[]=[];editProject(p=>{ids=pasteSelection(p,source,page,scopeGroupId);});setSelectedIds(ids);setSelectedEdgeIds([]);}catch(e){reportError(e);}
  }
  async function updateParameter(key:string,value:Parameters[string]) {
    if(selected)await updateElementParameter(selected.id,key,value);
  }
  async function updateElementParameter(id:string,key:string,value:Parameters[string]) {
    const element=project?.elements.find(e=>e.id===id);if(!element)return;
    if(JSON.stringify(effectiveParameters(element)[key])===JSON.stringify(value))return;
    if(active&&runId){try{await api('/runs/'+runId+'/commands',{action:'set',element_id:id,parameter:key,value});}catch(error){reportError(error);return;}}
    editProject(p=>{const scenario=p.scenarios.find(s=>s.id===scenarioId);
      if(scenario){scenario.overrides[id]||={};scenario.overrides[id][key]=value;}else p.elements.find(e=>e.id===id)!.parameters[key]=value;},!active);
  }
  function toggleCurve(path:string) {
    editProject(p=>{if(p.selected_variables.includes(path))p.selected_variables=p.selected_variables.filter(v=>v!==path);else if(p.selected_variables.length<64)p.selected_variables.push(path);else notify('最多同时记录 64 条曲线。',true);},false);
  }
  async function checkModel() {
    if(!project)return;setBusy(true);try{const result=await api<{valid:boolean;diagnostics:Diagnostic[];circuits:Circuit[];node_count:number;branch_count:number}>('/validate',project);setDiagnostics(result.diagnostics);setCircuits(result.circuits);
      if(result.valid)notify(`检查通过 · ${result.node_count} 个压力节点 / ${result.branch_count} 条计算支路`);else{setBottomTab('diagnostics');const id=result.diagnostics[0]?.element_id;if(id)focusElement(id);notify(result.diagnostics[0]?.message||'模型检查未通过',true);}}
    catch(error){reportError(error);}finally{setBusy(false);}
  }
  async function startRun(paused=false) {
    if(!project)return;setBusy(true);
    try{const {run_id}=await api<{run_id:string}>('/runs',{project,scenario_id:scenarioId||null,mode,duration_s:duration,dt_s:dt,speed,start_paused:paused,selected_variables:project.selected_variables});
      lastFrameTime.current=-1;finishedHistory.current=null;setRunId(run_id);setRun({id:run_id,status:'queued',mode,frame:null,name:project.name,project_id:project.id,started:Date.now()/1000,updated:Date.now()/1000});
      setHistory({variables:project.selected_variables,rows:[],total_rows:0});setDiagnostics([]);setStale(false);setBottomTab('trends');
    }catch(error){reportError(error);}finally{setBusy(false);}
  }
  async function sendCommand(action:string) {
    if(!runId)return;try{const response=await api<{run_id?:string}>('/runs/'+runId+'/commands',{action});
      if(response.run_id){setRunId(response.run_id);setRun(prev=>prev?{...prev,id:response.run_id!,status:'queued',frame:null}:prev);lastFrameTime.current=-1;finishedHistory.current=null;setHistory(h=>({...h,rows:[],total_rows:0}));}
    }catch(error){reportError(error);}
  }
  useEffect(()=>{
    if(!runId)return;let alive=true;let lastSequence=-1;let socket:WebSocket|null=null;
    const receive=(incoming:Run)=>{
      if(!alive)return;if(incoming.sequence!=null&&incoming.sequence===lastSequence)return;lastSequence=incoming.sequence??lastSequence+1;
      setRun(previous=>({...previous,...incoming} as Run));if(incoming.command_error)notify(incoming.command_error.message,true);
      if(incoming.frame){const f=incoming.frame;setFrame(f);setDiagnostics(f.diagnostics||[]);setCircuits(f.circuits||[]);
        if(f.time_s>lastFrameTime.current&&f.valid){lastFrameTime.current=f.time_s;setHistory(h=>{const row=[f.time_s,...h.variables.map(path=>{const[id,...keys]=path.split('.');return f.elements[id]?.[keys.join('.')]??null;})];return {...h,rows:[...h.rows,row].slice(-20000),total_rows:h.total_rows+1};});}
        if(incoming.status==='failed'||incoming.status==='event'){setBottomTab('diagnostics');const id=f.diagnostics?.find(x=>x.severity==='error')?.element_id;if(id)focusElement(id);}}
      if(terminal.has(incoming.status)&&finishedHistory.current!==runId){finishedHistory.current=runId;api<History>('/runs/'+runId+'/history').then(h=>{if(alive&&h.variables.length)setHistory(h);}).catch(()=>{});
        if(incoming.status==='completed')notify('计算已完成，结果和曲线已保存。');}
    };
    api<Run>('/runs/'+runId).then(receive).catch(reportError);
    try{socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/v1/runs/${runId}/stream`);socket.onmessage=e=>receive(JSON.parse(e.data));socket.onerror=()=>{};}catch{}
    const timer=setInterval(()=>api<Run>('/runs/'+runId).then(receive).catch(()=>{}),800);
    return()=>{alive=false;clearInterval(timer);socket?.close();};
  },[runId,notify]);
  useEffect(()=>{
    if(modal!=='compare'||!compareIds.length)return;let alive=true;
    const update=()=>Promise.all(compareIds.map(id=>api<Run>('/runs/'+id))).then(data=>{if(alive)setComparison(data);});
    update().catch(reportError);const timer=setInterval(()=>update().catch(()=>{}),800);return()=>{alive=false;clearInterval(timer);};
  },[modal,compareIds]);
  useEffect(()=>{
    function keys(event:KeyboardEvent){const target=event.target as HTMLElement;if(['INPUT','TEXTAREA','SELECT'].includes(target.tagName)||target.isContentEditable)return;
      if(event.key==='Escape'){setModal(null);return;}
      if(event.ctrlKey||event.metaKey){const key=event.key.toLowerCase();if(key==='s'){event.preventDefault();saveProject().catch(reportError);}
        if(key==='z'){event.preventDefault();event.shiftKey?redoEdit():undoEdit();}if(key==='y'){event.preventDefault();redoEdit();}
        if(key==='c'&&selectedIds.length){event.preventDefault();clipboard.current=selectedProject();notify('已复制选中元件及内部连接');}
        if(key==='v'&&clipboard.current){event.preventDefault();pasteProject(clipboard.current);}}
      else if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();deleteSelection();}}
    window.addEventListener('keydown',keys);return()=>window.removeEventListener('keydown',keys);
  });
  async function showHistory(){setRunList(await api<Run[]>('/runs'+(project?'?project_id='+project.id:'')));setModal('history');}
  async function viewRun(id:string){const r=await api<Run>('/runs/'+id);if(r.request?.project)installProject(await api<Project>('/projects/upgrade',r.request.project),true);setRunId(id);setRun(r);setFrame(r.frame);setHistory(await api<History>('/runs/'+id+'/history'));setModal(null);finishedHistory.current=id;lastFrameTime.current=r.frame?.time_s??-1;}
  async function openMedia(){setModal('media');if(project){const result=await api<{valid:boolean;circuits:Circuit[]}>('/validate',project);setCircuits(result.circuits);}}
  async function refreshTemplates(){setTemplates(await api<Template[]>('/templates'));}
  function showLibrary(){setModal('library');refreshTemplates().catch(reportError);}
  function editTemplate(template:Template){setTemplateDraft(copy(template));setDraftGroupId(null);setModal('template');}
  async function openEquipmentTemplate(){
    if(!selected)return;
    const draft=await api<TemplateDraft>('/modules/normalize',{name:selected.name||'设备型号',kind:'equipment',body:{...selected,group_id:null,parameters:effectiveParameters(selected)}});
    setTemplateDraft({...draft,id:selected.template_id||undefined,revision:selected.template_revision||0});setDraftGroupId(null);setModal('template');
  }
  async function openGroupTemplate(group:Group){
    const draft=await api<TemplateDraft>('/modules/extract',{project:projectRef.current,group_id:group.id,scenario_id:scenarioId||null});
    setTemplateDraft({...draft,id:group.template_id||undefined,revision:group.template_revision||0});setDraftGroupId(group.id);setModal('template');
  }
  function configureGroup(group:Group|null=null){setEditingGroupId(group?.id||null);setModal('group');}
  async function saveGroup(name:string,interfaceData:ModuleInterface){
    const current=projectRef.current;if(!current)return;
    const group=current.groups.find(g=>g.id===editingGroupId);
    const response=await api<ModuleResult>('/modules/group',{project:current,element_ids:group?.element_ids||selectedElements(current,selectedIds),group_id:group?.id||null,name,interface:interfaceData});
    if(current!==projectRef.current)throw Error('模型在请求期间发生变化，请重新配置');
    editProject(p=>Object.assign(p,response.project),false);setSelectedIds([groupNodeId(response.group_id!)]);setSelectedEdgeIds([]);setModal(null);
  }
  async function insertModel(template:TemplateDraft,enter=false,fromDraft=false){
    if(active||!projectRef.current)return;if(scopeGroupId&&template.kind==='group'){notify('请返回主画布后插入组合；首版不支持嵌套组合。',true);return;}
    const current=projectRef.current;setBusy(true);
    try{const canvas=document.querySelector('.canvas-area')?.getBoundingClientRect();const center=canvas?flow.screenToFlowPosition({x:canvas.x+canvas.width/2,y:canvas.y+canvas.height/2}):{x:200,y:200};
      const response=await api<ModuleResult>('/modules/insert',{project:current,page,position:{x:center.x-88,y:center.y-55},...(template.id&&!fromDraft?{template_id:template.id,revision:template.revision}:{template:templatePayload(template)})});
      if(current!==projectRef.current)throw Error('模型在请求期间发生变化，请重试插入');
      if(scopeGroupId){const g=response.project.groups.find(g=>g.id===scopeGroupId)!;for(const id of response.element_ids){response.project.elements.find(e=>e.id===id)!.group_id=g.id;g.element_ids.push(id);g.member_keys[id]=id;}}
      const group=response.project.groups.find(g=>g.id===response.group_id);
      if(group&&fromDraft&&template.id){group.template_id=template.id;group.template_revision=template.revision;}
      editProject(p=>Object.assign(p,response.project));setSelectedIds(group?[groupNodeId(group.id)]:response.element_ids);setSelectedEdgeIds([]);setModal(null);if(enter&&group)enterGroup(group);
    }catch(e){reportError(e);}finally{setBusy(false);}
  }
  function templateSaved(template:Template){refreshTemplates().catch(reportError);notify(`型号已保存 · v${template.revision}`);
    if(draftGroupId&&templateDraft&&JSON.stringify(templateDraft.body)===JSON.stringify(template.body)&&JSON.stringify(templateDraft.interface)===JSON.stringify(template.interface)&&projectRef.current?.groups.some(g=>g.id===draftGroupId))editProject(p=>{const group=p.groups.find(g=>g.id===draftGroupId)!;group.template_id=template.id;group.template_revision=template.revision;for(const eid of group.element_ids)if(!Object.values(group.member_keys).includes(eid))group.member_keys[eid]=eid;},false);
  }
  async function previewTemplate(template:TemplateDraft){
    const current=projectRef.current;if(!current||active)return;setBusy(true);
    try{const result=await api<TemplatePreview>('/modules/apply',{project:current,template_id:template.id,revision:template.revision,group_id:inspectorGroup?.id||null,element_id:selected?.id||null});
      if(current!==projectRef.current)throw Error('模型在请求期间发生变化，请重新预览');previewBase.current=current;setPreview(result);setModal('apply');
    }catch(e){reportError(e);}finally{setBusy(false);}
  }
  function applyPreview(){if(!preview)return;if(previewBase.current!==projectRef.current){notify('模型已变化，请重新预览版本。',true);return;}editProject(p=>Object.assign(p,preview.project));setModal(null);notify('版本已应用，可撤销恢复原实例。');}
  function dissolveGroup(group:Group){editProject(p=>{p.groups=p.groups.filter(g=>g.id!==group.id);for(const e of p.elements)if(e.group_id===group.id)e.group_id=null;},false);setScopeGroupId(null);setSelectedIds(group.element_ids);}
  function createScenario(){if(!project)return;const id=uid();const overrides=Object.fromEntries(project.elements.map(e=>[e.id,effectiveParameters(e)]));editProject(p=>p.scenarios.push({id,name:modalName||`工况 ${p.scenarios.length+1}`,overrides}),false);setScenarioId(id);setModalName('');notify('当前参数已保存为工况');}
  async function batchCompare(){const saved=await saveProject();if(!saved)return;const r=await api<{run_ids:string[]}>('/projects/'+saved.id+'/compare',saved.scenarios.map(s=>s.id));setCompareIds(r.run_ids);setComparison([]);setModal('compare');}

  if(!catalog||!project)return <div className="loading-screen"><div className="brand-symbol"><GitBranch size={30}/></div><h1>FluidNet Studio</h1><p>{loadError||'正在连接本地计算服务…'}</p>{loadError&&<button className="primary-button" onClick={()=>location.reload()}>重新连接</button>}</div>;
  const grouped=catalog.components.filter(d=>`${d.name} ${d.description}`.toLowerCase().includes(search.toLowerCase())).reduce<Record<string,ComponentDef[]>>((a,d)=>{(a[d.category]||=[]).push(d);return a;},{});
  const activeGroup=selectedGroup||project.groups.find(g=>g.element_ids.length===selectedIds.length&&g.element_ids.every(id=>selectedIds.includes(id)));
  const resultVariables=Object.entries(frame?.elements||{}).flatMap(([id,values])=>Object.entries(values).map(([key,value])=>({id,key,value})));
  const currentScenario=project.scenarios.find(s=>s.id===scenarioId);
  const selectionText=[selectedIds.length?`${selectedIds.length} 个${selectedGroup?'组合':'元件'}`:'',selectedEdgeIds.length?`${selectedEdgeIds.length} 条连接`:''].filter(Boolean).join('、');
  return <div className="studio">
    <header className="app-header"><div className="brand"><span className="brand-symbol"><GitBranch size={25}/></span><div><strong>FluidNet <span>Studio</span></strong><small>流体网络计算工作台</small></div></div>
      <span className="header-divider"/><button className="project-switch" onClick={()=>{refreshProjects().catch(reportError);setModal('projects');}}><FolderOpen size={17}/><span>{project.name}</span><ChevronDown size={14}/></button>
      <span className={`save-state ${dirty?'unsaved':''}`}><span/>{dirty?'未保存':'已保存'}{project.revision>0&&<small>v{project.revision}</small>}</span>
      <div className="header-spacer"/><span className="local-indicator"><span/> 本地计算服务</span><button className="icon-button" title="使用说明" onClick={()=>setModal('help')}><CircleHelp size={18}/></button><button className="secondary-button" onClick={()=>saveProject().catch(reportError)}><Save size={15}/> 保存项目</button>
    </header>
    <div className="run-toolbar"><div className="toolbar-group"><div className="segmented"><button className={mode==='steady'?'active':''} disabled={active} onClick={()=>setMode('steady')}>稳态求解</button><button className={mode==='dynamic'?'active':''} disabled={active} onClick={()=>{setMode('dynamic');if(!project.options.thermal)editProject(p=>{p.options.thermal=true;});}}>动态运行</button></div>
      <select aria-label="当前工况" className="scenario-select" disabled={active} value={scenarioId} onChange={e=>{setScenarioId(e.target.value);setStale(true);}}><option value="">当前模型参数</option>{project.scenarios.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select><button className="icon-button" title="工况管理与对比" onClick={()=>setModal('cases')}><Layers3 size={17}/></button></div>
      <div className="toolbar-group run-options">{mode==='dynamic'?<><label>步长<input aria-label="时间步长" type="number" min="0.001" max="60" step="0.1" disabled={active} value={dt} onChange={e=>setDt(+e.target.value)}/><span>s</span></label><label>时长<input aria-label="模拟时长" type="number" min="0.1" disabled={active} value={duration} onChange={e=>setDuration(+e.target.value)}/><span>s</span></label><select aria-label="运行倍速" value={speed} disabled={active} onChange={e=>setSpeed(+e.target.value)}>{[1,2,5,10,100,1000].map(v=><option key={v} value={v}>{v}×</option>)}</select></>:<label className="thermal-option"><input type="checkbox" checked={project.options.thermal} disabled={active} onChange={e=>editProject(p=>{p.options.thermal=e.target.checked;})}/><ThermometerIcon/> 热力耦合</label>}</div>
      <div className="header-spacer"/><button className="text-button check-button" onClick={checkModel} disabled={busy||active}><CheckCircle2 size={16}/> 检查模型</button>
      <div className="play-controls">{!active?<button className="primary-button run-button" data-testid="run-button" disabled={busy||!project.elements.length} onClick={()=>startRun()}><Play size={15} fill="currentColor"/> {mode==='steady'?'计算':'运行'}</button>:run?.status==='paused'?<button className="primary-button" onClick={()=>sendCommand('resume')}><Play size={15}/> 继续</button>:<button className="primary-button" disabled={mode==='steady'||run?.status==='queued'} onClick={()=>sendCommand('pause')}><Pause size={15}/> 暂停</button>}
      <button className="icon-button bordered" title="单步（先进入暂停）" aria-label="单步推进" disabled={mode!=='dynamic'||busy||(active&&run?.status!=='paused')} onClick={()=>active?sendCommand('step'):startRun(true)}><SkipForward size={18}/></button><button className="icon-button bordered" title="停止运行" aria-label="停止运行" disabled={!active} onClick={()=>sendCommand('stop')}><Square size={14}/></button><button className="icon-button bordered" title="重置到本工况初始状态" disabled={!runId||mode!=='dynamic'} onClick={()=>sendCommand('reset')}><RotateCcw size={16}/></button></div>
    </div>
    {recovery&&<div className="recovery-banner"><span>发现此项目的本地未保存草稿。</span><button onClick={()=>{const p=recovery;installProject(p,false);}}>恢复草稿</button><button onClick={()=>{localStorage.removeItem('fluidnet:draft:'+project.id);setRecovery(null);}}>忽略草稿</button></div>}
    <div className="workspace">
      <aside className="library-panel"><div className="panel-heading"><span><BoxIcon/> 模块库</span><span className="count-badge">{catalog.components.length}</span></div><div className="library-tabs"><button className={libraryTab==='components'?'active':''} onClick={()=>setLibraryTab('components')}>设备模块</button><button className={libraryTab==='templates'?'active':''} onClick={()=>setLibraryTab('templates')}>型号与组合</button></div>
        <div className="library-search"><Search size={15}/><input aria-label="搜索模块" placeholder="搜索模块…" value={search} onChange={e=>setSearch(e.target.value)}/><kbd>/</kbd></div>
        <div className="library-scroll">{libraryTab==='components'?Object.entries(grouped).map(([category,items])=><details key={category} className="library-category" open><summary>{category}<ChevronDown size={12}/></summary>{items.map(d=><button key={d.type} className={`library-item ${d.category==='热设备'?'orange':d.control?'purple':''}`} draggable={!active} disabled={active} title={d.description} onDragStart={event=>{event.dataTransfer.setData('application/fluidnet-type',d.type);event.dataTransfer.effectAllowed='copy';}} onClick={()=>addElement(d.type)}><span><EquipmentIcon name={d.icon} size={19}/></span><div><strong>{d.name}</strong><small>{d.ports.length?`${d.ports.length} 个流体端口`:'控制逻辑'}</small></div><Plus size={13}/></button>)}</details>):<>
          {!templates.length&&<div className="library-empty"><Library size={26}/><p>保存设备型号或组合模块后，可在这里重复使用。</p></div>}
          {templates.filter(t=>t.name.includes(search)).map(t=><button className="library-item" key={t.id} disabled={active||!!t.validation_error} title={t.validation_error} onClick={()=>insertModel(t)}><span><Package size={18}/></span><div><strong>{t.name}</strong><small>{t.kind==='group'?'组合模块':'设备型号'} · v{t.revision}{t.validation_error?' · 需要修复':''}</small></div><Plus size={13}/></button>)}
        </>}</div><button className="library-manage" onClick={showLibrary}><Library size={16}/> 型号管理与验证</button><button className="library-footer" onClick={()=>setModal('examples')}><FlaskConical size={18}/><span>打开示例项目<small>6 套可验证的标准模型</small></span><ArrowRight size={16}/></button>
      </aside>
      <main className="center-workspace"><div className="canvas-topbar"><div className="canvas-pages">{scopeGroup?<div className="module-breadcrumb" data-testid="module-breadcrumb"><button onClick={()=>{setScopeGroupId(null);setSelectedIds([groupNodeId(scopeGroup.id)]);setSelectedEdgeIds([]);}}>主画布</button><span>/</span><strong>{scopeGroup.name}</strong><button onClick={()=>configureGroup(scopeGroup)}>配置接口</button></div>:<>{Array.from({length:Math.min(16,Math.max(page+1,1,...project.elements.map(e=>e.page+1)))},(_,i)=><button key={i} className={page===i?'active':''} onClick={()=>{setPage(i);setSelectedIds([]);setSelectedEdgeIds([]);}}><GitBranch size={13}/> 画布 {i+1}</button>)}<button className="icon-button" title="新增画布" disabled={page>=15} onClick={()=>{setPage(p=>Math.min(15,p+1));setSelectedIds([]);setSelectedEdgeIds([]);}}><Plus size={14}/></button>{selected?.group_id&&<button onClick={()=>enterGroup(project.groups.find(g=>g.id===selected.group_id)!)}>进入所在组合</button>}</>}</div>
        <div className="canvas-tools"><button className="icon-button" title="撤销 Ctrl+Z" disabled={active||!undo.current.length} onClick={undoEdit}><Undo2 size={16}/></button><button className="icon-button" title="重做 Ctrl+Y" disabled={active||!redo.current.length} onClick={redoEdit}><Redo2 size={16}/></button><span className="mini-divider"/><button className="icon-button" title="复制选中元件" disabled={!selectedIds.length||active} onClick={()=>{clipboard.current=selectedProject();notify('已复制；Ctrl+V 粘贴');}}><Copy size={15}/></button><button className="icon-button" title="封装选中元件" disabled={(!selectedIds.length&&!scopeGroup)||active} onClick={()=>configureGroup(scopeGroup||activeGroup||null)}><Package size={16}/></button><button className="icon-button" title="删除选中元件或连接" disabled={!selectionText||active} onClick={deleteSelection}><Trash2 size={15}/></button><span className="mini-divider"/><button className="icon-button" title="适应画布" onClick={()=>flow.fitView({padding:0.22,duration:250})}><Maximize2 size={16}/></button><button className="icon-button" title="显示 / 隐藏属性面板" onClick={()=>setShowInspector(!showInspector)}><PanelRightClose size={16}/></button></div></div>
        <div className="canvas-area" onDragOver={e=>{e.preventDefault();e.dataTransfer.dropEffect='copy';}} onDrop={e=>{e.preventDefault();const type=e.dataTransfer.getData('application/fluidnet-type');if(type)addElement(type,flow.screenToFlowPosition({x:e.clientX,y:e.clientY}));}}>
          <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodeChanges} onEdgesChange={onEdgeChanges} onConnect={onConnect} connectionMode={ConnectionMode.Loose}
            onNodeDoubleClick={(_,node)=>{if(node.data.group)enterGroup(node.data.group);}}
            onNodeDragStop={(_,node,dragged)=>{if(active)return;const moved=dragged.length?dragged:[node];editProject(p=>{for(const n of moved){if(isGroupNode(n.id)){const g=p.groups.find(g=>g.id===n.id.slice(6));if(!g)continue;const dx=n.position.x-g.position.x,dy=n.position.y-g.position.y;g.position=n.position;for(const e of p.elements)if(g.element_ids.includes(e.id))e.position={x:e.position.x+dx,y:e.position.y+dy};}else{const e=p.elements.find(e=>e.id===n.id);if(e)e.position=n.position;}}},false);}}
            onSelectionChange={onSelectionChange}
            onEdgesDelete={deleted=>{if(!active)editProject(p=>{const ids=new Set(deleted.map(e=>e.id));p.connections=p.connections.filter(c=>!ids.has(c.id));});}}
            deleteKeyCode={null} minZoom={0.04} maxZoom={2} fitView fitViewOptions={{padding:0.22,maxZoom:1}} onlyRenderVisibleElements selectionOnDrag panOnDrag={[1,2]} nodesConnectable={!active} proOptions={{hideAttribution:false}}>
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#c8d5dc"/><Controls showInteractive={false}/><MiniMap pannable zoomable nodeColor={n=>defs.get((n.data as EquipmentData).element?.type)?.category==='热设备'?'#dbab6c':'#82b9b6'} maskColor="rgba(235,242,245,.7)"/>
          </ReactFlow>
          <div className="canvas-overlay-controls"><div className="overlay-tabs">{(['flow','pressure','temperature'] as const).map(v=><button className={overlay===v?'active':''} key={v} onClick={()=>setOverlay(v)}>{v==='flow'?<Activity size={13}/>:v==='pressure'?<GaugeIcon/>:<ThermometerIcon/>}{v==='flow'?'流量':v==='pressure'?'压力':'温度'}</button>)}</div><button className="medium-chip" onClick={()=>openMedia().catch(reportError)}><Droplets size={13}/>{project.media.find(m=>m.id===project.default_medium_id)?.name}<ChevronDown size={12}/></button></div>
          {stale&&frame&&<div className="stale-banner"><AlertCircle size={14}/> 模型或工况已更改，请重新计算</div>}
          {!project.elements.length&&<div className="canvas-empty"><span className="empty-network"><GitBranch size={44}/></span><h2>从一条通路开始</h2><p>点击或拖入左侧模块，连接端口，构建你的流体网络。</p><button className="secondary-button" onClick={()=>setModal('examples')}><FlaskConical size={15}/> 从示例开始</button></div>}
          <div className="canvas-hint">{selectionText?`已选择 ${selectionText}${activeGroup?' · '+activeGroup.name:''}`:'拖入元件 · 连接端口 · 框选编辑'}{project.elements.some(e=>e.page!==page)&&<span>其他画布的通路仍参与计算</span>}</div>
        </div>
        <section className="bottom-panel"><div className="bottom-heading"><div className="bottom-tabs"><button className={bottomTab==='trends'?'active':''} onClick={()=>setBottomTab('trends')}><TrendingUp size={14}/> 运行曲线</button><button className={bottomTab==='diagnostics'?'active':''} onClick={()=>setBottomTab('diagnostics')}><Activity size={14}/> 求解诊断{diagnostics.length>0&&<span className="count-badge warning">{diagnostics.length}</span>}</button><button className={bottomTab==='results'?'active':''} onClick={()=>setBottomTab('results')}><Layers3 size={14}/> 结果总表</button></div>
          <div className="bottom-actions"><span className="time-value"><Clock3 size={13}/> {numberText(frame?.time_s??0,6)} <small>s</small></span><button className="icon-button" title="历史运行" onClick={()=>showHistory().catch(reportError)}><Clock3 size={15}/></button><button className="icon-button" title="下载完整曲线 CSV" disabled={!runId} onClick={()=>window.open(`/api/v1/runs/${runId}/results?format=csv`,'_blank')}><Download size={15}/></button></div></div>
          <div className="bottom-content">{bottomTab==='trends'?(history.variables.length&&history.rows.length?<TrendChart history={history} project={project} catalog={catalog} units={units}/>:<div className="chart-empty"><TrendingUp size={30}/><div><strong>{project.selected_variables.length?`已选择 ${project.selected_variables.length} 个记录变量`:'让变化成为可见的曲线'}</strong><p>{project.selected_variables.length?'运行后显示随仿真时间变化的记录。':'计算后在元件的「运行结果」中勾选变量，再开始记录。'}</p></div></div>):bottomTab==='diagnostics'?<div className="diagnostics-view"><div className="metric-cards"><div><span>质量残差</span><strong>{numberText(frame?.metrics.mass_residual_kg_s,3)}<small> kg/s</small></strong></div><div><span>压差残差</span><strong>{numberText(frame?.metrics.pressure_residual_pa,3)}<small> Pa</small></strong></div><div><span>热量残差</span><strong>{numberText(frame?.metrics.energy_residual_w,3)}<small> W</small></strong></div><div><span>求解用时</span><strong>{numberText(frame?.metrics.elapsed_s==null?null:frame.metrics.elapsed_s*1000,4)}<small> ms</small></strong></div></div>
            {diagnostics.length?diagnostics.map((d,i)=><button className={`diagnostic-row ${d.severity}`} key={i} onClick={()=>{if(d.element_id){const e=project.elements.find(e=>e.id===d.element_id);if(e)focusElement(e.id);}}}><AlertCircle size={15}/><span><strong>{d.message}</strong><small>{d.code}{d.element_id?' · '+d.element_id:''}</small></span><ArrowRight size={14}/></button>):<div className="clean-diagnostic"><CheckCircle2 size={18}/>{frame?.valid?'当前结果通过守恒残差检查。':'模型检查与求解过程中产生的诊断会显示在这里。'}</div>}</div>:<div className="results-table-wrap"><table className="results-table"><thead><tr><th>元件</th><th>变量</th><th>数值</th><th>单位</th></tr></thead><tbody>{resultVariables.map(({id,key,value})=>{const meta=catalog.variables[key.split('.').at(-1)||key]||{label:key,unit:''};return <tr key={id+key} onClick={()=>focusElement(id)}><td>{project.elements.find(e=>e.id===id)?.name||id}</td><td>{key.includes('.')?key.split('.')[0].toUpperCase()+' · ':''}{meta.label}</td><td className="numeric">{numberText(displayValue(value,key,meta.unit,units,project.atmosphere_pa),7)}</td><td>{variableUnit(key,meta.unit,units)}</td></tr>;})}</tbody></table>{!frame&&<div className="table-empty">尚无计算结果</div>}</div>}</div>
        </section>
      </main>
      {showInspector&&(inspectorGroup?<GroupInspector group={inspectorGroup} project={project} catalog={catalog} units={units} active={active} parameters={effectiveParameters} onParameter={updateElementParameter} onName={name=>editProject(p=>{p.groups.find(g=>g.id===inspectorGroup.id)!.name=name;},false)} onEnter={()=>enterGroup(inspectorGroup)} onConfigure={()=>configureGroup(inspectorGroup)} onSave={()=>openGroupTemplate(inspectorGroup).catch(reportError)} onLibrary={showLibrary} onDissolve={()=>dissolveGroup(inspectorGroup)} onExpand={()=>{editProject(p=>{p.groups.find(g=>g.id===inspectorGroup.id)!.collapsed=!inspectorGroup.collapsed;},false);setScopeGroupId(null);setSelectedIds([groupNodeId(inspectorGroup.id)]);}} onMember={focusElement}/>:<Inspector element={selected} definition={selectedDef} project={project} parameters={selected?effectiveParameters(selected):{}} catalog={catalog} frame={frame} active={active} stale={stale} units={units} onParameter={updateParameter} onName={name=>{if(selected)editProject(p=>{p.elements.find(e=>e.id===selected.id)!.name=name;},false);}} onMedium={(group,id)=>{if(selected)editProject(p=>{const e=p.elements.find(x=>x.id===selected.id)!;if(id)e.media[group]=id;else delete e.media[group];});}} onCurve={toggleCurve} onSaveModel={()=>openEquipmentTemplate().catch(reportError)} onMedia={()=>openMedia().catch(reportError)} onSettings={()=>setModal('settings')}/>)}
    </div>
    <footer className="status-bar"><span className={`status-dot ${run?.status==='failed'?'error':active?'running':''}`}/><strong>{run?statusLabel[run.status]||run.status:'就绪'}</strong>{frame?.last_valid_state&&<span className="status-warning">保留最后有效状态</span>}<span className="status-separator"/><span>{project.elements.length} 元件</span><span>{project.connections.length} 连接</span><span className="header-spacer"/><button onClick={()=>setModal('settings')}>单位：{units.pressure==='gauge'?'kPa(g)':'kPa'} · {units.flow==='volume'?'m³/h':'kg/s'} · {units.temperature==='celsius'?'°C':'K'}</button><span className="status-separator"/><span>FluidNet {health?.version||'0.2.0'}</span></footer>
    <input ref={inputFile} type="file" accept=".json" className="hidden" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;try{const parsed=JSON.parse(await file.text());if(![1,2].includes(parsed.schema_version)||!Array.isArray(parsed.elements)||!Array.isArray(parsed.connections))throw new Error('不是受支持的项目文件');parsed.id=uid();parsed.revision=0;const stored=await api<Project>('/projects',parsed);installProject(stored);await refreshProjects();setModal(null);notify('项目已导入');}catch(error){reportError(error);}finally{e.target.value='';}}}/>
    {toast&&<div className={`toast ${toast.error?'error':''}`} role="status">{toast.error?<AlertCircle size={17}/>:<CheckCircle2 size={17}/>}<span>{toast.message}</span><button onClick={()=>setToast(null)}><X size={14}/></button></div>}
    {modal==='projects'&&<ModalBox title="项目工作区" subtitle="本地保存，保留版本，可随时恢复工况。" onClose={()=>setModal(null)} wide><div className="modal-action-row"><button className="primary-button" onClick={()=>{installProject(blankProject(),false);setModal(null);}}><FilePlus2 size={16}/> 新建项目</button><button className="secondary-button" onClick={()=>inputFile.current?.click()}><Upload size={15}/> 导入 JSON</button><button className="secondary-button" onClick={()=>download(project.name+'.json',JSON.stringify(project,null,2))}><Download size={15}/> 导出当前项目</button><button className="text-button" onClick={()=>setModal('examples')}>查看示例</button></div><div className="project-cards">{projectList.map(p=><button className={`project-card ${p.id===project.id?'current':''}`} key={p.id} onClick={()=>openSaved(p.id).catch(reportError)}><span className="project-card-icon"><GitBranch size={26}/></span><strong>{p.name}</strong><span>版本 {p.revision} · {new Date(p.updated*1000).toLocaleDateString()}</span><ArrowRight size={17}/></button>)}</div><div className="modal-action-row"><button className="secondary-button" onClick={()=>{const p=copy(project);p.id=uid();p.revision=0;p.name+=' · 副本';installProject(p,false);setModal(null);}}>当前项目另存为副本</button><button className="text-button" onClick={async()=>{try{setVersions(await api('/projects/'+project.id+'/versions'));setModal('versions');}catch(error){reportError(error);}}}>查看当前项目版本</button></div></ModalBox>}
    {modal==='examples'&&<ModalBox title="从可验证的模型开始" subtitle="六套标准示例。载入后生成独立副本，可自由修改。" onClose={()=>setModal(null)} wide><div className="example-grid">{examples.map((p,i)=><button className="example-card" key={p.id} onClick={()=>{const next=copy(p);next.id=uid();next.revision=0;installProject(next,false);setModal(null);}}><span className="example-number">0{i+1}</span><div className="example-visual"><GitBranch size={48}/>{i===4?<Droplets size={22}/>:i===5?<Activity size={22}/>:<WavesIcon/>}</div><strong>{p.name.slice(5)}</strong><p>{p.description}</p><span className="example-meta">{p.elements.length} 个元件 <ArrowRight size={14}/></span></button>)}</div></ModalBox>}
    {modal==='media'&&<ModalBox title="介质与流体回路" subtitle="物性、流动模型和设备适用性分别校验；换热器两侧保持独立。" onClose={()=>setModal(null)} wide><div className="medium-catalog">{catalog.media.map(m=><div className={`medium-card ${m.enabled?'enabled':''}`} key={m.kind}><Droplets size={22}/><strong>{m.name}</strong><span>{m.enabled?'已启用':'预留接口'}</span><p>{m.description}</p></div>)}</div>
      <h3 className="modal-section-heading">项目介质配置<button className="text-button" disabled={active} onClick={()=>editProject(p=>p.media.push({...copy(DEFAULT_WATER),id:'water_'+uid().slice(0,6),name:'液态水配置 '+(p.media.length+1)}))}><Plus size={14}/> 新增水介质配置</button></h3>
      {project.media.map(m=><div className="medium-definition" key={m.id}><Droplets size={19}/><input aria-label="介质名称" disabled={active} value={m.name} onChange={e=>editProject(p=>{p.media.find(x=>x.id===m.id)!.name=e.target.value;},false)}/><span>{m.backend}</span><span>{m.components.join(' / ')} · 质量分数 {m.mass_fractions.join(' / ')}</span><span className="phase-badge">{m.phase_policy==='liquid'?'液相':m.phase_policy}</span></div>)}
      <label className="setting-row"><span>新建回路默认介质</span><select disabled={active} value={project.default_medium_id} onChange={e=>editProject(p=>{p.default_medium_id=e.target.value;})}>{project.media.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
      <h3 className="modal-section-heading">已识别的流体回路</h3>{circuits.length?circuits.map((c,i)=><div className="circuit-row" key={c.id}><span className="circuit-number">{i+1}</span><div><strong>回路 {i+1}</strong><small>{c.ports.length} 个流体端口 · {c.id}</small></div><select aria-label={`回路 ${i+1} 介质`} disabled={active} value={c.medium_id} onChange={e=>{const mid=e.target.value;editProject(p=>{for(const address of c.ports){const[id,port]=address.split(':');const element=p.elements.find(x=>x.id===id);const group=element&&defs.get(element.type)?.ports.find(x=>x.id===port)?.group;if(element&&group)element.media[group]=mid;}});setCircuits(cs=>cs.map(x=>x.id===c.id?{...x,medium_id:mid}:x));}}>{project.media.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></div>):<div className="empty-notice">完成连接并通过模型检查后显示回路。建模过程中也可在元件属性中指定介质。</div>}
      <p className="field-help">其他介质的物性、相态和求解模型尚未启用，不会自动套用水的计算结果。</p></ModalBox>}
    {modal==='settings'&&<ModalBox title="项目与显示设置" onClose={()=>setModal(null)}><label className="setting-row"><span>项目名称</span><input value={project.name} onChange={e=>editProject(p=>{p.name=e.target.value;},false)}/></label><label className="setting-block"><span>项目说明</span><textarea rows={3} value={project.description} onChange={e=>editProject(p=>{p.description=e.target.value;},false)}/></label>
      <h3 className="modal-section-heading">显示单位</h3><label className="setting-row"><span>压力</span><select value={units.pressure} onChange={e=>setUnits(u=>({...u,pressure:e.target.value as Units['pressure']}))}><option value="gauge">kPa 表压</option><option value="absolute">kPa 绝压</option></select></label><label className="setting-row"><span>流量覆盖显示</span><select value={units.flow} onChange={e=>setUnits(u=>({...u,flow:e.target.value as Units['flow']}))}><option value="volume">m³/h 体积流量</option><option value="mass">kg/s 质量流量</option></select></label><label className="setting-row"><span>温度</span><select value={units.temperature} onChange={e=>setUnits(u=>({...u,temperature:e.target.value as Units['temperature']}))}><option value="celsius">摄氏度 °C</option><option value="kelvin">开尔文 K</option></select></label>
      <h3 className="modal-section-heading">计算设置</h3><ParameterInput def={{key:'atmosphere_pa',label:'当地大气压力（绝压）',kind:'number',unit:'Pa',default:101325,positive:true}} value={project.atmosphere_pa} units={{...units,pressure:'absolute'}} atmosphere={project.atmosphere_pa} disabled={active} onCommit={v=>editProject(p=>{p.atmosphere_pa=Number(v);})}/><ParameterInput def={{key:'initial_temperature_k',label:'默认节点初始温度',kind:'number',unit:'K',default:293.15,positive:true}} value={project.initial_temperature_k} units={units} atmosphere={project.atmosphere_pa} disabled={active} onCommit={v=>editProject(p=>{p.initial_temperature_k=Number(v);})}/><label className="setting-row"><span>最大水力迭代次数</span><input type="number" min="1" max="500" disabled={active} value={project.options.max_iterations} onChange={e=>editProject(p=>{p.options.max_iterations=+e.target.value;})}/></label><p className="field-help">计算内核使用 Pa 绝压、K、kg/s 和 W。界面单位变化不改变物理模型。</p></ModalBox>}
    {modal==='cases'&&<ModalBox title="工况管理" subtitle="保存当前参数组合，或批量计算比较不同设备设置。" onClose={()=>setModal(null)}><div className="name-entry"><input aria-label="工况名称" placeholder="新的工况名称" value={modalName} onChange={e=>setModalName(e.target.value)}/><button className="primary-button" disabled={active} onClick={createScenario}><Plus size={15}/> 保存工况</button></div>{project.scenarios.map(s=><div className="case-row" key={s.id}><Layers3 size={18}/><div><strong>{s.name}</strong><small>{Object.keys(s.overrides).length} 个元件参数快照</small></div><button className="text-button" disabled={active} onClick={()=>{setScenarioId(s.id);setStale(true);setModal(null);}}>使用</button><button className="icon-button" title="删除工况" disabled={active} onClick={()=>{editProject(p=>{p.scenarios=p.scenarios.filter(x=>x.id!==s.id);},false);if(scenarioId===s.id)setScenarioId('');}}><Trash2 size={14}/></button></div>)}<div className="modal-action-row"><button className="primary-button" disabled={!project.scenarios.length||active} onClick={()=>batchCompare().catch(reportError)}><Activity size={15}/> 批量计算并对比</button></div><p className="field-help">选择工况后，属性面板修改的是该工况的覆盖参数。切回「当前模型参数」可编辑基础模型。</p></ModalBox>}
    {modal==='group'&&<ModalBox title="组合设备接口" subtitle="配置真实内部端口和参数，计算沿用完整管网。" wide onClose={()=>setModal(null)}><GroupEditor key={editingGroupId||selectedIds.join(',')} project={project} members={project.groups.find(g=>g.id===editingGroupId)?.element_ids||selectedElements(project,selectedIds)} group={project.groups.find(g=>g.id===editingGroupId)||null} catalog={catalog} onSave={saveGroup} onClose={()=>setModal(null)}/></ModalBox>}
    {modal==='library'&&<ModalBox title="型号管理与验证" subtitle="型号版本与项目实例独立保存，可在预览差异后手动应用。" wide onClose={()=>setModal(null)}><TemplateLibrary items={templates} disabled={active||busy} onEdit={editTemplate} onInsert={t=>insertModel(t)} onApply={previewTemplate} canApply={!!(selected||inspectorGroup)} onRefresh={()=>refreshTemplates().catch(reportError)} onError={reportError}/></ModalBox>}
    {modal==='template'&&templateDraft&&<ModalBox title="型号编辑与独立验证" subtitle="编辑参数、定义接口，再用测试边界验证设备行为。" wide onClose={()=>setModal(null)}><TemplateEditor initial={templateDraft} catalog={catalog} units={units} onSaved={templateSaved} onInsert={(t,enter)=>insertModel(t,enter,true)} onBack={showLibrary} onApply={previewTemplate} canApply={!!(selected||inspectorGroup)&&!active}/></ModalBox>}
    {modal==='apply'&&preview&&<ModalBox title="应用型号版本" subtitle="以下修改仅在点击应用后写入当前项目，可以撤销。有效的工况覆盖与曲线引用会保留。" wide onClose={()=>setModal(null)}><div className="version-diff"><h3>结构变化</h3><p>新增：{preview.changes.added.join('、')||'无'}；移除：{preview.changes.removed.join('、')||'无'}；内部连接变化：{preview.changes.connections}</p><h3>接口变化</h3>{preview.changes.interfaces?.length?preview.changes.interfaces.map((line,i)=><p key={i}>{line}</p>):<p>无接口变化</p>}<h3>基础参数变化</h3>{preview.changes.parameters.length?preview.changes.parameters.map((line,i)=><p key={i}>{line}</p>):<p>无基础参数变化</p>}</div><div className="module-actions"><button className="secondary-button" onClick={()=>setModal(null)}>取消</button><button className="primary-button" onClick={applyPreview}>应用此版本</button></div></ModalBox>}
    {modal==='history'&&<ModalBox title="运行历史" subtitle="每次运行保存独立的模型、介质和参数快照。" onClose={()=>setModal(null)} wide>{runList.length?<table className="results-table history-table"><thead><tr><th>项目 / 工况</th><th>模式</th><th>状态</th><th>时间</th><th>结果</th></tr></thead><tbody>{runList.map(r=><tr key={r.id}><td>{r.name}</td><td>{r.mode==='steady'?'稳态':'动态'}</td><td><span className={'run-badge '+r.status}>{statusLabel[r.status]||r.status}</span></td><td>{new Date(r.started*1000).toLocaleString()}</td><td><button className="text-button" onClick={()=>viewRun(r.id).catch(reportError)}>查看</button><a href={`/api/v1/runs/${r.id}/results?format=html`} className="text-button">报告</a><a href={`/api/v1/runs/${r.id}/results?format=csv`} className="text-button">CSV</a></td></tr>)}</tbody></table>:<div className="empty-notice">此项目尚无运行记录。</div>}</ModalBox>}
    {modal==='compare'&&<ModalBox title="工况对比" subtitle="各工况使用相同内核独立计算，最多两个任务同时运行。" onClose={()=>setModal(null)} wide><div className="comparison-cards">{comparison.map(r=><div className="comparison-card" key={r.id}><strong>{r.name}</strong><span className={'run-badge '+r.status}>{statusLabel[r.status]||r.status}</span><button className="text-button" onClick={()=>viewRun(r.id).catch(reportError)}>打开结果</button></div>)}</div><div className="comparison-scroll"><table className="results-table"><thead><tr><th>记录变量</th>{comparison.map(r=><th key={r.id}>{r.name.split(' / ').at(-1)}</th>)}</tr></thead><tbody>{project.selected_variables.map(path=>{const[id,...keys]=path.split('.');const key=keys.join('.');const meta=catalog.variables[keys.at(-1)||'']||{label:key,unit:''};return <tr key={path}><td>{project.elements.find(e=>e.id===id)?.name} · {meta.label} <small>{variableUnit(key,meta.unit,units)}</small></td>{comparison.map(r=><td key={r.id} className="numeric">{numberText(r.frame?.elements[id]?.[key]==null?null:displayValue(r.frame.elements[id][key],key,meta.unit,units,project.atmosphere_pa),6)}</td>)}</tr>;})}</tbody></table></div></ModalBox>}
    {modal==='versions'&&<ModalBox title="项目版本" subtitle="载入历史版本后可另存为新项目，当前保存版本仍保留。" onClose={()=>setModal(null)}>{versions.map(v=><div className="case-row" key={v.revision}><Clock3 size={18}/><div><strong>版本 {v.revision}</strong><small>{new Date(v.created*1000).toLocaleString()}</small></div><button className="text-button" onClick={async()=>{try{const p=await api<Project>(`/projects/${project.id}?revision=${v.revision}`);p.id=uid();p.revision=0;p.name+=` · v${v.revision} 副本`;installProject(p,false);setModal(null);}catch(error){reportError(error);}}}>载入副本</button></div>)}</ModalBox>}
    {modal==='help'&&<ModalBox title="开始使用 FluidNet" onClose={()=>setModal(null)}><div className="help-steps">{[['01','搭建网络','点击或拖入模块，从一个端口连接到另一个端口。分支使用连接节点，换热器两侧分别连接各自回路。'],['02','设置物理参数','至少为每个回路设置压力参考。管径使用实际内径，泵需要有效曲线。检查介质配置和热力边界。'],['03','求解与调节','先检查模型，再稳态计算。慢动态可以暂停、单步，在线调节带绿点的参数。'],['04','保存与复现','保存项目和工况；从运行历史获取原始曲线、参数快照及计算报告。']].map(([n,title,desc])=><div key={n}><span>{n}</span><section><h3>{title}</h3><p>{desc}</p></section></div>)}</div><div className="shortcut-list"><span><kbd>Ctrl</kbd> + <kbd>S</kbd> 保存</span><span><kbd>Ctrl</kbd> + <kbd>Z</kbd> 撤销</span><span><kbd>Ctrl</kbd> + <kbd>C / V</kbd> 复制粘贴</span><span><kbd>Delete</kbd> 删除</span></div><p className="field-help">流体连接支持逆流；画布中的方向仅为正方向参考。首版采用单相水慢动态近似，不模拟压力波、气蚀和相变。</p><a className="text-button" href="/docs" target="_blank" rel="noreferrer">打开本地 API 文档 <ArrowRight size={14}/></a></ModalBox>}
  </div>;
}
function ThermometerIcon(){return <span className="small-symbol">°</span>;}
function GaugeIcon(){return <Activity size={13}/>;}
function BoxIcon(){return <Package size={16}/>;}
function WavesIcon(){return <Activity size={22}/>;}
