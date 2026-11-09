import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

// Exercise the public workflow from a new module to an assembled, saved project.
// JavaScript reads persisted state only; project changes go through the UI.
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[],evidence={};
page.on('pageerror',error=>errors.push(error.message));
page.setDefaultTimeout(15000);
const output='artifacts/module-assembly';mkdirSync(output,{recursive:true});
const navigate=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const state=()=>page.evaluate(async()=>{
  const {FluidNetDraftStore}=await import('/draft-store.js');
  return FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));
});
const active=s=>s.projects.find(p=>p.id===s.activeProject);
const api=async path=>{const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();};
const submit=async()=>{await page.locator('#dialog-form [type="submit"]').click();await expect(page.locator('#dialog-form')).toHaveCount(0);};
async function save(){
  const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await pending).ok()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');return state();
}
async function edit(id){await navigate('modules');await page.locator(`[data-module-id="${id}"] [data-action="edit-module"]`).click();}
async function newProject(name){
  await navigate('projects');await page.locator('[data-action="new-project"]').first().click();
  await page.locator('#dialog-form [name="name"]').fill(name);await submit();return active(await save());
}
async function publish(){
  const pending=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();const response=await pending,body=await response.json();
  expect(response.status(),JSON.stringify(body)).toBe(201);await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();return body.module;
}
async function quickInsert(id){
  await navigate('modules');await page.locator(`[data-module-id="${id}"] [data-action="insert-module"]`).click();
  const owner=active(await save());return owner.pages.find(pg=>pg.id===owner.activePage).nodes.at(-1);
}
async function parameter(id,key,value){
  await page.locator(`[data-node="${id}"]`).dblclick();
  const field=page.locator(`[data-instance-param="${key}"][data-id="${id}"]`).last();await field.fill(String(value));await field.blur();
  await page.locator(`[data-action="apply-instance"][data-id="${id}"]`).last().click();await submit();
  await page.locator('[data-action="float-close"]').last().click();
}
async function connect(id,port,target){
  await page.locator(`[data-node="${id}"]`).dblclick();
  const panel=page.getByRole('region',{name:id+' 设备参数',exact:true});
  await panel.locator('[data-action="float-tab"][data-value="connections"]').click();
  await panel.locator(`[data-action="connect-device-port"][data-port="${port}"]`).click();
  const choices=await page.locator('#dialog-form [name="target"] option').evaluateAll(options=>options.map(o=>o.value));
  expect(choices.every(value=>!value.startsWith(id+':'))).toBe(true);
  await page.locator('#dialog-form [name="target"]').selectOption(target);await submit();
  await panel.locator('[data-action="float-close"]').click();return choices;
}
async function run(){
  await navigate('workbench');const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const response=await pending;expect(response.ok(),await response.text()).toBe(true);const {run_id}=await response.json();let record;
  await expect.poll(async()=>{record=await api('/runs/'+run_id);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:45000}).toBe('completed');
  await expect(page.locator('#statusbar')).toContainText('已完成');return record;
}
let releasePending=()=>{};
try{
  await page.goto(server.base+'/#modules');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  // Failed asynchronous creation preserves input and cannot submit twice.
  let requests=0;const gate=new Promise(resolve=>{releasePending=resolve;});
  await page.route('**/api/v1/modules/from-template',async route=>{requests++;await gate;await route.fulfill({status:503,json:{detail:'创建暂时失败，请重试。'}});});
  await page.locator('[data-action="new-module"]').click();
  await page.locator('#dialog-form [name="name"]').fill('自定义阻力设备');
  await page.locator('#dialog-form [name="code"]').fill('ASSEMBLY_RESISTOR');
  await expect(page.locator('#dialog-form [name="base"]')).toHaveValue('template:resistance');
  await page.locator('#dialog-form [type="submit"]').click();
  await expect(page.locator('#dialog-form')).toHaveAttribute('aria-busy','true');
  await expect(page.locator('#dialog-form [type="submit"]')).toBeDisabled();
  await page.locator('#dialog-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  await expect.poll(()=>requests).toBe(1);releasePending();
  await expect(page.locator('#dialog-error')).toContainText('创建暂时失败');
  await expect(page.locator('#dialog-form [name="code"]')).toHaveValue('ASSEMBLY_RESISTOR');
  await expect(page.locator('#dialog-form [type="submit"]')).toBeEnabled();
  await page.unroute('**/api/v1/modules/from-template');await submit();
  await expect(page.locator('[data-action="use-module"]')).toBeDisabled();
  await navigate('modules');const beforeInsert=active(await save());
  await page.locator('[data-module-id="assembly_resistor"] [data-action="insert-module"]').click();
  await expect(page.locator('#toast')).toContainText('先校验并保存模块版本');
  await expect(page.locator('[data-module-id="assembly_resistor"]')).toBeVisible();
  expect(active(await save()).moduleSnapshots).toEqual(beforeInsert.moduleSnapshots);
  await edit('assembly_resistor');
  // Saving runs the real backend's validation and independent test.
  await page.locator('.editor-tabs [data-action="editor-tab"][data-value="contract"]').click();
  const contract=JSON.parse(await page.locator('[data-module-contract]').inputValue());
  Object.assign(contract.parameters.find(p=>p.id==='loss_coefficient'),{default:12,minimum:1,maximum:100,runtime:true});
  contract.parameters.find(p=>p.id==='diameter_m').default=.04;
  await page.locator('[data-module-contract]').fill(JSON.stringify(contract));
  const v1=await publish();expect(v1.version).toBe(1);
  await expect(page.locator('.module-use-bar')).toContainText('已保存 v1');
  await captureFhd(page,output+'/saved-module.png');

  const project=await newProject('模块组装验收');
  await page.locator('[data-action="new-canvas"]').first().click();await page.locator('#dialog-form [name="name"]').fill('设备装配');await submit();
  const canvas=active(await save()).activePage;
  await edit(v1.id);await page.locator('[data-action="use-module"]').click();
  await page.locator('#dialog-form [name="project"]').selectOption(project.id);
  await page.locator('#dialog-form [name="page"]').selectOption(canvas);
  await expect(page.locator('#module-insertion-version')).toContainText('已保存的 v1');await submit();
  let owner=active(await save());const device=owner.pages.find(pg=>pg.id===canvas).nodes[0];
  expect(owner.pages[0].nodes).toHaveLength(0);expect(device.moduleId).toBe(v1.id);expect(device.params.loss_coefficient).toBe(12);
  await expect(page.locator(`[data-quick-node="${device.id}"] .quick-param-label`)).toContainText('0.04');
  const panel=page.getByRole('region',{name:device.id+' 设备参数',exact:true});
  await panel.locator('[data-action="float-tab"][data-value="connections"]').click();
  await panel.locator('[data-action="connect-device-port"][data-port="in0"]').click();
  await expect(page.locator('#dialog-form [type="submit"]')).toBeDisabled();
  await expect(page.locator('#connection-hint')).toContainText('请先在目标画布放入');
  await page.locator('#dialog-form [data-action="close-dialog"]').last().click();await panel.locator('[data-action="float-close"]').click();

  const inlet=await quickInsert('source'),outlet=await quickInsert('source');
  await parameter(inlet.id,'pressure',250);await parameter(outlet.id,'pressure',120);
  await connect(device.id,'in0',inlet.id+':out0');
  const remaining=await connect(device.id,'out0',outlet.id+':out0');expect(remaining).not.toContain(inlet.id+':out0');
  await navigate('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="duration"]').fill('1');await page.locator('[data-solver-field="duration"]').blur();
  const original=await run(),flowKey=device.id+'.main.mass_flow_kg_s',flow=original.frame.variables[flowKey];
  const density=original.frame.variables[device.id+'.density_kg_m3'];
  const reference=Math.PI*.04**2/4*Math.sqrt(2*density*130000/12);
  expect(Math.abs(flow/reference-1)).toBeLessThan(1e-6);
  await parameter(device.id,'loss_coefficient',48);const adjusted=await run();expect(adjusted.frame.variables[flowKey]/flow).toBeCloseTo(.5,6);
  await save();await captureFhd(page,output+'/assembled-project.png');
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  owner=active(await state());expect(owner.moduleSnapshots[v1.id].version).toBe(1);
  expect(owner.pages.find(pg=>pg.id===canvas).nodes.find(n=>n.id===device.id).params.loss_coefficient).toBe(48);
  expect((await run()).frame.variables[flowKey]).toBeCloseTo(adjusted.frame.variables[flowKey],7);
  evidence.assembly={project:project.id,canvas,device:device.id,flow,reference,adjustedFlow:adjusted.frame.variables[flowKey]};

  // A new library release is reusable, while existing projects clearly retain their version.
  await edit(v1.id);await page.locator('.editor-tabs [data-action="editor-tab"][data-value="code"]').click();
  const source=await page.locator('#module-code').inputValue();await page.locator('#module-code').fill(source+'\n# 第二版\n');
  expect((await publish()).version).toBe(2);
  await page.locator('[data-action="use-module"]').click();
  await expect(page.locator('#module-insertion-version')).toContainText('此项目固定使用 v1，模块库已保存 v2');
  await captureFhd(page,output+'/version-choice.png');await submit();
  owner=active(await save());expect(owner.pages.find(pg=>pg.id===canvas).nodes.at(-1).package.version).toBe('1.0.0');
  // Remove this unconnected extra device before leaving the reusable assembled project.
  const extra=owner.pages.find(pg=>pg.id===canvas).nodes.at(-1);
  await page.locator('[data-action="float-close"]').last().click();
  await page.locator(`[data-action="delete-node"][data-id="${extra.id}"]`).first().click();await save();
  const reuse=await newProject('模块复用验收');await edit(v1.id);
  await page.locator('.editor-tabs [data-action="editor-tab"][data-value="code"]').click();await page.locator('#module-code').fill(source+'\n# 尚未保存的草稿\n');
  await page.locator('[data-action="use-module"]').click();await expect(page.locator('#module-insertion-version')).toContainText('已保存的 v2');await submit();
  owner=active(await save());expect(owner.id).toBe(reuse.id);expect(owner.moduleSnapshots[v1.id].version).toBe(2);
  expect(owner.moduleSnapshots[v1.id].manifest.source.runtime).toContain('第二版');
  expect(owner.moduleSnapshots[v1.id].manifest.source.runtime).not.toContain('尚未保存');
  expect((await state()).modules.find(m=>m.id===v1.id).source.runtime).toContain('尚未保存');
  // This project has just one canvas; connecting must still open a usable picker.
  expect(owner.pages).toHaveLength(1);const reused=owner.pages[0].nodes[0];
  const reusePanel=page.getByRole('region',{name:reused.id+' 设备参数',exact:true});
  await reusePanel.locator('[data-action="float-tab"][data-value="connections"]').click();
  await reusePanel.locator('[data-action="connect-device-port"][data-port="in0"]').click();
  await expect(page.locator('#dialog-title')).toHaveText('连接设备');
  await expect(page.locator('#dialog-form [type="submit"]')).toBeDisabled();
  await page.locator('#dialog-form [data-action="close-dialog"]').last().click();

  // Closing a pending create must not create a module or close a newer dialog.
  await navigate('modules');const lateGate=new Promise(resolve=>{releasePending=resolve;});let captured=false,delivered=false;
  await page.route('**/api/v1/modules/from-template',async route=>{const response=await route.fetch();captured=true;await lateGate;await route.fulfill({response});delivered=true;});
  await page.locator('[data-action="new-module"]').click();await page.locator('#dialog-form [name="code"]').fill('CANCELLED_MODULE');
  await page.locator('#dialog-form [type="submit"]').click();await expect.poll(()=>captured).toBe(true);
  await page.locator('#dialog-form [data-action="close-dialog"]').last().click();await page.locator('[data-action="new-module"]').click();
  releasePending();await expect.poll(()=>delivered).toBe(true);
  await expect(page.locator('#dialog-form [name="code"]')).toHaveValue('CUSTOM_VALVE');
  await page.locator('#dialog-form [data-action="close-dialog"]').last().click();await save();
  expect((await state()).modules.some(m=>m.id==='cancelled_module')).toBe(false);
  expect(errors).toEqual([]);evidence.passed=true;
  writeFileSync(output+'/evidence.json',JSON.stringify(evidence,null,2)+'\n');console.log('Module assembly passed: create retry/cancel, publish, choose canvas, connect, run, adjust, reload and reuse pinned releases.');
}catch(error){await captureFhd(page,output+'/failure.png');throw error;}
finally{releasePending();await browser.close();await server.close();}
