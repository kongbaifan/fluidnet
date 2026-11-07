import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const context=vm.createContext({window:{}});
for(const file of ['project-links.js','project-state.js'])loadFrontend(new URL('../frontend/'+file,import.meta.url),context);
const edits=context.window.FluidNetProjectState;
const plain=value=>JSON.parse(JSON.stringify(value));
const project=()=>({id:'p',pages:[{id:'a',nodes:[{id:'A',params:{opening:80,enabled:true},draft:{opening:80,enabled:true},
  variableState:{values:{custom:1},draft:{custom:2},banks:[]}}],edges:[]},{id:'b',nodes:[{id:'B',params:{},draft:{}}],edges:[]}],
  activePage:'a',run:{history:[{time:1}],status:'completed'},thermalCouplings:[]});
const definition=()=>({ports:[{id:'in',domain:'fluid'},{id:'out',domain:'fluid'}]});

test('draft writes and acknowledged parameter values remain independent',()=>{
  const p=project(),n=p.pages[0].nodes[0];
  edits.setDraft(p,n,{opening:40});
  assert.equal(n.params.opening,80);
  edits.setDraft(p,n,{opening:20});
  edits.applyParameters(p,n,{opening:40});
  assert.equal(n.params.opening,40);assert.equal(n.draft.opening,20);
  assert.deepEqual(p.run.history,[{time:1}]);
});
test('committing typed drafts updates parameter and custom variable projections together',()=>{
  const p=project(),n=p.pages[0].nodes[0];n.draft.enabled=false;
  edits.commitEdits(p,n,{'param:opening':40,custom:3},[
    {id:'param:opening',origin:'parameter',param:'opening'},{id:'custom',origin:'custom'}],
    [{id:'opening'},{id:'enabled'}]);
  assert.deepEqual(plain(n.params),{opening:40,enabled:false});
  assert.deepEqual(plain(n.variableState.values),{custom:3});
  assert.deepEqual(plain(n.variableState.draft),{custom:3});
});
test('replaced projects and devices reject writes through stale references',()=>{
  const p=project(),n=p.pages[0].nodes[0],replacement=plain(n);
  p.pages[0].nodes[0]=replacement;
  assert.throws(()=>edits.applyParameters(p,n,{opening:0}),/替换/);
  assert.equal(replacement.params.opening,80);
  assert.throws(()=>edits.assertCurrent({projects:[plain(p)]},p),/替换/);
});
test('invalid topology edits leave the complete existing network intact',()=>{
  const p=project();edits.connect(p,'e',['A','out'],['B','in'],definition);
  const before=plain(p);
  assert.throws(()=>edits.connect(p,'e',['A','out'],['missing','in'],definition,true),/不存在/);
  assert.throws(()=>edits.addNode(p,'b',{id:'A'}),/重复/);
  assert.deepEqual(plain(p),before);
});
test('canvas restore retains cross-page links and chart bindings and cannot cross project IDs',()=>{
  const p=project(),charts=[{projectId:'p',id:'curve'},{projectId:'other',id:'keep'}];
  edits.connect(p,'e',['A','out'],['B','in'],definition);
  const snapshot=edits.canvasSnapshot(p,charts,{workbenchChart:'flow',showChart:true});
  edits.removeNodes(p,['B']);
  const restored=edits.restoreCanvas(p,snapshot,charts);
  assert.equal(p.pages[1].nodes[0].id,'B');assert.equal(p.pages[0].edges.length,1);
  assert.deepEqual(plain(restored).map(c=>c.id),['keep','curve']);
  const before=plain(p);
  assert.throws(()=>edits.restoreCanvas(p,{...snapshot,projectId:'other'},charts),/另一个项目/);
  assert.deepEqual(plain(p),before);
});
test('failed workspace normalization restores the original object without changing input data',()=>{
  const original={projects:[project()]},incoming=plain(original),before=plain(incoming);let current=original;
  assert.throws(()=>edits.replaceWorkspace(incoming,{get:()=>current,set:value=>{current=value;},
    validate:()=>{},normalize:()=>{current.projects=[];throw Error('invalid');}}),/invalid/);
  assert.equal(current,original);assert.deepEqual(incoming,before);
});
test('single-project replacement retains other drafts, modules and revision ownership',()=>{
  const p=project(),other={id:'other',draft:'unsaved'};
  const current={projects:[p,other],modules:[],models:[],charts:{extra:[{projectId:'other',id:'keep'}]}};
  const before=plain(current),document={project:{...p,name:'replaced'},modules:[],models:[],charts:[]};
  const next=edits.mergeDocument(current,document,()=>({status:'ready'}),{revision:7});
  assert.equal(next.projects[0].name,'replaced');assert.equal(next.projectRevisions.p,7);
  assert.equal(next.projects[1].draft,'unsaved');assert.equal(next.charts.extra[0].id,'keep');
  assert.deepEqual(current,before);
});
