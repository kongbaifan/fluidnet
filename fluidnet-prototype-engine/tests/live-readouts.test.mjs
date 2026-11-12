import {test} from 'node:test';
import assert from 'node:assert/strict';
import {FluidNetLiveReadouts} from '../frontend/live-readouts.js';
import {FluidNetProjectRunState as runState} from '../frontend/project-run-state.js';

const frame=(sequence,revision=0,time=sequence/20)=>({sequence,parameter_revision:revision,time_s:time,valid:true,full:true,
  variables:{flow:sequence},diagnostics:[],metrics:{}});
const row=f=>({t:f.time_s,sequence:f.sequence,parameterRevision:f.parameter_revision,valid:f.valid,partial:f.full===false,canonical:f.variables,q:f.variables.flow});
function fixture({supported=true,secret=''}={}) {
  const run={id:'run',runId:'run',live:true,status:'running',time:0,history:[],offset:12,events:[],archiveCache:{rows:12}};
  const owner={id:'p',run,params:{opening:.8},draft:{opening:.5},moduleSnapshots:{valve:{version:2}}};
  const other={id:'other',run:{...run,id:'other-run',runId:'other-run',history:[]}};
  const state={activeProject:'p',projects:[owner,other]},sockets=[],paints=new Map(),refreshed=[],polls=[];
  let time=0,serial=0;
  const api=FluidNetLiveReadouts.create({state:()=>state,runState,rowFromFrame:(_,f)=>row(f),refresh:p=>refreshed.push(p),
    poll:p=>{polls.push(p);return Promise.resolve();},supported:()=>supported,token:()=>secret,location:()=> 'https://engine.test/#workbench',now:()=>time,
    schedule:callback=>{const id=++serial;paints.set(id,callback);return id;},cancelScheduled:id=>paints.delete(id),
    connect:(url,protocols)=>{const socket={url,protocols,readyState:1,closed:0,close(){this.closed++;this.readyState=3;},
      send(data){this.onmessage?.({data:JSON.stringify(data)});}};sockets.push(socket);return socket;}});
  const flush=()=>{const callbacks=[...paints.values()];paints.clear();for(const callback of callbacks)callback();};
  const send=(f,socket=sockets.at(-1))=>socket.send({type:'frame',status:'running',frame:f});
  return {api,state,owner,other,run,sockets,refreshed,polls,paints,flush,send,advance:ms=>{time+=ms;}};
}

test('one current-project authenticated stream coalesces queued frames without writing history or drafts',()=>{
  const f=fixture({secret:'fn_example'}),history=f.run.history,archive=f.run.archiveCache;
  const unchanged=JSON.stringify([f.owner.params,f.owner.draft,f.owner.moduleSnapshots]);
  f.api.sync();f.api.sync();assert.equal(f.sockets.length,1);
  const socket=f.sockets[0],url=new URL(socket.url);
  assert.equal(url.protocol,'wss:');assert.equal(url.pathname,'/api/v1/runs/run/stream');
  assert.equal(url.searchParams.get('full_frame'),'true');assert.equal(url.searchParams.get('interval_ms'),'50');
  assert.deepEqual(socket.protocols,['fluidnet.bearer.fn_example']);assert.doesNotMatch(socket.url,/fn_example/);
  f.send(frame(1));f.send(frame(2));f.send(frame(3));assert.equal(f.paints.size,1);f.flush();
  assert.equal(f.refreshed.length,1);assert.equal(f.run.latestFull.sequence,3);assert.equal(f.run.values.q,3);
  assert.equal(f.run.history,history);assert.equal(history.length,0);assert.equal(f.run.offset,12);assert.equal(f.run.archiveCache,archive);
  assert.equal(JSON.stringify([f.owner.params,f.owner.draft,f.owner.moduleSnapshots]),unchanged);
});

test('switching projects closes the prior stream and ignores late events before or after sync',()=>{
  const f=fixture();f.api.sync();const old=f.sockets[0],late=old.onmessage;
  f.send(frame(1));f.state.activeProject='other';late({data:JSON.stringify({type:'frame',frame:frame(2)})});f.flush();
  assert.equal(f.run.latestFull,undefined);f.api.sync();assert.equal(old.closed,1);
  assert.match(f.sockets[1].url,/other-run\/stream/);
  late({data:JSON.stringify({type:'frame',frame:frame(3)})});f.flush();assert.equal(f.refreshed.length,0);
});

test('reused IDs cannot transfer a stream to a replacement project or run object',()=>{
  for(const replace of ['run','owner']) {
    const f=fixture();f.api.sync();const old=f.sockets[0],late=old.onmessage;
    if(replace==='run')f.owner.run={...f.run,history:[]};
    else f.state.projects=[{...f.owner,run:{...f.run,history:[]}}];
    f.api.sync();late({data:JSON.stringify({type:'frame',frame:frame(2)})});f.flush();
    assert.equal(old.closed,1);assert.equal(f.sockets.length,2);assert.equal(f.refreshed.length,0);
  }
});

test('duplicate and older sequence or revision samples do not repaint or regress accepted values',()=>{
  const f=fixture();f.api.sync();f.send(frame(10,2,1));f.flush();
  for(const candidate of [frame(10,2,1),frame(9,3,1),frame(11,1,1.1)]){f.send(candidate);f.flush();}
  assert.equal(f.refreshed.length,1);assert.equal(f.run.latestFull.sequence,10);assert.equal(f.run.latestFull.parameterRevision,2);
  f.send(frame(10,3,1));f.flush();assert.equal(f.refreshed.length,2);assert.equal(f.run.latestFull.parameterRevision,3);
  f.send(frame(12,3,1.2));f.send(frame(11,3,1.1));f.flush();assert.equal(f.run.latestFull.sequence,12);
});

test('slow HTTP results after a streamed parameter revision cannot roll readouts or time back',()=>{
  const f=fixture();f.api.sync();f.send(frame(10,3,1));f.flush();
  runState.mergeLive(f.run,{status:'running',events:[],frame:frame(9,2,.9)},[row(frame(9,2,.9))],
    {totalRows:13,latest:row(frame(9,2,.9))});
  assert.equal(f.run.latestFull.sequence,10);assert.equal(f.run.latestFull.parameterRevision,3);assert.equal(f.run.values.q,10);assert.equal(f.run.time,1);
  assert.equal(f.run.history.length,1);assert.equal(f.run.history[0].sequence,9);
  runState.mergeLive(f.run,{status:'running',events:[],frame:frame(11,2,1)},[],{totalRows:13,latest:row(frame(11,2,1))});
  assert.equal(f.run.latestFull.sequence,10);assert.equal(f.run.values.q,10);
});

test('stream cache never completes partial HTTP history and legitimate older revisions remain',()=>{
  const f=fixture();f.api.sync();f.send(frame(10,3,1));f.flush();const streamed=f.run.latestFull;
  const previous=row(frame(8,1,.8)),partial={...row(frame(10,2,1)),partial:true};
  runState.mergeLive(f.run,{status:'running',events:[],frame:frame(9,2,.9)},[previous,partial],
    {totalRows:14,latest:row(frame(9,2,.9))});
  assert.equal(f.run.history.length,2);assert.equal(f.run.history[0],previous);
  assert.equal(f.run.history.at(-1),partial);assert.equal(partial.partial,true);
  assert.equal(f.run.history.includes(streamed),false);assert.equal(f.run.latestFull,streamed);
  assert.equal(f.run.values.q,10);assert.equal(f.run.time,1);
  const realHTTP=row(frame(10,3,1));
  runState.mergeLive(f.run,{status:'running',events:[],frame:frame(10,3,1)},[],{totalRows:14,latest:realHTTP});
  assert.equal(f.run.history.at(-1),realHTTP);assert.equal(f.run.history.includes(streamed),false);
});

test('an impossible later HTTP frame with an older revision cannot advance displayed time or values',()=>{
  const f=fixture();f.api.sync();f.send(frame(10,3,1));f.flush();
  const impossible={...row(frame(11,2,1.1)),q:99};
  runState.mergeLive(f.run,{status:'running',events:[],frame:frame(11,2,1.1)},[row(frame(9,2,.9)),impossible],
    {totalRows:14,latest:impossible});
  assert.equal(f.run.history.length,1);assert.equal(f.run.history[0].parameterRevision,2);
  assert.equal(runState.completeRow(f.run).parameterRevision,3);assert.equal(f.run.time,1);assert.equal(f.run.values.q,10);
});

test('invalid, partial or malformed frames never become effective readouts',()=>{
  const f=fixture();f.api.sync();f.send(frame(1));f.flush();
  for(const patch of [{valid:false},{full:false},{sequence:null},{time_s:null},{variables:null}]){f.send({...frame(2),...patch});f.flush();}
  f.sockets[0].send({type:'frame',status:'failed',frame:frame(3)});f.flush();
  assert.equal(f.refreshed.length,1);assert.equal(f.run.latestFull.sequence,1);
});

test('socket failure retries are bounded and optional streaming never changes the HTTP run state',()=>{
  const f=fixture();f.api.sync();
  for(let attempt=0;attempt<4;attempt++){
    const socket=f.sockets.at(-1);socket.onerror();f.advance(6000);f.api.sync();
  }
  assert.equal(f.sockets.length,4);assert.equal(f.run.status,'running');assert.equal(f.run.runId,'run');assert.equal(f.run.connectionError,undefined);
  f.advance(60000);f.api.sync();assert.equal(f.sockets.length,4);
  const absent=fixture({supported:false});absent.api.sync();assert.equal(absent.sockets.length,0);assert.equal(absent.run.live,true);
});

test('legacy protocol falls back without reconnect loops and end delegates terminal handling to HTTP',async()=>{
  const old=fixture();old.api.sync();old.sockets[0].send({type:'frame',values:{flow:3},sequence:3});
  old.advance(60000);old.api.sync();assert.equal(old.sockets.length,1);assert.equal(old.sockets[0].closed,1);assert.equal(old.run.latestFull,undefined);
  const f=fixture();f.api.sync();f.sockets[0].send({type:'end',status:'completed'});await Promise.resolve();
  assert.equal(f.polls[0],f.owner);assert.equal(f.run.status,'running');assert.equal(f.run.live,true);
  f.api.sync();assert.equal(f.sockets.length,1);
});

test('stop and page disposal close connections and discard scheduled work',()=>{
  for(const operation of ['stop','dispose']){
    const f=fixture();f.api.sync();f.send(frame(1));
    if(operation==='stop'){f.run.live=false;f.run.runId=null;f.run.status='stopped';f.api.sync();}else f.api.dispose();
    f.flush();assert.equal(f.sockets[0].closed,1);assert.equal(f.refreshed.length,0);
    if(operation==='dispose'){f.api.sync();assert.equal(f.sockets.length,1);}
  }
});
