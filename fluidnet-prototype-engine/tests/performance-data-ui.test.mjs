import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context=vm.createContext({window:{}});
for(const path of ['project-model.js','project-state.js','equipment-selection.js','performance-library.js'])vm.runInContext(readFileSync(new URL('../frontend/'+path,import.meta.url),'utf8'),context);
const api=context.window.FluidNetPerformanceData,selection=context.window.EquipmentSelection;
const plain=value=>JSON.parse(JSON.stringify(value));
const definition={id:'pump',version:1,definition_hash:'frozen',content_hash:'runtime',parameters:[
  {id:'head_curve',value_type:'curve',default:[[0,40],[20,0]]},
  {id:'design_temperature_k',value_type:'number',default:293.15,unit:{display_scale:1,display_offset:-273.15}},
  {id:'data_source',value_type:'text',default:''},
]};
const proposal=(version=1)=>({parameters:{head_curve:[[0,40+version],[20,0]],design_temperature_k:303.15,data_source:'教学数据'},
  provenance:{id:'user-pump',version,parameter_id:'head_curve',content_hash:'curve'+version,source:'教学数据'}});
function fixture(){const node={id:'P1',params:{head_curve:[[0,40],[20,0]],design_temperature_k:20,data_source:''},variableState:{banks:[{a:1},{a:2},{a:3}]}},owner={id:'project',pages:[{nodes:[node]}]};node.draft=plain(node.params);return {node,owner};}

test('legacy device and model records without performance metadata remain valid',()=>{
  const node={params:{opening:50},draft:{opening:60}},legacy={kind:'valve'};
  assert.deepEqual(plain(api.references(node,legacy,node.params)),{});
  api.commit(node,legacy,api.capture(node));assert.deepEqual(plain(node.performanceData),{});
});

test('performance proposal stages canonical values and metadata without applying or changing banks',()=>{
  const {node,owner}=fixture(),before=plain(node);
  api.stage(owner,node,definition,proposal());
  assert.deepEqual(plain(node.params),before.params);assert.deepEqual(plain(node.variableState),before.variableState);
  assert.equal(node.draft.design_temperature_k,30);assert.deepEqual(plain(node.draft.head_curve),[[0,41],[20,0]]);
  assert.equal(api.references(node,definition,node.draft).head_curve.provenance.version,1);
  assert.deepEqual(plain(api.references(node,definition,node.params,'current')),{});
});
test('source references require unchanged curves and the frozen runtime',()=>{
  const {node,owner}=fixture();api.stage(owner,node,definition,proposal());
  assert.deepEqual(plain(api.references(node,{...definition,content_hash:'changed'},node.draft)),{});
  node.draft.head_curve[0][1]=99;assert.deepEqual(plain(api.references(node,definition,node.draft)),{});
  assert.equal(node.performanceDataDraft.head_curve.parameterValues.head_curve[0][1],41);
});
test('new draft keeps provenance of previously applied values through serialization',()=>{
  const {node,owner}=fixture();api.stage(owner,node,definition,proposal(1));const receipt=api.capture(node);node.params=plain(node.draft);api.commit(node,definition,receipt);
  api.stage(owner,node,definition,proposal(2));const restored=plain(node);
  assert.equal(api.references(restored,definition,restored.params,'current').head_curve.provenance.version,1);
  assert.equal(api.references(restored,definition,restored.draft).head_curve.provenance.version,2);
  const model={moduleId:'pump',moduleVersion:1,performanceData:api.references(restored,definition,restored.draft)};
  selection.assertModelCompatible(model,definition);
  assert.throws(()=>selection.assertModelCompatible(model,{...definition,version:2}),/版本/);
});
test('identical curve points with a new source remain pending until explicitly applied',()=>{
  const {node,owner}=fixture();api.stage(owner,node,definition,proposal(1));let receipt=api.capture(node);node.params=plain(node.draft);api.commit(node,definition,receipt);
  const other=proposal(2);other.parameters=context.window.FluidNetProjectModel.canonicalParameters(definition,node.params);other.provenance.source='另一份同点资料';api.stage(owner,node,definition,other);
  assert.equal(api.pending(node),true);assert.deepEqual(plain(node.params),plain(node.draft));
  assert.equal(api.references(node,definition,node.params,'current').head_curve.provenance.version,1);
  assert.equal(api.references(node,definition,node.draft).head_curve.provenance.version,2);
  receipt=api.capture(node);api.commit(node,definition,receipt);
  assert.equal(api.pending(node),false);assert.equal(node.performanceData.head_curve.provenance.version,2);
});
test('an accepted receipt preserves a newer performance draft typed while waiting',()=>{
  const {node,owner}=fixture();api.stage(owner,node,definition,proposal(1));const receipt=api.capture(node),accepted=plain(node.draft);
  api.stage(owner,node,definition,proposal(2));node.params=accepted;api.commit(node,definition,receipt);
  assert.equal(node.performanceData.head_curve.provenance.version,1);
  assert.equal(node.performanceDataDraft.head_curve.provenance.version,2);assert.equal(api.pending(node),true);
});
test('invalid target or unsupported parameter cannot partially stage a proposal',()=>{
  const {node,owner}=fixture(),before=plain(node);
  assert.throws(()=>api.stage(owner,node,definition,{...proposal(),parameters:{head_curve:[[0,2],[2,0]],unknown:5}}),/不可写/);
  assert.deepEqual(plain(node),before);
  owner.pages[0].nodes=[];assert.throws(()=>api.stage(owner,node,definition,proposal()),/删除或替换/);
});
test('changing provenance invalidates an outstanding proposal even when values match',()=>{
  const {node,owner}=fixture(),state={activeProject:owner.id,projects:[owner]},before=selection.fingerprint(owner,node,definition);
  node.performanceData={head_curve:{}};
  assert.throws(()=>selection.assertCurrent(state,owner,node,definition,before),/变化/);
});
