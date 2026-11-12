import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const plain=value=>JSON.parse(JSON.stringify(value));
const manifest=(id='registered_device')=>({id,name:id,runtime:'builtin',version:1,ports:[{id:'in0',domain:'fluid',direction:'in'}],parameters:[],channels:[],variables:[]});
const metadata=(id='registered_device')=>({module_id:id,runtime:'builtin',domains:['fluid'],capabilities:['thermal_storage'],icon:'Database',canvas_family:'tank'});
function fixture({status=200,version=1,id='registered_device',initial}={}){
  const messages=[],requests=[];
  const state=initial||{modules:[],projects:[]};
  const host=vm.createContext({window:{createProjectServices:()=>({loadWorkspace:async()=>'',refreshArchives:async()=>{}})},sessionStorage:{getItem:()=>null},fetch:async path=>{
    requests.push(path);let body;
    if(path.endsWith('/health'))body={version:'test',auth:{required:false}};
    else if(path.endsWith('/catalog/presentation'))return {ok:status===200,status,json:async()=>status===200?{version,devices:[metadata(id)]}:{detail:'unavailable'}};
    else if(path.endsWith('/catalog'))body={modules:[manifest(id)],prototype_parameter_bindings:{}};
    else if(path.endsWith('/modules'))body={modules:[]};
    else throw Error('Unexpected request '+path);
    return {ok:true,status:200,json:async()=>body};
  }});
  for(const file of ['project-model','canvas-symbols','project-run-state','module-service','engine-client'])
    loadFrontend(new URL('../frontend/'+file+'.js',import.meta.url),host);
  const ui={state:()=>state,parameterDefinitions:{},emptyRun:()=>({history:[]}),render:()=>{},message:(text,error)=>messages.push({text,error})};
  const client=host.window.createEngineClient(ui);
  return {client,state,requests,messages,model:host.window.FluidNetProjectModel,symbols:host.window.FluidNetCanvasSymbols};
}

test('catalog metadata supplies registration, icons and canvas family without a frontend device ID entry',async()=>{
  const f=fixture();await f.client.init();
  assert.ok(f.requests.includes('/api/v1/catalog/presentation'));
  const device=f.state.modules.find(m=>m.id==='registered_device');assert.ok(device);
  assert.equal(device.icon,'Database');assert.equal(f.symbols.family(device),'tank');
  assert.deepEqual(plain(device.manifest),manifest());
  const owner={pages:[{nodes:[{moduleId:device.id}]}]};f.client.pinProject(owner);
  const bound=owner.moduleSnapshots[device.id];assert.equal(f.symbols.family(bound),'tank');
  device.presentation.canvas_family='pump';assert.equal(f.symbols.family(bound),'tank');
});

test('metadata never replaces an existing frozen project presentation or modifies physical parameter identity',async()=>{
  const device={...manifest(),kind:'registered_device',drawing:{},icon:'Box',presentation:{icon:'Box',canvas_family:'module'}};
  const owner={pages:[{nodes:[{moduleId:device.id}]}],moduleSnapshots:{[device.id]:device}};
  const f=fixture({initial:{modules:[],projects:[owner]}});await f.client.init();
  assert.equal(owner.moduleSnapshots[device.id],device);assert.equal(f.symbols.family(device),'module');
  const before=f.model.parameterKey(owner,[device],()=>null);
  device.presentation.canvas_family='tank';device.icon='Database';
  assert.equal(f.model.parameterKey(owner,[device],()=>null),before);
});

test('older backends and unknown metadata versions retain legacy tank visibility and fallback icons',async()=>{
  for(const options of [{status:404},{status:501},{version:2}]){
    const f=fixture({...options,id:'closed_buffer_tank'});await f.client.init();
    const device=f.state.modules.find(m=>m.id==='closed_buffer_tank');assert.ok(device);
    assert.equal(device.icon,'Database');assert.equal(f.symbols.family(device),'tank');
    assert.equal(f.messages.some(message=>message.error),false);
  }
});

test('a presentation service failure leaves the computation catalog usable and reports fallback',async()=>{
  const f=fixture({status:503,id:'closed_buffer_tank'});await f.client.init();
  assert.equal(f.client.health.version,'test');assert.equal(f.state.modules.length,1);
  assert.equal(f.messages.at(-1).error,true);assert.match(f.messages.at(-1).text,/展示目录读取失败/);
});

test('unregistered Python modules do not inherit builtin presentation and unsupported shapes fall back',()=>{
  const f=fixture(),source={...manifest(),runtime:'python'},copy=plain(source);
  const device=f.model.moduleFromManifest(source,undefined,metadata());
  assert.equal(device.icon,'Box');assert.equal(device.presentation,undefined);assert.deepEqual(source,copy);
  const unknown=f.model.moduleFromManifest(manifest(),undefined,{...metadata(),canvas_family:'missing'});
  assert.equal(f.symbols.family(unknown),'module');assert.doesNotThrow(()=>f.symbols.bodyBounds({},unknown));
  const target=f.model.moduleFromManifest(manifest());f.symbols.copyPresentation(unknown,target);
  assert.equal(target.presentation,undefined);
});

test('malformed or unfamiliar optional metadata cannot corrupt catalog lookup',()=>{
  const f=fixture();
  for(const response of [null,{},[],{version:1},{version:1,devices:{}},{version:2,devices:[metadata()]}])
    assert.deepEqual(Object.keys(f.model.catalogPresentationIndex(response)),[]);
  const result=f.model.catalogPresentationIndex({version:1,devices:[null,{},metadata(),{...metadata('python'),runtime:'python'},
    {...metadata('invalid'),icon:'<script>'}]});
  assert.deepEqual(Object.keys(result),['registered_device']);assert.equal(result.toString,undefined);
});

test('expanded catalog keeps prototype aliases and frozen snapshots while adding canonical devices',()=>{
  const f=fixture(),source={id:'source',kind:'source',icon:'Droplets',values:{'param:pressure':201.325},ports:[],channels:[]};
  const fields=[['pressure','Pressure','kPa',1,1000,1,201.325]],parameterDefinitions={source:fields},modules=[source];
  const definitions=[{...manifest('source'),parameters:[{id:'pressure_pa',label:'Pressure',value_type:'number',default:201325,unit:{display_scale:1000}}]},
    {...manifest('closed_volume'),parameters:[{id:'volume_m3',label:'Volume',value_type:'number',default:.01,unit:{display_scale:1}}]}];
  const presentations=f.model.catalogPresentationIndex({version:1,devices:[metadata('source'),metadata('closed_volume')]});
  const before=plain(source.values);
  f.model.installBuiltinCatalog({catalog:{modules:definitions},presentations,modules,parameterDefinitions});
  assert.equal(parameterDefinitions.source,fields);assert.equal(fields[0][0],'pressure');assert.deepEqual(source.values,before);
  assert.equal(source.runtime,undefined);assert.equal(source.manifest,undefined);assert.equal(source.presentation.canvas_family,'tank');
  const added=modules.find(item=>item.id==='closed_volume');assert.ok(added);assert.equal(added.runtime,'builtin');
  assert.equal(parameterDefinitions.closed_volume[0][0],'volume_m3');assert.equal(parameterDefinitions.closed_volume[0][6],.01);
  const owner={pages:[{nodes:[{moduleId:added.id}]}]};f.state.modules=modules;f.client.pinProject(owner);
  const bound=owner.moduleSnapshots[added.id];assert.equal(bound.presentation.canvas_family,'tank');
  presentations.closed_volume.canvas_family='pump';f.model.installBuiltinCatalog({catalog:{modules:definitions},presentations,modules,parameterDefinitions});
  assert.equal(modules.length,2);assert.equal(bound.presentation.canvas_family,'tank');
});

test('catalog metadata icon wins without a hardcoded ID and known Python packages retain fallback icons',()=>{
  const f=fixture(),entry=metadata('future_storage');entry.icon='Archive';
  assert.equal(f.model.moduleFromManifest(manifest('future_storage'),undefined,entry).icon,'Archive');
  const python={...manifest('fan'),runtime:'python'};
  assert.equal(f.model.moduleFromManifest(python,undefined,metadata('fan')).icon,'Wind');
});
