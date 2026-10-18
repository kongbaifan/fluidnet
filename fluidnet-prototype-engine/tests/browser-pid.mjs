import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// End-to-end run control: stopping a *background* dynamic run must reach the
// backend, the record must end `cancelled`, and the page must stop replaying.
// Dedicated store/server so acceptance never writes into the user's library.
const store = mkdtempSync(join(tmpdir(), 'fluidnet-runcontrol-'));
let server, port, base, serverLog = '', launched;
async function startServer() {
  launched = await launchEngine({ args: [], env: { FLUIDNET_MODULE_STORE: store } });
  ({ server, port, base } = launched);
  serverLog = launched.log();
}
async function stopServer() { if (launched) await launched.stop(); }

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = []; page.on('pageerror', e => errors.push(e.message));
// studio.js is an IIFE, so the page's live state is not reachable from evaluate();
// `保存` is the app's own way of flushing it to localStorage.
const projectState = async () => {
  await page.locator('[data-action="save"]').first().click();
  return page.evaluate(() => {
    const s = JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1') || '{}');
    const p = (s.projects || []).find(project => project.id === s.activeProject);
    return p ? { status: p.run.status, runId: p.run.runId ?? null, rows: p.run.history.length, time: p.run.time,
      events: (p.run.events || []).map(event => event.text) } : null;
  });
};
const createRun = () => Promise.all([
  page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/runs') && r.request().method() === 'POST', { timeout: 30000 }),
  page.locator('[data-action="run-project"][data-command="run"]').first().click(),
]).then(([response]) => response.json());

try {
  await startServer();
  await page.goto(base+'/#controls');
  await expect(page.locator('[data-action="pid-example"][data-kind="temperature"]')).toBeVisible();
  await page.locator('[data-action="pid-example"][data-kind="temperature"]').click();
  // 示例载入是异步的：慢速 CI 上立刻点单步可能落在按钮禁用期，请求不会发出。
  const stepButton=page.locator('[data-action="run-project"][data-command="step"]').first();
  await expect(stepButton).toBeEnabled({timeout:30000});
  const response=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/runs') && r.request().method()==='POST',{timeout:60000});
  await stepButton.click();
  const runId=(await (await response).json()).run_id;
  await expect.poll(async()=>{const r=await (await page.request.get(base+'/api/v1/runs/'+runId)).json();if(r.status==='failed')throw Error(JSON.stringify(r.frame));return r.status==='paused' && r.frame.time_s===1;},{timeout:15000}).toBe(true);
  await page.locator('.rail-link[data-route="controls"]').click();
  const card=page.locator('[data-pid-card="temperature"]');
  await expect(card).toBeVisible();
  await card.locator('[data-pid-field="setpoint"]').fill('304.15');
  await card.locator('[data-pid-field="setpoint"]').blur();
  await expect.poll(async()=>{const r=await (await page.request.get(base+'/api/v1/runs/'+runId+'/events')).json();return r.events.some(e=>e.command_status==='applied' && e.command_id);},{timeout:15000}).toBe(true);
  await card.locator('[data-pid-field="mode"]').selectOption('manual');
  await card.locator('[data-pid-field="manual_output"]').fill('1500');
  await card.locator('[data-pid-field="manual_output"]').blur();
  await page.locator('[data-action="save"]').first().click();
  await page.reload();
  await expect(page.locator('[data-pid-card="temperature"]')).toBeVisible();
  await page.screenshot({path:'artifacts/pid-controls.png',fullPage:true});
  await page.locator('.rail-link[data-route="workbench"]').click();
  await expect(stepButton).toBeEnabled({timeout:30000});
  await stepButton.click();
  await expect.poll(async()=>{const r=await (await page.request.get(base+'/api/v1/runs/'+runId)).json();return r.frame.time_s;},{timeout:15000}).toBe(2);
  const record=await (await page.request.get(base+'/api/v1/runs/'+runId)).json();
  expect(record.frame.variables['controller.temperature.setpoint']).toBe(304.15);
  expect(record.frame.variables['controller.temperature.output']).toBe(1500);
  expect(errors).toEqual([]);
  console.log(JSON.stringify({pid:'temperature',time:record.frame.time_s,output:record.frame.variables['controller.temperature.output'],errors}));
} catch(error) {
  mkdirSync('artifacts',{recursive:true});await page.screenshot({path:'artifacts/pid-failure.png',fullPage:true});
  console.error(serverLog.slice(-1000),errors);throw error;
} finally {await browser.close();await stopServer();}
