import { chromium, expect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const output = resolve('.cache/studio-prototype-qa');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 768 }, acceptDownloads: true });
const errors = [], checks = [], layouts = [];
page.on('pageerror', e => errors.push(e.message));
const click = (action, attrs = '') => page.locator(`[data-action="${action}"]${attrs}`).first().click();
const nav = async route => {
  await page.evaluate(route => location.hash = route, route);
  await expect(page.locator(`.rail-link[data-route="${route}"]`)).toHaveClass(/active/);
};
const submit = () => page.locator('#dialog-form button[type="submit"]').click();
const group = name => page.locator('.module-group-list button').filter({ has: page.locator('span').filter({ hasText: new RegExp('^' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$') }) });
const selectGroup = name => group(name).click();
const addGroup = async name => {
  await click('new-module-group');
  await page.getByRole('textbox', { name: '分组名称', exact: true }).fill(name);
  await submit();
  await expect(page.locator('#dialog-form')).toHaveCount(0);
  await expect(group(name)).toHaveAttribute('aria-pressed', 'true');
};
const savedState = async () => {
  await click('save');
  return page.evaluate(() => JSON.parse(localStorage.getItem('fluidnet-studio-prototype-20261009-v1')));
};
const exportData = async format => {
  await nav(format === 'models' ? 'models' : 'settings');
  if (format !== 'models') await click('settings-tab', '[data-value="storage"]');
  const [download] = await Promise.all([page.waitForEvent('download'), click('export', `[data-format="${format}"]`)]);
  return JSON.parse(await readFile(await download.path(), 'utf8'));
};
const loadImport = async data => {
  await nav('settings'); await click('settings-tab', '[data-value="storage"]'); await click('import');
  await page.locator('input[type="file"]').setInputFiles({ name: 'groups.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(data)) });
  await expect(page.locator('#import-preview')).not.toContainText('请选择文件');
};
const importData = async data => {
  await loadImport(data);
  await expect(page.locator('#import-preview')).not.toContainText('检查失败');
  await submit(); await expect(page.locator('#dialog-form')).toHaveCount(0);
};
const references = data => ({ models: data.models, nodes: data.projects.map(p => p.pages.map(pg => pg.nodes)), ids: data.modules.map(m => m.id) });

try {
  await page.goto(pathToFileURL(resolve('output/visualizations/fluidnet-studio-prototype.html')).href + '#modules');
  const baseline = await savedState();
  await click('new-module-group');
  await page.getByRole('textbox', { name: '分组名称', exact: true }).fill('取消的新分组');
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(group('取消的新分组')).toHaveCount(0);
  await addGroup('冷却水系统');
  await expect(group('冷却水系统').locator('small')).toHaveText('0');
  await expect(page.locator('#module-results')).toContainText('分组已建好');
  await page.screenshot({ path: resolve(output, 'module-group-empty.png') });
  await click('new-module-group');
  for (const name of ['   ', '冷却水系统', '管道与阻力', '全部模块']) {
    await page.getByRole('textbox', { name: '分组名称', exact: true }).fill(name);
    await submit(); await expect(page.locator('#dialog-error')).toBeVisible();
    await expect(group('冷却水系统')).toHaveCount(1);
  }
  await click('close-dialog');
  await savedState(); await page.reload();
  await selectGroup('冷却水系统');
  await expect(page.locator('#module-results')).toContainText('分组已建好');
  checks.push('Add/cancel, duplicate and blank-name validation, empty-group counts and saved reload');

  await page.getByRole('button', { name: '在此分组新建模块', exact: true }).click();
  await expect(page.getByRole('combobox', { name: '所属分组' })).toHaveValue('冷却水系统');
  await page.getByRole('textbox', { name: '模块名称', exact: true }).fill('冷却水调节阀');
  await page.getByRole('textbox', { name: '模块标识', exact: true }).fill('COOLING_VALVE');
  await submit();
  await nav('modules');
  await expect(group('冷却水系统').locator('small')).toHaveText('1');
  await expect(page.locator('.module-card')).toHaveCount(1);
  await selectGroup('全部模块');
  await click('move-module-group', '[data-id="valve"]');
  await page.getByRole('combobox', { name: '所属分组' }).selectOption('冷却水系统');
  await submit();
  await expect(group('冷却水系统').locator('small')).toHaveText('2');
  await expect(page.locator('[data-action="delete-module-group"]')).toBeDisabled();
  await click('rename-module-group');
  await page.getByRole('textbox', { name: '分组名称', exact: true }).fill('循环冷却系统');
  await submit();
  await expect(group('冷却水系统')).toHaveCount(0);
  await expect(group('循环冷却系统').locator('small')).toHaveText('2');
  const renamed = await savedState();
  expect(renamed.modules.filter(m => m.category === '循环冷却系统')).toHaveLength(2);
  expect(references(renamed).models).toEqual(references(baseline).models);
  expect(references(renamed).nodes).toEqual(references(baseline).nodes);
  expect(renamed.modules.slice(0, baseline.modules.length).map(m => m.id)).toEqual(references(baseline).ids);
  await nav('workbench');
  await expect(page.locator('.library-caption').filter({ hasText: '循环冷却系统' })).toBeVisible();
  await expect(page.locator('[data-action="place-module"][data-id="valve"]')).toBeVisible();
  await nav('modules');
  await page.screenshot({ path: resolve(output, 'module-groups-1366.png') });
  checks.push('New module inherits selected group; moving and renaming preserve module IDs, model and project references');

  await addGroup('临时空分组');
  await selectGroup('循环冷却系统');
  await click('move-module-group', '[data-id="valve"]');
  await page.getByRole('combobox', { name: '所属分组' }).selectOption('临时空分组'); await submit();
  await expect(page.locator('[data-action="delete-module-group"]')).toBeDisabled();
  await click('move-module-group', '[data-id="valve"]');
  await page.getByRole('combobox', { name: '所属分组' }).selectOption('循环冷却系统'); await submit();
  await selectGroup('临时空分组');
  await click('delete-module-group'); await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(group('临时空分组')).toHaveCount(1);
  await click('delete-module-group'); await submit();
  await expect(group('临时空分组')).toHaveCount(0);
  await selectGroup('边界与节点');
  await expect(page.locator('[data-action="rename-module-group"],[data-action="delete-module-group"]')).toHaveCount(0);
  checks.push('Built-in categories protected; occupied group deletion disabled; empty deletion supports cancel/confirm');

  const literal = '冷却 "A" <测试> & 支路';
  await addGroup(literal);
  await selectGroup('全部模块'); await click('move-module-group', '[data-id="pump"]');
  await page.getByRole('combobox', { name: '所属分组' }).selectOption(literal); await submit();
  await expect(page.locator('.module-group-context h2')).toHaveText(literal);
  await nav('workbench');
  await expect(page.locator('.library-caption').filter({ hasText: literal })).toHaveText(literal);
  await nav('modules'); await addGroup('长期空分组');
  const snapshot = await exportData('prototype');
  expect(snapshot.moduleGroups).toEqual(expect.arrayContaining(['循环冷却系统', literal, '长期空分组']));
  const modelLibrary = await exportData('models');
  expect(modelLibrary.moduleGroups).toEqual(snapshot.moduleGroups);
  await nav('modules'); await selectGroup('长期空分组'); await click('delete-module-group'); await submit();
  await importData(snapshot); await nav('modules');
  await expect(group('长期空分组').locator('small')).toHaveText('0');
  await savedState(); await page.reload();
  await expect(group(literal).locator('small')).toHaveText('1');
  checks.push('Literal special-character names, full prototype and model-library exports preserve populated and empty groups');

  const beforeInvalid = await savedState();
  for (const groups of ['invalid', ['重复', '重复'], ['非法\n分组'], ['全部模块'], [null]]) {
    await loadImport({ ...snapshot, moduleGroups: groups });
    await expect(page.locator('#import-preview')).toContainText('检查失败');
    await submit(); await expect(page.locator('#dialog-error')).toBeVisible();
    await click('close-dialog');
    expect((await savedState()).moduleGroups).toEqual(beforeInvalid.moduleGroups);
  }
  const legacy = structuredClone(snapshot); delete legacy.moduleGroups;
  await importData(legacy); await nav('modules');
  await expect(group('循环冷却系统').locator('small')).toHaveText('2');
  await expect(group('长期空分组')).toHaveCount(0);
  const missingCategory = structuredClone(legacy); delete missingCategory.modules[0].category;
  await importData(missingCategory);
  expect((await savedState()).modules[0].category).toBe('自定义模块');
  await importData(snapshot);
  // Library merge uses fresh IDs, as duplicate model IDs intentionally reject import.
  const library = structuredClone(modelLibrary); library.models = []; library.moduleGroups = ['导入的空分组'];
  library.modules = [structuredClone(library.modules.find(m => m.id === 'valve'))];
  library.modules[0].id = 'imported_valve'; library.modules[0].code = 'IMPORTED_VALVE'; library.modules[0].category = '导入的模块分组';
  await importData(library); await nav('modules');
  await expect(group('导入的空分组').locator('small')).toHaveText('0');
  await expect(group('导入的模块分组').locator('small')).toHaveText('1');
  await expect(group('长期空分组').locator('small')).toHaveText('0');
  checks.push('Invalid group imports rejected atomically; legacy categories recovered; library merge retains old and new empty groups');

  await selectGroup('循环冷却系统');
  for (const width of [1366, 1024, 736, 320]) {
    await page.setViewportSize({ width, height: 768 });
    await page.locator('#page').evaluate(el => el.scrollTop = 0);
    await expect(page.locator('[data-action="new-module-group"]')).toBeInViewport();
    const layout = await page.evaluate(() => ({ width: innerWidth, outer: document.documentElement.scrollWidth, page: document.getElementById('page').clientWidth, content: document.getElementById('page').scrollWidth }));
    expect(layout.outer).toBeLessThanOrEqual(width + 1);
    expect(layout.content).toBeLessThanOrEqual(layout.page + 1);
    layouts.push(layout);
    await page.screenshot({ path: resolve(output, `module-groups-${width}.png`) });
  }
  // Exercise creation at the narrowest size, not only desktop resizing.
  await addGroup('手机新增分组');
  await expect(page.locator('.module-group-context h2')).toHaveText('手机新增分组');
  await page.setViewportSize({ width: 1366, height: 768 });
  await selectGroup('循环冷却系统'); await click('theme');
  await page.screenshot({ path: resolve(output, 'module-groups-dark.png') });
  checks.push('Visible add-group entry, horizontal category scrolling and no page overflow at 1366/1024/736/320 px; narrow creation and dark appearance');
  expect(errors).toEqual([]);
} catch (error) {
  await page.screenshot({ path: resolve(output, 'module-groups-failure.png') });
  throw error;
} finally {
  await writeFile(resolve(output, 'module-groups.json'), JSON.stringify({ checks, errors, layouts }, null, 2));
  console.log(JSON.stringify({ checks, errors, layouts }, null, 2));
  await browser.close();
}
