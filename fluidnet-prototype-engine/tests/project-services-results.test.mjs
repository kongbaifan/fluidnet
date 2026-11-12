import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {loadFrontend} from './frontend-module-loader.mjs';
import {deferred} from './run-commands-fixture.mjs';

function fixture(){
  const host=vm.createContext({window:{}});loadFrontend(new URL('../frontend/project-services.js',import.meta.url),host);
  let workspace={activeProject:'original',projects:[]};
  const calls=[],shown=[],blocked=new Map();
  const service=host.window.createProjectServices({health:()=>({}),
    ui:{state:()=>workspace,showArchive:(record,overview)=>shown.push({id:record.id,overview}),archives:()=>{}},
    request:async path=>{
      calls.push(path);if(blocked.has(path))return blocked.get(path).promise;
      if(path==='/runs')return {runs:[]};
      if(path.endsWith('/overview'))return {rows:[{source:path.split('/')[2]}]};
      return {id:path.split('/')[2]};
    }});
  return {service,calls,shown,blocked,state:()=>workspace,replace:()=>{workspace={activeProject:'original',projects:[]};}};
}

test('the latest archive selection owns presentation even when the earlier overview arrives last',async()=>{
  const f=fixture(),late=deferred();f.blocked.set('/runs/first/overview',late);
  const first=f.service.openArchive('first');
  while(!f.calls.includes('/runs/first/overview'))await Promise.resolve();
  await f.service.openArchive('second');late.resolve({rows:[{source:'first'}]});await first;
  assert.deepEqual(f.shown.map(item=>item.id),['second']);
});

test('archive responses cannot attach to a replaced workspace or another selected project',async()=>{
  for(const replacement of ['workspace','project']){
    const f=fixture(),late=deferred();f.blocked.set('/runs/first/overview',late);
    const first=f.service.openArchive('first');
    while(!f.calls.includes('/runs/first/overview'))await Promise.resolve();
    if(replacement==='workspace')f.replace();else f.state().activeProject='another';
    late.resolve({rows:[]});await first;assert.equal(f.shown.length,0);
  }
});

test('obsolete archive errors stay silent while the current selection still reports failure',async()=>{
  const f=fixture(),late=deferred();f.blocked.set('/runs/first/overview',late);
  const first=f.service.openArchive('first');
  while(!f.calls.includes('/runs/first/overview'))await Promise.resolve();
  await f.service.openArchive('second');late.reject(Error('old archive failed'));await first;
  const failed=deferred();f.blocked.set('/runs/third/overview',failed);
  const third=f.service.openArchive('third');failed.reject(Error('current archive failed'));
  await assert.rejects(third,/current archive failed/);assert.deepEqual(f.shown.map(item=>item.id),['second']);
});

test('deleting an archive invalidates its unfinished read instead of restoring the deleted cache',async()=>{
  const f=fixture(),late=deferred();f.blocked.set('/runs/first/overview',late);
  const first=f.service.openArchive('first');
  while(!f.calls.includes('/runs/first/overview'))await Promise.resolve();
  await f.service.deleteArchive('first');late.resolve({rows:[]});await first;
  assert.equal(f.shown.length,0);
});

test('choosing an already loaded source can cancel an older outstanding archive read',async()=>{
  const f=fixture(),late=deferred();f.blocked.set('/runs/first/overview',late);
  const first=f.service.openArchive('first');
  while(!f.calls.includes('/runs/first/overview'))await Promise.resolve();
  f.service.cancelArchiveRead();late.resolve({rows:[]});assert.equal(await first,false);
  assert.equal(f.shown.length,0);
});
