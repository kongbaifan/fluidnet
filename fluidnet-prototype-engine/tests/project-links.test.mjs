import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/project-links.js',import.meta.url),'utf8'),context);
const links=context.window.FluidNetLinks,plain=value=>JSON.parse(JSON.stringify(value));
const definition=node=>({ports:[{id:'in',label:'入口',direction:'in',domain:node.domain||'fluid'},
  {id:'out',label:'出口',direction:'out',domain:node.domain||'fluid'}]});
const owner=()=>({pages:[{id:'plant',nodes:[{id:'A'},{id:'B'}],edges:[]},
  {id:'terminal',nodes:[{id:'C'},{id:'D'}],edges:[]}]});

test('cross-page ports are occupied globally and are visible at both endpoints',()=>{
  const p=owner();links.connect(p,'supply',['A','out'],['C','in'],definition);
  assert.equal(links.atPort(p,'C','in')[0],'supply');
  assert.equal(links.cross(p,'plant')[0].remotePage.id,'terminal');
  assert.equal(links.cross(p,'terminal')[0].remotePage.id,'plant');
  assert.throws(()=>links.connect(p,'duplicate',['B','out'],['C','in'],definition),/已经连接/);
  assert.equal(links.all(p).length,1);
  assert.equal(links.validate(p,definition,false).length,0);
});
test('replacement validates before mutation and leaves an invalid edit untouched',()=>{
  const p=owner();links.connect(p,'supply',['A','out'],['C','in'],definition);
  links.connect(p,'other',['B','out'],['D','in'],definition);
  const before=plain(p);
  assert.throws(()=>links.connect(p,'supply',['A','out'],['D','in'],definition,true),/已经连接/);
  assert.deepEqual(plain(p),before);
  links.remove(p,'other');links.connect(p,'supply',['A','out'],['D','in'],definition,true);
  assert.equal(links.atPort(p,'C','in'),undefined);
  assert.equal(links.atPort(p,'D','in')[0],'supply');
});
test('moving devices preserves connectivity, and deleting either side removes all references',()=>{
  const p=owner();links.connect(p,'supply',['A','out'],['B','in'],definition);
  links.move(p,'B','terminal');
  assert.equal(links.cross(p).length,1);
  links.move(p,'A','terminal');
  assert.equal(p.pages[0].edges.length,0);
  assert.equal(p.pages[1].edges[0][0],'supply');
  assert.equal(links.cross(p).length,0);
  links.removeNodes(p,['B']);assert.equal(links.all(p).length,0);
});
test('validation detects references and duplicate ports across different storage canvases',()=>{
  const p=owner();p.pages[0].edges.push(['one','A','out','C','in']);
  p.pages[1].edges.push(['two','B','out','C','in'],['missing','Gone','out','D','in']);
  const errors=plain(links.validate(p,definition,false));
  assert.ok(errors.some(error=>error.text.includes('端口重复')));
  assert.ok(errors.some(error=>error.text.includes('端口不存在')));
  p.pages[1].edges=[];assert.ok(links.validate(p,definition).some(error=>error.node==='C'&&error.text.includes('出口')));
});
test('incompatible types and signal directions cannot form a connection',()=>{
  const p=owner();p.pages[1].nodes[0].domain='refrigerant';
  assert.throws(()=>links.connect(p,'bad',['A','out'],['C','in'],definition),/物理类型/);
  p.pages[0].nodes[0].domain='signal';p.pages[1].nodes[0].domain='signal';
  assert.throws(()=>links.connect(p,'bad',['A','out'],['C','out'],definition),/输入与输出/);
  assert.equal(links.all(p).length,0);
});
test('serialization and project copies retain links without coupling their edits',()=>{
  const p=owner();links.connect(p,'supply',['A','out'],['C','in'],definition);
  const copy=plain(p);links.rehome(copy);
  assert.deepEqual(plain(links.all(copy)),plain(links.all(p)));
  links.remove(copy,'supply');assert.equal(links.all(p).length,1);
});
