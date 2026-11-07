import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const plain=value=>JSON.parse(JSON.stringify(value));
function fixture({rejection,delay=false}={}) {
  let release,notifyPosted;
  const posted=new Promise(resolve=>{notifyPosted=resolve;});
  const gate=delay?new Promise(resolve=>{release=resolve;}):Promise.resolve();
  const node={id:'V1',params:{opening:80},draft:{opening:55},variableState:{values:{},draft:{}}};
  const owner={id:'project',pages:[{nodes:[node]}],run:{id:'old',runId:'old',live:true,status:'paused',history:[],events:[],time:0}};
  const state={projects:[owner],charts:{range:'window'}},requests=[],effects=[];
  const variables=[{id:'param:opening',param:'opening',origin:'parameter',writable:true}];
  const module={frozen:true,variables,manifest:{parameters:[{id:'opening',value_type:'number',runtime:true,writable:true,
    unit:{display_scale:.01,display_offset:0}}]}};
  const key=()=>JSON.stringify(node.params);owner.run.parameterKey=key();
  const host=vm.createContext({window:{createProjectServices:()=>({})},crypto,sessionStorage:{getItem:()=>null},
    fetch:async(path,options)=>{
      requests.push({path,body:options.body&&JSON.parse(options.body)});
      if(path.endsWith('/command')){notifyPosted();await gate;return {ok:true,json:async()=>rejection
        ?{command_status:'rejected',message:rejection}:{command_status:'accepted',command_id:'write1'}};}
      if(path.endsWith('/events'))return {ok:true,json:async()=>({events:[{command_id:'write1',command_status:'applied'}]})};
      if(path.includes('/history'))return {ok:true,json:async()=>({rows:[],total_rows:0})};
      if(path==='/api/v1/runs/old')return {ok:true,json:async()=>({id:'old',status:'paused',events:[]})};
      throw Error(path);
    },
    state,moduleOf:()=>module,ownerOfInstance:()=>owner,instanceWritable:v=>v.writable,
    clone:plain,sameValue:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
    ensureInstanceVariables:()=>node.variableState,validateInstanceEdits:()=>{},
    markDirty:()=>effects.push('dirty'),remember:()=>effects.push('remember'),render:()=>effects.push('render'),
  });
  for(const name of ['project-model','project-state','project-run-state','performance-library','module-service','run-commands','engine-client','device-application'])
    loadFrontend(new URL('../frontend/'+name+'.js',import.meta.url),host);
  host.projectState=host.window.FluidNetProjectState;host.projectRunState=host.window.FluidNetProjectRunState;
  host.engine=host.window.createEngineClient({state:()=>state,moduleOf:()=>module,parameterKey:key,
    persist:()=>{},render:()=>{},refresh:()=>{},message:()=>{}});
  const application=host.window.FluidNetDeviceApplication.create({
    state:()=>state,projectState:host.projectState,projectRunState:host.projectRunState,
    engine:host.engine,performance:host.window.FluidNetPerformanceData,clone:plain,sameValue:host.sameValue,
    ownerOfInstance:host.ownerOfInstance,moduleOf:host.moduleOf,instanceWritable:host.instanceWritable,
    ensureInstanceVariables:host.ensureInstanceVariables,validateInstanceEdits:host.validateInstanceEdits,
    markDirty:host.markDirty,remember:host.remember,render:host.render,
  });
  return {owner,node,state,module,application,requests,effects,posted,release:()=>release?.(),
    proposal:(bank=0)=>application.capture(node,{'param:opening':bank<0?node.draft.opening:40},bank),
    apply:proposal=>application.apply(owner,node,proposal)};
}

test('library values use one acknowledged write and preserve input typed during the request',async()=>{
  const f=fixture({delay:true}),proposal=f.proposal(),pending=f.apply(proposal);
  await f.posted;
  assert.equal(f.node.params.opening,80);assert.equal(f.node.draft.opening,55);
  f.node.draft.opening=60;f.release();await pending;
  const command=f.requests.find(r=>r.path.endsWith('/command')).body;
  assert.deepEqual(command.values,{'V1.param.opening':.4});
  assert.equal(f.node.params.opening,40);assert.equal(f.node.draft.opening,60);
  assert.equal(f.requests.filter(r=>r.path.endsWith('/command')).length,1);
});

const provenance=(version,opening)=>({curve:{parameterValues:{opening},provenance:{id:'curve',version,parameter_id:'curve'}}});
test('performance provenance follows accepted values while a newer source remains a draft',async()=>{
  const f=fixture({delay:true});f.node.performanceData=provenance(1,.8);f.node.performanceDataDraft=provenance(2,.55);
  const pending=f.apply(f.proposal(-1));await f.posted;
  f.node.draft.opening=60;f.node.performanceDataDraft=provenance(3,.6);f.release();await pending;
  assert.equal(f.node.performanceData.curve.provenance.version,2);
  assert.equal(f.node.performanceDataDraft.curve.provenance.version,3);
  assert.equal(f.node.params.opening,55);assert.equal(f.node.draft.opening,60);
});
test('rejected performance application leaves applied and draft provenance intact',async()=>{
  const f=fixture({rejection:'控制器拒绝'});f.node.performanceData=provenance(1,.8);f.node.performanceDataDraft=provenance(2,.55);
  const before=plain(f.node);await assert.rejects(f.apply(f.proposal(-1)),/拒绝/);assert.deepEqual(plain(f.node),before);
});
test('source-only confirmation commits metadata without a fake parameter write',async()=>{
  const f=fixture();f.node.draft.opening=80;f.node.performanceData=provenance(1,.8);f.node.performanceDataDraft=provenance(2,.8);
  await f.apply(f.proposal(-1));assert.equal(f.node.performanceData.curve.provenance.version,2);assert.equal(f.node.performanceDataDraft,undefined);
  assert.equal(f.requests.length,0);assert.equal(f.node.params.opening,80);
});

test('a rejected controlled library write leaves applied values and drafts intact',async()=>{
  for(const rejection of ['由 PID flow 控制','由控制脚本 original 拥有']) {
    const f=fixture({rejection}),before=plain(f.node);
    await assert.rejects(f.apply(f.proposal()),new RegExp(rejection));
    assert.deepEqual(plain(f.node),before);
  }
});

test('a late library write acknowledgement cannot update a replacement project or run',async()=>{
  for(const replace of ['project','run']) {
    const f=fixture({delay:true}),before=plain(f.node),pending=f.apply(f.proposal());
    await f.posted;
    if(replace==='project')f.state.projects=[{...f.owner}];
    else f.owner.run={id:'new',runId:'new',live:true};
    f.release();await assert.rejects(pending,error=>error.name==='AbortError');
    assert.deepEqual(plain(f.node),before);
  }
});

test('a preview belonging to a replaced run sends no parameter write',async()=>{
  const f=fixture(),proposal=f.proposal();
  f.owner.run={id:'new',runId:'new',live:true};
  await assert.rejects(f.apply(proposal),error=>error.name==='AbortError');
  assert.equal(f.requests.length,0);assert.equal(f.node.params.opening,80);
});

test('a second application cannot race an outstanding acknowledgement for the same device',async()=>{
  const f=fixture({delay:true}),pending=f.apply(f.proposal());
  await f.posted;
  await assert.rejects(f.apply(f.proposal()),/正在应用/);
  f.release();await pending;
  assert.equal(f.requests.filter(r=>r.path.endsWith('/command')).length,1);
  assert.equal(f.node.params.opening,40);
});

test('an obsolete device or changed applied values cannot consume a preview',async()=>{
  for(const change of ['node','parameters','source']) {
    const f=fixture();f.node.performanceData=provenance(1,.8);
    const proposal=f.proposal(-1);
    if(change==='node')f.owner.pages[0].nodes=[{...f.node}];
    else if(change==='parameters')f.node.params.opening=70;
    else f.node.performanceData=provenance(2,.8);
    await assert.rejects(f.apply(proposal),/替换|参数已变化|性能资料已变化/);
    assert.equal(f.requests.length,0);assert.equal(f.application.isPending(f.node),false);
  }
});

test('custom values and model identity commit without consuming a later draft',async()=>{
  const f=fixture({delay:true});
  f.module.variables.push({id:'custom:offset',origin:'custom',writable:true});
  Object.assign(f.node.variableState,{values:{'custom:offset':1},draft:{'custom:offset':2}});
  Object.assign(f.node,{modelId:'previous',modelVersion:1,draftModelId:'candidate',draftModelVersion:2});
  const proposal=f.application.capture(f.node,{'param:opening':55,'custom:offset':2},-1);
  const pending=f.apply(proposal);await f.posted;
  assert.equal(f.application.isPending(f.node),true);
  f.node.variableState.draft['custom:offset']=3;
  f.node.draftModelId='later';f.node.draftModelVersion=4;
  f.release();await pending;
  assert.equal(f.node.variableState.values['custom:offset'],2);assert.equal(f.node.variableState.draft['custom:offset'],3);
  assert.equal(f.node.modelId,'candidate');assert.equal(f.node.modelVersion,2);
  assert.equal(f.node.draftModelId,'later');assert.equal(f.node.draftModelVersion,4);
  assert.equal(f.application.isPending(f.node),false);
});

test('offline application records undo before one local commit and sends no HTTP request',async()=>{
  const f=fixture();f.owner.run.live=false;f.owner.run.status='ready';
  await f.apply(f.proposal());
  assert.deepEqual(f.effects,['remember','dirty','render']);assert.equal(f.requests.length,0);
  assert.equal(f.node.params.opening,40);assert.equal(f.node.draft.opening,40);
  assert.equal(f.application.isPending(f.node),false);
});

test('a rejected acknowledgement releases its device lock for a later valid preview',async()=>{
  const f=fixture({rejection:'owned by controller'});
  await assert.rejects(f.apply(f.proposal()),/owned/);assert.equal(f.application.isPending(f.node),false);
  f.owner.run.live=false;f.owner.run.status='ready';
  await f.apply(f.proposal());assert.equal(f.node.params.opening,40);
});

test('a curve-only offline draft survives preview and commits a deep copy',async()=>{
  const f=fixture();f.owner.run.live=false;f.node.draft.opening=80;
  const curve=[[0,6],[6,4],[12,0]];f.node.draft.head_curve=curve;
  const proposal=f.proposal(-1);curve[0][1]=99;
  await f.apply(proposal);
  assert.deepEqual(plain(f.node.params.head_curve),[[0,6],[6,4],[12,0]]);
  assert.equal(f.node.draft.head_curve[0][1],6);assert.equal(curve[0][1],99);assert.equal(f.requests.length,0);
});
