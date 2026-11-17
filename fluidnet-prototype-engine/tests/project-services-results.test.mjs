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

async function workspaceFixture(){
  const host=vm.createContext({window:{}});loadFrontend(new URL('../frontend/project-services.js',import.meta.url),host);
  let workspace={workspaceRevision:4,projectRevisions:{p:2},projectSavedKeys:{},dirty:false,projects:[{id:'p',name:'original',dirty:true}]},handler;
  const calls=[],messages=[],persisted=[],clone=value=>JSON.parse(JSON.stringify(value));
  const service=host.window.createProjectServices({health:()=>({capabilities:{persistent_workspace:true}}),
    ui:{state:()=>workspace,restoreWorkspace:data=>{workspace=clone(data);},parameterKey:p=>p.id+':'+p.name,
      persist:()=>persisted.push(workspace),message:text=>messages.push(text),validateWorkspace:()=>{},render:()=>{}},
    request:(path,body)=>{
      calls.push({path,body:body===undefined?undefined:clone(body)});
      const response=handler?.(path,body);if(response!==undefined)return response;
      if(path==='/workspace')return body?{revision:5,project_revisions:{p:3},saved_at:'saved'}:{revision:4,data:clone(workspace),project_revisions:{p:2}};
      return {revision:3,previous_workspace_revision:4,workspace_revision:5};
    }});
  await service.loadWorkspace();calls.length=0;
  return {service,calls,messages,persisted,state:()=>workspace,replace:data=>{workspace=data;},handle:fn=>{handler=fn;},clone};
}
const replacementWorkspace=()=>({workspaceRevision:99,projectRevisions:{replacement:8},projectSavedKeys:{replacement:'known'},dirty:true,projects:[{id:'replacement',name:'new',dirty:true}]});
async function untilRequested(f,path,count=1){
  for(let i=0;i<30;i++){if(f.calls.filter(c=>c.path===path&&c.body).length>=count)return;await Promise.resolve();}
  throw Error('Expected request was not dispatched: '+path);
}
const aborted=error=>error.name==='AbortError';

test('late workspace save receipts cannot overwrite replacement revision metadata or authorize the next save',async()=>{
  const f=await workspaceFixture(),late=deferred();f.handle((path,body)=>path==='/workspace'&&body?late.promise:undefined);
  const saving=f.service.saveWorkspace(f.clone(f.state())),rejected=assert.rejects(saving,aborted);await untilRequested(f,'/workspace');
  const next=replacementWorkspace(),before=f.clone(next);f.replace(next);late.resolve({revision:5,project_revisions:{p:3}});await rejected;
  assert.deepEqual(f.state(),before);
  f.handle((path,body)=>path==='/workspace'&&body?{revision:100,project_revisions:{replacement:9}}:undefined);
  await f.service.saveWorkspace(f.clone(next));assert.equal(f.calls.at(-1).body.expected_revision,99);
  assert.equal(next.workspaceRevision,100);assert.deepEqual(Object.keys(next.projectSavedKeys),['replacement']);
});
test('obsolete queued saves are rejected before sending old data and do not block a replacement save',async()=>{
  const f=await workspaceFixture(),late=deferred();f.handle((path,body)=>path==='/workspace'&&body?late.promise:undefined);
  const first=f.service.saveWorkspace(f.clone(f.state())),a=assert.rejects(first,aborted);await untilRequested(f,'/workspace');
  const second=f.service.saveWorkspace(f.clone(f.state())),b=assert.rejects(second,aborted);
  f.replace(replacementWorkspace());late.resolve({revision:5,project_revisions:{p:3}});await Promise.all([a,b]);
  assert.equal(f.calls.filter(c=>c.path==='/workspace'&&c.body).length,1);
  f.handle((path,body)=>body?{revision:100,project_revisions:{replacement:9}}:undefined);
  await f.service.saveWorkspace(f.clone(f.state()));assert.equal(f.state().workspaceRevision,100);
});
test('the newest workspace load wins and invalidates older save receipts',async()=>{
  const f=await workspaceFixture(),late=deferred();f.handle((path,body)=>path==='/workspace'&&!body?late.promise:undefined);
  const first=f.service.loadWorkspace(true);
  const newest={revision:8,data:{workspaceRevision:8,projects:[{id:'newest',name:'latest'}],dirty:false},project_revisions:{newest:4}};
  f.handle((path,body)=>path==='/workspace'&&!body?newest:undefined);
  await f.service.loadWorkspace(true);const before=f.clone(f.state());
  late.resolve({revision:50,data:{projects:[]},project_revisions:{old:50}});
  assert.equal(await first,false);assert.deepEqual(f.clone(f.state()),before);assert.equal(f.state().workspaceRevision,8);
});
test('loading a workspace while an old save waits cannot apply its receipt even when project IDs match',async()=>{
  const f=await workspaceFixture(),late=deferred();f.handle((path,body)=>path==='/workspace'&&body?late.promise:undefined);
  const saving=f.service.saveWorkspace(f.clone(f.state())),rejected=assert.rejects(saving,aborted);await untilRequested(f,'/workspace');
  await f.service.loadWorkspace(true);const before=f.clone(f.state());late.resolve({revision:5,project_revisions:{p:3}});await rejected;
  assert.deepEqual(f.clone(f.state()),before);
});
test('an obsolete load failure cannot undo a newer successful workspace connection',async()=>{
  const f=await workspaceFixture(),late=deferred();f.handle((path,body)=>path==='/workspace'&&!body?late.promise:undefined);
  const old=f.service.loadWorkspace(true);
  f.handle(()=>undefined);await f.service.loadWorkspace(true);const before=f.clone(f.state());
  late.reject(Error('obsolete connection failure'));assert.equal(await old,false);assert.deepEqual(f.clone(f.state()),before);
  f.handle((path,body)=>path==='/workspace'&&!body?Promise.reject(Error('current connection failure')):undefined);
  await assert.rejects(f.service.loadWorkspace(true),/current connection failure/);
});
test('project save, restore, and deletion receipts cannot mutate a replacement workspace',async()=>{
  for(const operation of ['save','restore','delete']){
    const f=await workspaceFixture(),late=deferred(),owner=f.state().projects[0],before=f.clone(owner);
    const path='/projects/p'+(operation==='restore'?'/restore':operation==='delete'?'/delete':'');
    f.handle((route,body)=>route===path&&body?late.promise:undefined);
    const request=operation==='save'?f.service.saveProject(owner,{project:before}):operation==='restore'?f.service.restoreProject('p',1):f.service.deleteProject('p');
    const rejected=assert.rejects(request,aborted);await untilRequested(f,path);
    const next=replacementWorkspace(),nextBefore=f.clone(next);f.replace(next);
    late.resolve({revision:3,previous_workspace_revision:4,workspace_revision:5});await rejected;
    assert.deepEqual(next,nextBefore);assert.deepEqual(owner,before);
  }
});
test('replacing one project object invalidates its pending save even within the same workspace',async()=>{
  const f=await workspaceFixture(),late=deferred(),owner=f.state().projects[0];f.handle((path,body)=>path==='/projects/p'&&body?late.promise:undefined);
  const request=f.service.saveProject(owner,{project:f.clone(owner)}),rejected=assert.rejects(request,aborted);await untilRequested(f,'/projects/p');
  f.state().projects=[{id:'p',name:'replacement project',dirty:true}];const before=f.clone(f.state());
  late.resolve({revision:3,previous_workspace_revision:4,workspace_revision:5});await rejected;assert.deepEqual(f.clone(f.state()),before);
});
test('current save receipts record submitted parameter keys while preserving later edits',async()=>{
  const f=await workspaceFixture(),late=deferred(),owner=f.state().projects[0];f.handle((path,body)=>path==='/workspace'&&body?late.promise:undefined);
  const saving=f.service.saveWorkspace(f.clone(f.state()));await untilRequested(f,'/workspace');owner.name='edited during save';
  late.resolve({revision:5,project_revisions:{p:3}});await saving;
  assert.equal(owner.name,'edited during save');assert.equal(f.state().projectSavedKeys.p,'p:original');
  assert.equal(f.service.runMetadata(owner).project_revision,null);
});
test('first project save preserves edits made while the initial workspace save is pending',async()=>{
  const f=await workspaceFixture(),late=deferred(),workspace=f.clone(f.state());
  workspace.workspaceRevision=0;workspace.projectRevisions={};f.replace(workspace);
  const owner=workspace.projects[0],submitted={project:f.clone(owner)};
  f.handle((path,body)=>path==='/workspace'&&body?late.promise:undefined);
  const saving=f.service.saveProject(owner,submitted);await untilRequested(f,'/workspace');
  owner.name='edited during initialization';
  late.resolve({revision:5,project_revisions:{p:3}});await saving;
  assert.equal(f.calls.find(c=>c.path==='/projects/p').body.document.project.name,'original');
  assert.equal(owner.name,'edited during initialization');assert.equal(owner.dirty,true);
  assert.equal(workspace.projectSavedKeys.p,'p:original');
  assert.equal(f.service.runMetadata(owner).project_revision,null);
});
test('late project reads cannot import another workspace revision and current project saves preserve conflict guards',async()=>{
  const f=await workspaceFixture(),late=deferred();f.handle(path=>path==='/projects/p'?late.promise:undefined);
  const reading=f.service.readProject('p'),rejected=assert.rejects(reading,aborted);
  f.replace(replacementWorkspace());const before=f.clone(f.state());late.resolve({revision:30});await rejected;assert.deepEqual(f.state(),before);
  const g=await workspaceFixture();g.handle((path,body)=>path==='/projects/p'&&body?{revision:3,previous_workspace_revision:9,workspace_revision:10}:undefined);
  await g.service.saveProject(g.state().projects[0],{project:g.clone(g.state().projects[0])});
  assert.equal(g.state().workspaceRevision,4);assert.equal(g.state().projectRevisions.p,3);
});
