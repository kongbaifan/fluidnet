import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const host=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/workbench-refresh.js',import.meta.url),'utf8'),host);

// A small surface implementing only DOM operations used by this public controller.
function element(dataset={}) {
  const attributes=new Map(),classes=new Set();
  return {dataset,attributes,classes,style:{},textContent:'',innerHTML:'',
    setAttribute:(key,value)=>attributes.set(key,String(value)),
    classList:{toggle:(key,on)=>{if(on)classes.add(key);else classes.delete(key);}},
    querySelector:()=>null,querySelectorAll:()=>[]};
}
function fixture() {
  const page={id:'main',zoom:1,nodes:[{id:'A'},{id:'B'}],edges:[['local','A','out','B','in']]};
  const owner={id:'plant',run:{status:'ready'}},ui={route:'workbench',showLibrary:true,showChart:false,canvasMode:'select'};
  const nodes=page.nodes.map(n=>element({node:n.id})),edges=[element({canvasEdge:'local'})];
  const svg=element({project:owner.id,page:page.id}),shell=element(),area=element(),zoom=element(),hint=element(),library=element(),toggleChart=element();
  svg.querySelectorAll=selector=>selector==='[data-node]'?nodes:selector==='[data-canvas-edge]'?edges:[];
  const commands=Object.fromEntries(['run','pause','step','stop'].map(command=>{
    const button=element({command});button.label=element();button.querySelector=selector=>selector==='span'?button.label:null;return [command,button];
  }));
  const calls=[],single=new Map([['#network',svg],['.workbench',shell],['#network-area',area],['.zoom > span',zoom],['[data-canvas-hint]',hint]]);
  const groups=new Map([['.runbar [data-command]',Object.values(commands)],['.canvas-tools [data-action="toggle-library"]',[library]],['.runbar [data-action="toggle-chart"]',[toggleChart]]]);
  single.set('.canvas-info',{insertAdjacentHTML:()=>{calls.push('insert-chart');single.set('.workbench-chart',element());}});
  const root={querySelector:key=>single.get(key)||null,querySelectorAll:key=>groups.get(key)||[]};
  const controller=host.window.FluidNetWorkbenchRefresh.create({root,project:()=>owner,page:()=>page,ui,viewBox:()=> '0 0 100 100',
    canvas:()=>({refresh:()=>calls.push('canvas')}),selection:()=>calls.push('selection'),chartMarkup:()=>'<section></section>',
    chartRefresh:()=>calls.push('chart'),layout:()=>calls.push('layout'),chrome:()=>calls.push('chrome'),icon:name=>name,history:()=>false,placingName:()=> 'Pump'});
  return {controller,owner,page,ui,svg,shell,area,zoom,hint,library,toggleChart,commands,calls,nodes,edges,single};
}

test('foreign routes, projects and pages refuse local repaint without touching their DOM',()=>{
  for(const change of [f=>{f.ui.route='editor';},f=>{f.owner.id='another';},f=>{f.page.id='other-page';},f=>{f.single.delete('#network');},f=>{f.single.delete('.workbench');}]) {
    const f=fixture();change(f);assert.equal(f.controller.refresh(),false);
    assert.deepEqual(f.calls,[]);assert.equal(f.svg.attributes.size,0);assert.equal(f.shell.classes.size,0);
  }
});

test('added, removed or replaced nodes and local edges require structural render',()=>{
  for(const change of [f=>f.page.nodes.push({id:'C'}),f=>f.page.nodes.pop(),f=>{f.page.nodes[1]={id:'C'};},
    f=>f.page.edges.push(['new','A','out','B','in']),f=>f.page.edges.pop(),f=>{f.page.edges[0][0]='replacement';}]) {
    const f=fixture();change(f);assert.equal(f.controller.refresh(),false);assert.deepEqual(f.calls,[]);
    assert.equal(f.svg.attributes.size,0);
  }
});

test('cross-page connections do not force repaint when only their local endpoints are drawn',()=>{
  const f=fixture();f.page.edges.push(['outgoing','B','out','REMOTE','in'],['incoming','REMOTE','out','A','in']);
  assert.equal(f.controller.refresh(),true);assert.equal(f.svg.attributes.get('viewBox'),'0 0 100 100');
  assert.equal(f.calls.filter(item=>item==='selection').length,1);assert.equal(f.calls.filter(item=>item==='canvas').length,1);
  // A mistakenly rendered remote edge cannot be treated as a valid local path.
  f.edges.push(element({canvasEdge:'outgoing'}));f.calls.length=0;
  assert.equal(f.controller.refresh(),false);assert.deepEqual(f.calls,[]);
});

test('local runtime refresh updates control availability through the full lifecycle',()=>{
  const f=fixture(),expected={
    ready:['run','step'],running:['pause','stop'],solving:['stop'],paused:['run','step','stop'],
    completed:['run','step','stop'],failed:['run','step','stop'],stopped:['run','step'],
  };
  for(const [status,enabled] of Object.entries(expected)) {
    f.owner.run.status=status;f.calls.length=0;assert.equal(f.controller.refresh(),true);
    assert.deepEqual(Object.entries(f.commands).filter(([,button])=>!button.disabled).map(([name])=>name),enabled,status);
    assert.equal(f.commands.run.label.textContent,status==='paused'?'继续':'运行');
    assert.equal(f.calls.filter(item=>item==='selection').length,1);assert.equal(f.calls.filter(item=>item==='canvas').length,1);
  }
});

test('display toggles retain the original canvas and chart while syncing their visible state',()=>{
  const f=fixture(),svg=f.svg;
  Object.assign(f.ui,{showChart:true,showLibrary:false,pageGrid:true,placing:'pump'});f.page.zoom=1.25;
  assert.equal(f.controller.refresh(),true);const chart=f.single.get('.workbench-chart');
  assert.equal(f.single.get('#network'),svg);assert.equal(f.zoom.textContent,'125%');assert.match(f.hint.textContent,/Pump/);
  assert.equal(f.shell.classes.has('show-library'),false);assert.equal(f.area.classes.has('grid'),true);
  assert.equal(f.library.attributes.get('aria-expanded'),'false');assert.equal(f.toggleChart.attributes.get('aria-expanded'),'true');
  f.ui.showChart=false;assert.equal(f.controller.refresh(),true);assert.equal(chart.hidden,true);
  f.ui.showChart=true;assert.equal(f.controller.refresh(),true);assert.equal(chart.hidden,false);
  assert.equal(f.single.get('.workbench-chart'),chart);assert.equal(f.calls.filter(item=>item==='insert-chart').length,1);
});
