import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';

// Continuous run: the solver settings switch sends duration_s=null, the run keeps advancing
// until 停止, and the curves page can switch to the server's decimated whole-run overview.
const store = mkdtempSync(join(tmpdir(), 'fluidnet-continuous-'));
const socket = createServer(); socket.listen(0, '127.0.0.1'); await once(socket, 'listening');
const port = socket.address().port; await new Promise(resolve => socket.close(resolve));
const base = `http://127.0.0.1:${port}`;
let server, serverLog = '';
async function startServer() {
  server = spawn('python', ['-m', 'fn_engine', 'serve', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: resolve('.'), windowsHide: true, env: { ...process.env, FLUIDNET_MODULE_STORE: store }, stdio: ['ignore', 'ignore', 'pipe'] });
  server.stderr.on('data', chunk => serverLog += chunk);
  await expect.poll(async () => { try { return (await fetch(base + '/api/v1/health')).ok; } catch { return false; } }, { timeout: 15000 }).toBe(true);
}
async function stopServer() { if (server && server.exitCode === null) { const exited = once(server, 'exit'); server.kill(); await exited; } }
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
