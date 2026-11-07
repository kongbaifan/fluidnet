import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const host=vm.createContext({window:{},moduleOf:n=>n.module});
loadFrontend(new URL('../frontend/canvas-symbols.js',import.meta.url),host);
const geometry=host.window.FluidNetCanvasSymbols;
test('dense same-side port hit targets do not cover neighboring port centers',()=>{
  for(const count of [4,6,8,16]){
    const node={module:{kind:'manifold',category:'制冷站设备',ports:Array.from({length:count},(_,i)=>({id:'in'+i,direction:'in'}))}};
    const ports=node.module.ports;
    for(let i=0;i<count-1;i++){
      const a=geometry.portOffset(node,node.module,ports[i]),b=geometry.portOffset(node,node.module,ports[i+1]);
      assert.ok(geometry.hitRadius(node,node.module,ports[i])+geometry.hitRadius(node,node.module,ports[i+1])<Math.abs(a.y-b.y));
    }
  }
});
test('ordinary two-port equipment retains the original touch target',()=>{
  const port={id:'in0',direction:'in'},node={module:{kind:'valve',category:'管道',ports:[port,{id:'out0',direction:'out'}]}};
  assert.equal(geometry.hitRadius(node,node.module,port),10);
});
