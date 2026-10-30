import {chromium,expect} from '@playwright/test';
import {mkdtempSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-air-batch-'));
const browser=await chromium.launch({channel:'msedge',headless:true});
let launched,page;
const errors=[];
try {
  launched=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  page=await browser.newPage({...FHD_CONTEXT});page.on('pageerror',error=>errors.push(error.message));
  await page.goto(launched.base+'/#air');
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled({timeout:15000});
  await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
  await page.getByRole('button',{name:'创建项目',exact:true}).click();
  await expect(page.locator('[data-air-project] option:checked')).toHaveText('湿盘管除湿');
  await page.getByRole('button',{name:'批量方案',exact:true}).click();
  await page.getByRole('button',{name:'保存项目并准备工况',exact:true}).click();
  await page.getByLabel('扫描设备',{exact:true}).selectOption('Coil');
  await page.getByLabel('扫描参数',{exact:true}).selectOption('bypass_factor');
  await page.getByLabel('批次计算方式',{exact:true}).selectOption('steady');
  await page.getByLabel('取值方式',{exact:true}).selectOption('range');
  await page.getByLabel('起始值',{exact:true}).fill('0.15');
  await page.getByLabel('结束值',{exact:true}).fill('0.45');
  await page.getByLabel('工况数量',{exact:true}).fill('3');
  for(const key of await page.locator('[data-batch-variable]:checked').evaluateAll(items=>items.map(i=>i.dataset.batchVariable)))
    await page.locator(`[data-batch-variable="${key}"]`).uncheck();
  await page.locator('[data-batch-variable="Coil.condensate_kg_s"]').check();
  await page.locator('[data-batch-variable="Coil.cooling_load_w"]').check();
  await page.locator('[data-batch-variable="Coil.out0.temperature_k"]').check();
  await page.getByRole('button',{name:'预览工况',exact:true}).click();
  await expect(page.locator('#batch-preview tbody tr')).toHaveCount(3);
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/batches')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存并运行批次',exact:true}).click();
  const created=await posted;expect(created.ok(),await created.text()).toBe(true);const id=(await created.json()).id;
  let detail;
  await expect(async()=>{const response=await page.request.get(launched.base+'/api/v1/batches/'+id);detail=await response.json();if(detail.status==='failed'||detail.status==='completed_with_errors')throw Error(JSON.stringify(detail));expect(detail.status).toBe('completed');}).toPass({timeout:90000,intervals:[200,500]});
  expect(detail.items[0].values['Coil.condensate_kg_s']).toBeGreaterThan(detail.items[2].values['Coil.condensate_kg_s']);
  expect(detail.items[0].values['Coil.out0.temperature_k']).toBeLessThan(detail.items[2].values['Coil.out0.temperature_k']);
  await expect(page.locator('[data-batch-item][data-status="completed"]')).toHaveCount(3);
  await captureFhd(page,'artifacts/air-batches.png');
  await page.reload();
  await expect(page.locator('[data-batch-item][data-status="completed"]')).toHaveCount(3,{timeout:15000});
  expect(errors).toEqual([]);console.log(JSON.stringify({id,items:3,errors}));
} catch(error) {
  console.error(error,errors,await page?.locator('#batch-error').textContent().catch(()=>''),launched?.log());
  process.exitCode=1;await captureFhd(page,'artifacts/air-batches-failure.png').catch(()=>{});
} finally {
  await browser.close();await launched?.stop();
}
