import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const plain=value=>JSON.parse(JSON.stringify(value));
const context=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/project-model.js',import.meta.url),context);
loadFrontend(new URL('../frontend/control-programs.js',import.meta.url),context);
loadFrontend(new URL('../frontend/project-services.js',import.meta.url),context);
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

test('canonical import preserves cross-canvas connections and page identities',async()=>{
  const source=JSON.parse(readFileSync(new URL('../examples/refrigeration_extensions/author_station.json',import.meta.url),'utf8'));
  source.instances.forEach((node,index)=>node.page_id=index%2?'terminal':'plant');
  const service=context.window.createProjectServices({request:async()=>({valid:true}),
    moduleFromManifest:m=>({id:m.id,manifest:m,bankNames:['A','B','C']}),ui:{state:()=>({}),
      makeProject:(id,name,description,page)=>({id,name,description,pages:[page],controlPrograms:[],controlScripts:[]})}});
  const result=await service.exchangeDocument(source);
  assert.equal(result.project.pages.length,2);
  const edges=result.project.pages.flatMap(page=>page.edges);
  assert.deepEqual(plain(edges).sort((a,b)=>a[0].localeCompare(b[0])),source.connections.map(c=>
    [c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id]).sort((a,b)=>a[0].localeCompare(b[0])));
  for(const page of result.project.pages)for(const edge of page.edges)
    assert.ok(page.nodes.some(node=>node.id===edge[1]));
});

test('module port migration updates cross-canvas references stored on the other canvas',()=>{
  const owner={id:'p',moduleSnapshots:{author:{id:'author',manifest:module},source:{id:'source'}},
    pages:[{id:'plant',nodes:[{id:'Source',moduleId:'source'}],edges:[['feed','Source','out','Custom','old_in']]},
      {id:'terminal',nodes:[{id:'Custom',moduleId:'author',params:{opening_ratio:50}}],edges:[['return','Custom','old_out','Source','in']]}],
    controlPrograms:[],scenarios:[]};
  const service=context.window.createProjectServices({ui:{state:()=>({modules:[],models:[],charts:{extra:[]}}),emptyRun:()=>({})},
    pinProject:()=>{},moduleFromManifest:manifest=>({id:manifest.id,manifest})});
  const result=service.upgradeDocument(owner,{module,migration:{ports:{old_in:'new_in',old_out:'new_out'}},project:{
    instances:[{id:'Custom',parameters:{opening_ratio:.5,characteristic:'linear',kv_m3_h:.6},
      draft_parameters:{opening_ratio:.5,characteristic:'linear',kv_m3_h:.6},banks:[]}],
    scenarios:[],controllers:[],control_scripts:[]}});
  assert.equal(result.project.pages[0].edges[0][4],'new_in');
  assert.equal(result.project.pages[1].edges[0][2],'new_out');
  assert.equal(owner.pages[0].edges[0][4],'old_in');
});
