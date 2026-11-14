import {chromium,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const importLimitBytes=64*1024*1024;
const page=await browser.newPage({viewport:{width:1920,height:1080}}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
await page.addInitScript(({limit})=>{
  const read=File.prototype.text;
  const size=Object.getOwnPropertyDescriptor(Blob.prototype,'size').get;
  // Exercise the exact size boundary without transferring a 64 MiB test buffer.
  Object.defineProperty(File.prototype,'size',{get(){
    if(this.name==='too-large.json')return limit+1;
    if(this.name==='at-limit.json')return limit;
    return size.call(this);
  }});
  window.__settingsFileReads={};
  File.prototype.text=function(){
    if(this.name==='unreadable.json')return Promise.reject(Error('受控文件读取失败'));
    if(this.name==='delayed.json')return new Promise((resolve,reject)=>{
      window.__settingsFileReads.release=()=>read.call(this).then(resolve,reject);
    });
    return read.call(this);
  };
},{limit:importLimitBytes});
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const setting=async tab=>{await nav('settings');await page.locator(`[data-action="settings-tab"][data-value="${tab}"]`).click();};
const owner=state=>state.projects.find(project=>project.id===state.activeProject);
const dialog=()=>page.getByRole('dialog');
const submit=()=>page.locator('#dialog-form button[type="submit"]');
const chooser=()=>page.locator('#dialog-form input[name="file"]');
const preview=()=>page.locator('#import-preview');
const cancel=()=>dialog().locator('[data-action="close-dialog"]').first().click();
const file=(data,name='prototype.json')=>({name,mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});
async function save(){
  const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await response).ok()).toBe(true);
  await expect(page.locator('#toast')).toContainText('工作区已保存');
  return (await(await page.request.get(server.base+'/api/v1/workspace')).json()).data;
}
async function openVariables(){
  // A reload first renders the local draft; server initialization replaces it.
  // Wait for the existing ready header before opening a transient device window.
  await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await nav('workbench');await page.locator('.net-node[data-node="V1"]').dblclick();
  await page.locator('[data-float-id="V1"] [data-action="float-tab"][data-value="variables"]').click();
}
async function downloadedWorkspace(format='prototype'){
  await setting('storage');
  const pending=page.waitForEvent('download');await page.locator(`[data-action="export"][data-format="${format}"]`).click();
  const path=await(await pending).path();
  return {path,bytes:readFileSync(path)};
}
async function openImport(){
  await setting('storage');await page.locator('[data-action="import"]').click();
  await expect(submit()).toBeDisabled();
}
async function chooseValid(data,name){
  await chooser().setInputFiles(file(data,name));
  await expect(preview()).toContainText('确认后替换当前原型草稿');
  await expect(submit()).toBeEnabled();
}
async function chooseDownloaded(artifact){
  // Re-import the actual downloaded file without parsing or reformatting its bytes.
  await chooser().setInputFiles(artifact.path);
  expect(await chooser().evaluate(el=>el.files[0].size)).toBe(artifact.bytes.length);
  await expect(preview()).toContainText('确认后替换当前原型草稿');
  await expect(submit()).toBeEnabled();
}
try{
  await page.goto(server.base+'/#workbench');await expect(page.locator('#network')).toBeVisible();
  const baseline=await save(),active=owner(baseline),valve=active.pages.flatMap(p=>p.nodes).find(n=>n.id==='V1');
  const defaultPrecision=active.moduleSnapshots.valve.precision;
  const currentValue=()=>page.locator('[data-float-id="V1"] [data-instance-live="param:opening"]');
  await openVariables();await expect(currentValue()).toHaveText(valve.params.opening.toFixed(defaultPrecision));
  for(const digits of [2,4,6,8]){
    await setting('appearance');await page.locator('[data-module-precision]').selectOption(String(digits));
    await openVariables();await expect(currentValue()).toHaveText(valve.params.opening.toFixed(digits));
    await expect(page.locator('[data-float-id="V1"] [data-instance-live="system:mix"]')).toHaveText([1,0,0,0,0,0,0,0].map(n=>n.toFixed(digits)).join(', '));
    await expect(page.locator('[data-float-id="V1"] [data-instance-live="system:form"]')).toHaveText('125, 0, 0, 0, 0, 0, 0, 0');
  }
  await nav('modules');await page.locator('[data-module-id="valve"] [data-action="edit-module"]').click();
  await page.locator('[data-action="editor-tab"][data-value="values"]').click();
  const module=baseline.modules.find(m=>m.id==='valve');
  await expect(page.locator('[data-value-id="param:opening"][data-bank="-1"]')).toHaveValue(module.values['param:opening'].toFixed(8));
  await expect(page.locator('.array-btn[data-id="system:mix"]').first()).toHaveText([1,0,0,0,0,0,0,0].map(n=>n.toFixed(8)).join(', '));

  await setting('appearance');await page.locator('[data-theme-select]').selectOption('dark');await page.locator('[data-ui-toggle="pageGrid"]').check();
  const persisted=await save();
  expect(persisted.modules.map(m=>[m.id,m.precision])).toEqual(baseline.modules.map(m=>[m.id,m.precision]));
  expect(owner(persisted).moduleSnapshots).toEqual(active.moduleSnapshots);
  await page.reload();await expect(page.locator('[data-module-precision]')).toHaveValue('8');
  await expect(page.locator('#fn-studio')).toHaveAttribute('data-theme','dark');await expect(page.locator('[data-ui-toggle="pageGrid"]')).toBeChecked();
  await openVariables();await expect(currentValue()).toHaveText(valve.params.opening.toFixed(8));await expect(page.locator('#network-area')).toHaveClass(/grid/);
  await setting('appearance');await page.locator('[data-module-precision]').selectOption('');
  await openVariables();await expect(currentValue()).toHaveText(valve.params.opening.toFixed(defaultPrecision));
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1-ui')).modulePrecision)).toBeNull();

  const originalExport=await downloadedWorkspace(),exported=JSON.parse(originalExport.bytes.toString('utf8'));
  const author=exported.modules.find(m=>m.runtime==='python'&&!m.manifest?.execution_role&&m.manifest?.parameters.some(p=>p.value_type==='number'));
  expect(author).toBeTruthy();
  const parameter=author.manifest.parameters.find(p=>p.value_type==='number');
  await nav('bench');await page.locator('[data-bench-module]').selectOption(author.id);
  const benchField=()=>page.locator(`[data-bench-param="${parameter.id}"]`).first();
  const originalField=await benchField().evaluate(el=>({label:el.closest('label').textContent,min:el.min,max:el.max}));
  // Both a failed preview and a valid preview that is cancelled must leave loaded definitions intact.
  for(const invalid of [true,false]){
    const incoming=structuredClone(exported),changed=incoming.modules.find(m=>m.id===author.id);
    changed.manifest.parameters.find(p=>p.id===parameter.id).label='不应写入当前模块的导入预览';
    if(invalid)changed.precision=99;
    await openImport();await chooser().setInputFiles(file(incoming,invalid?'invalid-definition.json':'cancelled-definition.json'));
    if(invalid){await expect(preview()).toContainText('检查失败：显示精度不合法');await expect(submit()).toBeDisabled();}
    else {await expect(preview()).toContainText('确认后替换当前原型草稿');await expect(submit()).toBeEnabled();}
    await cancel();await nav('bench');
    expect(await benchField().evaluate(el=>({label:el.closest('label').textContent,min:el.min,max:el.max}))).toEqual(originalField);
  }

  const first=structuredClone(exported);owner(first).name='此前选择的文件';
  await openImport();await chooseValid(first,'at-limit.json');
  await chooser().setInputFiles(file(exported,'too-large.json'));
  await expect(preview()).toContainText('不超过 64 MB');await expect(submit()).toBeDisabled();
  // The submit handler must reject invalid state even when native button disabling is bypassed.
  await page.locator('#dialog-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  await expect(page.locator('#dialog-error')).toContainText('请先选择并读取有效文件');await expect(dialog()).toBeVisible();
  await cancel();await expect(page.locator('.project-picker')).toContainText(active.name);

  await openImport();await chooseValid(first,'previous.json');
  await chooser().setInputFiles(file(exported,'unreadable.json'));
  await expect(preview()).toContainText('受控文件读取失败');await expect(submit()).toBeDisabled();
  await chooseValid(exported,'after-error.json');await expect(chooser()).not.toHaveAttribute('aria-invalid','true');
  await chooser().setInputFiles([]);await expect(preview()).toContainText('请选择文件');await expect(submit()).toBeDisabled();
  await chooseValid(first,'before-cancel.json');await chooser().dispatchEvent('cancel');
  expect(await chooser().evaluate(el=>el.files.length)).toBe(0);await expect(submit()).toBeDisabled();await cancel();

  const latest=structuredClone(exported);owner(latest).name='最新选择的文件';
  await openImport();await chooser().setInputFiles(file(first,'delayed.json'));
  await expect(preview()).toContainText('正在读取');await expect(submit()).toBeDisabled();
  await expect.poll(()=>page.evaluate(()=>typeof window.__settingsFileReads.release)).toBe('function');
  await chooseValid(latest,'latest.json');
  await page.evaluate(async()=>{await window.__settingsFileReads.release();await new Promise(resolve=>requestAnimationFrame(resolve));});
  await expect(submit()).toBeEnabled();await submit().click();await expect(dialog()).toHaveCount(0);
  await expect(page.locator('.project-picker')).toContainText('最新选择的文件');
  expect(owner(await save()).name).toBe('最新选择的文件');

  await openImport();await chooseDownloaded(originalExport);await submit().click();await expect(dialog()).toHaveCount(0);
  const roundTrip=await save();expect(owner(roundTrip).name).toBe(active.name);expect(owner(roundTrip).moduleSnapshots).toEqual(active.moduleSnapshots);
  await page.reload();await expect(page.locator('.project-picker')).toContainText(active.name);

  // Ordinary completed runs add enough history and archive snapshots to exceed the old 5 MB limit.
  await setting('solver');await page.locator('[data-solver-field="mode"]').selectOption('dynamic');
  await page.locator('[data-live-mode]').selectOption('fast');await page.locator('[data-solver-continuous]').uncheck();
  for(const [field,value] of [['duration','1'],['dt','0.25']]){
    const input=page.locator(`[data-solver-field="${field}"]`);await input.fill(value);await input.blur();
  }
  await save();await nav('workbench');
  const created=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const runId=(await(await created).json()).run_id;
  await expect.poll(async()=>(await(await page.request.get(`${server.base}/api/v1/runs/${runId}`)).json()).status,{timeout:20000}).toBe('completed');
  await expect(page.locator('#statusbar')).toContainText('已完成');await save();
  const runExport=await downloadedWorkspace();
  expect(runExport.bytes.length).toBeGreaterThan(5_000_000);expect(runExport.bytes.length).toBeLessThanOrEqual(importLimitBytes);
  const runData=JSON.parse(runExport.bytes.toString('utf8'));
  await openImport();await chooseDownloaded(runExport);await submit().click();await expect(dialog()).toHaveCount(0);
  const importedRun=owner(await save());
  expect(importedRun.solver).toEqual(owner(runData).solver);expect(importedRun.run.history).toEqual(owner(runData).run.history);

  // Whitespace alone can exceed the limit. Preserve all data and switch both exchange formats to compact JSON.
  // This valid nested metadata stays small on import while its pretty form has over 75 MiB of indentation.
  const padded=structuredClone(runData);let metadata=Array(600_000).fill(0);
  for(let depth=0;depth<64;depth++)metadata={values:metadata};
  padded.models[0].exportMetadata=metadata;
  await openImport();await chooseValid(padded,'formatting-fixture.json');await submit().click();await expect(dialog()).toHaveCount(0);
  for(const format of ['prototype','models']){
    const artifact=await downloadedWorkspace(format),text=artifact.bytes.toString('utf8');
    expect(artifact.bytes.length).toBeLessThanOrEqual(importLimitBytes);expect(text.startsWith('{"')).toBe(true);
    const data=JSON.parse(text);expect(data.models[0].exportMetadata).toEqual(metadata);
    expect(data.models.length).toBe(padded.models.length);expect(data.modules.length).toBe(padded.modules.length);
    if(format==='prototype')expect(owner(data).run.history).toEqual(owner(runData).run.history);
  }
  expect(errors).toEqual([]);
  console.log(JSON.stringify({precisionChoices:4,precisionSurvivesReload:true,moduleDefinitionsUnchanged:true,themeAndGrid:true,
    importPreviewIsolated:true,oversizeClearsPrevious:true,failedAndCancelledFilesBlocked:true,latestFileWins:true,roundTrip:true,
    importLimitBytes,rawRunExportBytes:runExport.bytes.length,rawRunRoundTrip:true,largePrettyExportsCompactedWithoutDataLoss:true,errors}));
}catch(error){console.error('Browser errors:',errors);throw error;}
finally{await browser.close();await server.close();}
