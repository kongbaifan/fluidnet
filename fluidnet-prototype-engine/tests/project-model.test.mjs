import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const context=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/project-model.js',import.meta.url),'utf8'),context);
const model=context.window.FluidNetProjectModel;
const plain=value=>JSON.parse(JSON.stringify(value));

test('duplicate workspace restore ignores only top-level receipt metadata, never substantive drafts',()=>{
  const original={schema:1,dirty:false,projects:[{id:'p',dirty:false,run:{history:[{t:0,value:1}]},pages:[{nodes:[{id:'V1',params:{opening:40},draft:{opening:50}}]}]}],
    modules:[{id:'valve',manifest:{definition_hash:'original'},panelLayout:{parameters:['opening']}}],savedAt:'before',workspaceRevision:1};
  const receipt=structuredClone(original);Object.assign(receipt,{savedAt:'after',workspaceRevision:2,projectRevisions:{p:3},projectSavedKeys:{p:'key'}});
  assert.equal(model.workspaceContentEqual(original,receipt),true);
  for(const change of [v=>v.dirty=true,v=>v.projects[0].dirty=true,v=>v.projects[0].pages[0].nodes[0].draft.opening=60,
    v=>v.modules[0].panelLayout.parameters=[],v=>v.modules[0].manifest.definition_hash='changed',
    v=>v.projects[0].run.history[0].value=2,v=>v.projects[0].savedAt='nested-is-content']){
    const modified=structuredClone(receipt);change(modified);assert.equal(model.workspaceContentEqual(original,modified),false);
  }
  assert.equal(model.workspaceContentEqual(original,{...original,projects:undefined}),false);
});

test('workspace restore compares equally normalized content and rolls back if different-draft backup fails',()=>{
  const src=readFileSync(new URL('../frontend/studio.js',import.meta.url),'utf8');
  const original={dirty:false,modules:[],draft:{opening:55},derived:['default']};
  const ctx=vm.createContext({window:{},state:original,PARAM_DEFS:{valve:'original'},clone:structuredClone,
    ui:{floats:[],selectedNode:''},undoStack:[],redoStack:[],editRevision:0,savePhase:'',saveError:'',STORAGE_KEY:'test',render:()=>{},backups:[]});
  for(const name of ['project-model.js','project-state.js'])vm.runInContext(readFileSync(new URL('../frontend/'+name,import.meta.url),'utf8'),ctx);
  vm.runInContext(`const projectState=window.FluidNetProjectState,projectModel=window.FluidNetProjectModel;
    function validateImport(){}function normalizeState(){state.derived||=['default'];PARAM_DEFS.valve='normalized';}
    function backupLocalDraft(key,source){backups.push({key,source});throw Error('quota');}`,ctx);
  vm.runInContext(src.slice(src.indexOf('function replaceWorkspaceState('),src.indexOf('async function workspaceTools(')),ctx);
  ctx.restoreWorkspace({dirty:false,modules:[],draft:{opening:55}});
  assert.equal(ctx.backups.length,0);assert.equal(ctx.state.draft.opening,55);
  const accepted=ctx.state;ctx.PARAM_DEFS.valve='kept';
  assert.throws(()=>ctx.restoreWorkspace({dirty:false,modules:[],draft:{opening:66}}),/quota/);
  assert.equal(ctx.state,accepted);assert.equal(ctx.PARAM_DEFS.valve,'kept');
  assert.equal(ctx.backups[0].source,accepted);assert.equal(ctx.backups[0].source.draft.opening,55);
});

test('display and canonical conversions agree for absolute temperatures, differences, opening and power',()=>{
  for(const [unit,canonical,display] of [
    [{display_scale:1,display_offset:-273.15},298.15,25],
    [{display_scale:1,display_offset:0},5,5],
    [{display_scale:.01,display_offset:0},.4,40],
    [{display_scale:1000,display_offset:0},18000,18],
    [{display_scale:1/3600,display_offset:0},.001,3.6],
  ]){
    const spec={value_type:'number',unit};
    assert.ok(Math.abs(model.toDisplay(spec,canonical)-display)<1e-10);
    assert.ok(Math.abs(model.toCanonical(spec,display)-canonical)<1e-10);
  }
});
test('text, booleans, curves and missing values remain distinct from numeric conversion',()=>{
  for(const [type,value] of [['text','equal_percentage'],['boolean',false],['curve',[[0,4],[1,0]]]]){
    const spec={value_type:type};
    assert.deepEqual(plain(model.toDisplay(spec,value)),value);
    assert.deepEqual(plain(model.toCanonical(spec,value)),value);
  }
  assert.equal(model.toDisplay({value_type:'number',unit:{display_scale:1000}},null),null);
});
test('parameter views and defaults use the same units and do not mutate contracts',()=>{
  const manifest={parameters:[{id:'opening',label:'Opening',value_type:'number',default:.8,minimum:0,maximum:1,
    unit:{display_scale:.01,display_offset:0,display_unit:'%'}},{id:'enabled',value_type:'boolean',default:false}]};
  const before=structuredClone(manifest);
  const fields=model.manifestFields(manifest),specs=model.manifestParamSpecs(manifest);
  assert.equal(fields[0][6],80);assert.equal(specs[0].default,80);
  assert.deepEqual(plain(model.manifestParamDefaults(manifest)),{opening:80,enabled:false});
  assert.deepEqual(manifest,before);
});
