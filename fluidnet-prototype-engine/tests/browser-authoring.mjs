import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';

// Dedicated store/server: acceptance must not add test versions to a user's library.
const store=mkdtempSync(join(tmpdir(),'fluidnet-authoring-'));
const socket=createServer(); socket.listen(0,'127.0.0.1'); await once(socket,'listening');
const port=socket.address().port; await new Promise(resolve=>socket.close(resolve));
const base=`http://127.0.0.1:${port}`;
let server, serverLog='';
async function startServer() {
  server=spawn('python',['-m','fn_engine','serve','--host','127.0.0.1','--port',String(port)],{
    cwd:resolve('.'),windowsHide:true,env:{...process.env,FLUIDNET_MODULE_STORE:store},stdio:['ignore','ignore','pipe']});
  server.stderr.on('data',chunk=>serverLog+=chunk);
  await expect.poll(async()=>{try{return (await fetch(base+'/api/v1/health')).ok;}catch{return false;}},{timeout:15000}).toBe(true);
}
async function stopServer() { if(server && server.exitCode===null){const exited=once(server,'exit');server.kill();await exited;} }
const browser=await chromium.launch({channel:'msedge',headless:true});
let page=await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];
const watch=p=>p.on('pageerror',e=>errors.push(e.message)); watch(page);
const localState=async()=>{
  await page.locator('[data-action="save"]').first().click();
  return page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
};
// The prototype re-renders the whole rail on every state change, which can swallow a click
// that lands mid-render; retry the navigation until the module page is actually up.
const modules=()=>expect(async()=>{
  await page.locator('.rail-link[data-route="modules"]').click();
  await expect(page.locator('[data-action="new-module"]')).toBeVisible({timeout:2000});
}).toPass({timeout:20000});
const card=()=>page.locator('[data-module-id="authoring_valve"]');
const edit=async()=>{await expect(async()=>{
  await modules();
  await card().locator('[data-action="edit-module"]').click();
  await expect(page.locator('[data-action="editor-tab"]').first()).toBeVisible({timeout:2000});
}).toPass({timeout:20000});};
const tab=name=>page.locator(`[data-action="editor-tab"][data-value="${name}"]`).first().click();
async function saveVersion() {
  const response=page.waitForResponse(r=>r.url().endsWith('/modules/versions') && r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();
  const r=await response; const release=await r.json();
  expect(r.status(),JSON.stringify(release)).toBe(201);
  await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
  return release;
}
async function runProject() {
  const response=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/runs') && r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const queued=await (await response).json();
  await expect.poll(async()=> (await (await page.request.get(base+'/api/v1/runs/'+queued.run_id)).json()).status,{timeout:20000}).toBe('completed');
  await expect(page.locator('[data-result-status]').first()).toContainText('t = 1.0 s',{timeout:10000});
  const state=await localState();
  return state.projects.find(p=>p.id===state.activeProject);
}
try {
  await startServer();
  await page.goto(base+'/#modules');
  await expect(page.locator('[data-module-id="programmable_valve"]')).toBeVisible();
  await page.locator('[data-action="new-module"]').click();
  await page.locator('#dialog-form [name="name"]').fill('版本验收阀门');
  await page.locator('#dialog-form [name="code"]').fill('AUTHORING_VALVE');
  await page.locator('#dialog-form button[type="submit"]').click();
  const source=await page.locator('#module-code').inputValue();
  const algorithm=source.replace('kv=ctx.parameter("kv_m3_h")','kv=ctx.parameter("kv_m3_h") * ctx.parameter("gain")')
    .replace('        ctx.var("opening_ratio"','        ctx.var("gain", ctx.parameter("gain"))\n        ctx.var("opening_ratio"');
  await page.locator('#module-code').fill(algorithm);
  await tab('attributes');
  await page.locator('[data-action="edit-contract-item"][data-section="parameters"]').filter({hasText:'新增参数'}).click();
  await page.locator('#dialog-form [name="id"]').fill('gain');
  await page.locator('#dialog-form [name="label"]').fill('流量校正系数');
  await page.locator('#dialog-form [name="default"]').fill('1.2');
  await page.locator('#dialog-form [name="minimum"]').fill('0.1');
  await page.locator('#dialog-form [name="maximum"]').fill('3');
  await page.locator('#dialog-form button[type="submit"]').click();
  await page.locator('[data-action="edit-contract-item"][data-section="variables"]').filter({hasText:'新增输出'}).click();
  await page.locator('#dialog-form [name="id"]').fill('gain');
  await page.locator('#dialog-form [name="label"]').fill('当前校正系数');
  await page.locator('#dialog-form button[type="submit"]').click();
  await tab('contract');
  const contract=JSON.parse(await page.locator('[data-module-contract]').inputValue());
  contract.parameters[0].default=2;
  contract.ports[0].label='验收入口';
  await page.locator('[data-module-contract]').fill(JSON.stringify(contract,null,2));
  await page.locator('[data-action="validate-module-contract"]').click();
  await expect(page.locator('#module-output')).toContainText('默认值超出声明范围');
  expect((await (await page.request.get(base+'/api/v1/modules/authoring_valve/versions')).json()).versions).toEqual([]);
  contract.parameters[0].default=.6;
  await page.locator('[data-module-contract]').fill(JSON.stringify(contract,null,2));
  await page.locator('[data-action="validate-module-contract"]').click();
  await expect(page.locator('#module-output')).toContainText('Worker 入口与四阶段方法通过');
  // Boolean, text and curve parameters are authored through the same contract dialog.
  const addParam=async(id,label,type,value)=>{
    await tab('attributes');
    await page.locator('[data-action="edit-contract-item"][data-section="parameters"]').filter({hasText:'新增参数'}).click();
    await page.locator('#dialog-form [name="id"]').fill(id);
    await page.locator('#dialog-form [name="label"]').fill(label);
    await page.locator('#dialog-form [name="value_type"]').selectOption(type);
    await page.locator('#dialog-form [name="default"]').fill(value);
    await page.locator('#dialog-form button[type="submit"]').click();
  };
  await addParam('enabled_flag','启用标记','boolean','true');
  await addParam('tag','工况标签','text','验收');
  await addParam('samples','采样曲线','curve','[[0, 1], [1, 0.5]]');
  await tab('contract');
  await expect(page.locator('[data-module-contract]')).toHaveValue(/"value_type": "curve"/);
  await page.locator('[data-release-notes]').fill('新增校正参数与输出变量，完成首个版本');
  await page.locator('[data-action="test-module"]').click();
  await expect(page.locator('[data-bench-param="gain"]')).toHaveValue('1.2');
  await page.locator('[data-action="run-bench"][data-command="run"]').click();
  await expect(page.locator('[data-bench-commits]')).toHaveText('1',{timeout:15000});
  await edit(); await tab('contract');
  const v1=await saveVersion();
  expect(v1.module.version).toBe(1);
  expect(v1.test_result.evaluation.variables.gain).toBe(1.2);
  mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:'artifacts/module-authoring.png',fullPage:true});
  await modules(); await card().locator('[data-action="module-example"]').click();
  const original=await runProject();
  expect(original.pages[0].nodes.find(n=>n.id==='V1').package.version).toBe('1.0.0');
  const oldFlow=original.run.history.at(-1).canonical['V1.mass_flow_kg_s'];

  // Every declared parameter type is editable in the device panel and applies through one draft.
  await page.locator('[data-node="V1"]').dblclick();
  await expect(page.locator('[data-instance-param="enabled_flag"][data-param-type="boolean"]')).toBeChecked();
  await expect(page.locator('[data-instance-param="tag"][data-param-type="text"]')).toHaveValue('验收');
  await expect(page.locator('[data-instance-param="samples"][data-param-type="curve"]')).toHaveValue('[[0,1],[1,0.5]]');
  await page.locator('[data-instance-param="tag"]').fill('隔离工况');
  await expect(page.locator('[data-pending-for]').first()).toContainText('1 项待应用');
  await page.locator('[data-action="apply-instance"]').first().click();
  await expect(page.getByRole('dialog')).toContainText('隔离工况');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  const applied=await localState();
  const appliedNode=applied.projects.find(p=>p.id===applied.activeProject).pages[0].nodes.find(n=>n.id==='V1');
  expect(appliedNode.params.tag).toBe('隔离工况');
  expect(appliedNode.params.enabled_flag).toBe(true);
  expect(appliedNode.params.samples).toEqual([[0,1],[1,0.5]]);
  await page.locator('[data-action="float-close"]').first().click();

  await edit(); await tab('code');
  // An invalid editing draft must not affect a project already bound to a release.
  await page.locator('#module-code').fill('invalid Python draft');
  await localState(); await page.goto(base+'/#workbench');
  expect((await runProject()).run.history.at(-1).canonical['V1.mass_flow_kg_s']).toBe(oldFlow);
  await edit(); await tab('code');
  await page.locator('#module-code').fill(algorithm.replace('kv=ctx.parameter','kv=2 * ctx.parameter').replaceAll('parameter("gain")','parameter("gain_v2")'));
  await tab('contract');
  const contractV2=JSON.parse(await page.locator('[data-module-contract]').inputValue());
  const gain=contractV2.parameters.find(p=>p.id==='gain');gain.id='gain_v2';gain.default=1.4;
  await page.locator('[data-module-contract]').fill(JSON.stringify(contractV2,null,2));
  const v2=await saveVersion();
  expect(v2.module.version).toBe(2);
  expect(v2.package.definition_hash).not.toBe(v1.package.definition_hash);
  await page.goto(base+'/#workbench');
  const preserved=await runProject();
  expect(preserved.run.history.at(-1).canonical['V1.mass_flow_kg_s']).toBe(oldFlow);
  expect(preserved.moduleSnapshots.authoring_valve.version).toBe(1);
  await modules(); await card().locator('[data-action="module-example"]').click();
  const updated=await runProject();
  expect(updated.pages[0].nodes.find(n=>n.id==='V1').package.version).toBe('2.0.0');
  expect(updated.run.history.at(-1).canonical['V1.mass_flow_kg_s']).toBeGreaterThan(oldFlow);

  // Restart the service and use a fresh browser context (no localStorage).
  await stopServer(); await startServer();
  await page.close(); page=await browser.newPage({viewport:{width:1600,height:1000}});watch(page);
  await page.goto(base+'/#modules');
  await expect(card()).toContainText('Python · v2');
  await card().locator('[data-action="edit-module"]').click();await tab('contract');
  await page.locator('[data-action="module-versions"]').click();
  await expect(page.locator('[data-action="load-module-version"]')).toHaveCount(2);
  await page.locator('[data-action="load-module-version"][data-version="1"]').click();
  await expect(page.locator('#announcement')).toContainText('已载入 v1');
  await modules();await card().locator('[data-action="module-example"]').click();
  const reproduced=await runProject();
  expect(reproduced.run.history.at(-1).canonical['V1.mass_flow_kg_s']).toBe(oldFlow);
  expect(errors).toEqual([]);
  console.log(JSON.stringify({versions:[v1.module.version,v2.module.version],oldFlow,newFlow:updated.run.history.at(-1).canonical['V1.mass_flow_kg_s'],restartReproduced:true,errors},null,2));
} catch(error) {
  mkdirSync('artifacts',{recursive:true});await page.screenshot({path:'artifacts/authoring-failure.png',fullPage:true});
  console.error('Browser errors:',errors,'Server:',serverLog.slice(-2500));throw error;
} finally {await browser.close();await stopServer();}
