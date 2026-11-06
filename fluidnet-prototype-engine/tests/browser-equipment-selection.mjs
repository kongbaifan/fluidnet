import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const panel=()=>page.locator('[data-float-id="V1"]');
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
async function saved(){
 const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
 await page.locator('[data-action="save"]').first().click();expect((await receipt).ok()).toBe(true);
 return page.evaluate(()=>window.FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
}
const owner=s=>s.projects.find(p=>p.id===s.activeProject);
const node=s=>owner(s).pages.flatMap(p=>p.nodes).find(n=>n.id==='V1');
async function design(){
 await panel().locator('[data-action="equipment-selection"]').click();
 const dialog=page.getByRole('dialog');
 await dialog.getByLabel('目标体积流量',{exact:true}).fill('12');
 await dialog.getByLabel('设计压差',{exact:true}).fill('130');
 await dialog.getByLabel('阀门开度',{exact:true}).fill('60');
 await dialog.getByLabel('设计液温',{exact:true}).fill('30');
 const result=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/modules/design');
 await submit();const response=await result;expect(response.ok(),await response.text()).toBe(true);
 const request=response.request().postDataJSON();
 expect(request.parameters.design_pressure_drop_pa).toBe(130000);
 expect(request.parameters.design_temperature_k).toBe(303.15);
 expect(request.parameters.opening_ratio).toBe(.6);
 expect(request.parameters.design_flow_m3_s).toBeCloseTo(12/3600,12);
 await expect(page.getByRole('dialog')).toContainText('选型结果预览');
 return {request,response:await response.json()};
}
try{
 await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 await nav('modules');await page.locator('[data-module-id="design_valve"] [data-action="module-example"]').click();
 await page.locator('[data-node="V1"]').dblclick();
 const before=await saved(),frozen=owner(before).moduleSnapshots.design_valve.manifest;
 const first=await design();
 expect(first.request.module.definition_hash).toBe(frozen.definition_hash);
 await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
 let current=await saved();expect(node(current).params).toEqual(node(before).params);expect(node(current).draft).toEqual(node(before).draft);expect(current.models).toEqual(before.models);

 // Publish a new design while the project retains the original released definition.
 await nav('modules');await page.locator('[data-module-id="design_valve"] [data-action="edit-module"]').click();
 await page.locator('[data-action="editor-tab"][data-value="code"]').first().click();
 const oldSource=await page.locator('#module-code-design').inputValue();
 await page.locator('#module-code-design').fill(oldSource.replace("ctx.set('kv_m3_h', kv)","ctx.set('kv_m3_h', kv * 2)"));
 const publish=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/modules/versions'&&r.request().method()==='POST');
 await page.locator('[data-action="save-module-version"]').click();expect((await publish).ok()).toBe(true);
 await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
 await nav('workbench');await page.locator('[data-node="V1"]').dblclick();
 const second=await design();
 expect(second.request.module.definition_hash).toBe(frozen.definition_hash);
 expect(second.response.parameters.kv_m3_h).toBe(first.response.parameters.kv_m3_h);
 await page.getByRole('dialog').getByLabel('型号名称',{exact:true}).fill('12立方每小时选型');
 await submit();
 current=await saved();
 expect(node(current).params).toEqual(node(before).params);
 expect(node(current).draft.kv_m3_h).toBeCloseTo(second.response.parameters.kv_m3_h,10);
 expect(node(current).draft.opening_ratio).toBe(60);
 const selected=current.models.find(m=>m.id===node(current).draftModelId);
 expect(selected.name).toBe('12立方每小时选型');expect(selected.moduleVersion).toBe(1);
 expect(selected.selection.definitionHash).toBe(frozen.definition_hash);
 await panel().locator('[data-action="apply-instance"]').click();await submit();
 current=await saved();expect(node(current).params.opening_ratio).toBe(60);
 expect(node(current).params.kv_m3_h).toBeCloseTo(second.response.parameters.kv_m3_h,10);
 await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 const restored=await saved();expect(node(restored).params).toEqual(node(current).params);
 expect(restored.models.find(m=>m.id===selected.id).selection).toEqual(selected.selection);
 await page.locator('[data-node="V1"]').dblclick();await captureFhd(page,'artifacts/equipment-selection-1080p.png');
 expect(errors).toEqual([]);console.log(JSON.stringify({selection:true,cancelUnchanged:true,frozenDesign:true,savedModel:true,explicitApply:true,reload:true,errors}));
}catch(e){console.error(e);await captureFhd(page,'artifacts/equipment-selection-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
