import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
const panel=()=>page.locator('[data-float-id="V1"]');
const run=action=>page.locator(`[data-action="run-project"][data-command="${action}"]`).first();
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();};
async function saved(){
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await posted).ok()).toBe(true);
  return page.evaluate(async () =>(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
}
const owner=s=>s.projects.find(p=>p.id===s.activeProject);
const node=s=>owner(s).pages.flatMap(p=>p.nodes).find(n=>n.id==='V1');
async function step(){
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await run('step').click();const id=(await(await posted).json()).run_id;
  await expect.poll(async()=>(await api('/runs/'+id)).status,{timeout:20000}).toBe('paused');
  await expect(page.locator('#statusbar')).toContainText('已暂停');return id;
}
async function bank(value){
  await panel().locator('[data-action="float-tab"][data-value="variables"]').click();
  await panel().locator('[data-instance-source-select]').selectOption('0');
  await panel().locator('[data-instance-value="param:opening"]').fill(String(value));
  await panel().locator('[data-action="apply-instance-bank"]').click();
  await page.getByRole('dialog').locator('button[type="submit"]').click();
}
try {
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="start-modeling"]').first().click();
  // Curve inputs parse on blur. Their apply control must refresh even when no number was edited.
  await panel().locator('[data-action="float-close"]').click();
  await page.locator('.net-node[data-node="P1"]').dblclick();
  const pump=page.locator('[data-float-id="P1"]'),curve=pump.locator('textarea[data-instance-param="head_curve"]');
  await pump.locator('[data-action="float-tab"][data-value="parameters"]').click();
  await pump.locator('.device-other-parameters > summary').click();
  await pump.locator('.pump-curve-json > summary').click();
  const points=[[0,21],[10,18],[20,12],[30,0]];
  await curve.fill(JSON.stringify(points));await curve.blur();
  await expect(pump.locator('[data-action="apply-instance"]')).toBeEnabled();
  await pump.locator('[data-action="apply-instance"]').click();
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  const pumpState=owner(await saved()).pages.flatMap(p=>p.nodes).find(n=>n.id==='P1');
  expect(pumpState.params.head_curve).toEqual(points);
  await pump.locator('[data-action="float-close"]').click();
  await page.locator('[data-node="V1"]').dblclick();
  const first=await step();
  expect((await api('/runs/'+first)).request.project.instances.find(n=>n.id==='P1').parameters.head_curve).toEqual(points);
  await panel().locator('input[type="number"][data-instance-param="opening"]').fill('55');
  await bank(40);
  await expect(page.locator('#announcement')).toContainText('库值 1 已应用');
  let state=await saved();expect(node(state).params.opening).toBe(40);expect(node(state).draft.opening).toBe(40);
  const events=(await api('/runs/'+first+'/events')).events;
  const write=events.find(e=>e.command?.action==='write');
  expect(write,JSON.stringify(events)).toBeTruthy();
  expect(events.some(e=>e.command_id===write.command_id&&e.command_status==='applied')).toBe(true);
  await run('step').click();
  await expect.poll(async()=>(await api('/runs/'+first)).frame.variables['V1.param.opening_ratio']).toBe(.4);
  await run('stop').click();await expect(run('stop')).toBeDisabled();

  // The same bank path must honor the server's control ownership and keep every draft on rejection.
  await page.locator('.rail-link[data-route="controls"]').click();
  await page.locator('[data-control-enabled]').check();
  await page.locator('.rail-link[data-route="workbench"]').click();
  const controlled=await step();
  await page.locator('[data-node="V1"]').dblclick();
  await panel().locator('[data-action="float-tab"][data-value="variables"]').click();
  await panel().locator('[data-instance-source-select]').selectOption('-1');
  await panel().locator('[data-instance-value="param:opening"]').fill('55');
  const before=node(await saved());
  await bank(30);
  await expect(page.locator('#announcement')).toContainText(/控制|拥有/);
  state=await saved();expect(node(state).params).toEqual(before.params);expect(node(state).draft).toEqual(before.draft);
  expect(node(state).variableState.banks[0]['param:opening']).toBe(30);
  expect((await api('/runs/'+controlled)).frame.variables['V1.param.opening_ratio']).toBe(.65);
  await run('stop').click();await expect(run('stop')).toBeDisabled();

  // A new library release must not change the definition shown from a frozen project instance.
  await page.locator('.rail-link[data-route="modules"]').click();
  const card=page.locator('[data-module-id="programmable_valve"]');
  await card.locator('[data-action="module-example"]').click();
  await page.locator('[data-node="V1"]').dblclick();
  await panel().locator('[data-action="device-definition"]').first().click();
  const bound=page.locator('[data-bound-definition="programmable_valve"]');
  const version=Number(await bound.getAttribute('data-bound-version'));
  await expect(bound.locator('input,textarea')).toHaveCount(0);
  await bound.locator('[data-action="edit-device-library"]').click();
  await page.locator('[data-action="editor-tab"][data-value="code"]').first().click();
  const original=await page.locator('#module-code').inputValue();
  const marker='# library release after project binding';
  await page.locator('#module-code').fill(original+'\n'+marker+'\n');
  const published=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/modules/versions'&&r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();
  expect((await published).ok()).toBe(true);
  await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
  await page.locator('[data-action="return-device"]').click();
  await panel().locator('[data-action="device-definition"]').first().click();
  await expect(bound).toHaveAttribute('data-bound-version',String(version));
  await expect(bound).not.toContainText(marker);
  await expect(bound.locator('[data-action="edit-device-library"]')).toContainText('v'+(version+1));
  await bound.locator('[data-action="edit-device-library"]').click();
  await page.locator('[data-action="editor-tab"][data-value="code"]').first().click();
  await expect(page.locator('#module-code')).toHaveValue(new RegExp(marker));
  await page.locator('[data-action="return-device"]').click();
  await panel().locator('[data-action="float-tab"][data-value="variables"]').click();
  const variable=panel().locator('[data-instance-row="param:opening_ratio"]');
  await variable.locator('[data-action="device-definition"]').click();
  await expect(page.locator('[data-bound-variable="param:opening_ratio"]')).toBeVisible();
  await expect(bound).toHaveAttribute('data-bound-version',String(version));
  await captureFhd(page,'artifacts/device-bound-definition.png');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({curveOnlyApplied:true,bankWriteConfirmed:true,controlledBankRejected:true,boundVersion:version,libraryVersion:version+1,errors}));
}catch(error){console.error(error,errors);await captureFhd(page,'artifacts/device-transactions-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
