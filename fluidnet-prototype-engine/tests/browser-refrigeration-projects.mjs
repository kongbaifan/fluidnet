import {chromium,expect} from '@playwright/test';
import {mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-rf4-')),output='artifacts/platform-extension/rf4';
mkdirSync(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true}),errors=[],evidence={};
const moduleId='rf4_author_valve',valve='Expansion-Custom',flowKey=valve+'.mass_flow_kg_s';
let server,context,page;
async function start(){
  server=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  context=await browser.newContext({...FHD_CONTEXT,acceptDownloads:true});page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));await page.goto(server.base+'/#modules');
  await expect(page.locator('[data-module-id="isenthalpic_throttle"]')).toBeVisible();
}
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();};
const submit=async()=>{await page.locator('#dialog-form button[type="submit"]').click();await expect(page.locator('#dialog-form')).toHaveCount(0);};
const navigate=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const save=async()=>{const receipt=page.waitForResponse(r=>r.url().endsWith('/workspace')&&r.request().method()==='POST');await page.locator('[data-action="save"]').first().click();expect((await receipt).status()).toBe(200);return page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));};
const active=s=>s.projects.find(p=>p.id===s.activeProject);
async function edit(){await navigate('modules');await page.locator(`[data-module-id="${moduleId}"] [data-action="edit-module"]`).click();}
async function publish(){
  await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
  const receipt=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();
  const response=await receipt;expect(response.status(),await response.text()).toBe(201);
  await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();return response.json();
}
async function importFile(file){
  await navigate('projects');await page.locator('[data-action="wf-import"]').click();
  await page.getByLabel('单项目文件').setInputFiles(file);await submit();
  await expect(page.locator('#toast')).toContainText('项目已导入');
  await navigate('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="duration"]').fill('1');await page.locator('[data-solver-field="duration"]').blur();
  await page.locator('[data-solver-field="dt"]').fill('.1');await page.locator('[data-solver-field="dt"]').blur();
  return active(await save());
}
async function run(){
  await navigate('workbench');
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const queued=await(await receipt).json();let record;
  await expect.poll(async()=>{record=await api('/runs/'+queued.run_id);if(record.status==='failed')throw Error(JSON.stringify(record.frame));return record.status;},{timeout:45000}).toBe('completed');
  await expect(page.locator('[data-result-status]').first()).toContainText('t = 1.0 s');return record;
}
async function upgrade(version){
  await navigate('workbench');await page.locator('[data-action="wf-upgrades"]').click();
  await page.locator(`[data-action="wf-module-versions"][data-module="${moduleId}"]`).click();
  await page.locator(`[data-action="wf-preview-upgrade"][data-version="${version}"]`).click();
  await expect(page.getByRole('dialog')).toContainText('兼容检查通过');await submit();
  await expect(page.locator('#toast')).toContainText('模块版本已更新并保存');
}
async function exportFile(action,name){
  const owner=active(await save());await navigate('projects');
  await page.locator(`[data-action="wf-manage"][data-id="${owner.id}"]`).click();
  const download=page.waitForEvent('download');await page.locator(`[data-action="${action}"]`).click();
  const path=join(directory,name);await(await download).saveAs(path);
  await page.locator('[data-action="close-dialog"]').last().click();return path;
}
try{
  await start();
  await page.locator('[data-action="new-module"]').click();await page.locator('[name="name"]').fill('项目作者节流阀');
  await page.locator('[name="code"]').fill(moduleId.toUpperCase());await page.locator('[name="base"]').selectOption('template:refrigeration_throttle');await submit();
  const v1=await publish();
  const model=JSON.parse(readFileSync('examples/refrigeration_extensions/author_station.json','utf8'));
  model.modules=model.modules.map(m=>m.id==='isenthalpic_throttle'?v1.module:m);
  Object.assign(model.instances.find(n=>n.id===valve),{module_id:moduleId,package:v1.package});
  model.scenarios[0].overrides.ROOM1={heat_input_w:18000};
  const input=join(directory,'author.json');writeFileSync(input,JSON.stringify(model));
  const owner=await importFile(input);evidence.projectId=owner.id;
  const original=await run(),flow=original.frame.variables[flowKey];expect(flow).toBeGreaterThan(0);
  await navigate('curves');await expect(page.locator('#main-flow-chart')).toBeVisible();
  expect((await save()).projects.find(p=>p.id===owner.id).run.history.at(-1).q).toBeCloseTo(flow,9);
  console.log('RF-4 imported canonical project and ran v1.');

  await edit();await page.locator('[data-action="editor-tab"][data-value="code"]').first().click();
  const source=await page.locator('#module-code').inputValue();
  await page.locator('#module-code').fill(source.replace('fraction = opening','fraction = math.expm1(opening * math.log(50.0)) / 49.0'));
  const v2=await publish();expect(v2.module.version).toBe(2);
  expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow,9);
  await upgrade(2);const changed=await run();
  expect(changed.frame.variables[flowKey]).toBeLessThan(flow*.6);
  expect(changed.request.project.controllers).toEqual(original.request.project.controllers);
  expect(changed.request.project.scenarios).toEqual(original.request.project.scenarios);
  expect(changed.request.project.control_scripts).toEqual(original.request.project.control_scripts);
  await navigate('runs');await page.locator('[data-action="refresh-archives"]').click();
  await page.locator(`[data-action="open-archive"][data-id="${original.id}"]`).click();
  const report=page.waitForEvent('download');
  await page.locator(`[data-action="archive-report"][data-id="${original.id}"][data-format="html"]`).click();
  const reportFile=join(directory,'old-report.html');await(await report).saveAs(reportFile);
  const html=readFileSync(reportFile,'utf8');
  const csvDownload=page.waitForEvent('download');
  await page.locator(`[data-action="archive-report"][data-id="${original.id}"][data-format="csv"]`).click();
  const csvFile=join(directory,'old-report.csv');await(await csvDownload).saveAs(csvFile);
  expect(readFileSync(csvFile,'utf8')).toContain(valve+'.state.transferred_mass_kg [kg]');
  expect(html).toContain(v1.module.definition_hash);expect(html).not.toContain(v2.module.definition_hash);
  expect(html).toContain(valve+'.state.transferred_mass_kg');expect(html).not.toContain('EV1');
  const reportPage=await context.newPage();await reportPage.setContent(html);
  await reportPage.getByRole('heading',{name:'作者模块冻结版本'}).scrollIntoViewIfNeeded();
  expect(await reportPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await captureFhd(reportPage,output+'/frozen-report.png');await reportPage.close();
  writeFileSync(output+'/frozen-report.html',html);
  console.log('RF-4 version upgrade preserved partial scenarios and frozen report.');

  await navigate('batches');await page.getByRole('button',{name:'保存项目并准备工况',exact:true}).click();
  await page.getByLabel('扫描设备',{exact:true}).selectOption(valve);
  await page.getByLabel('扫描参数',{exact:true}).selectOption('kv_m3_h');
  await page.getByLabel('取值方式',{exact:true}).selectOption('range');
  await page.getByLabel('起始值',{exact:true}).fill('.3');await page.getByLabel('结束值',{exact:true}).fill('.6');
  await page.getByLabel('工况数量',{exact:true}).fill('2');
  await page.getByLabel('批次计算方式',{exact:true}).selectOption('dynamic');
  await page.getByLabel('仿真时长 · s',{exact:true}).fill('1');await page.getByLabel('输出步长 · s',{exact:true}).fill('.1');
  while(await page.locator('[data-batch-variable]:checked').count())await page.locator('[data-batch-variable]:checked').first().uncheck();
  await page.getByLabel('筛选批次变量',{exact:true}).fill(valve);
  await page.locator(`[data-batch-variable="${flowKey}"]`).check();
  await page.locator(`[data-batch-variable="${valve}.state.transferred_mass_kg"]`).check();
  const receipt=page.waitForResponse(r=>r.url().endsWith('/batches/preview')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'预览工况',exact:true}).click();expect((await receipt).status()).toBe(200);
  const created=page.waitForResponse(r=>r.url().endsWith('/batches')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存并运行批次',exact:true}).click();const batch=await(await created).json();let detail;
  await expect.poll(async()=>{detail=await api('/batches/'+batch.id);return detail.status;},{timeout:60000}).toBe('completed');
  expect(detail.source.modules.find(m=>m.id===moduleId).definition_hash).toBe(v2.module.definition_hash);
  expect(detail.items[0].values[flowKey]).toBeLessThan(detail.items[1].values[flowKey]);
  await expect(page.locator('[data-batch-series]')).toHaveCount(2);
  await captureFhd(page,output+'/batch.png');
  await upgrade(1);expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow,9);
  const single=await exportFile('wf-export','single.json');
  const canonical=await exportFile('wf-export-canonical','canonical.json');
  for(const file of [single,canonical]){await importFile(file);expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow,9);}
  const saved=active(await save());evidence.finalProjectId=saved.id;
  await context.close();await server.stop();await start();
  expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow,9);
  const old=await api('/runs/'+original.id);expect(old.frame).toEqual(original.frame);
  expect((await api('/batches/'+batch.id)).source.modules.find(m=>m.id===moduleId).version).toBe(2);
  await captureFhd(page,output+'/restored-project.png');
  evidence.versions=[1,2,1];evidence.flowV1=flow;evidence.flowV2=changed.frame.variables[flowKey];evidence.batch=batch.id;
  evidence.restarted=true;evidence.formats=['fluidnet-project','Project'];evidence.errors=errors;expect(errors).toEqual([]);
  writeFileSync(output+'/browser-validation.json',JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}catch(error){await captureFhd(page,output+'/failure.png').catch(()=>{});console.error(JSON.stringify({errors,toast:await page.locator('#toast').textContent().catch(()=>null)}));throw error;}
finally{await context?.close();await browser.close();await server?.stop();}
