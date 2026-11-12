import {chromium,expect} from '@playwright/test';
import {mkdtempSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[],evidence={cases:[]};
page.on('pageerror',error=>errors.push(error.message));
const directory=mkdtempSync(join(tmpdir(),'fluidnet-engineering-canvas-'));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const run=command=>page.locator(`[data-action="run-project"][data-command="${command}"]`).first();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
const edge=id=>page.locator(`[data-canvas-edge="${id}"]`);
const metadata=id=>edge(id).locator('metadata');
const api=async path=>{const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();};
const active=state=>state.projects.find(p=>p.id===state.activeProject);
const physics=p=>({modules:p.moduleSnapshots,pages:p.pages.map(pg=>({id:pg.id,edges:pg.edges,nodes:pg.nodes.map(n=>({id:n.id,moduleId:n.moduleId,params:n.params,draft:n.draft}))})),fluid:p.fluid,circuitFluids:p.circuitFluids,solver:p.solver});
async function save(){
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await receipt).ok()).toBe(true);
  return active((await api('/workspace')).data);
}
async function importProject(project){
  const file=join(directory,project.id+'.json');writeFileSync(file,JSON.stringify(project));
  await nav('projects');await page.locator('[data-action="wf-import"]').click();
  await page.getByLabel('单项目文件').setInputFiles(file);await submit();await expect(page.locator('#toast')).toContainText('项目已导入');
  await nav('workbench');await expect(page.locator('.net-node[data-node="V1"]')).toBeVisible();
}
async function step(){
  const started=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await run('step').click();const response=await started;expect(response.ok(),await response.text()).toBe(true);const id=(await response.json()).run_id;
  let record;
  await expect.poll(async()=>{record=await api('/runs/'+id);return ['paused','failed'].includes(record.status);},{timeout:20000}).toBe(true);
  expect(record.status,JSON.stringify({status:record.status,frame:record.frame})).toBe('paused');
  await expect(page.locator('#statusbar')).toContainText('已暂停');await expect(page.locator('[data-canvas-legend]')).toContainText('采样');
  return {id,record:await api('/runs/'+id)};
}
function project(definitions,id,opening=.7,left=250000,right=120000){
  return {schema_version:1,id,name:'工程画布验收 '+id,fluid:{fluid:'Water',phase_policy:'liquid'},modules:definitions,
    instances:[{id:'B1',module_id:'source',name:'左边界',parameters:{pressure_pa:left,temperature_k:293.15},position:{x:140,y:220}},
      {id:'V1',module_id:'valve',name:'试验调节阀',parameters:{opening_ratio:opening,kv_m3_h:16},position:{x:500,y:220}},
      {id:'B2',module_id:'source',name:'右边界',parameters:{pressure_pa:right,temperature_k:313.15},position:{x:860,y:220}}],
    connections:[{id:'left',source:{instance_id:'B1',port_id:'out0'},target:{instance_id:'V1',port_id:'in0'}},
      {id:'right',source:{instance_id:'V1',port_id:'out0'},target:{instance_id:'B2',port_id:'out0'}}],
    solver:{thermal:true,property_coupling:'reference',dynamic_step_s:.1}};
}
try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  const definitions=(await api('/catalog')).modules.filter(m=>['source','valve'].includes(m.id));
  for(const [name,opening,left,right,direction] of [['forward',.7,250000,120000,1],['reverse-connection',.7,250000,120000,-1],['closed',0,250000,120000,0]]){
    const input=project(definitions,name,opening,left,right);
    // An edge's source/target is an editing convention, not a physical one-way constraint.
    if(direction===-1)for(const connection of input.connections)[connection.source,connection.target]=[connection.target,connection.source];
    await importProject(input);
    await page.locator('[data-canvas-mode]').selectOption('flow');await page.locator('[data-canvas-labels]').check();
    for(const id of ['left','right']){await expect(metadata(id)).toHaveAttribute('data-edge-known','false');await expect(metadata(id)).toHaveAttribute('data-edge-direction','unknown');}
    await expect(page.locator('.canvas-flow-animation')).toHaveCount(0);
    const result=await step(),flow=result.record.frame.variables['V1.mass_flow_kg_s'];
    if(direction)expect(flow).toBeGreaterThan(0);else expect(Math.abs(flow)).toBeLessThan(1e-8);
    for(const id of ['left','right']){
      await expect(metadata(id)).toHaveAttribute('data-edge-known','true');await expect(metadata(id)).toHaveAttribute('data-edge-direction',String(direction));
      await expect(metadata(id)).toHaveAttribute('data-route-blocked','false');
      expect(await edge(id).locator('[data-flow-arrow]').count()).toBe(direction?1:0);
    }
    const before=physics(await save());
    await page.locator('[data-canvas-mode]').selectOption('temperature');
    await expect(edge('right').locator('.canvas-edge-label')).toContainText('°C');
    const connection=input.connections.find(c=>c.id==='right'),upstream=direction<0?connection.target:connection.source;
    const temperature=result.record.frame.variables[upstream.instance_id+'.'+upstream.port_id+'.temperature_k'];
    if(Number.isFinite(temperature))expect(await edge('right').locator('.canvas-edge-label').textContent()).toContain(String(Number((temperature-273.15).toPrecision(5))));
    await page.locator('[data-canvas-mode]').selectOption('pressure');
    await expect(edge('right').locator('.canvas-edge-label')).toContainText('kPa(abs)');
    await page.locator('[data-action="canvas-range"]').click();await page.getByRole('dialog').locator('[name="max"]').fill('100');await submit();
    await expect(edge('right').locator('[data-trace-edge]')).toHaveCSS('stroke','rgb(186, 61, 61)');
    expect(physics(await save())).toEqual(before);
    if(name==='forward'){
      await page.locator('[data-canvas-mode]').selectOption('flow');await page.locator('[data-canvas-animation]').check();
      await run('run').click();await expect(run('pause')).toBeEnabled();
      await expect.poll(()=>page.locator('.canvas-flow-animation').count(),{timeout:15000}).toBeGreaterThan(0);
      await page.locator('[data-canvas-animation]').uncheck();await expect(page.locator('.canvas-flow-animation')).toHaveCount(0);
      await page.locator('[data-canvas-animation]').check();
      await run('pause').click();await expect(run('pause')).toBeDisabled();await expect(page.locator('.canvas-flow-animation')).toHaveCount(0);
      await captureFhd(page,'artifacts/engineering-canvas-flow-1080p.png');
    }
    await run('stop').click();await expect(run('stop')).toBeDisabled();
    const persisted=await save();await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
    await nav('workbench');expect(physics(await save())).toEqual(physics(persisted));
    if(name==='forward'){
      // A saved parameter change after the run makes its old physical overlay obsolete.
      await page.locator('.net-node[data-node="V1"]').dblclick();
      await page.locator('[data-float-id="V1"] [data-instance-param="opening_ratio"]').fill('40');
      await page.locator('[data-float-id="V1"] [data-action="apply-instance"]').click();await submit();
      await expect(page.locator('[data-canvas-legend]')).toContainText('结果已过期');
      await expect(metadata('left')).toHaveAttribute('data-edge-direction','unknown');await expect(page.locator('.canvas-flow-animation')).toHaveCount(0);
      await page.locator('[data-float-id="V1"] [data-action="float-close"]').click();
    }
    evidence.cases.push({name,flow,direction,units:true,displayDoesNotChangePhysics:true,reload:true});
  }
  // This existing model deliberately warns when a legal zero-length input needs its numerical lower bound.
  // It executes in a real Worker, so alert ownership is tested without injected UI data.
  const capillary=(await api('/modules/capillary_tube/versions/1')).module;
  delete capillary.package;delete capillary.validation_evidence;
  const warning=project([...definitions.filter(m=>m.id==='source'),capillary],'warning');
  warning.instances[1].module_id='capillary_tube';warning.instances[1].parameters={length_m:0,diameter_m:.0015};
  await importProject(warning);const result=await step();
  expect(result.record.frame.diagnostics.some(d=>d.code==='CAP_LENGTH_CLAMPED'&&d.instance_id==='V1')).toBe(true);
  await expect(page.locator('.net-node[data-node="V1"]')).toHaveAttribute('data-canvas-state','warning');
  await page.locator('[data-action="canvas-alerts"]').click();await expect(page.getByRole('dialog')).toContainText('CAP_LENGTH_CLAMPED');
  await page.getByRole('dialog').locator('[data-action="canvas-locate-alert"][data-id="V1"]').first().click();
  await expect(page.locator('[data-float-id="V1"]')).toBeVisible();await captureFhd(page,'artifacts/engineering-canvas-alert-1080p.png');
  await run('stop').click();await expect(run('stop')).toBeDisabled();
  // A known initialization boundary is checked as a real failure, not accepted as a reverse-flow solution.
  await importProject(project(definitions,'reverse-pressure-boundary',.7,120000,250000));
  const failedRequest=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await run('step').click();const failedId=(await(await failedRequest).json()).run_id;
  await expect.poll(async()=>(await api('/runs/'+failedId)).status,{timeout:15000}).toBe('failed');
  await expect(page.locator('[data-action="canvas-alerts"]')).not.toContainText('运行告警 0');
  await expect(metadata('left')).toHaveAttribute('data-edge-known','false');await expect(page.locator('.canvas-flow-animation')).toHaveCount(0);
  await page.locator('[data-action="canvas-alerts"]').click();await expect(page.getByRole('dialog')).toContainText('HYDRAULIC_NOT_CONVERGED');
  await expect(page.getByRole('dialog').locator('[data-action="canvas-locate-alert"]')).toHaveCount(0);
  await captureFhd(page,'artifacts/engineering-canvas-initialization-failure-1080p.png');
  expect(errors).toEqual([]);Object.assign(evidence,{warningLocated:true,staleDisabled:true,liveAnimation:true,initializationFailureUnknown:true,errors});
  mkdirSync('artifacts',{recursive:true});writeFileSync('artifacts/engineering-canvas-evidence.json',JSON.stringify(evidence,null,2)+'\n');console.log(JSON.stringify(evidence));
}catch(error){console.error(error,errors);await captureFhd(page,'artifacts/engineering-canvas-failure-1080p.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
