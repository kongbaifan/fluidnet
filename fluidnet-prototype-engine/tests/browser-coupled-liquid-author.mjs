import {chromium,expect} from '@playwright/test';
import {mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-coupled-author-'));
const output='artifacts/coupled-liquid-author';mkdirSync(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true}),errors=[],evidence={};
const moduleId='coupled_liquid_valve',valve='LiquidValve-Custom',flowKey=valve+'.mass_flow_kg_s';
let server,context,page;
async function start(){
  server=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  context=await browser.newContext({...FHD_CONTEXT,acceptDownloads:true});page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));await page.goto(server.base+'/#modules');
  await expect(page.locator(`[data-module-id="${moduleId}"]`)).toBeVisible();
}
const api=async path=>{const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();};
const navigate=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=async()=>{await page.locator('#dialog-form button[type="submit"]').click();await expect(page.locator('#dialog-form')).toHaveCount(0);};
const active=state=>state.projects.find(project=>project.id===state.activeProject);
async function save(){
  const receipt=page.waitForResponse(response=>response.url().endsWith('/workspace')&&response.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await receipt).status()).toBe(200);
  return page.evaluate(async () => (await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
}
async function importFile(file){
  await navigate('projects');await page.locator('[data-action="wf-import"]').click();
  await page.getByLabel('单项目文件').setInputFiles(file);await submit();
  await expect(page.locator('#toast')).toContainText('项目已导入');
  await navigate('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  for(const [field,value] of [['duration','1'],['dt','.5']]){
    await page.locator(`[data-solver-field="${field}"]`).fill(value);await page.locator(`[data-solver-field="${field}"]`).blur();
  }
  return active(await save());
}
async function run(){
  await navigate('workbench');
  const receipt=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/v1/runs'&&response.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const response=await receipt;expect(response.ok(),await response.text()).toBe(true);const queued=await response.json();let record;
  await expect.poll(async()=>{
    record=await api('/runs/'+queued.run_id);if(record.status==='failed')throw Error(JSON.stringify(record.frame));return record.status;
  },{timeout:60000}).toBe('completed');
  await expect(page.locator('[data-action="run-project"][data-command="run"]').first()).toBeEnabled({timeout:20000});
  expect(record.frame.time_s).toBe(1);expect(record.frame.variables[valve+'.state.commit_count']).toBe(2);
  expect(record.frame.variables[valve+'.state.transferred_mass_kg']).toBeGreaterThan(0);
  return record;
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
  const pending=page.waitForEvent('download');await page.locator(`[data-action="${action}"]`).click();
  const path=join(directory,name);await(await pending).saveAs(path);await page.locator('[data-action="close-dialog"]').last().click();return path;
}
try{
  await start();
  const health=await api('/health');expect(health.capabilities.thermal_coupling_liquid_modules).toBe(true);
  const model=await api('/examples/thermal-coupling-author');
  expect(model.selected_variables).toEqual([]);
  expect(model.instances.some(instance=>instance.id===valve)).toBe(true);
  const input=join(directory,'author-loop.json');writeFileSync(input,JSON.stringify(model));
  const owner=await importFile(input);evidence.projectId=owner.id;
  const original=await run(),flow=original.frame.variables[flowKey];
  expect(flow).toBeGreaterThan(0);expect(original.frame.variables[valve+'.effective_opening_ratio']).toBe(.8);
  expect(Math.abs(original.frame.metrics.reference_heat_w)).toBeLessThan(1e-7);
  const resultPanel=await page.locator('.thermal-coupling').boundingBox();
  for(const identifier of [valve,'HX_W']){
    const box=await page.locator(`#network [data-node="${identifier}"]`).boundingBox();
    expect(box.y+box.height).toBeLessThan(resultPanel.y);
  }
  await captureFhd(page,output+'/initial-project.png');
  console.log('Coupled author canonical import and dynamic run passed.');

  await navigate('modules');await page.locator(`[data-module-id="${moduleId}"] [data-action="edit-module"]`).click();
  await page.locator('[data-action="editor-tab"][data-value="code"]').first().click();
  const source=await page.locator('#module-code').inputValue();
  expect(source).toContain('effective = opening ** exponent');
  await page.locator('#module-code').fill(source.replace('effective = opening ** exponent','effective = opening ** (exponent * 2.0)'));
  await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
  const published=page.waitForResponse(response=>response.url().endsWith('/modules/versions')&&response.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();
  const publication=await published;expect(publication.status(),await publication.text()).toBe(201);
  const v2=await publication.json();expect(v2.module.version).toBe(2);
  await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
  expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow,8);
  await upgrade(2);const changed=await run();
  expect(changed.frame.variables[flowKey]).toBeLessThan(flow);
  expect(changed.frame.variables[valve+'.effective_opening_ratio']).toBeCloseTo(.64,12);
  await captureFhd(page,output+'/upgraded-project.png');

  await navigate('runs');await page.locator('[data-action="refresh-archives"]').click();
  await page.locator(`[data-action="open-archive"][data-id="${original.id}"]`).click();
  for(const format of ['html','csv']){
    const download=page.waitForEvent('download');
    await page.locator(`[data-action="archive-report"][data-id="${original.id}"][data-format="${format}"]`).click();
    const file=join(directory,'frozen-report.'+format);await(await download).saveAs(file);
    const text=readFileSync(file,'utf8');expect(text).toContain(valve+'.state.transferred_mass_kg');
    expect(text).toContain(valve+'.effective_opening_ratio');
    if(format==='html'){
      expect(text).toContain(model.modules.find(module=>module.id===moduleId).definition_hash);
      expect(text).not.toContain(v2.module.definition_hash);
      const reportPage=await context.newPage();await reportPage.setContent(text);
      await reportPage.getByRole('heading',{name:'作者模块冻结版本'}).scrollIntoViewIfNeeded();
      expect(await reportPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await captureFhd(reportPage,output+'/frozen-report.png');await reportPage.close();
    }
  }
  console.log('Coupled author upgrade and frozen HTML/CSV downloads passed.');

  await navigate('batches');await page.getByRole('button',{name:'保存项目并准备工况',exact:true}).click();
  await page.getByLabel('扫描设备',{exact:true}).selectOption(valve);
  await page.getByLabel('扫描参数',{exact:true}).selectOption('opening_ratio');
  await page.getByLabel('取值方式',{exact:true}).selectOption('range');
  await page.getByLabel('起始值',{exact:true}).fill('40');await page.getByLabel('结束值',{exact:true}).fill('80');
  await page.getByLabel('工况数量',{exact:true}).fill('2');
  await page.getByLabel('批次计算方式',{exact:true}).selectOption('dynamic');
  await page.getByLabel('仿真时长 · s',{exact:true}).fill('1');await page.getByLabel('输出步长 · s',{exact:true}).fill('.5');
  while(await page.locator('[data-batch-variable]:checked').count())await page.locator('[data-batch-variable]:checked').first().uncheck();
  await page.getByLabel('筛选批次变量',{exact:true}).fill(valve);
  await page.locator(`[data-batch-variable="${flowKey}"]`).check();
  await page.locator(`[data-batch-variable="${valve}.state.transferred_mass_kg"]`).check();
  const preview=page.waitForResponse(response=>response.url().endsWith('/batches/preview')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'预览工况',exact:true}).click();expect((await preview).status()).toBe(200);
  const creation=page.waitForResponse(response=>response.url().endsWith('/batches')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'保存并运行批次',exact:true}).click();const batch=await(await creation).json();let detail;
  await expect.poll(async()=>{detail=await api('/batches/'+batch.id);return detail.status;},{timeout:60000}).toBe('completed');
  expect(detail.source.modules.find(module=>module.id===moduleId).definition_hash).toBe(v2.module.definition_hash);
  expect(detail.items[0].values[flowKey]).toBeLessThan(detail.items[1].values[flowKey]);
  await captureFhd(page,output+'/batch-comparison.png');

  await upgrade(1);expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow,8);
  const single=await exportFile('wf-export','single.json');
  const canonical=await exportFile('wf-export-canonical','canonical.json');
  for(const file of [single,canonical]){await importFile(file);expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow,8);}
  evidence.finalProjectId=active(await save()).id;
  await context.close();await server.stop();await start();
  expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow,8);
  expect((await api('/runs/'+original.id)).frame).toEqual(original.frame);
  expect((await api('/batches/'+batch.id)).source.modules.find(module=>module.id===moduleId).version).toBe(2);
  await captureFhd(page,output+'/restarted-project.png');
  Object.assign(evidence,{versions:[1,2,1],flowV1:flow,flowV2:changed.frame.variables[flowKey],batch:batch.id,
    formats:['fluidnet-project','Project'],restarted:true,errors});expect(errors).toEqual([]);
  writeFileSync(output+'/validation.json',JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}catch(error){await captureFhd(page,output+'/failure.png').catch(()=>{});console.error(JSON.stringify({errors,toast:await page?.locator('#toast').textContent().catch(()=>null)}));throw error;}
finally{await context?.close();await browser.close();await server?.stop();}
