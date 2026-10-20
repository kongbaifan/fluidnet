import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// A1 冷库案例验收：从真实页面创建 −18°C 单库房案例、运行到完成、读取热指标与
// 同屏曲线、通过设备窗口改参数并重算、保存工作区，再重启服务并用全新浏览器读取
// 复算。热平衡方程、会话命令和归档复算的细节由 tests/test_refrigeration_a1.py 覆盖，
// 本脚本只验证用户实际点击的页面链路。
const dir = mkdtempSync(join(tmpdir(), 'fluidnet-cold-storage-'));
const key = 'fluidnet-prototype-engine-v1';
let launched, base, log = '';
async function start() {
  // 端口在 close 之后可能被系统保留段拒绝绑定，launchEngine 会自动换端口重试。
  launched = await launchEngine({args: ['--data-dir', join(dir, 'data')], env: { FLUIDNET_MODULE_STORE: join(dir, 'modules') }});
  ({base} = launched); log = launched.log();
}
async function stop() { if (launched) await launched.stop(); }
const browser = await chromium.launch({ channel: 'msedge', headless: true });
let context = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
let page = await context.newPage();
const errors = [];
const watch = p => p.on('pageerror', e => errors.push(e.message));
watch(page);
const ready = p => expect(p.locator('.rail-link[data-route="projects"]')).toBeVisible();
const api = path => fetch(base + '/api/v1' + path).then(r => r.json());
const temperature = () => page.locator('[data-cold-temperature]').textContent();
const coolingPower = () => page.locator('[data-cold-power]').textContent();
const coolingEnergy = () => page.locator('[data-cold-energy]').textContent();
const runButton = () => page.locator('[data-action="run-project"][data-command="run"]').first();
async function startRun() {
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/runs' && r.request().method() === 'POST', { timeout: 30000 });
  await runButton().click();
  const body = await (await response).json();
  expect(body.run_id).toBeTruthy();
  return body.run_id;
}
async function finishedRun(runId) {
  const deadline = Date.now() + 120000;
  for (;;) {
    const record = await api('/runs/' + runId);
    if (record.status === 'failed') throw Error(JSON.stringify(record.frame).slice(0, 600));
    if (record.status === 'completed') return record;
    if (Date.now() > deadline) throw Error('运行在 120 s 内未结束：' + runId);
    await new Promise(done => setTimeout(done, 250));
  }
}
async function saveWorkspace(p = page) {
  const response = p.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/workspace' && r.request().method() === 'POST');
  await p.locator('[data-action="save"]').first().click();
  expect((await response).status()).toBe(200);
  await expect(p.locator('[data-save-status]')).not.toContainText('正在保存');
}
const firstFrameVariable = (record, name) => record.frame.variables[name];
try {
  await start();
  const health = await api('/health');
  expect(health.supported_domains).toContain('thermal');
  expect(health.capabilities.cold_room_ideal_source).toBe(true);

  // 1. 项目页创建案例。catalog 加载完成前点击会失败，按「点案例 → 等指标面板」重试。
  await page.goto(base + '/#projects'); await ready(page);
  const createButton = page.locator('[data-action="cold-storage-example"]');
  await expect(createButton).toBeVisible();
  const metrics = page.locator('.cold-storage-summary');
  await expect(async () => {
    if (await metrics.isVisible().catch(() => false)) return;
    await createButton.click();
    await expect(metrics).toBeVisible({ timeout: 5000 });
  }).toPass({ timeout: 60000 });
  await expect(metrics).toContainText('−18°C 单库房 · A1');
  await expect(metrics).toContainText('理想冷源');
  const local = await page.evaluate(k => JSON.parse(localStorage.getItem(k) || '{}'), key);
  const draft = local.projects.find(p => p.caseId === 'cold-room-ideal-v1');
  expect(draft).toBeTruthy();
  const projectId = draft.id;
  expect(draft.caseId).toBe('cold-room-ideal-v1');
  expect(draft.pages[0].nodes.map(n => n.id).sort()).toEqual(['COLD1', 'ROOM1']);
  expect(draft.pages[0].edges).toHaveLength(1);
  expect(draft.controllers).toHaveLength(1);
  expect(local.charts.extra.filter(c => c.projectId === projectId).map(c => c.label))
    .toEqual(['库温', '冷却功率', '累计冷量']);

  // 2. 运行 2 h 仿真时间到完成：指标面板、同屏曲线和归档帧一致。
  const firstRunId = await startRun();
  const first = await finishedRun(firstRunId);
  expect(first.total_rows).toBe(241);
  await expect.poll(temperature, { timeout: 20000 }).toBe('-18.000');
  await expect.poll(coolingPower, { timeout: 20000 }).toBe('2.864');
  await expect.poll(coolingEnergy, { timeout: 20000 }).toBe('8.305');
  await expect(page.locator('#workbench-chart-plot svg.chart')).toBeVisible();
  const curve = page.locator('#workbench-chart-plot path.chart-line').first();
  await expect(curve).toHaveAttribute('d', /L/);
  await expect(page.locator('#workbench-flow-chart-readout')).toContainText('库温');
  expect(firstFrameVariable(first, 'ROOM1.state.temperature_k')).toBeCloseTo(255.15, 4);
  expect(firstFrameVariable(first, 'COLD1.cooling_power_w')).toBeCloseTo(2864, 0);
  expect(Math.abs(first.frame.metrics.energy_residual_j)).toBeLessThan(1e-3);
  mkdirSync('artifacts', { recursive: true });
  await page.screenshot({ path: 'artifacts/cold-storage-run.png', fullPage: true });

  // 3. 在设备窗口把附加热负荷改为 1 kW（显示单位 kW），应用后重算，冷却功率应同步抬升。
  await page.locator('[data-node="ROOM1"]').dblclick();
  const heatInput = page.locator('[data-instance-param="heat_input_w"][data-id="ROOM1"]');
  await expect(heatInput).toBeVisible();
  await heatInput.fill('1'); await heatInput.blur();
  await page.locator('[data-action="apply-instance"][data-id="ROOM1"]').click();
  await expect(page.getByRole('dialog')).toContainText('应用到 ROOM1');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('#toast')).toContainText('ROOM1 参数已应用');
  await page.locator('[data-action="float-close"]').first().click();
  const secondRunId = await startRun();
  const second = await finishedRun(secondRunId);
  await expect.poll(temperature, { timeout: 20000 }).toBe('-18.000');
  expect(firstFrameVariable(second, 'ROOM1.param.heat_input_w')).toBe(1000);
  expect(firstFrameVariable(second, 'COLD1.cooling_power_w')).toBeCloseTo(3864, -1);
  await expect.poll(coolingPower, { timeout: 20000 }).toBe('3.864');

  // 4. 保存工作区：案例、参数和曲线绑定进入服务器工作区。
  await saveWorkspace();
  const saved = await api('/workspace');
  const savedDraft = saved.data.projects.find(p => p.id === projectId);
  expect(savedDraft.pages[0].nodes.find(n => n.id === 'ROOM1').params.heat_input_w).toBe(1);
  expect(saved.revision).toBeGreaterThan(0);

  // 5. 硬停服务，用全新浏览器上下文（无 localStorage）读取同一工作区并复算。
  await stop(); await context.close(); await start();
  context = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
  page = await context.newPage(); watch(page);
  await page.goto(base + '/#projects'); await ready(page);
  const card = page.locator(`.project-preview[data-action="open-project"][data-id="${projectId}"]`);
  await expect(card).toBeVisible({ timeout: 30000 });
  await expect(page.locator('.project-card').filter({ hasText: '库房热系统' }).first()).toBeVisible();
  await card.click();
  const reopened = page.locator('.cold-storage-summary');
  await expect(reopened).toBeVisible();
  expect(await temperature()).toBe('-18.000');
  expect(await coolingPower()).toBe('3.864');
  const archived = await api('/runs/' + secondRunId);
  expect(archived.status).toBe('completed');
  expect(archived.frame.variables).toEqual(second.frame.variables);
  const replayId = await startRun();
  const replay = await finishedRun(replayId);
  expect(replay.frame.variables).toEqual(archived.frame.variables);
  expect(errors).toEqual([]);
  mkdirSync('artifacts', { recursive: true });
  await page.screenshot({ path: 'artifacts/cold-storage-restart.png', fullPage: true });
  console.log(JSON.stringify({ projectId, firstRunId, secondRunId, replayId,
    temperature: await temperature(), coolingPower: await coolingPower(), coolingEnergy: await coolingEnergy(),
    restart: 'workspace read-back + same-frame replay', errors }));
} catch (error) {
  mkdirSync('artifacts', { recursive: true });
  await page.screenshot({ path: 'artifacts/cold-storage-failure.png', fullPage: true }).catch(() => {});
  console.error(log.slice(-2500), errors);
  throw error;
} finally { await browser.close(); await stop(); }
