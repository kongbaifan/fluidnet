import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
const panel=()=>page.locator('[data-float-id="V1"]');
const action=name=>panel().locator(`[data-action="${name}"]`);
const geometry=()=>panel().evaluate(el=>({x:parseFloat(el.style.left),y:parseFloat(el.style.top),w:parseFloat(el.style.width),h:parseFloat(el.style.height)}));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
async function drag(locator,dx,dy){const box=await locator.boundingBox(),x=box.x+box.width/2,y=box.y+box.height/2;await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+dx,y+dy,{steps:10});await page.mouse.up();}
async function saved(){
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await receipt).ok()).toBe(true);
  return (await(await page.request.get(server.base+'/api/v1/workspace')).json()).data;
}
const active=s=>s.projects.find(p=>p.id===s.activeProject);
const device=s=>active(s).pages.flatMap(p=>p.nodes).find(n=>n.id==='V1');
try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="start-modeling"]').first().click();await expect(panel()).toHaveClass(/docked/);
  await action('float-dock').click();await expect(panel()).not.toHaveClass(/docked/);
  const before=await saved(),start=await geometry();
  await drag(panel().locator('.float-title'),-100,70);const moved=await geometry();expect(moved.x).toBeCloseTo(start.x-100,1);expect(moved.y).toBeCloseTo(start.y+70,1);
  await drag(panel().locator('[data-float-resize]'),80,60);const sized=await geometry();expect(sized.w).toBeCloseTo(moved.w+80,1);expect(sized.h).toBeCloseTo(moved.h+60,1);
  await action('float-pin').click();await expect(action('float-pin')).toHaveAttribute('aria-pressed','true');
  await action('float-min').click();await expect(panel()).toHaveClass(/minimized/);await expect(panel().locator('.float-body')).toHaveCount(0);
  await action('float-min').click();await expect(panel()).not.toHaveClass(/minimized/);expect(await geometry()).toEqual(sized);
  await action('float-max').click();expect((await geometry()).w).toBeGreaterThan(sized.w);
  await action('float-max').click();expect(await geometry()).toEqual(sized);
  await action('float-tab').filter({hasText:'全部变量'}).click();await expect(panel()).toHaveClass(/variables-floater/);
  await action('float-tab').filter({hasText:'参数与型号'}).click();await expect(panel()).not.toHaveClass(/variables-floater/);
  await action('float-dock').click();await expect(panel()).toHaveClass(/docked/);await expect(page.locator('.workbench')).toHaveClass(/has-docked/);
  await action('float-dock').click();await expect(panel()).not.toHaveClass(/docked/);const remembered=await geometry();
  await action('float-close').click();await expect(panel()).toHaveCount(0);
  await page.locator('[data-node="V1"]').dblclick();expect(await geometry()).toEqual(remembered);await expect(action('float-pin')).toHaveAttribute('aria-pressed','true');
  const after=await saved();expect(device(after).params).toEqual(device(before).params);expect(device(after).draft).toEqual(device(before).draft);
  await nav('models');await expect(panel()).toHaveCount(0);await nav('workbench');await expect(panel()).toBeVisible();
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');await page.locator('[data-node="V1"]').dblclick();expect(await geometry()).toEqual(remembered);
  const restored=await saved();expect(device(restored).params).toEqual(device(before).params);expect(device(restored).draft).toEqual(device(before).draft);
  // Escape keeps the last displayed window position and must mark/store it as an edit.
  const title=await panel().locator('.float-title').boundingBox(),x=title.x+title.width/2,y=title.y+title.height/2;
  await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x-25,y+10,{steps:8});const cancelled=await geometry();
  await page.keyboard.press('Escape');await page.mouse.up();await expect(page.locator('[data-save-status]')).toContainText('有未保存修改');
  const committed=await saved(),position=committed.windowPositions[committed.activeProject+':V1'];
  for(const key of ['x','y','w','h'])expect(position[key]).toBeCloseTo(cancelled[key],1);
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');await page.locator('[data-node="V1"]').dblclick();expect(await geometry()).toEqual(cancelled);
  await captureFhd(page,'artifacts/device-windows-1080p.png');expect(errors).toEqual([]);
  console.log(JSON.stringify({drag:true,resize:true,dock:true,pin:true,minimize:true,maximize:true,tabs:true,closeReopen:true,reload:true,cancelGestureSaved:true,parametersUnchanged:true,errors}));
}catch(error){console.error(error,errors);await captureFhd(page,'artifacts/device-windows-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
