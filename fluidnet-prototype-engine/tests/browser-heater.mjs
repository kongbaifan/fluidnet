import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';
import {chromium, expect} from '@playwright/test';
import {mkdirSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';

const dir = mkdtempSync(join(tmpdir(), 'fluidnet-heater-ui-'));
const launched = await launchEngine({args: ['--data-dir', join(dir, 'data')],
  env: {FLUIDNET_MODULE_STORE: join(dir, 'modules')}});
const browser = await chromium.launch({channel: 'msedge', headless: true});
const page = await browser.newPage({...FHD_CONTEXT});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const state = () => page.evaluate(() => JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
const dialog = () => page.getByRole('dialog');
const runButton = () => page.locator('[data-action="run-project"][data-command="run"]').first();

async function save() {
  const posted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/workspace'
    && response.request().method() === 'POST');
  posted.catch(() => {});
  await page.locator('[data-action="save"]').first().click();
  const response = await posted;
  expect(response.ok(), await response.text()).toBe(true);
  const all = await state();
  return all.projects.find(project => project.id === all.activeProject);
}

async function run(powerW) {
  const posted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/runs'
    && response.request().method() === 'POST');
  posted.catch(() => {});
  await runButton().click();
  const response = await posted;
  expect(response.ok(), await response.text()).toBe(true);
  const submitted = response.request().postDataJSON();
  expect(submitted.project.instances.find(node => node.id === 'H1').parameters.heat_input_w).toBe(powerW);
  const id = (await response.json()).run_id;
  let record;
  await expect(async () => {
    const result = await page.request.get(launched.base + '/api/v1/runs/' + id);
    expect(result.ok(), await result.text()).toBe(true);
    record = await result.json();
    if (record.status === 'failed') throw Error(JSON.stringify(record.frame));
    expect(record.status).toBe('completed');
  }).toPass({timeout: 30000, intervals: [100, 250, 500]});
  expect(record.frame.variables['H1.heat_w']).toBeCloseTo(powerW, 6);
  expect(Math.abs(record.frame.metrics.energy_residual_w)).toBeLessThan(1e-6);
  await expect(runButton()).toBeEnabled();
  return record;
}

try {
  await page.goto(launched.base);
  await page.locator('[data-action="start-modeling"]').click();
  const initial = await save(), library = (await state()).modules;
  await page.locator('.rail-link[data-route="projects"]').click();
  await page.locator('[data-action="wf-manage"][data-id="' + initial.id + '"]').click();
  const downloaded = page.waitForEvent('download');
  await page.locator('[data-action="wf-export"]').click();
  const exportedPath = join(dir, 'original.json');
  await (await downloaded).saveAs(exportedPath);
  await dialog().locator('[data-action="close-dialog"]').first().click();
  const document = JSON.parse(readFileSync(exportedPath, 'utf8'));
  const project = document.project, pg = project.pages[0];
  project.id = 'heater-ui';
  project.name = '电加热器界面验收';
  project.scenarios = [];
  project.activeScenarioId = '';
  project.solver = {...project.solver, mode: 'dynamic', duration: 2, dt: 1, executionMode: 'fast', continuous: false};
  document.charts = [];
  document.modules = library.filter(module => ['source', 'valve', 'heater'].includes(module.id));
  project.moduleSnapshots = Object.fromEntries(document.modules.map(module => [module.id, module]));
  const node = (id, moduleId, params, x) => ({id, moduleId, name: id, x, y: 180, params, draft: {...params}});
  pg.nodes = [
    node('B1', 'source', {pressure: 250, temperature: 20}, 100),
    node('V1', 'valve', {opening: 50, kv: 10}, 330),
    node('H1', 'heater', {power: 2}, 560),
    node('B2', 'source', {pressure: 120, temperature: 20}, 800),
  ];
  pg.edges = [['e1', 'B1', 'out0', 'V1', 'in0'], ['e2', 'V1', 'out0', 'H1', 'in0'],
    ['e3', 'H1', 'out0', 'B2', 'out0']];
  pg.name = '边界 → 阀门 → 电加热器 → 出口';
  project.pages = [pg];
  const importedPath = join(dir, 'heater.json');
  writeFileSync(importedPath, JSON.stringify(document));
  await page.locator('[data-action="wf-import"]').click();
  await page.getByLabel('单项目文件').setInputFiles(importedPath);
  await dialog().locator('select[name="mode"]').selectOption('replace');
  await dialog().locator('button[type="submit"]').click();
  await expect(page.locator('#toast')).toContainText('项目已导入');
  await page.locator('.project-preview[data-id="heater-ui"]').click();
  const first = await run(2000);

  await page.locator('[data-node="H1"]').first().dblclick();
  const power = page.getByRole('spinbutton', {name: 'H1 加热功率草稿', exact: true});
  await expect(power).toHaveValue('2');
  await power.fill('5');
  await power.blur();
  await page.locator('[data-action="apply-instance"][data-id="H1"]').click();
  await dialog().locator('button[type="submit"]').click();
  await expect(dialog()).toHaveCount(0);
  const changed = await save();
  expect(changed.pages[0].nodes.find(node => node.id === 'H1').params.power).toBe(5);
  await page.getByRole('button', {name: '关闭设备窗口', exact: true}).click();
  const second = await run(5000);
  expect(second.frame.variables['H1.outlet_temperature_k']).toBeGreaterThan(first.frame.variables['H1.outlet_temperature_k']);
  await save();
  const reloaded = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/workspace'
    && response.request().method() === 'GET');
  reloaded.catch(() => {});
  await page.reload();
  expect((await reloaded).ok()).toBe(true);
  await expect(page.locator('[data-node="H1"]').first()).toBeVisible();
  expect((await state()).projects.find(project => project.id === 'heater-ui')
    .pages[0].nodes.find(node => node.id === 'H1').params.power).toBe(5);
  mkdirSync('artifacts', {recursive: true});
  await captureFhd(page, 'artifacts/heater-ui-run.png');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({beforeHeatW: first.frame.variables['H1.heat_w'],
    afterHeatW: second.frame.variables['H1.heat_w'], errors}));
} catch (error) {
  console.error(error, errors, launched.log());
  process.exitCode = 1;
  mkdirSync('artifacts', {recursive: true});
  await captureFhd(page, 'artifacts/heater-ui-failure.png').catch(() => {});
} finally {
  await browser.close();
  await launched.stop();
}
