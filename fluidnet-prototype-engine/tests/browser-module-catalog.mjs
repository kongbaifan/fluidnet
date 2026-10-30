import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';
import { testServer } from './browser-server.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';

// 8 个倍思鹿参考模块必须由 /api/v1/modules 自动发现并渲染进模块目录。
const CATEGORY = '倍思鹿参考模块';
const MODULES = [
  ['pipe_fitting', 'GitBranch'],
  ['check_valve', 'ArrowRightLeft'],
  ['fan_coil_unit', 'Wind'],
  ['cooling_tower', 'Sun'],
  ['fan', 'Wind'],
  ['pump_variable_speed', 'Gauge'],
  ['capillary_tube', 'Minus'],
  ['valve_equal_percentage', 'SlidersHorizontal'],
];

const fixture = await testServer();
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ ...FHD_CONTEXT });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(fixture.base + '/#modules');
  await expect(page.locator('#app-header')).toContainText(/v\d+\.\d+\.\d+/);

  const nav = page.locator(`[data-action="module-category"][data-value="${CATEGORY}"]`);
  await expect(nav).toBeVisible({ timeout: 15000 });
  await expect(nav.locator('small')).toHaveText('8');

  await nav.click();
  await expect(page.locator('#module-results')).toBeVisible();
  await expect(page.locator('.module-reference-note')).toContainText('L1/L2/L3');

  const cards = page.locator('#module-results article.module-card');
  await expect(cards).toHaveCount(8);
  const ids = await cards.evaluateAll(items => items.map(item => item.dataset.moduleId).sort());
  expect(ids).toEqual(MODULES.map(([id]) => id).sort());

  for (const [id, icon] of MODULES) {
    const card = page.locator(`[data-module-id="${id}"]`);
    await expect(card).toContainText('参考模块');
    await expect(card.locator('.stat-line')).toContainText(/\d+ 个参数/);
    await expect(card.locator('.stat-line')).toContainText(/\d+ 个端口/);
    await expect(card.locator('.stat-line')).toContainText(/\d+ 条通路/);
    await expect(card.locator('.stat-line')).toContainText(/\d+ 个变量/);
    const slug = icon.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
    await expect(card.locator('.object-icon svg')).toHaveClass(new RegExp(`lucide-${slug}`));
  }

  const pipeFitting = page.locator('[data-module-id="pipe_fitting"]');
  await expect(pipeFitting.locator('.stat-line')).toContainText('4 个参数');
  await pipeFitting.locator('[data-action="module-doc"]').click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('#dialog-title')).toContainText('管道管件');
  await expect(dialog.locator('#dialog-title')).toContainText('v1');
  await expect(dialog.locator('#dialog-title')).toContainText(CATEGORY);
  await expect(dialog.locator('.module-doc-hint')).toContainText('docs/MODULE_KIT.md');

  const tables = dialog.locator('table');
  await expect(tables).toHaveCount(4);
  await expect(tables.nth(0).locator('thead')).toContainText('单位 / value_type');
  await expect(tables.nth(0)).toContainText('diameter_m');
  await expect(tables.nth(1)).toContainText('in0');
  await expect(tables.nth(2)).toContainText('state.throughput_kg');
  await expect(tables.nth(2)).toContainText('derived');
  await expect(tables.nth(3)).toContainText('resistance');
  await expect(tables.nth(3)).toContainText('valve');

  // 说明弹窗只读：没有提交动作。
  await expect(dialog.locator('button[type="submit"]')).toHaveCount(0);
  await dialog.locator('[data-action="close-dialog"]').first().click();
  await expect(dialog).toHaveCount(0);

  mkdirSync('artifacts', { recursive: true });
  await captureFhd(page, 'artifacts/module-catalog.png');

  expect(errors).toEqual([]);
  console.log(JSON.stringify({ category: CATEGORY, count: ids.length, modules: ids, errors }, null, 2));
} catch (error) {
  mkdirSync('artifacts', { recursive: true });
  await captureFhd(page, 'artifacts/module-catalog-failure.png');
  console.error('Browser errors:', errors);
  throw error;
} finally {
  await browser.close();
  await fixture.close();
}
