import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const host=vm.createContext({window:{}});
for(const file of ['workspace-storage','project-model','project-state'])loadFrontend(new URL('../frontend/'+file+'.js',import.meta.url),host);
const api=host.window.FluidNetWorkspaceStorage;
function fixture(){
 let state={dirty:true,projects:[{dirty:true}],modules:[],draft:{valve:55}},version=0,requestCount=0,deliver,reject,notify;
 const posted=new Promise(resolve=>{notify=resolve;});
 const pending=new Promise((resolve,no)=>{deliver=resolve;reject=no;}),status={phase:'',localError:'',trimmed:false},messages=[],saved=new Map();
 const store=api.create({read:()=>state,write:v=>{state=v;},definitions:{},validate:()=>{},normalize:()=>{},projectState:host.window.FluidNetProjectState,model:host.window.FluidNetProjectModel,
  storage:{setItem:(key,text)=>saved.set(key,text)},key:'draft',ready:async()=>{},save:async payload=>{requestCount++;notify();return pending;},revision:()=>version,status:()=>status,
  changed:p=>Object.assign(status,p),message:t=>messages.push(t),resetView:()=>{},render:()=>{},updateWindows:()=>{},pending:()=>0});
 return {posted,store,status,messages,saved,get:()=>state,replace:()=>{state={dirty:false,projects:[],modules:[]};},edit:()=>{version++;state.draft.valve=66;},count:()=>requestCount,deliver:()=>deliver({revision:3,saved_at:'now'}),reject:()=>reject(Error('disk full'))};
}
test('duplicate saves share one lock and later edits remain dirty after acknowledgement',async()=>{
 const f=fixture(),work=f.store.saveAll();await f.posted;await f.store.saveAll();assert.equal(f.count(),1);f.edit();f.deliver();await work;
 assert.equal(f.get().workspaceRevision,3);assert.equal(f.get().dirty,true);assert.equal(f.get().draft.valve,66);assert.equal(f.status.phase,'saved');assert.equal(f.store.isSaving(),false);
});
test('a successful unchanged save clears dirty only on the original workspace',async()=>{
 const f=fixture(),work=f.store.saveAll();await f.posted;f.deliver();await work;assert.equal(f.get().dirty,false);assert.equal(f.get().projects[0].dirty,false);
});
test('late receipt or rejection cannot mutate a replacement workspace or claim it is saved',async()=>{
 for(const fail of [false,true]){const f=fixture(),work=f.store.saveAll();await f.posted;f.replace();const before=JSON.stringify(f.get());fail?f.reject():f.deliver();await work;
  assert.equal(JSON.stringify(f.get()),before);assert.equal(f.messages.length,0);assert.equal(f.status.phase,'');}
});
test('server save rejection leaves local draft intact and reports retryable error',async()=>{
 const f=fixture(),work=f.store.saveAll();await f.posted;f.reject();await work;assert.equal(f.status.phase,'error');assert.match(f.messages.at(-1),/disk full/);assert.equal(JSON.parse(f.saved.get('draft')).draft.valve,55);
});
test('full quota failure never replaces the old stored value or truncates in-memory state',()=>{
 const original={projects:[{run:{history:[{t:0,value:1}]}}],records:[],draft:{value:'x'.repeat(200)}},before=JSON.stringify(original),status={},messages=[];
 const store=api.create({read:()=>original,key:'draft',storage:{setItem:()=>{throw Object.assign(Error('quota'),{name:'QuotaExceededError'});}},status:()=>status,changed:p=>Object.assign(status,p),message:t=>messages.push(t)});
 assert.equal(store.persist(),false);assert.equal(JSON.stringify(original),before);assert.match(messages[0],/内存数据/);assert.throws(()=>store.backup('old'),/备份失败/);
});
