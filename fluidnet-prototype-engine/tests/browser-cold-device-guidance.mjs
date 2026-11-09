import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[],output='artifacts/cold-device-guidance';
mkdirSync(output,{recursive:true});page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=async()=>{await page.locator('#dialog-form [type="submit"]').click();await expect(page.locator('#dialog-form')).toHaveCount(0);};
const state=()=>page.evaluate(async()=>(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
const owner=s=>s.projects.find(p=>p.id===s.activeProject);
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();};
async function save(){const r=page.waitForResponse(r=>r.url().endsWith('/workspace')&&r.request().method()==='POST');await page.locator('[data-action="save"]').first().click();expect((await r).ok()).toBe(true);return state();}
async function panel(id,tab='overview'){await page.locator(`.net-node[data-node="${id}"]`).dblclick();const p=page.getByRole('region',{name:id+' 设备参数',exact:true});await p.locator(`[data-action="float-tab"][data-value="${tab}"]`).click();return p;}
const close=p=>p.locator('[data-action="float-close"]').click();
const metric=(p,key)=>p.locator(`[data-device-metric="runtime:${key}"] strong`);
const value=async l=>Number((await l.textContent()).replaceAll(',',''));
async function parameter(id,key,v){const p=await panel(id,'parameters'),field=p.locator(`input[type="number"][data-instance-param="${key}"]`);await field.fill(String(v));await field.blur();await p.locator('[data-action="apply-instance"]').click();await submit();await close(p);}
async function connect(id,port,target){const p=await panel(id,'connections');await p.locator(`[data-action="connect-device-port"][data-port="${port}"]`).click();await page.locator('#dialog-form [name="target"]').selectOption(target);await submit();await close(p);}
async function run(){const r=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');await page.locator('[data-action="run-project"][data-command="run"]').first().click();const response=await r;expect(response.ok(),await response.text()).toBe(true);const {run_id}=await response.json();let record;await expect.poll(async()=>{record=await api('/runs/'+run_id);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:60000}).toBe('completed');await expect(page.locator('#statusbar')).toContainText('已完成');return record;}
try{
  await page.goto(server.base+'/#modules');await expect(page.locator('#app-header')).toContainText('模块平台 · v');const catalog=await api('/catalog');
  for(const id of ['storage_room','unit_cooler','condensing_unit']){
    await page.locator(`[data-module-id="${id}"] [data-action="module-doc"]`).click();await expect(page.locator(`[data-device-guide="${id}"]`)).toBeVisible();
    if(id==='storage_room')await expect(page.locator('#dialog-form')).toContainText('温控脚本');
    await page.locator('#dialog-form [data-action="close-dialog"]').last().click();
  }
  await nav('projects');await page.locator('[data-action="new-project"]').first().click();await page.locator('#dialog-form [name="name"]').fill('从空白搭建单库房');await submit();
  expect(owner(await save()).pages[0].nodes).toHaveLength(0);const ids={};
  for(const id of ['storage_room','unit_cooler','condensing_unit']){
    await nav('modules');await page.locator(`[data-module-id="${id}"] [data-action="insert-module"]`).click();
    const current=owner(await save());ids[id]=current.pages.flatMap(p=>p.nodes).find(n=>n.moduleId===id).id;
  }
  const room=ids.storage_room,cooler=ids.unit_cooler,unit=ids.condensing_unit;
  await connect(unit,'cold',cooler+':supply');await connect(room,'heat',cooler+':heat');
  let p=await panel(room,'parameters');await expect(p.locator('input[data-instance-param="temperature_k"]')).toHaveValue('-10');
  await expect(p.locator('input[data-instance-param="setpoint_temperature_k"]')).toHaveValue('-18');
  await expect(p.locator('input[data-instance-param="heat_input_w"]')).toBeVisible();await expect(p.locator('[data-instance-param="wall_ua_w_k"]')).toBeHidden();
  await p.locator('[data-action="float-tab"][data-value="overview"]').click();await expect(metric(p,'state.temperature_k')).toHaveText('—');await close(p);
  p=await panel(cooler,'parameters');await expect(p.locator('input[data-instance-param="ua_w_k"]')).toHaveValue('1');await expect(p.locator('input[data-instance-param="fan_power_w"]')).toHaveValue('0.3');await close(p);
  p=await panel(unit,'parameters');await expect(p.locator('input[data-instance-param="rated_cooling_power_w"]')).toHaveValue('10');await expect(p.locator('input[data-instance-param="capacity_ratio"]')).toHaveValue('100');await close(p);
  await nav('settings');await page.locator('[data-action="settings-tab"][data-value="medium"]').click();await page.locator('[data-project-field="fluid"]').fill('HEOS::R290');await page.locator('[data-project-field="fluid"]').blur();
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();await page.locator('[data-solver-field="duration"]').fill('600');await page.locator('[data-solver-field="duration"]').blur();await page.locator('[data-solver-field="dt"]').fill('30');await page.locator('[data-solver-field="dt"]').blur();await nav('workbench');
  await nav('controls');await page.locator('[data-live-mode]').selectOption('fast');await nav('workbench');
  const baseline=await run(),vars=baseline.frame.variables;expect(vars[room+'.state.temperature_k']).toBeLessThan(263.15);expect(vars[unit+'.cooling_power_w']).toBeGreaterThan(0);
  p=await panel(room);expect(await value(metric(p,'state.temperature_k'))).toBeCloseTo(vars[room+'.state.temperature_k']-273.15,3);expect(await value(metric(p,'net_heat_w'))).toBeCloseTo(vars[room+'.net_heat_w']/1000,3);
  await p.locator('[data-action="float-dock"]').click();await captureFhd(page,output+'/room-overview.png');await close(p);
  p=await panel(cooler);await expect(metric(p,'state.mode')).toHaveText('制冷阶段');await expect(metric(p,'state.fan_running')).toHaveText('运行');await close(p);
  p=await panel(unit);await expect(metric(p,'state.running')).toHaveText('运行');expect(await value(metric(p,'evaporating_temperature_k'))).toBeCloseTo(vars[unit+'.evaporating_temperature_k']-273.15,3);await p.locator('[data-action="float-dock"]').click();await captureFhd(page,output+'/unit-overview.png');await close(p);
  await parameter(room,'heat_input_w',2);const loaded=await run();expect(loaded.request.project.instances.find(n=>n.id===room).parameters.heat_input_w).toBe(2000);expect(loaded.frame.variables[room+'.state.temperature_k']).toBeGreaterThan(vars[room+'.state.temperature_k']);
  await parameter(unit,'run_request',0);const stopped=await run();expect(stopped.frame.variables[unit+'.state.running']).toBe(0);expect(stopped.frame.variables[unit+'.cooling_power_w']).toBe(0);
  p=await panel(unit);await expect(metric(p,'state.running')).toHaveText('停止');await close(p);
  await parameter(unit,'run_request',1);await parameter(room,'heat_input_w',0);
  // A thermostat is explicitly added through the control page; a room setpoint alone is not an actuator.
  await nav('controls');await page.locator('[data-action="add-control-program"]').click();await page.locator('#dialog-form [name="id"]').fill('room_thermostat');await page.locator('#dialog-form [name="name"]').fill('单库房温控');await submit();
  await page.locator('[data-control-inputs]').fill([room+'.state.temperature_k',room+'.param.setpoint_temperature_k',room+'.param.hysteresis_k'].join('\n'));await page.locator('[data-control-inputs]').blur();
  await page.locator('[data-control-outputs]').fill(unit+'.param.run_request');await page.locator('[data-control-outputs]').blur();
  await page.locator('[data-control-setting="period"]').fill('5000');await page.locator('[data-control-setting="period"]').blur();
  await page.locator('#control-code').fill(`def initialize(ctx):\n    ctx.state["request"] = 1.0\n\ndef step(ctx, dt_s):\n    t = ctx.read("${room}.state.temperature_k")\n    target = ctx.read("${room}.param.setpoint_temperature_k")\n    band = ctx.read("${room}.param.hysteresis_k")\n    if t >= target + band:\n        ctx.state["request"] = 1.0\n    elif t <= target - band:\n        ctx.state["request"] = 0.0\n    ctx.write("${unit}.param.run_request", ctx.state["request"])\n\ndef finalize(ctx):\n    pass\n`);await page.locator('#control-code').blur();await page.locator('[data-control-enabled]').check();await nav('workbench');
  await parameter(room,'setpoint_temperature_k',-9);const satisfied=await run();expect(satisfied.frame.variables[unit+'.state.running']).toBe(0);
  await parameter(room,'setpoint_temperature_k',-18);const cooling=await run();expect(cooling.frame.variables[unit+'.state.running']).toBe(1);
  expect(cooling.frame.variables[room+'.state.temperature_k']).toBeLessThan(satisfied.frame.variables[room+'.state.temperature_k']);
  await save();await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');p=await panel(room);expect(await value(metric(p,'state.temperature_k'))).toBeCloseTo(cooling.frame.variables[room+'.state.temperature_k']-273.15,3);
  await close(p);const project=owner(await save());expect(project.pages[0].nodes).toHaveLength(3);expect(project.pages[0].edges).toHaveLength(2);expect(await api('/catalog')).toEqual(catalog);expect(errors).toEqual([]);
  writeFileSync(output+'/evidence.json',JSON.stringify({passed:true,ids,baselineC:vars[room+'.state.temperature_k']-273.15,loadedC:loaded.frame.variables[room+'.state.temperature_k']-273.15,manualStop:true,thermostatSetpoints:[-9,-18],saved:true,runIds:[baseline.id,loaded.id,stopped.id,satisfied.id,cooling.id]},null,2)+'\n');
  console.log('Cold device guidance passed: blank assembly, unit conversion, real cooling, increased load, stop/start, explicit thermostat, setpoint changes and reload.');
}catch(error){console.error(await page.locator('#dialog-layer').innerText(),await page.locator('#toast').innerText());await captureFhd(page,output+'/failure.png');throw error;}
finally{await browser.close();await server.close();}
