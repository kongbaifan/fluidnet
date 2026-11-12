import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const out=resolve('artifacts/large-cold-store/usability');mkdirSync(out,{recursive:true});
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true}),errors=[],summary={runs:{}};
page.setDefaultTimeout(15000);
page.on('pageerror',e=>errors.push(e.message));
const nav=r=>page.locator(`.rail-link[data-route="${r}"]`).click();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
const api=async path=>{const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();};
const stored=()=>page.evaluate(async()=>{const {FluidNetDraftStore}=await import('/draft-store.js');return FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));});
const active=state=>state.projects.find(p=>p.id===state.activeProject);
async function reloadWorkspace(){
 const loaded=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='GET',{timeout:30000});
 loaded.catch(()=>{});
 await page.reload();expect((await loaded).ok()).toBe(true);
 await expect(page.locator('#app-header')).toContainText('模块平台 · v',{timeout:30000});
}
async function save(){
 const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/workspace')&&r.request().method()==='POST');
 response.catch(()=>{});
 await page.locator('[data-action="save"]').first().click();expect((await response).ok()).toBe(true);
 await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
 await expect(page.locator('[data-save-status]')).not.toContainText('失败');
 return active((await api('/workspace')).data);
}
async function run(id){
 await nav('workbench');await page.locator('[data-wf-scenario]').selectOption(id);
 const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
 response.catch(()=>{});
 await page.locator('[data-action="run-project"][data-command="run"]').first().click();
 const posted=await response;expect(posted.ok(),await posted.text()).toBe(true);const rid=(await posted.json()).run_id;
 let record;await expect.poll(async()=>{record=await api('/runs/'+rid);if(record.status==='failed')throw Error(JSON.stringify(record.frame));return record.status;},{timeout:120000}).toBe('completed');
 await expect(page.locator('#statusbar')).toContainText('已完成');
 await expect(page.locator('[data-room-status="F01"]')).not.toContainText('运行后查看');
 await expect(page.locator('[data-save-status]')).not.toContainText('失败');
 summary.runs[id]={id:rid,time_s:record.frame.time_s,temperature_c:record.frame.variables['F01.state.temperature_k']-273.15,
   fan:record.frame.variables['F01_AC2.param.fan_ratio'],power_w:record.frame.metrics.electric_power_w};
 if(id==='cooler-off')await expect(page.locator('[data-room-status="F01"]')).toContainText('制冷已到上限');
 await captureFhd(page,join(out,id+'.png'));
 await page.locator('[data-action="run-project"][data-command="stop"]').first().click();
 await nav('runs');await page.locator('[data-action="refresh-archives"]').click();
 await page.locator(`[data-action="open-archive"][data-id="${rid}"]`).click();
 for(const format of ['html','csv']){
  const downloaded=page.waitForEvent('download');await page.locator(`[data-action="archive-report"][data-id="${rid}"][data-format="${format}"]`).click();
  await(await downloaded).saveAs(join(out,id+'.'+format));
 }
 await save();console.log('completed',id,summary.runs[id]);
 return record;
}
try{
 await page.goto(server.base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 await page.getByRole('button',{name:'六库自动温控',exact:true}).click();
 await expect(page.locator('[data-room-status]')).toHaveCount(6);
 let owner=await save();expect(owner.pages.flatMap(p=>p.nodes)).toHaveLength(51);expect(owner.controllers).toHaveLength(19);
 summary.projectId=owner.id;console.log('created',owner.id);
 // Real copy, internal connection, and undo on the six-room project.
 await page.locator('[data-action="project-group-tools"]').click();
 for(const checkbox of await page.getByRole('dialog').locator('input[type="checkbox"]').all())await checkbox.uncheck();
 for(const id of ['F01','F01_AC1'])await page.getByLabel('组选择 '+id,{exact:true}).check();
 await page.getByRole('dialog').locator('[name="group-action"]').selectOption('copy');
 await page.getByLabel('设备组目标画布').selectOption('frozen-b');await submit();
 await expect(page.getByRole('dialog')).toContainText('1 条内部连线');await submit();
 expect((await save()).pages.flatMap(p=>p.nodes)).toHaveLength(53);
 await page.locator('[data-action="undo"]').click();expect((await save()).pages.flatMap(p=>p.nodes)).toHaveLength(51);
 summary.copyAndUndo=true;console.log('copied and undone',JSON.stringify({controllers:(await save()).controllers?.length,errors}));
 for(const scenario of ['baseline','load-step','lower-load','cooler-off'])await run(scenario);
 await nav('workbench');await page.locator('[data-action="cs-room-targets"]').click();
 await page.getByLabel('冷冻库 1 / °C',{exact:true}).fill('-23');await submit();
 await expect(page.locator('[data-modular-cold-status]')).toContainText('配置已变更');
 owner=await save();expect(owner.controllers.filter(c=>c.measurement==='F01.state.temperature_k').every(c=>c.setpoint===250.15)).toBe(true);
 await reloadWorkspace();
 await nav('workbench');await page.locator('[data-action="cs-room-targets"]').click();
 await expect(page.getByLabel('冷冻库 1 / °C',{exact:true})).toHaveValue('-23');
 await page.getByLabel('冷冻库 1 / °C',{exact:true}).fill('-24');await submit();
 summary.targetReload=true;
 // Export and replace the same large project, exercising the old raw-backup failure.
 await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${owner.id}"]`).click();
 const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
 const filename=join(out,'six-room-controlled.studio.json');await(await download).saveAs(filename);
 await page.locator('[data-action="close-dialog"]').last().click();
 for(let i=0;i<2;i++){
  await page.locator('[data-action="wf-import"]').click();await page.getByLabel('单项目文件').setInputFiles(filename);
  await page.getByRole('dialog').locator('[name="mode"]').selectOption('replace');await submit();
  await expect(page.locator('#toast')).toContainText('项目已导入');await save();
 }
 summary.repeatedReplace=true;
 // Failed server save still leaves a recoverable local edit.
 await nav('workbench');await page.locator('[data-action="cs-room-targets"]').click();
 await page.getByLabel('冷冻库 1 / °C',{exact:true}).fill('-23.5');await submit();
 await page.route('**/api/v1/workspace',route=>route.request().method()==='POST'?route.fulfill({status:507,contentType:'application/json',body:JSON.stringify({detail:'injected save refusal'})}):route.continue());
 const refusal=page.waitForResponse(r=>r.url().endsWith('/api/v1/workspace')&&r.request().method()==='POST');
 await page.locator('[data-action="save"]').first().click();expect((await refusal).status()).toBe(507);
 await expect(page.locator('[data-save-status]')).toContainText('保存失败');
 await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 await nav('workbench');await page.locator('[data-action="cs-room-targets"]').click();
 await expect(page.getByLabel('冷冻库 1 / °C',{exact:true})).toHaveValue('-23.5');
 await page.getByLabel('冷冻库 1 / °C',{exact:true}).fill('-24');await submit();await page.unroute('**/api/v1/workspace');await save();
 summary.failedSaveRecovery=true;
 // Cached archived results must reload their full curve when requested.
 const cache=await stored(),cached=cache.records.find(r=>r.archiveCacheOnly);
 if(cached){
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');await nav('runs');
  await page.locator(`[data-action="select-record"][data-id="${cached.id}"]`).first().click();
  const fetched=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/v1/runs/${cached.id}/overview`);
  await page.locator(`[data-action="record-curves"][data-id="${cached.id}"]`).click();expect((await fetched).ok()).toBe(true);
  summary.archiveReload=true;
 }
 expect(errors).toEqual([]);summary.errors=errors;summary.localChars=await page.evaluate(()=>localStorage.getItem('fluidnet-prototype-engine-v1').length);
 writeFileSync(join(out,'summary.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
}catch(error){console.error(error);console.error('toast:',await page.locator('#toast').textContent().catch(()=>''));await captureFhd(page,join(out,'failure.png')).catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
