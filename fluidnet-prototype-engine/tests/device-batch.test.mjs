import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const host=vm.createContext({window:{}});
for(const file of ['project-model.js','device-batch.js'])vm.runInContext(readFileSync(new URL('../frontend/'+file,import.meta.url),'utf8'),host);
const batch=host.window.DeviceBatchEditor;
const plain=v=>JSON.parse(JSON.stringify(v));
const spec={id:'opening_ratio',label:'开度',value_type:'number',unit:{display_scale:.01,display_offset:0},minimum:0,maximum:1,writable:true,runtime:true};
const definition={id:'valve',version:1,parameters:[spec]};
const engine={catalog:{modules:[definition],prototype_parameter_bindings:{valve:{opening:'opening_ratio'}}}};
const moduleOf=()=>({id:'valve',kind:'valve'});
const nodes=[{id:'V1',params:{opening:80},draft:{opening:90}},{id:'V2',params:{opening:70},draft:{opening:75}}];
test('legacy UI alias maps to canonical contract, and only explicit proposed fields participate',()=>{
  const owner={run:{live:false}};const before=JSON.stringify(nodes);
  assert.equal(batch.fields(nodes[0],moduleOf,engine)[0].key,'opening');
  batch.checkEntries(owner,nodes.map(node=>({node,proposed:{opening:40}})),moduleOf,engine);
  assert.equal(JSON.stringify(nodes),before);
  assert.throws(()=>batch.checkEntries(owner,[],moduleOf,engine),/至少选择/);
});
test('values obey types and canonical bounds including temperature offsets',()=>{
  assert.equal(batch.parseValue('40',spec),40);
  assert.throws(()=>batch.parseValue('101',spec),/范围/);
  assert.throws(()=>batch.parseValue('',spec),/有限/);
  assert.equal(batch.parseValue('25',{...spec,unit:{display_scale:1,display_offset:-273.15},minimum:273.15,maximum:350}),25);
  assert.equal(batch.parseValue('false',{value_type:'boolean'}),false);
  assert.deepEqual(plain(batch.parseValue('[[0,1],[2,3]]',{value_type:'curve'})),[[0,1],[2,3]]);
  assert.throws(()=>batch.parseValue('[["0",1]]',{value_type:'curve'}),/数值/);
});
test('active ownership comes from frozen run and rejects the entire group',()=>{
  const owner={run:{live:true,parameterKey:JSON.stringify({controllers:[{id:'pid',instance_id:'V2',parameter_id:'opening_ratio'}]})},controllers:[]};
  assert.throws(()=>batch.checkEntries(owner,nodes.map(node=>({node,proposed:{opening:40}})),moduleOf,engine),/V2.*PID/);
  owner.run.live=false;batch.checkEntries(owner,nodes.map(node=>({node,proposed:{opening:40}})),moduleOf,engine);
  assert.equal(nodes[0].params.opening,80);assert.equal(nodes[1].draft.opening,75);
});
test('mismatched versions and readonly or offline-only fields are rejected',()=>{
  const owner={run:{live:true}},entries=nodes.map(node=>({node,proposed:{opening:40}}));
  assert.throws(()=>batch.checkEntries(owner,entries,n=>({manifest:{...definition,version:n.id==='V1'?1:2}}),engine),/不可写|版本/);
  const different=n=>({manifest:{...definition,version:n.id==='V1'?1:2}});
  assert.throws(()=>batch.checkEntries(owner,nodes.map(node=>({node,proposed:{opening_ratio:.4}})),different,engine),/版本/);
  const staticModule=()=>({manifest:{...definition,parameters:[{...spec,runtime:false}]}});
  assert.throws(()=>batch.checkEntries(owner,[{node:nodes[0],proposed:{opening_ratio:.4}}],staticModule,engine),/运行中/);
  assert.throws(()=>batch.checkEntries({run:{}},[{node:nodes[0],proposed:{unknown:1}}],moduleOf,engine),/不可写/);
});
test('draft and definition changes invalidate an already prepared preview fingerprint',()=>{
  const owner={run:{live:true,id:'run1',parameterKey:'frozen'}};
  const before=batch.snapshot(owner,nodes,moduleOf,engine),copy=plain(nodes);copy[0].draft.opening=45;
  assert.notEqual(batch.snapshot(owner,copy,moduleOf,engine),before);
  const altered=plain(engine);altered.catalog.modules[0].version=2;
  assert.notEqual(batch.snapshot(owner,nodes,moduleOf,altered),before);
});
