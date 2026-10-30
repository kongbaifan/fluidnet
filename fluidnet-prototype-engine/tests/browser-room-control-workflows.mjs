import {chromium,expect} from '@playwright/test';
import {mkdtempSync,mkdirSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-room-workflows-'));
const browser=await chromium.launch({channel:'msedge',headless:true});
let launched,page;
const errors=[];
async function api(path,body){
  const response=await page.request.fetch(launched.base+'/api/v1'+path,{method:body===undefined?'GET':'POST',data:body});
  expect(response.ok(),await response.text()).toBe(true);return response.json();
}
async function importProject(path){
  await page.locator('.rail-link[data-route="projects"]').click();
  await page.locator('[data-action="wf-import"]').click();
  await page.getByLabel('单项目文件').setInputFiles(path);
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('#toast')).toContainText('项目已导入');
  await page.locator('.rail-link[data-route="air"]').click();
}
try{
  launched=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  page=await(await browser.newContext({...FHD_CONTEXT,acceptDownloads:true})).newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(launched.base+'/#air');
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled({timeout:20000});
  await importProject(resolve('examples/room-control/room-temperature-control.project.json'));
  await expect(page.getByRole('button',{name:'反馈控制',exact:true})).toBeVisible();
  // Canonical imports deliberately use the generic 60 s duration, then retain the real controller.
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);
  const rid=(await response.json()).run_id;
  await expect.poll(async()=>{const r=await api('/runs/'+rid);return ['completed','failed'].includes(r.status);},
    {timeout:180000,intervals:[500,1500]}).toBe(true);
  const imported=await api('/runs/'+rid);expect(imported.status,JSON.stringify(imported.frame)).toBe('completed');
  expect(imported.request.project.controllers[0].measurement).toBe('Room.state.temperature_k');
  expect(imported.frame.variables['controller.room-temperature.setpoint']).toBeCloseTo(299.15,8);
  await page.getByRole('button',{name:'批量方案',exact:true}).click();
  await page.getByRole('button',{name:'保存项目并准备工况',exact:true}).click();
  await page.getByLabel('扫描设备',{exact:true}).selectOption('Room');
  await page.getByLabel('扫描参数',{exact:true}).selectOption('sensible_load_w');
  await page.getByLabel('批次计算方式',{exact:true}).selectOption('dynamic');
  await page.getByLabel('仿真时长 · s',{exact:true}).fill('60');
  await page.getByLabel('输出步长 · s',{exact:true}).fill('30');
  await page.getByLabel('取值方式',{exact:true}).selectOption('range');
  await page.getByLabel('起始值',{exact:true}).fill('5');
  await page.getByLabel('结束值',{exact:true}).fill('8');
  await page.getByLabel('工况数量',{exact:true}).fill('2');
  for(const key of await page.locator('[data-batch-variable]:checked').evaluateAll(items=>items.map(i=>i.dataset.batchVariable)))
    await page.locator(`[data-batch-variable="${key}"]`).uncheck();
  const keys=['Room.state.temperature_k','controller.room-temperature.setpoint','controller.room-temperature.output','Chiller.state.electric_energy_j'];
  for(const key of keys)await page.locator(`[data-batch-variable="${key}"]`).check();
  await page.getByRole('button',{name:'预览工况',exact:true}).click();
  await expect(page.locator('#batch-preview tbody tr')).toHaveCount(2);
  const saved=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/batches')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存并运行批次',exact:true}).click();
  const batchResponse=await saved;expect(batchResponse.ok(),await batchResponse.text()).toBe(true);
  const bid=(await batchResponse.json()).id;
  await expect.poll(async()=>{const b=await api('/batches/'+bid);return ['completed','failed'].includes(b.status);},
    {timeout:180000,intervals:[500,1500]}).toBe(true);
  const batch=await api('/batches/'+bid);expect(batch.status,JSON.stringify(batch)).toBe('completed');
  expect(batch.items).toHaveLength(2);
  for(const item of batch.items){
    expect(item.values['controller.room-temperature.setpoint']).toBeCloseTo(299.15,8);
    expect(item.values['controller.room-temperature.output']).toBeGreaterThan(.02);
    expect(item.values['Chiller.state.electric_energy_j']).toBeGreaterThan(0);
    const run=await api('/runs/'+item.run_id);
    expect(run.request.project.controllers).toEqual(imported.request.project.controllers);
  }
  expect(batch.items[1].values['Room.state.temperature_k']).toBeGreaterThan(batch.items[0].values['Room.state.temperature_k']);
  await expect(page.locator('[data-batch-item][data-status="completed"]')).toHaveCount(2);
  await captureFhd(page,'artifacts/room-control-batches-1080p.png');
  // Importing a scripted example also preserves source/hash and explains ownership of the target.
  await importProject(resolve('examples/room-control/room-control-setpoint-step.project.json'));
  await page.getByRole('button',{name:'反馈控制',exact:true}).click();
  await page.getByRole('button',{name:'调整设定',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('初始目标');
  await expect(page.getByRole('dialog')).toContainText('room-scenario');
  await expect(page.getByLabel('目标设定 / °C',{exact:true})).toHaveValue('26');
  await page.getByRole('button',{name:'取消',exact:true}).click();
  expect(errors).toEqual([]);
  mkdirSync('artifacts',{recursive:true});
  writeFileSync('artifacts/room-control-workflows-validation.json',JSON.stringify({importedRun:rid,batch:bid,
    items:batch.items.map(i=>({id:i.id,values:i.values})),errors},null,2));
  console.log(JSON.stringify({importedRun:rid,batch:bid,items:batch.items.length,errors}));
}catch(error){
  console.error(error,errors,await page?.locator('#toast').textContent().catch(()=>''),launched?.log());
  process.exitCode=1;await captureFhd(page,'artifacts/room-control-workflows-failure.png').catch(()=>{});
}finally{await browser.close();await launched?.stop();}
