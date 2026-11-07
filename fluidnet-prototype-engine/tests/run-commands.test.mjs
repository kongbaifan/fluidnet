import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fixture,deferred} from './run-commands-fixture.mjs';

test('concurrent polls share one request and refresh only current accepted frames',async()=>{
  const f=fixture(),response=deferred(),request=f.hooks.request;
  f.hooks.request=path=>path==='/runs/archive'?response.promise:request(path);
  const one=f.api.pollLive(f.owner),two=f.api.pollLive(f.owner);
  assert.equal(f.calls.length,1);response.resolve({status:'running',events:[],frame:null});
  await Promise.all([one,two]);assert.equal(f.calls.length,2);assert.equal(f.run.history.length,2);
  assert.equal(f.counts().refreshes,1);assert.equal(f.counts().renders,0);
  await f.api.pollLive(f.owner);assert.equal(f.calls.length,4);
});

test('a replacement run can poll while the previous run is unresolved, including reused run IDs',async()=>{
  const f=fixture(),late=deferred(),request=f.hooks.request;let count=0;
  f.hooks.request=path=>path==='/runs/archive'&&count++===0?late.promise:request(path);
  const old=f.api.pollLive(f.owner),replacement=f.replace();replacement.id='archive';replacement.runId='archive';
  await f.api.pollLive(f.owner);assert.equal(replacement.history.at(-1).t,61);
  const accepted=JSON.stringify(replacement);late.resolve({status:'completed',events:[],frame:null});await old;
  assert.equal(JSON.stringify(replacement),accepted);assert.equal(f.run.history.length,1);assert.equal(f.messages.length,0);
});

test('late poll rejection neither marks a replacement disconnected nor emits its error',async()=>{
  const f=fixture(),late=deferred();f.hooks.request=()=>late.promise;
  const old=f.api.pollLive(f.owner),replacement=f.replace();late.reject(Error('old connection failed'));await old;
  assert.equal(replacement.connectionError,undefined);assert.equal(f.messages.length,0);
});

test('confirmed command awaits an existing poll before handing applied receipt to its caller',async()=>{
  const f=fixture(),pollResponse=deferred(),eventRead=deferred(),request=f.hooks.request;
  f.hooks.request=path=>{
    if(path==='/runs/archive')return pollResponse.promise;
    if(path.endsWith('/events'))eventRead.resolve();
    return request(path);
  };
  const poll=f.api.pollLive(f.owner);let accepted=false;
  const command=f.api.confirmedCommand(f.owner,{action:'pause'}).then(()=>{accepted=true;});
  await eventRead.promise;await Promise.resolve();assert.equal(accepted,false);
  pollResponse.resolve({status:'paused',events:[],frame:null});await Promise.all([poll,command]);
  assert.equal(accepted,true);assert.equal(f.run.status,'paused');assert.equal(f.run.history.at(-1).t,61);
});

test('command receipt and event responses require original project and run ownership',async()=>{
  for(const stage of ['receipt','event']) {
    const f=fixture(),late=deferred(),entered=deferred(),request=f.hooks.request;
    f.hooks.request=path=>{
      if(path.endsWith(stage==='receipt'?'/command':'/events')){entered.resolve();return late.promise;}
      return request(path);
    };
    const command=f.api.confirmedCommand(f.owner,{action:'write',values:{flow:3}});
    await entered.promise;const replacement=f.replace();
    late.resolve(stage==='receipt'?{command_id:'command-1'}:{events:[{command_id:'command-1',command_status:'applied'}]});
    await assert.rejects(command,{name:'AbortError'});assert.equal(f.owner.run,replacement);assert.equal(f.counts().refreshes,0);
  }
});

test('a rejected command returns its reason without accepting frames or parameters',async()=>{
  const f=fixture();f.hooks.request=async()=>({command_id:'command-1',command_status:'rejected',message:'out of range'});
  await assert.rejects(f.api.confirmedCommand(f.owner,{action:'write'}),/out of range/);
  assert.equal(f.node.params.heat_input_w,5000);assert.equal(f.calls.length,1);assert.equal(f.counts().persists,0);
});

test('command polling is bounded and does not retry the submitted command',async()=>{
  const f=fixture();let delays=0;
  f.hooks.request=async path=>path.endsWith('/command')?{command_id:'command-1',command_status:'queued'}:{events:[]};
  f.hooks.delay=async()=>{delays++;};
  await assert.rejects(f.api.confirmedCommand(f.owner,{action:'pause'}),/尚未确认生效/);
  assert.equal(f.calls.filter(([p])=>p.endsWith('/command')).length,1);assert.equal(delays,200);
});

test('overview requests are shared and late errors cannot overwrite the new run cache',async()=>{
  const f=fixture(),late=deferred();f.run.source='engine';f.hooks.request=()=>late.promise;
  const one=f.api.loadOverview(f.owner),two=f.api.loadOverview(f.owner);assert.equal(f.calls.length,1);
  f.replace();late.reject(Error('old overview unavailable'));await Promise.all([one,two]);
  assert.equal(f.api.overview('archive'),undefined);assert.equal(f.counts().refreshes,0);
});

test('a failed current overview records fallback without destroying window history',async()=>{
  const f=fixture();f.run.source='engine';f.hooks.request=async()=>{throw Error('retained out');};
  assert.equal(await f.api.loadOverview(f.owner),null);assert.equal(f.api.overview('archive').error,'retained out');
  assert.equal(f.run.history[0],f.frame);
});

test('new run start is single flight and preserves the command payload contract',async()=>{
  const f=fixture('completed'),normalizing=deferred();f.hooks.normalize=()=>normalizing.promise;
  const work=f.api.liveCommand(f.owner,'run');await f.api.liveCommand(f.owner,'run');assert.equal(f.pending.size,1);
  normalizing.resolve({id:'canonical'});await work;
  const [,body]=f.calls.find(([p])=>p==='/runs?background=true');
  assert.equal(body.mode,'dynamic');assert.equal(body.project_revision,3);assert.equal(body.duration_s,1);
  assert.equal(body.history,'trend');assert.equal(body.start_paused,false);assert.equal(f.owner.run.id,'started');assert.equal(f.pending.size,0);
});

test('aborted creation responses cannot replace prior frames or report stale success',async()=>{
  const f=fixture('completed'),late=deferred(),posted=deferred();
  f.hooks.request=()=>{posted.resolve();return late.promise;};
  const work=f.api.liveCommand(f.owner,'run');await posted.promise;
  f.pending.get(f.owner.id).abort();late.resolve({run_id:'cancelled-create'});await work;
  assert.equal(f.owner.run,f.run);assert.equal(f.counts().persists,0);assert.equal(f.messages.length,0);assert.equal(f.pending.size,0);
});

test('replaced owners and parameter edits during normalization cannot start a new run',async()=>{
  for(const change of ['owner','parameters']) {
    const f=fixture('completed'),late=deferred();f.hooks.normalize=()=>late.promise;
    const work=f.api.liveCommand(f.owner,'run');
    if(change==='owner')f.state.projects=[];else f.hooks.key=()=> 'changed';
    late.resolve({id:'canonical'});await work;assert.equal(f.calls.length,0);assert.equal(f.pending.size,0);
    assert.equal(f.messages.length,change==='owner'?0:1);
  }
});
