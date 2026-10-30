import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';
import {chromium, expect} from '@playwright/test';
import {mkdtempSync, readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {launchEngine} from './browser-server.mjs';

const directory = mkdtempSync(join(tmpdir(), 'fluidnet-scenario-batches-'));
const browser = await chromium.launch({channel: 'msedge', headless: true});
const errors = [];
let launched, context, page;
async function start(route = '') {
  launched = await launchEngine({args: ['--data-dir', join(directory, 'data')],
    env: {FLUIDNET_MODULE_STORE: join(directory, 'modules')}});
  context = await browser.newContext({...FHD_CONTEXT, acceptDownloads: true});
  page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(launched.base + '/' + route);
}
async function api(path, body) {
  const response = await page.request.fetch(launched.base + '/api/v1' + path,
    {method: body === undefined ? 'GET' : 'POST', data: body});
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}
async function preview(status = 200) {
  const posted = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/batches/preview')
    && r.request().method() === 'POST');
  posted.catch(() => {});
  await page.getByRole('button', {name: '预览工况', exact: true}).click();
  const response = await posted;
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}
async function createBatch() {
  const posted = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/batches')
    && r.request().method() === 'POST');
  posted.catch(() => {});
  await page.getByRole('button', {name: '保存并运行批次', exact: true}).click();
  const response = await posted;
  expect(response.status(), await response.text()).toBe(201);
  return response.json();
}
async function completed(id) {
  let detail;
  await expect(async () => {
    detail = await api('/batches/' + id);
    if (['failed', 'completed_with_errors', 'cancelled', 'interrupted'].includes(detail.status))
      throw Error(JSON.stringify(detail));
    expect(detail.status).toBe('completed');
  }).toPass({timeout: 60000, intervals: [100, 250, 500]});
  await expect(page.locator('[data-batch-item][data-status="completed"]')).toHaveCount(detail.total);
  return detail;
}
function csvRows(text) {
  const rows = [], row = [];
  let value = '', quoted = false;
  for (const c of text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n')) {
    if (c === '"') {quoted = !quoted; continue;}
    if (!quoted && (c === ',' || c === '\n')) {
      row.push(value); value = '';
      if (c === '\n') {rows.push([...row]); row.length = 0;}
    } else value += c;
  }
  if (row.length || value) rows.push([...row, value]);
  return rows;
}
async function verifyValues(detail) {
  for (const item of detail.items) {
    for (const variable of detail.variables) {
      const cell = page.locator('[data-batch-item="' + item.id + '"] [data-batch-value="' + variable.key + '"]');
      const value = Number((await cell.textContent()).replaceAll(',', ''));
      const expected = item.values[variable.key] / variable.unit.display_scale + variable.unit.display_offset;
      expect(Math.abs(value - expected)).toBeLessThan(Math.max(1, Math.abs(expected)) * 1e-6);
    }
  }
}

try {
  await start();
  await page.locator('[data-action="start-modeling"]').click();
  await page.locator('.canvas-tools [data-route="batches"]').click();
  await expect(page.locator('#batch-page')).toBeVisible();
  await page.getByRole('button', {name: '保存项目并准备工况', exact: true}).click();
  await expect(page.getByLabel('扫描设备', {exact: true})).toBeVisible();
  await page.getByLabel('批次名称', {exact: true}).fill('五档阀门开度');
  await page.getByLabel('扫描设备', {exact: true}).selectOption('V1');
  await page.getByLabel('扫描参数', {exact: true}).selectOption('opening_ratio');
  await expect(page.locator('[data-batch-unit]')).toContainText('%');
  await page.getByLabel('批次计算方式', {exact: true}).selectOption('dynamic');
  await page.getByLabel('仿真时长 · s', {exact: true}).fill('2');
  await page.getByLabel('输出步长 · s', {exact: true}).fill('1');
  await page.getByLabel('结束值', {exact: true}).fill('120');
  await expect(page.getByRole('button', {name: '预览工况', exact: true})).toBeInViewport({ratio: 1});
  await preview(422);
  await expect(page.locator('#batch-error')).toContainText(/超出|范围/);
  await page.getByLabel('结束值', {exact: true}).fill('100');
  const plan = await preview();
  expect(plan.items.map(item => item.parameter_value)).toEqual([20, 40, 60, 80, 100]);
  await expect(page.locator('#batch-preview tbody tr')).toHaveCount(5);
  await expect(page.getByRole('button', {name: '保存并运行批次', exact: true})).toBeInViewport();
  await captureFhd(page, 'artifacts/batches-preview.png');
  const created = await createBatch(), detail = await completed(created.id);
  expect(detail.completed).toBe(5);
  await verifyValues(detail);
  await expect(page.locator('[data-batch-series]')).toHaveCount(3);
  await page.locator('[data-batch-curve-item="item-4"]').check();
  await expect(page.locator('[data-batch-series]')).toHaveCount(4);
  await page.getByLabel('批次比较变量', {exact: true}).selectOption('P1.shaft_power_w');
  await expect(page.locator('[data-batch-series]')).toHaveCount(4);
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', {name: '导出 CSV', exact: true}).click();
  const csvPath = join(directory, 'comparison.csv');
  await (await downloaded).saveAs(csvPath);
  const rows = csvRows(readFileSync(csvPath, 'utf8'));
  expect(rows).toHaveLength(6);
  expect(rows.slice(1).map(row => row[5])).toEqual(['completed', 'completed', 'completed', 'completed', 'completed']);
  expect(Number(rows[1][11])).toBeCloseTo(detail.items[0].values['V1.mass_flow_kg_s'], 9);
  await page.locator('#batch-detail').scrollIntoViewIfNeeded();
  await captureFhd(page, 'artifacts/batches-comparison.png');
  const local = await page.evaluate(() => {
    const state = JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));
    return state.projects.find(p => p.id === state.activeProject).pages[0].nodes.find(n => n.id === 'V1').params.opening;
  });
  expect(local).toBe(80);

  // Add reusable scenarios through the saved-project API, then load them after restart.
  const saved = await api('/projects/' + detail.project_id);
  saved.document.project.scenarios = [
    {id: 'low', name: '低开度', overrides: {V1: {opening: 20}}},
    {id: 'high', name: '高开度', overrides: {V1: {opening: 80}}},
  ];
  await api('/projects/' + detail.project_id, {document: saved.document, expected_revision: saved.revision});

  // The batch page must not need an ordinary run record to display its results.
  for (const item of detail.items) await api('/runs/' + item.run_id + '/delete', {});
  await context.close(); await launched.stop();
  await start('#batches');
  await expect(page.locator('[data-batch-item][data-status="completed"]')).toHaveCount(5, {timeout: 30000});
  expect((await api('/batches/' + created.id)).items).toEqual(detail.items);
  await verifyValues(detail);
  await expect(page.locator('[data-batch-series]')).toHaveCount(3);
  await captureFhd(page, 'artifacts/batches-restart.png');

  await page.getByRole('button', {name: '保存项目并准备工况', exact: true}).click();
  await expect(page.getByLabel('工况来源', {exact: true})).toBeVisible();
  await page.getByLabel('批次名称', {exact: true}).fill('已有工况对照');
  await page.getByLabel('工况来源', {exact: true}).selectOption('scenarios');
  await expect(page.locator('[data-batch-scenario]')).toHaveCount(2);
  await page.getByLabel('批次计算方式', {exact: true}).selectOption('steady');
  const existingPreview = await preview();
  expect(existingPreview.items.map(item => item.source_scenario_id)).toEqual(['low', 'high']);
  await expect(page.locator('#batch-preview')).toContainText('20 %');
  const existing = await createBatch(), existingResult = await completed(existing.id);
  expect(existingResult.items[0].values['V1.mass_flow_kg_s']).toBeLessThan(existingResult.items[1].values['V1.mass_flow_kg_s']);
  await captureFhd(page, 'artifacts/batches-existing-scenarios.png');

  // Abrupt service loss leaves an interrupted row, and continuing creates a fresh run.
  await page.getByLabel('批次名称', {exact: true}).fill('中断与取消验收');
  await page.getByLabel('工况来源', {exact: true}).selectOption('sweep');
  await page.getByLabel('批次计算方式', {exact: true}).selectOption('dynamic');
  await page.getByLabel('仿真时长 · s', {exact: true}).fill('86400');
  await page.getByLabel('输出步长 · s', {exact: true}).fill('0.1');
  await preview();
  const longBatch = await createBatch();
  let running;
  await expect(async () => {
    running = (await api('/batches/' + longBatch.id)).items.find(item => item.status === 'running');
    expect(running?.run_id).toBeTruthy();
  }).toPass({timeout: 20000});
  const oldRun = running.run_id;
  await context.close(); await launched.stop();
  await start('#batches');
  await expect(page.locator('[data-batch-item][data-status="interrupted"]')).toHaveCount(1, {timeout: 30000});
  await expect(page.locator('[data-batch-item][data-status="pending"]')).toHaveCount(4);
  await captureFhd(page, 'artifacts/batches-interrupted.png');
  await page.getByRole('button', {name: '继续未完成项', exact: true}).click();
  await expect(async () => {
    const state = await api('/batches/' + longBatch.id);
    running = state.items.find(item => item.status === 'running');
    expect(running?.run_id).toBeTruthy();
    expect(running.run_id).not.toBe(oldRun);
    expect(running.attempts).toHaveLength(2);
  }).toPass({timeout: 20000});
  await page.getByRole('button', {name: '取消剩余工况', exact: true}).click();
  await expect(page.locator('[data-batch-item][data-status="cancelled"]')).toHaveCount(4);
  await page.getByRole('button', {name: '停止当前工况', exact: true}).click();
  await expect(page.locator('[data-batch-item][data-status="cancelled"]')).toHaveCount(5, {timeout: 30000});
  expect((await api('/batches/' + longBatch.id)).status).toBe('cancelled');
  await captureFhd(page, 'artifacts/batches-cancelled.png');
  await page.getByLabel('已保存批次', {exact: true}).selectOption(created.id);
  await expect(page.locator('[data-batch-item][data-status="completed"]')).toHaveCount(5);
  await verifyValues(detail);
  expect(errors).toEqual([]);
  console.log(JSON.stringify({batches: [created.id, existing.id, longBatch.id], items: detail.total, sourceRevision: detail.project_revision,
    snapshot: detail.snapshot_hash, errors}));
} catch (error) {
  console.error(error, errors, await page?.locator('#batch-error').textContent().catch(() => ''), launched?.log());
  process.exitCode = 1;
  await captureFhd(page, 'artifacts/batches-failure.png').catch(() => {});
} finally {
  await browser.close();
  await launched?.stop();
}
