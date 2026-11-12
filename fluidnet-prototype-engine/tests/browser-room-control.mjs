import {chromium,expect} from '@playwright/test';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-room-control-'));
const browser=await chromium.launch({channel:'msedge',headless:true});
let launched,page;
const errors=[];
async function api(path,body){
  const response=await page.request.fetch(launched.base+'/api/v1'+path,{method:body===undefined?'GET':'POST',data:body});
  expect(response.ok(),await response.text()).toBe(true);return response.json();
}
async function create(name){
  const title={'room-temperature-control':'房间自动温控 · 初始降温',
    'room-control-load-step':'房间自动温控 · 负荷阶跃','room-control-setpoint-step':'房间自动温控 · 设定变化'}[name];
  await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
  await page.getByLabel('风侧示例',{exact:true}).selectOption(name);
  await page.getByRole('button',{name:'创建项目',exact:true}).click();
  await expect(page.getByLabel('风侧当前项目',{exact:true}).locator('option:checked')).toHaveText(title,{timeout:20000});
  await expect(page.getByRole('button',{name:'反馈控制',exact:true})).toBeVisible({timeout:20000});
  await expect(page.getByRole('button',{name:'运行计算',exact:true})).toBeEnabled({timeout:20000});
}
async function duration(value){
  await page.getByRole('button',{name:'湿空气设置',exact:true}).click();
  await page.getByLabel('动态运行时长 / s',{exact:true}).fill(String(value));
  await page.getByRole('button',{name:'应用设置',exact:true}).click();
}
async function run(){
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);
  const id=(await response.json()).run_id;
  await expect.poll(async()=>{
    const record=await api('/runs/'+id);return ['completed','failed','cancelled'].includes(record.status);
  },{timeout:600000,intervals:[500,2000]}).toBe(true);
  const record=await api('/runs/'+id);expect(record.status,JSON.stringify(record.frame)).toBe('completed');
  await expect(page.locator('[data-air-provenance]')).toContainText(id.slice(0,12),{timeout:20000});
  console.log(JSON.stringify({id,time:record.frame.time_s,room:record.frame.variables['Room.state.temperature_k']-273.15,
    target:record.frame.variables['controller.room-temperature.setpoint']-273.15}));
  return record;
}
try{
  launched=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  page=await(await browser.newContext({...FHD_CONTEXT,acceptDownloads:true})).newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(launched.base+'/#air');
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled({timeout:20000});
  await create('room-temperature-control');
  const first=await run();
  expect(first.frame.time_s).toBe(2400);
  expect(first.request.project.controllers[0].measurement).toBe('Room.state.temperature_k');
  expect(first.frame.variables['Room.state.temperature_k']).toBeCloseTo(299.15,0);
  expect(first.frame.variables['Chiller.state.electric_energy_j']).toBeGreaterThan(0);
  await expect(async()=>{
    const cached=await page.evaluate(async () => (await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
    const cachedProject=cached.projects.find(p=>p.id===cached.activeProject);
    expect(cachedProject.controllers[0].setpoint).toBeCloseTo(299.15,8);
    expect(cachedProject.run.history.at(-1).t).toBe(2400);
    expect(cachedProject.run.archiveCache).toBeTruthy();
  }).toPass({timeout:15000,intervals:[250,1000]});
  await expect(page.locator('[data-save-status]')).not.toContainText('本地草稿保存失败');
  // Complete frames retain air/water tables, not just the small list of controller signals.
  expect(first.frame.variables['Chiller.out0.temperature_k']).toBeGreaterThan(273.15);
  await page.getByRole('button',{name:'反馈控制',exact:true}).click();
  const target=page.locator('[data-air-control-value="controller.room-temperature.setpoint"]');
  await expect(target).toHaveText('26');
  await expect(page.getByRole('img',{name:'room-temperature 反馈与设定曲线'})).toBeVisible();
  await expect(page.getByRole('img',{name:'room-temperature 调节输出曲线'})).toBeVisible();
  await expect(page.locator('#toast')).toBeHidden({timeout:5000});
  await captureFhd(page,'artifacts/room-control-feedback-1080p.png');
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'HTML 报告',exact:true}).click();
  const report=join(directory,'room.html');await(await download).saveAs(report);
  expect(readFileSync(report,'utf8')).toContain('controller.room-temperature.setpoint');
  await page.getByRole('button',{name:'调整设定',exact:true}).click();
  await expect(page.getByLabel('目标设定 / °C',{exact:true})).toHaveValue('26');
  await page.getByLabel('目标设定 / °C',{exact:true}).fill('25');
  await page.getByRole('button',{name:'应用设定',exact:true}).click();
  await expect(page.locator('[data-air-provenance]')).toContainText('过期');
  await duration(60);
  const changed=await run();
  expect(changed.request.project.controllers[0].setpoint).toBeCloseTo(298.15,8);
  expect(changed.frame.variables['controller.room-temperature.setpoint']).toBeCloseTo(298.15,8);
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('#toast')).toContainText('风侧项目已保存');
  const state=await page.evaluate(async () => (await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
  const owner=state.projects.find(p=>p.id===state.activeProject);
  expect(owner.controllers[0].setpoint).toBeCloseTo(298.15,8);
  const prototype={format:'fluidnet-studio-prototype',schema:1,activeProject:owner.id,projects:[owner],modules:Object.values(owner.moduleSnapshots)};
  const normalized=await api('/prototype/normalize',prototype);
  expect(normalized.controllers).toEqual(changed.request.project.controllers);
  await page.reload();
  await expect(page.getByRole('button',{name:'运行计算',exact:true})).toBeEnabled({timeout:20000});
  const repeated=await run();
  expect(repeated.frame.variables['Room.state.temperature_k']).toBeCloseTo(changed.frame.variables['Room.state.temperature_k'],7);
  await page.getByLabel('风侧结果来源',{exact:true}).selectOption(first.id);
  await page.getByRole('button',{name:'反馈控制',exact:true}).click();
  await expect(target).toHaveText('26');
  await expect(page.getByRole('button',{name:'调整设定',exact:true})).toBeDisabled();
  // Both staged examples preserve their real Python script when created through the UI.
  const staged=[];
  for(const name of ['room-control-load-step','room-control-setpoint-step']){
    await create(name);await duration(630);
    const record=await run();staged.push(record.id);
    expect(record.frame.time_s).toBe(630);
    expect(record.request.project.control_scripts).toHaveLength(1);
    expect(record.request.project.control_scripts[0].enabled).toBe(true);
    expect(record.frame.variables['script.room-scenario.state.applied']).toBe(true);
    const key=name==='room-control-load-step'?'Room.sensible_load_w':'controller.room-temperature.setpoint';
    expect(record.frame.variables[key]).toBeCloseTo(name==='room-control-load-step'?8000:298.15,8);
  }
  // The shared batch catalog offers canonical PID values and their temperature display unit.
  const choices=await api('/air/variables/preview',normalized);
  expect(choices.variables.find(v=>v.key==='controller.room-temperature.setpoint').unit.display_unit).toBe('°C');
  expect(choices.variables.some(v=>v.key==='controller.room-temperature.output')).toBe(true);
  expect(errors).toEqual([]);
  mkdirSync('artifacts',{recursive:true});
  writeFileSync('artifacts/room-control-browser-validation.json',JSON.stringify({first:first.id,changed:changed.id,repeated:repeated.id,
    staged,finalTemperatureC:first.frame.variables['Room.state.temperature_k']-273.15,energyKwh:first.frame.variables['Chiller.state.electric_energy_j']/3600000,errors},null,2));
}catch(error){
  console.error(error,errors,await page?.locator('#toast').textContent().catch(()=>''),launched?.log());
  process.exitCode=1;await captureFhd(page,'artifacts/room-control-failure.png').catch(()=>{});
}finally{await browser.close();await launched?.stop();}
