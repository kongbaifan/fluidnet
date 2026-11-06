import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../frontend/engine-client.js',import.meta.url),'utf8');
const command=source.slice(source.indexOf('  async function liveCommand('),source.indexOf('  async function loadOverview('));
function fixture(status='completed') {
  const node={params:{heat_input_w:5000},draft:{heat_input_w:6000}};
  const frame={t:60,canonical:{'Own-Room.state.temperature_k':255.15}};
  const run={id:'archive',runId:null,live:false,status,history:[frame]},owner={id:'p',run,pages:[{nodes:[node]}]};
  const state={projects:[owner]};let writes=0,persists=0,renders=0;
  const host=vm.createContext({window:{},pending:new Map(),
    ui:{state:()=>state,persist:()=>{persists++;},render:()=>{renders++;},message:()=>{}},
    confirmedCommand:async()=>{writes++;throw Object.assign(Error('运行已结束'),{code:'RUN_ALREADY_FINISHED'});},
    pollLive:async()=>{run.live=false;run.runId=null;run.status='completed';},
  });
  vm.runInContext(readFileSync(new URL('../frontend/project-run-state.js',import.meta.url),'utf8'),host);
  host.runState=host.window.FluidNetProjectRunState;
  vm.runInContext(command,host);
  return {owner,node,run,frame,state,host,counts:()=>({writes,persists,renders}),stop:()=>host.liveCommand(owner,'stop')};
}

test('Stop after dynamic completion closes the task without discarding frames or editable drafts',async()=>{
  const f=fixture();await f.stop();
  assert.equal(f.run.status,'stopped');assert.equal(f.run.live,false);assert.equal(f.run.runId,null);
  assert.equal(f.run.id,'archive');assert.equal(f.run.history[0],f.frame);
  assert.equal(f.node.params.heat_input_w,5000);assert.equal(f.node.draft.heat_input_w,6000);
  assert.deepEqual(f.counts(),{writes:0,persists:1,renders:1});
});

test('a stale live session is released after the server confirms completion',async()=>{
  const f=fixture('running');Object.assign(f.run,{live:true,runId:'archive'});
  await f.stop();assert.equal(f.run.status,'stopped');assert.equal(f.run.live,false);
  assert.equal(f.run.history[0],f.frame);assert.equal(f.counts().writes,1);
});

test('completion of an old stop cannot change a replacement run',async()=>{
  const f=fixture('running');Object.assign(f.run,{live:true,runId:'archive'});
  const replacement={id:'new',runId:'new',live:true,status:'running',history:[]};
  f.host.pollLive=async()=>{f.owner.run=replacement;};
  await f.stop();assert.equal(f.owner.run,replacement);assert.equal(replacement.status,'running');
  assert.equal(replacement.live,true);assert.equal(f.counts().persists,0);
});
