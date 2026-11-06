import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function fixture() {
  const host=vm.createContext({window:{}});
  vm.runInContext(readFileSync(new URL('../frontend/cold-storage.js',import.meta.url),'utf8'),host);
  const definitions={
    custom_room:{solver_model:'cold_room',ports:[{domain:'thermal'}],variables:[{id:'state.temperature_k'}]},
    custom_compressor:{solver_model:'refrigerant_compressor',ports:[{domain:'refrigerant'}],variables:[{id:'mass_flow_kg_s'},{id:'electric_power_w'}]},
    custom_vessel:{solver_model:'saturated_vessel',ports:[{domain:'refrigerant'}],variables:[{id:'state.pressure_pa'},{id:'state.level_ratio'}]},
    custom_cascade:{solver_model:'cascade_exchanger',ports:[{domain:'refrigerant',circuit:'evaporating'},{domain:'refrigerant',circuit:'condensing'}],variables:[{id:'heat_w'},{id:'approach_k'}]},
  };
  const p={id:'Own-Project',name:'自建冷库',pages:[{nodes:[
    {id:'Room-North',name:'北库',moduleId:'custom_room'},
    {id:'Room-South',name:'南库',moduleId:'custom_room'},
    {id:'Compressor-Own',name:'压缩机',moduleId:'custom_compressor'},
    {id:'Vessel-Own',name:'循环桶',moduleId:'custom_vessel'},
    {id:'Cascade-North',name:'北侧复叠换热器',moduleId:'custom_cascade'},
    {id:'Cascade-South',name:'南侧复叠换热器',moduleId:'custom_cascade'},
  ]}],run:{history:[],status:'ready'}};
  const state={modules:[]};let dialog;
  const api=host.window.createColdStorageUI({state:()=>state,project:()=>p,
    engine:()=>({catalog:{modules:[]}}),moduleOf:n=>({manifest:definitions[n.moduleId]}),
    esc:value=>String(value??''),btn:()=>'',projectKey:()=>p.currentKey||'current',
    openDialog:(title,description,body)=>{dialog={title,description,body};},msg:()=>{},
  });
  return {api,p,definitions,dialog:()=>dialog};
}

test('modular refrigeration binds every actual room and machine without example IDs',()=>{
  const {api,p}=fixture(),bindings=JSON.parse(JSON.stringify(api.modularBindings(p)));
  assert.deepEqual(bindings.map(b=>b.key),['Room-North.state.temperature_k','Room-South.state.temperature_k',
    'Compressor-Own.mass_flow_kg_s','Compressor-Own.electric_power_w','Vessel-Own.state.pressure_pa','Vessel-Own.state.level_ratio',
    'Cascade-North.heat_w','Cascade-North.approach_k','Cascade-South.heat_w','Cascade-South.approach_k']);
  const markup=api.markup(p);
  assert.match(markup,/data-modular-cold-summary/);assert.match(markup,/北库 · 库温/);
  assert.doesNotMatch(markup,/ROOM1|NH₃\/CO₂ 两库房/);
});

test('summary converts real values and leaves missing or stale samples empty',()=>{
  const {api,p}=fixture();
  p.run={status:'completed',source:'engine',id:'run',parameterKey:'current',history:[{t:60,canonical:{
    'Room-North.state.temperature_k':255.15,'Compressor-Own.electric_power_w':2750,
    'Vessel-Own.state.pressure_pa':210000,'Vessel-Own.state.level_ratio':.4,
    'Cascade-North.heat_w':6000,'Cascade-North.approach_k':5,
    'Cascade-South.heat_w':7500,'Cascade-South.approach_k':7,
  }}]};
  let markup=api.markup(p);
  assert.match(markup,/data-modular-cold-key="Room-North.state.temperature_k">-18\.000</);
  assert.match(markup,/data-modular-cold-key="Room-South.state.temperature_k">—</);
  assert.match(markup,/data-modular-cold-key="Compressor-Own.electric_power_w">2\.750</);
  assert.match(markup,/data-modular-cold-key="Vessel-Own.state.pressure_pa">0\.210</);
  assert.match(markup,/data-modular-cold-key="Vessel-Own.state.level_ratio">40\.000</);
  assert.match(markup,/data-modular-cold-key="Cascade-North.heat_w">6\.000</);
  assert.match(markup,/data-modular-cold-key="Cascade-North.approach_k">5\.000</);
  assert.match(markup,/data-modular-cold-key="Cascade-South.heat_w">7\.500</);
  assert.match(markup,/data-modular-cold-key="Cascade-South.approach_k">7\.000</);
  p.currentKey='edited';markup=api.markup(p);
  assert.match(markup,/配置已变更/);
  assert.match(markup,/data-modular-cold-key="Room-North.state.temperature_k">—</);
});

test('blank refrigeration canvas explains the assembly without inserting devices',async()=>{
  const f=fixture();f.p.pages[0].nodes=[];f.p.modelingDomain='refrigeration';f.p.fluid='HEOS::R134a';
  assert.match(f.api.markup(f.p),/画布从空白开始/);
  await f.api.action('cs-assembly-guide',{dataset:{}});
  assert.match(f.dialog().body,/R134a/);assert.match(f.dialog().body,/低压桶第二个进口/);
  assert.match(f.dialog().body,/NH₃／CO₂/);assert.match(f.dialog().body,/两侧只交换热量/);
  assert.match(f.dialog().body,/分别选择各侧锚点/);assert.match(f.dialog().body,/任意连线并不保证/);
  assert.equal(f.p.pages[0].nodes.length,0);
});
