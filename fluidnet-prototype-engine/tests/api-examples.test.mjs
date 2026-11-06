import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const host=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/api-examples.js',import.meta.url),'utf8'),host);
const api=host.window.FluidNetApiExamples;
const record={request:{project:{instances:[{id:'Balance-X',module_id:'valve',name:'支路平衡阀'}],modules:[{
  id:'valve',variables:[{id:'mass_flow_kg_s',label:'质量流量',unit:{canonical_unit:'kg/s'}}],parameters:[
    {id:'opening',label:'开度',runtime:true,writable:true,unit:{canonical_unit:'1'}},
    {id:'diameter',label:'管径',runtime:false,writable:true}]}]}}};
const values={'Balance-X.mass_flow_kg_s':3,'Balance-X.param.opening':.4,'Balance-X.param.diameter':.05};
test('examples use published keys and canonical values from any instance ID',()=>{
  const items=api.directory(record,values);
  assert.equal(items.length,3);
  assert.equal(items[0].unit,'kg/s');
  assert.equal(items[1].value,.4);
  assert.equal(items[1].writable,true);
  assert.equal(items[2].writable,false);
  const call=api.request('run-a','set',items[1],.65);
  assert.equal(JSON.stringify(call.body.values),'{"Balance-X.param.opening":0.65}');
  assert.match(api.request('run-a','read',items[0]).path,/keys=Balance-X.mass_flow_kg_s/);
  assert.equal(api.directory(record,{}).length,0);
});
test('frozen control owners cannot be offered as direct parameter writes',()=>{
  const frozen=structuredClone(record);
  frozen.request.project.controllers=[{instance_id:'Balance-X',parameter_id:'opening'}];
  assert.equal(api.directory(frozen,values)[1].writable,false);
  frozen.request.project.controllers=[];
  frozen.request.project.control_scripts=[{enabled:true,outputs:['Balance-X.param.opening']}];
  assert.equal(api.directory(frozen,values)[1].writable,false);
});
test('empty projects cannot fabricate V1 and request targets are encoded',()=>{
  assert.equal(api.directory({request:{project:{instances:[],modules:[]}}},{}).length,0);
  assert.throws(()=>api.request('r','read'),/尚无/);
  assert.throws(()=>api.request('r','set',{key:'read-only',writable:false},2),/不可直接写入/);
  assert.match(api.request('r/a','stream',{key:'HX.hot:in.temperature_k'}).path,/r%2Fa\/stream\?keys=HX.hot%3Ain.temperature_k/);
  assert.equal(api.request('r','status').path,'/api/v1/runs/r');
});
