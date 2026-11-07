import {loadFrontend} from './frontend-module-loader.mjs';
import vm from 'node:vm';
export const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
export function fixture(status='running') {
  const node={params:{heat_input_w:5000},draft:{heat_input_w:6000}};
  const frame={t:60,canonical:{'Own-Room.state.temperature_k':255.15}};
  const run={id:'archive',runId:status==='running'?'archive':null,live:status==='running',status,history:[frame],events:[]};
  const owner={id:'p',run,pages:[{nodes:[node]}],solver:{continuous:false,duration:1,dt:.1}},state={projects:[owner],charts:{range:'window'}};
  const calls=[],messages=[],pending=new Map();let persists=0,renders=0,refreshes=0,prepared=0;
  const host=vm.createContext({window:{},AbortController,crypto:{randomUUID:()=> 'command-1'},setTimeout});
  for(const file of ['project-run-state.js','run-commands.js'])
    loadFrontend(new URL('../frontend/'+file,import.meta.url),host);
  const hooks={
    request:async path=>{
      if(path.endsWith('/command'))return {command_id:'command-1',command_status:'queued'};
      if(path.endsWith('/events'))return {events:[{command_id:'command-1',command_status:'applied',time_s:61}]};
      if(path.includes('/history'))return {total_rows:2,rows:[{time_s:61,variables:{flow:2}}]};
      if(path.endsWith('/overview'))return {rows:[{time_s:61,variables:{flow:2}}],stride:1,total_rows:2};
      if(path==='/runs?background=true')return {run_id:'started'};
      return {id:path.split('/').at(-1),status:'running',events:[],frame:{valid:true,time_s:61,variables:{flow:2}}};
    },
    normalize:async()=>({id:'canonical'}),delay:async()=>{},confirmArchiveCache:async()=>{},key:()=> 'stable',
  };
  const api=host.window.FluidNetRunCommands.create({state:()=>state,request:(...args)=>{calls.push(args);return hooks.request(...args);},
    runState:host.window.FluidNetProjectRunState,pending,key:()=>hooks.key(),parameterKey:()=> 'parameter-key',normalize:(...args)=>hooks.normalize(...args),
    runMetadata:()=>({project_revision:3}),trendVariables:()=>['flow'],emptyRun:()=>({history:[],events:[]}),
    prepareRun:()=>{prepared++;},rowFromFrame:(_,value)=>({t:value.time_s,canonical:value.variables}),
    confirmArchiveCache:(...args)=>hooks.confirmArchiveCache(...args),persist:()=>{persists++;},render:()=>{renders++;},refresh:()=>{refreshes++;},
    message:(text,error)=>messages.push({text,error}),delay:ms=>hooks.delay(ms)});
  return {api,hooks,owner,node,run,frame,state,calls,messages,pending,
    counts:()=>({persists,renders,refreshes,prepared}),replace:()=>{owner.run={id:'new',runId:'new',live:true,status:'running',history:[],events:[]};return owner.run;}};
}
