import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[],evidence=[];
const output='artifacts/desktop-workspace';mkdirSync(output,{recursive:true});
page.on('pageerror',e=>errors.push(e.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
async function contained(locator,width){
  const box=await locator.boundingBox();expect(box).not.toBeNull();
  expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(width+1);
  return box;
}
try {
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await expect(page.locator('#app-rail [role="group"]')).toHaveCount(3);
  await expect(page.locator('#app-rail [aria-current="page"]')).toHaveAttribute('data-route','home');
  await captureFhd(page,output+'/home.png');
  await page.locator('[data-action="start-modeling"]').click();
  await expect(page.locator('.workbench-flow > .runbar')).toBeVisible();
  await expect(page.locator('.floater.docked')).toBeVisible();
  await page.locator('.runbar [data-command="step"]').click();
  await expect(page.locator('.canvas-info [data-result-status]')).toContainText('结果已更新',{timeout:15000});
  await captureFhd(page,output+'/workbench.png');
  await page.locator('.floater [data-action="float-dock"]').click();
  const controls=await page.locator('.runbar').boundingBox(),panel=await page.locator('.floater').boundingBox();
  expect(panel.y).toBeGreaterThanOrEqual(controls.y+controls.height);
  await page.locator('.floater [data-action="float-close"]').click();
  // The footer must keep save feedback after repeated chrome updates and real persistence.
  const saved=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('#app-header [data-action="save"]').click();expect((await saved).ok()).toBe(true);
  await expect(page.locator('#statusbar [data-save-status]')).toContainText('工作区已保存');
  await nav('home');await page.locator('[data-action="edit-module"][data-id="valve"]').click();
  await expect(page.locator('#app-rail [aria-current="page"]')).toHaveAttribute('data-route','modules');
  for(const size of [{width:1280,height:800},{width:760,height:800},{width:390,height:844}]) {
    await page.setViewportSize(size);await nav('home');
    await expect(page.locator('#statusbar [data-save-status]')).not.toBeEmpty();
    for(const action of ['page-map','workspace-tools','reload-workspace','save','theme'])
      await contained(page.locator(`#app-header [data-action="${action}"]`),size.width);
    await page.screenshot({path:`${output}/home-${size.width}.png`});
    // Scrolling a compact rail must still reach every destination.
    for(const route of ['projects','controls','curves','runs','batches','air','modules','bench','models','connections','settings','help','workbench']) {
      await nav(route);await expect(page.locator('#app-rail [aria-current="page"]')).toHaveAttribute('data-route',route);
    }
    const flow=await contained(page.locator('.workbench-flow'),size.width);
    for(const command of ['run','pause','step','stop'])await contained(page.locator(`.runbar [data-command="${command}"]`),size.width);
    for(const action of ['toggle-chart','workbench-settings']) {
      const button=await contained(page.locator(`.runbar [data-action="${action}"]`),size.width);
      expect(button.y+button.height).toBeLessThanOrEqual(flow.y+flow.height);
    }
    const canvas=await page.locator('.canvas-area').boundingBox();expect(canvas.y).toBeGreaterThanOrEqual(flow.y+flow.height);
    await page.screenshot({path:`${output}/workbench-${size.width}.png`});
    evidence.push({...size,toolbarHeight:flow.height,canvasHeight:canvas.height});
  }
  expect(errors).toEqual([]);
  writeFileSync(output+'/verification.json',JSON.stringify({viewports:evidence,navigation:true,saveFeedback:true,acceptedSample:true,floatDoesNotCoverControls:true,errors},null,2)+'\n');
  console.log(JSON.stringify({desktopWorkspace:true,viewports:evidence,errors}));
} catch(error) {
  console.error(error,errors);await page.screenshot({path:output+'/failure.png'}).catch(()=>{});process.exitCode=1;
} finally {await browser.close();await server.close();}
