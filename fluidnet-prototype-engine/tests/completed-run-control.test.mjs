import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fixture,deferred} from './run-commands-fixture.mjs';

test('Stop after dynamic completion closes the task without discarding frames or editable drafts',async()=>{
  const f=fixture('completed');await f.api.liveCommand(f.owner,'stop');
  assert.equal(f.run.status,'stopped');assert.equal(f.run.live,false);assert.equal(f.run.runId,null);
  assert.equal(f.run.id,'archive');assert.equal(f.run.history[0],f.frame);
  assert.equal(f.node.params.heat_input_w,5000);assert.equal(f.node.draft.heat_input_w,6000);
  assert.deepEqual(f.counts(),{persists:1,renders:1,refreshes:0,prepared:0});assert.equal(f.calls.length,0);
});

test('a stale live session is released after the server confirms completion',async()=>{
  const f=fixture();
  f.hooks.request=async path=>{
    if(path.endsWith('/command'))throw Object.assign(Error('运行已结束'),{code:'RUN_ALREADY_FINISHED'});
    if(path.includes('/history'))return {total_rows:1,rows:[]};
    return {status:'completed',events:[],frame:null};
  };
  await f.api.liveCommand(f.owner,'stop');assert.equal(f.run.status,'stopped');assert.equal(f.run.live,false);
  assert.equal(f.run.history[0],f.frame);assert.equal(f.calls.filter(([path])=>path.endsWith('/command')).length,1);
});

test('completion of an old stop cannot change a replacement run or display a stale error',async()=>{
  const f=fixture(),response=deferred(),queried=deferred();
  f.hooks.request=async path=>{
    if(path.endsWith('/command'))throw Object.assign(Error('运行已结束'),{code:'RUN_ALREADY_FINISHED'});
    queried.resolve();return response.promise;
  };
  const work=f.api.liveCommand(f.owner,'stop');await queried.promise;const replacement=f.replace();
  response.resolve({status:'completed',events:[],frame:null});await work;
  assert.equal(f.owner.run,replacement);assert.equal(replacement.status,'running');assert.equal(replacement.live,true);
  assert.equal(f.counts().persists,0);assert.equal(f.messages.length,0);
});
