import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createModuleReplayUI} from '../frontend/module-replay.js';
const snapshot=()=>({format_version:1,module:{id:'valve',name:'测试阀',version:2,source:{runtime:'raise ValueError("<script>")'}},
  execution:{phase:'evaluate',time_s:.5,accepted_time_s:.4,instance_id:'Valve-own'},parameters:{opening:.4},state:{count:4},ports:{in0:{pressure_pa:120000}},channels:{},content_hash:'abc',definition_hash:'def'});
function setup(request,route=()=>null){
  const routes=[],files=[],messages=[];let renders=0;
  const ui=createModuleReplayUI({request,render:()=>{renders++;},navigate:r=>routes.push(r),download:(...a)=>files.push(a),message:text=>messages.push(text),route});
  return {ui,routes,files,messages,renders:()=>renders};
}
test('inspection and replay use frozen copies, escaped source and canonical inputs',async()=>{
  let posted;
  const {ui,routes,files}=setup(async(path,body)=>{posted={path,body};return {status:'failed',matched_failure:true,diagnostics:[{source_line:1,message:'same error'}]};});
  const input=snapshot();ui.load(input);input.module.source.runtime='changed';input.parameters.opening=1;
  assert.deepEqual(routes,['bench']);assert.match(ui.body(),/&lt;script&gt;/);assert.doesNotMatch(ui.body(),/<script>/);
  await ui.run();assert.equal(posted.path,'/modules/replay');assert.equal(posted.body.replay.parameters.opening,.4);
  assert.equal(posted.body.replay.ports.in0.pressure_pa,120000);assert.match(ui.body(),/已复现同一/);
  ui.exportInput();assert.equal(JSON.parse(files[0][1]).parameters.opening,.4);assert.equal(input.parameters.opening,1);
});
test('late response cannot overwrite a newly inspected failure',async()=>{
  let resolve;
  const {ui}=setup(()=>new Promise(r=>resolve=r));ui.load(snapshot());const pending=ui.run();
  const replacement=snapshot();replacement.execution.instance_id='Different';ui.load(replacement);
  resolve({status:'failed',matched_failure:true,diagnostics:[{message:'old response'}]});await pending;
  assert.match(ui.body(),/Different/);assert.doesNotMatch(ui.body(),/old response/);
  ui.close();assert.equal(ui.active,false);assert.equal(ui.body(),'');
});
test('missing captured input is rejected and completed replay is not called a repaired network',async()=>{
  const {ui}=setup(async()=>({status:'completed',diagnostics:[],result:{state:{}}}));
  assert.throws(()=>ui.load(null),/无法精确复现/);ui.load(snapshot());await ui.run();assert.match(ui.body(),/不代表原网络已修复/);
});
test('late archive response cannot navigate back after leaving the records page',async()=>{
  let resolve,route='runs';
  const {ui,routes}=setup(()=>new Promise(r=>resolve=r),()=>route);
  const pending=ui.archive('old-run');route='workbench';resolve({replay:snapshot()});await pending;
  assert.deepEqual(routes,[]);assert.equal(ui.active,false);
});
test('archive failure cannot leave a finished older replay permanently busy',async()=>{
  let resolve;
  const {ui}=setup(path=>path==='/modules/replay'?new Promise(r=>resolve=r):Promise.reject(Error('not found')));
  ui.load(snapshot());const pending=ui.run();await ui.archive('missing');
  resolve({status:'failed',matched_failure:true});await pending;
  assert.doesNotMatch(ui.body(),/正在复现/);assert.doesNotMatch(ui.body(),/data-action="run-module-replay" disabled/);
  assert.match(ui.body(),/已复现同一/);
});

test('late archive failures are silent after navigation, including leaving and returning',async()=>{
  for(const back of [false,true]){
    let reject,route='runs';
    const {ui,routes,messages}=setup(()=>new Promise((_,no)=>reject=no),()=>route);
    const pending=ui.archive('old');route='workbench';ui.navigationChanged();
    if(back){route='runs';ui.navigationChanged();}
    reject(Error('old failure'));await pending;
    assert.deepEqual(routes,[]);assert.deepEqual(messages,[]);assert.equal(ui.active,false);
  }
});

test('newer archives and explicit snapshot selection supersede older archive responses',async()=>{
  const releases=new Map(),{ui,routes}=setup(path=>new Promise(resolve=>releases.set(path,resolve)));
  const old=ui.archive('old'),latest=ui.archive('latest');
  const newer=snapshot();newer.execution.instance_id='Latest';
  releases.get('/runs/latest/module-failure')({replay:newer});await latest;
  releases.get('/runs/old/module-failure')({replay:snapshot()});await old;
  assert.match(ui.body(),/Latest/);assert.deepEqual(routes,['bench']);
  const pending=ui.archive('pending');ui.close();releases.get('/runs/pending/module-failure')({replay:snapshot()});await pending;
  assert.equal(ui.active,false);assert.deepEqual(routes,['bench']);
});

test('a completed replay releases its lock without repainting another page',async()=>{
  let release,route='bench',calls=0;
  const f=setup(()=>{calls++;return new Promise(resolve=>release=resolve);},()=>route);
  f.ui.load(snapshot());const pending=f.ui.run();await f.ui.run();assert.equal(calls,1);
  const renders=f.renders();route='workbench';f.ui.navigationChanged();
  release({status:'completed',diagnostics:[]});await pending;
  assert.equal(f.renders(),renders);assert.doesNotMatch(f.ui.body(),/正在复现/);
  assert.match(f.ui.body(),/本次回调完成/);
});

test('missing accepted time stays unknown and the simplified source panel stays accessible',()=>{
  const {ui}=setup(async()=>({})),input=snapshot();delete input.execution.accepted_time_s;
  ui.load(input,[{source_line:1,message:'error'}]);
  assert.match(ui.body(),/最近接受 时刻未记录/);assert.doesNotMatch(ui.body(),/未记录 s/);
  assert.match(ui.body(),/data-replay-error-line/);assert.match(ui.body(),/<details class="panel" open><summary class="panel-head">冻结 module.py/);
  assert.doesNotMatch(ui.body(),/locate-replay-source/);
});
