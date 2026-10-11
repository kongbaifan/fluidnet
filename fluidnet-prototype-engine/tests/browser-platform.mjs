import { chromium, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const browser = await chromium.launch({channel:'msedge',headless:true});
const page = await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
const save=async()=>{
  await page.locator('[data-action="save"]').first().click();
  return page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
};
try {
  await page.goto('http://127.0.0.1:8798/#modules');
  await expect(page.locator('#app-header')).toContainText('v0.2.0');
  const card=page.locator('[data-module-id="programmable_valve"]');
  await expect(card).toContainText('Python · v1');
  await card.locator('[data-action="test-module"]').click();
  await expect(page.locator('h1')).toHaveText('独立验证台');
  await expect(page.locator('[data-bench-param="opening_ratio"]')).toHaveValue('0.8');
  const response=page.waitForResponse(r=>r.url().endsWith('/modules/test') && r.request().method()==='POST');
  await page.locator('[data-action="run-bench"][data-command="run"]').click();
  const bench=await (await response).json();
  await expect(page.locator('[data-bench-commits]')).toHaveText('1');
  await expect(page.locator('#bench-results')).toContainText('density_kg_m3');
  expect(bench.committed.state.throughput_kg).toBeGreaterThan(0);
  let state=await save();
  expect(state.bench.run.values.q).toBe(bench.frame.variables['D1.mass_flow_kg_s']);
  mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:'artifacts/module-bench.png',fullPage:true});
  await page.locator('.rail-link[data-route="modules"]').click();
  await card.locator('[data-action="module-example"]').click();
  await expect(page.locator('[data-node="V1"]')).toContainText('可编程阀门');
  const result=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/runs') && r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const queued=await (await result).json();
  expect(queued.status).toBe('queued');
  await expect(page.locator('[data-result-status]').first()).toContainText('t = 1.0 s',{timeout:20000});
  state=await save();
  const project=state.projects.find(p=>p.id===state.activeProject);
  expect(project.run.history.at(-1).canonical['V1.state.commit_count']).toBe(10);
  expect(project.run.history.at(-1).variableValues['V1:runtime:state.throughput_kg']).toBeGreaterThan(0);
  await page.reload();
  await expect(page.locator('#app-header')).toContainText('v0.2.0');
  await page.locator('[data-node="V1"]').dblclick();
  await expect(page.locator('[data-instance-param="opening_ratio"][type="number"]')).toHaveValue('0.8');
  await page.screenshot({path:'artifacts/module-project.png',fullPage:true});
  await page.locator('[data-action="float-close"]').first().click();
  // A package from the server can use the original prototype drag/drop path.
  const drag=page.locator('[data-drag-module="programmable_valve"]');
  await drag.dragTo(page.locator('#network'),{targetPosition:{x:500,y:150}});
  state=await save();
  const nodes=state.projects.find(p=>p.id===state.activeProject).pages[0].nodes;
  expect(nodes.filter(n=>n.moduleId==='programmable_valve')).toHaveLength(2);
  expect(nodes.at(-1).params.opening_ratio).toBe(.8);
  expect(errors).toEqual([]);
  console.log(JSON.stringify({workerFlow:bench.frame.variables['D1.mass_flow_kg_s'],
    commits:project.run.history.at(-1).canonical['V1.state.commit_count'],errors},null,2));
} catch(error) {
  mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:'artifacts/platform-failure.png',fullPage:true});
  console.error('Browser errors:',errors);
  throw error;
} finally { await browser.close(); }
