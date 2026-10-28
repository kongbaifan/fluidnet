import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';
import {chromium,expect} from '@playwright/test';
import {mkdirSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {exerciseModuleAssertions} from './browser-module-assertions.mjs';
import {exerciseModuleAssertionBoundaries} from './browser-module-assertion-boundaries.mjs';

const server=await testServer();
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const results=[];
try{
  await page.goto(server.base+'/#modules');
  await expect(page.locator('[data-module-id="programmable_valve"]')).toBeVisible();
  for(const template of ['resistance','pump','heat_exchanger','managed_state']){
    console.log(JSON.stringify({template,status:'starting'}));
    const id='workflow_'+template;
    await page.locator('.rail-link[data-route="modules"]').click();
    await page.locator('[data-action="new-module"]').click();
    await page.locator('[name="name"]').fill('工作流 '+template);
    await page.locator('[name="code"]').fill(id.toUpperCase());
    await page.locator('[name="base"]').selectOption('template:'+template);
    await page.locator('#dialog-form button[type="submit"]').click();
    await expect(page.locator('#module-code')).toBeVisible();
    await page.locator('[data-action="editor-tab"][data-value="attributes"]').first().click();
    const parameter=template==='pump'?'speed_ratio':template==='heat_exchanger'?'ua_w_k':template==='resistance'?'loss_coefficient':'opening_ratio';
    await page.locator(`[data-action="edit-contract-item"][data-section="parameters"][data-id="${parameter}"]`).click();
    await page.locator('[name="default"]').fill(template==='pump'?'1.1':template==='heat_exchanger'?'110':template==='resistance'?'9':'.7');
    if(template==='managed_state'){
      await page.locator('[name="unit"]').fill('1');await page.locator('[name="display_unit"]').fill('%');
      await page.locator('[name="display_scale"]').fill('.01');await page.locator('[name="display_value"]').fill('70');
      await expect(page.locator('#parameter-engine-preview')).toContainText('0.7');
    }
    await page.locator('#dialog-form button[type="submit"]').click();
    await expect(page.locator('#dialog-form')).toHaveCount(0);
    await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
    await page.locator('[data-action="validate-module-contract"]').click();
    await expect(page.locator('#module-output')).toContainText('Worker 入口与四阶段方法通过');
    const published=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');
    await page.locator('[data-action="save-module-version"]').click();
    const response=await published,release=await response.json();expect(response.status(),JSON.stringify(release)).toBe(201);
    expect(release.validation_evidence[0].level).toBe('L3');
    await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
    await page.locator('.rail-link[data-route="modules"]').click();
    await page.locator(`[data-module-id="${id}"] [data-action="module-example"]`).click();
    const requested=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/runs')&&r.request().method()==='POST');
    await page.locator('[data-action="run-project"][data-command="run"]').first().click();
    const queued=await(await requested).json();
    await expect.poll(async()=>{const data=await(await page.request.get(server.base+'/api/v1/runs/'+queued.run_id)).json();if(data.status==='failed')throw Error(JSON.stringify({template,diagnostics:data.frame?.diagnostics,project:data.request?.project?.instances}));return data.status;},{timeout:30000}).toBe('completed');
    await page.locator('[data-action="save"]').first().click();
    const before=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
    const project=before.projects.find(p=>p.id===before.activeProject);
    expect(project.pages[0].nodes.some(n=>n.moduleId===id&&n.package.version==='1.0.0')).toBe(true);
    const original=await(await page.request.get(server.base+'/api/v1/runs/'+queued.run_id)).json();
    await page.reload();
    await expect(page.locator('[data-action="run-project"][data-command="run"]').first()).toBeVisible();
    const rerun=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/runs')&&r.request().method()==='POST');
    await page.locator('[data-action="run-project"][data-command="run"]').first().click();
    const next=await(await rerun).json();
    await expect.poll(async()=> (await(await page.request.get(server.base+'/api/v1/runs/'+next.run_id)).json()).status,{timeout:30000}).toBe('completed');
    const repeated=await(await page.request.get(server.base+'/api/v1/runs/'+next.run_id)).json();
    expect(repeated.frame.variables['V1.main.mass_flow_kg_s'] ?? repeated.frame.variables['V1.hot.mass_flow_kg_s']).toBeCloseTo(
      original.frame.variables['V1.main.mass_flow_kg_s'] ?? original.frame.variables['V1.hot.mass_flow_kg_s'],7);
    results.push({template,version:release.module.version,reloadRecomputed:true});
  }
  await exerciseModuleAssertionBoundaries(page,server.base);
  await exerciseModuleAssertions(page,server.base,'workflow_managed_state');
  await page.locator('.rail-link[data-route="modules"]').click();
  await page.locator('[data-module-id="workflow_managed_state"] [data-action="edit-module"]').click();
  await page.locator('[data-action="editor-tab"][data-value="code"]').first().click();
  const originalSource=await page.locator('#module-code').inputValue();
  const broken=originalSource.replace('def evaluate(self, ctx: ModuleContext) -> None:',
    'def evaluate(self, ctx: ModuleContext) -> None:\n        raise ValueError("replay workflow probe")');
  expect(broken).not.toBe(originalSource);
  await page.locator('#module-code').fill(broken);
  await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
  const rejected=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();
  const rejection=await(await rejected).json();expect(rejection.detail.replay.module.source.runtime).toContain('replay workflow probe');
  await page.locator('[data-action="module-error-line"]').first().click();
  await expect(page.locator('#module-code')).toBeFocused();
  const selection=await page.locator('#module-code').evaluate(e=>e.value.slice(e.selectionStart,e.selectionEnd));
  expect(selection).toContain('raise ValueError');
  await page.locator('#module-code').fill(originalSource);
  const versions=await(await page.request.get(server.base+'/api/v1/modules/workflow_managed_state/versions')).json();
  expect(versions.versions).toHaveLength(1);
  expect(errors).toEqual([]);
  mkdirSync('artifacts/module-system/98dadd5/MOD-E4',{recursive:true});
  await captureFhd(page, 'artifacts/module-system/98dadd5/MOD-E4/workflow.png');
  console.log(JSON.stringify({results,errors},null,2));
}catch(error){
  // CI-only failures need the dialog state: thrown onSubmit text or HTML validation that blocked submit.
  const dialog=await page.evaluate(()=>{const f=document.getElementById('dialog-form');if(!f)return null;
    return {title:document.getElementById('dialog-title')?.textContent,error:document.getElementById('dialog-error')?.textContent,
      invalid:[...f.elements].filter(e=>e.willValidate&&!e.checkValidity()).map(e=>({name:e.name,value:e.value,message:e.validationMessage})),
      preview:document.getElementById('parameter-engine-preview')?.textContent,toast:document.getElementById('toast')?.textContent};}).catch(()=>null);
  console.error(JSON.stringify({browser:browser.version(),results,errors,dialog}));
  mkdirSync('artifacts',{recursive:true});await captureFhd(page, 'artifacts/module-workflow-failure.png').catch(()=>{});
  throw error;
}finally{await browser.close();await server.close();}
