import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const context=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/module-test-editor.js',import.meta.url),'utf8'),context);
const editor=context.window.ModuleTestEditor;
const definition={sdk:{capabilities:['composite.refrigeration.open.v1']},parameters:[],variables:[],channels:[]};
const conditions={host_instance_id:'D1',host_project:{name:'真实回路',instances:[{id:'D1'}],fluid:{fluid:'R134a'},connections:[]},fluid:{fluid:'R134a',phase_policy:'any'},duration_s:.1,dt_s:.1};
test('open groups use one real host case and preserve a detached host on roundtrip',()=>{
 const cases=editor.cases({testConditions:conditions},definition);
 assert.equal(cases.length,1);assert.equal(cases[0].id,'host');assert.equal(cases[0].conditions.inlet_pressure_pa,undefined);
 const events={},container={innerHTML:'',addEventListener:(name,fn)=>events[name]=fn,contains:()=>true};
 const mounted=editor.mount(container,cases,definition);
 assert.match(container.innerHTML,/真实回路/);assert.doesNotMatch(container.innerHTML,/data-condition="inlet_pressure_pa"/);
 const button={dataset:{suiteAction:'add-case'}};
 events.click({target:{closest:()=>button},preventDefault(){},stopPropagation(){}});
 const result=mounted.read();assert.equal(result.length,2);
 for(const item of result)assert.equal(JSON.stringify(item.conditions.host_project),JSON.stringify(conditions.host_project));
 result[1].conditions.host_project.name='changed';assert.equal(result[0].conditions.host_project.name,'真实回路');assert.equal(conditions.host_project.name,'真实回路');
});
test('missing host is explicit and hydraulic defaults retain their reverse/zero cases',()=>{
 const container={innerHTML:'',addEventListener(){}};
 assert.throws(()=>editor.mount(container,editor.cases({},definition),definition).read(),/缺少宿主工况/);
 const ordinary=editor.cases({},{parameters:[],channels:[]});
 assert.deepEqual(Array.from(ordinary,item=>item.id),['forward','reverse','zero']);
 assert.equal(ordinary[1].conditions.inlet_pressure_pa,120000);
 assert.equal(ordinary[2].conditions.outlet_pressure_pa,250000);
});
