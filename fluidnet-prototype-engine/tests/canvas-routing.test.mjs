import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/canvas-routing.js',import.meta.url),'utf8'),context);
const route=options=>JSON.parse(JSON.stringify(context.window.FluidNetCanvasRouting.route(options)));
const right={x:1,y:0},left={x:-1,y:0};
const rectangle=(id,x,y,width,height)=>({id,x,y,width,height});
const base=()=>({source:{x:20,y:0,nodeId:'A',normal:right},target:{x:180,y:0,nodeId:'B',normal:left},
  obstacles:[rectangle('A',-20,-20,40,40),rectangle('B',180,-20,40,40)]});
function assertGeometry(result,input){
  assert.deepEqual(result.points[0],{x:input.source.x,y:input.source.y});
  assert.deepEqual(result.points.at(-1),{x:input.target.x,y:input.target.y});
  for(let i=1;i<result.points.length;i++){
    const a=result.points[i-1],b=result.points[i];
    assert.ok([a.x,a.y,b.x,b.y].every(Number.isFinite));
    assert.ok(a.x===b.x||a.y===b.y,'all segments must be orthogonal');
    // Independently sample each segment in its open interior to verify it never crosses a body.
    for(let j=1;j<100;j++){
      const p={x:a.x+(b.x-a.x)*j/100,y:a.y+(b.y-a.y)*j/100};
      for(const r of input.obstacles){
        if(i===1&&r.id===input.source.nodeId||i===result.points.length-1&&r.id===input.target.nodeId)continue;
        assert.ok(!(p.x>r.x&&p.x<r.x+r.width&&p.y>r.y&&p.y<r.y+r.height),`crossed ${r.id}`);
      }
    }
  }
  assert.ok(!/NaN|Infinity|undefined/.test(result.path));
}

test('direct ports keep exact endpoints and collapse unnecessary collinear segments',()=>{
  const input=base(),result=route(input);assert.equal(result.blocked,false);assertGeometry(result,input);
  assert.deepEqual(result.points,[{x:20,y:0},{x:180,y:0}]);
});
test('an intervening device forces a clear orthogonal detour with explicit clearance',()=>{
  const input=base();input.obstacles.push(rectangle('Middle',80,-30,40,60));
  const result=route(input);assert.equal(result.blocked,false);assertGeometry(result,input);
  assert.ok(result.points.some(p=>Math.abs(p.y)>=36));
  assert.ok(result.points[1].x>input.source.x);
  assert.ok(result.points.at(-2).x<input.target.x);
});
test('same-side ports and rotated vertical ports leave each body in the outward direction',()=>{
  const cases=[
    {source:{x:20,y:0,nodeId:'A',normal:right},target:{x:180,y:80,nodeId:'B',normal:right},
      obstacles:[rectangle('A',-20,-20,40,40),rectangle('B',140,60,40,40)]},
    {source:{x:0,y:20,nodeId:'A',normal:{x:0,y:1}},target:{x:100,y:100,nodeId:'B',normal:{x:0,y:-1}},
      obstacles:[rectangle('A',-20,-20,40,40),rectangle('B',80,100,40,40),rectangle('Middle',20,45,70,25)]}
  ];
  for(const input of cases){
    const result=route(input);assert.equal(result.blocked,false);assertGeometry(result,input);
    for(const [end,next] of [[input.source,result.points[1]],[input.target,result.points.at(-2)]])
      assert.ok((next.x-end.x)*end.normal.x+(next.y-end.y)*end.normal.y>0,'stub points outward');
  }
});
test('unset normals infer the nearest body side, including a port just inside its body',()=>{
  const input=base();delete input.source.normal;delete input.target.normal;input.source.x=18;input.target.x=182;
  const result=route(input);assert.equal(result.blocked,false);assertGeometry(result,input);
  assert.ok(result.points[1].x>input.source.x);
});
test('ports trapped in a different device report the fallback instead of claiming a valid route',()=>{
  const input=base();input.obstacles.push(rectangle('Cover',15,-10,35,20));
  const result=route(input);assert.equal(result.blocked,true);assert.equal(result.reason,'blocked-port');
  assert.deepEqual(result.points[0],{x:20,y:0});assert.deepEqual(result.points.at(-1),{x:180,y:0});
});
test('narrow routing channels and device order give deterministic results without mutation',()=>{
  const input=base();input.obstacles.push(rectangle('Top',55,-80,45,65),rectangle('Bottom',110,15,40,65));
  const before=JSON.stringify(input),result=route(input);assert.equal(result.blocked,false);assertGeometry(result,input);
  assert.deepEqual(route({...input,obstacles:[...input.obstacles].reverse()}),result);
  assert.equal(JSON.stringify(input),before);
});
test('search has a hard visit budget and reports blocked when no fallback lane is clear',()=>{
  const input={source:{x:0,y:0,normal:right},target:{x:200,y:0,normal:left},maxVisited:1,
    obstacles:[rectangle('north',-40,-40,100,10),rectangle('south',-40,30,100,10),rectangle('west',-40,-40,10,80),rectangle('east',50,-40,10,80)]};
  const result=route(input);assert.equal(result.blocked,true);assert.equal(result.reason,'search-budget');assert.equal(result.visited,1);
});
test('invalid or oversized geometry never yields nonfinite SVG and is not silently ignored',()=>{
  assert.equal(route({source:{x:NaN,y:0},target:{x:0,y:0}}).reason,'invalid-endpoint');
  assert.equal(route({...base(),obstacles:[rectangle('bad',50,0,-1,5)]}).reason,'invalid-obstacle');
  assert.equal(route({...base(),obstacles:Array.from({length:257},(_,i)=>rectangle(String(i),50,i,1,1))}).reason,'obstacle-budget');
});
test('a dense sixty-four-device page routes through a gap within the fixed search limit',()=>{
  const input={source:{x:-50,y:0,normal:right},target:{x:1050,y:0,normal:left},obstacles:[]};
  for(let row=0;row<8;row++)for(let col=0;col<8;col++)input.obstacles.push(rectangle('n'+row+'-'+col,col*120,row*90-300,50,50));
  const result=route(input);assert.equal(result.blocked,false);assert.ok(result.visited<=12000);assertGeometry(result,input);
});
