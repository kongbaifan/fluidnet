import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../frontend/module-replay.js',import.meta.url),'utf8');
const snapshot=()=>({format_version:1,module:{id:'valve',name:'测试阀',version:2,source:{runtime:'raise ValueError("<script>")'}},
  execution:{phase:'evaluate',time_s:.5,accepted_time_s:.4,instance_id:'Valve-own'},parameters:{opening:.4},state:{count:4},ports:{in0:{pressure_pa:120000}},channels:{},content_hash:'abc',definition_hash:'def'});
function setup(request,route=()=>null){
  const host=vm.createContext({window:{}});vm.runInContext(source,host);
  const routes=[],files=[];
  const ui=host.window.createModuleReplayUI({request,render:()=>{},navigate:r=>routes.push(r),download:(...a)=>files.push(a),message:()=>{},route});
  return {ui,routes,files};
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
});
