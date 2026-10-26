import {expect} from '@playwright/test';

// Exercise author-supplied expectations through the UI and the real module Worker.
export async function exerciseModuleAssertions(page, base, moduleId) {
  const edit = async () => {
    await page.locator('.rail-link[data-route="modules"]').click();
    await page.locator(`[data-module-id="${moduleId}"] [data-action="edit-module"]`).click();
    await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
  };
  const configure = () => page.locator('[data-action="configure-module-tests"]').click();
  const saveConfig = async () => {
    await page.locator('#dialog-form button[type="submit"]').click();
    await expect(page.locator('#dialog-form')).toHaveCount(0);
  };
  const run = async () => {
    const response = page.waitForResponse(r => r.url().endsWith('/modules/test-suite') && r.request().method() === 'POST');
    await page.locator('[data-action="module-test-suite"]').click();
    const received = await response;
    expect(received.status()).toBe(200);
    const result = await received.json();
    await expect(page.locator('[data-action="module-test-suite"]')).toBeEnabled();
    return result;
  };
  await edit();
  await configure();
  const forward = page.locator('[data-suite-case="0"]');
  await forward.locator('[data-suite-action="add-assertion"]').click();
  await forward.getByLabel('结果变量', {exact:true}).fill('D1.in0.pressure_pa');
  await forward.getByLabel('预期值', {exact:true}).fill('0');
  await forward.getByLabel('绝对容差', {exact:true}).fill('0.01');
  const zero = page.locator('[data-suite-case="2"]');
  await zero.locator('[data-suite-action="add-assertion"]').click();
  await zero.getByLabel('结果变量', {exact:true}).fill('D1.main.mass_flow_kg_s');
  await zero.getByLabel('预期值', {exact:true}).fill('0');
  await zero.getByLabel('绝对容差', {exact:true}).fill('1e-10');
  await saveConfig();
  const mismatch = await run();
  expect(mismatch.passed).toBe(false);
  expect(mismatch.cases[0].assertions[0].status).toBe('outside_tolerance');
  expect(mismatch.cases[0].assertions[0].actual).toBeCloseTo(250000, 2);
  expect(mismatch.cases[2].passed).toBe(true);
  await expect(page.locator('#module-output')).toContainText('绝对误差');
  await expect(page.locator('#module-output')).toContainText('✓ zero');
  await configure();
  await forward.getByLabel('预期值', {exact:true}).fill('250000');
  await saveConfig();
  const saved = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/workspace' && r.request().method() === 'POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await saved).status()).toBe(200);
  await page.reload();
  await expect(page.locator('[data-action="editor-tab"]').first()).toBeVisible();
  await edit();
  await configure();
  await expect(forward.getByLabel('预期值', {exact:true})).toHaveValue('250000');
  await expect(forward.getByLabel('绝对容差', {exact:true})).toHaveValue('0.01');
  await expect(zero.getByLabel('结果变量', {exact:true})).toHaveValue('D1.main.mass_flow_kg_s');
  await saveConfig();
  const correct = await run();
  expect(correct.passed, JSON.stringify(correct.cases.map(c => ({id:c.id, diagnostics:c.diagnostics, assertions:c.assertions})))).toBe(true);
  expect(correct.cases[0].input_hash).not.toBe(mismatch.cases[0].input_hash);
  console.log(JSON.stringify({moduleAssertions:{mismatchDetected:true, laterCaseExecuted:true, savedAndReloaded:true, correctedPassed:true}}));
}
