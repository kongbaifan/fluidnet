import {chromium,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync,mkdirSync,readdirSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

export const hash=value=>createHash('sha256').update(value).digest('hex');
function baseline(){
  const files=directory=>readdirSync(directory,{withFileTypes:true}).flatMap(entry=>{
    const path=join(directory,entry.name);
    return entry.isDirectory()?files(path):/\.(js|py|html|css)$/.test(entry.name)?[path]:[];
  });
  const paths=['frontend','backend'].flatMap(files).sort();
  return {head:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8',windowsHide:true}).trim(),
    productHash:hash(paths.map(path=>path.replaceAll('\\','/')+':'+hash(readFileSync(path))).join('\n')),files:paths.length};
}

export function compareFrames(expected,actual){
  const before=expected.frame.variables,after=actual.frame.variables;
  expect(Object.keys(after).sort()).toEqual(Object.keys(before).sort());
  let count=0,maxRelativeError=0,maxAbsoluteError=0;
  for(const [key,value] of Object.entries(before)){
    if(typeof value!=='number'){expect(after[key],key).toEqual(value);continue;}
    expect(Number.isFinite(after[key]),key).toBe(true);
    const error=Math.abs(after[key]-value),relative=error/Math.max(1,Math.abs(value));
    expect(relative,key).toBeLessThanOrEqual(1e-8);count++;
    maxRelativeError=Math.max(maxRelativeError,relative);maxAbsoluteError=Math.max(maxAbsoluteError,error);
  }
  expect(actual.frame.time_s).toBe(expected.frame.time_s);
  return {numericVariables:count,maxRelativeError,maxAbsoluteError,time_s:actual.frame.time_s};
}

export async function coreWorkflow(name){
  expect(process.env.FLUIDNET_TEST_URL,'Core workflows require an isolated temporary testServer workspace').toBeFalsy();
  const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true}),errors=[],out=resolve('artifacts/core-workflow',name);
  mkdirSync(out,{recursive:true});page.setDefaultTimeout(20000);
  const evidence={scenario:name,startedAt:new Date().toISOString(),baseline:baseline(),browser:browser.version(),node:process.version,
    viewport:FHD_CONTEXT,steps:[],runs:{},screenshots:[],apiPolicy:'GET reads only; all project, parameter, control, connection and file operations use the UI'};
  evidence.testSources=Object.fromEntries(['tests/browser-core-workflow.mjs','tests/core-workflow-fixture.mjs'].map(path=>[path,hash(readFileSync(path))]));
  page.on('pageerror',error=>errors.push(error.message));
  const write=()=>writeFileSync(join(out,'evidence.json'),JSON.stringify(evidence,null,2)+'\n');
  const note=(action,details={})=>{evidence.steps.push({at:new Date().toISOString(),action,...details});console.log(name+': '+action);write();};
  async function api(path){const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();}
  const current=workspace=>workspace.projects.find(project=>project.id===workspace.activeProject);
  const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
  async function submit(){await page.locator('#dialog-form [type="submit"]').click();await expect(page.locator('#dialog-form')).toHaveCount(0);}
  async function closePanels(){
    while(await page.locator('[data-action="float-close"]:visible').count()){
      const front=page.locator('.floater.front [data-action="float-close"]:visible');
      await (await front.count()?front.last():page.locator('[data-action="float-close"]:visible').last()).click();
    }
  }
  async function closeDialog(){if(await page.getByRole('dialog').count())await page.getByRole('dialog').locator('[data-action="close-dialog"]').last().click();}
  async function save(){
    const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');pending.catch(()=>{});
    await page.locator('#app-header [data-action="save"]').click();const response=await pending;expect(response.ok(),await response.text()).toBe(true);
    await expect(page.locator('[data-save-status]')).not.toContainText(/正在保存|失败/);return (await api('/workspace')).data;
  }
  async function capture(label){const path=join(out,label+'.png');await captureFhd(page,path);evidence.screenshots.push(label+'-1080p.png');write();}
  async function reveal(field){
    for(const details of await field.locator('xpath=ancestor::details').all())if(await details.getAttribute('open')===null)await details.locator(':scope > summary').click();
    await expect(field).toBeVisible();
  }
  async function openProject(id){await closePanels();await nav('projects');await page.locator(`[data-action="open-project"][data-id="${id}"]`).first().click();return current(await save());}
  async function newProject(label,template='blank'){
    await closePanels();await nav('projects');await page.locator('[data-action="new-project"]').first().click();
    await page.locator('#dialog-form [name="name"]').fill(label);await page.locator('#dialog-form [name="template"]').selectOption(template);await submit();
    const owner=current(await save());note('created-project',{id:owner.id,template});return owner;
  }
  async function insert(moduleId){
    await closePanels();await nav('modules');await page.locator(`[data-module-id="${moduleId}"] [data-action="insert-module"]`).click();
    const owner=current(await save()),node=owner.pages.find(pg=>pg.id===owner.activePage).nodes.at(-1);
    expect(node.moduleId).toBe(moduleId);note('inserted-device',{id:node.id,moduleId});return node.id;
  }
  async function locate(id){
    await closePanels();await nav('workbench');await page.locator('[data-action="project-find"]').click();
    await page.getByLabel('全项目查找关键词').fill(id);await page.locator(`[data-action="project-find-node"][data-id="${id}"]`).click();
    await expect(page.getByRole('region',{name:id+' 设备参数',exact:true})).toBeVisible();
  }
  async function panel(id,tab='overview'){
    await nav('workbench');let region=page.getByRole('region',{name:id+' 设备参数',exact:true});
    // Use the visible project finder: an SVG group's bounding-box center can
    // land on a port after fitting a crowded diagram or opening inline charts.
    if(!await region.isVisible())await locate(id);
    region=page.getByRole('region',{name:id+' 设备参数',exact:true});await region.locator(`[data-action="float-tab"][data-value="${tab}"]`).click();return region;
  }
  async function parameter(id,key,value){
    const region=await panel(id,'parameters'),field=region.locator(`input[type="number"][data-instance-param="${key}"]`);
    await reveal(field);await expect(field).toBeEnabled();await field.fill(String(value));await field.blur();
    const apply=region.locator('[data-action="apply-instance"]');
    if(await apply.isEnabled()){await apply.click();await submit();}
    await region.locator('[data-action="float-close"]').click();note('applied-parameter',{id,key,displayValue:value});
  }
  async function connect(id,port,target){
    const region=await panel(id,'connections');await region.locator(`[data-action="connect-device-port"][data-port="${port}"]`).click();
    await page.locator('#dialog-form [name="target"]').selectOption(target);await submit();await region.locator('[data-action="float-close"]').click();
    note('connected-ports',{source:id+':'+port,target});
  }
  async function configure(duration,dt){
    await closePanels();await nav('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
    await page.locator('[data-solver-field="mode"]').selectOption('dynamic');
    if(await page.locator('[data-solver-continuous]').isChecked())await page.locator('[data-solver-continuous]').uncheck();
    for(const [key,value] of Object.entries({duration,dt})){await page.locator(`[data-solver-field="${key}"]`).fill(String(value));await page.locator(`[data-solver-field="${key}"]`).blur();}
    await page.locator('[data-live-mode]').selectOption('fast');await save();await nav('workbench');note('configured-run',{duration_s:duration,dt_s:dt,execution:'fast'});
  }
  async function run(label){
    await closePanels();await nav('workbench');note('started-run',{label});
    const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');pending.catch(()=>{});
    await page.locator('[data-action="run-project"][data-command="run"]').first().click();
    const response=await pending;expect(response.ok(),await response.text()).toBe(true);const {run_id}=await response.json();let record;
    await expect.poll(async()=>{record=await api('/runs/'+run_id);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:180000}).toBe('completed');
    await expect(page.locator('#statusbar')).toContainText('已完成');expect(record.frame.valid).toBe(true);
    evidence.runs[label]={id:run_id,status:record.status,time_s:record.frame.time_s,rows:record.total_rows,inputHash:hash(JSON.stringify(record.request.project)),
      requested:{mode:record.request.mode,execution_mode:record.request.execution_mode,duration_s:record.request.duration_s,dt_s:record.request.dt_s,scenario_id:record.request.scenario_id},
      topology:{devices:record.request.project.instances.length,connections:record.request.project.connections.length,pages:[...new Set(record.request.project.instances.map(n=>n.page_id))]},
      variables:record.frame.variables,metrics:record.frame.metrics};
    note('completed-run',{label,id:run_id,time_s:record.frame.time_s});return record;
  }
  async function stop(){await closePanels();await nav('workbench');const button=page.locator('[data-action="run-project"][data-command="stop"]').first();if(await button.isEnabled()){await button.click();await expect(button).toBeDisabled();}}
  async function metric(id,field,expected,scale=1,offset=0){
    const region=await panel(id),value=region.locator(`[data-device-metric="${field}"] strong`);
    await expect.poll(async()=>Number((await value.innerText()).replaceAll(',',''))).toBeCloseTo(expected/scale+offset,3);
    return {id,field,shown:await value.innerText(),expected:expected/scale+offset};
  }
  async function charts(keys,label,record){
    await closePanels();let workspace=await save(),owner=current(workspace);
    const canonical=value=>value.toLowerCase().replace(/[._:\-]/g,'');
    for(const key of keys){
      if(workspace.charts.extra.some(binding=>binding.projectId===owner.id&&binding.canonicalKey===key))continue;
      await nav('curves');await page.locator('[data-action="add-chart-variable"]').click();
      const options=await page.locator('#dialog-form [name="variable"] option').evaluateAll(items=>items.map(o=>({value:o.value,label:o.textContent})));
      const selected=options.find(option=>canonical(option.value)===canonical(key));
      expect(selected,JSON.stringify({key,available:options.filter(option=>option.value.startsWith(key.split('.')[0]+'.')).map(option=>option.value)})).toBeTruthy();
      await page.locator('#dialog-form [name="variable"]').selectOption(selected.value);await submit();workspace=await save();owner=current(workspace);
    }
    await nav('curves');await page.locator('[data-chart-source]').selectOption('live');
    await expect(page.locator('#main-flow-chart-readout')).not.toContainText('还没有当前运行数据');
    const bindings=workspace.charts.extra.filter(binding=>binding.projectId===owner.id),checked=[];
    for(const key of keys){
      const binding=bindings.find(b=>b.canonicalKey===key);expect(binding,key).toBeTruthy();
      const curve=page.locator(`path[data-series-key="extra:${binding.id}"]`);await expect(curve).toHaveAttribute('d',/L/);
      const svg=curve.locator('xpath=ancestor::*[local-name()="svg"]');await svg.scrollIntoViewIfNeeded();
      const box=await svg.boundingBox();await page.mouse.move(box.x+box.width-20,box.y+45);
      const readout=page.locator('#'+await svg.getAttribute('id')+'-readout');
      await expect(readout).toContainText(binding.unit);await expect(readout).toContainText('t =');
      const text=await readout.innerText(),expected=record.frame.variables[key]/binding.canonicalScale+binding.canonicalOffset;
      const numbers=text.replaceAll(',','').match(/-?\d+(?:\.\d+)?/g).map(Number);
      expect(numbers.at(-1),key+': '+text).toBeCloseTo(expected,2);checked.push({key,readout:text,expected});
      await capture(label+'-'+key.replace(/[^A-Za-z0-9_-]/g,'-'));
    }
    await page.locator('#extra-charts .panel').first().scrollIntoViewIfNeeded();await capture(label);note('verified-current-curves',{label,variables:checked});await nav('workbench');return checked;
  }
  async function roundtrip(reference,label){
    await stop();let owner=current(await save());const id=owner.id;
    await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');await openProject(id);
    const reloaded=await run(label+'-reloaded'),reloadEquality=compareFrames(reference,reloaded);await stop();
    let workspace=await save();const beforeIds=new Set(workspace.projects.map(p=>p.id));await nav('projects');
    await page.locator(`[data-action="duplicate-project"][data-id="${id}"]`).click();workspace=await save();
    const copied=workspace.projects.find(p=>!beforeIds.has(p.id));expect(copied).toBeTruthy();await openProject(copied.id);
    const copyRun=await run(label+'-copied'),copyEquality=compareFrames(reference,copyRun);await stop();
    await openProject(id);await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${id}"]`).click();
    const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
    const file=join(out,label+'-original-export.json');await(await download).saveAs(file);const originalHash=hash(readFileSync(file));await closeDialog();
    await page.locator('[data-action="wf-import"]').click();await page.getByLabel('单项目文件').setInputFiles(file);
    await page.locator('#dialog-form [name="mode"]').selectOption('copy');await submit();await expect(page.locator('#toast')).toContainText('项目已导入');
    owner=current(await save());expect(owner.id).not.toBe(id);const imported=await run(label+'-file-imported'),importEquality=compareFrames(reference,imported);
    expect(hash(readFileSync(file))).toBe(originalHash);await stop();await save();
    const result={originalId:id,copiedId:copied.id,importedId:owner.id,exportFile:file,unmodifiedFileSha256:originalHash,reloadEquality,copyEquality,importEquality};
    note('verified-save-reopen-copy-file-roundtrip',result);return result;
  }
  async function finish(){evidence.functionalPassed=true;evidence.finishedAt=new Date().toISOString();evidence.finalBaseline=baseline();evidence.errors=errors;
    evidence.stableBaseline=evidence.baseline.productHash===evidence.finalBaseline.productHash;expect(errors).toEqual([]);
    expect(evidence.stableBaseline,'Product changed during this run; repeat on the final shared baseline').toBe(true);evidence.passed=true;write();
    for(const file of ['failure-1080p.png','failure-1080p.png.json']){const path=join(out,file);if(existsSync(path))rmSync(path);}
    console.log(JSON.stringify({scenario:name,passed:true,stableBaseline:true,runs:Object.keys(evidence.runs),evidence:join(out,'evidence.json')}));}
  async function failure(error){evidence.passed=false;evidence.error=String(error.stack||error);evidence.errors=errors;evidence.finalBaseline=baseline();
    evidence.stableBaseline=evidence.baseline.productHash===evidence.finalBaseline.productHash;write();await capture('failure').catch(()=>{});
    console.error(name+': '+error.stack);console.error('toast:',await page.locator('#toast').innerText().catch(()=>''));}
  await page.goto(server.base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v');await save();write();
  return {page,api,current,nav,submit,save,capture,note,reveal,openProject,newProject,insert,locate,panel,parameter,connect,configure,run,stop,metric,charts,roundtrip,
    closePanels,evidence,out,finish,failure,close:async()=>{await browser.close();await server.close();}};
}
