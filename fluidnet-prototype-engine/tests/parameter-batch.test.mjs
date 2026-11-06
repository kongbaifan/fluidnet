import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const plain=x=>JSON.parse(JSON.stringify(x));
function fixture({live=true,reject=false,delay=false}={}){
  let release,posted;const sent=new Promise(r=>posted=r),gate=delay?new Promise(r=>release=r):Promise.resolve();
  const nodes=['ValveA','ValveB'].map(id=>({id,moduleId:'valve',params:{opening:80,temperature:20},draft:{opening:55,temperature:25},modelId:'old',variableState:{values:{},draft:{},banks:[{},{},{}]}}));
  const owner={id:'p',pages:[{nodes}],run:{id:'run1',runId:live?'run1':null,live,status:live?'paused':'ready',events:[],history:[],time:0}};
  const state={projects:[owner],models:[],charts:{range:'window'}};
  const definition={id:'valve',version:1,parameters:[{id:'opening',label:'开度',value_type:'number',runtime:true,minimum:0,maximum:1,unit:{display_scale:.01,display_offset:0}},
    {id:'temperature',label:'温度',value_type:'number',runtime:true,minimum:273.15,unit:{display_scale:1,display_offset:-273.15}}]};
  const module={manifest:definition,variables:[]};
  const key=()=>JSON.stringify({controllers:[],controls:[],params:nodes.map(n=>n.params)});owner.run.parameterKey=key();
  const requests=[];
  const host=vm.createContext({window:{createProjectServices:()=>({})},crypto,sessionStorage:{getItem:()=>null},
    fetch:async(path,options)=>{
      requests.push({path,body:options.body&&JSON.parse(options.body)});
      if(path.endsWith('/command')){posted();await gate;return {ok:true,json:async()=>reject?{command_status:'rejected',message:'由控制器接管'}:{command_status:'accepted',command_id:'batch1'}};}
      if(path.endsWith('/events'))return {ok:true,json:async()=>({events:[{command_id:'batch1',command_status:'applied',parameter_revision:1,time_s:0}]})};
      if(path.includes('/history'))return {ok:true,json:async()=>({rows:[],total_rows:0})};
      if(path==='/api/v1/runs/run1')return {ok:true,json:async()=>({id:'run1',status:'paused',events:[]})};
      throw Error(path);
    }});
  for(const name of ['project-model','project-state','project-run-state','parameter-batch','engine-client'])vm.runInContext(readFileSync(new URL('../frontend/'+name+'.js',import.meta.url),'utf8'),host);
  const engine=host.window.createEngineClient({state:()=>state,moduleOf:()=>module,parameterKey:key,persist:()=>{},render:()=>{},refresh:()=>{},message:()=>{},dirty:()=>{}});
  const apply=()=>engine.applyParameterBatch(owner,nodes.map(node=>({node,proposed:{opening:40}})));
  return {nodes,owner,state,definition,requests,engine,apply,sent,release:()=>release?.()};
}
test('multiple devices use one acknowledged write; later typing and unrelated drafts survive',async()=>{
  const f=fixture({delay:true});f.nodes[0].draftModelId='pending-model';f.nodes[0].draftModelVersion=3;
  const variableState=plain(f.nodes.map(n=>n.variableState)),pending=f.apply();await f.sent;
  assert.equal(f.nodes[0].params.opening,80);assert.equal(f.nodes[1].params.opening,80);
  f.nodes[0].draft.opening=63;f.release();await pending;
  const writes=f.requests.filter(r=>r.path.endsWith('/command'));assert.equal(writes.length,1);
  assert.deepEqual(writes[0].body.values,{'ValveA.param.opening':.4,'ValveB.param.opening':.4});
  assert.equal(f.nodes[0].draft.opening,63);assert.equal(f.nodes[1].draft.opening,40);
  for(const n of f.nodes){assert.equal(n.params.opening,40);assert.equal(n.draft.temperature,25);assert.equal(n.modelId,null);}
  assert.equal(f.nodes[0].draftModelId,'pending-model');assert.deepEqual(plain(f.nodes.map(n=>n.variableState)),variableState);
});
test('invalid second device leaves every local object unchanged and sends nothing',async()=>{
  const f=fixture({live:false}),before=plain(f.nodes);
  await assert.rejects(f.engine.applyParameterBatch(f.owner,[{node:f.nodes[0],proposed:{opening:40}},{node:f.nodes[1],proposed:{opening:101}}]),/超出范围/);
  assert.deepEqual(plain(f.nodes),before);assert.equal(f.requests.length,0);
});
test('server rejection preserves all drafts, models and applied parameters',async()=>{
  const f=fixture({reject:true}),before=plain(f.nodes);await assert.rejects(f.apply(),/接管/);assert.deepEqual(plain(f.nodes),before);
});
test('late receipt cannot partly apply when a target, project or run is replaced',async()=>{
  for(const replace of ['node','project','run']){
    const f=fixture({delay:true}),before=plain(f.nodes),pending=f.apply();await f.sent;
    if(replace==='node')f.owner.pages[0].nodes=[f.nodes[0],{...f.nodes[1]}];
    if(replace==='project')f.state.projects=[{...f.owner}];
    if(replace==='run')f.owner.run={id:'new',live:true};
    f.release();await assert.rejects(pending);assert.deepEqual(plain(f.nodes),before);
  }
});
test('batch and individual parameter writes cannot race for the same device',async()=>{
  const f=fixture({delay:true}),pending=f.apply();await f.sent;
  await assert.rejects(f.apply(),/正在应用/);await assert.rejects(f.engine.applyParameters(f.owner,f.nodes[0],{opening:70}),/正在应用/);
  f.release();await pending;assert.equal(f.requests.filter(r=>r.path.endsWith('/command')).length,1);
});
test('frozen control ownership blocks the complete batch and cannot be changed through a draft script',async()=>{
  const f=fixture();f.owner.run.parameterKey=JSON.stringify({controllers:[{id:'pid',instance_id:'ValveB',parameter_id:'opening'}],controls:[]});
  f.owner.controllers=[];const before=plain(f.nodes);await assert.rejects(f.apply(),/PID/);
  assert.equal(f.requests.length,0);assert.deepEqual(plain(f.nodes),before);
});
test('stopped batch supports canonical offsets and model provenance without a server command',async()=>{
  const f=fixture({live:false});f.state.models=[{id:'new-model',moduleId:'valve',moduleVersion:1,version:2,params:{opening:50,temperature:30}}];
  await f.engine.applyParameterBatch(f.owner,f.nodes.map(node=>({node,proposed:{opening:50,temperature:30},model:{id:'new-model',version:2}})));
  assert.equal(f.requests.length,0);for(const n of f.nodes){assert.equal(n.params.temperature,30);assert.equal(n.modelId,'new-model');assert.equal(n.modelVersion,2);}
});
test('readonly, nonruntime and stale model version changes are rejected before any write',async()=>{
  for(const kind of ['readonly','nonruntime','model']){
    const f=fixture();if(kind==='readonly')f.definition.parameters[0].writable=false;if(kind==='nonruntime')f.definition.parameters[0].runtime=false;
    if(kind==='model'){f.state.models=[{id:'m',moduleId:'valve',moduleVersion:2,version:1,params:{opening:40}}];
      await assert.rejects(f.engine.applyParameterBatch(f.owner,[{node:f.nodes[0],proposed:{opening:40},model:{id:'m',version:1}}]),/版本/);
    }else await assert.rejects(f.apply(),/只读|运行中/);
    assert.equal(f.requests.length,0);assert.equal(f.nodes[0].params.opening,80);
  }
});

test('canonical and display aliases cannot silently write the same parameter twice',()=>{
  const host=vm.createContext({window:{}});
  for(const name of ['project-model','project-state','parameter-batch'])vm.runInContext(readFileSync(new URL('../frontend/'+name+'.js',import.meta.url),'utf8'),host);
  const node={id:'V1',params:{opening:80},draft:{opening:80}},owner={id:'p',pages:[{nodes:[node]}],run:{live:false}},state={projects:[owner],models:[]};
  const describe=()=>({definition:{parameters:[{id:'opening_ratio',label:'开度',unit:{display_scale:.01}}]},bindings:{opening:'opening_ratio'}});
  for(const proposed of [{opening:40,opening_ratio:50},{opening_ratio:50}])assert.throws(()=>host.window.FluidNetParameterBatch.prepare(state,owner,[{node,proposed}],describe),/别名/);
  assert.equal(node.params.opening,80);
});
