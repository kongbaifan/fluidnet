import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';

// End-to-end run control: stopping a *background* dynamic run must reach the
// backend, the record must end `cancelled`, and the page must stop replaying.
// Dedicated store/server so acceptance never writes into the user's library.
const store = mkdtempSync(join(tmpdir(), 'fluidnet-runcontrol-'));
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
  await page.goto(base);
  await page.locator('[data-action="start-modeling"]').click();
  // Slow the run down on purpose: 30 s at 0.05 s steps is 601 backend frames,
  // so a stop can land while the timeline is genuinely still running.
  await page.locator('.rail-link[data-route="settings"]').click();
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('input[data-solver-field="duration"]').fill('30');
  await page.locator('input[data-solver-field="dt"]').fill('0.05');
  await page.locator('[data-action="save"]').first().click();
  await page.locator('.rail-link[data-route="workbench"]').click();

  const created = await createRun();
  expect(created.status, JSON.stringify(created)).toBe('queued');
  const runId = created.run_id;
  // The run really is the long one the settings page asked for; otherwise a
  // stop could only ever race an already-finished timeline.
  const record = await (await page.request.get(`${base}/api/v1/runs/${runId}`)).json();
  expect(record.request.duration_s).toBe(30);

  // The frontend must have published the backend id before polling, otherwise
  // stop has nothing real to cancel.
  await expect.poll(async () => (await projectState()).runId, { timeout: 5000 }).toBe(runId);

  await page.locator('[data-action="run-project"][data-command="stop"]').first().click();

  await expect.poll(async () => (await (await page.request.get(`${base}/api/v1/runs/${runId}`)).json()).status,
    { timeout: 20000 }).toBe('cancelled');
  const final = await (await page.request.get(`${base}/api/v1/runs/${runId}`)).json();
  const history = await (await page.request.get(`${base}/api/v1/runs/${runId}/history`)).json();
  // Cancelled runs keep the frames computed before the stop was observed.
  expect(history.total_rows).toBeGreaterThan(0);
  expect(final.frame.time_s).toBeLessThan(30);

  await expect.poll(async () => (await projectState()).status, { timeout: 5000 }).toBe('stopped');
  await expect(page.locator('[data-result-status]').first()).not.toContainText('t = 30.0 s');
  // The in-flight poll observes the cancelled record and releases the backend id;
  // until it does, a second stop would target a run that no longer exists.
  await expect.poll(async () => (await projectState()).runId, { timeout: 10000 }).toBeNull();
  const afterStop = await projectState();
  // The stop handler only claims this when the backend actually answered
  // `cancelled`, so the wording is the page's own evidence that the cancel landed.
  expect(afterStop.events.join('\n')).toContain('已停止后端运行');
  const rowsAtStop = afterStop.rows;
  await page.waitForTimeout(800);   // replay must not creep forward after the stop
  const later = await projectState();
  expect(later.rows).toBe(rowsAtStop);
  expect(later.time).toBe(afterStop.time);

  mkdirSync('artifacts', { recursive: true });
  await page.screenshot({ path: 'artifacts/run-control.png', fullPage: true });
  expect(errors).toEqual([]);
  console.log(JSON.stringify({ runId, finalStatus: final.status, timeS: final.frame.time_s, rows: history.total_rows,
    rowsAfterStop: rowsAtStop, timeAfterStop: afterStop.time, events: afterStop.events, errors }, null, 2));
} catch (error) {
  mkdirSync('artifacts', { recursive: true }); await page.screenshot({ path: 'artifacts/run-control-failure.png', fullPage: true });
  console.error('Browser errors:', errors, 'Server:', serverLog.slice(-2500)); throw error;
} finally { await browser.close(); await stopServer(); }