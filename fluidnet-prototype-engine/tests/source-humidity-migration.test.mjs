import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const host=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/workspace-normalization.js',import.meta.url),'utf8'),host);
function migrate(data) {
 const options={parameterDefinitions:{source:[['humidity_ratio_kg_kg','含湿量','1',0,.2,.001,0]]},clone:structuredClone,
  variablesFor:()=>[{id:'param:humidity_ratio_kg_kg',origin:'parameter',value:0,unit:'1'}]};
 host.window.FluidNetWorkspaceNormalization.create(options).backfillBuiltinParams(data);
}
test('source fields added to old workspaces use the canonical zero default',()=>{
 const data={modules:[{id:'source',kind:'source',variables:[],values:{},banks:[{}, {}, {}]}],
  projects:[{pages:[{nodes:[{moduleId:'source',params:{},draft:{}}]}]}]};
 migrate(data);assert.equal(data.modules[0].values['param:humidity_ratio_kg_kg'],0);
 assert.equal(data.projects[0].pages[0].nodes[0].params.humidity_ratio_kg_kg,0);
});
test('repair the exact invalid g/kg default without changing valid canonical values',()=>{
 const m={id:'source',kind:'source',variables:[{id:'param:humidity_ratio_kg_kg',origin:'parameter',unit:'g/kg_da',value:8}],
  values:{'param:humidity_ratio_kg_kg':8},banks:[{'param:humidity_ratio_kg_kg':8},{'param:humidity_ratio_kg_kg':.012}]};
 const data={modules:[m],projects:[{pages:[{nodes:[{moduleId:'source',params:{humidity_ratio_kg_kg:.008},draft:{humidity_ratio_kg_kg:8}}]}]}]};
 migrate(data);assert.equal(m.values['param:humidity_ratio_kg_kg'],.008);assert.equal(m.banks[1]['param:humidity_ratio_kg_kg'],.012);
 assert.equal(data.projects[0].pages[0].nodes[0].params.humidity_ratio_kg_kg,.008);
 assert.equal(data.projects[0].pages[0].nodes[0].draft.humidity_ratio_kg_kg,.008);
 migrate(data);assert.equal(m.values['param:humidity_ratio_kg_kg'],.008);
});
test('unrelated invalid values and frozen contracts remain available for normal rejection',()=>{
 const frozen={id:'source',kind:'source',manifest:{},variables:[{id:'param:humidity_ratio_kg_kg',unit:'g/kg_da',value:8}],values:{'param:humidity_ratio_kg_kg':8},banks:[]};
 const original=JSON.stringify(frozen);migrate({modules:[frozen]});assert.equal(JSON.stringify(frozen),original);
 const ordinary={id:'source',kind:'source',variables:[{id:'param:humidity_ratio_kg_kg',unit:'1',value:0}],values:{'param:humidity_ratio_kg_kg':3},banks:[]};
 migrate({modules:[ordinary]});assert.equal(ordinary.values['param:humidity_ratio_kg_kg'],3);
});

test('legacy model versions and instance banks repair once while frozen project snapshots stay untouched',()=>{
 const m={id:'source',kind:'source',variables:[{id:'param:humidity_ratio_kg_kg',origin:'parameter',unit:'g/kg_da',value:8}],
  values:{'param:humidity_ratio_kg_kg':8},banks:[]};
 const node={moduleId:'source',params:{humidity_ratio_kg_kg:8},draft:{humidity_ratio_kg_kg:8},
  variableState:{banks:[{'param:humidity_ratio_kg_kg':8},{'param:humidity_ratio_kg_kg':.012}]}};
 const frozen={moduleSnapshots:{source:{manifest:{parameters:[]},values:{'param:humidity_ratio_kg_kg':8}}},pages:[{nodes:[structuredClone(node)]}]};
 const before=JSON.stringify(frozen);
 const data={modules:[m],models:[{moduleId:'source',params:{humidity_ratio_kg_kg:8},versions:[{params:{humidity_ratio_kg_kg:8}}]}],
  projects:[frozen,{pages:[{nodes:[node]}]}]};
 migrate(data);
 assert.equal(data.models[0].params.humidity_ratio_kg_kg,.008);assert.equal(data.models[0].versions[0].params.humidity_ratio_kg_kg,.008);
 assert.equal(node.variableState.banks[0]['param:humidity_ratio_kg_kg'],.008);assert.equal(node.variableState.banks[1]['param:humidity_ratio_kg_kg'],.012);
 assert.equal(JSON.stringify(frozen),before);
 const repaired=JSON.stringify(data);migrate(data);assert.equal(JSON.stringify(data),repaired);
});
