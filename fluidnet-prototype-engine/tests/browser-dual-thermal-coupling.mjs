import {FHD_CONTEXT, FHD_VIEWPORT, captureFhd} from './browser-viewport.mjs';
import {chromium, expect} from '@playwright/test';
import {mkdirSync, mkdtempSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';

const dir=mkdtempSync(join(tmpdir(),'fluidnet-dual-coils-'));
const storageKey='fluidnet-prototype-engine-v1', errors=[],responses=[];
const browser=await chromium.launch({channel:'msedge',headless:true});
let launched,base,context,page;
async function start(){
  launched=await launchEngine({args:['--data-dir',join(dir,'data')],env:{FLUIDNET_MODULE_STORE:join(dir,'modules')}});
  base=launched.base;context=await browser.newContext({...FHD_CONTEXT});
  page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{responses.push([new URL(response.url()).pathname,response.status()]);if(responses.length>30)responses.shift();});
  await page.goto(base+'/#projects');
  await expect(page.locator('[data-action="cs-create-dual"]')).toBeVisible();
}
const dialog=()=>page.getByRole('dialog');
const closeDialog=async()=>{if(await dialog().count())await dialog().locator('[data-action="close-dialog"]').first().click();};
const state=()=>page.evaluate(key=>JSON.parse(localStorage.getItem(key)),storageKey);
async function save(){
  const saved=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();
  const response=await saved;expect(response.ok(),await response.text()).toBe(true);
  const all=await state();return all.projects.find(p=>p.id===all.activeProject);
}
async function api(path,body){
  const response=await page.request.fetch(base+'/api/v1'+path,{method:body===undefined?'GET':'POST',data:body});
  expect(response.ok(),await response.text()).toBe(true);return response.json();
}
async function finished(id){
  let result;
  await expect(async()=>{
    result=await api('/runs/'+id);
    if(result.status==='failed')throw Error(JSON.stringify(result.frame));
    expect(result.status).toBe('completed');
  }).toPass({timeout:120000,intervals:[100,250,500]});
  return result;
}
async function configureShortRun(){
  await page.locator('.rail-link[data-route="settings"]').click();
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  for(const [name,value] of [['duration','2'],['dt','1']]){
    const input=page.locator(`[data-solver-field="${name}"]`);await input.fill(value);await input.blur();
  }
  await page.locator('.rail-link[data-route="workbench"]').click();
}
async function run(){
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  posted.catch(()=>{});
  await page.locator('[data-action="run-project"][data-command="run"]').first().click({timeout:10000});
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);
  const id=(await response.json()).run_id,record=await finished(id);
  for(const link of record.request.project.thermal_couplings){
    await expect(page.locator(`[data-coupling-id="${link.id}"] [data-coupled-heat]`))
      .toHaveText((record.frame.variables[`coupling.${link.id}.heat_w`]/1000).toFixed(3),{timeout:20000});
  }
  if(record.request.project.thermal_couplings.length===2){
    await expect(page.locator('[data-coupled-total-heat]')).toHaveText((record.frame.metrics.coupling_heat_w/1000).toFixed(3));
    const sum=record.request.project.thermal_couplings.reduce((total,link)=>total+record.frame.variables[`coupling.${link.id}.heat_w`],0);
    expect(record.frame.metrics.coupling_heat_w).toBeCloseTo(sum,8);
  }
  await expect(page.locator('[data-action="run-project"][data-command="run"]').first()).toBeEnabled();
  return {id,record,body:response.request().postDataJSON()};
}
async function openRelation(id){
  await page.locator('[data-action="cs-coupling"]').click();
  const edit=dialog().locator(`[data-action="cs-edit-coupling"][data-coupling="${id}"]`);
  if(await edit.count())await edit.click();
  await expect(dialog().getByLabel('关系标识',{exact:true})).toHaveValue(id);
}
async function createExample(topology){
  await page.locator('.rail-link[data-route="projects"]').click();
  await page.locator('[data-action="cs-create-dual"]').click();
  await dialog().getByLabel('双盘管拓扑').selectOption(topology);
  await dialog().locator('button[type="submit"]').click();
  await expect(page.locator('[data-coupling-id]')).toHaveCount(2,{timeout:30000});
  await configureShortRun();return save();
}

try{
  await start();
  const parallel=await createExample('parallel');
  expect(parallel.thermalCouplings.map(link=>link.id)).toEqual(['HX1','HX2']);
  const first=await run();
  expect(first.record.frame.variables['WP1.mass_flow_kg_s']).toBeCloseTo(
    first.record.frame.variables['coupling.HX1.mass_flow_kg_s']+first.record.frame.variables['coupling.HX2.mass_flow_kg_s'],8);
  expect(first.body.trend_variables).toContain('metrics.coupling_heat_w');

  // Duplicate IDs cannot overwrite the other coil, and used pipes are excluded.
  await openRelation('HX2');
  const pipes=await dialog().getByLabel('液体管段',{exact:true}).locator('option').evaluateAll(options=>options.map(o=>o.value));
  expect(pipes).not.toContain('HX_W');
  await dialog().getByLabel('关系标识',{exact:true}).fill('HX1');
  await dialog().locator('button[type="submit"]').click();
  await expect(dialog().locator('#dialog-error')).toContainText('标识');
  await dialog().getByLabel('关系标识',{exact:true}).fill('HX2');
  await dialog().getByLabel('换热能力 UA · W/K',{exact:true}).fill('900');
  await dialog().locator('button[type="submit"]').click();
  const changedDraft=await save();
  expect(changedDraft.thermalCouplings[0]).toEqual(parallel.thermalCouplings[0]);
  expect(changedDraft.thermalCouplings[1].ua_w_k).toBe(900);
  await expect(page.locator('[data-coupled-total-heat]')).toHaveText('—');
  const changed=await run();
  expect(changed.record.frame.metrics.coupling_heat_w).not.toBe(first.record.frame.metrics.coupling_heat_w);
  expect((await api('/runs/'+first.id)).request.project.thermal_couplings[1].ua_w_k).toBe(1400);

  // Deleting one endpoint removes only its relation; undo/redo restores both maps.
  await page.locator('[data-node="HX_W2"]').first().click();
  await page.locator('[data-action="delete-node"][data-id="HX_W2"]').first().click();
  await expect(dialog()).toContainText('HX2');
  await dialog().locator('button[type="submit"]').click();
  expect((await save()).thermalCouplings.map(link=>link.id)).toEqual(['HX1']);
  await expect(page.locator('[data-coupling-id="HX1"]')).toBeVisible();
  await expect(page.locator('[data-coupling-id="HX2"]')).toHaveCount(0);
  await page.locator('[data-action="undo"]').first().click();
  expect((await save()).thermalCouplings).toEqual(changedDraft.thermalCouplings);
  await page.locator('[data-action="redo"]').first().click();
  expect((await save()).thermalCouplings.map(link=>link.id)).toEqual(['HX1']);
  await page.locator('[data-action="undo"]').first().click();

  // Remove/add the second relation without touching either device or the first binding.
  await openRelation('HX2');
  await dialog().getByRole('button',{name:'移除热耦合',exact:true}).click();
  await dialog().getByRole('button',{name:'解除关系',exact:true}).click();
  expect((await save()).thermalCouplings.map(link=>link.id)).toEqual(['HX1']);
  await expect(page.locator('[data-node="HX_W2"]').first()).toBeVisible();
  await openRelation('HX1');
  await dialog().getByRole('button',{name:'新增关系',exact:true}).click();
  await dialog().getByLabel('关系标识',{exact:true}).fill('HX2');
  await dialog().getByLabel('液体管段',{exact:true}).selectOption('HX_W2');
  await dialog().getByLabel('换热能力 UA · W/K',{exact:true}).fill('900');
  await dialog().locator('button[type="submit"]').click();
  const restored=await save();
  expect(restored.thermalCouplings).toEqual(changedDraft.thermalCouplings);
  await page.locator('[data-action="cs-coupling"]').click();
  await expect(dialog().getByRole('button',{name:'新增关系',exact:true})).toBeDisabled();
  await closeDialog();

  // A copied project has independent relation and chart objects with its own IDs.
  await page.locator('.rail-link[data-route="projects"]').click();
  await page.locator(`[data-action="duplicate-project"][data-id="${parallel.id}"]`).click();
  const copiedState=await state(),copy=copiedState.projects.find(p=>p.name===parallel.name+' 副本');
  expect(copy).toBeTruthy();expect(copy.thermalCouplings).toEqual(restored.thermalCouplings);
  const originalCharts=copiedState.charts.extra.filter(c=>c.projectId===parallel.id),copyCharts=copiedState.charts.extra.filter(c=>c.projectId===copy.id);
  expect(copyCharts.map(c=>c.canonicalKey)).toEqual(originalCharts.map(c=>c.canonicalKey));
  expect(copyCharts.some(c=>originalCharts.some(original=>original.id===c.id))).toBe(false);
  await page.locator(`.project-preview[data-id="${copy.id}"]`).click();
  await openRelation('HX2');await dialog().getByLabel('换热能力 UA · W/K',{exact:true}).fill('800');
  await dialog().locator('button[type="submit"]').click();await save();
  expect((await state()).projects.find(p=>p.id===parallel.id).thermalCouplings[1].ua_w_k).toBe(900);
  await run();

  const independent=await createExample('independent'),independentRun=await run();
  expect(independentRun.body.project.circuit_fluids.map(c=>c.fluid.fluid)).toEqual(['Ammonia','Water','INCOMP::MEG[0.3]']);
  expect(independentRun.record.frame.variables['HX_W2.in0.density_kg_m3']).toBeGreaterThan(independentRun.record.frame.variables['HX_W.in0.density_kg_m3']);
  expect(independentRun.record.frame.variables['WP1.mass_flow_kg_s']).toBeCloseTo(independentRun.record.frame.variables['coupling.HX1.mass_flow_kg_s'],8);
  expect(independentRun.record.frame.variables['WP2.mass_flow_kg_s']).toBeCloseTo(independentRun.record.frame.variables['coupling.HX2.mass_flow_kg_s'],8);
  await save();mkdirSync('artifacts',{recursive:true});
  await captureFhd(page, 'artifacts/dual-thermal-coupling.png');
  await page.setViewportSize(FHD_VIEWPORT);await openRelation('HX2');
  await expect(dialog().getByLabel('液体管段',{exact:true})).toBeInViewport();
  await expect(dialog().locator('button[type="submit"]')).toBeInViewport();
  await captureFhd(page, 'artifacts/dual-thermal-editor-1080p.png');await closeDialog();
  await launched.stop();await context.close();await start();
  await page.locator(`.project-preview[data-id="${independent.id}"]`).click();
  const replay=await run();expect(replay.record.frame.variables).toEqual(independentRun.record.frame.variables);
  const saved=await api(`/projects/${independent.id}/runs`,{mode:'dynamic',duration_s:2,dt_s:1,scenario_id:'rated'});
  expect((await finished(saved.run_id)).frame.variables).toEqual(independentRun.record.frame.variables);
  expect(errors).toEqual([]);
  console.log(JSON.stringify({projects:[parallel.id,copy.id,independent.id],totalHeat:independentRun.record.frame.metrics.coupling_heat_w,errors}));
}catch(error){
  console.error(error,errors,responses,await page?.locator('#toast').textContent().catch(()=>''),launched?.log());process.exitCode=1;
  mkdirSync('artifacts',{recursive:true});await captureFhd(page, 'artifacts/dual-thermal-failure.png').catch(()=>{});
}finally{await browser.close();await launched?.stop();}
