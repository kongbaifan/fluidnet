import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.locator('#dialog-form button[type="submit"]').click();
async function library(name,prefix){
 await nav('modules');await page.locator('[data-action="equipment-library"]').click();
 await page.getByLabel('设备组模板',{exact:true}).selectOption(name);await page.getByLabel('实例前缀',{exact:true}).fill(prefix);await submit();
 await expect(page.locator(`.net-node[data-node="${prefix}-Equipment"]`)).toBeVisible({timeout:20000});
}
try{
 await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 for(const [name,prefix] of [['design_pump','Pump'],['design_fan','Fan'],['design_plate_exchanger','Plate']]){
  await library(name,prefix);await page.locator(`.net-node[data-node="${prefix}-Equipment"]`).dblclick();
  const panel=page.locator(`[data-float-id="${prefix}-Equipment"]`);await panel.locator('[data-action="equipment-selection"]').click();
  await expect(page.getByRole('dialog')).toContainText('设计目标与参考条件');
  const result=page.waitForResponse(r=>r.url().endsWith('/modules/design')&&r.request().method()==='POST');await submit();
  const response=await result;expect(response.ok(),await response.text()).toBe(true);
  await expect(page.getByRole('dialog')).toContainText('选型结果预览');await page.getByLabel('保存方式',{exact:true}).selectOption('model');await submit();
  await panel.locator('[data-action="equipment-provenance"]').click();await expect(page.getByRole('dialog')).toContainText('designHash');await page.locator('[data-action="close-dialog"]').last().click();
  if(await panel.locator('[data-action="apply-instance"]').isEnabled()){await panel.locator('[data-action="apply-instance"]').click();await submit();}
  await panel.locator('[data-action="float-close"]').click();
 }
 await library('group_pump_branch','Branch');
 const requested=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
 await page.locator('[data-action="run-project"][data-command="run"]').first().click();const rid=(await(await requested).json()).run_id;
 await expect.poll(async()=>{const r=await(await page.request.get(server.base+'/api/v1/runs/'+rid)).json();if(r.status==='failed')throw Error(JSON.stringify(r.frame.diagnostics));return r.status;},{timeout:30000}).toBe('completed');
 await page.locator('[data-action="run-project"][data-command="stop"]').first().click();
 await library('fcu_terminal','Coil');await page.locator('.net-node[data-node="Coil-Equipment"]').dblclick();
 const panel=page.locator('[data-float-id="Coil-Equipment"]');await panel.locator('[data-action="coil-geometry-design"]').click();await submit();
 await expect(page.getByRole('dialog')).toContainText('盘管几何方案预览');await submit();
 await expect(panel.locator('[data-pending-for]')).not.toHaveText('0 项待应用');
 await panel.locator('[data-action="apply-instance"]').click();await submit();
 await captureFhd(page,'artifacts/design-library.png');
 const saved=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');await page.locator('[data-action="save"]').first().click();expect((await saved).ok()).toBe(true);
 await page.reload();await expect(page.locator('.net-node[data-node="Coil-Equipment"]')).toBeVisible();
 expect(errors).toEqual([]);console.log(JSON.stringify({designs:3,groupRun:true,geometry:true,reload:true,errors}));
}catch(e){console.error(e);await captureFhd(page,'artifacts/design-library-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
