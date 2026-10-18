import { chromium, expect } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { launchEngine } from './browser-server.mjs';

// Dedicated store/server: acceptance must not add test versions to a user's library.
const store=mkdtempSync(join(tmpdir(),'fluidnet-authoring-'));
let server, port, base, serverLog='', launched;
async function startServer() {
  launched=await launchEngine({args:[],env:{FLUIDNET_MODULE_STORE:store}});
  ({server,port,base}=launched);
  serverLog=launched.log();
}
async function stopServer() { if(launched)await launched.stop(); }
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
const tab=async name=>{
  await expect(page.locator('.dialog-backdrop')).toHaveCount(0,{timeout:15000});
  await page.locator(`[data-action="editor-tab"][data-value="${name}"]`).first().click();
};
// 弹窗提交：界面在状态变化时会整体重绘，点击可能被吞掉。若弹窗没关闭就重试；
// 若弹窗内已显示校验错误则直接抛出错误文本，避免 30 秒盲等。
const submitDialog=()=>expect(async()=>{
  const backdrop=page.locator('.dialog-backdrop');
  if (await backdrop.count()===0) return;
  const error=page.locator('#dialog-error');
  if (await error.isVisible().catch(()=>false)) throw Error('弹窗校验失败：'+await error.textContent());
  await page.locator('#dialog-form button[type="submit"]').click({timeout:5000});
  await expect(backdrop).toHaveCount(0,{timeout:5000});
}).toPass({timeout:30000});
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
  await submitDialog();
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
  await submitDialog();
  await page.locator('[data-action="edit-contract-item"][data-section="variables"]').filter({hasText:'新增输出'}).click();
  await page.locator('#dialog-form [name="id"]').fill('gain');
  await page.locator('#dialog-form [name="label"]').fill('当前校正系数');
  await submitDialog();
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
    await submitDialog();
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
  // design.py derives Kv for one library-value set; nothing changes until the result is confirmed.
  await edit(); await tab('code');
  await page.locator('#module-code-design').fill('def design(ctx):\n    ctx.set("kv_m3_h", round(10.0 * ctx.parameter("gain"), 6))\n    ctx.log("Kv 由校正系数推算")\n');
  await tab('values');
  await page.locator('[data-action="bank-select"][data-value="1"]').click();
  await page.locator('[data-value-id="param:gain"][data-bank="1"]').fill('1.5');
  const designed=page.waitForResponse(r=>r.url().endsWith('/modules/design'));
  await page.locator('[data-action="preview-design"]').click();
  expect((await designed).status()).toBe(200);
  await expect(page.getByRole('dialog')).toContainText('Kv 由校正系数推算');
  await expect(page.getByRole('dialog').locator('.diff-table')).toContainText('15');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  const designedModule=(await localState()).modules.find(m=>m.id==='authoring_valve');
  expect(designedModule.banks[1]['param:kv_m3_h']).toBe(15);
  expect(designedModule.banks[0]['param:kv_m3_h']).toBe(16);
  expect(designedModule.values['param:kv_m3_h']).toBe(16);
  await edit(); await tab('contract');
  const v1=await saveVersion();
  expect(v1.module.version).toBe(1);
  expect(v1.module.source.design).toContain('def design(ctx)');
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
  await card().locator('[data-action="edit-module"]').click();
  await tab('code'); await expect(page.locator('#module-code-design')).toHaveValue(/def design\(ctx\)/);
  await tab('contract');
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
  console.error('Module cards:',await page.locator('[data-module-id]').evaluateAll(items=>items.map(x=>x.dataset.moduleId)));
  console.error('Browser errors:',errors,'Server:',serverLog.slice(-2500));throw error;
} finally {await browser.close();await stopServer();}
