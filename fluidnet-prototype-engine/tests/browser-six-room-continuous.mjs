import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const out=resolve('artifacts/six-room-continuous/browser');mkdirSync(out,{recursive:true});
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true}),errors=[],summary={};
page.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(e.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const api=async path=>{const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();};
async function save(){
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/v1/workspace')&&r.request().method()==='POST');
 await page.locator('[data-action="save"]').first().click();expect((await pending).ok()).toBe(true);
 const data=(await api('/workspace')).data;return data.projects.find(p=>p.id===data.activeProject);
}
async function waitRun(id,predicate){
 let record;await expect.poll(async()=>{record=await api('/runs/'+id);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return predicate(record);},{timeout:180000}).toBe(true);return record;
}
const command=name=>page.locator(`[data-action="run-project"][data-command="${name}"]`).first().click();
try{
 await page.goto(server.base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 await page.getByRole('button',{name:'六库持续仿真',exact:true}).click();
 await expect(page.locator('[data-room-status]')).toHaveCount(6);
 await expect(page.locator('[data-continuous-plant]')).toContainText('全站持续运行');
 let owner=await save();expect(owner.pages.flatMap(p=>p.nodes)).toHaveLength(126);
 expect(owner.controllers).toHaveLength(21);expect(owner.controlScripts).toHaveLength(2);
 summary.projectId=owner.id;
 await nav('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
 await expect(page.locator('[data-solver-continuous]')).toBeChecked();
 await expect(page.locator('[data-solver-field="duration"]')).toBeDisabled();
 await nav('controls');await page.locator('[data-live-mode]').selectOption('fast');await nav('workbench');
 const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
 await command('run');const response=await pending;expect(response.ok(),await response.text()).toBe(true);
 expect(response.request().postDataJSON().duration_s).toBeNull();
 const id=(await response.json()).run_id;summary.runId=id;
 await waitRun(id,r=>r.frame?.time_s>=60);await command('pause');
 let record=await waitRun(id,r=>r.status==='paused');const pausedTime=record.frame.time_s;
 await expect(page.locator('[data-room-status="F01"]')).not.toContainText('运行后查看');
 await expect(page.locator('[data-continuous-plant]')).toContainText('LT_PUMP2：停机');
 await command('step');record=await waitRun(id,r=>r.status==='paused'&&r.frame.time_s===pausedTime+30);
 expect(Math.abs(record.frame.metrics.energy_residual_j)).toBeLessThan(.1);
 await command('run');await waitRun(id,r=>r.frame.time_s>=pausedTime+60);await command('pause');
 record=await waitRun(id,r=>r.status==='paused');summary.pauseResume={pausedTime,continuedTime:record.frame.time_s};
 for(const pageId of ['plant','frozen-a','frozen-b','chilled']){
  await page.locator(`[data-action="canvas-tab"][data-id="${pageId}"]`).click();await page.locator('[data-action="fit"]').click();
  await captureFhd(page,join(out,pageId+'.png'));
 }
 await command('stop');record=await waitRun(id,r=>r.status==='cancelled');
 expect(record.checkpoint_available).toBe(true);summary.checkpointTime=record.checkpoint_time_s;
 await nav('runs');await page.locator('[data-action="refresh-archives"]').click();
 await page.locator(`[data-action="open-archive"][data-id="${id}"]`).click();
 await page.locator(`[data-action="resume-archive"][data-id="${id}"]`).click();
 await page.getByLabel('续算终止时刻').fill(String(record.frame.time_s+60));
 const resumed=page.waitForResponse(r=>r.url().endsWith(`/runs/${id}/resume`)&&r.request().method()==='POST');
 await page.getByRole('dialog').locator('button[type="submit"]').click();
 const child=(await(await resumed).json()).run_id;summary.resumedRunId=child;
 await waitRun(child,r=>r.status==='paused');await command('step');
 await waitRun(child,r=>r.status==='paused'&&r.frame.time_s===record.frame.time_s+30);
 await command('stop');await waitRun(child,r=>r.status==='cancelled');
 owner=await save();await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${owner.id}"]`).click();
 const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
 const filename=join(out,'six-room-continuous.studio.json');await(await download).saveAs(filename);
 await page.locator('[data-action="close-dialog"]').last().click();
 await page.locator('[data-action="wf-import"]').click();await page.getByLabel('单项目文件').setInputFiles(filename);
 // Import a copy: the original remains available without allocating a second
 // full replacement backup inside the browser's limited local storage.
 await page.getByRole('dialog').locator('[name="mode"]').selectOption('copy');
 await page.getByRole('dialog').locator('button[type="submit"]').click();
 await expect(page.locator('#toast')).toContainText('项目已导入');await save();
 await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');await nav('workbench');
 owner=await save();expect(owner.pages.flatMap(p=>p.nodes)).toHaveLength(126);expect(owner.controllers).toHaveLength(21);
 await expect(page.locator('[data-room-status]')).toHaveCount(6);
 expect(errors).toEqual([]);summary.errors=errors;summary.exportImportReload=true;
 writeFileSync(join(out,'summary.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
}catch(error){console.error(error);console.error('toast',await page.locator('#toast').textContent().catch(()=>''));await captureFhd(page,join(out,'failure.png'));process.exitCode=1;}
finally{await browser.close();await server.close();}
