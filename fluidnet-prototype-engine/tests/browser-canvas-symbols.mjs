import {chromium,expect} from '@playwright/test';
import {readFileSync,mkdtempSync,mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.locator('#dialog-form button[type="submit"]').click();
const owner=state=>state.projects.find(p=>p.id===state.activeProject);
const api=async path=>{const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();};
async function save(){
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await receipt).ok()).toBe(true);
  return (await api('/workspace')).data;
}
async function editModule(){
  await nav('modules');await page.locator('[data-module-id="design_valve"] [data-action="edit-module"]').click();
  await page.locator('[data-action="editor-tab"][data-value="drawing"]').first().click();
}
async function authorDrawing(){
  await page.locator('[data-action="select-picture"]').click();
  await page.locator('[data-drawing-field="shape"]').selectOption('circle');
  await page.locator('[data-drawing-field="width"]').fill('50');await page.locator('[data-drawing-field="width"]').blur();
  await page.locator('[data-drawing-field="height"]').fill('45');await page.locator('[data-drawing-field="height"]').blur();
  await page.locator('[data-drawing-field="label"]').fill('作者阀图');await page.locator('[data-drawing-field="label"]').blur();
  for(const [id,x,y] of [['in0','10','25'],['out0','90','75']]){
    await page.locator(`#module-drawing [data-draw-id="${id}"]`).click();
    await page.locator(`[data-port-field="x"][data-id="${id}"]`).fill(x);await page.locator(`[data-port-field="x"][data-id="${id}"]`).blur();
    await page.locator(`[data-port-field="y"][data-id="${id}"]`).fill(y);await page.locator(`[data-port-field="y"][data-id="${id}"]`).blur();
  }
}
async function checkDrawing(rotation){
  const node=page.locator('#network [data-node="V1"]'),shape=node.locator('[data-canvas-family]');
  await expect(shape).toHaveAttribute('transform',`rotate(${rotation})`);
  await expect(shape.locator('ellipse')).toHaveAttribute('rx','22.5');await expect(shape.locator('ellipse')).toHaveAttribute('ry','13.5');
  await expect(shape).toContainText('作者阀图');
  for(const [id,x,y] of [['in0',-43.2,-16.125],['out0',43.2,16.125]]){
    const point=await node.locator(`[data-port-id="${id}"] circle.net-port`).evaluate(p=>({x:Number(p.getAttribute('cx')),y:Number(p.getAttribute('cy'))}));
    expect(point.x).toBeCloseTo(x,9);expect(point.y).toBeCloseTo(y,9);
  }
  const gaps=await page.evaluate(()=>{
    const screen=(element,x,y)=>new DOMPoint(x,y).matrixTransform(element.getScreenCTM());
    return [['e2','in0',true],['e3','out0',false]].map(([edge,port,last])=>{
      const circle=document.querySelector(`#network [data-port-node="V1"][data-port-id="${port}"] circle.net-port`);
      const line=document.querySelector(`#network [data-trace-edge="${edge}"]`),length=line.getTotalLength();
      const endpoint=line.getPointAtLength(last?length:0),a=screen(line,endpoint.x,endpoint.y),b=screen(circle,Number(circle.getAttribute('cx')),Number(circle.getAttribute('cy')));
      return Math.hypot(a.x-b.x,a.y-b.y);
    });
  });
  for(const gap of gaps)expect(gap).toBeLessThan(.01);
}
async function importProject(data,name='project.json'){
  await nav('projects');await page.locator('[data-action="wf-import"]').click();
  await page.getByLabel('单项目文件').setInputFiles({name,mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});
  await submit();await expect(page.locator('#toast')).toContainText('项目已导入');await nav('workbench');
}
try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await editModule();await authorDrawing();
  const configured=await save(),draft=configured.modules.find(m=>m.id==='design_valve');
  expect(draft.drawing).toEqual({shape:'circle',width:50,height:45,label:'作者阀图'});
  const receipt=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();const published=await receipt;
  expect(published.status(),await published.text()).toBe(201);const release=(await published.json()).module;
  await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
  const afterPublish=await save();expect(afterPublish.modules.find(m=>m.id==='design_valve').drawing).toEqual(draft.drawing);
  await nav('modules');await page.locator('[data-module-id="design_valve"] [data-action="module-example"]').click();
  await expect(page.locator('#network [data-node="V1"]')).toBeVisible();await checkDrawing(0);
  let current=owner(await save()),snapshot=current.moduleSnapshots.design_valve;
  expect(snapshot.drawing).toEqual(draft.drawing);expect(snapshot.manifest.content_hash).toBe(release.content_hash);
  expect(snapshot.ports.map(p=>[p.id,p.x,p.y])).toEqual([['in0',10,25],['out0',90,75]]);
  await page.locator('#network [data-node="V1"]').click();await page.locator('[data-action="rotate-device"][data-id="V1"]:not([data-direction])').click();await checkDrawing(90);
  current=owner(await save());expect(current.pages[0].edges).toHaveLength(3);
  await captureFhd(page,'artifacts/canvas-author-layout-1080p.png');
  // A later library presentation edit must not alter the existing project's frozen drawing.
  await editModule();await page.locator('[data-action="select-picture"]').click();
  await page.locator('[data-drawing-field="shape"]').selectOption('rectangle');await page.locator('[data-drawing-field="width"]').fill('35');await page.locator('[data-drawing-field="width"]').blur();
  await save();await nav('workbench');await checkDrawing(90);
  await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${current.id}"]`).click();
  const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
  const file=join(mkdtempSync(join(tmpdir(),'canvas-symbols-')),'author-layout.json');await(await download).saveAs(file);
  const document=JSON.parse(readFileSync(file,'utf8'));expect(document.project.moduleSnapshots.design_valve.drawing).toEqual(draft.drawing);
  await page.locator('[data-action="close-dialog"]').last().click();await importProject(document,'author-layout.json');await checkDrawing(90);
  await save();await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');await nav('workbench');await checkDrawing(90);
  current=owner(await save());expect(current.moduleSnapshots.design_valve.drawing).toEqual(draft.drawing);
  expect(current.moduleSnapshots.design_valve.manifest.definition_hash).toBe(snapshot.manifest.definition_hash);
  // Existing generic author modules use their label as the fallback, never a meaningless function glyph.
  await nav('modules');await page.locator('[data-module-id="flow_limiter"] [data-action="module-example"]').click();
  const unknown=page.locator('#network [data-node="V1"] [data-canvas-family="module"]');await expect(unknown).toBeVisible();await expect(unknown.locator('text')).not.toBeEmpty();await expect(unknown).not.toContainText('ƒ');
  const cold=await api('/examples/refrigeration-modular-room');await importProject(cold,'cold-glyphs.json');await page.locator('[data-action="fit"]').click();
  const expected={refrigerant_compressor:'compressor',evaporative_condenser:'condenser',hp_receiver:'tank',lp_drum:'tank',refrigerant_pump:'pump',expansion_valve:'valve',air_cooler:'coil',cold_room:'room'};
  for(const item of cold.instances){if(expected[item.module_id])await expect(page.locator(`#network [data-node="${item.id}"] [data-canvas-family]`)).toHaveAttribute('data-canvas-family',expected[item.module_id]);}
  await captureFhd(page,'artifacts/canvas-cold-equipment-1080p.png');expect(errors).toEqual([]);
  const result={authorLayout:true,publishedPresentation:true,frozenPresentation:true,rotatedConnections:true,exportImport:true,reload:true,genericFallback:true,coldEquipmentFamilies:true,errors};
  mkdirSync('artifacts',{recursive:true});writeFileSync('artifacts/canvas-symbols-ui.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}catch(error){console.error(error);await captureFhd(page,'artifacts/canvas-symbols-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
