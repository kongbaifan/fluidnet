import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const plain=value=>JSON.parse(JSON.stringify(value));
const context=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/control-programs.js',import.meta.url),'utf8'),context);
vm.runInContext(readFileSync(new URL('../frontend/project-services.js',import.meta.url),'utf8'),context);
const module={id:'author',version:2,parameters:[
  {id:'opening_ratio',default:.5,value_type:'number',unit:{display_scale:.01,display_offset:0}},
  {id:'characteristic',default:'linear',value_type:'text'},{id:'kv_m3_h',default:.6,value_type:'number'}]};

test('upgrade retains sparse scenario overrides and other device display units',()=>{
  const owner={id:'p',moduleSnapshots:{author:{id:'author',manifest:module}},pages:[{nodes:[
    {id:'Valve-custom',moduleId:'author',params:{opening_ratio:50,characteristic:'linear',kv_m3_h:.6}}],edges:[]}],
    controlPrograms:[],selectedVariables:['Valve-custom.old_output'],
    scenarios:[{id:'partial',name:'Partial',overrides:{'Valve-custom':{opening_ratio:20},Source:{temperature:25,pressure:250}}}]};
  const state={modules:[],models:[],charts:{extra:[]}};
  const service=context.window.createProjectServices({ui:{state:()=>state,emptyRun:()=>({})},pinProject:()=>{},
    moduleFromManifest:manifest=>({id:manifest.id,manifest}),request:()=>{},health:()=>({})});
  const before=plain(owner);
  const next=service.upgradeDocument(owner,{module,project:{instances:[{id:'Valve-custom',
    parameters:{opening_ratio:.5,characteristic:'linear',kv_m3_h:.6},draft_parameters:{opening_ratio:.8,characteristic:'equal_percentage',kv_m3_h:.6},banks:[]}],
    scenarios:[{id:'partial',name:'Partial',overrides:{'Valve-custom':{opening_ratio:.2},Source:{temperature_k:298.15,pressure_pa:250000}}}],
    selected_variables:['Valve-custom.new_output'],controllers:[],control_scripts:[]}});
  assert.deepEqual(plain(next.project.scenarios),before.scenarios);
  assert.equal(next.project.pages[0].nodes[0].draft.opening_ratio,80);
  assert.equal(next.project.pages[0].nodes[0].draft.characteristic,'equal_percentage');
  assert.deepEqual(plain(next.project.selectedVariables),['Valve-custom.new_output']);
  assert.deepEqual(owner.pages,before.pages);
});

test('canonical import preserves authored hashes, controls, fluid options, drafts and banks',async()=>{
  const source=JSON.parse(readFileSync(new URL('../examples/refrigeration_extensions/author_station.json',import.meta.url),'utf8'));
  const valve=source.instances.find(n=>n.id==='Expansion-Custom');
  valve.parameters.opening_ratio=.4;valve.draft_parameters={opening_ratio:.2};
  valve.banks=[{name:'Saved opening',values:{opening_ratio:.3}}];
  source.scenarios[0].overrides.ROOM1={heat_input_w:18000};
  source.selected_variables=['Expansion-Custom.mass_flow_kg_s'];
  const before=plain(source),requests=[];
  const service=context.window.createProjectServices({request:async(path,body)=>{requests.push([path,plain(body)]);return {valid:true};},
    moduleFromManifest:m=>({id:m.id,manifest:m,bankNames:['A','B','C']}),ui:{state:()=>({}),
      makeProject:(id,name,description,page)=>({id,name,description,pages:[page],controlPrograms:[],controlScripts:[]})}});
  const document=await service.exchangeDocument(source),project=document.project;
  const node=project.pages[0].nodes.find(n=>n.id===valve.id);
  assert.equal(node.params.opening_ratio,40);assert.equal(node.draft.opening_ratio,20);
  assert.equal(node.variableState.banks[0]['param:opening_ratio'],30);
  assert.equal(project.scenarios[0].overrides.ROOM1.heat_input_w,18);
  assert.deepEqual(plain(project.controllers),source.controllers);
  assert.deepEqual(plain(project.controlScripts),source.control_scripts);
  assert.deepEqual(plain(project.circuitFluids[0].fluidConfig),source.circuit_fluids[0].fluid);
  assert.equal(project.moduleSnapshots.isenthalpic_throttle.manifest.definition_hash,source.modules.find(m=>m.id==='isenthalpic_throttle').definition_hash);
  assert.deepEqual(plain(project.selectedVariables),source.selected_variables);
  assert.equal(requests[0][0],'/projects/validate');assert.deepEqual(source,before);
});
