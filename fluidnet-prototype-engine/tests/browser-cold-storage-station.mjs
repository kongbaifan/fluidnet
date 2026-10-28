import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// 冷库 B 案例页面验收（EXECUTION_PLAN 第 4 节产品验收）：项目页创建 NH₃/CO₂ 制冷站 → 运行负荷阶跃工况 →
// 单步暂停中改目标蒸发压力并继续 → 导出报告与 CSV → 保存 → 硬停服务、全新浏览器读取并复算。
// 五闭环、上层启停与四个验收场景的数值由 tests/test_refrigeration_station_control.py 覆盖。
const dir = mkdtempSync(join(tmpdir(), 'fluidnet-station-'));
let launched, base;
const start = async () => { launched = await launchEngine({args: ['--data-dir', join(dir, 'data')], env: { FLUIDNET_MODULE_STORE: join(dir, 'modules') }}); ({base} = launched); };
const stop = async () => { if (launched) await launched.stop(); };
const errors = [];
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const newPage = async () => { const c = await browser.newContext({ ...FHD_CONTEXT, acceptDownloads: true }); const p = await c.newPage(); p.on('pageerror', e => errors.push(e.message)); return [c, p]; };
let [context, page] = await newPage();
const api = path => fetch(base + '/api/v1' + path).then(r => r.json());
const metric = id => page.locator(`[data-station-${id}]`).textContent();
async function finished(runId, status = 'completed') {
  const deadline = Date.now() + 240000;
  for (;;) {
    const record = await api('/runs/' + runId);
    if (record.status === status) return record;
    if (record.status === 'failed') throw Error(JSON.stringify(record.frame).slice(0, 600));
    if (Date.now() > deadline) throw Error('运行未在时限内到 ' + status + '：' + runId);
    await new Promise(done => setTimeout(done, 250));
  }
}
async function posted(click) {
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/runs' && r.request().method() === 'POST', { timeout: 30000 });
  await click();
  const r = await response;
  return { id: (await r.json()).run_id, body: r.request().postDataJSON() };
}
async function runScenario(id) {
  await page.locator('[data-action="cs-scenarios"]').click();
  return posted(() => page.locator(`[data-action="cs-run-scenario"][data-scenario="${id}"]`).click());
}
async function downloaded(click) {
  const event = page.waitForEvent('download'); await click();
  const file = await event; return readFileSync(await file.path(), 'utf-8');
}
try {
  await start();
  await page.goto(base + '/#projects');
  const panel = page.locator('.cold-storage-summary.cold-room');
  await expect(async () => {
    if (await panel.isVisible().catch(() => false)) return;
    await page.locator('[data-action="cs-create-station"]').click();
    await expect(panel).toBeVisible({ timeout: 5000 });
  }).toPass({ timeout: 60000 });
  const draft = (await page.evaluate(() => JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')))).projects.find(p => p.caseId === 'cold-storage-nh3co2-v2');
  expect(draft.pages[0].nodes).toHaveLength(20);
  expect(draft.controllers.map(c => c.id).sort()).toEqual(['head', 'level', 'room1', 'room2', 'suction']);
  expect(draft.circuitFluids.map(c => c.fluid).sort()).toEqual(['Ammonia', 'CarbonDioxide']);

  // 1. 负荷阶跃工况跑完：增开 1 台、减停 1 台，指标面板与归档一致。
  const first = await runScenario('B-S02');
  expect(first.body).toMatchObject({ duration_s: 86400, scenario_id: 'B-S02', history_window: 2881 });
  const run1 = await finished(first.id);
  const v1 = run1.frame.variables;
  expect(v1['script.control.state.starts']).toBe(1); expect(v1['script.control.state.stops']).toBe(1);
  await expect.poll(() => metric('room1'), { timeout: 20000 }).toBe((v1['ROOM1.state.temperature_k'] - 273.15).toFixed(2));
  expect(await metric('running')).toBe('3');
  expect(await metric('satisfaction')).toBe('100.00');
  mkdirSync('artifacts', { recursive: true });
  await captureFhd(page, 'artifacts/cold-storage-station-run.png');

  // 2. 单步（暂停态）中把目标蒸发压力改为 115 kPa，再继续：吸气压力跟到新目标。
  const stepped = await posted(() => page.locator('[data-action="run-project"][data-command="step"]').first().click());
  await finished(stepped.id, 'paused');
  await page.locator('[data-action="cs-targets"]').click();
  await page.getByRole('dialog').locator('input[name="evaporating"]').fill('115');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('#toast')).toContainText('目标压力已在运行中生效', { timeout: 20000 });
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const run2 = await finished(stepped.id);
  expect(run2.frame.variables['controller.suction.setpoint']).toBe(115000);
  expect(Math.abs(run2.frame.variables['LP1.state.pressure_pa'] - 115000)).toBeLessThan(600);
  const events = (await api(`/runs/${stepped.id}/events`)).events;
  expect(events.filter(e => e.command_status === 'applied').length).toBeGreaterThanOrEqual(2);   // step + two setpoints

  // 3. 报告与 CSV。
  await expect.poll(() => metric('lp-target'), { timeout: 20000 }).toBe('0.1150');
  const report = await downloaded(() => page.locator('[data-action="cs-report"]').click());
  expect(report).toContain('NH₃/CO₂ 制冷站运行报告'); expect(report).toContain(stepped.id);
  const csv = await downloaded(() => page.locator('[data-action="cs-csv"]').click());
  expect(csv.trim().split(/\r?\n/)).toHaveLength(2882);

  // 4. 保存，硬停服务，全新浏览器读取；按项目原设定复算 B-S02 与第一次归档逐变量一致。
  const save = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/workspace' && r.request().method() === 'POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await save).status()).toBe(200);
  await stop(); await context.close(); await start();
  [context, page] = await newPage();
  await page.goto(base + '/#projects');
  const card = page.locator(`.project-preview[data-action="open-project"][data-id="${draft.id}"]`);
  await expect(card).toBeVisible({ timeout: 30000 }); await card.click();
  await expect(page.locator('.cold-storage-summary.cold-room')).toBeVisible();
  expect((await api('/runs/' + first.id)).status).toBe('completed');
  const replay = await runScenario('B-S02');
  const run3 = await finished(replay.id);
  expect(run3.frame.variables).toEqual(run1.frame.variables);
  expect(errors).toEqual([]);
  await captureFhd(page, 'artifacts/cold-storage-station-restart.png');
  console.log(JSON.stringify({ project: draft.id, runs: [first.id, stepped.id, replay.id], room1: await metric('room1'), errors }));
} catch (error) {
  console.error(error);
  mkdirSync('artifacts', { recursive: true });
  await captureFhd(page, 'artifacts/cold-storage-station-failure.png').catch(() => {});
  process.exitCode = 1;
} finally {
  await browser.close();
  await stop();
}
