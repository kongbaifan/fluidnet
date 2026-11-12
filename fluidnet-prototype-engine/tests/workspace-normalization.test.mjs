import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const host=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/workspace-normalization.js',import.meta.url),host);
const plain=value=>JSON.parse(JSON.stringify(value));
const emptyRun=()=>({source:'engine',status:'ready',history:[],events:[],values:{q:0}});
function setup(){
  const calls=[],definitions={},manifest={parameters:[{id:'opening',default:.8}],definition_hash:'frozen'};
  const python={id:'valve',kind:'valve',runtime:'python',category:'自定义',manifest,source:{runtime:'custom code'},variables:[]};
  const node={id:'V1',moduleId:'valve',params:{},variableState:{schema:1}};
  const owner={id:'first',pages:[{nodes:[node]}],moduleSnapshots:{valve:structuredClone(python)},
    run:{source:'engine',status:'solving'},controlConfig:{input:'old-flow',output:'old-valve'}};
  const state={modules:[python],projects:[owner],models:[],records:[{id:'archive',history:null,events:null}],bench:{moduleId:'valve'}};
  const api=host.window.FluidNetWorkspaceNormalization.create({parameterDefinitions:definitions,variablesFor:()=>[],clone:plain,
    moduleSpecs:[],pythonModuleSource:()=>({}),legacyModuleSource:()=>({}),defaultGroups:['基础'],
    manifestFields:m=>m.parameters.map(p=>[p.id,p.default]),manifestParamSpecs:m=>m.parameters,emptyRun,
    pinProject:(p,legacy)=>calls.push(['pin',p.id,legacy]),normalizeControls:p=>calls.push(['controls',p.id]),
    moduleOf:(n,p,data)=>p.moduleSnapshots?.[n.moduleId]||data.modules.find(m=>m.id===n.moduleId),
    validateInstanceVariableState:n=>{if(n.variableState?.schema!==1)throw Error('invalid variable state');calls.push(['validate',n.id]);},
    ensureInstanceVariables:(n,m,p)=>calls.push(['variables',n.id,m.id,p.id]),rehome:p=>calls.push(['rehome',p.id]),
    projectVariables:()=>[{id:'V1.flow',legacyId:'old-flow'},{id:'V1.opening',legacyId:'old-valve'}],
  });
  return {api,state,owner,node,python,definitions,calls};
}

test('older workspaces gain usable run fields and typed defaults once while retaining frozen contracts',()=>{
  const f=setup(),frozen=JSON.stringify(f.owner.moduleSnapshots),manifest=JSON.stringify(f.python.manifest);
  f.api.normalize(f.state);
  assert.equal(f.node.params.opening,.8);assert.equal(f.node.draft.opening,.8);assert.equal(f.state.bench.params.opening,.8);
  assert.equal(f.owner.run.status,'ready');assert.deepEqual(plain(f.owner.run.history),[]);
  assert.deepEqual(plain(f.state.records[0]),{id:'archive',history:[],events:[]});
  assert.deepEqual(plain(f.owner.controlConfig),{input:'V1.flow',output:'V1.opening'});
  assert.equal(JSON.stringify(f.owner.moduleSnapshots),frozen);assert.equal(JSON.stringify(f.python.manifest),manifest);
  assert.deepEqual(plain(f.definitions.valve),[['opening',.8]]);
  assert.deepEqual(f.calls.slice(0,5),[['pin','first',true],['controls','first'],['validate','V1'],['variables','V1','valve','first'],['rehome','first']]);
  const normalized=JSON.stringify(f.state);f.api.normalize(f.state);assert.equal(JSON.stringify(f.state),normalized);
  assert.doesNotThrow(()=>JSON.stringify(f.state));
});

test('the same normalizer reads each supplied workspace rather than retaining a previous owner',()=>{
  const f=setup();f.api.normalize(f.state);const previous=JSON.stringify(f.state);
  const other=structuredClone(f.state);other.projects[0].id='second';delete other.projects[0].pages[0].nodes[0].draft;
  f.api.normalize(other);assert.equal(JSON.stringify(f.state),previous);
  assert.equal(other.projects[0].pages[0].nodes[0].draft.opening,.8);assert.ok(f.calls.some(c=>c[0]==='pin'&&c[1]==='second'));
});

test('config-only project and circuit fluids become visible without changing their physical options',()=>{
  const f=setup(),config={backend:'coolprop',fluid:'REFPROP::R32[0.5]&R125[0.5]',reference:'mole',phase_policy:'liquid',composition:{}};
  f.owner.fluidConfig=structuredClone(config);
  f.owner.circuitFluids=[{id:'secondary',anchor:{instance_id:'V1',port_id:'in0'},fluidConfig:{...structuredClone(config),fluid:'INCOMP::MEG[0.3]'}}];
  f.api.normalize(f.state);
  assert.equal(f.owner.fluid,config.fluid);assert.equal(f.owner.fluidReference,'mole');
  assert.deepEqual(f.owner.fluidConfig,config);
  assert.equal(f.owner.circuitFluids[0].fluid,'INCOMP::MEG[0.3]');
  assert.equal(f.owner.circuitFluids[0].fluidReference,'mole');
  const once=JSON.stringify(f.state);f.api.normalize(f.state);assert.equal(JSON.stringify(f.state),once);
});

test('explicit cleared or edited fluid selectors survive normalization and JSON reload',()=>{
  for(const fluid of ['', '   ', 'Water']){
    const f=setup(),config={fluid:'REFPROP::R32[0.5]&R125[0.5]',reference:'mole',phase_policy:'liquid'};
    Object.assign(f.owner,{medium:'water',fluid,fluidReference:'mass',fluidConfig:structuredClone(config),
      circuitFluids:[{id:'secondary',anchor:{instance_id:'V1',port_id:'in0'},medium:'meg30',fluid,fluidReference:'mass',fluidConfig:structuredClone(config)}]});
    f.api.normalize(f.state);
    const reloaded=plain(f.state);f.api.normalize(reloaded);
    for(const owner of [f.owner,reloaded.projects[0]])for(const selection of [owner,...owner.circuitFluids]){
      assert.equal(selection.fluid,fluid);assert.equal(selection.fluidReference,'mass');
      assert.deepEqual(selection.fluidConfig,config);
    }
  }
});

test('absent fluid settings stay absent and explicit invalid selectors are not silently replaced',()=>{
  const f=setup();f.api.normalize(f.state);
  assert.equal(Object.hasOwn(f.owner,'fluid'),false);assert.equal(Object.hasOwn(f.owner,'fluidReference'),false);
  Object.assign(f.owner,{fluid:null,fluidReference:'unknown',fluidConfig:{fluid:'Water',reference:'mass'}});
  f.api.normalize(f.state);assert.equal(f.owner.fluid,null);assert.equal(f.owner.fluidReference,'unknown');
});

test('invalid device payload stays available to the normal validator instead of being silently replaced',()=>{
  const f=setup();f.node.variableState.schema=99;
  assert.throws(()=>f.api.normalize(f.state),/invalid variable state/);
  assert.equal(f.node.variableState.schema,99);
});

test('only recognized legacy templates migrate; custom source and Python packages remain unchanged',()=>{
  const api=host.window.FluidNetWorkspaceNormalization.create({moduleSpecs:[['pipe',null,'P']],
    pythonModuleSource:()=>({runtime:'new runtime',header:'new header',design:['new design']}),
    legacyModuleSource:()=>({runtime:'old\nruntime',header:'old header',design:['old design']})});
  const legacy={kind:'pipe',code:'P',source:{runtime:'old\r\nruntime',header:'user header',design:['user design']}};
  api.normalizePythonSource(legacy);
  assert.deepEqual(plain(legacy.source),{runtime:'new runtime',header:'user header',design:['user design']});
  const converted=JSON.stringify(legacy);api.normalizePythonSource(legacy);assert.equal(JSON.stringify(legacy),converted);
  const python={runtime:'python',source:{runtime:'old\nruntime',header:'old header',design:['old design']}};
  const original=JSON.stringify(python);api.normalizePythonSource(python);assert.equal(JSON.stringify(python),original);
});

test('group normalization keeps custom groups and fills missing module categories idempotently',()=>{
  const f=setup();f.state.modules.push({id:'uncategorized'});f.state.moduleGroups=['保留空分组'];
  f.api.normalizeGroups(f.state);
  assert.deepEqual(plain(f.state.moduleGroups),['保留空分组','自定义','自定义模块']);
  const once=JSON.stringify(f.state);f.api.normalizeGroups(f.state);assert.equal(JSON.stringify(f.state),once);
});
