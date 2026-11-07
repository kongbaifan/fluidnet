import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const panel=()=>page.locator('[data-float-id="V1"]');
const opening=()=>panel().locator('input[type="number"][data-instance-param="opening"]');
const metric=()=>panel().locator('[data-device-metric="in0:FLOW"] strong');
async function save(){
  const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await response).ok()).toBe(true);
  return page.evaluate(async () =>{const s=(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));return s.projects.find(p=>p.id===s.activeProject);});
}
try {
  await page.goto(server.base);
  await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="start-modeling"]').first().click();
  await expect(panel().locator('[data-device-result-source]')).toContainText('尚未计算');
  await expect(metric()).toHaveText('—');
  // A completed steady run makes draft/apply staleness observable without live commands.
  await page.locator('.rail-link[data-route="settings"]').click();
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="mode"]').selectOption('steady');
  await page.locator('.rail-link[data-route="workbench"]').click();
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  await expect(panel().locator('[data-device-result-source]')).toContainText('当前计算结果',{timeout:20000});
  const first=await metric().textContent();expect(Number(first)).toBeGreaterThan(0);
  await opening().fill('40');
  await expect(opening()).toBeFocused();
  await expect(metric()).toHaveText(first);
  await expect(panel().locator('[data-device-result-source]')).toContainText('当前计算结果');
  await panel().locator('[data-action="apply-instance"]').click();
  await expect(page.getByRole('dialog')).toContainText('40');
  await page.getByRole('dialog').locator('[data-action="close-dialog"]').first().click();
  await expect(opening()).toHaveValue('40');
  let owner=await save(),node=owner.pages.flatMap(p=>p.nodes).find(n=>n.id==='V1');
  expect(node.params.opening).toBe(80);expect(node.draft.opening).toBe(40);
  await panel().locator('[data-action="apply-instance"]').click();
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(panel().locator('[data-device-result-source]')).toContainText('已过期');
  await expect(metric()).toHaveText(first);
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  await expect(panel().locator('[data-device-result-source]')).toContainText('当前计算结果',{timeout:20000});
  expect(Number(await metric().textContent())).toBeLessThan(Number(first));
  await captureFhd(page,'artifacts/device-panel-overview.png');
  await panel().locator('[data-action="float-tab"][data-value="parameters"]').click();
  await expect(opening()).toHaveValue('40');
  await expect(panel().locator('[data-instance-model]')).toBeVisible();
  await panel().locator('[data-action="float-tab"][data-value="variables"]').click();
  await expect(panel().locator('[data-instance-group] option[value="runtime"]')).toHaveCount(1);
  await panel().locator('[data-action="float-tab"][data-value="connections"]').click();
  await expect(panel()).toContainText('入口');
  owner=await save();
  await page.reload();
  await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-node="V1"]').dblclick();
  await expect(opening()).toHaveValue('40');
  await panel().locator('[data-action="float-tab"][data-value="overview"]').click();
  await expect(panel().locator('[data-device-result-source]')).toContainText('当前计算结果');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({before:Number(first),after:Number(await metric().textContent()),saved:owner.id,errors}));
} catch(error) {
  await captureFhd(page,'artifacts/device-panel-failure.png').catch(()=>{});
  console.error(error,errors);process.exitCode=1;
} finally { await browser.close();await server.close(); }
