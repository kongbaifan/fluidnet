import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// Two fluids in one project: the heat-loop example gets a glycol secondary circuit; the check
// reports two circuits, the canvas colours them, and the computed cold side carries glycol density.
const store = mkdtempSync(join(tmpdir(), 'fluidnet-multifluid-'));
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

try {
  await startServer();
  await page.goto(base);
  await page.locator('[data-action="open-project"][data-id="heat-loop"]').first().click();
  await page.locator('.rail-link[data-route="settings"]').click();
  await page.locator('[data-action="settings-tab"][data-value="medium"]').click();
  await page.locator('[data-action="add-circuit-fluid"]').click();
  await page.locator('[data-circuit-field="anchor"][data-index="0"]').selectOption('B3:out0');
  await page.locator('[data-circuit-field="medium"][data-index="0"]').selectOption('meg30');
  await page.locator('.rail-link[data-route="workbench"]').click();

  const checked = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/projects/validate'));
  await page.locator('[data-action="validate"]').first().click();
  const validation = await (await checked).json();
  expect(validation.valid).toBe(true);
  expect(validation.circuits.map(c => c.fluid.fluid).sort()).toEqual(['INCOMP::MEG[0.3]', 'Water']);
  await expect(page.locator('.canvas-caption')).toContainText('多工质 · 2 个回路');
  const strokes = await page.locator('#network .net-line').evaluateAll(lines => [...new Set(lines.map(l => l.style.stroke))]);
  expect(strokes.length).toBe(2);

  // The check opens its result dialog; close it before using the run bar.
  await page.getByRole('dialog').getByRole('button', { name: '关闭' }).last().click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const [response] = await Promise.all([
    page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/runs') && r.request().method() === 'POST', { timeout: 20000 }),
    page.locator('[data-action="run-project"][data-command="step"]').first().click(),
  ]);
  const runId = (await response.json()).run_id;
  let frame;
  await expect.poll(async () => { const r = await (await page.request.get(base + '/api/v1/runs/' + runId)).json();
    if (r.status === 'failed') throw Error(JSON.stringify(r.frame.diagnostics)); frame = r.frame; return r.status === 'paused' && r.frame.time_s > 0; },
    { timeout: 20000 }).toBe(true);
  expect(frame.variables['HX1.in1.density_kg_m3']).toBeGreaterThan(1020);
  expect(frame.variables['HX1.in0.density_kg_m3']).toBeLessThan(1000);
  await page.locator('[data-action="run-project"][data-command="stop"]').first().click();
  mkdirSync('artifacts', { recursive: true }); await page.screenshot({ path: 'artifacts/multifluid.png', fullPage: true });
  expect(errors).toEqual([]);
  console.log(JSON.stringify({ circuits: validation.circuits.map(c => [c.fluid.fluid, c.ports.length]),
    cold: frame.variables['HX1.in1.density_kg_m3'], hot: frame.variables['HX1.in0.density_kg_m3'], errors }));
} catch (error) {
  mkdirSync('artifacts', { recursive: true }); await page.screenshot({ path: 'artifacts/multifluid-failure.png', fullPage: true });
  console.error(serverLog.slice(-1000), errors); throw error;
} finally { await browser.close(); await stopServer(); }
