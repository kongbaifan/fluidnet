import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const hint=page.locator('#canvas-inspection');
const port=id=>page.locator(`[data-port-node="HX1"][data-port-id="${id}"]`);
const state=()=>page.evaluate(async () =>{const s=(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));return s.projects.find(p=>p.id===s.activeProject);});
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
async function save(){
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await posted).ok()).toBe(true);return state();
}
const activeEdges=()=>page.locator('#network .net-line.path-trace-active').evaluateAll(els=>els.map(el=>el.dataset.traceEdge).sort());
try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="open-project"][data-id="heat-loop"]').first().click();
  const original=await save();
  await port('in0').hover();
  await expect(hint).toContainText('in0 ↔ out0');
  expect(await activeEdges()).toEqual(['h2','h3']);
  await expect(page.locator('[data-node="HX1"] .channel-active')).toHaveCount(1);
  await expect(page.locator('[data-port-node="HX1"][data-port-id="in1"]')).not.toHaveClass(/path-trace-active/);
  await expect(page.locator('[data-port-node="P1"][data-port-id="out0"]')).toHaveClass(/path-trace-remote/);
  await expect(hint.locator('[data-trace-destination="B2:out0"]')).toBeVisible();
  await hint.locator('[data-trace-close]').click();await expect(hint).toBeHidden();
  expect(await activeEdges()).toEqual([]);

  // Keyboard focus selects only the other side. No pointer hover or project mutation needed.
  await port('in1').focus();
  await expect(hint).toContainText('in1 ↔ out1');
  expect(await activeEdges()).toEqual(['h5','h6']);
  await expect(page.locator('[data-port-node="HX1"][data-port-id="in0"]')).not.toHaveClass(/path-trace-active/);
  await page.keyboard.press('Escape');await expect(hint).toBeHidden();
  expect((await save()).pages).toEqual(original.pages);

  // Rehome one endpoint through the real UI; the same edge must remain traceable across canvases.
  await page.locator('[data-action="new-canvas"]').first().click();
  await page.getByRole('dialog').locator('[name="name"]').fill('换热器回水');await submit();
  const remotePage=(await save()).activePage;
  await page.locator(`[data-action="canvas-tab"][data-id="${original.activePage}"]`).click();
  await page.locator('[data-node="B2"]').click();
  await page.locator('[data-action="move-device-page"][data-id="B2"]').click();
  await page.getByRole('dialog').locator('[name="page"]').selectOption(remotePage);await submit();
  const split=await save();
  expect(split.pages.flatMap(p=>p.edges)).toEqual(original.pages.flatMap(p=>p.edges));
  await page.locator(`[data-action="canvas-tab"][data-id="${original.activePage}"]`).click();
  await port('in0').hover();
  expect(await activeEdges()).toEqual(['h2']);
  await expect(hint).toContainText('跨页 · 换热器回水');
  await expect(page.locator('.cross-page-strip [data-id="h3"]')).toHaveClass(/path-trace-active/);
  await captureFhd(page,'artifacts/path-trace-cross-page.png');
  await hint.locator('[data-trace-destination="B2:out0"]').click();
  await expect(page.locator('[data-node="B2"]')).toBeVisible();
  expect((await save()).activePage).toBe(remotePage);
  await page.locator('[data-action="float-close"]').click();
  await page.locator(`[data-action="canvas-tab"][data-id="${original.activePage}"]`).click();
  await save();await page.reload();
  await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await port('out0').focus();
  await expect(hint).toContainText('跨页 · 换热器回水');
  expect(await activeEdges()).toEqual(['h2']);
  await expect(page.locator('[data-node="HX1"] .channel-active')).toHaveCount(1);
  expect(errors).toEqual([]);
  console.log(JSON.stringify({twoSidesIsolated:true,keyboard:true,crossPage:true,reload:true,errors}));
}catch(error){await captureFhd(page,'artifacts/path-trace-failure.png');throw error;}
finally{await browser.close();await server.close();}
