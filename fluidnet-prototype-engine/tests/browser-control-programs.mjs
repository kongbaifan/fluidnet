import { chromium, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { testServer } from './browser-server.mjs';

const fixture = await testServer(), base = fixture.base;
const browser = await chromium.launch({channel: 'msedge', headless: true});
const page = await browser.newPage({viewport: {width: 1600, height: 1100}});
const errors = []; page.on('pageerror', error => errors.push(error.message));
const storageKey = 'fluidnet-prototype-engine-v1';
const longId = 'alpha_' + 'a'.repeat(75); // Maximum valid backend Identifier length: 81.
const source = (id, target, value) => `def initialize(ctx):\n    ctx.state["count"] = 0\n\ndef step(ctx, dt_s):\n    ctx.state["count"] += 1\n    ctx.write("${target}", ${value})\n    ctx.log("${id}")\n\ndef finalize(ctx):\n    pass\n`;
const script = (id, target, value, timeout_s) => {
  const code = source(id, target, value);
  return {id, language: 'python', source: code, enabled: true, sample_s: .1,
    inputs: [], outputs: [target], timeout_s, content_hash: createHash('sha256').update(code).digest('hex')};
};
const api = async (path, body) => {
  const response = body === undefined ? await page.request.get(base + '/api/v1' + path)
    : await page.request.post(base + '/api/v1' + path, {data: body});
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
};
const save = async () => {
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/workspace' && r.request().method() === 'POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await response).ok()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
  return page.evaluate(key => JSON.parse(localStorage.getItem(key)), storageKey);
};
const selectedProject = data => data.projects.find(project => project.id === data.activeProject);
const select = id => page.getByLabel('选择控制脚本').selectOption(id);
const ready = () => expect(page.locator('#app-header')).toContainText('模块平台 · v');
let runId;
try {
  await page.goto(base + '/#controls'); await ready();
  await expect(page.getByLabel('选择控制脚本').locator('option')).toHaveCount(1);
  // Import the pre-editor multi-script shape. The old single-script projection
  // must not overwrite either script or its timeout/hash during normalization.
  const alpha = script(longId, 'V1.param.opening_ratio', .6, 7.5);
  const beta = script('beta', 'V2.param.opening_ratio', .4, 9);
  const seed = await save();
  const oldSingle = structuredClone(seed), oldOwner = selectedProject(oldSingle);
  oldSingle.dirty = true;
  delete oldOwner.controlPrograms; delete oldOwner.selectedControlId;
  oldOwner.controlScripts = [script('control', 'V1.param.opening_ratio', .5, 9)];
  oldOwner.control = source('saved edit after old run', 'V1.param.opening_ratio', .55);
  oldOwner.controlEnabled = false; delete oldOwner.controlTimeout;
  await page.evaluate(({key, data}) => localStorage.setItem(key, JSON.stringify(data)), {key: storageKey, data: oldSingle});
  await page.reload(); await ready();
  await expect(page.getByLabel('项目控制脚本')).toHaveValue(oldOwner.control);
  await expect(page.getByLabel('控制执行超时')).toHaveValue('9');
  const migratedSingle = selectedProject(await save()).controlScripts[0];
  expect(migratedSingle.source).toBe(oldOwner.control);
  expect(migratedSingle.enabled).toBe(false);
  expect(migratedSingle.content_hash).toBeUndefined();
  // Continue from the latest saved revision before importing the multi-script shape.
  Object.assign(seed, await save());
  seed.dirty = true;
  const owner = selectedProject(seed);
  delete owner.controlPrograms; delete owner.selectedControlId;
  owner.controlScripts = [alpha, beta];
  await page.evaluate(({key, data}) => localStorage.setItem(key, JSON.stringify(data)), {key: storageKey, data: seed});
  await page.reload(); await ready();
  await expect(page.getByLabel('选择控制脚本').locator('option')).toHaveCount(2);
  await expect(page.getByLabel('项目控制脚本')).toHaveValue(alpha.source);
  await expect(page.getByLabel('控制执行超时')).toHaveValue('7.5');
  await select('beta');
  await expect(page.getByLabel('项目控制脚本')).toHaveValue(beta.source);
  const editedSource = source('beta edited', 'V2.param.opening_ratio', .35);
  await page.getByLabel('项目控制脚本').fill(editedSource);
  await page.getByLabel('控制程序名称').fill('出口阀控制');
  await page.getByLabel('控制执行超时').fill('12.5');
  await page.getByLabel('控制执行超时').blur();
  const edited = selectedProject(await save());
  expect(edited.controlScripts[0]).toEqual(alpha);
  expect(edited.controlScripts[1]).toMatchObject({id: 'beta', source: editedSource, timeout_s: 12.5});
  expect(edited.controlScripts[1].content_hash).toBeUndefined();
  await select(longId);
  await expect(page.getByLabel('项目控制脚本')).toHaveValue(alpha.source);
  await select('beta');
  await expect(page.getByLabel('项目控制脚本')).toHaveValue(editedSource);

  const preview = page.waitForResponse(r => r.url().endsWith('/controls/preview'));
  await page.locator('[data-action="preview-control"]').click();
  const previewResponse = await preview;
  expect(previewResponse.ok(), await previewResponse.text()).toBe(true);
  expect(previewResponse.request().postDataJSON().script).toMatchObject({id: 'beta', timeout_s: 12.5});
  await expect(page.locator('#control-output')).toContainText('预览成功');
  expect(selectedProject(await save()).controlScripts[0]).toEqual(alpha);

  await page.reload(); await ready();
  await expect(page.getByLabel('选择控制脚本')).toHaveValue('beta');
  await expect(page.getByLabel('控制程序名称')).toHaveValue('出口阀控制');
  await expect(page.getByLabel('控制执行超时')).toHaveValue('12.5');
  await page.locator('.rail-link[data-route="workbench"]').click();
  const created = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/runs' && r.request().method() === 'POST');
  await page.locator('[data-action="run-project"][data-command="step"]').first().click();
  const request = await created;
  expect(request.request().postDataJSON().project.control_scripts.map(script => script.id)).toEqual([longId, 'beta']);
  runId = (await request.json()).run_id;
  await expect.poll(async () => (await api('/runs/' + runId)).frame?.time_s, {timeout: 30000}).toBeGreaterThan(0);
  const record = await api('/runs/' + runId);
  expect(record.frame.variables['V1.param.opening_ratio']).toBe(.6);
  expect(record.frame.variables['V2.param.opening_ratio']).toBe(.35);
  expect(record.frame.variables[`script.${longId}.state.count`]).toBeGreaterThan(0);
  expect(record.frame.variables['script.beta.state.count']).toBeGreaterThan(0);
  const savedRun = selectedProject(await save()).run;
  expect(JSON.parse(savedRun.parameterKey).controls.map(script => script.id)).toEqual([longId, 'beta']);
  await page.locator('[data-action="run-project"][data-command="stop"]').first().click();
  await expect.poll(async () => (await api('/runs/' + runId)).status).toBe('cancelled');

  // Selection/deletion affect one program. New programs start disabled with no
  // output ownership, so adding one does not conflict with the existing pair.
  await page.locator('.rail-link[data-route="controls"]').click();
  await page.locator('[data-action="add-control-program"]').click();
  await page.getByRole('dialog').getByLabel('脚本标识').fill('gamma');
  await page.getByRole('dialog').getByLabel('脚本名称').fill('备用控制');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.getByLabel('选择控制脚本')).toHaveValue('gamma');
  expect(selectedProject(await save()).controlScripts).toHaveLength(3);
  await page.locator('[data-action="remove-control-program"]').click();
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  const afterDelete = selectedProject(await save());
  expect(afterDelete.controlScripts).toEqual(edited.controlScripts);

  // Legacy Lua remains editable and disabled, alongside the other Python
  // programs. Choosing Python preserves its text for deliberate migration.
  const legacy = await save(); legacy.dirty = true;
  const legacyOwner = selectedProject(legacy);
  legacyOwner.control = '-- preserved legacy script'; delete legacyOwner.controlLanguage;
  await page.evaluate(({key, data}) => localStorage.setItem(key, JSON.stringify(data)), {key: storageKey, data: legacy});
  await page.reload(); await ready();
  await expect(page.getByLabel('项目控制脚本')).toHaveValue('-- preserved legacy script');
  await expect(page.locator('[data-control-enabled]')).toBeDisabled();
  const legacySaved = selectedProject(await save());
  expect(legacySaved.controlPrograms).toHaveLength(2);
  expect(legacySaved.controlScripts.map(script => script.id)).toEqual(['beta']);
  await page.getByLabel('脚本语言').selectOption('python');
  await expect(page.getByLabel('项目控制脚本')).toHaveValue('-- preserved legacy script');
  await expect(page.locator('[data-control-enabled]')).not.toBeChecked();

  // The shared list operations reject a seventeenth script without truncating.
  const capacity = await page.evaluate(() => {
    const owner = {controlPrograms: []}, controls = window.FluidNetControls;
    for (let i = 0; i < 16; i++) controls.add(owner, 'item_' + i, 'Script ' + i);
    let error;
    try { controls.add(owner, 'overflow', 'Overflow'); } catch (failure) { error = failure.message; }
    return {count: owner.controlPrograms.length, error};
  });
  expect(capacity.count).toBe(16); expect(capacity.error).toContain('16');

  // A real module-version upgrade must preserve every program and editor name,
  // including the selected program when its id is not the legacy "control".
  await page.goto(base + '/#modules');
  await page.locator('[data-module-id="programmable_valve"] [data-action="module-example"]').click();
  const example = selectedProject(await save()), projectId = example.id;
  await page.locator('.rail-link[data-route="controls"]').click();
  await page.getByLabel('控制执行超时').fill('3'); await page.getByLabel('控制执行超时').blur();
  await page.locator('[data-action="add-control-program"]').click();
  await page.getByRole('dialog').getByLabel('脚本标识').fill('observer');
  await page.getByRole('dialog').getByLabel('脚本名称').fill('升级后保留的观察器');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await page.getByLabel('控制执行超时').fill('11'); await page.getByLabel('控制执行超时').blur();
  await page.locator('[data-action="add-control-program"]').click();
  await page.getByRole('dialog').getByLabel('脚本标识').fill('empty_draft');
  await page.getByRole('dialog').getByLabel('脚本名称').fill('待编写的空草稿');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await page.getByLabel('项目控制脚本').fill('');
  await page.getByLabel('控制执行超时').fill('13'); await page.getByLabel('控制执行超时').blur();
  await select('observer');
  const beforeUpgrade = selectedProject(await save());
  expect(beforeUpgrade.controlPrograms).toHaveLength(3);
  expect(beforeUpgrade.controlScripts).toHaveLength(2);
  const pinned = beforeUpgrade.moduleSnapshots.programmable_valve.version;
  const latest = Math.max(...(await api('/modules/programmable_valve/versions')).versions.map(item => Number(item.package.version.split('.')[0])));
  const {module} = await api('/modules/programmable_valve/versions/' + pinned);
  module.content_hash = null; module.definition_hash = null;
  module.parameters.push({id: 'control_test_gain', label: '控制回归增益', value_type: 'number', default: 2});
  await api('/modules/versions', {module, expected_latest_version: latest, release_notes: 'Control-program preservation regression'});
  await page.locator('.rail-link[data-route="workbench"]').click();
  await page.locator('[data-action="wf-upgrades"]').click();
  await page.locator('[data-action="wf-module-versions"]').click();
  await page.locator(`[data-action="wf-preview-upgrade"][data-version="${latest + 1}"]`).click();
  await expect(page.getByRole('dialog')).toContainText('兼容检查通过');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('#toast')).toContainText('模块版本已更新并保存');
  const upgraded = (await api('/projects/' + projectId)).document.project;
  expect(upgraded.controlScripts.map(program => program.id)).toEqual(['control', 'observer']);
  expect(upgraded.controlScripts.map(program => program.timeout_s)).toEqual([3, 11]);
  expect(upgraded.controlScripts.map(program => program.source)).toEqual(beforeUpgrade.controlScripts.map(program => program.source));
  expect(upgraded.controlPrograms[1].name).toBe('升级后保留的观察器');
  expect(upgraded.controlPrograms.find(program => program.id === 'empty_draft')).toMatchObject({
    name: '待编写的空草稿', source: '', enabled: false, timeout_s: 13
  });
  await page.reload(); await ready();
  await page.locator('.rail-link[data-route="controls"]').click();
  await expect(page.getByLabel('选择控制脚本')).toHaveValue('observer');
  await expect(page.getByLabel('控制程序名称')).toHaveValue('升级后保留的观察器');
  await expect(page.getByLabel('控制执行超时')).toHaveValue('11');
  await select('empty_draft');
  await expect(page.getByLabel('项目控制脚本')).toHaveValue('');
  await expect(page.getByLabel('控制程序名称')).toHaveValue('待编写的空草稿');
  await expect(page.getByLabel('控制执行超时')).toHaveValue('13');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({scripts: 2, importedIdLength: longId.length, runId, capacity: capacity.count, errors}));
} catch (error) {
  mkdirSync('artifacts', {recursive: true});
  await page.screenshot({path: 'artifacts/control-programs-failure.png', fullPage: true}).catch(() => {});
  throw error;
} finally {
  if (runId) await api(`/runs/${runId}/command`, {action: 'stop'}).catch(() => {});
  await browser.close(); await fixture.close();
}
