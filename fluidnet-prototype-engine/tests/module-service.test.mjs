import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const plain=value=>JSON.parse(JSON.stringify(value));
const released=(changes={})=>({id:'test_valve',name:'试验阀',category:'阀门',version:1,runtime:'python',solver_model:'generic',entrypoint:'module:Module',
  source:{runtime:'class Module: pass',design:'def design(ctx): pass'},content_hash:'a'.repeat(64),definition_hash:'b'.repeat(64),
  ports:[{id:'in0',label:'入口',domain:'fluid',direction:'in',required:true,circuit:'water'},
    {id:'out0',label:'出口',domain:'fluid',direction:'out',required:true,circuit:'water'}],
  channels:[{id:'main',name:'主通路',input_port:'in0',output_port:'out0',relation:'resistance',solver_model:'generic',enabled:true}],
  parameters:[{id:'opening',label:'开度',value_type:'number',default:.5,minimum:0,maximum:1,writable:true,runtime:true,unit:{display_unit:'%',display_scale:.01,display_offset:0}},
    {id:'temperature',label:'温度',value_type:'number',default:293.15,minimum:273.15,unit:{display_unit:'°C',display_scale:1,display_offset:-273.15}},
    {id:'source_note',label:'来源',value_type:'text',default:'教学数据'}],variables:[],bank_names:['额定','部分负荷','备用'],...changes});
function fixture({definition=released(),handler=()=>{throw Error('Unexpected request');},persist=true}={}){
  const host=vm.createContext({window:{}});
  for(const name of ['project-model','canvas-symbols','module-service'])loadFrontend(new URL('../frontend/'+name+'.js',import.meta.url),host);
  const model=host.window.FluidNetProjectModel,moduleFromManifest=value=>model.moduleFromManifest(value),m=moduleFromManifest(plain(definition));
  m.publishedManifest=plain(definition);m.latestVersion=definition.version;m.dirty=false;
  const modules=[m],fields={},calls=[],outputs=[],messages=[],dirties=[],bench={moduleId:'other'},owner={id:'project',pages:[{nodes:[{id:'Device',moduleId:m.id}]}]};
  const normalized={id:'host',name:'真实宿主',instances:[{id:'Selected',module_id:m.id}],modules:[plain(definition)],fluid:{fluid:'Ammonia'}};
  let renders=0,saves=0;
  const service=host.window.createModuleService({model,moduleFromManifest,modules:()=>modules,getBench:()=>bench,parameterDefinitions:fields,
    request:async(path,body)=>{calls.push({path,body:body&&plain(body)});return handler(path,body);},
    normalizeProject:async p=>{assert.equal(p,owner);return normalized;},
    testFlow:()=>null,copyPanel:(a,b)=>{if(a.panelLayout)b.panelLayout=plain(a.panelLayout);},
    copyPresentation:host.window.FluidNetCanvasSymbols.copyPresentation,
    output:(module,text)=>outputs.push({module,text}),dirty:module=>dirties.push(module),render:()=>renders++,persist:()=>{saves++;return persist;},message:(text,error)=>messages.push({text,error})});
  return {service,m,modules,fields,bench,owner,normalized,calls,outputs,messages,dirties,get renders(){return renders;},get saves(){return saves;}};
}
const release=(module,version=2)=>{const definition={...plain(module),version,content_hash:'c'.repeat(64),definition_hash:'d'.repeat(64)};
  return {module:definition,package:{version:version+'.0.0',content_hash:definition.content_hash,definition_hash:definition.definition_hash},test_result:{frame:{variables:{}}}};};

test('frozen definitions preserve executable hashes and strip only receipt metadata',()=>{
  const f=fixture(),m=f.m;m.frozen=true;m.manifest.package={path:'receipt'};m.manifest.validation_evidence=[{level:'L3'}];
  m.source.runtime='different library draft';const before=plain(m),payload=f.service.manifestPayload(m);
  assert.equal(payload.content_hash,'a'.repeat(64));assert.equal(payload.source.runtime,'class Module: pass');assert.equal(payload.package,undefined);
  payload.ports[0].label='detached';assert.deepEqual(plain(m),before);
  m.frozen=false;m.contractDraft='{"runtime":"builtin"}';assert.throws(()=>f.service.manifestPayload(m),/不能编辑字段/);
});
test('insertion freezes a published release and detached drawing without applying library drafts',()=>{
  const f=fixture();f.m.source.runtime='new draft';f.m.drawing={shape:'circle',width:40,height:35,label:'自定义图形'};f.m.ports[0].x=15;
  const bound=f.service.moduleForInsert(f.m.id);assert.equal(bound.frozen,true);assert.equal(bound.manifest.source.runtime,'class Module: pass');
  assert.equal(bound.ports[0].x,15);assert.equal(bound.drawing.shape,'circle');
  f.service.pinProject(f.owner);const snapshot=f.owner.moduleSnapshots[f.m.id];f.m.drawing.width=50;f.m.ports[0].x=30;
  assert.equal(snapshot.drawing.width,40);assert.equal(snapshot.ports[0].x,15);assert.equal(f.owner.pages[0].nodes[0].package.version,'1.0.0');
  f.m.publishedManifest.version=2;assert.equal(f.service.bindModule(f.owner,f.m.id),snapshot);assert.equal(snapshot.version,1);
  delete f.m.publishedManifest;assert.throws(()=>f.service.moduleForInsert(f.m.id),/先校验并保存/);
});
test('builtin presentation snapshots keep their own display parameter definitions and no Python package',()=>{
  const f=fixture(),m={id:'pipe',kind:'pipe',runtime:'builtin',drawing:{shape:'rectangle'},ports:[]};f.modules.push(m);
  f.fields.pipe=[['length','长度','m',0,100,1,1]];f.owner.pages[0].nodes=[{id:'P',moduleId:'pipe'}];
  f.service.pinProject(f.owner);f.fields.pipe[0][0]='canonical_length';
  assert.equal(f.owner.moduleSnapshots.pipe.parameterDefs[0][0],'length');assert.equal(f.owner.pages[0].nodes[0].package,undefined);
});

test('insertion planning reports the actual pinned release and never mutates the project or draft',()=>{
  const f=fixture();f.owner.pages[0].id='main';
  const before=plain(f.owner),draft=plain(f.m),plan=f.service.insertionPlan(f.owner,f.m.id,'main');
  assert.equal(plan.module.version,1);assert.equal(plan.usesPinnedVersion,false);
  assert.deepEqual(plain(f.owner),before);assert.deepEqual(plain(f.m),draft);
  f.service.pinProject(f.owner);f.m.publishedManifest=released({version:2,definition_hash:'new'});f.m.source.runtime='unpublished draft';
  const pinned=f.service.insertionPlan(f.owner,f.m.id,'main');
  assert.equal(pinned.module.version,1);assert.equal(pinned.availableVersion,2);assert.equal(pinned.usesPinnedVersion,true);
  assert.equal(pinned.module.manifest.source.runtime,'class Module: pass');
  delete f.m.publishedManifest;
  assert.equal(f.service.insertionPlan(f.owner,f.m.id,'main').module,pinned.module);
  f.modules.length=0;
  assert.equal(f.service.insertionPlan(f.owner,f.m.id,'main').module,pinned.module);
});

test('insertion refuses unavailable releases, running projects and full or missing canvases without pinning',()=>{
  const f=fixture();f.owner.pages[0].id='main';const before=plain(f.owner);
  assert.throws(()=>f.service.insertionPlan(f.owner,f.m.id,'missing'),/不存在/);
  assert.throws(()=>f.service.insertionPlan(f.owner,'missing','main'),/模块已不存在/);
  delete f.m.publishedManifest;assert.throws(()=>f.service.insertionPlan(f.owner,f.m.id,'main'),/先校验并保存/);
  assert.deepEqual(plain(f.owner),before);
  f.m.publishedManifest=released();
  for(const status of ['running','solving','paused']){f.owner.run={status};assert.throws(()=>f.service.insertionPlan(f.owner,f.m.id,'main'),/停止/);}
  f.owner.run={status:'completed'};f.owner.pages[0].nodes=Array.from({length:64},(_,i)=>({id:'n'+i}));
  assert.throws(()=>f.service.insertionPlan(f.owner,f.m.id,'main'),/64/);assert.equal(f.owner.moduleSnapshots,undefined);
});
test('a validation reply cannot overwrite a draft edited while validation is pending',async()=>{
  let deliver;const f=fixture({handler:()=>new Promise(resolve=>{deliver=resolve;})});
  const pending=f.service.checkModule(f.m,true);f.m.source.runtime='edited during request';deliver({valid:true,diagnostics:[]});
  assert.equal(await pending,false);assert.equal(f.m.source.runtime,'edited during request');assert.equal(f.dirties.length,0);
  assert.match(f.outputs.at(-1).text,/草稿已变化/);
});
test('design uses canonical numbers and returns detached display proposals without applying the bank',async()=>{
  const f=fixture({handler:()=>({changes:[{id:'opening',before:.5,after:.8},{id:'temperature',before:293.15,after:303.15}],diagnostics:[],design_hash:'design'})});
  const before=plain(f.m.banks);const result=await f.service.runDesign(f.m,0);
  assert.deepEqual(f.calls[0].body.parameters,{opening:.5,temperature:293.15});assert.equal(result.changes[0].after,80);assert.equal(result.changes[1].after,30);
  assert.deepEqual(plain(f.m.banks),before);assert.equal(result.designHash,'design');
});
test('late design reply rejects a changed bank',async()=>{
  let deliver;const f=fixture({handler:()=>new Promise(resolve=>{deliver=resolve;})});const pending=f.service.runDesign(f.m,0);
  f.m.banks[0]['param:opening']=70;deliver({changes:[],diagnostics:[]});await assert.rejects(pending,/库值已变化/);assert.equal(f.m.banks[0]['param:opening'],70);
});
test('publication validates defaults, converts bench boundaries, and promotes only the submitted draft',async()=>{
  const f=fixture({handler:(path,body)=>path==='/modules/versions'?release(body.module):{versions:[{package:{version:'2.0.0'}}]}});
  Object.assign(f.bench,{moduleId:f.m.id,run:{step:.5},boundary:{inlet:250,outlet:120,temperature:30}});
  f.m.banks[0]['param:opening']=90;await f.service.saveModule(f.m);
  const request=f.calls[0].body;assert.deepEqual(request.test,{inlet_pressure_pa:250000,outlet_pressure_pa:120000,temperature_k:303.15,dt_s:.5,duration_s:.5});
  assert.equal(request.module.parameters[0].default,.5);assert.equal(request.expected_latest_version,1);
  assert.equal(f.m.version,2);assert.equal(f.m.publishedManifest.version,2);assert.equal(f.m.dirty,false);assert.equal(f.m.saving,false);assert.equal(f.saves,1);
});
test('save locks duplicate submissions and preserves incomplete JSON typed before the receipt',async()=>{
  let deliver;const f=fixture({handler:(path)=>path==='/modules/versions'?new Promise(resolve=>{deliver=resolve;}):{versions:[{package:{version:'2.0.0'}}]}});
  const pending=f.service.saveModule(f.m);await f.service.saveModule(f.m);assert.equal(f.calls.length,1);
  const sent=f.calls[0].body.module;f.m.contractDraft='{"parameters":';f.m.dirty=true;deliver(release(sent));await pending;
  assert.equal(f.m.contractDraft,'{"parameters":');assert.equal(f.m.publishedManifest.version,2);assert.equal(f.m.version,1);assert.equal(f.m.latestVersion,2);assert.equal(f.m.dirty,true);assert.equal(f.m.saving,false);
  assert.match(f.outputs.at(-1).text,/新编辑已保留/);
});
test('publication failure retains release and draft, while local save failure still reports the real published version',async()=>{
  const rejected=fixture({handler:()=>{throw Object.assign(Error('invalid'),{detail:{diagnostics:[{code:'BAD'}],replay:{stage:'evaluate'}}});}});
  const old=plain(rejected.m.publishedManifest);await rejected.service.saveModule(rejected.m);
  assert.deepEqual(plain(rejected.m.publishedManifest),old);assert.equal(rejected.m.authoringDiagnostics[0].code,'BAD');assert.equal(rejected.m.authoringReplay.stage,'evaluate');assert.equal(rejected.m.saving,false);
  const local=fixture({persist:false,handler:(path,body)=>path==='/modules/versions'?release(body.module):{versions:[]}});await local.service.saveModule(local.m);
  assert.equal(local.m.publishedManifest.version,2);assert.match(local.messages.at(-1).text,/后端 v2 已保存.*浏览器草稿存储失败/);
});
test('open group publication retains the real host and refuses missing host before any request',async()=>{
  const definition=released({sdk:{capabilities:['composite.refrigeration.open.v1']}}),f=fixture({definition,handler:(path,body)=>path==='/modules/versions'?release(body.module):{versions:[]}});
  await f.service.saveModule(f.m);assert.equal(f.calls.length,0);assert.match(f.outputs.at(-1).text,/缺少宿主/);
  f.m.testConditions={host_project:{id:'host',name:'完整站',instances:[{id:'D1',module_id:f.m.id}]},host_instance_id:'D1',fluid:{fluid:'Ammonia'},dt_s:.1,duration_s:1};
  Object.assign(f.bench,{moduleId:f.m.id,run:{step:.3},boundary:{inlet:999,outlet:1,temperature:100}});
  const before=plain(f.m.testConditions);await f.service.saveModule(f.m);const sent=f.calls[0].body.test;
  assert.deepEqual(sent.host_project,before.host_project);assert.equal(sent.inlet_pressure_pa,undefined);assert.equal(sent.temperature_k,undefined);assert.equal(sent.dt_s,.3);assert.equal(sent.duration_s,.3);
});
test('version loading restores its host and keeps already-bound project releases unchanged',async()=>{
  const f=fixture({handler:()=>({module:released({version:2,sdk:{capabilities:['composite.refrigeration.open.v1']}}),test_conditions:{host_project:{name:'旧版宿主'}}})});
  f.service.pinProject(f.owner);f.m.drawing.shape='circle';await f.service.loadVersion(f.m,2);
  assert.equal(f.m.version,2);assert.equal(f.m.testConditions.host_project.name,'旧版宿主');assert.equal(f.m.drawing.shape,'circle');assert.equal(f.owner.moduleSnapshots[f.m.id].version,1);
});
test('templates and composites keep their own test conditions and use normalized host data',async()=>{
  const f=fixture({handler:(path,body)=>path==='/modules/composites/test-context'?{host_project:{...body.project,name:'封组宿主'}}:
    released({id:body.id,name:body.name,sdk:{capabilities:body.instance_ids?['composite.refrigeration.open.v1']:[]}})});
  const pump=await f.service.newTemplate('pump_a','泵','设备','pump');assert.deepEqual(plain(pump.testConditions),{inlet_pressure_pa:120000,outlet_pressure_pa:250000});
  const group=await f.service.newComposite(f.owner,['Selected'],'group_a','设备组');assert.equal(group.testConditions.host_project.name,'封组宿主');
  const call=f.calls.find(c=>c.path==='/modules/composites/from-group');assert.deepEqual(call.body.project,plain(f.normalized));assert.equal(group.latestVersion,0);assert.equal(group.dirty,true);
});
test('contract edits reject duplicate identifiers before changing the authoring model',()=>{
  const f=fixture(),before=plain(f.m);assert.throws(()=>f.service.updateContractItem(f.m,'ports','in0',{id:'out0'}),/重复/);assert.deepEqual(plain(f.m),before);
  f.service.updateContractItem(f.m,'parameters','opening',{...f.m.parameters[0],default:.7});
  assert.equal(f.m.parameters[0].default,.7);assert.equal(f.m.banks[0]['param:opening'],70);assert.equal(f.dirties[0],f.m);
});

test('common parameter editing converts percentages, retains other banks and leaves project releases untouched',()=>{
  const f=fixture();f.service.pinProject(f.owner);f.m.banks[1]['param:temperature']=35;
  const pinned=plain(f.owner.moduleSnapshots[f.m.id]);
  f.service.updateDisplayParameter(f.m,'opening',{label:'开度',unit:'0',default:'75',minimum:'10',maximum:'100'});
  const p=f.m.parameters.find(p=>p.id==='opening');assert.equal(p.default,.75);assert.equal(p.minimum,.1);assert.equal(p.maximum,1);
  assert.equal(p.runtime,true);assert.equal(f.m.banks[0]['param:opening'],75);assert.equal(f.m.banks[1]['param:temperature'],35);
  assert.deepEqual(plain(f.owner.moduleSnapshots[f.m.id]),pinned);assert.equal(f.m.publishedManifest.parameters[0].default,.5);
});

test('common parameter units preserve custom mappings and convert length and absolute temperature bounds',()=>{
  const f=fixture();let form=f.service.parameterEditor(f.m);
  const mm=form.units.findIndex(u=>u?.display_unit==='mm');
  f.service.updateDisplayParameter(f.m,null,{id:'diameter',label:'直径',value_type:'number',unit:String(mm),default:'40',minimum:'10',maximum:'80'});
  const p=f.m.parameters.find(p=>p.id==='diameter');assert.equal(p.default,.04);assert.equal(p.minimum,.01);assert.equal(p.maximum,.08);
  form=f.service.parameterEditor(f.m,'diameter');assert.ok(form.units.every(u=>u.canonical_unit==='m'));
  f.service.updateDisplayParameter(f.m,'temperature',{label:'温度',unit:'0',default:'-10',minimum:'-20',maximum:'30'});
  const temperature=f.m.parameters.find(p=>p.id==='temperature');
  for(const [key,expected] of [['default',263.15],['minimum',253.15],['maximum',303.15]])assert.ok(Math.abs(temperature[key]-expected)<1e-10);
  f.m.parameters[0].unit={quantity:'custom',canonical_unit:'widgets',display_unit:'boxes',display_scale:12,display_offset:2};
  assert.deepEqual(plain(f.service.parameterEditor(f.m,'opening').units),[f.m.parameters[0].unit]);
});

test('common parameter validation rejects invalid defaults atomically and preserves boolean and text types',()=>{
  const f=fixture(),before=plain(f.m);
  for(const change of [{default:'101'},{default:''},{default:'Infinity'},{minimum:'90',maximum:'20'},{unit:'999'},{label:' '}]){
    assert.throws(()=>f.service.updateDisplayParameter(f.m,'opening',{label:'开度',unit:'0',default:'75',minimum:'0',maximum:'100',...change}));
    assert.deepEqual(plain(f.m),before);
  }
  f.service.updateDisplayParameter(f.m,null,{id:'enabled',label:'启用',value_type:'boolean',default:'false'});
  assert.equal(f.m.parameters.find(p=>p.id==='enabled').default,false);
  f.service.updateDisplayParameter(f.m,'source_note',{label:'说明',default:'设备 A'});
  assert.equal(f.m.parameters.find(p=>p.id==='source_note').default,'设备 A');
  const after=plain(f.m);assert.throws(()=>f.service.updateDisplayParameter(f.m,null,{id:'enabled',label:'重复',value_type:'text',default:'x'}),/重复/);
  assert.deepEqual(plain(f.m),after);
});

test('metadata edits keep library values, publication and pending contract edits, and reject invalid JSON atomically',()=>{
  const f=fixture();f.m.banks[0]['param:opening']=70;f.m.contractDraft=JSON.stringify({description:'旧说明',parameters:f.m.parameters});
  const published=plain(f.m.publishedManifest);f.service.updateMetadata(f.m,{name:'新名称',description:'新用途'});
  assert.equal(f.m.drawing.label,'新名称');assert.equal(f.m.banks[0]['param:opening'],70);
  assert.equal(JSON.parse(f.m.contractDraft).description,'新用途');assert.equal(f.service.manifestPayload(f.m).name,'新名称');
  assert.deepEqual(plain(f.m.publishedManifest),published);
  f.m.contractDraft='{';const before=plain(f.m);assert.throws(()=>f.service.updateMetadata(f.m,{name:'不可写入'}));assert.deepEqual(plain(f.m),before);
});
