import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';

const dir=mkdtempSync(join(tmpdir(),'fluidnet-workspace-'));
const socket=createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');
const port=socket.address().port;await new Promise(done=>socket.close(done));
const base=`http://127.0.0.1:${port}`, key='fluidnet-prototype-engine-v1';
let server, log='', runId;
async function start(){
  server=spawn('python',['-m','fn_engine','serve','--port',String(port),'--data-dir',join(dir,'data')],{
    cwd:resolve('.'),windowsHide:true,env:{...process.env,FLUIDNET_MODULE_STORE:join(dir,'modules')},stdio:['ignore','pipe','pipe']});
  server.stdout.on('data',chunk=>log+=chunk);
  server.stderr.on('data',chunk=>log+=chunk);
  await expect.poll(async()=>{try{return (await fetch(base+'/api/v1/health')).ok;}catch{return false;}},{timeout:20000}).toBe(true);
}
async function stop(){if(server?.exitCode===null){const ended=once(server,'exit');server.kill();await ended;}}
const browser=await chromium.launch({channel:'msedge',headless:true});
let context=await browser.newContext({viewport:{width:1600,height:1100}}), page=await context.newPage();
const errors=[];
const watch=p=>p.on('pageerror',e=>errors.push(e.message));watch(page);
const ready=async p=>expect(p.locator('#app-header')).toContainText('模块平台 · v');
async function save(p){
  const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace' && r.request().method()==='POST');
  await p.locator('[data-action="save"]').first().click();
  const result=await response;
  await expect(p.locator('[data-save-status]')).not.toContainText('正在保存');
  return result;
}
const workspace=async()=>fetch(base+'/api/v1/workspace').then(r=>r.json());
try{
  await start();await page.goto(base+'/#controls');await ready(page);
  await expect(page.getByLabel('项目控制脚本')).toContainText('def initialize');
  await page.locator('[data-action="preview-control"]').click();
  await expect(page.locator('#control-output')).toContainText('预览成功');
  await expect(page.locator('#control-output')).toContainText('"V1.param.opening_ratio": 0.65');
  await page.locator('[data-control-enabled]').check();
  expect((await save(page)).status()).toBe(200);
  const first=await workspace();expect(first.revision).toBe(1);
  const draft=first.data.projects[0];expect(draft.controlEnabled).toBe(true);
  expect(draft.control).toContain('def step');

  // Both pages load revision 1. One saving cannot advance the other's revision.
  const stale=await context.newPage();watch(stale);await stale.goto(base+'/#controls');await ready(stale);
  await page.getByLabel('控制程序名称').fill('saved from first tab');
  expect((await save(page)).status()).toBe(200);
  await stale.getByLabel('控制程序名称').fill('stale tab draft');
  expect((await save(stale)).status()).toBe(409);
  await expect(stale.locator('[data-save-status]')).toContainText('保存失败');
  expect((await workspace()).data.projects[0].controlConfig.name).toBe('saved from first tab');
  await stale.reload();await ready(stale);
  await expect(stale.getByLabel('控制程序名称')).toHaveValue('stale tab draft');
  await stale.close();

  // Keep a failed-save draft and retry without consuming an extra revision.
  await page.getByLabel('控制程序名称').fill('retry after disk error');
  await page.route('**/api/v1/workspace',async route=>{
    if(route.request().method()==='POST')await route.fulfill({status:507,contentType:'application/json',body:JSON.stringify({detail:{message:'disk full'}})});
    else await route.continue();
  });
  expect((await save(page)).status()).toBe(507);
  await expect(page.locator('[data-save-status]')).toContainText('保存失败');
  expect((await workspace()).revision).toBe(2);
  await page.unroute('**/api/v1/workspace');expect((await save(page)).status()).toBe(200);
  expect((await workspace()).revision).toBe(3);

  await page.locator('.rail-link[data-route="curves"]').click();
  for(const variable of ['V1.EX0_FLOW','V1.OPENING']){
    await page.locator('[data-action="add-chart-variable"]').click();
    await page.getByRole('dialog').getByLabel('项目变量').selectOption(variable);
    await page.getByRole('dialog').locator('button[type="submit"]').click();
  }
  await page.locator('.rail-link[data-route="workbench"]').click();
  const created=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs' && r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="step"]').first().click();
  runId=(await (await created).json()).run_id;
  await expect.poll(async()=>{const r=await fetch(base+'/api/v1/runs/'+runId).then(r=>r.json());return r.status==='paused' && r.frame?.variables['V1.param.opening_ratio']===.65;},{timeout:20000}).toBe(true);
  await page.locator('.rail-link[data-route="controls"]').click();
  await expect(page.locator('#control-live')).toContainText('"V1.param.opening_ratio": 0.65');
  mkdirSync('artifacts',{recursive:true});await page.screenshot({path:'artifacts/workspace-controls.png',fullPage:true});
  await save(page);

  // A hard process termination, then a fresh browser with no localStorage.
  await stop();await context.close();await start();
  context=await browser.newContext({viewport:{width:1600,height:1100}});page=await context.newPage();watch(page);
  await page.goto(base+'/#controls');await ready(page);
  await expect(page.getByLabel('控制程序名称')).toHaveValue('retry after disk error');
  await expect(page.locator('[data-control-enabled]')).toBeChecked();
  const restored=await fetch(base+'/api/v1/runs/'+runId).then(r=>r.json());
  expect(restored.status).toBe('interrupted');expect(restored.persisted_rows).toBeGreaterThan(1);
  expect(restored.frame.variables['script.control.state.samples']).toBeGreaterThan(0);
  await page.locator('.rail-link[data-route="runs"]').click();
  await page.locator(`[data-action="open-archive"][data-id="${runId}"]`).click();
  await expect(page.locator('.run-details')).toContainText(runId);
  await expect(page.locator('.run-details')).toContainText('服务已重新启动');
  await page.locator('[data-action="record-curves"]').click();
  await expect(page.locator('#main-chart svg')).toBeVisible();
  await expect(page.locator('#extra-charts svg path.chart-line')).toHaveCount(2);
  for(const curve of await page.locator('#extra-charts svg path.chart-line').all())await expect(curve).toHaveAttribute('d',/L/);

  // Download a consistent backup through the UI and restore it to a new directory.
  await page.locator('[data-action="workspace-tools"]').click();
  await page.route('**/api/v1/workspace/backup',route=>route.fulfill({status:204}));
  await page.locator('[data-action="download-backup"]').click();
  await expect(page.locator('#toast')).toContainText('备份下载未返回 ZIP 文件');
  await page.unroute('**/api/v1/workspace/backup');
  const download=page.waitForEvent('download');
  const zipResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace/backup' && r.request().method()==='POST');
  await page.locator('[data-action="download-backup"]').click();
  const file=await download,backupPath=join(dir,'downloaded-backup.zip');await file.saveAs(backupPath);
  const zipReply=await zipResponse;
  expect(zipReply.status()).toBe(200);
  expect(readFileSync(backupPath).subarray(0,4)).toEqual(Buffer.from([0x50,0x4b,0x03,0x04]));
  const restoredResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace/restore');
  await page.locator('#workspace-backup-file').setInputFiles(backupPath);
  const restoredReply=await restoredResponse;expect(restoredReply.status()).toBe(200);
  await expect(page.getByRole('dialog')).toContainText('备份已恢复');
  await expect(page.getByRole('dialog')).toContainText('serve --data-dir');
  await page.getByRole('dialog').locator('[data-action="close-dialog"]').first().click();
  await page.locator('[data-action="workspace-tools"]').click();
  await page.locator('[data-action="restore-workspace-revision"][data-revision="1"]').click();
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect.poll(async()=> (await workspace()).revision).toBe(5);
  expect((await workspace()).data.projects[0].controlConfig.name).toBe(first.data.projects[0].controlConfig.name);

  // A pre-existing Lua draft is preserved and cannot be enabled accidentally.
  await page.evaluate(k=>{const data=JSON.parse(localStorage.getItem(k));data.projects[0].control='-- preserved legacy script';delete data.projects[0].controlLanguage;data.dirty=true;localStorage.setItem(k,JSON.stringify(data));},key);
  await page.goto(base+'/#controls');await page.reload();await ready(page);
  await expect(page.getByLabel('项目控制脚本')).toHaveValue('-- preserved legacy script');
  await expect(page.locator('[data-control-enabled]')).toBeDisabled();
  expect(errors).toEqual([]);
  mkdirSync('artifacts',{recursive:true});await page.screenshot({path:'artifacts/workspace-legacy.png',fullPage:true});
  console.log(JSON.stringify({runId,restart:'interrupted',conflict:409,saveFailure:507,errors}));
}catch(error){mkdirSync('artifacts',{recursive:true});await page.screenshot({path:'artifacts/workspace-failure.png',fullPage:true}).catch(()=>{});console.error(log.slice(-2500),errors);throw error;}
finally{await browser.close();await stop();}
