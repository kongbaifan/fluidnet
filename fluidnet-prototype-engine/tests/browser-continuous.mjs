import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// Continuous run: the solver settings switch sends duration_s=null, the run keeps advancing
// until 停止, and the curves page can switch to the server's decimated whole-run overview.
const store = mkdtempSync(join(tmpdir(), 'fluidnet-continuous-'));
let server, port, base, serverLog = '', launched;
async function startServer() {
  launched = await launchEngine({ args: [], env: { FLUIDNET_MODULE_STORE: store } });
  ({ server, port, base } = launched);
  serverLog = launched.log();
}
async function stopServer() { if (launched) await launched.stop(); }
const record = async id => (await page.request.get(base + '/api/v1/runs/' + id)).json();

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = []; page.on('pageerror', e => errors.push(e.message));

try {
  await startServer();
  await page.goto(base);
  await page.locator('[data-action="start-modeling"]').first().click();
  await page.locator('.rail-link[data-route="settings"]').click();
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-continuous]').check();
  await expect(page.locator('[data-solver-field="duration"]')).toBeDisabled();
  await page.locator('.rail-link[data-route="workbench"]').click();

  const created = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/runs') && r.method() === 'POST');
  const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/runs') && r.request().method() === 'POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  expect((await created).postDataJSON().duration_s).toBeNull();
  const runId = (await (await response).json()).run_id;
  await expect.poll(async () => (await record(runId)).total_rows, { timeout: 20000 }).toBeGreaterThan(20);
  expect((await record(runId)).status).toBe('running');

  await page.locator('.rail-link[data-route="curves"]').click();
  const overview = page.waitForResponse(r => new URL(r.url()).pathname.endsWith(`/runs/${runId}/overview`));
  await page.locator('[data-chart-range]').selectOption('all');
  const data = await (await overview).json();
  expect(data.rows.length).toBeGreaterThan(10);
  await expect(page.locator('#main-chart svg')).toBeVisible();

  await page.locator('[data-action="run-project"][data-command="stop"]').first().click();
  await expect.poll(async () => (await record(runId)).status, { timeout: 15000 }).toBe('cancelled');
  const final = await record(runId);
  expect(errors).toEqual([]);
  console.log(JSON.stringify({ runId, status: final.status, rows: final.total_rows, timeS: final.frame.time_s, overviewRows: data.rows.length, errors }));
} catch (error) {
  mkdirSync('artifacts', { recursive: true }); await page.screenshot({ path: 'artifacts/continuous-failure.png', fullPage: true });
  console.error(serverLog.slice(-1000), errors); throw error;
} finally { await browser.close(); await stopServer(); }
