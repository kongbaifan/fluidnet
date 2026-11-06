import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context=vm.createContext({window:{}});
for(const path of ['project-model.js','project-state.js','equipment-selection.js'])vm.runInContext(readFileSync(new URL('../frontend/'+path,import.meta.url),'utf8'),context);
const api=context.window.EquipmentSelection;
const plain=value=>JSON.parse(JSON.stringify(value));
const definition={id:'device',version:1,runtime:'python',source:{design:'def design(ctx): pass'},definition_hash:'a',content_hash:'b',parameters:[
  {id:'temperature',label:'温度',value_type:'number',default:293.15,minimum:273.15,unit:{display_scale:1,display_offset:-273.15}},
  {id:'opening',label:'开度',value_type:'number',default:.5,minimum:0,maximum:1,unit:{display_scale:.01,display_offset:0}},
  {id:'enabled',label:'启用',value_type:'boolean',default:true},
  {id:'curve',label:'曲线',value_type:'curve',default:[[0,1],[1,0]]},
]};
test('selection respects declared unit conversion and nonnumeric parameter types',()=>{
  const values=api.readInputs(definition,{'selection:temperature':'30','selection:opening':'75','selection:enabled':'false','selection:curve':'[[0,2],[1,1]]'});
  assert.deepEqual(plain(context.window.FluidNetProjectModel.canonicalParameters(definition,values)),{temperature:303.15,opening:.75,enabled:false,curve:[[0,2],[1,1]]});
  assert.deepEqual(plain(api.proposal(definition,{temperature:303.15,opening:.75,enabled:false,curve:[[0,2],[1,1]]})),plain(values));
  assert.throws(()=>api.readInputs(definition,{'selection:temperature':'','selection:opening':'50'}),/有限数值/);
  assert.throws(()=>api.readInputs(definition,{'selection:temperature':'30','selection:opening':'101'}),/范围/);
});
test('a changed draft, fluid, instance or definition invalidates an outstanding selection',()=>{
  const node={id:'D1',params:{opening:50},draft:{opening:60}},owner={id:'p',fluid:'Water',pages:[{nodes:[node]}]},state={activeProject:'p',projects:[owner]};
  const before=api.fingerprint(owner,node,definition);
  api.assertCurrent(state,owner,node,definition,before);
  node.draft.opening=70;assert.throws(()=>api.assertCurrent(state,owner,node,definition,before),/变化/);
  node.draft.opening=60;owner.fluid='Air';assert.throws(()=>api.assertCurrent(state,owner,node,definition,before),/变化/);
  owner.fluid='Water';assert.throws(()=>api.assertCurrent(state,owner,node,{...definition,version:2},before),/变化/);
  owner.pages[0].nodes=[{...node}];assert.throws(()=>api.assertCurrent(state,owner,node,definition,before),/替换/);
  assert.equal(node.params.opening,50);
});
test('selection model cannot be silently applied to a different module release',()=>{
  const item={moduleId:'device',moduleVersion:1,selection:{definitionHash:'a',contentHash:'b'}};
  api.assertModelCompatible(item,definition);
  assert.throws(()=>api.assertModelCompatible(item,{...definition,version:2}),/版本/);
  assert.throws(()=>api.assertModelCompatible(item,{...definition,definition_hash:'c'}),/版本/);
  assert.equal(api.supported(definition),true);
  assert.equal(api.supported({...definition,source:{runtime:'code'}}),false);
});
