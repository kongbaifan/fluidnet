import {chromium,expect} from '@playwright/test';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const out=resolve('artifacts/large-cold-store/workspace');mkdirSync(out,{recursive:true});
const project=JSON.parse(readFileSync('examples/large-cold-store/six-room.project.json','utf8'));
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true}),errors=[],runs={};
page.on('pageerror',error=>errors.push(error.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
const api=async path=>{const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();};
const active=async()=>{const data=(await api('/workspace')).data;return data.projects.find(p=>p.id===data.activeProject);};
async function save(){
 const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
 await page.locator('[data-action="save"]').first().click();expect((await receipt).ok()).toBe(true);
 await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
 return active();
}
async function run(scenario){
 await nav('workbench');await page.locator('[data-wf-scenario]').selectOption(scenario);
 const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
 await page.locator('[data-action="run-project"][data-command="run"]').first().click();
 const response=await pending;expect(response.ok(),await response.text()).toBe(true);const rid=(await response.json()).run_id;
 let record;
 await expect.poll(async()=>{record=await api('/runs/'+rid);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:90000}).toBe('completed');
 await expect(page.locator('#statusbar')).toContainText('已完成');
 expect(record.frame.valid).toBe(true);expect(record.frame.time_s).toBe(600);
 expect(record.request.project.instances).toHaveLength(51);expect(record.request.project.connections).toHaveLength(72);
 expect(Math.abs(record.frame.metrics.mass_residual_kg_circuit0)).toBeLessThan(1e-7);
 expect(Math.abs(record.frame.metrics.energy_residual_j)).toBeLessThan(1);
 await page.locator('[data-action="run-project"][data-command="stop"]').first().click();
 return record;
}
try{
 await page.goto(server.base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 await page.locator('[data-action="wf-import"]').click();
 await page.getByLabel('单项目文件').setInputFiles('examples/large-cold-store/six-room.project.json');
 await page.getByRole('dialog').locator('[name="mode"]').selectOption('replace');await submit();
 await expect(page.locator('#toast')).toContainText('项目已导入');let owner=await save();
 expect(owner.pages).toHaveLength(4);expect(owner.pages.flatMap(p=>p.nodes)).toHaveLength(51);
 await nav('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
 for(const [key,value] of Object.entries({duration:600,dt:10})){
  await page.locator(`[data-solver-field="${key}"]`).fill(String(value));await page.locator(`[data-solver-field="${key}"]`).blur();
 }
 await nav('controls');await page.locator('[data-live-mode]').selectOption('fast');
 for(const scenario of project.scenarios){
  const record=await run(scenario.id);runs[scenario.id]=record;
  if(scenario.id==='baseline'){
   for(const room of ['F01','F02','F03','F04','C01','C02'])
    expect(record.frame.variables[room+'.state.temperature_k']).toBeCloseTo(project.instances.find(n=>n.id===room).parameters.temperature_k,4);
  }else expect(record.frame.variables['F01.state.temperature_k']).toBeGreaterThan(249.15+.05);
  if(scenario.id==='f01-cooler-off')expect(record.frame.variables['F01_AC1.supply_mass_flow_kg_s']).toBe(0);
  await nav('runs');await page.locator('[data-action="refresh-archives"]').click();
  await page.locator(`[data-action="open-archive"][data-id="${record.id}"]`).click();
  for(const format of ['html','csv']){
   const download=page.waitForEvent('download');
   await page.locator(`[data-action="archive-report"][data-id="${record.id}"][data-format="${format}"]`).click();
   await(await download).saveAs(join(out,scenario.id+'.'+format));
  }
 }
 await nav('workbench');await page.locator('[data-wf-scenario]').selectOption('baseline');
 await page.locator('[data-action="canvas-tab"][data-id="plant"]').click();await page.locator('[data-action="fit"]').click();
 owner=await save();
 await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${owner.id}"]`).click();
 const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
 await(await download).saveAs(join(out,'six-room.studio.json'));await page.locator('[data-action="close-dialog"]').last().click();
 await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 const repeated=await run('baseline');
 for(const [key,value] of Object.entries(runs.baseline.frame.variables))
  if(typeof value==='number')expect(repeated.frame.variables[key],key).toBeCloseTo(value,6);
 runs.reloaded=repeated;
 await nav('curves');
 for(const room of ['F01','C01']){
  await page.locator('[data-action="add-chart-variable"]').click();
  await page.getByRole('dialog').locator('[name="variable"]').selectOption(room+'.STATE_TEMPERATURE_K');await submit();
 }
 await expect(page.locator('#extra-charts svg path.chart-line').first()).toHaveAttribute('d',/L/);
 await captureFhd(page,join(out,'room-curves.png'));await nav('workbench');
 for(const pageId of ['plant','frozen-a','frozen-b','chilled']){
  await page.locator(`[data-action="canvas-tab"][data-id="${pageId}"]`).click();await page.locator('[data-action="fit"]').click();
  await captureFhd(page,join(out,pageId+'.png'));
 }
 await page.locator('[data-action="canvas-tab"][data-id="plant"]').click();await save();
 await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${owner.id}"]`).click();
 const finalExport=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
 await(await finalExport).saveAs(join(out,'six-room.studio.json'));await page.locator('[data-action="close-dialog"]').last().click();
 await nav('workbench');
 expect(errors).toEqual([]);writeFileSync(join(out,'runs.json'),JSON.stringify(runs,null,2));
 const summary={projectId:owner.id,url:server.base+'/#workbench',nodes:51,connections:72,pages:4,
  scenarios:Object.fromEntries(Object.entries(runs).map(([key,record])=>[key,{runId:record.id,time_s:record.frame.time_s,
   temperature_c:record.frame.variables['F01.state.temperature_k']-273.15,metrics:record.frame.metrics}])),reload:true,reports:true,errors};
 writeFileSync(join(out,'summary.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
}catch(error){console.error(error);await captureFhd(page,join(out,'failure.png')).catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
