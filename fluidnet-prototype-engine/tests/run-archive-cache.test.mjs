import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context=vm.createContext({window:{createProjectServices:()=>({})}});
vm.runInContext(readFileSync(new URL('../frontend/project-model.js',import.meta.url),'utf8'),context);
vm.runInContext(readFileSync(new URL('../frontend/project-run-state.js',import.meta.url),'utf8'),context);
vm.runInContext(readFileSync(new URL('../frontend/engine-client.js',import.meta.url),'utf8'),context);
const {archiveCacheMetadata}=context.window.createEngineClient({});
const plain=value=>JSON.parse(JSON.stringify(value));
const record=()=>({id:'run-a',total_rows:81,persisted_rows:81,persisted_at:'2026-10-30T10:00:00Z',
  frame:{time_s:2400,variables:{'Room.state.temperature_k':299.15}}});

test('only a matching persisted run covering all fetched rows authorizes a local cache',()=>{
  const saved=record(),before=plain(saved);
  assert.deepEqual(plain(archiveCacheMetadata('run-a',saved,81)),
    {id:'run-a',rows:81,time_s:2400,persisted_at:saved.persisted_at});
  assert.deepEqual(saved,before);
  assert.equal(archiveCacheMetadata('other-run',saved,81),null);
  assert.equal(archiveCacheMetadata('',saved,81),null);
});

test('incomplete asynchronous persistence cannot authorize removal of newer frames',()=>{
  const saved=record();saved.persisted_rows=80;
  assert.equal(archiveCacheMetadata('run-a',saved,81),null);
  // Even if /history still exposed 80 rows, its newer record frame is not durable.
  assert.equal(archiveCacheMetadata('run-a',saved,80),null);
  saved.persisted_rows=81;
  assert.equal(archiveCacheMetadata('run-a',saved,82),null);
  assert.equal(archiveCacheMetadata('run-a',saved,81).rows,81);
});

test('nonpersistent servers and legacy records without archive receipts retain their local results',()=>{
  for(const missing of ['persisted_at','persisted_rows','total_rows','frame']){
    const saved=record();delete saved[missing];
    assert.equal(archiveCacheMetadata('run-a',saved,81),null,missing);
  }
  for(const persisted_at of [null,'', '   ',false]){
    assert.equal(archiveCacheMetadata('run-a',{...record(),persisted_at},81),null);
  }
});

test('invalid row counts and frame times never authorize local cache trimming',()=>{
  for(const rows of [0,-1,1.5,NaN,Infinity,'81',undefined]){
    assert.equal(archiveCacheMetadata('run-a',record(),rows),null);
  }
  for(const time_s of [-1,NaN,Infinity,'2400',null]){
    assert.equal(archiveCacheMetadata('run-a',{...record(),frame:{time_s}},81),null);
  }
  for(const count of [NaN,Infinity,'81',true]){
    assert.equal(archiveCacheMetadata('run-a',{...record(),persisted_rows:count},81),null);
    assert.equal(archiveCacheMetadata('run-a',{...record(),total_rows:count},81),null);
  }
});

test('a persisted initial frame and an acknowledged live prefix can retain their exact boundary',()=>{
  const saved={...record(),status:'running',total_rows:1,persisted_rows:1,frame:{time_s:0}};
  assert.deepEqual(plain(archiveCacheMetadata('run-a',saved,1)),
    {id:'run-a',rows:1,time_s:0,persisted_at:saved.persisted_at});
});
