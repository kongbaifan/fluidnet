import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/path-trace.js',import.meta.url),'utf8'),context);
const trace=context.window.FluidNetPathTrace,plain=value=>JSON.parse(JSON.stringify(value));
const ports=['hot_in','hot_out','cold_in','cold_out'].map(id=>({id,label:id,domain:'fluid'}));
const channels=[{id:'hot',input:'hot_in',output:'hot_out',enabled:true},{id:'cold',input:'cold_in',output:'cold_out',enabled:true}];
function fixture(){
  const definitions={HX:{ports:structuredClone(ports),channels:structuredClone(channels)},A:{ports:[{id:'out'}]},B:{ports:[{id:'in'}]},C:{ports:[{id:'out'}]}};
  return {definitions,owner:{pages:[{id:'main',name:'机房',nodes:[{id:'HX',name:'换热器'},{id:'A'},{id:'C'}],edges:[
    ['hotIn','A','out','HX','hot_in'],['hotOut','HX','hot_out','B','in'],['coldIn','C','out','HX','cold_in']]},
    {id:'other',name:'末端',nodes:[{id:'B',name:'回水'}],edges:[]}]}};
}
test('trace isolates the selected exchanger side and includes both adjacent edges across pages',()=>{
  const {definitions,owner}=fixture(),before=JSON.stringify(owner);
  const result=plain(trace.describe(owner,'HX','hot_in',n=>definitions[n.id]));
  assert.deepEqual(result.ports.map(p=>p.id),['hot_in','hot_out']);
  assert.deepEqual(result.channels.map(c=>c.id),['hot']);
  assert.deepEqual(result.connections.map(c=>c.id),['hotIn','hotOut']);
  assert.equal(result.connections[1].crossPage,true);assert.equal(result.connections[1].pageName,'末端');
  assert.equal(JSON.stringify(owner),before);
});
test('reverse endpoint selection gives same structural path without guessing current flow',()=>{
  const {definitions,owner}=fixture();
  const a=plain(trace.describe(owner,'HX','hot_in',n=>definitions[n.id]));
  const b=plain(trace.describe(owner,'HX','hot_out',n=>definitions[n.id]));
  assert.deepEqual(a.connections,b.connections);assert.deepEqual(a.ports,b.ports);
});
test('disabled channels and unbound ports never imply a connection to the other side',()=>{
  const {definitions,owner}=fixture();definitions.HX.channels[0]={...channels[0],enabled:false};
  const result=plain(trace.describe(owner,'HX','hot_in',n=>definitions[n.id]));
  assert.deepEqual(result.ports.map(p=>p.id),['hot_in']);assert.deepEqual(result.channels,[]);
  assert.deepEqual(result.connections.map(c=>c.id),['hotIn']);
});
test('frozen manifest channel declarations take precedence over altered library display data',()=>{
  const {definitions,owner}=fixture();definitions.HX.manifest={channels:[
    {id:'frozen',name:'冻结侧',input_port:'hot_in',output_port:'hot_out'}]};
  definitions.HX.channels=[{id:'wrong',input:'hot_in',output:'cold_in'}];
  const result=plain(trace.describe(owner,'HX','hot_in',n=>definitions[n.id]));
  assert.deepEqual(result.channels.map(c=>c.id),['frozen']);
  assert.deepEqual(result.connections.map(c=>c.id),['hotIn','hotOut']);
});
test('a shared explicit channel endpoint is followed but remote device internals are not',()=>{
  const {definitions,owner}=fixture();definitions.HX.channels.push({id:'declared-branch',input:'hot_out',output:'cold_out'});
  definitions.HX.channels[1].enabled=false;
  definitions.B={ports:[{id:'in'},{id:'out'}],channels:[{id:'remote',input:'in',output:'out'}]};
  owner.pages[1].edges.push(['remoteEdge','B','out','C','out']);
  const result=plain(trace.describe(owner,'HX','hot_in',n=>definitions[n.id]));
  assert.deepEqual(result.ports.map(p=>p.id),['hot_in','hot_out','cold_out']);
  assert.equal(result.connections.some(c=>c.id==='remoteEdge'),false);
});
test('invalid endpoints remain visible as errors without navigation targets',()=>{
  const {definitions,owner}=fixture();owner.pages[1].nodes=[];
  const result=trace.describe(owner,'HX','hot_in',n=>definitions[n.id]);
  assert.equal(result.connections[1].valid,false);
  const html=trace.markup(result,s=>String(s));
  assert.match(html,/连接端点已失效/);assert.doesNotMatch(html,/data-trace-destination="B:in"/);
  assert.equal(trace.describe(owner,'missing','in',n=>definitions[n.id]),null);
  assert.equal(trace.describe(owner,'HX','missing',n=>definitions[n.id]),null);
});
