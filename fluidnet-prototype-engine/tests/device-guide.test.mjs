import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const host=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/device-guide.js',import.meta.url),host);
const guide=host.window.FluidNetDeviceGuide,plain=v=>JSON.parse(JSON.stringify(v));
const device=id=>({id,kind:id,runtime:'builtin',ports:[{id:'in0',label:'自定义入口'},{id:'out0',label:'出口'}],
  variables:[{id:'in0:FLOW',origin:'port',port:'in0',label:'入口流量',unit:'kg/s',type:'double'},
    {id:'in0:PRE',origin:'port',port:'in0',unit:'MPa',type:'double'},
    {id:'out0:PRE',origin:'port',port:'out0',unit:'MPa',type:'double'}]});

test('guidance is limited to reviewed builtins and never inferred from a Python name or shape',()=>{
  for(const id of ['pump','valve','pipe','exchanger','storage_room','unit_cooler','condensing_unit'])assert.ok(guide.get(device(id)));
  assert.equal(guide.get({...device('pump'),runtime:'python'}),null);
  assert.equal(guide.get({...device('pump'),manifest:{runtime:'python'}}),null);
  assert.equal(guide.get({...device('custom_pump'),kind:'pump'}),null);
  assert.equal(guide.get(device('cold_room')),null);
});

test('common parameters follow canonical or legacy identities without dropping advanced fields',()=>{
  for(const ids of [['speed','efficiency','head_curve'],['speed_ratio','efficiency_ratio','head_curve']]){
    const m=device('pump'),specs=ids.map(id=>({id})),before=plain(specs),groups=guide.parameters(m,specs);
    assert.equal(groups.common[0].id,ids[0]);assert.deepEqual(plain(groups.other.map(p=>p.id)),ids.slice(1));assert.deepEqual(specs,before);
  }
  const specs=['length','diameter','roughness_m','heatLoss','cells'].map(id=>({id}));
  assert.deepEqual(plain(guide.parameters(device('pipe'),specs).common.map(p=>p.id)),['length','diameter','roughness_m']);
});

test('extra metrics require declared output and matching units and cannot invent missing observations',()=>{
  const m=device('pump'),definition={variables:[{id:'shaft_power_w',source:'derived',unit:{canonical_unit:'W'}}]};
  const before=plain(m),metrics=guide.results(m,definition),shaft=metrics.find(r=>r.variable.canonicalId==='shaft_power_w');
  assert.equal(shaft.variable.unit,'kW');assert.equal(shaft.variable.unitSpec.display_scale,1000);
  assert.equal(shaft.variable.origin,'runtime');assert.deepEqual(plain(m),before);assert.equal(shaft.variable.value,undefined);
  assert.equal(guide.results(m,{variables:[]}).some(r=>r.variable.canonicalId==='shaft_power_w'),false);
  definition.variables[0].source='parameter';assert.equal(guide.results(m,definition).length,3);
  definition.variables[0].source='derived';definition.variables[0].unit.canonical_unit='Pa';assert.equal(guide.results(m,definition).length,3);
});

test('help retains user port labels and escapes labels rather than altering device definitions',()=>{
  const m=device('valve');m.ports[0].label='<自定义入口>';const before=plain(m);
  const html=guide.markup(m,s=>String(s).replaceAll('<','&lt;'),true);
  assert.match(html,/&lt;自定义入口>/);assert.match(html,/80% 表示开度 0.8/);assert.deepEqual(m,before);
});

test('cold store readings preserve temperature offsets, power scales and explicit state labels',()=>{
  const definitions={storage_room:[['state.temperature_k','K'],['state.goods_temperature_k','K'],['cooling_power_w','W'],['net_heat_w','W']],
    unit_cooler:[['state.mode','1'],['state.fan_running','1'],['refrigerant_heat_w','W'],['heater_power_w','W']],
    condensing_unit:[['state.running','1'],['state.switch_blocked','1'],['cooling_power_w','W'],['electric_power_w','W'],['evaporating_temperature_k','K'],['condensing_temperature_k','K']]};
  for(const [id,specs] of Object.entries(definitions)){
    const definition={variables:specs.map(([id,unit])=>({id,source:id.startsWith('state.')?'state':'derived',unit:{canonical_unit:unit}}))};
    const metrics=guide.results(device(id),definition);assert.equal(metrics.length,specs.length);
    for(const {variable:v} of metrics){
      const canonical=specs.find(s=>s[0]===v.canonicalId)[1];
      assert.equal(v.unitSpec.display_scale,canonical==='W'?1000:1);
      assert.equal(v.unitSpec.display_offset,canonical==='K'?-273.15:0);
    }
    if(id==='unit_cooler')assert.equal(metrics[0].variable.valueLabels[2],'滴水等待');
    if(id==='condensing_unit')assert.equal(metrics[0].variable.valueLabels[0],'停止');
  }
  assert.match(guide.get(device('storage_room')).hints.setpoint_temperature_k,/不会自动启停/);
});
