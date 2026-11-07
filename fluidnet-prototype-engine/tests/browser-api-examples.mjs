import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
try {
  await page.goto(server.base+'/#air');
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled({timeout:15000});
  await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
  await page.getByLabel('风侧示例',{exact:true}).selectOption('hvac-water-balance');
  await page.getByRole('button',{name:'创建项目',exact:true}).click();
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  const rid=(await(await posted).json()).run_id;
  await expect.poll(async()=>{const record=await(await page.request.get(server.base+'/api/v1/runs/'+rid)).json();return record.status;},{timeout:30000}).toBe('completed');
  await page.locator('.rail-link[data-route="connections"]').click();
  await page.locator('[data-action="connection-tab"][data-value="api"]').click();
  const target=page.getByLabel('接口变量',{exact:true});
  await expect(target).toBeEnabled();
  await target.selectOption('Balance1.mass_flow_kg_s');
  await page.locator('[data-action="api-preview"]').click();
  await expect(page.locator('#api-response')).toContainText('"status": 200');
  await expect(page.locator('#api-response')).toContainText('Balance1.mass_flow_kg_s');
  await expect(page.locator('#api-request')).not.toContainText('V1.');
  await page.locator('[data-action="api-example"][data-value="stream"]').click();
  await target.selectOption('Balance2.mass_flow_kg_s');
  await expect(page.locator('#api-request')).toContainText('/stream?keys=Balance2.mass_flow_kg_s');
  await page.locator('[data-action="api-example"][data-value="set"]').click();
  await target.selectOption('Balance1.param.opening_ratio');
  await page.getByLabel('接口写入值',{exact:true}).fill('0.65');
  await page.getByLabel('接口写入值',{exact:true}).blur();
  await expect(page.locator('#api-request')).toContainText('"Balance1.param.opening_ratio":0.65');
  await expect(page.locator('[data-action="api-preview"]')).toBeDisabled();
  await captureFhd(page,'artifacts/api-examples-custom-project.png');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({project:'hvac-water-balance',runId:rid,errors}));
} catch(error) { await captureFhd(page,'artifacts/api-examples-failure.png').catch(()=>{});throw error; }
finally {await browser.close();await server.close();}
