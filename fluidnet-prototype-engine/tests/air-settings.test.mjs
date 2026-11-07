import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const host=vm.createContext({window:{},clearTimeout});
loadFrontend(new URL('../frontend/air-side.js',import.meta.url),host);
function fixture(options={contract_version:1,max_iterations:123,relaxation:.65}){
 let dialog,dirty=0,persisted=0;
 const project={id:'p',run:{live:false},pages:[],solver:{duration:1,dt:.1,mode:'dynamic'},
  solverOptions:{moist_air:!!options,moist_air_options:options},airSideView:{reference_pressure_pa:101325,selected_instance_ids:[]}};
 const feature=host.window.createAirSideUI({esc:String,btn:()=>'',msg:()=>{},state:()=>({}),project:()=>project,
  engine:()=>({}),ui:()=>({route:'air'}),openDialog:(title,text,html,submit)=>{dialog={html,submit};},
  markDirty:()=>dirty++,persist:()=>persisted++,render:()=>{}});
 return {feature,project,get:()=>dialog,effects:()=>({dirty,persisted})};
}
const valid={enabled:'on',pressure:'101.325',duration:'1',dt:'.1',mode:'dynamic',maxIterations:'400'};
test('moist settings expose the existing backend iteration limit and preserve other options',async()=>{
 const f=fixture();await f.feature.action('air-config');
 assert.match(f.get().html,/name="maxIterations"[^>]*value="123"[^>]*min="1" max="500"/);
 f.get().submit(valid);
 assert.equal(f.project.solverOptions.moist_air_options.max_iterations,400);
 assert.equal(f.project.solverOptions.moist_air_options.relaxation,.65);
 assert.deepEqual(f.effects(),{dirty:1,persisted:1});
});
test('invalid iteration limits reject before mutating the physical configuration',async()=>{
 for(const value of ['', '0', '501', '2.5', 'NaN', 'Infinity']){
  const f=fixture();await f.feature.action('air-config');const before=JSON.stringify(f.project);
  assert.throws(()=>f.get().submit({...valid,maxIterations:value}),/1–500/);
  assert.equal(JSON.stringify(f.project),before);assert.deepEqual(f.effects(),{dirty:0,persisted:0});
 }
});
test('new settings start at the contract default and accept boundary values',async()=>{
 for(const value of ['1','500']){
  const f=fixture(null);await f.feature.action('air-config');assert.match(f.get().html,/name="maxIterations"[^>]*value="60"/);
  f.get().submit({...valid,maxIterations:value});assert.equal(f.project.solverOptions.moist_air_options.max_iterations,Number(value));
 }
});
