import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const clone=value=>JSON.parse(JSON.stringify(value));
function context(state,quota=Infinity){
  const stored=new Map(),messages=[],status={localError:'',trimmed:false};
  const ctx=vm.createContext({window:{}});
  for(const file of ['workspace-storage.js','project-model.js'])loadFrontend(new URL('../frontend/'+file,import.meta.url),ctx);
  const api=ctx.window.FluidNetWorkspaceStorage.create({read:()=>state,key:'fluidnet-prototype-engine-v1',
    storage:{setItem:(key,value)=>{if(value.length>quota){const error=Error('quota');error.name='QuotaExceededError';throw error;}stored.set(key,value);}},
    status:()=>status,changed:patch=>Object.assign(status,patch),message:(...args)=>messages.push(args)});
  return {ctx:{persistLocal:api.persist,compactArchivedDraft:ctx.window.FluidNetWorkspaceStorage.compactArchivedDraft,
    projectParameterKey:owner=>ctx.window.FluidNetProjectModel.parameterKey(owner,state.modules,()=> '')},stored,messages};
}
function largeState(){
  const history=Array.from({length:81},(_,i)=>({t:i*30,partial:false,canonical:{temperature:300-i/20,payload:'x'.repeat(4000)}}));
  return {modules:[],projects:[{id:'room',controllers:[{id:'custom',setpoint:299.15}],pages:[],
    controlScripts:[{id:'load',source:'author code'}],moduleSnapshots:{room:{version:7}},
    run:{id:'server-run',source:'engine',time:2400,history,parameterKey:'frozen-key',
      archiveCache:{id:'server-run',rows:81,time_s:2400,persisted_at:'2026-10-30T10:00:00Z'}}}],
    records:[{id:'RECORD-user',source:'engine',history:[{t:0,value:7},{t:10,value:9}],params:{setting:3}}],
    charts:{extra:[{id:'user-curve',key:'custom.temperature'}]}};
}

test('quota pressure compacts only confirmed server caches and preserves drafts and local snapshots',()=>{
  const state=largeState(),original=clone(state),{ctx,stored,messages}=context(state,60000);
  assert.equal(ctx.persistLocal(),true);
  const saved=JSON.parse(stored.get('fluidnet-prototype-engine-v1'));
  assert.equal(saved.projects[0].run.history.length,8);
  assert.deepEqual(saved.projects[0].run.history.at(-1),original.projects[0].run.history.at(-1));
  assert.deepEqual(saved.records,original.records);
  assert.deepEqual(saved.projects[0].controllers,original.projects[0].controllers);
  assert.deepEqual(saved.projects[0].controlScripts,original.projects[0].controlScripts);
  assert.deepEqual(saved.projects[0].moduleSnapshots,original.projects[0].moduleSnapshots);
  assert.deepEqual(saved.charts,original.charts);
  assert.deepEqual(state,original);
  assert.match(messages.at(-1)[0],/服务端档案/);
});

test('incomplete or mismatched archive receipts do not authorize cache trimming',()=>{
  for(const change of [{persisted_at:null},{persisted_at:true},{id:'another-run'},
    {rows:undefined},{rows:'81'},{rows:80},{time_s:2399}]){
    const state=largeState(),run=state.projects[0].run;
    Object.assign(run.archiveCache,change);
    const {ctx}=context(state);
    assert.equal(ctx.compactArchivedDraft(state,1),false);
    assert.equal(run.history.length,81);
  }
});

test('cache compaction retains the last complete frame before partial trend frames',()=>{
  const state=largeState(),history=state.projects[0].run.history;
  history.slice(1).forEach(row=>{row.partial=true;row.canonical={temperature:299.15};});
  const first=clone(history[0]),{ctx}=context(state);
  assert.equal(ctx.compactArchivedDraft(state,1),true);
  assert.equal(state.projects[0].run.history.length,2);
  assert.deepEqual(state.projects[0].run.history[0],first);
  assert.equal(state.projects[0].run.history[1].t,2400);
});

test('PID settings participate in stale-result detection without run-cache noise',()=>{
  const state=largeState(),{ctx}=context(state),owner=state.projects[0];
  const original=ctx.projectParameterKey(owner);
  owner.run.history=[];
  assert.equal(ctx.projectParameterKey(owner),original);
  owner.controllers[0].setpoint=298.15;
  assert.notEqual(ctx.projectParameterKey(owner),original);
  owner.controllers[0].setpoint=299.15;
  assert.equal(ctx.projectParameterKey(owner),original);
  owner.controllers[0].kp=-.1;
  assert.notEqual(ctx.projectParameterKey(owner),original);
});

test('canvas layout and library drafts cannot invalidate a frozen project result',()=>{
  const state=largeState(),{ctx}=context(state),owner=state.projects[0];
  const module={id:'device',kind:'device',version:1,manifest:{definition_hash:'frozen'},ports:[{id:'in0',domain:'fluid',direction:'in',x:20,y:50}],channels:[]};
  state.modules=[clone(module)];owner.pages=[{nodes:[{id:'D1',moduleId:'device',params:{a:1},x:10,y:20}],edges:[]}];owner.moduleSnapshots={device:clone(module)};
  const original=ctx.projectParameterKey(owner);
  owner.pages[0].nodes[0].x=200;owner.moduleSnapshots.device.ports[0].x=30;state.modules[0].version=2;state.modules[0].ports[0].domain='info';
  assert.equal(ctx.projectParameterKey(owner),original);
  owner.pages[0].nodes[0].params.a=2;assert.notEqual(ctx.projectParameterKey(owner),original);
  owner.pages[0].nodes[0].params.a=1;owner.moduleSnapshots.device.manifest.definition_hash='new';assert.notEqual(ctx.projectParameterKey(owner),original);
});
