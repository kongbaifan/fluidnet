import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const context=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/project-run-state.js',import.meta.url),context);
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

test('live readouts advance on full responses even when trend history is already ahead',()=>{
  const initial=row(0,0),run={history:[initial],time:0,status:'running',live:true};
  for(let t=1;t<=3;t++){
    const latest={...row(t,t*10),sequence:t},trend={...row(t+1,t+1,true),sequence:t+1};
    runs.mergeLive(run,{status:'running',events:[],frame:{}},[trend],{totalRows:t+1,latest,limit:2});
    assert.equal(runs.completeRow(run),latest);
    assert.equal(run.time,t+1);
    assert.equal(run.history.at(-1),trend);
    assert.equal(run.history.at(-1).partial,true);
    assert.equal(run.offset,t+1);
  }
  assert.equal(run.history.length,2);
  assert.ok(run.history.every(r=>r.partial));
  const restored=JSON.parse(JSON.stringify(run));
  assert.equal(runs.completeRow(restored).canonical.flow,30);
});

test('same-time full frames keep the newest sequence and parameter revision',()=>{
  const run={history:[],status:'running'},latest={...row(5,50),sequence:10,parameterRevision:2};
  const merge=value=>runs.mergeLive(run,{status:'paused',events:[],frame:{}},[],{totalRows:0,latest:value});
  merge(latest);
  assert.equal(run.time,5);assert.equal(run.values.q,50);assert.equal(run.history.length,0);
  for(const rejected of [{...row(5,40),sequence:9,parameterRevision:3},
    {...row(5,30),sequence:10,parameterRevision:1},{...row(6,60,true),sequence:11},
    {...row(6,60),sequence:11,valid:false}]){
    merge(rejected);assert.equal(runs.completeRow(run),latest);assert.equal(run.values.q,50);
  }
  const applied={...row(5,55),sequence:10,parameterRevision:3};merge(applied);
  assert.equal(runs.completeRow(run),applied);assert.equal(run.values.q,55);
});

test('newer complete history wins and failed frames preserve the last accepted readout',()=>{
  const initial=row(0,0),current={...row(3,30),sequence:3};
  const run={history:[initial],time:0,status:'running',live:true,runId:'run'};
  runs.mergeLive(run,{status:'running',events:[],frame:{}},[current,row(4,40,true)],
    {totalRows:3,latest:{...row(2,20),sequence:2},limit:1});
  assert.equal(runs.completeRow(run),current);assert.equal(run.history.length,1);
  runs.mergeLive(run,{status:'failed',events:[],frame:{time_s:5,valid:false,diagnostics:[{message:'failed'}]}},[],
    {totalRows:3,latest:null});
  assert.equal(run.live,false);assert.equal(runs.completeRow(run),current);
  assert.equal(run.diagnosticTime,5);assert.equal(run.diagnostics[0].message,'failed');
  assert.equal(runs.completeRow({history:[initial,row(1,1,true)]}),initial);
  assert.equal(runs.completeRow({history:[]}),undefined);
});
test('live result windows, final status and diagnostics come from one run record',()=>{
  const run={history:[],events:[],live:true,runId:'run',status:'running'};
  const data={status:'failed',events:[{time_s:3,type:'failed'}],frame:{time_s:3,diagnostics:[{message:'range'}]}};
  const result=runs.mergeLive(run,data,[row(0,0),row(1,1),row(2,2)],{totalRows:3,latest:row(2,2),limit:2});
  assert.equal(run.history.length,2);assert.equal(run.offset,3);assert.equal(run.status,'failed');
  assert.equal(run.runId,null);assert.equal(result.terminal,true);assert.equal(run.events.at(-1).text,'range');
  assert.equal(run.diagnostics[0].message,'range');assert.equal(run.diagnosticTime,3);
  data.frame.diagnostics[0].message='mutated';assert.equal(run.diagnostics[0].message,'range');
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
  for(const file of ['project-model.js','project-run-state.js','module-service.js','run-commands.js','engine-client.js'])
    loadFrontend(new URL('../frontend/'+file,import.meta.url),host);
  const client=host.window.createEngineClient({state:()=>state,parameterKey:p=>p.key,emptyRun:()=>({history:[],events:[]}),render:()=>{}});
  const pending=client.command('project','run','p');await submitted;
  const replacement={id:'new',status:'running',history:[row(7,42)],events:[]};owner.run=replacement;
  deliver();await pending;
  assert.equal(owner.run,replacement);assert.equal(owner.run.status,'running');assert.equal(owner.run.history[0].q,42);
});

test('queued controller edits cannot move to a replacement run after the first request fails',async()=>{
  let deliver,posted;
  const submitted=new Promise(resolve=>{posted=resolve;});
  const owner={id:'p',controllers:[{id:'pid',setpoint:1}],run:{id:'old',runId:'old',live:true}};
  const state={projects:[owner]},requests=[];
  const host=vm.createContext({window:{createProjectServices:()=>({})},crypto,sessionStorage:{getItem:()=>null},
    fetch:async path=>{
      requests.push(path);
      if(path==='/api/v1/runs/old/command'){
        posted();return new Promise(resolve=>{deliver=()=>resolve({ok:true,status:202,
          json:async()=>({command_id:'old-command',command_status:'accepted'})});});
      }
      throw Error('An old queued command reached '+path);
    }});
  for(const file of ['project-model.js','project-run-state.js','module-service.js','run-commands.js','engine-client.js'])
    loadFrontend(new URL('../frontend/'+file,import.meta.url),host);
  const client=host.window.createEngineClient({state:()=>state,parameterKey:p=>JSON.stringify(p.controllers)});
  const results=Promise.allSettled([client.applyController(owner,'pid','setpoint',2),client.applyController(owner,'pid','setpoint',3)]);
  await submitted;owner.run={id:'new',runId:'new',live:true};deliver();
  const settled=await results;
  assert.equal(requests.length,1);
  assert.ok(settled.every(result=>result.status==='rejected' && result.reason.name==='AbortError'));
  assert.equal(owner.controllers[0].setpoint,1);
});
