import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context = vm.createContext({window:{createProjectServices:()=>({})}});
vm.runInContext(readFileSync(new URL('../frontend/engine-client.js',import.meta.url),'utf8'),context);
const engine=context.window.createEngineClient({moduleOf:node=>node.definition});
const plain=value=>JSON.parse(JSON.stringify(value));
const definition=(id,model,channels=[{id:'main',input_port:'feed',output_port:'return',enabled:true}])=>({id,solver_model:model,
  ports:channels.flatMap(channel=>[{id:channel.input_port,domain:'fluid'},{id:channel.output_port,domain:'fluid'}]),channels});

test('refrigeration author overview follows the declared role and instance ID',()=>{
  const manifest={id:'cold_author',execution_role:'refrigeration.isenthalpic_throttle.v1',channels:[],
    ports:[{id:'in0',domain:'refrigerant'},{id:'out0',domain:'refrigerant'}]};
  const bindings=engine.overviewBindings({instances:[{id:'Custom-X',name:'节流',module_id:manifest.id}],modules:[manifest]});
  assert.equal(bindings.q.key,'Custom-X.mass_flow_kg_s');
  assert.equal(bindings.temperature.key,'Custom-X.out0.temperature_k');
});

test('imported builtin snapshots do not receive a Python package with null hashes',()=>{
  const owner={pages:[{nodes:[{id:'Reservoir',moduleId:'vessel'}]}],moduleSnapshots:{vessel:{id:'vessel',runtime:'builtin',
    frozen:true,version:1,manifest:{content_hash:null,definition_hash:null}}}};
  engine.pinProject(owner);
  assert.equal(owner.pages[0].nodes[0].package,undefined);
});

test('report availability uses the frozen run domain, status and used instances',()=>{
  const record={status:'completed',request:{project:{instances:[{module_id:'author'}],modules:[
    {id:'author',ports:[{domain:'refrigerant'}]},{id:'unused_water',ports:[{domain:'fluid'}]}]}}};
  assert.equal(engine.refrigerationReportAvailable(record),true);
  assert.equal(engine.refrigerationReportAvailable({...record,status:'running'}),false);
  record.request.project.thermal_couplings=[{id:'coil'}];
  assert.equal(engine.refrigerationReportAvailable(record),false);
  record.request.project.thermal_couplings=[];record.request.project.instances.push({module_id:'unused_water'});
  assert.equal(engine.refrigerationReportAvailable(record),false);
});

test('overview follows device roles and actual custom IDs, with no example-name dependency',()=>{
  const pump=definition('custom_pump','pump_curve'),valve=definition('custom_valve','valve');
  const bindings=engine.overviewBindings({instances:[
    {id:'branch-z',name:'支路',module_id:valve.id}, {id:'circulator-x',name:'泵',module_id:pump.id}],modules:[pump,valve]});
  const values=plain(engine.overviewValues(bindings,{'circulator-x.mass_flow_kg_s':2,'branch-z.mass_flow_kg_s':1,
    'circulator-x.return.pressure_pa':250000,'circulator-x.return.temperature_k':300}));
  assert.equal(values.q,2);assert.equal(values.a,1);assert.equal(values.b,null);
  assert.equal(values.pressure,250);assert.ok(Math.abs(values.temperature-26.85)<1e-10);
  assert.match(bindings.q.label,/circulator-x/);
});

test('two-channel historical snapshot uses its own port and channel contract',()=>{
  const frozen=definition('author_hx','generic',[
    {id:'hot',input_port:'hot_feed',output_port:'hot_return'},
    {id:'cold',input_port:'cold_feed',output_port:'cold_return'}]);
  const bindings=engine.overviewBindings({instances:[{id:'HeatBank',name:'换热器',module_id:frozen.id}],modules:[frozen]});
  const values=plain(engine.overviewValues(bindings,{'HeatBank.hot.mass_flow_kg_s':3,'HeatBank.cold.mass_flow_kg_s':4,
    'HeatBank.hot_return.temperature_k':320,'HeatBank.cold_return.temperature_k':290}));
  assert.equal(values.q,3);assert.equal(values.a,4);assert.equal(values.pressure,null);
  assert.ok(Math.abs(values.temperature-46.85)<1e-10);
  assert.equal(bindings.temperature.key,'HeatBank.hot_return.temperature_k');
});

test('missing or non-finite samples stay missing and thermal-only projects get no fluid placeholders',()=>{
  const module=definition('resistor','generic');
  const bindings=engine.overviewBindings({pages:[{nodes:[{id:'Loss42',name:'阻力',definition:module}]}]});
  assert.deepEqual(plain(engine.overviewValues(bindings,{'Loss42.mass_flow_kg_s':NaN,'Loss42.return.pressure_pa':null})),
    {q:null,a:null,b:null,pressure:null,temperature:null});
  assert.deepEqual(plain(engine.overviewBindings({instances:[{id:'Room',module_id:'room'}],
    modules:[{id:'room',ports:[{id:'heat',domain:'thermal'}],channels:[]}]})),{});
});

test('saved prototype channel overrides take precedence over the catalog manifest',()=>{
  const manifest=definition('author_dual','generic',[
    {id:'hot',input_port:'hot_in',output_port:'hot_out'},
    {id:'cold',input_port:'cold_in',output_port:'cold_out'}]);
  const module={...manifest,manifest,channels:[
    {id:'hot',input:'hot_in',output:'hot_out',enabled:false},
    {id:'cold',input:'cold_in',output:'cold_out',enabled:true}]};
  const bindings=engine.overviewBindings({pages:[{nodes:[{id:'Coil42',name:'盘管',definition:module}]}]});
  assert.equal(bindings.temperature.key,'Coil42.cold_out.temperature_k');
  assert.equal(bindings.a,undefined);
});
