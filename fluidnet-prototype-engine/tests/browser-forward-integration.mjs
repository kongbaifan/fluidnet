import {chromium,expect} from '@playwright/test';
import {mkdtempSync,readFileSync,writeFileSync,mkdirSync} from 'node:fs';import {join} from 'node:path';import {tmpdir} from 'node:os';
import {testServer} from './browser-server.mjs';import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click(),submit=()=>page.locator('#dialog-form button[type="submit"]').click(),close=()=>page.locator('[data-action="close-dialog"]').last().click();
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();};
async function save(){const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');await page.locator('[data-action="save"]').first().click();expect((await response).ok()).toBe(true);const s=(await api('/workspace')).data;return s.projects.find(p=>p.id===s.activeProject);}
async function run(){await nav('workbench');const requested=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');await page.locator('[data-action="run-project"][data-command="run"]').first().click();const rid=(await(await requested).json()).run_id;let record;
 await expect.poll(async()=>{record=await api('/runs/'+rid);if(record.status==='failed')throw Error(JSON.stringify(record.frame.diagnostics));return record.status;},{timeout:45000}).toBe('completed');await expect(page.locator('#statusbar')).toContainText('已完成');return record;}
try{
 await page.goto(server.base+'/#modules');await expect(page.locator('[data-action="equipment-library"]')).toBeVisible();await page.locator('[data-action="equipment-library"]').click();
 await page.getByLabel('设备组模板',{exact:true}).selectOption('group_pump_branch');await page.getByLabel('实例前缀',{exact:true}).fill('System');await submit();await expect(page.locator('.net-node[data-node="System-Equipment"]')).toBeVisible();
 const original=await save();
 await page.locator('[data-action="project-group-tools"]').click();for(const cb of await page.getByRole('dialog').locator('input[type="checkbox"]').all())await cb.check();await submit();await expect(page.getByRole('dialog')).toContainText('2 条内部连线');await submit();
 const copied=await save(),groups=copied.pages.flatMap(g=>g.nodes).filter(n=>n.moduleId==='group_pump_branch');expect(groups).toHaveLength(2);expect(copied.pages.flatMap(g=>g.edges)).toHaveLength(4);
 await page.locator('[data-action="device-batch-edit"]').click();await page.getByLabel('批量设备模块',{exact:true}).selectOption('group_pump_branch');await submit();
 await page.getByLabel('修改 Pump · 转速比',{exact:true}).check();await page.getByLabel('批量 Pump · 转速比',{exact:true}).fill('.9');await submit();await submit();await expect(page.getByRole('dialog')).toHaveCount(0);
 const changed=await save();for(const n of changed.pages.flatMap(g=>g.nodes).filter(n=>n.moduleId==='group_pump_branch'))expect(n.params.Pump_speed_ratio).toBe(.9);
 await page.locator('[data-action="project-find"]').click();await page.getByLabel('全项目查找关键词').fill('System-Equipment');await page.locator('[data-action="project-find-node"][data-id="System-Equipment"]').click();
 const panel=page.locator('[data-float-id="System-Equipment"]');await panel.locator('[data-action="configure-device-panel"]').click();const config=page.getByRole('dialog');
 for(const cb of await config.locator('[data-panel-config] input[type="checkbox"]').all())await cb.uncheck();
 const speed=config.locator('[data-panel-config-row="Pump_speed_ratio"]');await speed.locator('input[type="checkbox"]').check();await speed.locator('select').selectOption('slider');await speed.locator('input[aria-label$="分组"]').fill('泵组操作');
 const flow=config.locator('[data-panel-config-row="in0:FLOW"]');await flow.locator('input[type="checkbox"]').check();await flow.locator('input[aria-label$="分组"]').fill('实际流量');await submit();
 await panel.locator('[data-action="float-tab"][data-value="overview"]').click();await expect(panel.locator('[data-panel-parameter-group="泵组操作"]')).toBeVisible();await panel.locator('[data-action="float-close"]').click();
 const first=await run();await save();
 await nav('runs');await page.locator('[data-action="refresh-archives"]').click();await page.locator(`[data-action="open-archive"][data-id="${first.id}"]`).click();
 await page.locator(`[data-action="inspect-run"][data-id="${first.id}"]`).click();await expect(page.locator('[data-system-inspection]')).toContainText(first.id);await expect(page.locator('[data-system-inspection]')).toContainText('System-Equipment');await captureFhd(page,'artifacts/forward-integration-inspection.png');await close();
 const dir=mkdtempSync(join(tmpdir(),'forward-integration-'));
 for(const format of ['html','csv']){const download=page.waitForEvent('download');await page.locator(`[data-action="archive-report"][data-id="${first.id}"][data-format="${format}"]`).click();const file=join(dir,'report.'+format);await(await download).saveAs(file);expect(readFileSync(file,'utf8')).toContain(first.id);expect(readFileSync(file,'utf8')).toContain('System-Equipment');}
 await nav('workbench');await page.locator('[data-action="run-project"][data-command="stop"]').first().click();await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${original.id}"]`).click();
 const downloaded=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();const exportFile=join(dir,'project.json');await(await downloaded).saveAs(exportFile);await close();
 await page.locator('[data-action="wf-import"]').click();await page.getByLabel('单项目文件').setInputFiles(exportFile);await submit();await expect(page.locator('#toast')).toContainText('项目已导入');const restored=await save();expect(restored.id).not.toBe(original.id);expect(restored.moduleSnapshots.group_pump_branch.panelLayout).toBeTruthy();
 await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');const second=await run();
 for(const [key,value] of Object.entries(first.frame.variables))if(typeof value==='number')expect(second.frame.variables[key],key).toBeCloseTo(value,6);
 await expect(page.locator('.net-node[data-node="System-Equipment"]')).toBeVisible();await page.locator('.net-node[data-node="System-Equipment"]').dblclick();await page.locator('[data-float-id="System-Equipment"] [data-action="float-tab"][data-value="overview"]').click();await expect(page.locator('[data-panel-result-group="实际流量"]')).toBeVisible();await captureFhd(page,'artifacts/forward-integration-final.png');
 expect(errors).toEqual([]);mkdirSync('artifacts',{recursive:true});const evidence={library:'group_pump_branch',copies:2,groupNodes:groups.map(n=>n.id),firstRun:first.id,reloadedRun:second.id,reports:['html','csv'],sameVariables:true,errors};writeFileSync('artifacts/forward-integration.json',JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}catch(e){console.error(e);await captureFhd(page,'artifacts/forward-integration-failure.png').catch(()=>{});process.exitCode=1;}finally{await browser.close();await server.close();}
