import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const host=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/action-router.js',import.meta.url),'utf8'),host);
const create=host.window.FluidNetActionRouter.create;
test('exact feature actions win over broad prefixes and unknown actions fall through',()=>{
  const calls=[],router=create(error=>{throw error;});router.prefix('canvas-',()=>calls.push('display'));router.action('canvas-tab',()=>calls.push('navigation'));
  assert.equal(router.dispatch('canvas-tab',{}),true);assert.deepEqual(calls,['navigation']);assert.equal(router.dispatch('unowned',{}),false);
});
test('a feature may decline an action without swallowing another feature',()=>{
  const calls=[],router=create(()=>{});router.prefix('canvas-',()=>{calls.push('canvas');return false;});router.prefix('canvas-view-',()=>{calls.push('view');return false;});
  assert.equal(router.dispatch('canvas-view-other',{}),false);assert.deepEqual(calls,['view','canvas']);
});
test('registration rejects duplicates and disposal removes only its original action',()=>{
  const router=create(()=>{}),remove=router.action('save',()=>{});assert.throws(()=>router.action('save',()=>{}),/重复/);remove();
  router.action('save',()=>{});remove();assert.equal(router.dispatch('save'),true);assert.throws(()=>router.prefix('',()=>{}),/无效/);
});
test('sync errors and rejected async actions are reported exactly once',async()=>{
  const errors=[],router=create(error=>errors.push(error.message));router.action('sync',()=>{throw Error('sync failure');});router.action('async',async()=>{throw Error('async failure');});
  assert.equal(router.dispatch('sync'),true);assert.equal(router.dispatch('async'),true);await Promise.resolve();assert.deepEqual(errors,['sync failure','async failure']);
});
