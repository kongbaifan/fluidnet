import {chromium,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtempSync,writeFileSync,mkdirSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir,cpus,platform,release} from 'node:os';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const counts=process.argv.includes('--quick')?[30,64]:[30,64,100,300];
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[],metrics=[];
page.on('pageerror',error=>errors.push(error.message));
// Instrument only browser timing; the application project and run state are never patched by this probe.
await page.addInitScript(()=>{
  window.__canvasPerformanceProbe={active:null,observer:null};
  try{const observer=new PerformanceObserver(list=>{
    const active=window.__canvasPerformanceProbe.active;
    if(active)for(const item of list.getEntries())if(item.startTime>=active.started)active.longTasks.push({startTime:item.startTime,duration:item.duration});
  });observer.observe({type:'longtask',buffered:false});window.__canvasPerformanceProbe.observer=observer;}catch{}
});
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
const frame=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
const node=id=>page.locator(`#network [data-node="${id}"]`);
const position=id=>node(id).evaluate(el=>{const matrix=el.transform.baseVal.consolidate().matrix;return {x:matrix.e,y:matrix.f};});
const quantile=(values,q)=>{if(!values.length)return null;const sorted=[...values].sort((a,b)=>a-b);return sorted[Math.min(sorted.length-1,Math.ceil(q*sorted.length)-1)];};
const summary=values=>({samples:values.length,p50:quantile(values,.5),p95:quantile(values,.95),max:values.length?Math.max(...values):null});
async function measured(label,callback){
  await page.evaluate(label=>{
    const probe=window.__canvasPerformanceProbe,active={label,started:performance.now(),frames:[],longTasks:[]};probe.active=active;
    const tick=time=>{if(probe.active!==active)return;active.frames.push(time);requestAnimationFrame(tick);};requestAnimationFrame(tick);
  },label);
  const started=performance.now();await callback();await frame();
  const observed=await page.evaluate(()=>{
    const probe=window.__canvasPerformanceProbe,active=probe.active;
    for(const item of probe.observer?.takeRecords()||[])if(item.startTime>=active.started)active.longTasks.push({startTime:item.startTime,duration:item.duration});
    probe.active=null;return {...active,browserWallMs:performance.now()-active.started};
  });
  const frameGaps=observed.frames.slice(1).map((t,i)=>t-observed.frames[i]);
  return {label,automationWallMs:performance.now()-started,browserWallMs:observed.browserWallMs,
    frameGapMs:summary(frameGaps),rawFrameGapsMs:frameGaps,longTaskCount:observed.longTasks.length,
    longTaskDurationMs:observed.longTasks.reduce((sum,t)=>sum+t.duration,0)};
}
async function save(){
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await receipt).ok()).toBe(true);
  const data=await(await page.request.get(server.base+'/api/v1/workspace')).json();return data.data.projects.find(p=>p.id===data.data.activeProject);
}
async function bodyPoint(id){
  return node(id).evaluate(el=>{
    for(const [x,y] of [[0,0],[0,-3],[8,0],[-8,0],[0,3]]){
      const p=new DOMPoint(x,y).matrixTransform(el.getScreenCTM()),hit=document.elementFromPoint(p.x,p.y);
      if(hit?.closest('[data-node]')===el&&!hit.closest('[data-port-node],[data-quick-node]'))return {x:p.x,y:p.y};
    }
    throw Error('No unobstructed device body: '+el.dataset.node);
  });
}
async function checkConnections(connections){
  const failures=await page.locator('#network').evaluate((svg,connections)=>{
    const mismatch=[];
    for(const edge of connections){
      const path=svg.querySelector(`[data-trace-edge="${CSS.escape(edge.id)}"]`);if(!path)continue;
      const targets=[edge.source,edge.target];
      for(let i=0;i<2;i++){
        const target=targets[i],port=svg.querySelector(`[data-port-node="${CSS.escape(target.instance_id)}"][data-port-id="${CSS.escape(target.port_id)}"] .net-port`);
        if(!port){mismatch.push(edge.id+':missing-port');continue;}
        const center=new DOMPoint(Number(port.getAttribute('cx')),Number(port.getAttribute('cy'))).matrixTransform(port.getScreenCTM());
        const point=path.getPointAtLength(i?path.getTotalLength():0),end=new DOMPoint(point.x,point.y).matrixTransform(path.getScreenCTM());
        if(!Number.isFinite(end.x+end.y)||Math.hypot(center.x-end.x,center.y-end.y)>.2)mismatch.push(edge.id+':endpoint'+i);
      }
    }
    return mismatch;
  },connections);
  expect(failures).toEqual([]);
}
async function drag(id,other,dx,dy,connections){
  const before=await position(id),still=await position(other),p=await bodyPoint(id);
  const handle=await node(id).elementHandle(),child=await handle.$('.node-hit'),otherHandle=await node(other).elementHandle();
  await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+dx,p.y+dy,{steps:24});await frame();
  expect(await handle.evaluate(el=>el.isConnected&&document.querySelector(`#network [data-node="${el.dataset.node}"]`)===el)).toBe(true);
  expect(await child.evaluate(el=>el.isConnected)).toBe(true);expect(await otherHandle.evaluate(el=>el.isConnected)).toBe(true);
  const during=await position(id);expect(Math.hypot(during.x-before.x,during.y-before.y)).toBeGreaterThan(1);
  expect(await position(other)).toEqual(still);await checkConnections(connections.filter(c=>c.source.instance_id===id||c.target.instance_id===id));
  await page.mouse.up();await frame();const after=await position(id);expect(after).toEqual(during);
  await checkConnections(connections);await handle.dispose();await child.dispose();await otherHandle.dispose();return {before,after};
}
async function blankPoint(){
  return page.locator('#network').evaluate(svg=>{
    const r=svg.getBoundingClientRect();
    for(let y=r.y+100;y<r.bottom-95;y+=29)for(let x=r.right-180;x>r.x+100;x-=47){
      const hit=document.elementFromPoint(x,y);
      if(hit?.closest('#network')===svg&&!hit.closest('[data-node],[data-edge],[data-canvas-edge]'))return {x,y};
    }
    throw Error('No unobstructed canvas area for pan');
  });
}
try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  const response=await page.request.get(server.base+'/api/v1/catalog');expect(response.ok()).toBe(true);
  const definitions=(await response.json()).modules.filter(m=>['source','pipe'].includes(m.id));
  const directory=mkdtempSync(join(tmpdir(),'fluidnet-canvas-performance-'));
  for(const count of counts){
    const p={schema_version:1,id:'canvas-size-'+count,name:'画布交互参考 '+count,fluid:{fluid:'Water',phase_policy:'liquid'},modules:definitions,instances:[],connections:[],solver:{thermal:false,hydraulic_method:'auto'}};
    for(let i=0;i<count;i++)p.instances.push({id:'Part'+i,module_id:i===0||i===count-1?'source':'pipe',name:'设备 '+i,page_id:'page'+Math.floor(i/64),parameters:i===0?{pressure_pa:250000}:i===count-1?{pressure_pa:120000}:{length_m:1,diameter_m:.05},position:{x:90+(i%8)*130,y:90+(Math.floor(i/8)%8)*110}});
    for(let i=1;i<count;i++)p.connections.push({id:'edge'+i,source:{instance_id:'Part'+(i-1),port_id:'out0'},target:{instance_id:'Part'+i,port_id:i===count-1?'out0':'in0'}});
    const file=join(directory,'size-'+count+'.json');writeFileSync(file,JSON.stringify(p));console.log('Fixture:',file);
    await nav('projects');await page.locator('[data-action="wf-import"]').click();await page.getByLabel('单项目文件').setInputFiles(file);await submit();await expect(page.locator('#toast')).toContainText('项目已导入');
    await nav('workbench');await page.locator('[data-action="canvas-tab"][data-id="page0"]').click();await page.locator('[data-action="fit"]').click();await frame();
    await expect(page.locator('#network [data-node]')).toHaveCount(Math.min(count,64));
    const visibleConnections=p.connections.filter(c=>Number(c.target.instance_id.slice(4))<64),rounds=[];
    await checkConnections(visibleConnections);
    for(let round=0;round<3;round++){
      const operations=[],initialA=await position('Part9'),initialB=await position('Part10');let movedA,movedB;
      operations.push(await measured('drag-Part9',async()=>{movedA=await drag('Part9','Part10',-12,-8,visibleConnections);}));
      operations.push(await measured('drag-Part10',async()=>{movedB=await drag('Part10','Part9',12,8,visibleConnections);}));
      await page.locator('[data-action="undo"]').click();await expect.poll(()=>position('Part10')).toEqual(initialB);
      await page.locator('[data-action="undo"]').click();await expect.poll(()=>position('Part9')).toEqual(initialA);
      await checkConnections(visibleConnections);
      await page.locator('[data-action="redo"]').click();await expect.poll(()=>position('Part9')).toEqual(movedA.after);
      await page.locator('[data-action="redo"]').click();await expect.poll(()=>position('Part10')).toEqual(movedB.after);
      operations.push(await measured('pan',async()=>{const old=await page.locator('#network').getAttribute('viewBox'),start=await blankPoint();await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(start.x+28,start.y+16,{steps:24});await page.mouse.up();await expect(page.locator('#network')).not.toHaveAttribute('viewBox',old);}));
      operations.push(await measured('zoom-in-out',async()=>{const old=await page.locator('#network').getAttribute('viewBox');await page.locator('[data-action="zoom-in"]').click();await expect(page.locator('#network')).not.toHaveAttribute('viewBox',old);await page.locator('[data-action="zoom-out"]').click();}));
      await checkConnections(visibleConnections);expect(await position('Part9')).toEqual(movedA.after);expect(await position('Part10')).toEqual(movedB.after);
      const stored=await save(),nodes=stored.pages.flatMap(p=>p.nodes);expect(nodes).toHaveLength(count);
      expect({x:nodes.find(n=>n.id==='Part9').x,y:nodes.find(n=>n.id==='Part9').y}).toEqual(movedA.after);
      expect({x:nodes.find(n=>n.id==='Part10').x,y:nodes.find(n=>n.id==='Part10').y}).toEqual(movedB.after);
      rounds.push({round:round+1,operations,nodeIdentityPreservedDuringDrag:true,undoRedoPositions:true,endpointsMatch:true});
    }
    const gaps=rounds.flatMap(r=>r.operations.flatMap(o=>o.rawFrameGapsMs));
    metrics.push({totalInstances:count,pageCount:Math.ceil(count/64),visibleNodes:await page.locator('#network [data-node]').count(),
      visibleEdges:await page.locator('#network [data-canvas-edge]').count(),complexity:'Two-port built-in water pipe chain with pressure boundaries; no running simulation or complex Python/refrigeration nodes',
      rounds,aggregateFrameGapMs:summary(gaps),longTaskCount:rounds.reduce((s,r)=>s+r.operations.reduce((n,o)=>n+o.longTaskCount,0),0)});
    console.log(JSON.stringify({count,frameGapMs:metrics.at(-1).aggregateFrameGapMs,longTasks:metrics.at(-1).longTaskCount}));
  }
  expect(errors).toEqual([]);await captureFhd(page,'artifacts/canvas-performance-1080p.png');
  const commit=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8',windowsHide:true}).trim();
  const dirtyPaths=execFileSync('git',['diff','--name-only','--','frontend'],{encoding:'utf8',windowsHide:true}).trim().split(/\r?\n/).filter(Boolean);
  const sourceHashes=Object.fromEntries(['frontend/studio.js','frontend/canvas-view.js','frontend/canvas-workspace.js','frontend/canvas-routing.js','frontend/canvas-symbols.js',
    'frontend/canvas-observations.js','frontend/canvas-view.css','frontend/project-model.js','tests/browser-canvas-performance.mjs'].map(path=>[path,createHash('sha256').update(readFileSync(path)).digest('hex')]));
  mkdirSync('artifacts',{recursive:true});writeFileSync('artifacts/canvas-performance-metrics.json',JSON.stringify({capturedAt:new Date().toISOString(),commit,dirtyPaths,
    sourceHashes,environment:{node:process.version,platform:platform(),release:release(),cpu:cpus()[0]?.model,logicalProcessors:cpus().length},
    browser:browser.version(),viewport:FHD_CONTEXT,quick:counts.length===2,
    hostLoadNote:process.env.FLUIDNET_BENCH_LOAD_NOTE||'Other development-host activity is not controlled; concurrent browser or compute work can affect these observations.',
    measurementScope:'Three automated interaction rounds per size. Frame intervals and long tasks are observations, not an FPS/SLA guarantee. Headless Edge on the development host; wall time includes automation and assertions.',metrics,errors},null,2)+'\n');
}catch(error){console.error(error);await captureFhd(page,'artifacts/canvas-performance-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
