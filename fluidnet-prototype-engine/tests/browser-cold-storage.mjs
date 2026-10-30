import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// 冷库 A 案例页面验收（PLAN 5.3）：项目页创建 −18°C 案例 → 选工况运行 → 单步/暂停中改参数并继续 →
// 编辑负荷日程后重算 → 导出报告与 CSV → 策略对照 → 机组工作点 → 保存 → 硬停服务、全新浏览器读取并复算。
// 物理、守恒、事件与控制细节由 tests/test_refrigeration_cold_store.py 覆盖；本脚本只验证用户实际点击的链路。
const dir = mkdtempSync(join(tmpdir(), 'fluidnet-cold-storage-'));
const key = 'fluidnet-prototype-engine-v1';
let launched, base;
async function start() {
  launched = await launchEngine({args: ['--data-dir', join(dir, 'data')], env: { FLUIDNET_MODULE_STORE: join(dir, 'modules') }});
  ({base} = launched);
}
async function stop() { if (launched) await launched.stop(); }
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const newPage = async () => { const c = await browser.newContext({ ...FHD_CONTEXT, acceptDownloads: true }); const p = await c.newPage(); p.on('pageerror', e => errors.push(e.message)); return [c, p]; };
const errors = [];
let [context, page] = await newPage();
const ready = p => expect(p.locator('.rail-link[data-route="projects"]')).toBeVisible();
const api = path => fetch(base + '/api/v1' + path).then(r => r.json());
const metric = id => page.locator(`[data-cold-${id}]`).textContent();
async function finished(runId, status = 'completed') {
  const deadline = Date.now() + 180000;
  for (;;) {
    const record = await api('/runs/' + runId);
    if (record.status === status) return record;
    if (record.status === 'failed') throw Error(JSON.stringify(record.frame).slice(0, 600));
    if (Date.now() > deadline) throw Error('运行在 180 s 内未到 ' + status + '：' + runId);
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
  const event = page.waitForEvent('download');
  await click();
  const file = await event;
  return { name: file.suggestedFilename(), text: readFileSync(await file.path(), 'utf-8') };
}
async function saveWorkspace() {
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/workspace' && r.request().method() === 'POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await response).status()).toBe(200);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
}
const temperatureOf = record => (record.frame.variables['ROOM1.state.temperature_k'] - 273.15).toFixed(2);
try {
  await start();
  expect((await api('/health')).capabilities.cold_store_cycle).toBe(true);

  // 1. 项目页创建案例（catalog 加载完成前点击会失败，重试到面板出现）。
  await page.goto(base + '/#projects'); await ready(page);
  const panel = page.locator('.cold-storage-summary.cold-room');
  await expect(async () => {
    if (await panel.isVisible().catch(() => false)) return;
    await page.locator('[data-action="cs-create"]').click();
    await expect(panel).toBeVisible({ timeout: 5000 });
  }).toPass({ timeout: 60000 });
  const draft = (await page.evaluate(k => JSON.parse(localStorage.getItem(k)), key)).projects.find(p => p.caseId === 'cold-room-minus18-v1');
  const projectId = draft.id;
  expect(draft.pages[0].nodes.map(n => n.id).sort()).toEqual(['AC1', 'CU1', 'ROOM1']);
  expect(draft.scenarios.map(s => s.id)).toContain('A-S05-variable');
  expect(draft.fluid).toBe('HEOS::R290');

  // 2. 工况 A-S02 运行到完成：面板指标与归档帧一致，全部 721 帧保留。
  const first = await runScenario('A-S02');
  expect(first.body).toMatchObject({ duration_s: 21600, dt_s: 30, scenario_id: 'A-S02', history_window: 721 });
  const run1 = await finished(first.id);
  expect(run1.total_rows).toBe(721);
  await expect.poll(() => metric('temperature'), { timeout: 20000 }).toBe(temperatureOf(run1));
  expect(await metric('starts')).toBe(String(run1.frame.variables['CU1.state.starts']));
  expect(Math.abs(run1.frame.metrics.energy_residual_j)).toBeLessThan(1e-2);
  mkdirSync('artifacts', { recursive: true });
  await captureFhd(page, 'artifacts/cold-storage-run.png');

  // 3. 单步（暂停态），在设备窗口把温控设定改为 −19 °C 并应用，再继续运行到结束。
  const stepped = await posted(() => page.locator('[data-action="run-project"][data-command="step"]').first().click());
  await finished(stepped.id, 'paused');
  await page.locator('[data-node="ROOM1"]').dblclick();
  const setpoint = page.locator('[data-instance-param="setpoint_temperature_k"][data-id="ROOM1"]');
  await expect(setpoint).toBeVisible();
  await setpoint.fill('-19'); await setpoint.blur();
  await page.locator('[data-action="apply-instance"][data-id="ROOM1"]').click();
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect.poll(async () => (await api(`/runs/${stepped.id}/events`)).events.some(e => e.command_status === 'applied'), { timeout: 20000 }).toBe(true);
  await page.locator('[data-action="float-close"]').first().click();
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const run2 = await finished(stepped.id);
  expect(run2.frame.variables['ROOM1.param.setpoint_temperature_k']).toBeCloseTo(254.15, 9);

  // 4. 负荷日程：给 A-S02 加一个 1 h 室外 35 °C 事件，校验应用后重算。
  // 页面轮询到运行结束后才允许编辑（运行中点击会提示先停止），所以重试到弹窗出现。
  await expect.poll(() => metric('temperature'), { timeout: 20000 }).toBe(temperatureOf(run2));
  await expect(async () => {
    await page.locator('[data-action="cs-schedule"]').click();
    await expect(page.locator('#cs-event-type')).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 30000 });
  await page.locator('#cs-event-type').selectOption('ambient_temperature');
  await page.locator('#cs-time').fill('1'); await page.locator('#cs-temperature').fill('35');
  await page.locator('[data-action="cs-add-event"]').click();
  await expect(page.locator('#cs-events')).toContainText('室外温度变化');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('#toast')).toContainText('日程已校验并应用');
  const third = await runScenario('A-S02');
  expect(third.body.project.scenarios.find(s => s.id === 'A-S02').events).toHaveLength(2);
  const run3 = await finished(third.id);
  expect(run3.frame.variables['CU1.param.ambient_temperature_k']).toBeCloseTo(308.15, 9);
  await expect.poll(() => metric('temperature'), { timeout: 20000 }).toBe(temperatureOf(run3));

  // 5. 报告、CSV 与两次运行对照。
  const report = await downloaded(() => page.locator('[data-action="cs-report"]').click());
  expect(report.text).toContain('冷库运行报告'); expect(report.text).toContain(third.id);
  const csv = await downloaded(() => page.locator('[data-action="cs-csv"]').click());
  expect(csv.text.trim().split(/\r?\n/)).toHaveLength(722);
  await page.locator('[data-action="cs-compare"]').click();
  await page.getByRole('dialog').locator('select[name="a"]').selectOption(first.id);
  await page.getByRole('dialog').locator('select[name="b"]').selectOption(third.id);
  const comparison = await downloaded(() => page.getByRole('dialog').locator('button[type="submit"]').click());
  expect(comparison.text).toContain('公平性'); expect(comparison.text).toContain('不一致');

  // 6. 机组工作点验证台：额定点与 A0 独立参考一致（10.000 kW、COP 1.5070）。
  await page.locator('[data-action="cs-bench"]').click();
  await page.locator('[data-action="cs-bench-run"]').click();
  await expect(page.locator('[data-bench-cooling]')).toHaveText('10.000 kW');
  await expect(page.locator('[data-bench-cop]')).toHaveText('1.5070');
  await page.locator('[data-action="close-dialog"]').first().click();

  // 7. 保存，硬停服务，全新浏览器上下文读取同一工作区：归档报告可下载，复算与归档帧逐变量一致。
  await saveWorkspace();
  await stop(); await context.close(); await start();
  [context, page] = await newPage();
  await page.goto(base + '/#projects'); await ready(page);
  const card = page.locator(`.project-preview[data-action="open-project"][data-id="${projectId}"]`);
  await expect(card).toBeVisible({ timeout: 30000 });
  await card.click();
  await expect(page.locator('.cold-storage-summary.cold-room')).toBeVisible();
  expect((await (await fetch(`${base}/api/v1/runs/${third.id}/report.html`)).text())).toContain(third.id);
  const replay = await runScenario('A-S02');
  const run4 = await finished(replay.id);
  expect(run4.frame.variables).toEqual(run3.frame.variables);
  expect(errors).toEqual([]);
  await captureFhd(page, 'artifacts/cold-storage-restart.png');
  console.log(JSON.stringify({ projectId, runs: [first.id, stepped.id, third.id, replay.id], temperature: await metric('temperature'), errors }));
} catch (error) {
  console.error(error);
  mkdirSync('artifacts', { recursive: true });
  await captureFhd(page, 'artifacts/cold-storage-failure.png').catch(() => {});
  process.exitCode = 1;
} finally {
  await browser.close();
  await stop();
}
