import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// Project-level acceptance uses the real import/editor/save/run paths. The
// fixture changes every device ID, omits caseId, and offers two connected pipes
// for rebinding one coil; it does not call the app's private state functions.
const dir = mkdtempSync(join(tmpdir(), 'fluidnet-coupling-modeling-'));
const storageKey = 'fluidnet-prototype-engine-v1';
const errors = [];
const browser = await chromium.launch({channel: 'msedge', headless: true});
let launched, base, context, page;
const primary = 'user_hx_w', spare = 'user_spare_coil', vessel = 'user_lp1';
const couplingId = 'CustomCoil-2', heatKey = `coupling.${couplingId}.heat_w`;

async function start() {
  launched = await launchEngine({args: ['--data-dir', join(dir, 'data')],
    env: {FLUIDNET_MODULE_STORE: join(dir, 'modules')}});
  base = launched.base;
  context = await browser.newContext({viewport: {width: 1700, height: 1150}});
  page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base + '/#projects');
  await expect(page.locator('.rail-link[data-route="projects"]')).toBeVisible();
}

async function api(path, body) {
  const response = await page.request.fetch(base + '/api/v1' + path, {
    method: body === undefined ? 'GET' : 'POST', data: body,
  });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

const current = () => page.evaluate(key => {
  const state = JSON.parse(localStorage.getItem(key));
  return state.projects.find(project => project.id === state.activeProject);
}, storageKey);
const runButton = command => page.locator(`[data-action="run-project"][data-command="${command}"]`).first();
const editor = () => page.getByRole('dialog');
const closeDialog = async () => {
  if (await editor().count()) await editor().locator('[data-action="close-dialog"]').first().click();
};
const openEditor = async () => {
  await page.locator('[data-action="cs-coupling"]').first().click();
  await expect(editor()).toContainText('热耦合关系');
};

async function save() {
  const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/workspace'
    && response.request().method() === 'POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await response).ok()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
  return current();
}

async function createRun() {
  const posted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/runs'
    && response.request().method() === 'POST');
  await runButton('run').click();
  const response = await posted;
  expect(response.ok(), await response.text()).toBe(true);
  return {id: (await response.json()).run_id, body: response.request().postDataJSON()};
}

async function finished(id) {
  let record;
  await expect(async () => {
    record = await api('/runs/' + id);
    if (record.status === 'failed') throw Error(JSON.stringify(record.frame));
    expect(record.status).toBe('completed');
  }).toPass({timeout: 120000, intervals: [100, 250, 500]});
  return record;
}

async function run() {
  const created = await createRun(), record = await finished(created.id);
  await expect(page.locator('[data-coupled-heat]')).toHaveText(
    (record.frame.variables[heatKey] / 1000).toFixed(3), {timeout: 20000});
  await expect(runButton('run')).toBeEnabled({timeout: 20000});
  expect(created.body.trend_variables).toContain(heatKey);
  expect(created.body.trend_variables).not.toContain('coupling.HX1.heat_w');
  expect(Math.abs(record.frame.variables[`coupling.${couplingId}.equation_residual_w`])).toBeLessThan(.01);
  return {...created, record};
}

async function selectNode(id) {
  await page.locator(`[data-node="${id}"]`).first().click();
  await expect(page.locator(`[data-action="delete-node"][data-id="${id}"]`).first()).toBeVisible();
}

async function deleteNode(id) {
  await selectNode(id);
  await page.locator(`[data-action="delete-node"][data-id="${id}"]`).first().click();
}

function customDocument(document) {
  const oldProject = document.project.id;
  const ids = Object.fromEntries(document.project.pages.flatMap(p => p.nodes).map(n => [n.id, 'user_' + n.id.toLowerCase()]));
  ids[oldProject] = 'thermal-modeling-custom';
  const rename = value => {
    if (typeof value === 'string') return ids[value] ?? value;
    if (Array.isArray(value)) return value.map(rename);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value)
      .map(([key, entry]) => [ids[key] ?? key, rename(entry)]));
    return value;
  };
  const result = rename(document), p = result.project, pg = p.pages[0];
  p.name = '自建单盘管系统';
  delete p.caseId;
  p.thermalCouplings = [];
  result.charts = [];
  p.solver = {...p.solver, duration: 2, dt: 1, executionMode: 'fast', continuous: false};
  // Split the old storage-free pipe into two series pipes without changing
  // total length, so either is a physically valid coupling endpoint.
  const first = pg.nodes.find(n => n.id === primary), second = structuredClone(first);
  const length = Object.hasOwn(first.params, 'length') ? 'length' : 'length_m';
  first.params[length] /= 2;
  first.draft[length] = first.params[length];
  second.id = spare; second.name = '备用浸没盘管'; second.x = 310; second.y = 600;
  second.params[length] = first.params[length]; second.draft[length] = first.params[length];
  pg.nodes.push(second);
  const outlet = pg.edges.find(edge => edge[1] === primary && edge[2] === 'out0');
  outlet[1] = spare;
  pg.edges.push(['custom-series', primary, 'out0', spare, 'in0']);
  return result;
}

async function setContinuous(enabled) {
  await page.locator('.rail-link[data-route="settings"]').click();
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-continuous]').setChecked(enabled);
  if (!enabled) {
    await page.locator('[data-solver-field="duration"]').fill('2');
    await page.locator('[data-solver-field="duration"]').blur();
  }
  await page.locator('.rail-link[data-route="workbench"]').click();
}

try {
  await start();
  await expect(async () => {
    if (await page.locator('.thermal-coupling').isVisible().catch(() => false)) return;
    await page.locator('[data-action="cs-create-coupled"]').click();
    await expect(page.locator('.thermal-coupling')).toBeVisible({timeout: 4000});
  }).toPass({timeout: 30000});
  const original = await save();
  await page.goto(base + '/#projects');
  await page.locator(`[data-action="wf-manage"][data-id="${original.id}"]`).click();
  const downloaded = page.waitForEvent('download');
  await page.locator('[data-action="wf-export"]').click();
  const exportedPath = join(dir, 'original.json');
  await (await downloaded).saveAs(exportedPath);
  await closeDialog();
  const fixture = customDocument(JSON.parse(readFileSync(exportedPath, 'utf8')));
  const importedPath = join(dir, 'custom.json');
  writeFileSync(importedPath, JSON.stringify(fixture));
  await page.locator('[data-action="wf-import"]').click();
  await page.getByLabel('单项目文件').setInputFiles(importedPath);
  await editor().locator('select[name="mode"]').selectOption('replace');
  await editor().locator('button[type="submit"]').click();
  await expect(page.locator('#toast')).toContainText('项目已导入');
  await page.locator(`.project-preview[data-id="${fixture.project.id}"]`).click();
  const withoutLink = await save();
  expect(withoutLink.caseId).toBeUndefined();
  expect(withoutLink.thermalCouplings).toEqual([]);
  expect((await api('/projects/' + fixture.project.id)).document.project.thermalCouplings).toEqual([]);

  await openEditor();
  const pipes = await editor().getByLabel('液体管段', {exact: true}).locator('option').evaluateAll(options => options.map(o => o.value));
  expect(pipes).toContain(primary);
  expect(pipes).toContain(spare);
  expect(pipes).not.toContain('user_wp1');
  expect(pipes).not.toContain('user_wl1');
  await editor().getByLabel('关系标识', {exact: true}).fill(couplingId);
  await editor().getByLabel('液体管段', {exact: true}).selectOption(primary);
  await expect(editor().getByLabel('通路', {exact: true})).toHaveValue('ch0');
  await editor().getByLabel('饱和制冷剂容器', {exact: true}).selectOption(vessel);
  await editor().getByLabel('换热能力 UA · W/K', {exact: true}).fill('-1');
  await editor().locator('button[type="submit"]').click();
  await expect(editor()).toBeVisible();
  expect((await current()).thermalCouplings).toEqual([]);
  await editor().getByLabel('换热能力 UA · W/K', {exact: true}).fill('1800');
  await editor().getByLabel('关系标识', {exact: true}).fill('_invalid');
  await editor().locator('button[type="submit"]').click();
  await expect(editor()).toBeVisible();
  expect((await current()).thermalCouplings).toEqual([]);
  await editor().getByLabel('关系标识', {exact: true}).fill(couplingId);
  await editor().locator('button[type="submit"]').click();
  await expect(editor()).toHaveCount(0);
  const created = await save();
  expect(created.thermalCouplings).toEqual([{id: couplingId, fluid_instance_id: primary,
    fluid_channel_id: 'ch0', refrigerant_vessel_id: vessel, ua_w_k: 1800}]);
  const first = await run();
  expect(first.record.frame.variables[heatKey]).toBeGreaterThan(0);
  // Observations added after a run must still be included in its saved snapshot.
  await page.locator('.rail-link[data-route="curves"]').click();
  await page.locator('[data-action="add-chart-variable"]').click();
  await editor().locator('button[type="submit"]').click();
  await save();
  const addedBinding = await page.evaluate(key => JSON.parse(localStorage.getItem(key)).charts.extra
    .find(binding => binding.projectId === 'thermal-modeling-custom' && !binding.couplingId), storageKey);
  expect(addedBinding).toBeTruthy();
  await page.locator('.rail-link[data-route="runs"]').click();
  await page.locator('[data-action="record-project"]').click();
  await save();
  const historical = await page.evaluate(key => JSON.parse(localStorage.getItem(key)).records[0], storageKey);
  expect(historical.chartBindings.find(binding => binding.canonicalKey === heatKey).nodeId).toBe(primary);
  expect(historical.chartBindings.some(binding => binding.id === addedBinding.id)).toBe(true);
  await page.locator('.rail-link[data-route="workbench"]').click();

  // Rebinding changes the actual run input and leaves the old archived snapshot intact.
  await openEditor();
  await editor().getByLabel('液体管段', {exact: true}).selectOption(spare);
  await editor().getByLabel('换热能力 UA · W/K', {exact: true}).fill('900');
  await editor().locator('button[type="submit"]').click();
  await expect(page.locator('[data-result-status]').first()).toContainText('参数已变更');
  await expect(page.locator('[data-coupled-heat]')).toHaveText('—');
  await expect(page.locator('[data-coupled-result-status]')).toContainText('过期');
  await page.locator('.rail-link[data-route="curves"]').click();
  await page.getByLabel('曲线数据来源', {exact: true}).selectOption('live');
  const heatPanel = page.locator('#extra-charts .panel').filter({has: page.getByRole('heading', {name: couplingId + ' · 盘管换热量', exact: true})});
  await expect(heatPanel.locator('svg[data-chart]')).toHaveCount(0);
  await expect(page.locator('#extra-charts')).toContainText('结果已过期');
  await page.getByLabel('曲线数据来源', {exact: true}).selectOption(historical.id);
  await expect(page.locator('#extra-charts svg[data-chart]').first()).toBeVisible();
  await page.getByLabel('曲线数据来源', {exact: true}).selectOption('live');
  await page.locator('.rail-link[data-route="workbench"]').click();
  const changed = await run();
  expect(changed.body.project.thermal_couplings[0].fluid_instance_id).toBe(spare);
  expect(changed.body.project.thermal_couplings[0].ua_w_k).toBe(900);
  expect(changed.record.frame.variables[heatKey]).not.toBe(first.record.frame.variables[heatKey]);
  expect((await api('/runs/' + first.id)).request.project.thermal_couplings[0].fluid_instance_id).toBe(primary);

  // A single-device copy has no implicit thermal relation; undo removes only the copy.
  await selectNode(spare);
  await page.keyboard.press('Control+c');
  await page.keyboard.press('Control+v');
  const copied = await save();
  expect(copied.pages[0].nodes).toHaveLength(fixture.project.pages[0].nodes.length + 1);
  expect(copied.thermalCouplings).toHaveLength(1);
  expect(copied.thermalCouplings[0].fluid_instance_id).toBe(spare);
  await page.locator('[data-action="undo"]').first().click();

  // Referenced deletion is reviewable, and undo/redo restores the graph AND relation.
  await deleteNode(spare);
  await expect(editor()).toContainText(couplingId);
  await closeDialog();
  expect((await save()).thermalCouplings).toHaveLength(1);
  await expect(page.locator(`[data-node="${spare}"]`).first()).toBeVisible();
  await deleteNode(spare);
  await editor().locator('button[type="submit"]').click();
  expect((await save()).thermalCouplings).toEqual([]);
  await expect(page.locator(`[data-node="${spare}"]`)).toHaveCount(0);
  await page.locator('[data-action="undo"]').first().click();
  expect((await save()).thermalCouplings[0].fluid_instance_id).toBe(spare);
  await expect(page.locator(`[data-node="${spare}"]`).first()).toBeVisible();
  await page.locator('[data-action="redo"]').first().click();
  expect((await save()).thermalCouplings).toEqual([]);
  await page.locator('[data-action="undo"]').first().click();

  // Removing the relation never deletes its devices; undo restores its current charts.
  await openEditor();
  await editor().getByRole('button', {name: '移除热耦合', exact: true}).click();
  await editor().getByRole('button', {name: '解除关系', exact: true}).click();
  const removed = await save();
  expect(removed.thermalCouplings).toEqual([]);
  expect(removed.pages[0].nodes).toHaveLength(fixture.project.pages[0].nodes.length);
  await expect(page.locator('[data-coupled-heat]')).toHaveCount(0);
  await page.locator('[data-action="undo"]').first().click();
  expect((await save()).thermalCouplings[0].fluid_instance_id).toBe(spare);

  // A real continuous session holds the edit lock in both running and paused states.
  await setContinuous(true);
  const live = await createRun();
  await expect.poll(async () => (await api('/runs/' + live.id)).status, {timeout: 30000}).toBe('running');
  for (const phase of ['running', 'paused']) {
    if (phase === 'paused') {
      await runButton('pause').click();
      await expect.poll(async () => (await api('/runs/' + live.id)).status, {timeout: 30000}).toBe('paused');
    }
    await page.locator('[data-action="cs-coupling"]').first().click();
    await expect(page.locator('#toast')).toContainText('停止');
    await expect(editor()).toHaveCount(0);
    await deleteNode(spare);
    await expect(page.locator('#toast')).toContainText('停止');
    await expect(editor()).toHaveCount(0);
    await page.locator('[data-action="undo"]').first().click();
    await expect(page.locator('#toast')).toContainText('停止');
    expect((await save()).thermalCouplings[0].fluid_instance_id).toBe(spare);
    await expect(page.locator(`[data-node="${spare}"]`).first()).toBeVisible();
  }
  await runButton('stop').click();
  await expect.poll(async () => (await api('/runs/' + live.id)).status, {timeout: 30000}).toBe('cancelled');
  await expect.poll(async () => (await current()).run.status, {timeout: 20000}).toBe('stopped');
  await setContinuous(false);
  const beforeRestart = await run();
  await save();
  mkdirSync('artifacts', {recursive: true});
  await page.screenshot({path: 'artifacts/thermal-coupling-modeling.png', fullPage: true});

  await launched.stop(); await context.close(); await start();
  await page.locator(`.project-preview[data-id="${fixture.project.id}"]`).click();
  await expect(page.locator('.thermal-coupling')).toBeVisible();
  const replay = await run();
  expect(replay.record.frame.variables).toEqual(beforeRestart.record.frame.variables);
  const stored = await api('/projects/' + fixture.project.id);
  expect(stored.document.project.caseId).toBeUndefined();
  expect(stored.document.project.thermalCouplings).toEqual(beforeRestart.body.project.thermal_couplings);
  const saved = await api(`/projects/${fixture.project.id}/runs`, {mode: 'dynamic', duration_s: 2, dt_s: 1, scenario_id: 'rated'});
  expect((await finished(saved.run_id)).frame.variables).toEqual(beforeRestart.record.frame.variables);
  await page.setViewportSize({width: 1366, height: 768});
  await openEditor();
  await expect(editor().getByLabel('液体管段', {exact: true})).toBeInViewport();
  await expect(editor().getByLabel('饱和制冷剂容器', {exact: true})).toBeInViewport();
  await expect(editor().locator('button[type="submit"]')).toBeInViewport();
  await page.screenshot({path: 'artifacts/thermal-coupling-editor-1366.png', fullPage: true});
  await closeDialog();
  expect(errors).toEqual([]);
  console.log(JSON.stringify({projectId: fixture.project.id, couplingId,
    runs: [first.id, changed.id, live.id, beforeRestart.id, replay.id, saved.run_id], errors}));
} catch (error) {
  console.error(error, errors, launched?.log());
  process.exitCode = 1;
  mkdirSync('artifacts', {recursive: true});
  await page?.screenshot({path: 'artifacts/thermal-coupling-modeling-failure.png', fullPage: true}).catch(() => {});
} finally {
  await browser.close();
  await launched?.stop();
}
