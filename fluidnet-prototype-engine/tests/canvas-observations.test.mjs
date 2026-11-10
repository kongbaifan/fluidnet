import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const context=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/canvas-observations.js',import.meta.url),context);
const api=context.window.FluidNetCanvasObservations,plain=value=>JSON.parse(JSON.stringify(value));
const device={ports:[{id:'in0',domain:'fluid',direction:'in'},{id:'out0',domain:'fluid',direction:'out'}],
  channels:[{id:'main',input_port:'in0',output_port:'out0'}],variables:[{id:'is_running',source:'derived'}]};
const inputs={edge:['e','A','out0','B','in0'],sourceNode:{id:'A'},targetNode:{id:'B'},sourceModule:device,targetModule:device};
const sample=(canonical,other={})=>({canonical,t:12,...other});

test('arrows follow actual signed port mass flow, irrespective of declared direction or connection order',()=>{
  let out=api.edge({...inputs,mode:'flow',row:sample({'A.out0.mass_flow_kg_s':-2,'B.in0.mass_flow_kg_s':2})});
  assert.equal(out.direction,1);assert.equal(out.value,2);assert.equal(out.flowKnown,true);
  out=api.edge({...inputs,mode:'flow',row:sample({'A.out0.mass_flow_kg_s':2,'B.in0.mass_flow_kg_s':-2})});
  assert.equal(out.direction,-1);assert.equal(out.value,-2);assert.equal(out.width,3.08);
  out=api.edge({...inputs,edge:['e','B','in0','A','out0'],sourceNode:{id:'B'},targetNode:{id:'A'},mode:'flow',row:sample({'A.out0.mass_flow_kg_s':-2,'B.in0.mass_flow_kg_s':2})});
  assert.equal(out.direction,-1);assert.equal(out.value,-2);
});
test('zero flow stays zero, missing, nonfinite and setting-only values stay unknown',()=>{
  const zero=api.edge({...inputs,mode:'flow',row:sample({'A.out0.mass_flow_kg_s':-0})});
  assert.equal(zero.direction,0);assert.equal(zero.value,0);
  for(const canonical of [{},{'A.out0.mass_flow_kg_s':'2'},{'A.out0.mass_flow_kg_s':Infinity},{'A.param.running':1}]){
    const out=api.edge({...inputs,mode:'flow',row:sample(canonical)});
    assert.equal(out.known,false);assert.equal(out.direction,null);assert.equal(out.color,null);
  }
});
test('signed channel fallback is tied to the actual channel endpoints',()=>{
  const out=api.edge({...inputs,mode:'flow',row:sample({'A.main.mass_flow_kg_s':3})});
  assert.equal(out.value,3);assert.equal(out.sourceKey,'A.main.mass_flow_kg_s');
  assert.equal(api.edge({...inputs,mode:'flow',row:sample({'A.mass_flow_kg_s':4})}).value,4);
  const multi={...device,ports:[...device.ports,{id:'in1',domain:'fluid'},{id:'out1',domain:'fluid'}],
    channels:[...device.channels,{id:'other',input_port:'in1',output_port:'out1'}]};
  assert.equal(api.edge({...inputs,sourceModule:multi,mode:'flow',row:sample({'A.mass_flow_kg_s':7})}).known,false);
  assert.equal(api.edge({...inputs,sourceModule:multi,mode:'flow',row:sample({'A.other.mass_flow_kg_s':7})}).known,false);
  assert.equal(api.edge({...inputs,sourceModule:multi,mode:'flow',row:sample({'A.main.mass_flow_kg_s':2})}).value,2);
});
test('multiport refrigeration and thermal devices do not invent per-port flows from aggregate output',()=>{
  for(const domain of ['refrigerant','thermal','info']){
    const sourceModule={ports:[{id:'out0',domain,direction:'out'}],channels:[]};
    const targetModule={ports:[{id:'in0',domain,direction:'in'}],channels:[]};
    const out=api.edge({...inputs,sourceModule,targetModule,mode:'flow',row:sample({'A.mass_flow_kg_s':9,'A.heat_flow_w':2000})});
    assert.equal(out.known,false);assert.equal(out.direction,null);
  }
});
test('mismatched endpoint fluxes suppress the arrow and explain the inconsistency',()=>{
  const out=api.edge({...inputs,mode:'flow',row:sample({'A.out0.mass_flow_kg_s':-2,'B.in0.mass_flow_kg_s':3})});
  assert.equal(out.known,false);assert.equal(out.direction,null);assert.match(out.reason,/不一致/);
});
test('temperature and absolute pressure use canonical units and the actual upstream endpoint',()=>{
  const row=sample({'A.out0.mass_flow_kg_s':2,'B.in0.mass_flow_kg_s':-2,
    'A.out0.temperature_k':293.15,'B.in0.temperature_k':303.15,'A.out0.pressure_pa':150000,'B.in0.pressure_pa':250000});
  const t=api.edge({...inputs,mode:'temperature',row}),p=api.edge({...inputs,mode:'pressure',row});
  assert.equal(t.value,30);assert.equal(t.observationKey,'B.in0.temperature_k');assert.equal(t.direction,-1);
  assert.equal(p.value,250);assert.equal(p.unit,'kPa(abs)');assert.match(p.label,/目标端/);
});
test('known scalar values do not fabricate missing flow, and state sampling is labelled',()=>{
  const out=api.edge({...inputs,mode:'temperature',row:sample({'A.out0.temperature_k':283.15},{partial:true})});
  assert.equal(out.value,10);assert.equal(out.flowKnown,false);assert.equal(out.direction,null);assert.equal(out.partial,true);
  assert.match(out.label,/源端/);assert.equal(out.time,12);
});
test('stale, invalid or unaccepted rows cannot animate or color physical values',()=>{
  for(const flags of [{stale:true},{valid:false},{accepted:false}]){
    const row=sample({'A.out0.mass_flow_kg_s':-2,'A.out0.temperature_k':300},flags);
    const out=api.edge({...inputs,mode:'temperature',row});assert.equal(out.known,false);assert.equal(out.direction,null);
  }
});
test('color clipping is explicit and never changes values; custom ranges remain detached',()=>{
  const out=api.edge({...inputs,mode:'pressure',row:sample({'A.out0.pressure_pa':2000000})});
  assert.equal(out.value,2000);assert.equal(out.outOfRange,true);assert.equal(out.color,'rgb(186, 61, 61)');
  assert.equal(api.edge({...inputs,mode:'circuit',row:sample({'A.out0.mass_flow_kg_s':-2})}).color,null);
  const scale={min:0,max:5000};assert.equal(api.edge({...inputs,mode:'pressure',scale,row:sample({'A.out0.pressure_pa':2000000})}).outOfRange,false);
  const first=api.legend('flow');first.colors[0]='bad';assert.equal(api.legend('flow').colors[0],'#2b7bba');
  assert.deepEqual(plain(api.legend('pressure',{min:10,max:0})),plain(api.legend('pressure')));
});
test('node state uses declared sampled outputs and never the requested setting',()=>{
  const n={id:'A',params:{running:1},draft:{running:0}};
  assert.equal(api.node({node:n,module:device,row:sample({'A.param.running':1})}).state,'unknown');
  assert.equal(api.node({node:n,module:device,row:sample({'A.is_running':1})}).state,'running');
  assert.equal(api.node({node:n,module:device,row:sample({'A.is_running':false})}).state,'stopped');
  assert.equal(api.node({node:n,module:{...device,variables:[]},row:sample({'A.is_running':1})}).state,'unknown');
  assert.equal(api.node({node:n,module:{...device,variables:[{id:'is_running',source:'parameter'}]},row:sample({'A.is_running':1})}).state,'unknown');
});
test('only known cooler mode semantics produce defrost/drip states',()=>{
  const m={solver_model:'defrost_air_cooler',variables:[{id:'state.mode',source:'state'}]};
  assert.equal(api.node({node:{id:'C'},module:m,row:sample({'C.state.mode':1})}).state,'defrost');
  assert.equal(api.node({node:{id:'C'},module:m,row:sample({'C.state.mode':2})}).state,'drip');
  assert.equal(api.node({node:{id:'C'},module:m,row:sample({'C.state.mode':0})}).state,'unknown');
  assert.equal(api.node({node:{id:'C'},module:{...m,solver_model:'unrelated'},row:sample({'C.state.mode':1})}).state,'unknown');
  const graph={solver_model:'frost_hotgas_cooler',variables:[{id:'defrost_mode',source:'output'}]};
  for(const mode of [1,2])assert.equal(api.node({node:{id:'C'},module:graph,row:sample({'C.defrost_mode':mode})}).state,'defrost');
  assert.equal(api.node({node:{id:'C'},module:graph,row:sample({'C.defrost_mode':3})}).state,'drip');
  assert.equal(api.node({node:{id:'C'},module:graph,row:sample({'C.defrost_mode':4})}).label,'再冷却');
  assert.equal(api.node({node:{id:'C'},module:graph,row:sample({'C.defrost_mode':0})}).state,'unknown');
});
test('node diagnostics prioritize associated errors and preserve child paths without mutating input',()=>{
  const row=sample({'A.is_running':1},{diagnostics:[{instance_id:'B',severity:'error',message:'other'},
    {instance_id:'A',severity:'warning',message:'<script>example</script>',source_path:'A.Child'},
    {instance_id:null,severity:'error',message:'network'}]});
  const before=plain(row),out=api.node({node:{id:'A'},module:device,row});
  assert.equal(out.state,'warning');assert.equal(out.diagnostics.length,1);assert.equal(out.diagnostics[0].source_path,'A.Child');
  assert.equal(out.diagnostics[0].message,'<script>example</script>');assert.equal(typeof out.label,'string');
  out.diagnostics[0].message='changed';assert.deepEqual(plain(row),before);
  row.diagnostics.push({instance_id:'A',severity:'error',message:'failed'});
  assert.equal(api.node({node:{id:'A'},module:device,row}).state,'error');
  assert.equal(api.node({node:{id:'A'},module:device,row:{...row,stale:true}}).state,'unknown');
  assert.equal(api.node({node:{id:'A'},module:device,row:{...row,valid:false}}).state,'error');
});
test('invalid endpoint identities and mismatched domain cannot receive a physical overlay',()=>{
  const row=sample({'A.out0.mass_flow_kg_s':-2});
  assert.equal(api.edge({...inputs,sourceNode:{id:'changed'},mode:'flow',row}).known,false);
  assert.equal(api.edge({...inputs,targetModule:{ports:[{id:'in0',domain:'thermal'}]},mode:'flow',row}).known,false);
});
