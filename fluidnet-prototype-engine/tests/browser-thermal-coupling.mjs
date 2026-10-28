import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

const dir=mkdtempSync(join(tmpdir(),'fluidnet-coupling-'));
const storageKey='fluidnet-prototype-engine-v1', errors=[];
const browser=await chromium.launch({channel:'msedge',headless:true});
let launched,base,context,page;
async function start(){
  launched=await launchEngine({args:['--data-dir',join(dir,'data')],env:{FLUIDNET_MODULE_STORE:join(dir,'modules')}});
  base=launched.base;
  context=await browser.newContext({...FHD_CONTEXT});
  page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#projects');
  await expect(page.locator('.rail-link[data-route="projects"]')).toBeVisible();
}
const api=async(path,body)=>{
  const response=await fetch(base+'/api/v1'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  expect(response.ok,await response.clone().text()).toBe(true);return response.json();
};
async function finished(id){
  let record;
  await expect(async()=>{
    record=await api('/runs/'+id);
    if(record.status==='failed')throw Error(JSON.stringify(record.frame));
    expect(record.status).toBe('completed');
  }).toPass({timeout:120000,intervals:[100,250,500]});
  return record;
}
async function run(){
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);
  const id=(await response.json()).run_id, record=await finished(id);
  await expect(page.locator('[data-coupled-heat]')).toHaveText((record.frame.variables['coupling.HX1.heat_w']/1000).toFixed(3),{timeout:20000});
  await expect(page.locator('[data-action="run-project"][data-command="run"]').first()).toBeEnabled({timeout:20000});
  return {id,record,body:response.request().postDataJSON()};
}
async function save(){
  const saved=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await saved).ok()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
}
try{
  await start();
  const model=await api('/examples/thermal-coupling');
  await expect(async()=>{
    if(await page.locator('.thermal-coupling').isVisible().catch(()=>false))return;
    await page.locator('[data-action="cs-create-coupled"]').click();
    await expect(page.locator('.thermal-coupling')).toBeVisible({timeout:4000});
  }).toPass({timeout:30000});
  const draft=(await page.evaluate(k=>JSON.parse(localStorage.getItem(k)),storageKey)).projects.find(p=>p.caseId===model.id);
  expect(draft.thermalCouplings).toEqual(model.thermal_couplings);
  expect(draft.fluidConfig).toEqual(model.fluid);
  expect(draft.circuitFluids.map(c=>c.fluidConfig)).toEqual(model.circuit_fluids.map(c=>c.fluid));
  expect(draft.solverOptions).toEqual(model.solver);
  const id=draft.id;
  await page.locator('.rail-link[data-route="settings"]').click();
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="duration"]').fill('2');await page.locator('[data-solver-field="duration"]').blur();
  await page.locator('[data-solver-field="dt"]').fill('1');await page.locator('[data-solver-field="dt"]').blur();
  await page.locator('.rail-link[data-route="workbench"]').click();
  const first=await run();
  expect(first.body.project.fluid).toEqual(model.fluid);
  expect(first.body.project.thermal_couplings).toEqual(model.thermal_couplings);
  expect(first.body.trend_variables).toContain('coupling.HX1.heat_w');
  expect(first.body.project.solver).toEqual(model.solver);
  expect(Math.abs(first.record.frame.variables['coupling.HX1.equation_residual_w'])).toBeLessThan(.01);
  // The editable coupling changes the model key: old results must become stale before rerunning.
  await page.locator('[data-action="cs-coupling"]').click();
  await page.getByRole('dialog').locator('input[name="ua"]').fill('900');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('[data-result-status]').first()).toContainText('参数已变更');
  await page.locator('[data-wf-scenario]').selectOption('warm_load');
  const changed=await run();
  expect(changed.body.project.thermal_couplings[0].ua_w_k).toBe(900);
  expect(changed.record.frame.variables['WL1.param.ambient_temperature_k']).toBeCloseTo(313.15,8);
  await save();
  mkdirSync('artifacts',{recursive:true});
  await captureFhd(page, 'artifacts/thermal-coupling-run.png');
  await launched.stop();await context.close();await start();
  await page.locator(`.project-preview[data-id="${id}"]`).click();
  await expect(page.locator('.thermal-coupling')).toBeVisible();
  const replay=await run();
  expect(replay.record.frame.variables).toEqual(changed.record.frame.variables);
  expect(replay.body.project.fluid).toEqual(model.fluid);
  const accepted=await api(`/projects/${id}/runs`,{mode:'dynamic',duration_s:2,dt_s:1,scenario_id:'warm_load'});
  const savedRun=await finished(accepted.run_id);
  expect(savedRun.frame.variables).toEqual(changed.record.frame.variables);
  expect(savedRun.request.project_revision).toBeGreaterThan(0);
  expect(errors).toEqual([]);
  console.log(JSON.stringify({projectId:id,runs:[first.id,changed.id,replay.id,accepted.run_id],heat_w:savedRun.frame.variables['coupling.HX1.heat_w'],errors}));
}catch(error){
  console.error(error);process.exitCode=1;
  mkdirSync('artifacts',{recursive:true});
  await captureFhd(page, 'artifacts/thermal-coupling-failure.png').catch(()=>{});
}finally{await browser.close();await launched?.stop();}
