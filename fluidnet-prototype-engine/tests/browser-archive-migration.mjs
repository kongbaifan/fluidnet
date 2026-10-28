import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';
import { chromium, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// 浏览器旧存档迁移验收（M1 收尾项）：
// 旧版本只把原型草稿写在 localStorage（fluidnet-prototype-engine-v1），没有服务器工作区。
// 本脚本模拟“旧版本地存档 + 新版本已保存的服务器工作区”，并按 ROADMAP 的顺序验收：
//   1) 生成含 Python 模块快照（content_hash/definition_hash）的旧存档写入 localStorage；
//   2) 重新打开页面：新版本保留 dirty 本地草稿，不静默覆盖；
//   3) 迁移前先在设置页“导出原型 JSON”保留原始导出（迁移前证据，之后必须逐字节不变）；
//   4) 点“载入服务器”载入服务器工作区，旧草稿备份到 -before-workspace；
//   5) 从保留的原始导出取出单项目文档，用“导入单项目”迁入服务器工作区；
//   6) 断言项目数量、模块双哈希、关键参数在浏览器 / 服务器 / 全新浏览器上下文恢复后一致，
//      且原始导出与 -before-workspace 备份未被破坏。
// 全程使用临时端口、临时数据目录和临时模块库，不触碰 8799 端口的现有服务。

const KEY = 'fluidnet-prototype-engine-v1';
const BEFORE_WORKSPACE = KEY + '-before-workspace';
const BEFORE_PROJECT = KEY + '-before-project';
const artifacts = join('artifacts', 'archive-migration');

const dir = mkdtempSync(join(tmpdir(), 'fluidnet-archive-migration-'));
const launched = await launchEngine({ args: ['--data-dir', join(dir, 'data')], env: { FLUIDNET_MODULE_STORE: join(dir, 'modules') } });
const base = launched.base;
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ ...FHD_CONTEXT, acceptDownloads: true });
const page = await context.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));

const sha256File = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const sha256Text = text => createHash('sha256').update(text, 'utf8').digest('hex');
const localState = () => page.evaluate(k => JSON.parse(localStorage.getItem(k) || 'null'), KEY);
const localText = key => page.evaluate(k => localStorage.getItem(k), key);
const ready = p => expect(p.locator('#app-header')).toContainText('模块平台 · v');
const api = async (path, body) => {
  const response = await fetch(base + '/api/v1' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw Error(await response.text());
  return response.json();
};
// 原型每次状态变化都会重绘导航；点击可能落在重绘间隙，按 browser-authoring 的做法重试到目标页出现。
const nav = async (route, marker) => {
  await expect(async () => {
    await page.locator(`.rail-link[data-route="${route}"]`).click();
    await expect(marker).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 20000 });
};
// 原型导出入口在“设置 → 保存与交换”页签，不在默认的项目属性页签。
const settingsStorage = async () => {
  await nav('settings', page.locator('[data-action="settings-tab"][data-value="storage"]'));
  await page.locator('[data-action="settings-tab"][data-value="storage"]').click();
  await expect(page.locator('[data-action="export"][data-format="prototype"]')).toBeVisible();
};
async function saveWorkspace() {
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/workspace' && r.request().method() === 'POST');
  await page.locator('[data-action="save"]').first().click();
  const result = await response;
  expect(result.status()).toBe(200);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
  return result;
}
const exportPrototype = async path => {
  const download = page.waitForEvent('download');
  await page.locator('[data-action="export"][data-format="prototype"]').click();
  await (await download).saveAs(path);
  return JSON.parse(readFileSync(path, 'utf8'));
};

try {
  mkdirSync(artifacts, { recursive: true });

  // 1. 先建立“新版本已保存的服务器工作区”基线：内置 3 个项目，修订 1。
  await page.goto(base + '/#projects');
  await ready(page);
  await saveWorkspace();
  const baseline = await api('/workspace');
  expect(baseline.revision).toBe(1);
  expect(baseline.data.projects).toHaveLength(3);
  const baselineIds = baseline.data.projects.map(p => p.id).sort();

  // 2. 常用操作“新建项目”：空白画布新建的项目应进入当前草稿和迁移前导出。
  await page.locator('[data-action="new-project"]').click();
  await page.locator('#dialog-form [name="name"]').fill('试用验收 · 空白画布');
  await page.locator('#dialog-form [name="template"]').selectOption('blank');
  await page.locator('#dialog-form button[type="submit"]').click();
  await expect(page.locator('.project-picker')).toContainText('试用验收 · 空白画布');

  // 3. 生成旧存档内容：内置 3 个项目 + 新建空白项目 + 一个绑定固定 Python 模块快照的项目。
  await nav('modules', page.locator('[data-module-id="programmable_valve"]'));
  await page.locator('[data-module-id="programmable_valve"] [data-action="module-example"]').click();
  await expect(page.locator('.project-picker')).toContainText('管网验收');
  await settingsStorage();
  const live = await exportPrototype(join(dir, 'live-prototype.json'));
  expect(live.projects).toHaveLength(5);
  expect(live.projects.some(p => p.name === '试用验收 · 空白画布'), '新建的空白项目应出现在导出中').toBe(true);
  const livePython = live.projects.find(p => p.moduleSnapshots?.programmable_valve);
  expect(livePython, '模块算例项目应固定 programmable_valve 快照').toBeTruthy();
  const snapshot = livePython.moduleSnapshots.programmable_valve;
  const contentHash = snapshot.manifest.content_hash;
  const definitionHash = snapshot.manifest.definition_hash;
  expect(contentHash, '快照应带 content_hash').toMatch(/^[0-9a-f]{64}$/);
  expect(definitionHash, '快照应带 definition_hash').toMatch(/^[0-9a-f]{64}$/);
  const pythonProjectId = livePython.id;

  // 4. 把导出改造成“旧版本地存档”：去掉新版本才有的字段，写入待核对的关键参数，dirty=true 模拟未保存草稿。
  const oldArchive = structuredClone(live);
  delete oldArchive.workspaceRevision;
  delete oldArchive.projectRevisions;
  delete oldArchive.projectSavedKeys;
  delete oldArchive.savedAt;
  delete oldArchive.format;
  oldArchive.dirty = true;
  const oldPython = oldArchive.projects.find(p => p.id === pythonProjectId);
  oldPython.name = '旧版存档 · 可编程阀门管网';
  const oldV1 = oldPython.pages[0].nodes.find(n => n.id === 'V1');
  expect(oldV1, '旧存档应含 V1 实例').toBeTruthy();
  oldV1.params.opening_ratio = 0.65;
  oldV1.params.kv_m3_h = 20;
  const oldArchiveText = JSON.stringify(oldArchive);
  const oldArchivePath = join(artifacts, 'old-browser-draft.json');
  writeFileSync(oldArchivePath, oldArchiveText);
  const oldArchiveHash = sha256File(oldArchivePath);

  // 5. 写入 localStorage 后重新打开：dirty 本地草稿应被保留，且此时还没有载入前备份。
  await page.evaluate(([k, text]) => localStorage.setItem(k, text), [KEY, oldArchiveText]);
  await page.reload();
  await ready(page);
  const retained = await localState();
  expect(retained.projects, '旧存档应被原样保留').toHaveLength(5);
  const retainedPython = retained.projects.find(p => p.id === pythonProjectId);
  expect(retainedPython.name).toBe('旧版存档 · 可编程阀门管网');
  expect(retainedPython.moduleSnapshots.programmable_valve.manifest.content_hash).toBe(contentHash);
  expect(retainedPython.pages[0].nodes.find(n => n.id === 'V1').params.opening_ratio).toBeCloseTo(0.65, 9);
  expect(await localText(BEFORE_WORKSPACE), '尚未载入服务器时不应有备份').toBeNull();

  // 6. 迁移前先保留原始导出：设置页“导出原型 JSON”下载迁移前的完整存档。
  await settingsStorage();
  const originalExportPath = join(artifacts, 'original-export-before-migration.json');
  const originalExport = await exportPrototype(originalExportPath);
  const originalExportHash = sha256File(originalExportPath);
  expect(originalExport.projects).toHaveLength(5);
  const originalPython = originalExport.projects.find(p => p.id === pythonProjectId);
  expect(originalPython.name).toBe('旧版存档 · 可编程阀门管网');
  expect(originalPython.moduleSnapshots.programmable_valve.manifest.content_hash).toBe(contentHash);
  expect(originalPython.moduleSnapshots.programmable_valve.manifest.definition_hash).toBe(definitionHash);
  expect(originalPython.pages[0].nodes.find(n => n.id === 'V1').params.opening_ratio).toBeCloseTo(0.65, 9);

  // 7. 载入服务器工作区：旧草稿先备份到 -before-workspace，再替换为服务器基线。
  await page.locator('[data-action="reload-workspace"]').click();
  await expect(page.getByRole('dialog')).toContainText('载入服务器工作区');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect.poll(async () => (await localText(BEFORE_WORKSPACE)) !== null, { timeout: 20000 }).toBe(true);
  await expect.poll(async () => (await localState())?.projects?.length, { timeout: 20000 }).toBe(3);
  const backupText = await localText(BEFORE_WORKSPACE);
  const backup = JSON.parse(backupText);
  expect(backup.projects, '载入前备份应保留 5 个旧项目').toHaveLength(5);
  const backupPython = backup.projects.find(p => p.id === pythonProjectId);
  expect(backupPython.name).toBe('旧版存档 · 可编程阀门管网');
  expect(backupPython.moduleSnapshots.programmable_valve.manifest.content_hash).toBe(contentHash);
  expect(backupPython.moduleSnapshots.programmable_valve.manifest.definition_hash).toBe(definitionHash);
  expect(backupPython.pages[0].nodes.find(n => n.id === 'V1').params.opening_ratio).toBeCloseTo(0.65, 9);
  // 原始导出与载入前备份的项目数据一致（导出仅多一个 format 字段）。
  expect(originalExport.projects).toEqual(backup.projects);
  const loaded = await localState();
  expect(loaded.projects.map(p => p.id).sort()).toEqual(baselineIds);
  expect((await api('/workspace')).revision).toBe(1);

  // 8. 单项目导入：从保留的原始导出取出 Python 项目，按 copy 模式导入服务器工作区。
  const used = new Set(originalPython.pages.flatMap(pg => pg.nodes.map(n => n.moduleId)));
  const project = {
    ...structuredClone(originalPython),
    moduleSnapshots: Object.fromEntries([...used].map(id => [id, structuredClone(originalPython.moduleSnapshots?.[id] ?? originalExport.modules.find(m => m.id === id))])),
  };
  const document = {
    format: 'fluidnet-project', schema: 1, project,
    modules: Object.values(project.moduleSnapshots).map(m => structuredClone(m)),
    models: structuredClone(originalExport.models.filter(m => used.has(m.moduleId))),
    charts: structuredClone((originalExport.charts?.extra || []).filter(c => c.projectId === project.id)),
  };
  const singleProjectPath = join(artifacts, 'single-project-from-old-export.json');
  writeFileSync(singleProjectPath, JSON.stringify(document, null, 2));

  await nav('projects', page.locator('[data-action="wf-import"]'));
  await page.locator('[data-action="wf-import"]').click();
  await page.locator('#wf-import-file').setInputFiles(singleProjectPath);
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('#toast')).toContainText('项目已导入');
  await expect.poll(async () => (await localState())?.projects?.length, { timeout: 20000 }).toBe(4);
  const migrated = await localState();
  const imported = migrated.projects.find(p => p.name === '旧版存档 · 可编程阀门管网 导入');
  expect(imported, 'copy 模式导入的项目应追加“导入”后缀').toBeTruthy();
  // copy 模式会重新生成项目 ID；只需保证它在迁移后的工作区里唯一、且不是服务器原有项目。
  expect(baselineIds).not.toContain(imported.id);
  expect(migrated.projects.filter(p => p.id === imported.id)).toHaveLength(1);
  const importedSnapshot = imported.moduleSnapshots.programmable_valve;
  expect(importedSnapshot.manifest.content_hash).toBe(contentHash);
  expect(importedSnapshot.manifest.definition_hash).toBe(definitionHash);
  const importedV1 = imported.pages[0].nodes.find(n => n.id === 'V1');
  expect(importedV1.params.opening_ratio).toBeCloseTo(0.65, 9);
  expect(importedV1.params.kv_m3_h).toBeCloseTo(20, 9);
  expect(importedV1.package.content_hash).toBe(contentHash);
  expect(importedV1.package.definition_hash).toBe(definitionHash);
  // 服务器上原有的 3 个项目没有被迁移改动。
  expect(migrated.projects.filter(p => p.id !== imported.id).map(p => p.id).sort()).toEqual(baselineIds);
  // 导入前的浏览器草稿也留有备份。
  const beforeProjectText = await localText(BEFORE_PROJECT);
  expect(beforeProjectText, '导入前应写入 -before-project 备份').toBeTruthy();
  const beforeProject = JSON.parse(beforeProjectText);
  expect(beforeProject.projects).toHaveLength(3);
  await expect(page.locator('.filterbar')).toContainText('4 个项目');

  // 9. 保存工作区：迁移结果写入服务器，修订 1 → 2。
  await saveWorkspace();
  const saved = await api('/workspace');
  expect(saved.revision).toBe(2);
  expect(saved.data.projects).toHaveLength(4);
  const serverProject = saved.data.projects.find(p => p.id === imported.id);
  expect(serverProject).toBeTruthy();
  expect(serverProject.moduleSnapshots.programmable_valve.manifest.content_hash).toBe(contentHash);
  expect(serverProject.moduleSnapshots.programmable_valve.manifest.definition_hash).toBe(definitionHash);
  expect(serverProject.pages[0].nodes.find(n => n.id === 'V1').params.opening_ratio).toBeCloseTo(0.65, 9);

  // 10. 迁移后、再次载入前：原始导出与载入前备份都必须保持原样。
  expect(sha256File(originalExportPath), '原始导出不应被迁移改写').toBe(originalExportHash);
  expect(await localText(BEFORE_WORKSPACE), '载入前备份不应被迁移改写').toBe(backupText);
  expect(sha256File(oldArchivePath), '落盘的旧存档证据不应变化').toBe(oldArchiveHash);

  // 11. 全新浏览器上下文（无任何本地草稿）从服务器恢复：证明迁移结果已持久化，而不只是浏览器内存。
  const fresh = await browser.newContext({ ...FHD_CONTEXT });
  const freshPage = await fresh.newPage();
  freshPage.on('pageerror', e => errors.push(e.message));
  await freshPage.goto(base + '/#projects');
  await ready(freshPage);
  await expect.poll(async () => freshPage.evaluate(k => JSON.parse(localStorage.getItem(k) || 'null')?.projects?.length, KEY), { timeout: 20000 }).toBe(4);
  const restored = await freshPage.evaluate(k => JSON.parse(localStorage.getItem(k) || 'null'), KEY);
  expect(restored.workspaceRevision).toBe(2);
  const restoredProject = restored.projects.find(p => p.id === imported.id);
  expect(restoredProject.moduleSnapshots.programmable_valve.manifest.content_hash).toBe(contentHash);
  expect(restoredProject.moduleSnapshots.programmable_valve.manifest.definition_hash).toBe(definitionHash);
  expect(restoredProject.pages[0].nodes.find(n => n.id === 'V1').params.opening_ratio).toBeCloseTo(0.65, 9);
  await fresh.close();

  // 12. 全新上下文载入没有改写原页面的载入前备份；原始导出仍逐字节一致。
  expect(await localText(BEFORE_WORKSPACE)).toBe(backupText);
  expect(sha256File(originalExportPath)).toBe(originalExportHash);
  expect(errors).toEqual([]);

  await captureFhd(page, join(artifacts, 'archive-migration.png'));
  const result = {
    projectCount: { oldArchive: oldArchive.projects.length, serverBaseline: baseline.data.projects.length, afterImport: migrated.projects.length, afterRestore: restored.projects.length },
    module: { id: 'programmable_valve', contentHash, definitionHash },
    keyParams: { 'V1.opening_ratio': 0.65, 'V1.kv_m3_h': 20 },
    revisions: { baseline: baseline.revision, afterMigrationSave: saved.revision },
    preserved: { originalExportSha256: originalExportHash, beforeWorkspaceSha256: sha256Text(backupText), oldArchiveSha256: oldArchiveHash },
    artifacts,
    errors,
  };
  writeFileSync(join(artifacts, 'migration-result.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  mkdirSync(artifacts, { recursive: true });
  await captureFhd(page, join(artifacts, 'archive-migration-failure.png')).catch(() => {});
  console.error('Browser errors:', errors, 'Server:', launched.log().slice(-2500));
  throw error;
} finally {
  await browser.close();
  await launched.stop();
}
