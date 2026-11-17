import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage(FHD_CONTEXT),errors=[],output='artifacts/desktop-entry-fixes';
mkdirSync(output,{recursive:true});page.on('pageerror',error=>errors.push(error.message));
const evidence={viewport:FHD_CONTEXT.viewport,legacyReferences:[],sixRoomViews:[]};
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const card=id=>page.locator(`.module-card[data-module-id="${id}"]`);
const dialog=()=>page.getByRole('dialog');
async function save(){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/workspace')&&r.request().method()==='POST');
  await page.locator('#app-header [data-action="save"]').click();expect((await response).ok()).toBe(true);
  await expect(page.locator('#statusbar [data-save-status]')).toContainText('工作区已保存');
  return (await(await page.request.get(server.base+'/api/v1/workspace')).json()).data;
}
async function closeDialog(){await dialog().locator('[data-action="close-dialog"]').first().click();await expect(dialog()).toHaveCount(0);}
async function snapshot(name){await page.mouse.move(20,25);await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(180);await captureFhd(page,output+'/'+name+'.png');}
async function visibleGeometry(){return page.locator('#network-area').evaluate(area=>{
  const bounds=area.getBoundingClientRect(),nodes=[...area.querySelectorAll('.net-node')].map(node=>node.getBoundingClientRect());
  return {viewBox:area.querySelector('#network').getAttribute('viewBox'),nodes:nodes.length,
    fullyVisible:nodes.filter(node=>node.left>=bounds.left&&node.right<=bounds.right&&node.top>=bounds.top&&node.bottom<=bounds.bottom).length};
});}

try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v',{timeout:20000});
  await expect(card('check_valve')).toHaveCount(0);
  await nav('modules');await expect(card('check_valve')).toHaveAttribute('data-module-available','true');
  for(const id of ['check','sensor','pid','refprop']){
    await expect(card(id)).toHaveAttribute('data-module-available','false');
    await expect(card(id)).toContainText('旧参考对象');await expect(card(id).locator('[data-action="insert-module"]')).toHaveCount(0);
    await card(id).locator('[data-action="module-availability"]').click();await expect(dialog()).toContainText('未注册计算算法');
    evidence.legacyReferences.push(id);
    if(id==='check'){
      await expect(dialog().locator('[data-action="choose-module-alternative"][data-id="check_valve"]')).toBeVisible();
      await expect(dialog().locator('[data-id="refrigerant_check_valve"]')).toHaveCount(0);
      await snapshot('legacy-check-alternatives');await closeDialog();
    }else{
      await dialog().locator('[data-action="module-alternative-route"]').click();
      await expect(page.locator('#app-rail [aria-current="page"]')).toHaveAttribute('data-route',id==='refprop'?'settings':'controls');
      if(id==='refprop')await expect(page.locator('[data-action="settings-tab"][data-value="medium"]')).toHaveClass('active');
    }
    await nav('modules');
  }
  await card('check').locator('[data-action="edit-module"]').click();
  await expect(page.locator('[data-action="use-module"]')).toBeDisabled();
  await page.locator('.editor-tabs [data-value="code"]').click();await expect(page.locator('[data-builtin-code-notice]')).toContainText('不参与运行');
  await nav('workbench');await page.locator('.canvas-tools [data-action="toggle-library"]').click();
  if(!await page.locator('.canvas-library').isVisible())await page.locator('.canvas-tools [data-action="toggle-library"]').click();
  const reference=page.locator('.library-item[data-id="check"]');
  await expect(reference).toHaveAttribute('data-action','module-availability');await expect(reference).not.toHaveAttribute('draggable','true');
  await expect(reference).not.toHaveAttribute('data-drag-module','check');
  await reference.click();await dialog().locator('[data-action="choose-module-alternative"][data-id="check_valve"]').click();
  await expect(page.locator('[data-canvas-hint]')).toContainText('止回阀');
  const before=await page.locator('#network .net-node').count();
  await page.locator('#network').click({position:{x:30,y:50}});await expect(page.locator('#network .net-node')).toHaveCount(before+1);
  const inserted=await save(),owner=inserted.projects.find(p=>p.id===inserted.activeProject);
  expect(owner.pages.flatMap(p=>p.nodes).filter(n=>n.moduleId==='check_valve')).toHaveLength(1);
  expect(owner.moduleSnapshots.check_valve.runtime).toBe('python');evidence.replacementInserted=true;
  await page.locator('[data-action="undo"]').click();await expect(page.locator('#network .net-node')).toHaveCount(before);
  await nav('modules');await card('valve').locator('[data-action="edit-module"]').click();await page.locator('.editor-tabs [data-value="code"]').click();
  await expect(page.locator('[data-builtin-code-notice]')).toContainText('内置算法说明 · 只读');
  const code=page.locator('#module-code'),source=await code.inputValue();
  for(const area of await page.locator('.module-code-pane textarea').all())await expect(area).toHaveAttribute('readonly','');
  await code.focus();await page.keyboard.press('Control+A');await page.keyboard.press('Delete');await page.keyboard.press('Tab');
  expect(await code.inputValue()).toBe(source);
  await expect(page.locator('[data-action="insert-code-variable"]')).toHaveCount(0);
  await expect(page.locator('.editor-header [data-action="compile-preview"]')).toHaveCount(0);
  await expect(page.locator('.editor-header [data-action="save"]')).toHaveText('保存工作区');
  await snapshot('builtin-algorithm-readonly');evidence.builtinCodeReadOnly=true;
  await page.locator('[data-builtin-code-notice] [data-action="new-module"]').click();
  await dialog().locator('[name="name"]').fill('桌面入口验证阀');await dialog().locator('[name="code"]').fill('DESKTOP_ENTRY_VALVE');
  await dialog().locator('[name="base"]').selectOption('programmable_valve');await dialog().locator('[type="submit"]').click();
  await expect(dialog()).toHaveCount(0);await page.locator('.editor-tabs [data-value="code"]').click();
  await expect(code).not.toHaveAttribute('readonly','');await code.fill((await code.inputValue())+'\n# desktop entry authoring check\n');
  const published=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();expect((await published).ok()).toBe(true);
  await expect(page.locator('[data-action="use-module"]')).toBeEnabled();evidence.pythonAuthoringPublished=true;
  await nav('home');await page.locator('[data-action="start-modeling"]').click();
  await page.locator('.runbar [data-command="step"]').click();await expect(page.locator('#statusbar')).toContainText('已暂停',{timeout:20000});
  await page.locator('.runbar [data-command="stop"]').click();await expect(page.locator('.runbar [data-command="stop"]')).toBeDisabled();
  evidence.originalProjectStillRuns=true;
  for(const action of ['cs-create-multi','cs-create-continuous']){
    await nav('projects');await page.locator('[data-action="project-examples"]').click();await page.locator(`.example-card[data-action="${action}"]`).click();
    await expect(page.locator('.workbench')).toBeVisible({timeout:20000});
    await expect.poll(async()=>{const geometry=await visibleGeometry();return geometry.fullyVisible===geometry.nodes&&geometry.nodes>0;}).toBe(true);
    const geometry=await visibleGeometry();expect(geometry.viewBox).not.toBe('-35 -5 1140 510');
    const workspace=await save(),p=workspace.projects.find(p=>p.id===workspace.activeProject);
    for(const pg of p.pages){expect(pg.viewBounds).toHaveLength(4);expect(pg.zoom).toBe(1);expect(pg.pan).toEqual([0,0]);}
    evidence.sixRoomViews.push({action,...geometry});await snapshot(action+'-first-view');
    if(action==='cs-create-multi'){
      await nav('modules');await card('check').locator('[data-action="module-availability"]').click();
      await expect(dialog().locator('[data-action="choose-module-alternative"][data-id="refrigerant_check_valve"]')).toBeVisible();
      await expect(dialog().locator('[data-id="check_valve"]')).toHaveCount(0);await closeDialog();await nav('workbench');
    }
  }
  await page.reload();await expect.poll(async()=>{const geometry=await visibleGeometry();return geometry.fullyVisible===geometry.nodes&&geometry.nodes>0;},{timeout:20000}).toBe(true);
  evidence.sixRoomFitRestored=true;
  // Deliver a real committed save after the user replaces the local workspace through the UI.
  let held,release;const gate=new Promise(resolve=>release=resolve);
  await page.route('**/api/v1/workspace',async route=>{
    if(route.request().method()!=='POST'){await route.continue();return;}
    const response=await route.fetch();held={response,revision:(await response.json()).revision};await gate;await route.fulfill({response});
  });
  await page.locator('#app-header [data-action="save"]').click();await expect.poll(()=>!!held).toBe(true);
  await nav('settings');await page.locator('[data-action="settings-tab"][data-value="storage"]').click();
  await page.locator('[data-action="reset-prototype"]').click();await dialog().locator('[type="submit"]').click();
  await expect(page.locator('#app-rail [aria-current="page"]')).toHaveAttribute('data-route','home');
  release();await expect(page.locator('#statusbar [data-save-status]')).not.toContainText('正在保存');
  await expect(page.locator('#statusbar [data-save-status]')).toContainText('未保存');
  await page.unroute('**/api/v1/workspace');
  const nextRequest=page.waitForRequest(r=>r.url().endsWith('/api/v1/workspace')&&r.method()==='POST');
  await page.locator('#app-header [data-action="save"]').click();const payload=(await nextRequest).postDataJSON();
  expect(payload.data.workspaceRevision).not.toBe(held.revision);expect(payload.expected_revision).toBe(0);
  expect(payload.data.activeProject).toBe('water-net');await expect(page.locator('#statusbar [data-save-status]')).toContainText('保存失败');
  evidence.lateSaveDoesNotMarkReplacementSaved=true;evidence.replacementConflictPreservesDraft=true;
  expect(errors).toEqual([]);evidence.errors=errors;writeFileSync(output+'/verification.json',JSON.stringify(evidence,null,2)+'\n');
  console.log(JSON.stringify(evidence));
}catch(error){console.error(error,errors);await snapshot('failure').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
