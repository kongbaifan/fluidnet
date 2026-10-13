import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { execFileSync, spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';

// Token-protected server: the page asks for a token, keeps it for the tab, and the API tab
// sends a real authenticated read of the running project.
const dir = mkdtempSync(join(tmpdir(), 'fluidnet-auth-'));
const env = { ...process.env, FLUIDNET_MODULE_STORE: join(dir, 'modules'), FLUIDNET_TOKEN_FILE: join(dir, 'tokens.json') };
const created = execFileSync('python', ['-m', 'fn_engine', 'token', 'create', 'browser', '--scope', 'control'], { cwd: resolve('.'), env, encoding: 'utf8' });
const token = created.trim().split(/\r?\n/).at(-1);
const socket = createServer(); socket.listen(0, '127.0.0.1'); await once(socket, 'listening');
const port = socket.address().port; await new Promise(resolve => socket.close(resolve));
const base = `http://127.0.0.1:${port}`;
let server, serverLog = '';
async function startServer() {
  server = spawn('python', ['-m', 'fn_engine', 'serve', '--host', '127.0.0.1', '--port', String(port), '--auth', 'required'], {
    cwd: resolve('.'), windowsHide: true, env, stdio: ['ignore', 'ignore', 'pipe'] });
  server.stderr.on('data', chunk => serverLog += chunk);
  await expect.poll(async () => { try { return (await fetch(base + '/api/v1/health')).ok; } catch { return false; } }, { timeout: 15000 }).toBe(true);
}
async function stopServer() { if (server && server.exitCode === null) { const exited = once(server, 'exit'); server.kill(); await exited; } }

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = []; page.on('pageerror', e => errors.push(e.message));

try {
  await startServer();
  expect((await fetch(base + '/api/v1/catalog')).status).toBe(401);
  await page.goto(base);
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('输入访问令牌');
  await dialog.locator('input[name="token"]').fill('fn_wrong');
  await dialog.locator('button[type="submit"]').click();
  await expect(page.getByRole('dialog')).toContainText('令牌无效或已撤销');
  await page.getByRole('dialog').locator('input[name="token"]').fill(token);
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('#app-header')).toContainText(/v\d+\.\d+\.\d+/);
  await expect(page.locator('body')).toContainText('计算服务 v');

  await page.locator('[data-action="start-modeling"]').first().click();
  const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/runs') && r.request().method() === 'POST');
  await page.locator('[data-action="run-project"][data-command="step"]').first().click();
  const runId = (await (await response).json()).run_id;
  expect(runId).toBeTruthy();
  await page.locator('.rail-link[data-route="connections"]').click();
  await page.locator('[data-action="connection-tab"][data-value="api"], [data-value="api"]').first().click();
  await expect(page.locator('#api-path')).toContainText(`/api/v1/runs/${runId}/variables`);
  await expect(page.locator('#api-request')).toContainText('Authorization: Bearer');
  await expect.poll(async () => {
    await page.locator('[data-action="api-preview"]').click();
    return page.locator('#api-response').textContent();
  }, { timeout: 15000 }).toContain('"V1.param.opening_ratio"');
  await expect(page.locator('#api-response')).toContainText('"status": 200');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({ runId, errors }));
} catch (error) {
  mkdirSync('artifacts', { recursive: true }); await page.screenshot({ path: 'artifacts/auth-failure.png', fullPage: true });
  console.error(serverLog.slice(-1500), errors); throw error;
} finally { await browser.close(); await stopServer(); }
