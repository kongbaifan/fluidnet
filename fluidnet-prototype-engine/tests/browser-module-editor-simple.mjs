import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[];
page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(15000);
const output='artifacts/module-editor-simple';mkdirSync(output,{recursive:true});
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const tab=value=>page.locator(`.editor-tabs [data-action="editor-tab"][data-value="${value}"]`).click();
const submit=async()=>{await page.locator('#dialog-form [type="submit"]').click();await expect(page.locator('#dialog-form')).toHaveCount(0);};
const edit=async id=>{await nav('modules');await page.locator(`[data-module-id="${id}"] [data-action="edit-module"]`).click();};
const state=()=>page.evaluate(async()=>{const {FluidNetDraftStore}=await import('/draft-store.js');return FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));});
async function save(){
  const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await pending).ok()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');return state();
}
async function publish(status=201){
  const pending=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();const response=await pending,body=await response.json();
  expect(response.status(),JSON.stringify(body)).toBe(status);await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();return body;
}
async function addParameter({id,label,unit,value,minimum='',maximum='',type='number'}){
  await page.locator('[data-action="edit-module-parameter"]').filter({hasText:'新增参数'}).click();
  await page.locator('#dialog-form [name="label"]').fill(label);await page.locator('#dialog-form [name="id"]').fill(id);
  await page.locator('#dialog-form [name="value_type"]').selectOption(type);
  if(type==='number'){
    await page.locator('#dialog-form [name="unit"]').selectOption({label:unit});
    await page.locator('#dialog-form [name="minimum"]').fill(minimum);await page.locator('#dialog-form [name="maximum"]').fill(maximum);
  }
  if(type==='boolean')await page.locator('#dialog-form [name="default"]').selectOption(value);
  else await page.locator('#dialog-form [name="default"]').fill(value);
  await submit();
}
try{
  await page.goto(server.base+'/#modules');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  // Existing devices present their familiar values before the full variable definitions.
  for(const id of ['pump','valve','exchanger']){
    await edit(id);await expect(page.locator('[data-action="edit-module-metadata"]')).toBeVisible();await tab('attributes');
    await expect(page.locator('.editor-content')).toContainText('常用参数');
    await expect(page.locator('.editor-content')).toContainText('保存为型号');
    await expect(page.locator('.editor-content details[open]')).toHaveCount(0);
    await expect(page.locator('[data-module-contract]')).toHaveCount(0);
  }
  await nav('modules');await page.locator('[data-action="new-module"]').click();
  await page.locator('#dialog-form [name="name"]').fill('简易编辑阀');await page.locator('#dialog-form [name="code"]').fill('SIMPLE_EDITOR_VALVE');
  await page.locator('#dialog-form [name="base"]').selectOption('programmable_valve');await submit();
  await expect(page.locator('#module-drawing')).toBeVisible();await expect(page.locator('#module-code')).toHaveCount(0);
  await page.locator('[data-action="edit-module-metadata"]').click();await page.locator('#dialog-form [name="name"]').fill('循环水调节阀');
  await page.locator('#dialog-form [name="description"]').fill('用于调节循环水流量。入口接上游，开度按百分比填写。');await submit();
  await expect(page.locator('.module-basic-info')).toContainText('循环水调节阀');
  await page.locator('[data-draw-id="in0"]').click();await page.locator('[data-port-field="label"]').fill('介质入口');await page.locator('[data-port-field="label"]').blur();
  await captureFhd(page,output+'/equipment-setup.png');
  await tab('attributes');await expect(page.locator('.editor-parameter-advanced')).not.toHaveAttribute('open','');
  await page.locator('[data-action="edit-module-parameter"][data-id="opening_ratio"]').click();
  await page.locator('#dialog-form [name="unit"]').selectOption({label:'%'});
  await expect(page.locator('#dialog-form [name="unit"] option:checked')).toHaveText('%');
  await expect(page.locator('#dialog-form [name="default"]')).toHaveValue('80');
  await expect(page.locator('#dialog-form [name="display_scale"]')).toHaveCount(0);
  await page.locator('#dialog-form [name="default"]').fill('150');await page.locator('#dialog-form [type="submit"]').click();
  await expect(page.locator('#dialog-error')).toContainText('默认值必须');await expect(page.locator('#dialog-form [name="default"]')).toHaveValue('150');
  await page.locator('#dialog-form [name="default"]').fill('75');
  await page.locator('#dialog-form [name="unit"]').selectOption({label:'1'});await expect(page.locator('#dialog-form [name="default"]')).toHaveValue('0.75');
  await page.locator('#dialog-form [name="unit"]').selectOption({label:'%'});await expect(page.locator('#dialog-form [name="default"]')).toHaveValue('75');
  await captureFhd(page,output+'/parameter-editor.png');await submit();
  await expect(page.locator('[data-module-parameter="opening_ratio"]')).toContainText('75');
  await addParameter({id:'reference_diameter',label:'参考直径',unit:'mm',value:'40',minimum:'10',maximum:'80'});
  await addParameter({id:'reference_temperature',label:'参考温度',unit:'°C',value:'25',minimum:'-20',maximum:'80'});
  await addParameter({id:'equipment_note',label:'设备说明',type:'text',value:'循环水支路'});
  await addParameter({id:'enabled_note',label:'示例启用标记',type:'boolean',value:'false'});
  await expect(page.locator('[data-module-parameter="reference_temperature"]')).toContainText('-20 ~ 80');
  await expect(page.locator('[data-module-parameter="enabled_note"]')).toContainText('否');
  await captureFhd(page,output+'/common-parameters.png');
  // Save feedback must be visible on the ordinary parameter page as well as in the algorithm editor.
  await tab('code');const good=await page.locator('#module-code').inputValue();await page.locator('#module-code').fill('def broken(');
  await tab('attributes');await publish(422);await expect(page.locator('.module-save-feedback')).toContainText('版本未保存');
  await tab('code');await page.locator('#module-code').fill(good);await tab('attributes');const release=await publish();
  await expect(page.locator('.module-save-feedback')).toContainText('v1 已保存');
  const parameters=Object.fromEntries(release.module.parameters.map(p=>[p.id,p]));
  expect(parameters.opening_ratio.default).toBe(.75);expect(parameters.reference_diameter.default).toBe(.04);
  expect(parameters.reference_diameter.minimum).toBe(.01);expect(parameters.reference_temperature.default).toBeCloseTo(298.15,10);
  expect(parameters.reference_temperature.minimum).toBeCloseTo(253.15,10);expect(parameters.enabled_note.default).toBe(false);
  expect(parameters.equipment_note.default).toBe('循环水支路');expect(release.module.ports[0].label).toBe('介质入口');
  expect(release.module.name).toBe('循环水调节阀');
  // Saved values use display units when the device is put into a project.
  await nav('projects');await page.locator('[data-action="new-project"]').first().click();await page.locator('#dialog-form [name="name"]').fill('常用参数验收');await submit();
  await edit('simple_editor_valve');await page.locator('[data-action="use-module"]').click();await submit();
  let workspace=await save(),owner=workspace.projects.find(p=>p.id===workspace.activeProject),device=owner.pages[0].nodes[0];
  expect(device.params.opening_ratio).toBe(75);expect(device.params.reference_diameter).toBe(40);expect(device.params.reference_temperature).toBe(25);
  const panel=page.getByRole('region',{name:device.id+' 设备参数',exact:true});
  await panel.locator('[data-instance-param="reference_temperature"][type="number"]').fill('30');
  await panel.locator('[data-instance-param="reference_temperature"][type="number"]').blur();
  await panel.locator('[data-action="apply-instance"]').click();await submit();
  await panel.locator('[data-action="float-close"]').click();await save();
  // Further library edits stay in the library; this project's saved definition stays at v1.
  await edit('simple_editor_valve');await tab('attributes');
  await page.locator('[data-action="edit-module-parameter"][data-id="opening_ratio"]').click();await page.locator('#dialog-form [name="default"]').fill('60');await submit();
  await save();await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  workspace=await state();owner=workspace.projects.find(p=>p.id===owner.id);
  expect(owner.pages[0].nodes[0].params.reference_temperature).toBe(30);expect(owner.moduleSnapshots.simple_editor_valve.parameters.find(p=>p.id==='opening_ratio').default).toBe(.75);
  const library=workspace.modules.find(m=>m.id==='simple_editor_valve');expect(library.parameters.find(p=>p.id==='opening_ratio').default).toBe(.6);
  expect(library.publishedManifest.parameters.find(p=>p.id==='opening_ratio').default).toBe(.75);expect(library.authoringDiagnostics).toEqual([]);
  expect(errors).toEqual([]);writeFileSync(output+'/evidence.json',JSON.stringify({passed:true,devicesReviewed:['pump','valve','exchanger'],display:{opening:75,diameter:40,temperature:25},canonical:{opening:.75,diameter:.04,temperature:298.15},projectDraftRetained:true},null,2)+'\n');
  console.log('Simple module editor passed: existing devices, names and ports, display units, validation, real publication, project application and reload.');
}catch(error){await captureFhd(page,output+'/failure.png');throw error;}
finally{await browser.close();await server.close();}
