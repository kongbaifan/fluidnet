import {chromium,expect} from '@playwright/test';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {launchEngine} from './browser-server.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-results-boundaries-'));
const out=resolve('artifacts/core-workflow');mkdirSync(out,{recursive:true});
const env={...process.env,FLUIDNET_MODULE_STORE:join(directory,'modules')};
const launched=await launchEngine({args:['--data-dir',join(directory,'data')],env});
const {base,port}=launched;let service=launched.server,serverLog='';
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080}}),page=await context.newPage(),errors=[];
const report={at:new Date().toISOString(),directory,base,checks:[],findings:[],errors};
page.on('pageerror',error=>errors.push(error.message));
await page.route('**/studio.js*',async route=>{
  const response=await route.fetch(),source=await response.text();
  // Read-only observations in this isolated audit response; the product files are untouched.
  await route.fulfill({response,body:source.replace('workspaceInteractions().mount();',`workspaceInteractions().mount();
    window.__coreAudit={snapshot:()=>clone(state),view:()=>({route:ui.route,selectedRecord:ui.selectedRecord}),
      stored:()=>FluidNetDraftStore.parse(localStorage.getItem(STORAGE_KEY)),ready:()=>engine.whenReady()};`)});
});
const state=()=>page.evaluate(()=>window.__coreAudit.snapshot());
const view=()=>page.evaluate(()=>window.__coreAudit.view());
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const current=s=>s.projects.find(p=>p.id===s.activeProject);
const setting=async tab=>{await nav('settings');await page.locator(`[data-action="settings-tab"][data-value="${tab}"]`).click();};
const save=async(target=page)=>{
  const pending=target.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await target.locator('[data-action="save"]').first().click();const response=await pending;
  await expect(target.locator('[data-save-status]')).not.toContainText('正在保存');return response;
};
const readRun=async id=>{const r=await page.request.get(`${base}/api/v1/runs/${id}`);expect(r.ok()).toBe(true);return r.json();};
async function open(id){await nav('projects');await page.locator(`[data-action="open-project"][data-id="${id}"]`).first().click();}
async function options({duration=1,dt=.25,mode='fast',continuous=false}={}){
  await setting('solver');await page.locator('[data-solver-field="mode"]').selectOption('dynamic');
  await page.locator('[data-live-mode]').selectOption(mode);
  await page.locator('[data-solver-continuous]').setChecked(continuous);
  for(const [field,value] of [['dt',dt],...(!continuous?[['duration',duration]]:[])]){
    await page.locator(`[data-solver-field="${field}"]`).fill(String(value));await page.locator(`[data-solver-field="${field}"]`).blur();
  }
}
async function run({finish=true}={}){
  await nav('workbench');
  const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const response=await pending;expect(response.ok()).toBe(true);const id=(await response.json()).run_id;
  await expect.poll(async()=>(await readRun(id)).status,{timeout:30000}).toBe(finish?'completed':'running');
  if(finish)await expect.poll(async()=>current(await state()).run.status).toBe('completed');
  return id;
}
async function record(){await nav('runs');await page.locator('[data-action="record-project"]').click();return (await view()).selectedRecord;}
async function screenshot(name){await page.screenshot({path:join(out,name),fullPage:true});}
function check(name,passed,details){report.checks.push({name,passed,details});if(!passed)report.findings.push({name,...details});console.log(JSON.stringify({check:name,passed}));}
async function stop(){if(!service||service.exitCode!==null)return;const end=once(service,'exit');service.kill();await end;}
async function restart(){
  service=spawn('python',['-m','fn_engine','serve','--host','127.0.0.1','--port',String(port),'--data-dir',join(directory,'data')],{
    cwd:resolve('.'),env,windowsHide:true,stdio:['ignore','ignore','pipe']});
  service.stderr.on('data',chunk=>{serverLog=(serverLog+chunk).slice(-4000);});
  await expect.poll(async()=>{try{return (await fetch(base+'/api/v1/health')).status;}catch{return 0;}},{timeout:30000}).toBe(200);
}
try{
  await page.goto(base+'/#workbench');await page.waitForFunction(()=>window.__coreAudit);await page.evaluate(()=>window.__coreAudit.ready());
  expect((await save()).ok()).toBe(true);
  const initial=await state(),aId=initial.activeProject,bId=initial.projects.find(p=>p.id==='heat-loop').id;
  await options();const aRun=await run();const aRecord=await record();const a=current(await state());
  await open(bId);await options();const bRun=await run();const bRecord=await record();const b=current(await state());
  check('independent completed projects have distinct physical results',Math.abs(a.run.history.at(-1).q-b.run.history.at(-1).q)>1e-5,{aId,bId,aRun,bRun,aFlow:a.run.history.at(-1).q,bFlow:b.run.history.at(-1).q});

  await nav('curves');await page.locator('[data-chart-source]').selectOption(aRecord);await page.locator('[data-chart-compare]').check();
  const observations=await page.evaluate(()=>({labels:document.querySelector('.chart-variable-list')?.textContent,
    q:document.querySelector('#main-flow-chart [data-series-key="q"]')?.getAttribute('d'),
    baseline:document.querySelector('#main-flow-chart [data-series-key="baseline-q"]')?.getAttribute('d')}));
  const storedA=(await state()).records.find(r=>r.id===aRecord);
  check('manual historical snapshot keeps its original primary variable bindings',observations.labels.includes(a.run.overviewBindings.q.label),{
    aRecord,bRecord,activeProject:bId,expectedLabel:a.run.overviewBindings.q.label,otherProjectLabel:b.run.overviewBindings.q.label,
    actualLabels:observations.labels,snapshotHasBindings:!!storedA.overviewBindings});
  check('historical comparison uses the selected record project',observations.q===observations.baseline,{
    selectedRecord:aRecord,selectedProject:aId,activeProject:bId,mainPath:observations.q,baselinePath:observations.baseline});
  const csvPending=page.waitForEvent('download');await page.locator('[data-action="export"][data-format="csv"]').click();
  const csv=readFileSync(await(await csvPending).path(),'utf8'),lines=csv.trim().split(/\r?\n/);
  const csvValues=[...lines.at(-1).matchAll(/"((?:[^"]|"")*)"/g)].map(match=>match[1]);
  check('historical curve export uses the selected record values and identifiers',Math.abs(Number(csvValues[1])-a.run.history.at(-1).q)<1e-12&&lines[0].includes(a.run.overviewBindings.q.key),{
    selectedRecord:aRecord,exportedFlow:Number(csvValues[1]),expectedFlow:a.run.history.at(-1).q,header:lines[0]});
  await screenshot('results-history-owner.png');

  await nav('runs');let releaseArchive,archiveCaptured=false,archiveDelivered=false;
  const archiveGate=new Promise(resolve=>{releaseArchive=resolve;}),archiveUrl=`${base}/api/v1/runs/${aRun}/overview`;
  await page.route(archiveUrl,async route=>{const response=await route.fetch();archiveCaptured=true;await archiveGate;await route.fulfill({response});archiveDelivered=true;});
  await page.locator(`[data-action="open-archive"][data-id="${aRun}"]`).click();await expect.poll(()=>archiveCaptured).toBe(true);
  await page.locator(`[data-action="open-archive"][data-id="${bRun}"]`).click();await expect.poll(async()=>(await view()).selectedRecord).toBe(bRun);
  releaseArchive();await expect.poll(()=>archiveDelivered).toBe(true);await page.unroute(archiveUrl);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  check('late archive reads cannot replace the newer selection',(await view()).selectedRecord===bRun,{lateArchive:aRun,selectedArchive:bRun,displayedArchive:(await view()).selectedRecord});

  await nav('runs');let releaseNavigation,navigationCaptured=false,navigationDelivered=false;
  const navigationGate=new Promise(resolve=>{releaseNavigation=resolve;});
  await page.route(archiveUrl,async route=>{const response=await route.fetch();navigationCaptured=true;await navigationGate;await route.fulfill({response});navigationDelivered=true;});
  try{
    await page.locator(`[data-action="open-archive"][data-id="${aRun}"]`).click();await expect.poll(()=>navigationCaptured).toBe(true);
    await nav('workbench');releaseNavigation();await expect.poll(()=>navigationDelivered).toBe(true);
    await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,100)));
    check('leaving archive browsing cancels an unfinished same-project selection',(await view()).route==='workbench',{
      lateArchive:aRun,route:(await view()).route});
  }finally{releaseNavigation();await page.unroute(archiveUrl);}

  await nav('runs');await page.locator(`[data-action="open-archive"][data-id="${aRun}"]`).click();
  await expect(page.locator('.run-details')).toContainText(aRun);
  await page.locator(`[data-action="record-curves"][data-id="${aRun}"]`).click();
  await nav('runs');await page.locator(`[data-action="delete-archive"][data-id="${aRun}"]`).click();
  const deleted=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/v1/runs/${aRun}/delete`&&r.request().method()==='POST');
  await page.locator('#dialog-form button[type="submit"]').click();expect((await deleted).ok()).toBe(true);
  await expect.poll(async()=>(await state()).records.some(r=>r.id===aRun)).toBe(false);await nav('curves');
  const afterDelete={source:(await state()).charts.source,visibleSource:await page.locator('[data-chart-source]').inputValue(),
    historyBadge:await page.locator('#page').innerText(),activeProject:(await state()).activeProject};
  check('removing the selected archive keeps chart source and visible data consistent',afterDelete.source===afterDelete.visibleSource,afterDelete);
  await screenshot('results-deleted-source.png');

  await open(aId);await page.locator('.net-node[data-node="V1"]').dblclick();
  const valveWindow=page.locator('[data-float-id="V1"]');
  await valveWindow.locator('input[type="number"][data-instance-param="opening"]').fill('35');
  const beforeDraftRecords=new Set((await state()).records.map(r=>r.id));await nav('runs');await page.locator('[data-action="record-project"]').click();
  const draftSnapshot=(await state()).records.find(r=>!beforeDraftRecords.has(r.id));
  check('unapplied drafts do not block recording the unchanged accepted parameters',draftSnapshot?.params.V1.opening===80,{
    snapshot:draftSnapshot?.id,recordedOpening:draftSnapshot?.params.V1.opening,pendingOpening:current(await state()).pages.flatMap(p=>p.nodes).find(n=>n.id==='V1').draft.opening});
  await nav('workbench');
  await valveWindow.locator('[data-action="apply-instance"]').click();await page.locator('#dialog-form button[type="submit"]').click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const staleResult=await page.locator('[data-result-status]').first().textContent();
  check('applied edits mark previously computed results as stale',/过期|参数已变更|等待重新采样/.test(staleResult),{status:staleResult});
  const savedRecords=JSON.stringify((await state()).records),priorRecords=new Set((await state()).records.map(r=>r.id));await nav('runs');await page.locator('[data-action="record-project"]').click();
  const staleSnapshot=(await state()).records.find(r=>!priorRecords.has(r.id)),acceptedOpening=a.pages.flatMap(p=>p.nodes).find(n=>n.id==='V1').params.opening;
  check('recording stale results never attributes them to newly applied parameters',(!staleSnapshot||staleSnapshot.params.V1.opening===acceptedOpening)&&JSON.stringify((await state()).records)===savedRecords,{
    acceptedOpening,currentOpening:current(await state()).pages.flatMap(p=>p.nodes).find(n=>n.id==='V1').params.opening,
    newSnapshot:staleSnapshot?.id,snapshotOpening:staleSnapshot?.params.V1.opening,toast:await page.locator('#toast').innerText()});
  await run();const freshRun=current(await state()).run,freshRecord=await record(),freshSnapshot=(await state()).records.find(r=>r.id===freshRecord);
  check('resampled accepted parameters can be recorded without changing older snapshots',freshSnapshot.params.V1.opening===35&&freshSnapshot.history.at(-1).q===freshRun.history.at(-1).q&&JSON.stringify((await state()).records.filter(r=>r.id!==freshRecord))===savedRecords,{
    snapshot:freshRecord,opening:freshSnapshot.params.V1.opening,flow:freshSnapshot.history.at(-1).q});

  await open(aId);await options({mode:'realtime',dt:.1,continuous:true});expect((await save()).ok()).toBe(true);
  const liveRun=await run({finish:false});await expect.poll(async()=>(await readRun(liveRun)).frame?.time_s||0).toBeGreaterThan(.4);
  await expect.poll(async()=>current(await state()).run.time).toBeGreaterThan(.4);
  let releaseLate,capturedLate=false,deliveredLate=false;
  const lateGate=new Promise(resolve=>{releaseLate=resolve;}),runUrl=`${base}/api/v1/runs/${liveRun}`;
  await page.route(runUrl,async route=>{const response=await route.fetch();capturedLate=true;await lateGate;await route.fulfill({response});deliveredLate=true;});
  await expect.poll(()=>capturedLate).toBe(true);await open(bId);
  const bBefore=JSON.stringify(current(await state()).run);releaseLate();await expect.poll(()=>deliveredLate).toBe(true);
  await page.unroute(runUrl);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  check('late HTTP frames after project switch cannot overwrite the visible project',JSON.stringify(current(await state()).run)===bBefore,
    {lateRun:liveRun,visibleProject:bId,visibleStatus:await page.locator('[data-result-status]').first().textContent()});
  await open(aId);
  await stop();await expect.poll(async()=>Boolean(current(await state()).run.connectionError)).toBe(true);
  const disconnected={run:current(await state()).run,status:await page.locator('[data-result-status]').first().textContent(),
    guidance:await page.locator('.workbench-next').count()?await page.locator('.workbench-next').innerText():'',
    toast:await page.locator('#toast').innerText()};
  check('lost service marks the displayed result as disconnected',/连接中断|断开|重连/.test(disconnected.status+' '+disconnected.guidance),{
    runId:liveRun,time:disconnected.run.time,error:disconnected.run.connectionError,status:disconnected.status,guidance:disconnected.guidance,toast:disconnected.toast});
  await screenshot('results-disconnected.png');
  await setting('project');await page.locator('[data-project-field="description"]').fill('断连期间保留的编辑草稿');
  await page.locator('[data-action="save"]').first().click();await expect(page.locator('[data-save-status]')).toContainText('保存失败');
  const offlineDraft=await page.evaluate(()=>window.__coreAudit.stored());
  check('offline save failure preserves the edit in browser draft',current(offlineDraft).description==='断连期间保留的编辑草稿',{dirty:offlineDraft.dirty,description:current(offlineDraft).description});
  await restart();await expect.poll(async()=>current(await state()).run.live,{timeout:20000}).toBe(false);
  const restored=await readRun(liveRun),reconnected=current(await state());
  check('same-origin restart reconciles interrupted run without losing local edits',restored.status==='interrupted'&&reconnected.run.status==='stopped'&&!reconnected.run.connectionError&&reconnected.description==='断连期间保留的编辑草稿',{
    serverStatus:restored.status,clientStatus:reconnected.run.status,clientTime:reconnected.run.time,serverTime:restored.frame?.time_s,
    description:reconnected.description,error:reconnected.run.connectionError});
  await nav('workbench');await screenshot('results-restarted.png');expect((await save()).ok()).toBe(true);

  const workspaceUrl=base+'/api/v1/workspace',remote=async()=>(await(await page.request.get(workspaceUrl)).json()).data;
  await setting('project');const description=page.locator('[data-project-field="description"]');
  await description.fill('保存请求中的编辑');let releaseSave,saveCaptured=false;
  const saveGate=new Promise(resolve=>{releaseSave=resolve;});
  await page.route(workspaceUrl,async route=>{
    if(route.request().method()!=='POST')return route.continue();
    const response=await route.fetch();saveCaptured=true;await saveGate;await route.fulfill({response});
  });
  const pendingSave=save();await expect.poll(()=>saveCaptured).toBe(true);
  await description.fill('保存期间继续编辑的内容');releaseSave();expect((await pendingSave).ok()).toBe(true);await page.unroute(workspaceUrl);
  const afterConcurrent=await state(),savedConcurrent=await remote();
  check('edits made while saving remain dirty until a later save',afterConcurrent.dirty&&current(afterConcurrent).description==='保存期间继续编辑的内容'&&current(savedConcurrent).description==='保存请求中的编辑',{
    dirty:afterConcurrent.dirty,browserDescription:current(afterConcurrent).description,serverDescription:current(savedConcurrent).description});
  await screenshot('storage-save-concurrent.png');expect((await save()).ok()).toBe(true);

  const stale=await page.context().newPage();stale.on('pageerror',error=>errors.push(error.message));
  await stale.goto(base+'/#settings');await expect(stale.locator('[data-project-field="description"]')).toHaveValue('保存期间继续编辑的内容');
  await description.fill('主标签页的新修订');expect((await save()).ok()).toBe(true);
  await stale.locator('[data-project-field="description"]').fill('旧修订标签页的未保存草稿');
  const conflict=await save(stale);await expect(stale.locator('[data-save-status]')).toContainText('保存失败');
  await stale.reload();await expect(stale.locator('[data-project-field="description"]')).toHaveValue('旧修订标签页的未保存草稿');
  check('409 conflicts preserve the losing tab draft and do not overwrite server edits',conflict.status()===409&&current(await remote()).description==='主标签页的新修订',{
    response:conflict.status(),serverDescription:current(await remote()).description,restoredDraft:await stale.locator('[data-project-field="description"]').inputValue()});
  await stale.screenshot({path:join(out,'storage-conflict-409.png'),fullPage:true});await stale.close();

  const historyBeforeFailure=JSON.stringify(current(await state()).run.history);
  await description.fill('507 保存失败时保留的草稿');
  await page.route(workspaceUrl,route=>route.request().method()==='POST'?route.fulfill({status:507,json:{detail:{message:'受控磁盘空间不足'}}}):route.continue());
  const failedSave=await save();await expect(page.locator('[data-save-status]')).toContainText('保存失败');
  const failedState=await state(),failedCache=await page.evaluate(()=>window.__coreAudit.stored());
  check('507 save failure preserves edits and all accepted history',failedSave.status()===507&&failedState.dirty&&current(failedCache).description==='507 保存失败时保留的草稿'&&JSON.stringify(current(failedState).run.history)===historyBeforeFailure,{
    response:failedSave.status(),dirty:failedState.dirty,description:current(failedCache).description,historyRows:current(failedState).run.history.length});
  await screenshot('storage-failure-507.png');await page.unroute(workspaceUrl);expect((await save()).ok()).toBe(true);

  const cacheBeforeQuota=await page.evaluate(()=>localStorage.getItem('fluidnet-prototype-engine-v1'));
  await page.evaluate(()=>{
    window.__originalStorageSet=Storage.prototype.setItem;
    Storage.prototype.setItem=function(key,value){if(key==='fluidnet-prototype-engine-v1')throw new DOMException('受控浏览器配额不足','QuotaExceededError');return window.__originalStorageSet.call(this,key,value);};
  });
  await description.fill('浏览器配额不足时由服务器保留的内容');expect((await save()).ok()).toBe(true);
  await expect(page.locator('#toast')).toContainText('本地草稿保存失败');
  const quotaState=await state(),quotaRemote=await remote(),cacheAfterQuota=await page.evaluate(()=>localStorage.getItem('fluidnet-prototype-engine-v1'));
  check('browser quota errors retain the previous cache and complete server-side save without data loss',cacheBeforeQuota===cacheAfterQuota&&current(quotaRemote).description===current(quotaState).description&&JSON.stringify(current(quotaState).run.history)===historyBeforeFailure,{
    fault:'injected QuotaExceededError',oldCacheUnchanged:cacheBeforeQuota===cacheAfterQuota,serverDescription:current(quotaRemote).description,historyRows:current(quotaState).run.history.length});
  await screenshot('storage-browser-quota.png');await page.evaluate(()=>{Storage.prototype.setItem=window.__originalStorageSet;delete window.__originalStorageSet;});
  await page.reload();await page.waitForFunction(()=>window.__coreAudit);await page.evaluate(()=>window.__coreAudit.ready());
  check('fresh reload recovers the confirmed server edit after browser quota failure',current(await state()).description==='浏览器配额不足时由服务器保留的内容',{description:current(await state()).description});
  report.summary={aRun,bRun,liveRun,currentEvidence:true};
  expect(report.findings).toEqual([]);expect(errors).toEqual([]);
  console.log(JSON.stringify({checks:report.checks.length,allPassed:true,summary:report.summary,errors}));
}catch(error){report.failure={message:error.message,serverLog};await screenshot('results-audit-failure.png').catch(()=>{});console.error(error);process.exitCode=1;}
finally{writeFileSync(join(out,'results-audit.json'),JSON.stringify(report,null,2));await browser.close();await stop();}
