import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[],evidence={};
page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
const output='artifacts/device-guidance';mkdirSync(output,{recursive:true});
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=async()=>{await page.locator('#dialog-form [type="submit"]').click();await expect(page.locator('#dialog-form')).toHaveCount(0);};
const state=()=>page.evaluate(async()=>{const {FluidNetDraftStore}=await import('/draft-store.js');return FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));});
const owner=s=>s.projects.find(p=>p.id===s.activeProject);
async function api(path){const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();}
async function save(){
  const r=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await r).ok()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');return state();
}
async function createProject(template){
  await nav('projects');await page.locator('[data-action="new-project"]').first().click();
  await page.locator('#dialog-form [name="name"]').fill('设备易用性 '+template);
  await page.locator('#dialog-form [name="template"]').selectOption(template);await submit();
  await nav('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="mode"]').selectOption('steady');await nav('workbench');
}
async function panel(id,tab='overview'){
  await page.locator(`.net-node[data-node="${id}"]`).dblclick();const region=page.getByRole('region',{name:id+' 设备参数',exact:true});
  await region.locator(`[data-action="float-tab"][data-value="${tab}"]`).click();return region;
}
async function close(region){await region.locator('[data-action="float-close"]').click();}
async function run(){
  const [response]=await Promise.all([
    page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST'),
    page.locator('[data-action="run-project"][data-command="run"]').first().click()
  ]);
  expect(response.ok(),await response.text()).toBe(true);const {run_id}=await response.json();let record;
  await expect.poll(async()=>{record=await api('/runs/'+run_id);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:45000}).toBe('completed');
  await expect(page.locator('#statusbar')).toContainText('已完成');return record;
}
const metric=(region,id)=>region.locator(`[data-device-metric="${id}"] strong`);
const value=async locator=>Number((await locator.textContent()).replaceAll(',',''));
try{
  await page.goto(server.base+'/#modules');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  const catalog=await api('/catalog'),initial=await save();
  for(const id of ['pump','valve','pipe','exchanger']){
    const card=page.locator(`[data-module-id="${id}"]`);await card.locator('[data-action="module-doc"]').click();
    await expect(page.locator(`[data-device-guide="${id}"]`)).toBeVisible();
    const specs=catalog.modules.find(m=>m.id===id).parameters;
    for(const spec of specs.filter(p=>p.value_type==='number')){
      const row=page.locator('#dialog-form table').first().locator('tr').filter({has:page.locator('td').first().filter({hasText:new RegExp('^'+spec.id+'$')})});
      const expected=spec.unit?spec.default/spec.unit.display_scale+spec.unit.display_offset:spec.default;
      expect(Number(await row.locator('td').nth(2).textContent())).toBeCloseTo(expected,8);
      await expect(row.locator('td').nth(3)).toHaveText(spec.unit?.display_unit||spec.unit?.canonical_unit||'—');
    }
    await page.locator('#dialog-form [data-action="close-dialog"]').last().click();
    await card.locator('[data-action="edit-module"]').click();
    await page.locator('.editor-tabs [data-value="attributes"]').click();
    const fields=page.locator('[data-builtin-parameter]');expect(await fields.count()).toBe(specs.length);
    await nav('modules');
  }
  const after=await save();
  for(const id of ['pump','valve','pipe','exchanger'])expect(after.modules.find(m=>m.id===id)).toEqual(initial.modules.find(m=>m.id===id));

  await createProject('water');
  let region=await panel('P1');await expect(metric(region,'runtime:shaft_power_w')).toHaveText('—');
  expect(await region.locator('input[type="number"][data-instance-param]').count()).toBe(1);
  await expect(region.locator('[data-instance-param="speed"]')).toBeVisible();await close(region);
  region=await panel('L1','parameters');
  await expect(region.locator('input[type="number"][data-instance-param="length"]')).toBeVisible();await expect(region.locator('[data-instance-param="diameter"]')).toBeVisible();
  await expect(region.locator('[data-instance-param="roughness"]')).toBeVisible();
  await expect(region.locator('.parameter-row').filter({has:page.locator('[data-instance-param="roughness"]')})).toContainText('已应用设置 0.045 mm');
  await expect(region.locator('.device-other-parameters')).not.toHaveAttribute('open','');
  await expect(region.locator('[data-instance-param="heatLoss"]')).toBeHidden();
  await region.locator('.device-other-parameters > summary').click();await region.locator('[data-instance-param="heatLoss"]').fill('10');
  await region.locator('[data-instance-param="heatLoss"]').blur();await close(region);
  region=await panel('L1','parameters');await expect(region.locator('.device-other-parameters')).toHaveAttribute('open','');
  await expect(region.locator('[data-instance-param="heatLoss"]')).toHaveValue('10');await captureFhd(page,output+'/pipe-parameters.png');await close(region);
  const baseline=await run();evidence.water=baseline.id;
  region=await panel('P1');
  await expect(region.locator('[data-device-result-source]')).toContainText('当前计算结果');
  expect(await value(metric(region,'runtime:shaft_power_w'))).toBeCloseTo(baseline.frame.variables['P1.shaft_power_w']/1000,3);
  await region.locator('[data-instance-param="speed"]').fill('0.8');await region.locator('[data-action="apply-instance"]').click();await submit();
  await expect(region.locator('[data-device-result-source]')).toContainText('已过期');
  await expect(region.locator('[data-pending-for="P1"]')).toContainText('0 项待应用');
  await region.locator('[data-action="float-dock"]').click();
  const slowed=await run();
  await expect.poll(()=>value(metric(region,'runtime:shaft_power_w'))).toBeCloseTo(slowed.frame.variables['P1.shaft_power_w']/1000,3);
  await captureFhd(page,output+'/pump-overview.png');await close(region);
  region=await panel('V1');
  await expect(region.locator('input[type="number"][data-instance-param="opening"]')).toBeVisible();await region.locator('[data-action="float-tab"][data-value="parameters"]').click();await expect(region.locator('[data-instance-param="kv"]')).toBeVisible();await region.locator('[data-action="float-tab"][data-value="overview"]').click();
  expect(await value(metric(region,'runtime:pressure_drop_pa'))).toBeCloseTo(slowed.frame.variables['V1.pressure_drop_pa']/1000,3);await close(region);
  region=await panel('L1');expect(await value(metric(region,'runtime:pressure_drop_pa'))).toBeCloseTo(slowed.frame.variables['L1.pressure_drop_pa']/1000,3);await close(region);
  const savedWater=owner(await save());expect(savedWater.pages[0].nodes.find(n=>n.id==='L1').params.heatLoss).toBe(0);expect(savedWater.pages[0].nodes.find(n=>n.id==='L1').draft.heatLoss).toBe(10);

  await createProject('heat');const heat=await run();evidence.heat=heat.id;
  region=await panel('HX1');await expect(region.locator('[data-device-result-group]')).toHaveCount(2);
  for(const [key,scale] of [['ch0.heat_w',1000],['ch1.heat_w',1000]])expect(await value(metric(region,'runtime:'+key))).toBeCloseTo(heat.frame.variables['HX1.'+key]/scale,3);
  expect(await value(metric(region,'runtime:ch0.heat_w'))).toBeLessThan(0);expect(await value(metric(region,'runtime:ch1.heat_w'))).toBeGreaterThan(0);
  expect(Math.abs(heat.frame.variables['HX1.ch0.heat_w']+heat.frame.variables['HX1.ch1.heat_w'])).toBeLessThan(.01);
  await region.locator('[data-device-guide] > summary').click();await expect(region.locator('[data-device-guide]')).toContainText('同一工质');
  await region.locator('[data-device-guide] > summary').click();await region.locator('[data-action="float-dock"]').click();
  await region.locator('[data-device-result-source]').scrollIntoViewIfNeeded();
  await captureFhd(page,output+'/exchanger-overview.png');await save();await close(region);
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  region=await panel('HX1');expect(await value(metric(region,'runtime:ch0.heat_w'))).toBeCloseTo(heat.frame.variables['HX1.ch0.heat_w']/1000,3);
  await region.locator('[data-action="float-tab"][data-value="connections"]').click();await expect(region).toContainText('与 out1 二次侧出口');
  const finalCatalog=await api('/catalog');expect(finalCatalog).toEqual(catalog);expect(errors).toEqual([]);
  evidence.passed=true;evidence.heatW=[heat.frame.variables['HX1.ch0.heat_w'],heat.frame.variables['HX1.ch1.heat_w']];
  writeFileSync(output+'/evidence.json',JSON.stringify(evidence,null,2)+'\n');
  console.log('Device guidance passed: four builtin docs, unit/default consistency, common fields, retained drafts, actual pump/valve/pipe/heat results and reload.');
}catch(error){console.error('UI state:',await page.locator('#dialog-layer').innerText(),await page.locator('#toast').innerText());await captureFhd(page,output+'/failure.png');throw error;}
finally{await browser.close();await server.close();}
