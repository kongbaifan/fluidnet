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

test('unchanged HTTP samples do not repeatedly redraw a paused or streaming run',async()=>{
  const f=fixture();
  f.hooks.request=async path=>path.includes('/history')?{total_rows:1,rows:[]}:
    {status:'running',events:[],frame:{valid:true,time_s:61,variables:{flow:2}}};
  await f.api.pollLive(f.owner);const count=f.counts().refreshes;
  await f.api.pollLive(f.owner);await f.api.pollLive(f.owner);
  assert.equal(f.counts().refreshes,count);assert.equal(f.calls.length,6);
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

test('new run start locks its prior result and resumes only after claiming a paused creation',async()=>{
  const f=fixture('completed'),normalizing=deferred();f.hooks.normalize=()=>normalizing.promise;
  const work=f.api.liveCommand(f.owner,'run');await f.api.liveCommand(f.owner,'run');assert.equal(f.pending.size,1);
  assert.equal(f.owner.run,f.run);assert.equal(f.run.status,'solving');assert.equal(f.run.history[0],f.frame);
  assert.equal(f.api.isCreating(f.owner),true);assert.equal(f.counts().renders,1);
  normalizing.resolve({id:'canonical'});await work;
  const [,body]=f.calls.find(([p])=>p==='/runs?background=true');
  assert.equal(body.mode,'dynamic');assert.equal(body.project_revision,3);assert.equal(body.duration_s,1);
  assert.equal(body.history,'trend');assert.equal(body.start_paused,true);assert.equal(f.owner.run.id,'started');assert.equal(f.pending.size,0);
  assert.deepEqual(f.calls.filter(([p])=>p.endsWith('/command')).map(([,body])=>body.action),['resume']);
  assert.ok(f.calls.some(([p])=>p==='/runs/started/events'));
  assert.equal(f.owner.run.status,'running');assert.equal(f.api.isCreating(f.owner),false);
});

test('aborted creation responses cannot replace prior frames or report stale success',async()=>{
  const f=fixture('completed'),late=deferred(),posted=deferred(),request=f.hooks.request;
  f.hooks.request=(path,...args)=>{if(path==='/runs?background=true'){posted.resolve();return late.promise;}return request(path,...args);};
  const work=f.api.liveCommand(f.owner,'run');await posted.promise;
  f.pending.get(f.owner.id).abort();late.resolve({run_id:'cancelled-create'});await work;
  assert.equal(f.owner.run,f.run);assert.equal(f.run.status,'stopped');assert.equal(f.run.history[0],f.frame);
  assert.deepEqual(f.calls.filter(([p])=>p.endsWith('/command')).map(([path,body])=>[path,body.action]),
    [['/runs/cancelled-create/command','stop']]);
  assert.equal(f.messages.length,0);assert.equal(f.pending.size,0);
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

test('single step claims a paused creation and stays paused after its applied command',async()=>{
  const f=fixture('completed');await f.api.liveCommand(f.owner,'step');
  const [,body]=f.calls.find(([path])=>path==='/runs?background=true');assert.equal(body.start_paused,true);
  assert.deepEqual(f.calls.filter(([p])=>p.endsWith('/command')).map(([,body])=>body.action),['step']);
  assert.ok(f.calls.some(([p])=>p==='/runs/started/events'));
  assert.equal(f.owner.run.status,'paused');assert.equal(f.owner.run.runId,'started');assert.equal(f.pending.size,0);
});

test('normalization and submission failures restore the complete prior result and drafts',async()=>{
  for(const stage of ['normalize','submit']) {
    const f=fixture('completed'),entered=deferred(),late=deferred(),original=JSON.stringify(f.run);
    if(stage==='normalize')f.hooks.normalize=()=>{entered.resolve();return late.promise;};
    else f.hooks.request=()=>{entered.resolve();return late.promise;};
    const work=f.api.liveCommand(f.owner,'run');await entered.promise;
    assert.equal(f.run.status,'solving');assert.equal(f.owner.run,f.run);assert.equal(f.run.history[0],f.frame);
    // A save/export during startup still contains the previous accepted result.
    assert.equal(JSON.parse(JSON.stringify(f.state)).projects[0].run.history[0].t,60);
    late.reject(Error(stage+' failed'));await work;
    assert.equal(f.owner.run,f.run);assert.equal(JSON.stringify(f.run),original);
    assert.equal(f.node.params.heat_input_w,5000);assert.equal(f.node.draft.heat_input_w,6000);
    assert.equal(f.pending.size,0);assert.equal(f.api.isCreating(f.owner),false);
    assert.equal(f.messages.at(-1).text,stage+' failed');
  }
});

test('stop during normalization cancels startup and retains the prior result',async()=>{
  const f=fixture('completed'),late=deferred();let signal,stopped=false;
  f.hooks.normalize=(_,value)=>{signal=value;return late.promise;};
  const work=f.api.liveCommand(f.owner,'run');
  const stop=f.api.liveCommand(f.owner,'stop').then(()=>{stopped=true;});
  assert.equal(signal.aborted,true);assert.equal(f.run.status,'solving');assert.equal(stopped,false);
  late.resolve({id:'canonical'});await Promise.all([work,stop]);
  assert.equal(f.calls.length,0);assert.equal(f.pending.size,0);assert.equal(f.owner.run,f.run);
  assert.equal(f.run.status,'stopped');assert.equal(f.run.history[0],f.frame);assert.equal(f.messages.length,0);
});

test('stop during submission retains the POST, then stops its returned ID without activation',async()=>{
  const f=fixture('completed'),late=deferred(),posted=deferred(),request=f.hooks.request;
  let signal,stopped=false;
  f.hooks.request=(path,body,submittedSignal)=>{
    if(path==='/runs?background=true'){signal=submittedSignal;posted.resolve();return late.promise;}
    return request(path,body,submittedSignal);
  };
  const work=f.api.liveCommand(f.owner,'run');await posted.promise;
  const stop=f.api.liveCommand(f.owner,'stop').then(()=>{stopped=true;});
  await f.api.liveCommand(f.owner,'run');
  assert.equal(signal,undefined);assert.equal(stopped,false);assert.equal(f.pending.size,1);assert.equal(f.run.status,'solving');
  late.resolve({run_id:'late-create'});await Promise.all([work,stop]);
  assert.equal(f.calls.filter(([path])=>path==='/runs?background=true').length,1);
  assert.deepEqual(f.calls.filter(([path])=>path.endsWith('/command')).map(([path,body])=>[path,body.action]),
    [['/runs/late-create/command','stop']]);
  assert.equal(f.owner.run,f.run);assert.equal(f.run.status,'stopped');assert.equal(f.run.history[0],f.frame);
  assert.equal(f.pending.size,0);assert.equal(f.messages.length,0);
});

test('a queued cleanup stop is confirmed before the old result is unlocked',async()=>{
  const f=fixture('completed'),late=deferred(),posted=deferred(),queried=deferred(),finished=deferred();
  f.hooks.request=async(path,body)=>{
    if(path==='/runs?background=true'){posted.resolve();return late.promise;}
    if(path.endsWith('/command'))return {command_id:'stop-1',command_status:'queued'};
    if(path==='/runs/late-create'){queried.resolve();return finished.promise;}
    throw Error('unexpected '+path);
  };
  const work=f.api.liveCommand(f.owner,'run');await posted.promise;const stop=f.api.liveCommand(f.owner,'stop');
  late.resolve({run_id:'late-create'});await queried.promise;
  assert.equal(f.run.status,'solving');assert.equal(f.api.isCreating(f.owner),true);
  finished.resolve({status:'cancelled'});await Promise.all([work,stop]);
  assert.equal(f.run.status,'stopped');assert.equal(f.pending.size,0);
  assert.equal(f.calls.filter(([path])=>path.endsWith('/command')).length,1);
});

test('a late creation is stopped without touching a replacement owner or run',async()=>{
  for(const change of ['owner','run']) {
    const f=fixture('completed'),late=deferred(),posted=deferred(),request=f.hooks.request;
    f.hooks.request=(path,...args)=>{if(path==='/runs?background=true'){posted.resolve();return late.promise;}return request(path,...args);};
    const work=f.api.liveCommand(f.owner,'run');await posted.promise;
    if(change==='owner')f.state.projects=[{...f.owner,run:{id:'replacement',status:'ready',history:[],events:[]}}];
    else f.replace();
    const replacement=JSON.stringify(f.state);
    late.resolve({run_id:'detached-create'});await work;
    assert.equal(JSON.stringify(f.state),replacement);assert.equal(f.counts().persists,0);assert.equal(f.messages.length,0);
    assert.deepEqual(f.calls.filter(([path])=>path.endsWith('/command')).map(([path,body])=>[path,body.action]),
      [['/runs/detached-create/command','stop']]);
    assert.equal(f.pending.size,0);
  }
});

test('a configuration edit bypassing the UI guard cannot activate an accepted creation',async()=>{
  const f=fixture('completed'),late=deferred(),posted=deferred(),request=f.hooks.request;
  f.hooks.request=(path,...args)=>{if(path==='/runs?background=true'){posted.resolve();return late.promise;}return request(path,...args);};
  const work=f.api.liveCommand(f.owner,'run');await posted.promise;f.hooks.key=()=> 'changed';
  late.resolve({run_id:'stale-configuration'});await work;
  assert.equal(f.owner.run,f.run);assert.equal(f.run.status,'completed');assert.equal(f.run.history[0],f.frame);
  assert.deepEqual(f.calls.filter(([path])=>path.endsWith('/command')).map(([,body])=>body.action),['stop']);
  assert.match(f.messages.at(-1).text,/项目已变化/);assert.equal(f.pending.size,0);
});

test('ownership lost while activation is in flight also cleans up the created ID',async()=>{
  const f=fixture('completed'),late=deferred(),activating=deferred(),request=f.hooks.request;
  f.hooks.request=(path,body,...args)=>{
    if(path.endsWith('/command')&&body?.action==='resume'){activating.resolve();return late.promise;}
    return request(path,body,...args);
  };
  const work=f.api.liveCommand(f.owner,'run');await activating.promise;
  const replacement=f.replace(),snapshot=JSON.stringify(replacement);
  late.resolve({command_id:'command-1',command_status:'applied'});await work;
  assert.equal(JSON.stringify(replacement),snapshot);assert.equal(f.owner.run,replacement);
  assert.deepEqual(f.calls.filter(([path])=>path.endsWith('/command')).map(([,body])=>body.action),['resume','stop']);
  assert.equal(f.messages.length,0);assert.equal(f.pending.size,0);
});

test('failed cleanup retains a controllable paused ID and allows an explicit stop retry',async()=>{
  const f=fixture('completed'),late=deferred(),posted=deferred(),request=f.hooks.request;
  f.hooks.request=(path,body,...args)=>{
    if(path==='/runs?background=true'){posted.resolve();return late.promise;}
    if(path.endsWith('/command')&&body?.action==='stop')throw Error('connection unavailable');
    return request(path,body,...args);
  };
  const work=f.api.liveCommand(f.owner,'run');await posted.promise;const stop=f.api.liveCommand(f.owner,'stop');
  late.resolve({run_id:'retained-create'});await Promise.all([work,stop]);
  assert.equal(f.owner.run.id,'retained-create');assert.equal(f.owner.run.runId,'retained-create');
  assert.equal(f.owner.run.live,true);assert.equal(f.owner.run.status,'paused');
  assert.match(f.owner.run.connectionError,/retained-create.*connection unavailable/);
  assert.match(f.messages.at(-1).text,/停止.*尚未确认/);assert.equal(f.pending.size,0);
  f.hooks.request=request;await f.api.liveCommand(f.owner,'stop');
  assert.equal(f.owner.run.status,'stopped');assert.equal(f.owner.run.live,false);assert.equal(f.owner.run.runId,null);
});

test('stop during activation keeps its confirmed result when the late resume reports completion',async()=>{
  const f=fixture('completed'),late=deferred(),activating=deferred(),request=f.hooks.request;
  f.hooks.request=(path,body,...args)=>{
    if(path.endsWith('/command')&&body?.action==='resume'){activating.resolve();return late.promise;}
    return request(path,body,...args);
  };
  const work=f.api.liveCommand(f.owner,'run');await activating.promise;
  await f.api.liveCommand(f.owner,'stop');
  late.reject(Object.assign(Error('运行已结束'),{code:'RUN_ALREADY_FINISHED'}));await work;
  assert.equal(f.owner.run.status,'stopped');assert.equal(f.owner.run.live,false);assert.equal(f.owner.run.runId,null);
  assert.equal(f.messages.length,0);assert.equal(f.pending.size,0);
});
