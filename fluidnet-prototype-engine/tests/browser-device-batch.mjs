import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const run=command=>page.locator(`[data-action="run-project"][data-command="${command}"]`).first();
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();};
const owner=s=>s.projects.find(p=>p.id===s.activeProject);
const nodes=s=>Object.fromEntries(owner(s).pages.flatMap(p=>p.nodes).filter(n=>n.id==='V1'||n.id==='V2').map(n=>[n.id,n]));
async function saved(){
  const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await pending).ok()).toBe(true);
  return page.evaluate(()=>window.FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
}
async function edit(value){
  await page.locator('[data-action="device-batch-edit"]').click();
  await page.getByLabel('批量设备模块',{exact:true}).selectOption('valve');await submit();
  await expect(page.getByLabel('选择设备 V1',{exact:true})).toBeChecked();
  await expect(page.getByLabel('选择设备 V2',{exact:true})).toBeChecked();
  await page.getByLabel('修改 阀门开度',{exact:true}).check();
  await page.getByLabel('批量 阀门开度',{exact:true}).fill(String(value));
  await submit();
}
async function step(){
  const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await run('step').click();const id=(await(await pending).json()).run_id;
  await expect.poll(async()=>(await api('/runs/'+id)).status,{timeout:20000}).toBe('paused');
  await expect(page.locator('#statusbar')).toContainText('已暂停');return id;
}
try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="start-modeling"]').first().click();
  // An unrelated Kv draft must survive a batch that edits opening only.
  const panel=page.locator('[data-float-id="V1"]');
  await panel.locator('[data-action="float-tab"][data-value="parameters"]').click();
  await panel.locator('input[type="number"][data-instance-param="kv"]').fill('19');
  await panel.locator('[data-action="float-close"]').click();
  const before=await saved(),main=owner(before).activePage;
  await edit(45);await expect(page.locator('[data-device-batch-preview]')).toContainText('V2');
  await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
  expect(nodes(await saved())).toEqual(nodes(before));
  // Same module across pages is selectable as one atomic group.
  await page.locator('[data-action="new-canvas"]').first().click();
  await page.getByRole('dialog').locator('[name="name"]').fill('第二阀组');await submit();
  const destination=owner(await saved()).activePage;
  await page.locator(`[data-action="canvas-tab"][data-id="${main}"]`).click();
  await page.locator('[data-node="V2"]').click();await page.locator('[data-action="move-device-page"][data-id="V2"]').click();
  await page.getByRole('dialog').locator('[name="page"]').selectOption(destination);await submit();
  await page.locator(`[data-action="canvas-tab"][data-id="${main}"]`).click();
  const id=await step(),eventsBefore=(await api('/runs/'+id+'/events')).events.filter(e=>e.command?.action==='write').length;
  await edit(45);await submit();await expect(page.getByRole('dialog')).toHaveCount(0);
  let state=await saved(),n=nodes(state);
  expect(n.V1.params.opening).toBe(45);expect(n.V2.params.opening).toBe(45);
  expect(n.V1.draft.kv).toBe(19);expect(n.V1.params.kv).toBe(nodes(before).V1.params.kv);
  const events=(await api('/runs/'+id+'/events')).events,writes=events.filter(e=>e.command?.action==='write');
  expect(writes).toHaveLength(eventsBefore+1);
  expect(writes.at(-1).command.values).toEqual({'V1.param.opening_ratio':.45,'V2.param.opening_ratio':.45});
  expect(events.some(e=>e.command_id===writes.at(-1).command_id&&e.command_status==='applied')).toBe(true);
  await run('step').click();await expect.poll(async()=>(await api('/runs/'+id)).frame.variables['V2.param.opening_ratio']).toBe(.45);
  await run('stop').click();await expect(run('stop')).toBeDisabled();
  // Frozen project control owns one selected parameter: reject every edit.
  await nav('controls');await page.locator('[data-control-enabled]').check();await nav('workbench');
  const controlled=await step(),blockedBefore=nodes(await saved());
  await edit(30);await expect(page.locator('#dialog-error')).toContainText(/接管/);
  await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
  expect(nodes(await saved())).toEqual(blockedBefore);
  expect((await api('/runs/'+controlled+'/events')).events.filter(e=>e.command?.action==='write')).toHaveLength(0);
  await run('stop').click();await expect(run('stop')).toBeDisabled();
  // Whole-model replacement keeps model provenance; overriding it becomes custom settings.
  await page.locator('[data-action="device-batch-edit"]').click();
  await page.getByLabel('批量设备模块',{exact:true}).selectOption('valve');await submit();
  await page.getByLabel('批量型号',{exact:true}).selectOption('valve-25');await submit();await submit();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  for(const value of Object.values(nodes(await saved()))){expect(value.modelId).toBe('valve-25');expect(value.params.kv).toBe(25);expect(value.params.opening).toBe(65);}
  await page.locator('[data-action="device-batch-edit"]').click();
  await page.getByLabel('批量设备模块',{exact:true}).selectOption('valve');await submit();
  await page.getByLabel('批量型号',{exact:true}).selectOption('valve-25');
  await page.getByLabel('修改 阀门开度',{exact:true}).check();await page.getByLabel('批量 阀门开度',{exact:true}).fill('50');await submit();
  await expect(page.getByRole('dialog')).toContainText('自定义参数');await submit();await expect(page.getByRole('dialog')).toHaveCount(0);
  for(const value of Object.values(nodes(await saved()))){expect(value.modelId).toBe(null);expect(value.params.kv).toBe(25);expect(value.params.opening).toBe(50);}
  state=await saved();await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  expect(nodes(await saved())).toEqual(nodes(state));
  await edit(50);await captureFhd(page,'artifacts/device-batch-preview.png');
  await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
  expect(errors).toEqual([]);console.log(JSON.stringify({cancelPreserved:true,crossPage:true,oneAtomicWrite:true,unselectedDraftPreserved:true,controlledBatchRejected:true,modelAndCustom:true,reload:true,errors}));
}catch(e){console.error(e);await captureFhd(page,'artifacts/device-batch-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
