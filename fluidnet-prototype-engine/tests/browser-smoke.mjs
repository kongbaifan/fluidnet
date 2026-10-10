import { chromium, expect } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';
const browser = await chromium.launch({channel:'msedge',headless:true});
const page = await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const runButton=(command)=>page.locator(`[data-action="run-project"][data-command="${command}"]`).first();
async function step() {
  const response=page.waitForResponse(r=>r.url().endsWith('/runs') && r.request().method()==='POST');
  await runButton('step').click();
  const result=await (await response).json();
  expect(result.status).toBe('completed');
  await expect(page.locator('[data-result-status]').first()).toContainText('结果已更新');
  await page.locator('[data-action="save"]').first().click();
  const state=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
  const run=state.projects.find(p=>p.id===state.activeProject).run;
  expect(run.history.at(-1).canonical['V1.mass_flow_kg_s']).toBe(result.frame.variables['V1.mass_flow_kg_s']);
  expect(run.history.at(-1).variableValues['V1:out0:FLOW']).toBe(result.frame.variables['V1.mass_flow_kg_s']);
  expect(run.history.at(-1).variableValues['V1:out0:TEMP']).toBeNull();
  return {result,run};
}
try {
  await page.goto('http://127.0.0.1:8798');
  await page.locator('[data-action="start-modeling"]').click();
  await page.locator('[data-action="save"]').first().click();
  const state = await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
  expect(state.records).toHaveLength(0);
  if (process.argv.includes('--refresh-fixture')) {
    mkdirSync('tests/fixtures',{recursive:true});
    const payload={format:'fluidnet-studio-prototype',activeProject:state.activeProject,
      modules:state.modules.map(({id,kind,ports,channels})=>({id,kind,ports,channels})),
      projects:state.projects.map(({id,name,medium,pages,solver})=>({id,name,medium,pages:pages.map(({id,nodes,edges})=>({id,edges,nodes:nodes.map(({id,moduleId,name,x,y,params,draft})=>({id,moduleId,name,x,y,params,draft}))})),solver}))};
    writeFileSync('tests/fixtures/prototype.json',JSON.stringify(payload,null,2));
  }
  await page.locator('[data-action="validate"]').click();
  await expect(page.getByRole('dialog')).toContainText('定物性液态水水力');
  await page.getByRole('dialog').locator('[data-action="close-dialog"]').first().click();
  const first=await step();
  const opening=page.locator('input[type="number"][data-instance-param="opening"][data-id="V1"]');
  await opening.fill('40'); await opening.blur();
  await page.locator('[data-action="apply-instance"][data-id="V1"]').click();
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  const second=await step();
  expect(second.result.frame.variables['V1.mass_flow_kg_s']).toBeLessThan(first.result.frame.variables['V1.mass_flow_kg_s']);
  expect(second.result.frame.variables['V2.mass_flow_kg_s']).toBeGreaterThan(first.result.frame.variables['V2.mass_flow_kg_s']);
  expect(second.run.history).toHaveLength(3);
  expect(second.run.time).toBe(.2);
  await page.reload();
  await expect(page.locator('[data-result-status]').first()).toContainText('结果已更新');
  mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:'artifacts/workbench.png',fullPage:true});
  const startResponse=page.waitForResponse(r=>r.url().endsWith('/runs') && r.request().method()==='POST');
  await runButton('run').click();
  expect((await (await startResponse).json()).status).toBe('completed');
  await expect(page.locator('[data-result-status]').first()).toContainText(/t = 0\.[1-9]/);
  await runButton('pause').click();
  await expect(runButton('pause')).toBeDisabled();
  await expect(runButton('run')).toBeEnabled();
  await runButton('run').click();
  await expect(runButton('pause')).toBeEnabled();
  await runButton('stop').click();
  await expect(runButton('stop')).toBeDisabled();
  console.log(JSON.stringify({status:second.result.status,metrics:second.result.frame.metrics,
    before:first.result.frame.variables['V1.mass_flow_kg_s'],after:second.result.frame.variables['V1.mass_flow_kg_s'],errors},null,2));
  expect(errors).toEqual([]);
} catch(error) {
  console.error('Browser errors:',errors);
  throw error;
} finally { await browser.close(); }
