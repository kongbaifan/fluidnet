import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const host=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/device-windows.js',import.meta.url),host);
const plain=value=>JSON.parse(JSON.stringify(value));
function fixture(){
  const nodes={V1:{id:'V1',name:'调节阀',params:{opening:80},draft:{opening:45}},P1:{id:'P1',name:'水泵',params:{speed:1},draft:{speed:.7}}};
  const state={project:'p1',route:'workbench',floats:[],positions:{},front:'',selected:'',serial:0,width:1920,dirty:0,rendered:0,selection:0,messages:[],retained:0};
  const rect={left:66,top:54,width:1854,height:996,right:1920,bottom:1050};
  const classes=new Map(),workbench={classList:{toggle:(name,value)=>classes.set(name,value)}};
  const elements=new Map(),layer={innerHTML:'',querySelectorAll:()=>[...elements.values()]};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const api=host.window.FluidNetDeviceWindows.create({
    windows:{list:()=>state.floats,replace:v=>{state.floats=v;},front:()=>state.front,focus:id=>{state.front=id;return ++state.serial;},route:()=>state.route,select:id=>{state.selected=id;},project:()=>state.project},
    storage:{read:(project,id)=>state.positions[project+':'+id],write:(project,id,value)=>{state.positions[project+':'+id]=value;}},
    elements:{root:()=>({querySelector:()=>workbench}),page:()=>({getBoundingClientRect:()=>rect}),floatingTop:()=>state.floatingTop||0,floatingRight:()=>state.floatingRight,layer:()=>layer,dock:()=>({getBoundingClientRect:()=>({left:1400,top:54,width:520,height:996})}),viewport:()=>({width:state.width,height:1080})},
    content:{node:id=>nodes[id],body:(f,n)=>`body:${n.id}:${f.tab}`,footer:(f,n)=>`footer:${n.id}`,extras:()=>'<aside>shared overlays</aside>'},
    chrome:{esc,icon:id=>`<i>${id}</i>`,ibtn:(action,label,icon,attrs)=>`<button data-action="${action}" ${attrs}>${label}</button>`},
    effects:{dirty:()=>state.dirty++,selection:()=>state.selection++,message:s=>state.messages.push(s),retainFocus:fn=>{state.retained++;fn();},rendered:()=>{state.rendered++;for(const f of state.floats)if(!elements.has(f.id))elements.set(f.id,{dataset:{floatId:f.id},style:{}});}}
  });
  const event=(id,kind='window',button=false)=>({target:{closest:selector=>selector==='[data-float-resize]'?(kind==='resize'?{dataset:{floatResize:id}}:null):selector==='[data-float-move]'?{dataset:{floatMove:id}}:button?{}:null}});
  const act=(name,id='V1',value)=>api.action(name,{dataset:{id,value}});
  return {api,state,nodes,rect,classes,layer,elements,event,act};
}

test('open restores only its project window presentation and leaves device drafts unchanged',()=>{
  const f=fixture(),before=plain(f.nodes);f.state.positions['p1:V1']={x:120,y:100,w:510,h:600,pinned:true};
  const opened=f.api.open('V1');assert.equal(opened.x,120);assert.equal(opened.tab,'parameters');assert.equal(f.state.front,'V1');
  f.api.open('V1');assert.equal(f.state.floats.length,1);assert.equal(f.state.selected,'V1');
  assert.deepEqual(plain(f.nodes),before);assert.match(f.layer.innerHTML,/body:V1:parameters/);assert.match(f.layer.innerHTML,/footer:V1/);
  assert.equal(f.api.open('missing'),undefined);assert.equal(f.state.floats.length,1);
});
test('one dock is visible, minimizing releases its dock, narrow screens reject new docking',()=>{
  const f=fixture(),first=f.api.open('V1'),second=f.api.open('P1');f.api.toggleDock('V1');
  assert.equal(f.classes.get('has-docked'),true);assert.equal(f.api.isDocked(first),true);
  f.api.toggleDock('P1');assert.equal(first.docked,false);assert.equal(second.docked,true);assert.equal(f.state.positions['p1:V1'].docked,false);
  f.act('float-min','P1');assert.equal(f.classes.get('has-docked'),false);
  f.act('float-min','P1');f.api.setTab(second,'variables');f.api.render();assert.equal(f.classes.get('has-docked-variables'),true);
  f.state.width=900;assert.equal(f.api.isDocked(second),false);f.api.toggleDock('V1');assert.equal(first.docked,false);assert.equal(f.state.messages.length,1);
});
test('move and resize act on their own window and save clamped geometry on completion',()=>{
  const f=fixture(),first=f.api.open('V1');f.api.open('P1');const second=plain(f.state.floats[1]);
  const drag=f.api.beginPointer(f.event('V1'));assert.equal(drag.kind,'window');assert.equal(f.state.front,'V1');
  assert.equal(f.api.movePointer(drag,-5000,-5000),true);assert.equal(first.x,f.rect.left+8);assert.equal(first.y,f.rect.top+8);
  assert.equal(f.elements.get('V1').style.left,first.x+'px');assert.deepEqual(plain(f.state.floats[1]),second);
  assert.equal(f.api.finishPointer(drag),true);assert.equal(f.state.positions['p1:V1'].x,first.x);assert.equal(f.state.dirty,1);
  const resize=f.api.beginPointer(f.event('V1','resize'));f.api.movePointer(resize,5000,5000);f.api.finishPointer(resize);
  assert.equal(first.w,f.rect.width-16);assert.equal(first.h,f.rect.height-16);assert.equal(f.state.dirty,2);
});
test('late pointer work cannot write into a closed, replaced or different-project window',()=>{
  for(const mode of ['closed','replaced','project']){
    const f=fixture();f.api.open('V1');const ticket=f.api.beginPointer(f.event('V1'));
    if(mode==='closed')f.act('float-close');else if(mode==='replaced')f.state.floats=[{...f.state.floats[0]}];else f.state.project='p2';
    const before=plain(f.state);assert.equal(f.api.movePointer(ticket,20,20),false);assert.equal(f.api.finishPointer(ticket),false);
    assert.deepEqual(plain(f.state),before);
  }
});

test('opening, dragging and maximizing leave the workbench run controls reachable',()=>{
  const f=fixture();f.state.floatingTop=180;f.state.floatingRight=1830;f.state.positions['p1:V1']={x:1300,y:80,w:440,h:950};
  const window=f.api.open('V1');assert.equal(window.y,180);assert.ok(window.y+window.h<=f.rect.bottom-8);
  const drag=f.api.beginPointer(f.event('V1'));f.api.movePointer(drag,0,-1000);f.api.finishPointer(drag);
  assert.equal(window.y,180);
  f.act('float-max');assert.equal(window.y,180);assert.ok(window.y+window.h<=f.rect.bottom-8);
  assert.ok(window.x+window.w<=1830);
  const moveRight=f.api.beginPointer(f.event('V1'));f.api.movePointer(moveRight,5000,0);f.api.finishPointer(moveRight);assert.ok(window.x+window.w<=1830);
  f.state.floatingTop=220;f.state.floatingRight=1750;f.api.render();assert.equal(window.y,220);assert.ok(window.y+window.h<=f.rect.bottom-8);assert.ok(window.x+window.w<=1750);
});
test('header controls and docked windows cannot accidentally start pointer moves',()=>{
  const f=fixture();f.api.open('V1');assert.equal(f.api.beginPointer(f.event('V1','window',true)),null);
  f.api.toggleDock('V1');assert.equal(f.api.beginPointer(f.event('V1')).blocked,true);
});
test('close/reopen, maximize/restore, pin and tab switches retain existing layout behavior',()=>{
  const f=fixture(),w=f.api.open('V1');const before=plain(w);f.act('float-max');assert.equal(w.w,f.rect.width-16);
  f.act('float-max');assert.equal(w.w,before.w);assert.equal(w.restore,undefined);
  f.act('float-pin');assert.equal(w.pinned,true);f.act('device-panel-tab','V1','variables');assert.equal(w.w,780);
  w.w=680;f.act('float-tab','V1','parameters');f.act('float-tab','V1','variables');assert.equal(w.w,680);
  f.act('float-close');assert.equal(f.state.floats.length,0);f.api.open('V1');assert.equal(f.state.floats[0].w,680);assert.equal(f.state.floats[0].pinned,true);
  assert.equal(f.act('float-made-up'),false);assert.equal(f.act('float-close','missing'),true);
});
test('non-workbench routes and deleted devices hide windows while shared overlays remain',()=>{
  const f=fixture();f.api.open('V1');f.state.route='models';f.api.render();assert.doesNotMatch(f.layer.innerHTML,/class="floater/);assert.match(f.layer.innerHTML,/shared overlays/);
  f.state.route='workbench';delete f.nodes.V1;f.api.render();assert.doesNotMatch(f.layer.innerHTML,/class="floater/);
  f.api.updateBodies();assert.equal(f.state.retained,1);
});
test('window title and identifiers are escaped and reopening never aliases saved position data',()=>{
  const f=fixture();f.nodes.V1.name='<img src=x onerror=bad>';f.state.positions['p1:V1']={x:140,y:120,w:440,h:500};
  const w=f.api.open('V1');assert.match(f.layer.innerHTML,/&lt;img/);assert.doesNotMatch(f.layer.innerHTML,/<img/);
  w.x=200;assert.equal(f.state.positions['p1:V1'].x,140);
  f.act('float-close');f.state.project='p2';f.api.open('V1');assert.notEqual(f.state.floats[0].x,200);
});
