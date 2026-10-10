import { chromium, expect } from '@playwright/test';
import { strict as assert } from 'node:assert';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';

const output = resolve('.cache/studio-prototype-qa');
await mkdir(output, { recursive: true });
const checks = [], errors = [], context = vm.createContext({});
vm.runInContext(await readFile('output/visualizations/studio/python-code.js', 'utf8'), context);
vm.runInContext(await readFile('output/visualizations/studio/data.js', 'utf8'), context);
const api = vm.runInContext('({ initialState, legacyModuleSource, normalizePythonSource, pythonCodeIssue })', context);
const fixture = JSON.parse(JSON.stringify(api.initialState()));
const samples = fixture.modules.flatMap(m => [m.source.runtime, m.source.header, ...m.source.design]);
const syntax = spawnSync('python', ['-X', 'utf8', '-c', 'import ast,json,sys\nfor source in json.load(sys.stdin): ast.parse(source)\nprint("Python templates parsed successfully")'], { input: JSON.stringify(samples), encoding: 'utf8' });
assert.equal(syntax.status, 0, syntax.stderr || syntax.error?.message);
assert.equal(samples.length, 60);
for (const source of samples) assert.equal(api.pythonCodeIssue(source), '');
checks.push('All 60 built-in run/common/design templates pass Python ast.parse without executing module code');

for (const source of [
  '# unmatched comment ([{\ndef run():\n    return 12 // 3\n',
  '"""Documentation with ([{ and # comments\nacross lines."""\nvalue = {"a": [1, 2]}\n',
  "value = '''Apostrophes ' and brackets ) ] }'''\n",
  'path = r"C:\\temp\\data"\ntext = "# [ ("\n'
]) assert.equal(api.pythonCodeIssue(source), '');
assert.match(api.pythonCodeIssue('value = [1, 2)\n'), /第 1 行：括号不配对/);
assert.match(api.pythonCodeIssue('text = "unfinished\n'), /字符串未闭合/);
assert.match(api.pythonCodeIssue('text = """unfinished\n'), /字符串未闭合/);
assert.match(api.pythonCodeIssue('void Run() {}\n'), /旧版代码写法/);
checks.push('Python comments, triple-quoted strings, raw strings and floor division are accepted; unmatched brackets/quotes and legacy declarations are reported');

for (const m of fixture.modules) {
  m.source = JSON.parse(JSON.stringify(api.legacyModuleSource(m.kind, m.code)));
  delete m.sourceFormat;
}
const editedModule = fixture.modules.find(m => m.id === 'valve');
const editedSource = editedModule.source.runtime + '// user change: preserve this draft\n';
editedModule.source.runtime = editedSource;
const migration = JSON.parse(JSON.stringify(fixture));
for (const m of migration.modules) api.normalizePythonSource(m);
assert.equal(migration.modules.find(m => m.id === 'valve').source.runtime, editedSource);
assert.match(migration.modules.find(m => m.id === 'pump').source.runtime, /def run\(\):/);
assert.match(migration.modules.find(m => m.id === 'valve').source.header, /from dataclasses import dataclass/);
const once = JSON.stringify(migration);
for (const m of migration.modules) api.normalizePythonSource(m);
assert.equal(JSON.stringify(migration), once);
checks.push('Migration replaces only exact legacy defaults in each pane, preserves edited source and is idempotent');

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 768 }, acceptDownloads: true });
page.on('pageerror', e => errors.push(e.message));
const storageKey = 'fluidnet-studio-prototype-20261009-v1';
const click = (action, attrs = '') => page.locator(`[data-action="${action}"]${attrs}`).first().click();
try {
  await page.goto(pathToFileURL(resolve('output/visualizations/fluidnet-studio-prototype.html')).href + '#editor');
  await page.evaluate(({ key, data }) => localStorage.setItem(key, JSON.stringify(data)), { key: storageKey, data: fixture });
  await page.reload(); await click('editor-tab', '[data-value="code"]');
  await expect(page.locator('#module-code')).toHaveValue(editedSource);
  await expect(page.locator('#module-code-header')).toHaveValue(migration.modules.find(m => m.id === 'valve').source.header);
  await click('check-code', '[data-kind="runtime"]');
  await expect(page.locator('#code-output')).toContainText('已保留原文');
  const pythonDraft = '# 用户编辑的 Python\ndef run():\n    return {"opening": OPENING}\n';
  await page.locator('#module-code').fill(pythonDraft); await click('save'); await page.reload();
  await expect(page.locator('#module-code')).toHaveValue(pythonDraft);
  await click('compile-preview');
  await expect(page.locator('#code-output')).toContainText('Python 基础结构检查通过');
  await expect(page.locator('#code-output')).toContainText('未进行完整 Python 语法');
  await expect(page.locator('#code-output')).not.toContainText('×');
  checks.push('Browser restoration migrates untouched panes, preserves edited legacy code, and saves/reloads replacement Python drafts');

  await page.evaluate(() => location.hash = 'settings'); await click('settings-tab', '[data-value="storage"]');
  const [download] = await Promise.all([page.waitForEvent('download'), click('export', '[data-format="prototype"]')]);
  const exported = JSON.parse(await readFile(await download.path(), 'utf8'));
  assert.equal(exported.modules.find(m => m.id === 'valve').source.runtime, pythonDraft);
  assert.equal(exported.modules.find(m => m.id === 'valve').sourceFormat, 'python-v1');
  await click('import');
  await page.locator('input[type=file]').setInputFiles({ name: 'legacy-module-code.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(fixture)) });
  await expect(page.locator('#import-preview')).toContainText('3 个项目');
  await page.locator('#dialog-form button[type=submit]').click();
  await page.evaluate(() => location.hash = 'modules'); await click('edit-module', '[data-id="pump"]'); await click('editor-tab', '[data-value="code"]');
  await expect(page.locator('#module-code')).toHaveValue(migration.modules.find(m => m.id === 'pump').source.runtime);
  await expect(page.locator('.code-file-name')).toHaveText(['run.py', 'common.py', 'design1.py']);
  await click('compile-preview');
  await expect(page.locator('#code-output')).not.toContainText('×');
  await page.screenshot({ path: resolve(output, 'python-module-code-1366.png') });
  await click('theme'); await page.screenshot({ path: resolve(output, 'python-module-code-dark.png') });
  checks.push('JSON export retains Python and migration metadata; importing a legacy file updates the untouched pump example in the code page');
  expect(errors).toEqual([]);
} catch (error) {
  await page.screenshot({ path: resolve(output, 'python-code-failure.png') }); throw error;
} finally {
  await writeFile(resolve(output, 'python-code.json'), JSON.stringify({ checks, errors }, null, 2));
  console.log(JSON.stringify({ checks, errors }, null, 2));
  await browser.close();
}
