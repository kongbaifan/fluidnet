import { chromium, expect } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';
const base=process.env.FLUIDNET_TEST_URL || 'http://127.0.0.1:8798';
const browser = await chromium.launch({channel:'msedge',headless:true});
const page = await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const runButton=(command)=>page.locator(`[data-action="run-project"][data-command="${command}"]`).first();
async function step() {
  await page.locator('[data-action="save"]').first().click();
  const old=await page.evaluate(()=>{const s=JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));return s.projects.find(p=>p.id===s.activeProject).run;});
  const response=page.waitForResponse(r=>r.request().method()==='POST' && (new URL(r.url()).pathname.endsWith('/runs') || new URL(r.url()).pathname.endsWith('/command')));
  await runButton('step').click();
  const accepted=await (await response).json(),runId=accepted.run_id || old.runId;
  let result;
  await expect.poll(async()=>{result=await (await page.request.get(base+'/api/v1/runs/'+runId)).json();return result.status==='paused' && result.frame.time_s>old.time;},{timeout:15000}).toBe(true);
  await expect(page.locator('[data-result-status]').first()).toContainText('t = '+result.frame.time_s.toFixed(1)+' s');
  await expect(page.locator('[data-result-status]').first()).toContainText('结果已更新');
  await page.locator('[data-action="save"]').first().click();
  const state=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
  const run=state.projects.find(p=>p.id===state.activeProject).run;
  expect(run.history.at(-1).canonical['V1.mass_flow_kg_s']).toBe(result.frame.variables['V1.mass_flow_kg_s']);
  expect(run.history.at(-1).variableValues['V1:out0:FLOW']).toBe(result.frame.variables['V1.mass_flow_kg_s']);
  // Thermal layer: 20 °C supply plus a small pump temperature rise.
  const temperature=run.history.at(-1).variableValues['V1:out0:TEMP'];
  expect(Number.isFinite(temperature)).toBe(true);
  expect(temperature).toBeGreaterThanOrEqual(19.9);
  expect(temperature).toBeLessThanOrEqual(20.5);
  return {result,run};
}
try {
  await page.goto(base);
  await expect(page.locator('#app-header')).toContainText(/v\d+\.\d+\.\d+/);
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
  await expect(page.getByRole('dialog')).toContainText('各回路工质的水力与端口焓、温度');
  await page.getByRole('dialog').locator('[data-action="close-dialog"]').first().click();
  const first=await step();
  const opening=page.locator('input[type="number"][data-instance-param="opening"][data-id="V1"]');
  await opening.fill('40'); await opening.blur();
  await page.locator('[data-action="apply-instance"][data-id="V1"]').click();
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect.poll(async()=>{await page.locator('[data-action="save"]').first().click();return page.evaluate(()=>{const s=JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));return s.projects.find(p=>p.id===s.activeProject).pages[0].nodes.find(n=>n.id==='V1').params.opening;});}).toBe(40);
  const second=await step();
  expect(second.result.frame.variables['V1.mass_flow_kg_s']).toBeLessThan(first.result.frame.variables['V1.mass_flow_kg_s']);
  expect(second.result.frame.variables['V2.mass_flow_kg_s']).toBeGreaterThan(first.result.frame.variables['V2.mass_flow_kg_s']);
  expect(second.run.history).toHaveLength(3);
  expect(second.run.time).toBe(.2);
  await page.reload();
  await expect(page.locator('[data-result-status]').first()).toContainText('结果已更新');
  mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:'artifacts/workbench.png',fullPage:true});
  const startResponse=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/command') && r.request().method()==='POST');
  await runButton('run').click();
  expect((await (await startResponse).json()).command_status).toBe('accepted');
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
