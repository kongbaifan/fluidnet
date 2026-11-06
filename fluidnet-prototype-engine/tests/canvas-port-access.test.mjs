import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../frontend/studio.js',import.meta.url),'utf8');
const host=vm.createContext({moduleOf:n=>n.module});
vm.runInContext(source.slice(source.indexOf('function portOffset('),source.indexOf('function endpoint(')),host);
test('dense same-side port hit targets do not cover neighboring port centers',()=>{
  for(const count of [4,6,8,16]){
    const node={module:{kind:'manifold',category:'制冷站设备',ports:Array.from({length:count},(_,i)=>({id:'in'+i,direction:'in'}))}};
    const ports=node.module.ports;
    for(let i=0;i<count-1;i++){
      const a=host.portOffset(node,ports[i]),b=host.portOffset(node,ports[i+1]);
      assert.ok(host.portHitRadius(node,ports[i])+host.portHitRadius(node,ports[i+1])<Math.abs(a.y-b.y));
    }
  }
});
test('ordinary two-port equipment retains the original touch target',()=>{
  const port={id:'in0',direction:'in'},node={module:{kind:'valve',category:'管道',ports:[port,{id:'out0',direction:'out'}]}};
  assert.equal(host.portHitRadius(node,port),10);
});
