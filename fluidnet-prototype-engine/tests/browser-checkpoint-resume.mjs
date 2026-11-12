import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[];
page.setDefaultTimeout(20000);page.on('pageerror',error=>errors.push(error.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const stored=()=>page.evaluate(async()=>
  (await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
const active=state=>state.projects.find(project=>project.id===state.activeProject);
const api=async path=>{const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();};
async function save(){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/workspace')&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await response).ok()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
  return stored();
}
async function waitStatus(id,status){
  await expect.poll(async()=>{const record=await api('/runs/'+id);if(record.status==='failed')throw Error(JSON.stringify(record.frame));return record.status;},{timeout:60000}).toBe(status);
}
try {
  await page.goto(server.base);
  await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="start-modeling"]').click();
  await nav('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('input[data-solver-field="duration"]').fill('1');
  await page.locator('input[data-solver-field="dt"]').fill('0.1');await save();
  await nav('workbench');
  const created=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const sourceId=(await(await created).json()).run_id;
  console.log('source',sourceId);await waitStatus(sourceId,'completed');await expect(page.locator('#statusbar')).toContainText('已完成');
  const originalRecord=await api('/runs/'+sourceId);
  expect(originalRecord.checkpoint_available).toBe(true);expect(originalRecord.checkpoint_time_s).toBe(1);
  // Preserve a workspace version that has since diverged from the frozen run.
  await nav('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('input[data-solver-field="duration"]').fill('11');
  await page.locator('input[data-solver-field="duration"]').press('Tab');
  const before=await save(),original=active(before),originalPages=JSON.stringify(original.pages);
  await nav('runs');await page.locator('[data-action="refresh-archives"]').click();
  await page.locator(`[data-action="open-archive"][data-id="${sourceId}"]`).click();
  await page.locator(`[data-action="resume-archive"][data-id="${sourceId}"]`).click();
  await page.getByLabel('续算终止时刻').fill('1');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('#dialog-error')).toContainText('终止时刻');
  await page.getByLabel('续算终止时刻').fill('2');
  const resumed=page.waitForResponse(r=>r.url().endsWith(`/runs/${sourceId}/resume`)&&r.request().method()==='POST');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  const response=await resumed;expect(response.ok(),await response.text()).toBe(true);
  expect(response.request().postDataJSON()).toEqual({duration_s:2,start_paused:true});
  const childId=(await response.json()).run_id;await waitStatus(childId,'paused');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('#statusbar')).toContainText('已暂停');
  const after=await save(),copy=active(after),preserved=after.projects.find(p=>p.id===original.id);
  expect(after.projects.length).toBe(before.projects.length+1);
  expect(copy.id).not.toBe(original.id);expect(copy.run.runId).toBe(childId);expect(copy.run.time).toBe(1);
  expect(copy.solver.duration).toBe(2);expect(preserved.solver.duration).toBe(11);
  expect(JSON.stringify(preserved.pages)).toBe(originalPages);
  expect(copy.moduleSnapshots).toBeTruthy();
  const first=(await api('/runs/'+childId+'/history')).rows[0];
  expect(first.time_s).toBe(1);expect(first.variables).toEqual(originalRecord.frame.variables);
  await page.locator('[data-action="run-project"][data-command="step"]').first().click();
  await expect.poll(async()=>(await api('/runs/'+childId)).frame.time_s).toBeCloseTo(1.1,8);
  await waitStatus(childId,'paused');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  await waitStatus(childId,'completed');await expect(page.locator('#statusbar')).toContainText('已完成');
  expect((await api('/runs/'+childId)).frame.time_s).toBe(2);
  expect(errors).toEqual([]);
  mkdirSync('artifacts/foundation',{recursive:true});await captureFhd(page,'artifacts/foundation/checkpoint-resume.png');
  const summary={sourceId,childId,start:1,step:1.1,end:2,independentProject:copy.id,originalDraftPreserved:true,errors};
  writeFileSync('artifacts/foundation/checkpoint-resume.json',JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
} catch(error) {
  mkdirSync('artifacts/foundation',{recursive:true});await captureFhd(page,'artifacts/foundation/checkpoint-resume-failure.png');
  console.error('Page errors:',errors);throw error;
} finally {await browser.close();await server.close();}
