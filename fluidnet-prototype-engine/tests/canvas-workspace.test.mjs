import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const plain=v=>JSON.parse(JSON.stringify(v));
function fixture(){
  const host=vm.createContext({window:{}});
  for(const name of ['canvas-symbols','canvas-routing','canvas-observations','canvas-view','canvas-workspace'])loadFrontend(new URL('../frontend/'+name+'.js',import.meta.url),host);
  const modules={source:{id:'source',kind:'source',name:'压力源',ports:[{id:'out0',label:'出口',domain:'fluid',direction:'out'}],variables:[]}};
  const nodes=[{id:'B1',moduleId:'source',name:'入口',x:0,y:0,params:{}},{id:'B2',moduleId:'source',name:'出口',x:200,y:0,params:{}}],page={id:'main',nodes,edges:[['edge','B1','out0','B2','out0']]};
  const run={source:'engine',status:'running',parameterKey:'key',history:[{t:1,canonical:{'B1.out0.mass_flow_kg_s':-2,'B2.out0.mass_flow_kg_s':2},diagnostics:[]}]},owner={id:'p',pages:[page],run},ui={canvasModeValue:'flow'},state={projects:[owner]};
  const esc=v=>String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const view=host.window.FluidNetCanvasWorkspace.create({getState:()=>state,project:()=>owner,activePage:()=>page,moduleOf:n=>modules[n.moduleId],ui,esc,btn:()=>'',links:{atPort:()=>true,locate:()=>null},domains:{fluid:{label:'流体',color:'orange'}},quick:()=>'',channels:()=>'',projectKey:()=>owner.key||'key',selectedIds:()=>[],engine:()=>({circuits:()=>[]}),openDialog:()=>{},closeDialog:()=>{},render:()=>{},saveUI:()=>{},locate:()=>{}});
  return {view,owner,page,run,ui,state,modules};
}
test('real accepted frames drive colors and animation without altering topology',()=>{
  const f=fixture(),before=plain(f.owner),html=f.view.markup(f.page);
  assert.match(html,/data-edge-known="true"/);assert.match(html,/data-edge-direction="1"/);assert.match(html,/canvas-flow-animation/);
  assert.deepEqual(plain(f.owner),before);assert.ok(f.view.context(f.owner).row);
});
test('stale, missing and non-engine records do not borrow displayed values or arrows',()=>{
  for(const change of [f=>{f.owner.key='changed';},f=>{f.run.source='prototype';},f=>{f.run.history=[];}]){
    const f=fixture();change(f);const html=f.view.markup(f.page);
    assert.match(html,/data-edge-known="false"/);assert.doesNotMatch(html,/data-flow-arrow|class="canvas-flow-animation"/);
  }
});
test('trend frames keep the timestamp of the last complete frame and suspend motion',()=>{
  const f=fixture();f.run.history.push({t:2,partial:true,canonical:{'B1.out0.mass_flow_kg_s':99}});
  const c=f.view.context(f.owner);assert.equal(c.time,1);assert.equal(c.partial,true);assert.equal(c.animate,false);
  assert.match(f.view.markup(f.page),/2 kg\/s/);assert.doesNotMatch(f.view.markup(f.page),/99 kg\/s|class="canvas-flow-animation"/);
  f.run.history.shift();assert.equal(f.view.context(f.owner).row,null);
});

test('live full responses drive canvas values independently of trend history',()=>{
  const f=fixture();f.run.history.push({t:3,partial:true,canonical:{}});
  f.run.latestFull={t:2,sequence:2,canonical:{'B1.out0.mass_flow_kg_s':-7,'B2.out0.mass_flow_kg_s':7}};
  let c=f.view.context(f.owner);assert.equal(c.time,2);assert.equal(c.partial,true);assert.equal(c.animate,false);
  assert.match(f.view.markup(f.page),/7 kg\/s/);
  f.run.latestFull={t:3,sequence:3,canonical:{'B1.out0.mass_flow_kg_s':-8,'B2.out0.mass_flow_kg_s':8}};
  c=f.view.context(f.owner);assert.equal(c.time,3);assert.equal(c.partial,false);assert.equal(c.animate,true);
  assert.match(f.view.markup(f.page),/8 kg\/s/);
  f.run.status='paused';assert.equal(f.view.context(f.owner).animate,false);
  assert.match(f.view.markup(f.page),/8 kg\/s/);
  f.run.history=[];assert.equal(f.view.context(f.owner).time,3);
  f.owner.key='changed';assert.equal(f.view.context(f.owner).row,null);
});
test('paused frames retain static direction but never claim continuing physical motion',()=>{
  const f=fixture();f.run.status='paused';const html=f.view.markup(f.page);
  assert.match(html,/data-flow-arrow/);assert.doesNotMatch(html,/class="canvas-flow-animation"/);
});
test('current diagnostics are deduplicated and stale diagnostics are excluded',()=>{
  const f=fixture(),d={code:'FAIL',severity:'error',instance_id:'B1',message:'Bad <script>'};
  f.run.history[0].diagnostics=[d];f.run.diagnostics=[d];assert.equal(f.view.diagnostics().length,1);
  assert.match(f.view.markup(f.page),/data-canvas-state="error"/);
  f.owner.key='different';assert.deepEqual(plain(f.view.diagnostics()),[]);assert.doesNotMatch(f.view.markup(f.page),/data-canvas-state="error"/);
});
test('a failure without accepted frames exposes its diagnosis without fabricating flow',()=>{
  const f=fixture();f.run.history=[];f.run.status='failed';f.run.diagnosticTime=0;
  f.run.diagnostics=[{instance_id:'B1',severity:'error',code:'PHYSICS_FAILED',message:'range'}];
  const html=f.view.markup(f.page);assert.match(html,/data-canvas-state="error"/);assert.match(html,/data-edge-known="false"/);assert.doesNotMatch(html,/data-flow-arrow|class="canvas-flow-animation"/);
  assert.equal(f.view.diagnostics().length,1);f.owner.key='changed';assert.equal(f.view.diagnostics().length,0);
});
test('project thumbnails use that project geometry and never another active run',()=>{
  const f=fixture();const html=f.view.markup(f.page,true);assert.doesNotMatch(html,/canvas-flow-animation|data-flow-arrow|data-edge-known="true"/);
  assert.match(html,/data-canvas-family="source"/);
});
test('short pipe bodies and spread header ports retain their authored outward side',()=>{
  const f=fixture();f.modules.pipe={id:'pipe',kind:'pipe',name:'管段',ports:[{id:'in0',direction:'in',domain:'fluid',x:20,y:50},{id:'out0',direction:'out',domain:'fluid',x:80,y:50}]};
  const n={id:'P',moduleId:'pipe',x:100,y:0,rotation:0};f.page.nodes.push(n);
  assert.deepEqual(plain(f.view.endpoint(f.page,'P','out0').normal),{x:1,y:0});
  n.rotation=90;const normal=f.view.endpoint(f.page,'P','out0').normal;assert.ok(Math.abs(normal.x)<1e-12);assert.equal(normal.y,1);
});
