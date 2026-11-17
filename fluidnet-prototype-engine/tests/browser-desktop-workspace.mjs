import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[],evidence=[],examples=[];
const output='artifacts/desktop-workspace';mkdirSync(output,{recursive:true});
page.on('pageerror',e=>errors.push(e.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const menu=id=>page.locator(`[data-workspace-menu="${id}"]`);
async function menuReachable(id){
  const disclosure=menu(id);await disclosure.locator('summary').click();
  await expect(disclosure).toHaveAttribute('open','');
  await expect(page.locator('[data-workspace-menu][open]')).toHaveCount(1);
  const panel=disclosure.locator('.workspace-menu-panel'),box=await contained(panel,page.viewportSize().width);
  const controls=await page.locator('.workbench-flow').boundingBox();
  expect(box.y).toBeGreaterThanOrEqual(controls.y+controls.height);
  expect(box.y+box.height).toBeLessThanOrEqual(page.viewportSize().height);
  for(const control of await panel.locator('button:not(:disabled),input,select').all()){
    await control.scrollIntoViewIfNeeded();
    expect(await control.evaluate(el=>{const b=el.getBoundingClientRect();return el.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2));})).toBe(true);
  }
  return disclosure;
}
async function contained(locator,width){
  const box=await locator.boundingBox();expect(box).not.toBeNull();
  expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(width+1);
  return box;
}
async function receivesPointer(locator){
  await expect.poll(()=>locator.evaluate(el=>{const b=el.getBoundingClientRect();return el.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2));})).toBe(true);
}
try {
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v',{timeout:20000});
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
  for(const id of ['extensions','display','device']){
    const disclosure=await menuReachable(id);
    await captureFhd(page,`${output}/menu-${id}.png`);
    await page.keyboard.press('Escape');await expect(disclosure).not.toHaveAttribute('open','');
    await expect(disclosure.locator('summary')).toBeFocused();
  }
  await menuReachable('extensions');await menu('display').locator('summary').click();
  await expect(menu('extensions')).not.toHaveAttribute('open','');
  await page.locator('#network').click({position:{x:10,y:50}});await expect(menu('display')).not.toHaveAttribute('open','');
  await menuReachable('display');await page.locator('[data-canvas-mode]').selectOption('flow');
  await expect(page.locator('[data-canvas-mode]')).toHaveValue('flow');
  await page.keyboard.press('Escape');
  await menuReachable('device');await menu('device').locator('[data-action="open-device"]').click();
  await expect(page.locator('.floater [data-action="float-tab"].active')).toContainText('参数与型号');
  await page.locator('.floater [data-action="float-close"]').click();
  // The footer must keep save feedback after repeated chrome updates and real persistence.
  const saved=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('#app-header [data-action="save"]').click();expect((await saved).ok()).toBe(true);
  await expect(page.locator('#statusbar [data-save-status]')).toContainText('工作区已保存');
  await page.locator('.runbar [data-command="stop"]').click();
  await expect(page.locator('.runbar [data-command="stop"]')).toBeDisabled();
  await nav('home');await page.locator('[data-action="browse-equipment"]').first().click();
  await expect(page.locator('#app-rail [aria-current="page"]')).toHaveAttribute('data-route','workbench');
  await expect(page.locator('[data-filter="canvasModuleSearch"]')).toBeFocused();
  await nav('workbench');
  await nav('home');
  await page.locator('[data-action="home-place-module"][data-id="pump"]').click();
  await expect(page.locator('[data-canvas-hint]')).toContainText('离心泵');
  await expect(page.locator('[data-action="place-module"][data-id="pump"].active')).toBeVisible();
  const beforePlacement=await page.locator('#network .net-node').count();
  const placementPoint=await page.locator('#network-area').evaluate(area=>{
    const bounds=area.getBoundingClientRect(),nodes=[...area.querySelectorAll('#network [data-node]')].map(node=>node.getBoundingClientRect());
    for(let y=64;y<bounds.height-64;y+=28)for(let x=48;x<bounds.width-48;x+=28){
      const px=bounds.left+x,py=bounds.top+y;
      if(nodes.every(node=>px<node.left-36||px>node.right+36||py<node.top-36||py>node.bottom+36))return{x,y};
    }
    throw new Error('画布上没有找到空闲放置位置');
  });
  await page.locator('#network-area').click({position:placementPoint});
  await expect(page.locator('#network .net-node')).toHaveCount(beforePlacement+1);
  await expect(page.locator('[data-canvas-hint]')).toBeEmpty();
  await page.keyboard.press('Escape');await expect(page.locator('[data-canvas-hint]')).toBeEmpty();
  await nav('home');await page.locator('[data-action="home-place-module"][data-id="pipe"]').click();
  const occupied=page.locator('#network .net-node[data-node="V1"]'),originalTransform=await occupied.getAttribute('transform'),occupiedBox=await occupied.boundingBox();
  await page.mouse.move(occupiedBox.x+occupiedBox.width/2,occupiedBox.y+occupiedBox.height/2);
  await page.mouse.down();await page.mouse.move(occupiedBox.x+occupiedBox.width/2+12,occupiedBox.y+occupiedBox.height/2+8);await page.mouse.up();
  await expect(page.locator('#network .net-node')).toHaveCount(beforePlacement+2);
  await expect(occupied).toHaveAttribute('transform',originalTransform);
  await nav('projects');await page.locator('[data-action="project-examples"]').click();
  await expect(page.locator('.project-examples .example-card')).toHaveCount(9);
  await captureFhd(page,output+'/project-examples.png');
  await page.locator('.example-card[data-template="water"]').click();
  await expect(page.getByRole('dialog')).toContainText('新建项目');
  await expect(page.getByLabel('起始内容')).toHaveValue('water');
  await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect(page.locator('.workbench')).toBeVisible();
  await expect(page.locator('#network .net-node')).toHaveCount(9);
  examples.push({template:'water',devicesOnPage:9});
  await menuReachable('extensions');await menu('extensions').locator('[data-action="project-find"]').click();
  await expect(page.getByRole('dialog')).toContainText('全项目查找');
  await expect(menu('extensions')).not.toHaveAttribute('open','');await page.keyboard.press('Escape');
  for(const choice of [{template:'heat',count:7},{template:'tank',count:5},
    ...['cs-create','cs-create-multi','cs-create-continuous','cs-create-station','cs-create-coupled','cs-create-dual'].map(action=>({action}))]){
    await nav('projects');await page.locator('[data-action="project-examples"]').click();
    await page.locator(choice.template?`.example-card[data-template="${choice.template}"]`:`.example-card[data-action="${choice.action}"]`).click();
    if(choice.template){await expect(page.getByLabel('起始内容')).toHaveValue(choice.template);await page.getByRole('dialog').locator('button[type="submit"]').click();}
    if(choice.action==='cs-create-dual'){await expect(page.getByLabel('双盘管拓扑')).toHaveValue('parallel');await page.getByRole('dialog').locator('button[type="submit"]').click();}
    await expect(page.locator('.workbench')).toBeVisible({timeout:20000});
    await expect(page.getByRole('dialog')).toHaveCount(0);
    const nodes=page.locator('#network .net-node');
    if(choice.count)await expect(nodes).toHaveCount(choice.count);else expect(await nodes.count()).toBeGreaterThan(0);
    examples.push({...choice,devicesOnPage:await nodes.count()});
  }
  await nav('projects');
  await page.locator('.project-card').filter({hasText:'泵阀并联管网'}).last().locator('[data-action="open-project"]').first().click();
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
      await receivesPointer(page.locator(`.runbar [data-action="${action}"]`));
    }
    await receivesPointer(page.locator('.runbar [data-command="run"]'));
    const canvas=await page.locator('.canvas-area').boundingBox();expect(canvas.y).toBeGreaterThanOrEqual(flow.y+flow.height);
    if(size.width<=500){
      await expect.poll(async()=>{const library=await page.locator('.canvas-library').boundingBox();return library.y;}).toBeGreaterThanOrEqual(canvas.y);
      await page.locator('.canvas-tools [data-action="toggle-library"]').click();await expect(page.locator('.canvas-library')).not.toBeVisible();
      await page.locator('.canvas-tools [data-action="toggle-library"]').click();await expect(page.locator('.canvas-library')).toBeVisible();
      await receivesPointer(page.locator('.runbar [data-command="run"]'));
      await page.locator('[data-filter="canvasModuleSearch"]').fill('离心泵');
      await expect(page.locator('.library-item[data-id="pump"]')).toBeVisible();await page.locator('[data-filter="canvasModuleSearch"]').fill('');
    }
    for(const id of ['extensions','display']){await menuReachable(id);await page.keyboard.press('Escape');}
    await page.screenshot({path:`${output}/workbench-${size.width}.png`});
    evidence.push({...size,toolbarHeight:flow.height,canvasHeight:canvas.height});
  }
  expect(errors).toEqual([]);
  await page.setViewportSize({width:1920,height:1080});await page.locator('#app-header [data-action="theme"]').click();
  await menuReachable('extensions');await captureFhd(page,output+'/menu-dark.png');await page.keyboard.press('Escape');
  writeFileSync(output+'/verification.json',JSON.stringify({viewports:evidence,navigation:true,saveFeedback:true,acceptedSample:true,homeEquipmentPlacement:true,occupiedPlacementPreservesGeometry:true,examples,accessibleMenus:true,menuActions:true,floatDoesNotCoverControls:true,errors},null,2)+'\n');
  console.log(JSON.stringify({desktopWorkspace:true,viewports:evidence,errors}));
} catch(error) {
  console.error(error,errors);await page.screenshot({path:output+'/failure.png'}).catch(()=>{});process.exitCode=1;
} finally {await browser.close();await server.close();}
