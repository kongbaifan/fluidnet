import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const host=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/workspace-interactions.js',import.meta.url),host);
const create=host.window.FluidNetWorkspaceInteractions.create;
const plain=v=>JSON.parse(JSON.stringify(v));
function surface(){const listeners=new Map();return {listeners,addEventListener:(key,fn)=>{const list=listeners.get(key)||[];list.push(fn);listeners.set(key,list);},removeEventListener:(key,fn)=>listeners.set(key,(listeners.get(key)||[]).filter(x=>x!==fn))};}
function target(matches={},editable=false){return {dataset:{},closest:selector=>matches[selector]||null,matches:()=>editable};}
function fixture(){
  const calls=[],errors=[],root={...surface(),setPointerCapture:id=>calls.push(['capture',id]),releasePointerCapture:id=>calls.push(['release',id])};
  const svg={isConnected:true,getScreenCTM:()=>({inverse:()=>({})}),append:()=>{}},page={nodes:[{id:'N',x:0,y:0},{id:'B',x:20,y:20}],pan:[0,0]},owner={id:'project'};
  let actualOwner=owner,actualPage=page,hit=null;
  const view={route:'workbench',modal:false},doc={...surface(),elementFromPoint:()=>hit,createElementNS:()=>({setAttribute:()=>{},remove:()=>calls.push(['box-remove'])})};
  const selection={ids:()=>[],group:ids=>calls.push(['group',plain(ids)]),node:id=>calls.push(['node',id]),single:id=>calls.push(['single',id]),edge:()=>{},clearConnection:()=>calls.push(['clear-connection']),mode:()=>{}};
  const module={ports:[{id:'p',x:20,y:50}]};
  const api=create({root,document:doc,getView:()=>view,point:(_,e)=>({x:e.clientX,y:e.clientY}),now:()=>1000,
    canvas:{owner:()=>actualOwner,page:()=>actualPage,node:id=>actualPage.nodes.find(n=>n.id===id),svg:()=>svg,remember:()=>calls.push(['remember']),move:(n,x,y)=>{n.x=x;n.y=y;calls.push(['move',n.id,x,y]);},pan:v=>{page.pan=v;},flush:()=>calls.push(['flush']),commit:()=>calls.push(['commit']),connect:(id,p)=>calls.push(['connect',id,p]),insert:(id,p)=>calls.push(['insert',id,p]),hasModule:id=>id==='pipe',rotate:()=>{},undo:r=>calls.push(['undo',r]),copy:()=>calls.push(['copy']),paste:()=>calls.push(['paste']),removeNode:id=>calls.push(['delete',id]),removeEdge:()=>{},pageSelect:()=>{},zoom:()=>{},fit:()=>{},grid:()=>{}},
    selection,editor:{current:()=>module,select:()=>{},svg:()=>svg,move:(id,x,y)=>calls.push(['port',id,x,y]),commit:()=>calls.push(['editor-commit']),nudge:()=>{}},
    windows:{beginPointer:e=>e.windowTicket||null,movePointer:(ticket,x,y)=>calls.push(['window-move',ticket.id,x,y]),finishPointer:t=>calls.push(['window-finish',t.id]),open:id=>calls.push(['open',id])},
    charts:{hover:()=>{},pin:()=>{}},shell:{error:e=>errors.push(e),render:()=>calls.push(['render']),action:n=>calls.push(['action',n]),clearContext:()=>{},dismissContext:()=>{},context:()=>{}}
  });
  const ev=(t,x=0,y=0,other={})=>({button:0,pointerId:1,clientX:x,clientY:y,target:t,preventDefault(){this.prevented=true;},...other});
  const nTarget=target({'#network':svg,'[data-node]':{dataset:{node:'N'}}});
  return {api,calls,errors,page,view,root,doc,svg,ev,nTarget,blank:target({'#network':svg}),replace:()=>{actualOwner={id:'project'};actualPage={...page,nodes:[...page.nodes]};},setHit:t=>{hit=t;}};
}
test('node drag has one capture and undo boundary, unrelated pointer cannot finish it',()=>{
  const f=fixture();f.api.pointerdown(f.ev(f.nTarget));f.api.pointermove(f.ev(f.nTarget,2,2));assert.equal(f.calls.some(c=>c[0]==='remember'),false);
  f.api.pointermove(f.ev(f.nTarget,10,12));f.api.pointermove(f.ev(f.nTarget,14,18));f.api.pointerup(f.ev(f.nTarget,14,18,{pointerId:2}));assert.equal(f.api.busy(),true);
  f.api.pointerup(f.ev(f.nTarget,14,18));assert.equal(f.api.busy(),false);assert.deepEqual([f.page.nodes[0].x,f.page.nodes[0].y],[14,18]);
  assert.equal(f.calls.filter(c=>c[0]==='remember').length,1);assert.equal(f.calls.filter(c=>c[0]==='commit').length,1);
});
test('replacing project during drag cannot apply positions or commit into its replacement',()=>{
  const f=fixture();f.api.pointerdown(f.ev(f.nTarget));f.replace();f.api.pointermove(f.ev(f.nTarget,100,100));assert.equal(f.api.busy(),false);
  assert.equal(f.calls.some(c=>['move','commit'].includes(c[0])),false);
});
test('cancelled drag preserves the visible geometry and commits its dirty state once',()=>{
  const f=fixture();f.api.pointerdown(f.ev(f.nTarget));f.api.pointermove(f.ev(f.nTarget,20,30));f.api.cancel();f.api.cancel();
  assert.equal(f.api.busy(),false);assert.deepEqual([f.page.nodes[0].x,f.page.nodes[0].y],[20,30]);assert.equal(f.calls.filter(c=>c[0]==='commit').length,1);
  const replaced=fixture();replaced.api.pointerdown(replaced.ev(replaced.nTarget));replaced.api.pointermove(replaced.ev(replaced.nTarget,20,30));replaced.replace();replaced.api.cancel();assert.equal(replaced.calls.some(c=>c[0]==='commit'),false);
});
test('reusing an instance id during a gesture does not move the replacement instance',()=>{
  const f=fixture();f.api.pointerdown(f.ev(f.nTarget));f.page.nodes[0]={id:'N',x:100,y:100};f.api.pointermove(f.ev(f.nTarget,20,30));
  assert.equal(f.api.busy(),false);assert.deepEqual([f.page.nodes[0].x,f.page.nodes[0].y],[100,100]);assert.equal(f.calls.some(c=>c[0]==='commit'),false);
});
test('shift click and box selection have one coordinated owner and suppress trailing click',()=>{
  const f=fixture();f.api.pointerdown(f.ev(f.nTarget,0,0,{shiftKey:true}));f.api.click(f.ev(f.nTarget));assert.deepEqual(f.calls.filter(c=>c[0]==='group'),[['group',['N']]]);assert.equal(f.calls.some(c=>c[0]==='single'),false);
  f.api.pointerdown(f.ev(f.blank,-5,-5,{shiftKey:true}));f.api.pointermove(f.ev(f.blank,25,25));f.api.pointerup(f.ev(f.blank,25,25));assert.deepEqual(f.calls.filter(c=>c[0]==='group').at(-1),['group',['N','B']]);
});
test('floating gestures are delegated without taking a canvas undo snapshot',()=>{
  const f=fixture();f.api.pointerdown(f.ev(target(),0,0,{windowTicket:{id:'D1',kind:'resize'}}));f.api.pointermove(f.ev(target(),20,30));f.api.pointerup(f.ev(target(),20,30));
  assert.deepEqual(f.calls.find(c=>c[0]==='window-move'),['window-move','D1',20,30]);assert.equal(f.calls.some(c=>c[0]==='remember'||c[0]==='commit'),false);
});
test('port drag connects only the actual released-on target',()=>{
  const f=fixture(),from=target({'#network':f.svg,'[data-port-node]':{dataset:{portNode:'N',portId:'out0'}}}),to=target({'[data-port-node]':{dataset:{portNode:'B',portId:'in0'}}});
  f.setHit(to);f.api.pointerdown(f.ev(from));f.api.pointermove(f.ev(from,40,40));f.api.pointerup(f.ev(from,40,40));
  assert.deepEqual(f.calls.filter(c=>c[0]==='connect'),[['connect','N','out0'],['connect','B','in0']]);
});
test('workbench shortcuts respect text editing and active dialogs',()=>{
  const f=fixture();f.view.selectedNode='N';f.api.keydown(f.ev(target({},true),0,0,{key:'Delete'}));f.view.modal=true;f.api.keydown(f.ev(target(),0,0,{key:'Delete'}));assert.equal(f.calls.length,0);
  f.view.modal=false;f.api.keydown(f.ev(target(),0,0,{key:'Delete'}));f.api.keydown(f.ev(target(),0,0,{key:'z',ctrlKey:true,shiftKey:true}));assert.deepEqual(f.calls,[['delete','N'],['undo',true]]);
});
test('mount is idempotent and destroy releases listeners and capture',()=>{
  const f=fixture();f.api.mount();f.api.mount();assert.equal(f.root.listeners.get('pointerdown').length,1);
  f.api.pointerdown(f.ev(f.nTarget));f.api.destroy();assert.equal(f.api.busy(),false);for(const list of f.root.listeners.values())assert.equal(list.length,0);assert.equal(f.doc.listeners.get('keydown').length,0);
});
