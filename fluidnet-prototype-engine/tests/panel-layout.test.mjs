import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const host=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/panel-layout.js',import.meta.url),host);
const api=host.window.FluidNetPanelLayout,plain=x=>JSON.parse(JSON.stringify(x));
const make=()=>({id:'valve',version:1,manifest:{id:'valve',version:1,content_hash:'one',definition_hash:'two',parameters:[{id:'opening',value_type:'number'}]},
 variables:[{id:'runtime:flow',origin:'runtime',canonicalId:'flow',unit:'kg/s'},{id:'in0:TEMP',origin:'port',unit:'°C'},{id:'param:opening',origin:'parameter',param:'opening',unit:'%'}]});
const specs=[{id:'opening',value_type:'number',minimum:0,maximum:100},{id:'enabled',value_type:'boolean'},{id:'fixed',value_type:'number',minimum:null,maximum:null}];
const layout=m=>({schema:1,binding:api.binding(m),parameters:[{id:'opening',group:'调节',order:0,widget:'slider'}],results:[{id:'runtime:flow',group:'流量',order:2},{id:'in0:TEMP',group:'温度',order:1}]});
test('presentation binds exact release and fields without modifying physical contract',()=>{
 const m=make(),before=JSON.stringify(m.manifest);m.panelLayout=layout(m);
 assert.equal(api.resolved(m,specs).warning,'');assert.equal(JSON.stringify(m.manifest),before);
 const target=make();api.copy(m,target);assert.deepEqual(plain(target.panelLayout),plain(m.panelLayout));
 target.panelLayout.parameters[0].group='changed';assert.equal(m.panelLayout.parameters[0].group,'调节');
 target.manifest.definition_hash='different';assert.equal(api.resolved(target,specs).layout,null);
 assert.match(api.resolved(target,specs).warning,/默认面板/);
});
test('widget choices honor parameter types and explicit finite ranges',()=>{
 assert.deepEqual(plain(api.widgets(specs[0])),['number','slider','display']);
 assert.deepEqual(plain(api.widgets(specs[1])),['switch','display']);
 assert.deepEqual(plain(api.widgets(specs[2])),['number','display']);
 const m=make(),bad=layout(m);bad.parameters[0].widget='switch';assert.throws(()=>api.validate(bad,m,specs),/控件/);
 bad.parameters[0].widget='slider';bad.results.push({...bad.results[0]});assert.throws(()=>api.validate(bad,m,specs),/重复/);
});
test('groups preserve explicit field order and unknown output cannot become a fabricated result',()=>{
 const m=make(),v=layout(m);assert.deepEqual(plain(api.groups(v.results)).map(g=>g.name),['温度','流量']);
 v.results[0].id='invented';assert.throws(()=>api.validate(v,m,specs),/字段/);
 assert.equal(api.resolved(make(),specs).layout,null);
});
