import { spawnSync, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import process from 'node:process';

const root = resolve(import.meta.dirname, '..');
const command = process.argv[2];
const args = process.argv.slice(3);
const env = { ...process.env, PYTHONPATH: [resolve(root, '.runtime/python'), root, process.env.PYTHONPATH || ''].join(process.platform === 'win32' ? ';' : ':'), PYTHONUTF8: '1' };
function run(exe, argv, options={}) {
  const r = spawnSync(exe, argv, { cwd: root, env, stdio: 'inherit', ...options });
  if (r.error) throw r.error;
  if (r.status !== 0) process.exit(r.status || 1);
}
const nodeBin = name => resolve(root, 'node_modules', name);
function buildWeb() {
  run(process.execPath, [nodeBin('typescript/bin/tsc'), '--noEmit', '-p', 'web/tsconfig.json']);
  run(process.execPath, [nodeBin('vite/bin/vite.js'), 'build', '--config', 'web/vite.config.ts']);
}
function testBrowser(argv=[]) {
  buildWeb();
  run(process.execPath, [nodeBin('@playwright/test/cli.js'), 'test', ...argv]);
}
if (command === 'check') {
  run('python', ['-m', 'compileall', '-q', 'fluidnet', 'scripts']);
  if (existsSync(resolve(root, 'web/tsconfig.json'))) run(process.execPath, [nodeBin('typescript/bin/tsc'), '--noEmit', '-p', 'web/tsconfig.json']);
} else if (command === 'test') {
  if (args.includes('--e2e')) testBrowser(args.filter(arg => arg !== '--e2e'));
  else {
    run('python', ['-m', 'pytest', ...args]);
    if (args.length === 0) testBrowser();
  }
} else if (command === 'build') {
  buildWeb();
  if (args.includes('--portable')) run('python', ['scripts/build_portable.py']);
} else if (command === 'smoke') {
  run('python', ['scripts/smoke_portable.py', ...args]);
} else if (command === 'preview') {
  run('python', ['scripts/launch.py', 'serve', ...args]);
} else if (command === 'dev') {
  const api = spawn('python', ['scripts/launch.py', 'serve', '--port', '8765'], { cwd: root, env, stdio: 'inherit' });
  const ui = spawn(process.execPath, [nodeBin('vite/bin/vite.js'), '--config', 'web/vite.config.ts'], { cwd: root, env, stdio: 'inherit' });
  process.on('SIGINT', () => { api.kill(); ui.kill(); process.exit(); });
} else {
  throw new Error(`Unknown task ${command}`);
}
