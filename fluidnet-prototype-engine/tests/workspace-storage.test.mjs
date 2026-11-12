import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const host=vm.createContext({window:{}});
for(const file of ['workspace-storage','project-model','project-state','draft-store'])loadFrontend(new URL('../frontend/'+file+'.js',import.meta.url),host);
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

test('backup re-encodes a large legacy stored draft without losing either saved or pending values',()=>{
 const codec=host.window.FluidNetDraftStore,plain=value=>JSON.parse(JSON.stringify(value));
 const saved={projects:[{name:'旧项目',draft:{opening:35},history:Array.from({length:60},()=>({value:'重复设备数据'.repeat(30)}))}]};
 const pending=structuredClone(saved);pending.projects[0].draft.opening=45;
 const raw=JSON.stringify(saved),packed=codec.pack(saved),backup=codec.pack(pending);
 const limit=Math.max(raw.length,packed.length+backup.length)+20;
 assert.ok(raw.length+backup.length>limit);
 const values=new Map([['draft',raw]]),storage={getItem:key=>values.get(key)||null,setItem:(key,text)=>{
   const size=[...values].filter(([id])=>id!==key).reduce((sum,[,value])=>sum+value.length,0)+text.length;
   if(size>limit)throw Object.assign(Error('quota'),{name:'QuotaExceededError'});
   values.set(key,text);
 }};
 const store=api.create({read:()=>pending,key:'draft',storage,draftStore:codec});
 assert.equal(store.backup('before-workspace'),true);
 assert.ok(values.get('draft').length<raw.length);
 assert.deepEqual(plain(codec.parse(values.get('draft'))),saved);
 assert.deepEqual(plain(codec.parse(values.get('before-workspace'))),pending);
 assert.equal(pending.projects[0].draft.opening,45);
});
