import {chromium,expect} from '@playwright/test';
import {mkdirSync,mkdtempSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

// 暖通基础设备验收：模块目录、测点、PID 反馈、曲线、联锁模板与保存重载。
const directory=mkdtempSync(join(tmpdir(),'fluidnet-hvac-ui-'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const errors=[];
let launched,page;
async function api(path) {
  const response=await page.request.get(launched.base+'/api/v1'+path);
  expect(response.ok(),await response.text()).toBe(true);return response.json();
}
async function runProject() {
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);const id=(await response.json()).run_id;
  let record;
  await expect(async()=>{record=await api('/runs/'+id);if(record.status==='failed')throw Error(JSON.stringify(record.frame));
    expect(record.status).toBe('completed');}).toPass({timeout:90000,intervals:[200,500,1000]});
  return record;
}
try {
  launched=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  const context=await browser.newContext({...FHD_CONTEXT,acceptDownloads:true});
  page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  // 1. 新基础设备由 modules/ 种子包自动进入模块目录，供画布拖入。
  const catalog=(await api('/modules')).modules.map(module=>module.id);
  for(const id of ['water_tee','water_header_4','water_collector_4','water_balancing_valve','water_shutoff_valve',
    'water_strainer','water_three_way_valve','hvac_water_pump','hvac_check_valve','pipe_reducer'])expect(catalog).toContain(id);
  await page.goto(launched.base+'/#air');
  // 2. 风侧页提供七个暖通基础示例，创建两支路水力平衡案例。
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled({timeout:15000});
  await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
  await page.getByLabel('风侧示例',{exact:true}).selectOption('hvac-water-balance');
  await page.getByRole('button',{name:'创建项目',exact:true}).click();
  await expect(page.getByLabel('风侧当前项目')).toContainText('两支路水力平衡');
  const record=await runProject();
  expect(record.frame.variables['measurement.branch1-flow']).toBeGreaterThan(0);
  expect(record.frame.variables['measurement.supply-dp']).toBeGreaterThan(0);
  // 3. 控制页测点面板读取同一运行帧，未绑定有效输入的测点显示占位符而不是零。
  await page.locator('.rail-link[data-route="controls"]').click();
  await expect(page.locator('[data-meter-card="branch1-flow"]')).toContainText('m³/h');
  await expect(page.locator('[data-meter-value="branch1-flow"]')).not.toHaveText('—',{timeout:15000});
  // 4. 界面新增两点差值测点：两台平衡阀的进出口压力。
  await page.locator('[data-action="add-meter"][data-kind="difference"]').click();
  const dialog=page.getByRole('dialog');
  await dialog.locator('[name="label"]').fill('平衡阀压差');
  await dialog.locator('[name="source0"]').selectOption('Balance1.in0.pressure_pa');
  await dialog.locator('[name="source1"]').selectOption('Balance1.out0.pressure_pa');
  await dialog.locator('button[type="submit"]').click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('[data-meter-card]')).toHaveCount(4);
  await expect(page.locator('[data-meter-card]:has-text("平衡阀压差")')).toHaveCount(1);
  // 5. 新测点可直接作为 PID 反馈变量，并加入曲线。
  await page.locator('[data-action="add-pid"]').click();
  await expect(page.locator('[data-pid-field="measurement"] option:has-text("平衡阀压差")')).toHaveCount(1);
  await page.locator('[data-action="meter-curve"][data-id="branch1-flow"]').click();
  await expect(page.locator('.chart-variable-list')).toContainText('支路 1 体积流量');
  await captureFhd(page,'artifacts/hvac-meter-curves.png');
  // 6. 控制页可新建脚本并载入机房联锁控制模板（B13）。
  await page.locator('.rail-link[data-route="controls"]').click();
  await page.locator('[data-action="add-control-program"]').click();
  const programDialog=page.getByRole('dialog');
  await programDialog.locator('[name="id"]').fill('plant-interlock');
  await programDialog.locator('button[type="submit"]').click();
  await expect(programDialog).toHaveCount(0);
  await page.locator('[data-action="control-template"][data-kind="interlock"]').click();
  const templateDialog=page.getByRole('dialog');
  await expect(templateDialog).toContainText('机房联锁');
  await templateDialog.locator('button[type="submit"]').click();
  await expect(templateDialog).toHaveCount(0);
  await expect(page.locator('textarea[data-control-code]')).toContainText('MIN_DP_PA');
  await expect(page.locator('textarea[data-control-inputs]')).toContainText('Discharge.common.pressure_pa');
  await expect(page.locator('textarea[data-control-outputs]')).toContainText('Pump1.param.running');
  // 7. 保存工作区后重载，测点随项目持久化。
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await posted).ok()).toBe(true);
  const saved=await page.evaluate(async () => (await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
  const owner=saved.projects.find(project=>project.id===saved.activeProject);
  expect(owner.measurements.map(meter=>meter.label)).toContain('平衡阀压差');
  const reloaded=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='GET');
  await page.reload();
  expect((await reloaded).ok()).toBe(true);
  await page.locator('.rail-link[data-route="controls"]').click();
  await expect(page.locator('[data-meter-card]:has-text("平衡阀压差")')).toHaveCount(1);
  mkdirSync('artifacts',{recursive:true});
  await captureFhd(page,'artifacts/hvac-meters.png');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({modules:catalog.length,meters:owner.measurements.length,errors}));
} catch (error) {
  console.error(error,errors,launched?.log());
  process.exitCode=1;
  mkdirSync('artifacts',{recursive:true});
  await captureFhd(page,'artifacts/hvac-equipment-failure.png').catch(()=>{});
} finally {
  await browser.close();
  await launched?.stop();
}
