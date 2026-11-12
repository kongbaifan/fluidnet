import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),output='artifacts/core-workflow/parameter-controls';
let browser,page,runId;
const errors=[],commands=[],evidence={};
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const card=()=>page.locator('[data-pid-card="temperature"]');
const input=key=>card().locator(`[data-pid-field="${key}"]`);
const selected=data=>data.projects.find(project=>project.id===data.activeProject);
const state=()=>page.evaluate(async()=>(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();};
async function save(){
 const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
 await page.locator('[data-action="save"]').first().click();expect((await response).ok()).toBe(true);
 await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');return state();
}
async function at(time){
 let record;
 await expect.poll(async()=>{record=await api('/runs/'+runId);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.frame?.time_s;},{timeout:20000}).toBe(time);
 return record;
}
async function newStep(){
 await nav('workbench');
 const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
 await page.locator('.runbar [data-command="step"]').click();runId=(await(await posted).json()).run_id;
 return at(1);
}
async function step(time){await nav('workbench');await page.locator('.runbar [data-command="step"]').click();return at(time);}
async function stop(){
 await nav('workbench');await page.locator('.runbar [data-command="stop"]').click();
 await expect.poll(async()=>(await api('/runs/'+runId)).status).toBe('cancelled');
 await expect(page.locator('#statusbar')).toContainText('已停止');
}
async function setController(key,value){
 const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/v1/runs/${runId}/command`&&r.request().method()==='POST');
 if(key==='mode')await input(key).selectOption(value);else{await input(key).fill(String(value));await input(key).blur();}
 const r=await response;expect(r.ok(),await r.text()).toBe(true);const receipt=await r.json();
 await expect.poll(async()=>(await api('/runs/'+runId+'/events')).events.findLast(e=>e.command_id===receipt.command_id)?.command_status).toBe('applied');
 return receipt;
}
try{
 browser=await chromium.launch({channel:'msedge',headless:true});page=await browser.newPage(FHD_CONTEXT);
 page.setDefaultTimeout(15000);page.on('pageerror',error=>errors.push(error.message));
 page.on('request',request=>{if(request.method()==='POST'&&new URL(request.url()).pathname.endsWith('/command'))commands.push(request.postDataJSON());});
 await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 await page.locator('[data-action="start-modeling"]').first().click();

 // A cancelled device preview keeps the user's draft but does not apply it.
 const valve=page.locator('[data-float-id="V1"]');
 const oldValve=selected(await save()).pages.flatMap(p=>p.nodes).find(n=>n.id==='V1');
 await valve.locator('input[type="number"][data-instance-param="opening"]').fill('55');
 await valve.locator('input[type="number"][data-instance-param="opening"]').blur();
 await valve.locator('[data-action="apply-instance"]').click();
 await expect(page.getByRole('dialog')).toContainText('55');
 await page.getByRole('dialog').locator('[data-action="close-dialog"]').last().click();
 const cancelledValve=selected(await save()).pages.flatMap(p=>p.nodes).find(n=>n.id==='V1');
 expect(cancelledValve.params).toEqual(oldValve.params);expect(cancelledValve.draft.opening).toBe(55);expect(commands).toHaveLength(0);
 evidence.previewCancelled=true;

 await nav('controls');await page.locator('[data-action="pid-example"][data-kind="temperature"]').click();
 await expect(page.locator('.runbar [data-command="step"]')).toBeVisible();
 const first=await newStep();await nav('controls');
 const original=first.frame.variables['controller.temperature.setpoint'];
 await expect(input('setpoint')).toHaveValue(String(original));
 const beforeInvalid=commands.length;
 for(const invalid of ['', '1e309']){
   await input('setpoint').fill(invalid);await input('setpoint').blur();
   await expect(page.locator('#toast')).toContainText('有效数值');
   await expect(input('setpoint')).toHaveValue(String(original));
 }
 await input('manual_output').fill('1000000');await input('manual_output').blur();
 await expect(page.locator('#toast')).toContainText('手动输出超出范围');
 expect(commands).toHaveLength(beforeInvalid);
 expect((await api('/runs/'+runId)).frame.variables['controller.temperature.setpoint']).toBe(original);
 evidence.invalidPidRejected=true;

 // While a valid acknowledgement is delayed, duplicate change events do not
 // submit twice and subsequent typing remains an unapplied input until blur.
 let release,entered,handled,routeError;
 const gate=new Promise(resolve=>{release=resolve;});const accepted=new Promise(resolve=>{entered=resolve;});
 const commandPath=`**/api/v1/runs/${runId}/command`;
 const delayed=route=>{
   const body=route.request().postDataJSON();
   if(body.action!=='controller'||body.parameter_id!=='setpoint'||body.value!==304.15)return route.continue();
   handled=(async()=>{const response=await route.fetch();entered(await response.json());await gate;await route.fulfill({response});})().catch(error=>{routeError=error;});
   return handled;
 };
 await page.route(commandPath,delayed);
 const writesBefore=commands.length;
 try{
   await input('setpoint').fill('304.15');await input('setpoint').blur();await accepted;
   await input('setpoint').dispatchEvent('change');
   await input('setpoint').fill('306.15');release();await handled;
   await expect.poll(async()=>selected(await state()).controllers[0].setpoint).toBe(304.15);
   await expect(input('setpoint')).toHaveValue('306.15');
   expect(commands.length-writesBefore).toBe(1);
 }finally{release();await page.unroute(commandPath,delayed);await handled;if(routeError)throw routeError;}
 await input('setpoint').blur();
 await expect.poll(async()=>selected(await state()).controllers[0].setpoint).toBe(306.15);
 evidence.pendingTypingPreserved=true;evidence.duplicatePidSuppressed=true;

 // A server refusal leaves both the saved setting and sampled value intact.
 const reject=route=>route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:{code:'PID_COMMAND_INVALID',message:'专项拒绝：参数未接受'}})});
 await page.route(commandPath,reject);
 try{
   await input('setpoint').fill('307.15');await input('setpoint').blur();
   await expect(page.locator('#toast')).toContainText('参数未接受');
   await expect(input('setpoint')).toHaveValue('306.15');
   expect(selected(await state()).controllers[0].setpoint).toBe(306.15);
 }finally{await page.unroute(commandPath,reject);}
 evidence.rejectionPreserved=true;

 await setController('mode','manual');await setController('manual_output',1500);
 const manual=await step(2);expect(manual.frame.variables['controller.temperature.mode']).toBe('manual');
 expect(manual.frame.variables['controller.temperature.manual_output']).toBe(1500);
 expect(manual.frame.variables['controller.temperature.output']).toBe(1500);
 await nav('controls');await setController('mode','auto');
 const automatic=await step(3);expect(automatic.frame.variables['controller.temperature.mode']).toBe('auto');
 expect(automatic.frame.variables['controller.temperature.output']).toBeGreaterThanOrEqual(0);
 evidence.manualAuto={manualOutput:1500,autoOutput:automatic.frame.variables['controller.temperature.output']};
 await stop();

 await nav('controls');
 await page.getByLabel('项目控制脚本').fill('def initialize(ctx):\n    pass\n\ndef step(ctx, dt_s):\n    ctx.write("controller.temperature.mode", "manual")\n    ctx.write("controller.temperature.manual_output", 1200)\n    ctx.write("controller.temperature.setpoint", 310.15)\n\ndef finalize(ctx):\n    pass\n');
 await page.getByLabel('控制输入',{exact:true}).fill('');
 await page.getByLabel('控制输出',{exact:true}).fill('controller.temperature.mode\ncontroller.temperature.manual_output\ncontroller.temperature.setpoint');
 await page.locator('[data-control-enabled]').check();
 const initialControllers=selected(await save()).controllers;
 const controlled=await newStep();await nav('controls');
 await expect(input('mode')).toHaveValue('manual');await expect(input('setpoint')).toHaveValue('310.15');
 await expect(input('manual_output')).toHaveValue('1200');
 for(const key of ['mode','setpoint','manual_output']){
   await expect(input(key)).toBeDisabled();
   await expect(card().locator(`[data-pid-field-note="${key}"]`)).toContainText('由脚本 control 接管');
   await expect(card().locator(`[data-pid-field-note="${key}"]`)).toContainText('初始配置');
 }
 await expect(page.locator('[data-save-status]')).not.toContainText('有未保存修改');
 expect(selected(await save()).controllers).toEqual(initialControllers);
 const protectedCount=commands.length;
 await input('setpoint').evaluate(element=>{element.value='299.15';element.dispatchEvent(new Event('change',{bubbles:true}));});
 await expect(page.locator('#toast')).toContainText('由脚本 control 接管');
 await expect(input('setpoint')).toHaveValue('310.15');expect(commands).toHaveLength(protectedCount);

 // Editing next-run script enablement cannot relinquish the current ownership.
 await page.locator('[data-control-enabled]').uncheck();
 for(const key of ['mode','setpoint','manual_output'])await expect(input(key)).toBeDisabled();
 await nav('workbench');const target=controlled.request.project.controllers[0].instance_id;
 await page.locator(`.net-node[data-node="${target}"]`).dblclick();
 const device=page.locator(`[data-float-id="${target}"]`);
 await device.locator('[data-action="float-tab"][data-value="parameters"]').click();
 const ownerNote=device.locator('[data-parameter-owner]').filter({hasText:'PID temperature'});
 await expect(ownerNote).toContainText('手动输出');await expect(ownerNote).not.toContainText('自动控制');
  if(!await ownerNote.isVisible())await device.locator('.device-other-parameters > summary').click();
  await ownerNote.scrollIntoViewIfNeeded();await expect(ownerNote).toBeVisible();
 await captureFhd(page,output+'/script-controlled-device.png');
 await stop();await nav('controls');
 await expect(input('mode')).toHaveValue(initialControllers[0].mode);
 await expect(input('setpoint')).toHaveValue(String(initialControllers[0].setpoint));
 await expect(input('mode')).toBeEnabled();
 expect(selected(await save()).controllers).toEqual(initialControllers);
 evidence.scriptOwnership={actualMode:'manual',actualSetpoint:310.15,manualOutput:1200,initialSettingsPreserved:true};

 expect(errors).toEqual([]);mkdirSync(output,{recursive:true});
 writeFileSync(output+'/summary.json',JSON.stringify({...evidence,errors},null,2)+'\n');
 console.log(JSON.stringify({...evidence,errors},null,2));
}catch(error){if(page)await captureFhd(page,output+'/failure.png').catch(()=>{});throw error;}
finally{if(browser)await browser.close();await server.close();}
