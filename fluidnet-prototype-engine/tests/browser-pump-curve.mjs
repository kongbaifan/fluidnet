import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[],output='artifacts/pump-curve';
mkdirSync(output,{recursive:true});page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=async()=>{await page.locator('#dialog-form [type="submit"]').click();await expect(page.locator('#dialog-form')).toHaveCount(0);};
const cancel=()=>page.locator('#dialog-form [data-action="close-dialog"]').last().click();
const cell=(row,axis)=>page.locator(`[data-curve-row="${row}"][data-curve-axis="${axis}"]`);
const state=()=>page.evaluate(async()=>(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
const owner=s=>s.projects.find(p=>p.id===s.activeProject),pump=s=>owner(s).pages.flatMap(p=>p.nodes).find(n=>n.id==='P1');
async function save(){const r=page.waitForResponse(r=>r.url().endsWith('/workspace')&&r.request().method()==='POST');await page.locator('[data-action="save"]').first().click();expect((await r).ok()).toBe(true);return state();}
async function api(path){const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();}
async function panel(){await page.locator('.net-node[data-node="P1"]').dblclick();const p=page.getByRole('region',{name:'P1 设备参数',exact:true});await p.locator('[data-action="float-tab"][data-value="parameters"]').click();const d=p.locator('.device-other-parameters');if(await d.getAttribute('open')===null)await d.locator('summary').first().click();return p;}
async function openCurve(p){const d=p.locator('.device-other-parameters');if(await d.getAttribute('open')===null)await d.locator('summary').first().click();await p.locator('[data-action="edit-pump-curve"]').click();}
async function run(command,status){const r=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');await page.locator(`[data-action="run-project"][data-command="${command}"]`).first().click();const response=await r;expect(response.ok(),await response.text()).toBe(true);const {run_id}=await response.json();let record;await expect.poll(async()=>{record=await api('/runs/'+run_id);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:45000}).toBe(status);await expect(page.locator('#statusbar')).toContainText(status==='paused'?'已暂停':'已完成');return record;}
try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="start-modeling"]').first().click();await page.locator('[data-float-id="V1"] [data-action="float-close"]').click();
  let p=await panel(),before=pump(await save());const original=[];
  await openCurve(p);await expect(page.locator('[data-curve-plot] svg')).toBeVisible();
  for(let i=0;i<await page.locator('[data-curve-rows] tr').count();i++)original.push([Number(await cell(i,0).inputValue()),Number(await cell(i,1).inputValue())]);
  await cell(0,1).fill('50');await cancel();expect(pump(await save())).toEqual(before);
  await openCurve(p);await expect(cell(0,1)).toHaveValue(String(original[0][1]));
  await cell(1,0).fill('0');await expect(page.locator('[data-curve-validation]')).toContainText('第 2 行：流量必须大于上一行');
  await expect(page.locator('#dialog-form [type="submit"]')).toBeDisabled();await expect(page.locator('[data-curve-plot] svg')).toHaveCount(0);
  await cell(1,0).fill(String(original[1][0]));await cell(1,1).fill('');await expect(cell(1,1)).toHaveAttribute('aria-invalid','true');
  await cell(1,1).fill(String(original[1][1]));await page.locator('[data-curve-insert="0"]').click();
  await expect(page.locator('[data-curve-rows] tr')).toHaveCount(original.length+1);await expect(page.locator('#dialog-form [type="submit"]')).toBeEnabled();
  await page.locator('[data-curve-remove="1"]').click();await page.locator('[data-curve-add]').click();
  await expect(page.locator('#dialog-form [type="submit"]')).toBeDisabled();await page.locator(`[data-curve-remove="${original.length}"]`).click();
  const points=original.map(([q,h])=>[q,Number((h*1.1).toPrecision(10))]);for(let i=0;i<points.length;i++)await cell(i,1).fill(String(points[i][1]));
  await captureFhd(page,output+'/point-table.png');await submit();
  let s=await save();expect(pump(s).params.head_curve).toEqual(before.params.head_curve);expect(pump(s).draft.head_curve).toEqual(points);
  await p.locator('[data-action="apply-instance"]').click();await cancel();expect(pump(await save()).params.head_curve).toEqual(before.params.head_curve);
  await p.locator('[data-action="apply-instance"]').click();await submit();expect(pump(await save()).params.head_curve).toEqual(points);
  await p.locator('[data-action="float-close"]').click();const record=await run('step','paused');
  expect(record.request.project.instances.find(n=>n.id==='P1').parameters.head_curve).toEqual(points);
  expect(record.frame.variables['P1.in0.mass_flow_kg_s']).toBeGreaterThan(0);
  p=await panel();await expect(p.locator('[data-action="edit-pump-curve"]')).toBeDisabled();await p.locator('[data-action="float-close"]').click();
  await page.locator('[data-action="run-project"][data-command="stop"]').first().click();await expect(page.locator('[data-action="run-project"][data-command="stop"]').first()).toBeDisabled();
  await save();await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');p=await panel();
  await p.locator('[data-action="edit-pump-curve"]').click();for(let i=0;i<points.length;i++)await expect(cell(i,1)).toHaveValue(String(points[i][1]));await cancel();await p.locator('[data-action="float-close"]').click();
  // The same table also edits the reusable Python pump template's default, through real publication.
  await nav('modules');await page.locator('[data-action="new-module"]').click();
  await page.locator('#dialog-form [name="name"]').fill('点表循环泵');await page.locator('#dialog-form [name="code"]').fill('TABLE_PUMP');
  await page.locator('#dialog-form [name="base"]').selectOption('template:pump');await submit();
  await page.locator('.editor-tabs [data-value="attributes"]').click();await page.locator('[data-action="edit-module-parameter"][data-id="head_curve"]').click();
  const count=await page.locator('[data-curve-rows] tr').count(),modulePoints=[];
  for(let i=0;i<count;i++){const q=Number(await cell(i,0).inputValue()),h=Number((Number(await cell(i,1).inputValue())*1.05).toPrecision(10));modulePoints.push([q,h]);await cell(i,1).fill(String(h));}
  await submit();const publish=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');await page.locator('[data-action="save-module-version"]').click();
  const response=await publish,body=await response.json();expect(response.status(),JSON.stringify(body)).toBe(201);
  expect(body.module.parameters.find(p=>p.id==='head_curve').default).toEqual(modulePoints);
  await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();await save();await page.reload();
  await expect(page.locator('[data-action="edit-module-parameter"][data-id="head_curve"]')).toBeVisible();await page.locator('[data-action="edit-module-parameter"][data-id="head_curve"]').click();
  for(let i=0;i<count;i++)await expect(cell(i,1)).toHaveValue(String(modulePoints[i][1]));await cancel();
  expect(errors).toEqual([]);writeFileSync(output+'/evidence.json',JSON.stringify({passed:true,points,modulePoints,runId:record.id,flow:record.frame.variables['P1.in0.mass_flow_kg_s'],cancelPreserved:true,reloaded:true},null,2)+'\n');
  console.log('Pump curve editor passed: validation, preview, insert/remove, cancel, draft/apply, real run, runtime lock, publication and reload.');
}catch(error){await captureFhd(page,output+'/failure.png');throw error;}
finally{await browser.close();await server.close();}
