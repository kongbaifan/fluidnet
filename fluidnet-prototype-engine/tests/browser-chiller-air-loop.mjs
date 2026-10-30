import {chromium,expect} from '@playwright/test';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-chiller-'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const errors=[];
let launched,page;
async function api(path,body) {
  const response=await page.request.fetch(launched.base+'/api/v1'+path,{method:body===undefined?'GET':'POST',data:body});
  expect(response.ok(),await response.text()).toBe(true);return response.json();
}
async function run() {
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);
  const id=(await response.json()).run_id;
  console.log('submitted', id);
  let record;
  await expect(async()=>{
    record=await api('/runs/'+id);
    expect(record.status).toBe('completed');
  }).toPass({timeout:90000,intervals:[300,1000]});
  await expect(page.locator('[data-air-provenance]')).toContainText(id.slice(0,12),{timeout:15000});
  return record;
}
try {
  launched=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  page=await (await browser.newContext({...FHD_CONTEXT,acceptDownloads:true})).newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(launched.base+'/#air');
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled({timeout:15000});
  await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
  await page.getByLabel('风侧示例',{exact:true}).selectOption('chiller-air-loop');
  await page.getByRole('button',{name:'创建项目',exact:true}).click();
  await expect(page.getByLabel('风侧当前项目')).toContainText('冷水机组与房间风水联算');
  await page.getByRole('button',{name:'湿空气设置',exact:true}).click();
  await page.getByLabel('动态运行时长 / s',{exact:true}).fill('4');
  await page.getByRole('button',{name:'应用设置',exact:true}).click();
  const state=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
  expect(state.projects.find(p=>p.id===state.activeProject).solverOptions.moist_air_options.max_iterations).toBe(400);
  await page.getByRole('button',{name:'相对湿度换算',exact:true}).click();
  await expect(page.getByRole('dialog').locator('select[name="instance"] option')).toHaveCount(2);
  await expect(page.getByRole('dialog')).not.toContainText('ChilledRef');
  await page.getByRole('button',{name:'取消',exact:true}).click();
  const first=await run();
  console.log('first completed');
  expect(first.request.project.circuit_fluids).toHaveLength(2);
  expect(first.air_metadata.continuity_basis).toBe('mixed');
  expect(first.frame.variables['Chiller.cooling_power_w']).toBeGreaterThan(10000);
  expect(first.frame.variables['Chiller.state.electric_energy_j']).toBeGreaterThan(0);
  await expect(page.getByRole('heading',{name:'空气回路',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'液体回路',exact:true})).toBeVisible();
  await expect(page.locator('[data-air-value="Chiller.out0.temperature_k"]')).not.toHaveText('—');
  expect(await page.locator('[data-air-value="Chiller.out0.humidity_ratio_kg_kg"]').count()).toBe(0);
  await captureFhd(page,'artifacts/chiller-air-distribution-1080p.png');
  await page.getByRole('button',{name:'湿空气状态图',exact:true}).click();
  await expect(page.locator('.air-point-list')).not.toContainText('Chiller.');
  await page.getByRole('button',{name:'设备与水耗',exact:true}).click();
  await expect(page.locator('.air-device-grid')).toContainText('累计耗电量');
  await expect(page.locator('.air-device-grid')).toContainText('水侧得热');
  await captureFhd(page,'artifacts/chiller-air-devices-1080p.png');
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'HTML 报告',exact:true}).click();
  const reportPath=join(directory,'report.html');await (await download).saveAs(reportPath);
  expect(readFileSync(reportPath,'utf8')).toContain('累计耗电量');
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('#toast')).toContainText('风侧项目已保存');
  const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
  const owner=saved.projects.find(p=>p.id===saved.activeProject);
  expect(owner.circuitFluids).toHaveLength(2);
  const exported={format:'fluidnet-studio-prototype',schema:1,activeProject:owner.id,projects:[owner],modules:Object.values(owner.moduleSnapshots)};
  const normalized=await api('/prototype/normalize',exported);
  expect(normalized.circuit_fluids).toEqual(first.request.project.circuit_fluids);
  mkdirSync('artifacts',{recursive:true});
  writeFileSync('artifacts/chiller-air-loop.prototype.json',JSON.stringify(exported,null,2));
  writeFileSync('artifacts/chiller-air-loop.project.json',JSON.stringify(normalized,null,2));
  await page.reload();
  await expect(page.getByRole('button',{name:'运行计算',exact:true})).toBeEnabled({timeout:15000});
  const second=await run();
  expect(second.frame.variables['Chiller.state.electric_energy_j']).toBeCloseTo(first.frame.variables['Chiller.state.electric_energy_j'],5);
  // Change a physical water setpoint through the regular device editor, then rerun.
  await page.getByRole('button',{name:'编辑拓扑',exact:true}).click();
  await page.locator('[data-node="Chiller"]').first().dblclick();
  const setpoint=page.getByRole('spinbutton',{name:/Chiller.*冷冻水出水设定.*草稿/}).first();
  await setpoint.fill('9');await setpoint.blur();
  await page.locator('[data-action="apply-instance"][data-id="Chiller"]').click();
  if(await page.getByRole('dialog').count())await page.getByRole('dialog').locator('button[type="submit"]').click();
  await page.getByRole('button',{name:'关闭设备窗口',exact:true}).click();
  await page.locator('.rail-link[data-route="air"]').click();
  await expect(page.locator('[data-air-provenance]')).toContainText('过期');
  const changed=await run();
  expect(changed.frame.variables['Chiller.out0.temperature_k']).toBeCloseTo(282.15,4);
  expect(changed.frame.variables['Coil.water_heat_w']).toBeLessThan(second.frame.variables['Coil.water_heat_w']);
  // Scan the actual chiller setpoint in Celsius through the shared batch workflow.
  await page.getByRole('button',{name:'批量方案',exact:true}).click();
  await page.getByRole('button',{name:'保存项目并准备工况',exact:true}).click();
  await page.getByLabel('扫描设备',{exact:true}).selectOption('Chiller');
  await page.getByLabel('扫描参数',{exact:true}).selectOption('chilled_water_setpoint_k');
  await page.getByLabel('批次计算方式',{exact:true}).selectOption('dynamic');
  await page.getByLabel('仿真时长 · s',{exact:true}).fill('2');
  await page.getByLabel('输出步长 · s',{exact:true}).fill('2');
  await page.getByLabel('取值方式',{exact:true}).selectOption('range');
  await page.getByLabel('起始值',{exact:true}).fill('7');
  await page.getByLabel('结束值',{exact:true}).fill('9');
  await page.getByLabel('工况数量',{exact:true}).fill('2');
  for(const key of await page.locator('[data-batch-variable]:checked').evaluateAll(items=>items.map(i=>i.dataset.batchVariable)))
    await page.locator(`[data-batch-variable="${key}"]`).uncheck();
  for(const key of ['Coil.water_heat_w','Chiller.state.electric_energy_j','Chiller.out0.temperature_k'])
    await page.locator(`[data-batch-variable="${key}"]`).check();
  await page.getByRole('button',{name:'预览工况',exact:true}).click();
  await expect(page.locator('#batch-preview tbody tr')).toHaveCount(2);
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/batches')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存并运行批次',exact:true}).click();
  const batchResponse=await posted;expect(batchResponse.ok(),await batchResponse.text()).toBe(true);
  const batchId=(await batchResponse.json()).id;
  let batch;
  await expect(async()=>{batch=await api('/batches/'+batchId);expect(batch.status).toBe('completed');})
    .toPass({timeout:90000,intervals:[300,1000]});
  expect(batch.items[0].values['Chiller.out0.temperature_k']).toBeCloseTo(280.15,4);
  expect(batch.items[1].values['Chiller.out0.temperature_k']).toBeCloseTo(282.15,4);
  expect(batch.items[0].values['Coil.water_heat_w']).toBeGreaterThan(batch.items[1].values['Coil.water_heat_w']);
  expect(batch.items.every(item=>item.values['Chiller.state.electric_energy_j']>0)).toBe(true);
  await expect(page.locator('[data-batch-item][data-status="completed"]')).toHaveCount(2);
  await captureFhd(page,'artifacts/chiller-air-batches-1080p.png');
  expect(errors).toEqual([]);
  writeFileSync('artifacts/chiller-air-browser-validation.json',JSON.stringify({firstRun:first.id,changedRun:changed.id,
    circuits:normalized.circuit_fluids,cooling:first.frame.variables['Chiller.cooling_power_w'],
    waterCoil:first.frame.variables['Coil.water_heat_w'],batchId,batchItems:2,errors},null,2));
  console.log(JSON.stringify({run:first.id,changed:changed.id,errors}));
} catch(error) {
  console.error(error,errors,await page?.locator('#toast').textContent().catch(()=>''),launched?.log());
  process.exitCode=1;
  await captureFhd(page,'artifacts/chiller-air-failure.png').catch(()=>{});
} finally {
  await browser.close();await launched?.stop();
}
