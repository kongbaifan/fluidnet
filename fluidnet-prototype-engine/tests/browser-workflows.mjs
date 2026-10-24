import {testServer} from './browser-server.mjs';
import {chromium,expect} from '@playwright/test';
import {mkdirSync,mkdtempSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const fixture=await testServer(),base=fixture.base;
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1700,height:1100}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const api=async(path,body)=>{const response=await fetch(base+'/api/v1'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!response.ok)throw Error(await response.text());return response.json();};
const close=async()=>{if(await page.getByRole('dialog').count())await page.getByRole('dialog').locator('[data-action="close-dialog"]').first().click();};
const manage=async id=>{await close();await page.goto(base+'/#projects');await page.locator(`[data-action="wf-manage"][data-id="${id}"]`).click();};
async function saveProject(id){await manage(id);const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/projects/'+id&&r.request().method()==='POST');await page.locator('[data-action="wf-save"]').click();expect((await response).status()).toBe(200);await expect(page.locator('#toast')).toContainText('项目已保存');await close();}
const runButton=()=>page.locator('[data-action="run-project"][data-command="run"]').first();
async function run(){const created=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');await runButton().click();const id=(await (await created).json()).run_id;await expect.poll(async()=> (await api('/runs/'+id)).status,{timeout:20000}).toBe('completed');return id;}
try{
  await page.goto(base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await saveProject('water-net');
  const first=await api('/projects/water-net');
  const other=await api('/projects/heat-loop');other.document.project.name='并发修改的换热项目';
  await api('/projects/heat-loop',{document:other.document,expected_revision:other.revision});
  await manage('water-net');await page.locator('[data-action="wf-rename"]').click();await page.getByLabel('项目名称',{exact:true}).fill('水网独立保存');await page.getByRole('dialog').locator('button[type="submit"]').click();
  await saveProject('water-net');expect((await api('/projects/heat-loop')).document.project.name).toBe('并发修改的换热项目');
  await manage('water-net');await page.locator('[data-action="wf-history"]').click();await page.locator(`[data-action="wf-restore"][data-revision="${first.revision}"]`).click();await page.getByRole('dialog').locator('button[type="submit"]').click();
  await expect.poll(async()=> (await api('/projects/water-net')).document.project.name).toBe(first.document.project.name);

  await page.goto(base+'/#workbench');await page.locator('[data-action="wf-scenarios"]').first().click();await page.locator('[data-action="wf-new-scenario"]').click();
  await page.getByLabel('工况名称',{exact:true}).fill('节流 25%');await page.getByLabel('工况设备').selectOption('V1');await page.getByLabel('工况参数').selectOption('opening');await page.getByLabel('覆盖值',{exact:true}).fill('25');await page.locator('[data-action="wf-add-override"]').click();await page.getByRole('dialog').locator('button[type="submit"]').click();await expect(page.locator('#toast')).toContainText('工况已应用');
  await page.goto(base+'/#settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();await page.locator('[data-solver-field="mode"]').selectOption('dynamic');await page.locator('[data-solver-field="duration"]').fill('1');await page.locator('[data-solver-field="duration"]').blur();
  await saveProject('water-net');
  await page.goto(base+'/#workbench');const throttled=await run();
  const throttledRecord=await api('/runs/'+throttled);expect(throttledRecord.request.scenario_id).toBeTruthy();expect(throttledRecord.frame.variables['V1.param.opening_ratio']).toBe(.25);expect(throttledRecord.request.project_revision).toBeTruthy();
  await page.getByLabel('运行工况').selectOption('');await saveProject('water-net');await page.goto(base+'/#workbench');const baseline=await run();
  expect((await api('/runs/'+baseline)).frame.variables['V1.mass_flow_kg_s']).toBeGreaterThan(throttledRecord.frame.variables['V1.mass_flow_kg_s']);
  expect((await api('/projects/water-net')).document.project.pages[0].nodes.find(n=>n.id==='V1').params.opening).toBe(80);
  await page.goto(base+'/#curves');await page.locator('[data-action="wf-refresh-runs"]').click();await page.getByLabel('运行 A',{exact:true}).selectOption(baseline);await page.getByLabel('运行 B',{exact:true}).selectOption(throttled);await page.locator('[data-action="wf-compare"]').click();await expect(page.locator('[data-comparison-series]')).toHaveCount(2);for(const curve of await page.locator('[data-comparison-series]').all())await expect(curve).toHaveAttribute('d',/L/);await expect(page.locator('#wf-comparison-result')).toContainText('节流 25%');
  mkdirSync('artifacts',{recursive:true});await page.screenshot({path:'artifacts/workflows-comparison.png',fullPage:true});

  await manage('water-net');const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();const file=await download,path=join(mkdtempSync(join(tmpdir(),'fluidnet-project-')),'project.json');await file.saveAs(path);expect(JSON.parse(readFileSync(path)).project.scenarios).toHaveLength(1);
  await close();await page.locator('[data-action="wf-import"]').click();await page.getByLabel('单项目文件').setInputFiles(path);await page.getByRole('dialog').locator('button[type="submit"]').click();await expect(page.locator('#toast')).toContainText('项目已导入');
  const imported=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')).activeProject);expect(imported).not.toBe('water-net');await saveProject(imported);
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await manage(imported);await page.locator('[data-action="wf-delete"]').click();await page.getByRole('dialog').locator('button[type="submit"]').click();await expect.poll(async()=> (await api('/projects')).projects.some(p=>p.id===imported)).toBe(false);

  await page.goto(base+'/#modules');await page.locator('[data-module-id="programmable_valve"] [data-action="module-example"]').click();
  await page.locator('[data-action="save"]').first().click();await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
  const state=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1'))),id=state.activeProject;
  // Seeds may already ship several versions (e.g. SDK v2); upgrade from the pinned one to a fresh latest.
  const pinned=state.projects.find(p=>p.id===id).moduleSnapshots.programmable_valve.version;
  const latest=Math.max(...(await api('/modules/programmable_valve/versions')).versions.map(v=>Number(v.package.version.split('.')[0]))),next=latest+1;
  const release=await api('/modules/programmable_valve/versions/'+pinned);const module=release.module;module.content_hash=null;module.definition_hash=null;module.parameters.push({id:'gain',label:'新增增益',value_type:'number',default:2.0});
  await api('/modules/versions',{module,expected_latest_version:latest,release_notes:'兼容增加参数'});
  await page.locator('[data-action="wf-upgrades"]').click();await page.locator('[data-action="wf-module-versions"]').click();await page.locator(`[data-action="wf-preview-upgrade"][data-version="${next}"]`).click();await expect(page.getByRole('dialog')).toContainText('兼容检查通过');await page.screenshot({path:'artifacts/workflows-upgrade.png',fullPage:true});await page.getByRole('dialog').locator('button[type="submit"]').click();await expect(page.locator('#toast')).toContainText('模块版本已更新并保存');
  const upgraded=await api('/projects/'+id);expect(upgraded.document.project.moduleSnapshots.programmable_valve.version).toBe(next);expect(upgraded.document.project.pages[0].nodes.find(n=>n.id==='V1').params.gain).toBe(2);
  await manage(id);await page.locator('[data-action="wf-history"]').click();await page.locator(`[data-action="wf-restore"][data-revision="${upgraded.revision-1}"]`).click();await page.getByRole('dialog').locator('button[type="submit"]').click();await expect.poll(async()=> (await api('/projects/'+id)).document.project.moduleSnapshots.programmable_valve.version).toBe(pinned);
  expect(errors).toEqual([]);console.log(JSON.stringify({project:id,baseline,throttled,upgrade:`v${pinned} -> v${next} -> v${pinned}`,errors}));
}catch(error){mkdirSync('artifacts',{recursive:true});await page.screenshot({path:'artifacts/workflows-failure.png',fullPage:true});console.error(errors);throw error;}
finally{await browser.close();await fixture.close();}
