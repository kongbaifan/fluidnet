import {chromium,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
const dialog=()=>page.getByRole('dialog'),panel=()=>page.locator('[data-float-id="V1"]');
const submit=()=>dialog().locator('button[type="submit"]').click();
const close=()=>dialog().locator('[data-action="close-dialog"]').last().click();
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const action=(name)=>dialog().locator(`[data-performance-action="${name}"]`);
const owner=s=>s.projects.find(p=>p.id===s.activeProject),node=s=>owner(s).pages.flatMap(p=>p.nodes).find(n=>n.id==='V1');
const csv='flow,value\n0,30\n2,20\n4,0\n';
async function saved(){
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await receipt).ok()).toBe(true);
  return page.evaluate(()=>window.FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
}
async function library(){await panel().locator('[data-action="performance-library"]').click();await expect(dialog()).toContainText('导入CSV / JSON');}
const record=version=>dialog().locator(`[data-performance-record="browser_curve"][data-performance-version="${version}"]`);
async function importPreview({version=1,invalid=false}={}){
  if(version===1)await action('import').click();else await record(1).locator('[data-performance-action="version"]').click();
  const data=version===1?csv:JSON.stringify([[0,32],[2,21],[4,0]]);
  await dialog().getByLabel('性能曲线文件',{exact:true}).setInputFiles({name:version===1?'泵测试.csv':'泵测试.json',mimeType:'text/plain',buffer:Buffer.from(invalid?'flow,value\n0,30\n0,20\n':data)});
  if(version===1)await dialog().locator('[name="id"]').fill('browser_curve');
  await dialog().locator('[name="name"]').fill('浏览器教学泵');
  await dialog().locator('[name="format"]').selectOption(version===1?'csv':'json');
  await dialog().locator('[name="flow_unit"]').selectOption('L/s');
  await dialog().locator('[name="source"]').fill('浏览器验收自建数据，非厂家性能');
  await submit();await expect(dialog()).toContainText(invalid?'资料校验未通过':'性能资料预览');
  if(!invalid)await expect(dialog()).toContainText('14.4');
}
async function propose(version){
  await record(version).locator('[data-performance-action="apply"]').click();
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/performance-data/proposal');
  await submit();const response=await receipt;expect(response.ok(),await response.text()).toBe(true);
  await expect(dialog()).toContainText('性能资料应用预览');await dialog().locator('[data-performance-reference-confirm]').check();return response.request().postDataJSON();
}
try{
  await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await nav('modules');await page.locator('[data-module-id="design_pump"] [data-action="module-example"]').click();
  await page.locator('[data-node="V1"]').dblclick();const before=await saved();
  await library();await importPreview();await close();
  expect((await (await page.request.get(server.base+'/api/v1/performance-data')).json()).items).toHaveLength(0);
  await library();await importPreview({invalid:true});await close();
  expect((await (await page.request.get(server.base+'/api/v1/performance-data')).json()).items).toHaveLength(0);
  await library();await importPreview();await submit();await expect(record(1)).toBeVisible();
  await importPreview({version:2});await submit();await expect(record(2)).toBeVisible();
  await action('compare').click();await dialog().locator('[name="a"]').selectOption('0');await dialog().locator('[name="b"]').selectOption('1');await submit();
  await expect(dialog().locator('[data-performance-comparison]')).toContainText('分段线性插值');await captureFhd(page,'artifacts/performance-comparison-1080p.png');await close();
  await library();await record(1).locator('[data-performance-action="view"]').click();
  const exportEvent=page.waitForEvent('download');await action('export').click();
  const exported=await exportEvent;expect(await readFile(await exported.path(),'utf8')).toBe(csv);await close();
  await library();const request=await propose(1);expect(request.module.definition_hash).toBe(owner(before).moduleSnapshots.design_pump.manifest.definition_hash);
  await close();let current=await saved();expect(node(current).params).toEqual(node(before).params);expect(node(current).draft).toEqual(node(before).draft);
  await library();await propose(1);await submit();current=await saved();
  expect(node(current).params).toEqual(node(before).params);expect(node(current).draft.head_curve).toEqual([[0,30],[7.2,20],[14.4,0]]);
  expect(node(current).performanceDataDraft.head_curve.provenance.version).toBe(1);expect(node(current).performanceData).toBeUndefined();
  await panel().locator('[data-action="equipment-selection"]').click();
  await dialog().locator('[name="selection:design_flow_m3_s"]').fill('8');await dialog().locator('[name="selection:design_head_m"]').fill('15');
  const design=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/modules/design');await submit();expect((await design).ok()).toBe(true);
  await expect(dialog()).toContainText('选型结果预览');await dialog().getByLabel('型号名称',{exact:true}).fill('带性能资料的选型型号');await submit();
  current=await saved();expect(current.models.find(m=>m.name==='带性能资料的选型型号').selection.performanceData.head_curve.provenance.version).toBe(1);
  await panel().locator('[data-action="save-instance-model"]').click();await dialog().locator('[name="name"]').fill('性能资料草稿型号');await dialog().locator('[name="source"]').selectOption('draft');await submit();
  current=await saved();let model=current.models.find(m=>m.name==='性能资料草稿型号');
  expect(model.params.head_curve).toEqual(node(current).draft.head_curve);expect(model.params.data_source).toContain('自建数据');expect(model.performanceData.head_curve.provenance.version).toBe(1);
  await panel().locator('[data-action="apply-instance"]').click();await submit();current=await saved();expect(node(current).params.head_curve).toEqual(model.params.head_curve);
  await library();await propose(2);await submit();
  await panel().locator('[data-action="equipment-provenance"]').click();await expect(dialog()).toContainText('当前参数资料');await expect(dialog()).toContainText('"version": 2');await expect(dialog()).toContainText('"version": 1');await close();
  await nav('models');await page.locator(`[data-action="focus-model"][data-id="${model.id}"]`).first().click();await expect(page.locator('[data-model-performance-source]')).toContainText('浏览器教学泵 v1');
  await page.locator(`[data-action="edit-model"][data-id="${model.id}"]`).click();await submit();
  current=await saved();model=current.models.find(m=>m.id===model.id);expect(model.version).toBe(2);expect(model.params.head_curve).toEqual([[0,30],[7.2,20],[14.4,0]]);expect(model.performanceData.head_curve.provenance.version).toBe(1);
  await page.locator(`[data-action="insert-model"][data-id="${model.id}"]`).click();current=await saved();
  const inserted=owner(current).pages.flatMap(p=>p.nodes).find(n=>n.id!=='V1'&&n.modelId===model.id);expect(inserted.performanceData).toEqual(model.performanceData);expect(inserted.params.head_curve).toEqual(model.params.head_curve);
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  const restored=await saved();expect(node(restored).performanceData).toEqual(node(current).performanceData);expect(node(restored).performanceDataDraft).toEqual(node(current).performanceDataDraft);expect(restored.models.find(m=>m.id===model.id)).toEqual(model);
  await nav('workbench');await page.locator('[data-node="V1"]').dblclick();
  await panel().locator('[data-action="apply-instance"]').click();await submit();
  await library();await importPreview({version:3});await submit();await expect(record(3)).toBeVisible();await propose(3);await submit();
  current=await saved();expect(node(current).params).toEqual(node(current).draft);
  expect(node(current).performanceData.head_curve.provenance.version).toBe(2);expect(node(current).performanceDataDraft.head_curve.provenance.version).toBe(3);
  await expect(panel().locator('[data-action="apply-instance"]')).toBeEnabled();
  await panel().locator('[data-action="save-instance-model"]').click();await dialog().locator('[name="name"]').fill('同点新来源仍只保存当前');await submit();
  current=await saved();expect(current.models.find(m=>m.name==='同点新来源仍只保存当前').performanceData.head_curve.provenance.version).toBe(2);
  await panel().locator('[data-action="apply-instance"]').click();await submit();current=await saved();expect(node(current).performanceData.head_curve.provenance.version).toBe(3);expect(node(current).performanceDataDraft).toBeUndefined();
  await captureFhd(page,'artifacts/performance-device-1080p.png');
  expect(errors).toEqual([]);console.log(JSON.stringify({importPreviewCancel:true,invalidUnchanged:true,immutableVersions:true,compare:true,exportOriginal:true,frozenDefinition:true,draftOnly:true,modelCurveAndSource:true,designModelSource:true,sourceOnlyExplicitApply:true,reload:true,errors}));
}catch(error){console.error(error);await captureFhd(page,'artifacts/performance-data-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
