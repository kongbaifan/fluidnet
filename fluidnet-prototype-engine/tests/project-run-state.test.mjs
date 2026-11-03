import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const context=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/project-run-state.js',import.meta.url),'utf8'),context);
const runs=context.window.FluidNetProjectRunState;
const row=(t,value,partial=false)=>({t,q:value,a:null,b:null,pressure:null,temperature:null,partial,canonical:{flow:value}});

test('responses remain bound to their project object and run even when IDs are reused',()=>{
  const owner={id:'p',run:{id:'same'}},state={projects:[owner]};
  const token=runs.capture(state,owner);
  state.activeProject='other';assert.equal(runs.isCurrent(state,token),true);
  owner.run={id:'same'};assert.equal(runs.isCurrent(state,token),false);
  owner.run=token.run;state.projects=[{...owner}];assert.equal(runs.isCurrent(state,token),false);
  assert.throws(()=>runs.assertCurrent(state,token),error=>error.name==='AbortError');
});
test('polling cannot make results from an older configuration look current',()=>{
  const run={history:[]};
  runs.prepare(run,{overviewBindings:{},chartBindings:[],parameterKey:'old'});
  runs.prepare(run,{overviewBindings:{},chartBindings:[],parameterKey:'edited'});
  assert.equal(run.parameterKey,'old');
  runs.advanceParameterKey(run,'edited','edited','applied');assert.equal(run.parameterKey,'old');
  runs.advanceParameterKey(run,'old','another-edit','applied');assert.equal(run.parameterKey,'old');
  runs.advanceParameterKey(run,'old','old','applied');assert.equal(run.parameterKey,'applied');
});
test('late or partial frames cannot erase a newer complete frame',()=>{
  const run={history:[]};runs.append(run,row(5,10));
  runs.append(run,row(4,9));runs.append(run,row(5,8,true));
  assert.equal(run.history.length,1);assert.equal(run.values.q,10);
  runs.append(run,row(5,11));assert.equal(run.history.length,1);assert.equal(run.values.q,11);
});
test('live result windows, final status and diagnostics come from one run record',()=>{
  const run={history:[],events:[],live:true,runId:'run',status:'running'};
  const data={status:'failed',events:[{time_s:3,type:'failed'}],frame:{time_s:3,diagnostics:[{message:'range'}]}};
  const result=runs.mergeLive(run,data,[row(0,0),row(1,1),row(2,2)],{totalRows:3,latest:row(2,2),limit:2});
  assert.equal(run.history.length,2);assert.equal(run.offset,3);assert.equal(run.status,'failed');
  assert.equal(run.runId,null);assert.equal(result.terminal,true);assert.equal(run.events.at(-1).text,'range');
});
test('an archive listing started before a new run cannot stop the new run',()=>{
  const owner={id:'p',run:{live:true,runId:'old',events:[]}},state={projects:[owner]};
  const observed=[runs.capture(state,owner)];
  owner.run={live:true,runId:'new',events:[]};
  runs.reconcileArchives(state,[],observed);assert.equal(owner.run.live,true);
});
test('a delayed real adapter response does not overwrite a replacement run',async()=>{
  let deliver,posted;
  const submitted=new Promise(resolve=>{posted=resolve;});
  const owner={id:'p',pages:[],moduleSnapshots:{},solver:{mode:'steady',duration:1,dt:1},key:'v1',run:{history:[],events:[]}};
  const state={activeProject:'p',projects:[owner],modules:[],charts:{extra:[]}};
  const host=vm.createContext({window:{createProjectServices:()=>({prepare:()=>{},runMetadata:()=>({})})},
    AbortController,performance,sessionStorage:{getItem:()=>null},
    fetch:async path=>{
      if(path.endsWith('/prototype/normalize'))return {ok:true,status:200,json:async()=>({modules:[]})};
      if(path.endsWith('/runs')){posted();return new Promise(resolve=>{deliver=()=>resolve({ok:true,status:201,json:async()=>({run_id:'old',status:'completed'})});});}
      throw Error(path);
    }});
  for(const file of ['project-model.js','project-run-state.js','engine-client.js'])
    vm.runInContext(readFileSync(new URL('../frontend/'+file,import.meta.url),'utf8'),host);
  const client=host.window.createEngineClient({state:()=>state,parameterKey:p=>p.key,emptyRun:()=>({history:[],events:[]}),render:()=>{}});
  const pending=client.command('project','run','p');await submitted;
  const replacement={id:'new',status:'running',history:[row(7,42)],events:[]};owner.run=replacement;
  deliver();await pending;
  assert.equal(owner.run,replacement);assert.equal(owner.run.status,'running');assert.equal(owner.run.history[0].q,42);
});
