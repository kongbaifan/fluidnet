import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const context=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/canvas-symbols.js',import.meta.url),context);
const api=context.window.FluidNetCanvasSymbols,plain=x=>JSON.parse(JSON.stringify(x));
const device=(kind,ports=[{id:'in0',direction:'in',domain:'fluid',x:20,y:50},{id:'out0',direction:'out',domain:'fluid',x:80,y:50}])=>
  ({id:kind,kind,name:kind,ports,drawing:{shape:'rectangle',width:32,height:30,label:kind}});

test('refrigeration and HVAC equipment have distinguishable engineering symbols',()=>{
  const expected={design_pump:'pump',dx_compressor:'compressor',air_source_heat_pump:'heat-pump',air_cooled_chiller:'chiller',
    horizontal_drum:'horizontal-tank',headed_receiver:'horizontal-tank',lp_drum:'tank',air_cooler:'coil',defrost_air_cooler:'coil',
    cold_room_multi:'room',refrigerant_header:'header',fan_performance:'fan',cooling_tower_moist:'tower',
    air_cooled_condenser:'condenser',water_coil:'coil',immersed_tube_bundle:'exchanger',plate_exchanger:'exchanger',
    pressure_independent_valve:'valve',check_valve:'check',porous_filter:'filter',hydronic_boiler:'heater',
    refrigerant_line:'pipe'};
  for(const [kind,family] of Object.entries(expected)){
    const m=device(kind),before=JSON.stringify(m),svg=api.symbol({id:'Device'},m);
    assert.equal(api.family(m),family,kind);assert.match(svg,new RegExp(`data-canvas-family="${family}"`));
    assert.doesNotMatch(svg,/ƒ/);assert.equal(JSON.stringify(m),before);
  }
  const group=device('my_custom_group');group.manifest={composite:{children:[]},solver_model:'generic'};
  assert.equal(api.family(group),'group');assert.match(api.symbol({},group),/stroke-dasharray/);
});

test('author shape dimensions and port coordinates use the drawing editor coordinate system',()=>{
  const m=device('custom');m.drawing={shape:'circle',width:60,height:55,label:'定制设备'};
  m.ports[0].x=10;m.ports[0].y=20;const before=JSON.stringify(m);
  const b=api.bodyBounds({},m),point=api.portOffset({},m,m.ports[0]);
  assert.equal(b.width,54);assert.equal(b.height,33);
  assert.ok(Math.abs(point.x+43.2)<1e-10);assert.ok(Math.abs(point.y+19.35)<1e-10);
  assert.match(api.symbol({},m),/<ellipse rx="27" ry="16.5"/);assert.match(api.symbol({},m),/定制设备/);
  assert.equal(JSON.stringify(m),before);
});

test('dense and overlapping author ports remain distinct without modifying stored coordinates',()=>{
  for(const count of [4,8,16,24]){
    const m=device('header',Array.from({length:count},(_,i)=>({id:'p'+i,direction:'in',domain:'fluid',x:20,y:i%2?70:30}))),before=JSON.stringify(m);
    const points=m.ports.map(p=>api.portOffset({},m,p)),box=api.hitBounds({},m);
    for(let i=0;i<points.length;i++)for(let j=0;j<i;j++)assert.ok(Math.hypot(points[i].x-points[j].x,points[i].y-points[j].y)>=12-.001);
    for(const p of points)assert.ok(p.x>box.x&&p.x<box.x+box.width&&p.y>box.y&&p.y<box.y+box.height);
    assert.ok(api.labelY({},m)>Math.max(...points.map(p=>p.y)));assert.equal(JSON.stringify(m),before);
  }
  const m=device('custom',[{id:'a',x:5,y:10,direction:'in'},{id:'b',x:10,y:10,direction:'out'},{id:'c',x:10,y:10,direction:'in'}]);
  const points=m.ports.map(p=>api.portOffset({},m,p));
  for(let i=0;i<points.length;i++)for(let j=0;j<i;j++)assert.ok(Math.hypot(points[i].x-points[j].x,points[i].y-points[j].y)>=12-.001);
});

test('legacy boundary and junction orientation is preserved until the author moves a port',()=>{
  const source=device('source',[{id:'out0',direction:'out',x:78,y:50}]);
  assert.deepEqual(plain(api.portOffset({id:'B1'},source,source.ports[0])),{x:28,y:0});
  assert.deepEqual(plain(api.portOffset({id:'B2'},source,source.ports[0])),{x:-28,y:0});
  source.ports[0].x=50;source.ports[0].y=10;
  assert.deepEqual(plain(api.portOffset({id:'B2'},source,source.ports[0])),{x:0,y:-25.8});
  const junction=device('junction',[{id:'in0',direction:'in',x:20,y:50},{id:'out0',direction:'out',x:80,y:30},{id:'out1',direction:'out',x:80,y:70}]);
  assert.deepEqual(plain(api.portOffset({id:'N2'},junction,junction.ports[0])),{x:24,y:0});
  assert.deepEqual(plain(api.portOffset({id:'N2'},junction,junction.ports[1])),{x:-24,y:-18});
});

test('symbols own one rotation while port and body geometry stays local',()=>{
  const m=device('design_pump'),node={id:'P1',rotation:90};
  assert.match(api.symbol(node,m),/transform="rotate\(90\)"/);
  assert.equal((api.symbol(node,m).match(/transform=/g)||[]).length,1);
  assert.deepEqual(plain(api.portOffset(node,m,m.ports[0])),plain(api.portOffset({...node,rotation:0},m,m.ports[0])));
  assert.ok(api.labelY(node,m)>api.portOffset(node,m,m.ports[1]).x);
  m.ports[1].x=95;assert.ok(api.labelY(node,m)>api.portOffset(node,m,m.ports[1]).x);
});

test('presentation copy preserves matching ports and executable hashes without aliasing',()=>{
  const source=device('custom'),target=device('custom');source.drawing={shape:'circle',width:50,height:45,label:'作者图形'};
  source.ports[0].x=35;source.ports[0].y=15;target.ports[1].domain='thermal';
  source.manifest={content_hash:'old',definition_hash:'old'};target.manifest={content_hash:'new',definition_hash:'new'};
  const prior=JSON.stringify(source);assert.equal(api.copyPresentation(source,target),target);
  assert.deepEqual(plain(target.drawing),source.drawing);assert.equal(target.ports[0].x,35);assert.equal(target.ports[1].domain,'thermal');assert.equal(target.ports[1].x,80);
  assert.deepEqual(target.manifest,{content_hash:'new',definition_hash:'new'});
  target.drawing.width=30;target.ports[0].x=20;assert.equal(JSON.stringify(source),prior);
});

test('unknown labels and malformed numeric presentation cannot inject markup or invalid coordinates',()=>{
  const m=device('unknown');m.name=m.drawing.label='<script>alert("x")</script>';
  m.ports[0].x='" onload="x';m.ports[0].y=Infinity;
  const svg=api.symbol({rotation:'" onload="x'},m,{esc:s=>s});
  assert.doesNotMatch(svg,/<script|onload=/);assert.match(svg,/&lt;script&gt;/);assert.match(svg,/rotate\(0\)/);
  const p=api.portOffset({},m,m.ports[0]);assert.ok(Number.isFinite(p.x)&&Number.isFinite(p.y));
  assert.doesNotMatch(api.symbol({},undefined),/undefined|NaN|ƒ/);
});
