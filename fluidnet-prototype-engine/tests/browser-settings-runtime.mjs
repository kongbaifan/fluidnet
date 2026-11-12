import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

// A separate server/store exercises real settings, persistence and run requests.
// All dynamic sessions are stepped, paused or explicitly stopped; none waits for
// a long simulation to finish. No access to Studio's private state is needed.
const server=await testServer(),output='artifacts/settings-runtime';
let browser,page;
const errors=[],evidence={};
const solverFields=['mode','duration','dt','maxIter','massAtol','pressureAtol','hydraulicMethod'];
const solverSelectors=[...solverFields.map(key=>`[data-solver-field="${key}"]`),
  '[data-solver-option="property_coupling"]','[data-solver-continuous]',
  '[data-live-mode]','[data-live-speed]'];
const mediumSelectors=['[data-project-field="medium"]','[data-project-field="fluid"]',
  '[data-project-field="fluidReference"]','[data-project-phase-policy]',
  ...['anchor','medium','fluid','fluidReference'].map(key=>`[data-circuit-field="${key}"]`),
  '[data-action="add-circuit-fluid"]','[data-action="remove-circuit-fluid"]'];
const dynamicSelectors=['[data-solver-field="duration"]','[data-solver-field="dt"]',
  '[data-solver-continuous]','[data-live-mode]','[data-live-speed]'];
const field=key=>page.locator(`[data-solver-field="${key}"]`);
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
async function settings(tab='solver'){
  await nav('settings');
  await page.locator(`[data-action="settings-tab"][data-value="${tab}"]`).click();
}
async function setNumber(key,value){
  await field(key).fill(String(value));
  await field(key).blur();
}
async function enabled(selectors,wanted){
  for(const selector of selectors){
    const locator=page.locator(selector);
    expect(await locator.count(),`setting exists: ${selector}`).toBeGreaterThan(0);
    for(const item of await locator.all()){
      if(wanted)await expect(item).toBeEnabled();
      else await expect(item).toBeDisabled();
    }
  }
}
async function api(path){
  const response=await page.request.get(server.base+'/api/v1'+path);
  expect(response.ok(),await response.text()).toBe(true);
  return response.json();
}
async function savedOwner(){
  const posted=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/v1/workspace'
    &&response.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
  return page.evaluate(async()=>{
    const {FluidNetDraftStore}=await import('/draft-store.js');
    const state=FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));
    return state.projects.find(owner=>owner.id===state.activeProject);
  });
}
function physical(owner){
  return {solver:owner.solver,solverOptions:owner.solverOptions,medium:owner.medium,
    fluid:owner.fluid,fluidReference:owner.fluidReference,fluidConfig:owner.fluidConfig,
    circuitFluids:owner.circuitFluids};
}
function acceptedResults(run){
  return {id:run.id,history:run.history,time:run.time,values:run.values,parameterKey:run.parameterKey};
}
async function holdReply(pattern){
  let release,entered,reject,handling=null,handlerError=null,abortExpected=false;
  const gate=new Promise(resolve=>{release=resolve;});
  const received=new Promise((resolve,no)=>{entered=resolve;reject=no;});received.catch(()=>{});
  const handler=route=>handling=(async()=>{
    const response=await route.fetch();
    entered({request:route.request().postDataJSON(),result:await response.json()});
    await gate;
    await route.fulfill({response});
  })().catch(error=>{if(!abortExpected)handlerError=error;reject(error);});
  await page.route(pattern,handler);
  return {received,release,expectAbort:()=>{abortExpected=true;},close:async()=>{
    release();await page.unroute(pattern,handler);await handling;
    if(handlerError)throw handlerError;
  }};
}
async function syntheticChange(selector,value){
  // Native disabled controls stop pointer/keyboard edits. Dispatch separately to
  // verify the event handler also protects the running model and saved document.
  await page.locator(selector).first().evaluate((element,value)=>{
    if(element.type==='checkbox')element.checked=value;
    else element.value=String(value);
    element.dispatchEvent(new Event('change',{bubbles:true}));
  },value);
}
const runResponse=response=>new URL(response.url()).pathname==='/api/v1/runs'
  &&response.request().method()==='POST';
async function start(action='step'){
  await nav('workbench');
  const [response]=await Promise.all([page.waitForResponse(runResponse),
    page.locator(`.runbar [data-command="${action}"]`).click()]);
  expect(response.ok(),await response.text()).toBe(true);
  const result=await response.json();
  return {id:result.run_id,request:response.request().postDataJSON()};
}
async function status(id,wanted,expectedTime){
  let record;
  await expect.poll(async()=>{
    record=await api('/runs/'+id);
    if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));
    return expectedTime===undefined?record.status:{status:record.status,time:record.frame?.time_s};
  },{timeout:20000}).toEqual(expectedTime===undefined?wanted:{status:wanted,time:expectedTime});
  return record;
}
async function stop(id){
  await nav('workbench');
  await page.locator('.runbar [data-command="stop"]').click();
  await status(id,'cancelled');
}
function requestSummary(request){
  const solver=request.project.solver;
  return {mode:request.mode,duration:request.duration_s,dt:request.dt_s,
    pace:request.execution_mode,speed:request.speed_ratio,
    maxIter:solver.max_iterations,massAtol:solver.mass_tolerance_kg_s,
    pressureAtol:solver.pressure_tolerance_pa,method:solver.hydraulic_method,
    coupling:solver.property_coupling,moistAir:solver.moist_air};
}
function appliedActions(record){
  const actions=new Map(record.events.filter(event=>event.command).map(event=>[event.command_id,event.command.action]));
  return record.events.filter(event=>event.command_status==='applied')
    .map(event=>event.command?.action||actions.get(event.command_id));
}

try{
  browser=await chromium.launch({channel:'msedge',headless:true});
  page=await browser.newPage(FHD_CONTEXT);page.setDefaultTimeout(15000);
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(server.base);
  await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="start-modeling"]').first().click();

  // Keep a real circuit override present so running-state locks cover its
  // fields and add/remove actions as well as the project defaults.
  await settings('medium');
  await page.locator('[data-action="add-circuit-fluid"]').click();
  await expect(page.locator('[data-circuit-row]')).toHaveCount(1);
  const circuitAlternative=await page.locator('[data-circuit-field="anchor"] option').nth(1).getAttribute('value');

  await settings();
  await field('mode').selectOption('dynamic');
  await setNumber('duration',120);await setNumber('dt',.25);await setNumber('maxIter',73);
  await setNumber('massAtol',1e-6);await setNumber('pressureAtol',.25);
  await field('hydraulicMethod').selectOption('sparse');
  await page.locator('[data-solver-option="property_coupling"]').selectOption('node');
  await page.locator('[data-live-mode]').selectOption('realtime');
  await page.locator('[data-live-speed]').fill('2.5');await page.locator('[data-live-speed]').blur();
  await expect(page.locator('[data-live-speed]')).toHaveValue('2.5');

  for(const invalid of ['', '0', '101']){
    await page.locator('[data-live-speed]').fill(invalid);await page.locator('[data-live-speed]').blur();
    await expect(page.locator('#toast')).toContainText(invalid===''?/有效数值/:/0\.1.*100/);
    await expect(page.locator('[data-live-speed]')).toHaveValue('2.5');
    expect(errors,`invalid speed ${JSON.stringify(invalid)} must be handled`).toEqual([]);
  }
  evidence.speedValidation=['empty','below minimum','above maximum'];

  // Unavailable settings remain saved as preferences for the next applicable
  // mode; changing modes must not quietly replace them with defaults.
  await page.locator('[data-live-mode]').selectOption('fast');
  await expect(page.locator('[data-live-speed]')).toBeDisabled();
  await page.locator('[data-solver-continuous]').check();
  await expect(field('duration')).toBeDisabled();await expect(field('dt')).toBeEnabled();
  await field('mode').selectOption('steady');
  await enabled(dynamicSelectors,false);
  await enabled(['[data-solver-field="maxIter"]','[data-solver-field="hydraulicMethod"]',
    '[data-solver-field="massAtol"]','[data-solver-field="pressureAtol"]'],true);
  const steady=await savedOwner();
  expect(steady.solver).toMatchObject({mode:'steady',continuous:true,duration:120,dt:.25,
    executionMode:'fast',speedRatio:2.5});
  await field('mode').selectOption('dynamic');
  await expect(page.locator('[data-solver-continuous]')).toBeChecked();
  await expect(page.locator('[data-live-mode]')).toHaveValue('fast');
  await expect(page.locator('[data-live-speed]')).toHaveValue('2.5');
  await expect(page.locator('[data-live-speed]')).toBeDisabled();
  await page.locator('[data-solver-continuous]').uncheck();
  await page.locator('[data-live-mode]').selectOption('realtime');
  await enabled(dynamicSelectors,true);

  const before=physical(await savedOwner());
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await settings();
  for(const [key,value] of Object.entries({mode:'dynamic',duration:120,dt:.25,maxIter:73,
    massAtol:1e-6,pressureAtol:.25,hydraulicMethod:'sparse'})){
    if(typeof value==='number')expect(Number(await field(key).inputValue())).toBe(value);
    else await expect(field(key)).toHaveValue(value);
  }
  await expect(page.locator('[data-live-mode]')).toHaveValue('realtime');
  await expect(page.locator('[data-live-speed]')).toHaveValue('2.5');
  await expect(page.locator('[data-solver-continuous]')).not.toBeChecked();
  await expect(page.locator('[data-solver-option="property_coupling"]')).toHaveValue('node');
  expect(physical(await savedOwner())).toEqual(before);
  evidence.persistence=true;

  const first=await start();
  expect(requestSummary(first.request)).toEqual({mode:'dynamic',duration:120,dt:.25,
    pace:'realtime',speed:2.5,maxIter:73,massAtol:1e-6,pressureAtol:.25,
    method:'sparse',coupling:'node',moistAir:false});
  // Initialization is itself paused at t=0 before the first step is applied.
  const paused=await status(first.id,'paused',.25);expect(appliedActions(paused)).toContain('step');
  await settings();await enabled(solverSelectors,false);
  for(const [selector,value] of [
    ['[data-solver-field="mode"]','steady'],['[data-solver-field="duration"]',99],
    ['[data-solver-field="dt"]',2],['[data-solver-field="maxIter"]',18],
    ['[data-solver-field="massAtol"]',.01],['[data-solver-field="pressureAtol"]',10],
    ['[data-solver-field="hydraulicMethod"]','dense'],
    ['[data-solver-option="property_coupling"]','reference'],
    ['[data-solver-continuous]',true],['[data-live-mode]','fast'],['[data-live-speed]',7],
  ])await syntheticChange(selector,value);
  expect(physical(await savedOwner())).toEqual(before);

  await settings('medium');await enabled(mediumSelectors,false);
  for(const [selector,value] of [
    ['[data-project-field="medium"]','air'],['[data-project-field="fluid"]','Air'],
    ['[data-project-field="fluidReference"]','mole'],['[data-project-phase-policy]','gas'],
    ['[data-circuit-field="anchor"]',circuitAlternative],['[data-circuit-field="medium"]','air'],
    ['[data-circuit-field="fluid"]','Air'],['[data-circuit-field="fluidReference"]','mole'],
  ])await syntheticChange(selector,value);
  for(const action of ['add-circuit-fluid','remove-circuit-fluid']){
    await page.locator(`[data-action="${action}"]`).first().dispatchEvent('click');
    await expect(page.locator('[data-circuit-row]')).toHaveCount(1);
  }
  expect(physical(await savedOwner())).toEqual(before);
  expect(errors).toEqual([]);
  evidence.pausedGuards=true;

  await nav('workbench');await page.locator('.runbar [data-command="run"]').click();
  await status(first.id,'running');
  await settings();await enabled(solverSelectors,false);
  await settings('medium');await enabled(mediumSelectors,false);
  await captureFhd(page,output+'/running-settings.png');
  await stop(first.id);
  await settings();await enabled(solverSelectors,true);
  await settings('medium');await enabled(mediumSelectors,true);
  evidence.runningAndStoppedLocks=true;
  evidence.firstRequest=requestSummary(first.request);

  // Continuous requests must actually omit the duration, while the stored
  // finite duration survives toggling the checkbox off again.
  await settings();await page.locator('[data-solver-continuous]').check();
  await expect(field('duration')).toBeDisabled();
  const continuous=await start();
  expect(continuous.request.duration_s).toBeNull();expect(continuous.request.mode).toBe('dynamic');
  await status(continuous.id,'paused',.25);
  await stop(continuous.id);await settings();
  await page.locator('[data-solver-continuous]').uncheck();await expect(field('duration')).toHaveValue('120');
  evidence.continuousRequest=true;

  // A synchronous steady solve has no live flag. Hold its HTTP request to
  // observe the separate `solving` state, then release and complete a real run.
  await setNumber('duration',7);await setNumber('dt',.5);await setNumber('maxIter',99);
  await setNumber('massAtol',2e-7);await setNumber('pressureAtol',.75);
  await field('hydraulicMethod').selectOption('dense');
  await page.locator('[data-solver-option="property_coupling"]').selectOption('reference');
  await field('mode').selectOption('steady');
  let release;
  const gate=new Promise(resolve=>{release=resolve;});
  const intercept=async route=>{await gate;await route.continue();};
  await page.route('**/api/v1/runs',intercept);
  const posted=page.waitForResponse(runResponse);posted.catch(()=>{});
  let steadyRun;
  try{
    await nav('workbench');await page.locator('.runbar [data-command="run"]').click();
    await settings();await enabled(solverSelectors,false);
    await settings('medium');await enabled(mediumSelectors,false);
    release();
    const response=await posted;expect(response.ok(),await response.text()).toBe(true);
    steadyRun={id:(await response.json()).run_id,request:response.request().postDataJSON()};
  }finally{release();await page.unroute('**/api/v1/runs',intercept);}
  await status(steadyRun.id,'completed');
  expect(requestSummary(steadyRun.request)).toMatchObject({mode:'steady',duration:7,dt:.5,
    maxIter:99,massAtol:2e-7,pressureAtol:.75,method:'dense',coupling:'reference'});
  await settings();await expect(field('mode')).toBeEnabled();await enabled(dynamicSelectors,false);
  evidence.solvingLocks=true;evidence.changedRequest=requestSummary(steadyRun.request);
  await savedOwner();

  // Dynamic startup must be locked before the backend ID arrives too. A slow
  // normalization can be cancelled without creating a task or losing results.
  await settings();await field('mode').selectOption('dynamic');
  const startupBefore=await savedOwner(),startupResults=acceptedResults(startupBefore.run);
  const startupPhysical=physical(startupBefore),creationFailures=[];let creationPosts=0;
  const onRequest=request=>{if(new URL(request.url()).pathname==='/api/v1/runs'&&request.method()==='POST')creationPosts++;};
  const onRequestFailed=request=>{if(new URL(request.url()).pathname==='/api/v1/runs'&&request.method()==='POST')creationFailures.push(request.failure()?.errorText);};
  page.on('request',onRequest);page.on('requestfailed',onRequestFailed);
  const normalization=await holdReply('**/api/v1/prototype/normalize');
  try{
    await nav('workbench');await page.locator('.runbar [data-command="run"]').click();await normalization.received;
    await expect(page.locator('.runbar [data-command="run"]')).toBeDisabled();
    await expect(page.locator('.runbar [data-command="stop"]')).toBeEnabled();
    await settings();await enabled(solverSelectors,false);
    await syntheticChange('[data-solver-field="dt"]',2);
    await settings('medium');await enabled(mediumSelectors,false);
    await syntheticChange('[data-project-field="fluid"]','Air');
    const savingStartup=await savedOwner();
    expect(physical(savingStartup)).toEqual(startupPhysical);
    expect(acceptedResults(savingStartup.run)).toEqual(startupResults);
    normalization.expectAbort();
    await nav('workbench');await page.locator('.runbar [data-command="stop"]').click();
    await expect(page.locator('#statusbar')).toContainText('已停止');
  }finally{await normalization.close();}
  expect(creationPosts).toBe(0);
  const normalizedStop=await savedOwner();
  expect(acceptedResults(normalizedStop.run)).toEqual(startupResults);
  expect(normalizedStop.run.status).toBe('stopped');

  // A steady project's single-step command still creates a dynamic session.
  // Its pending stop must use the same lifecycle, rather than the legacy steady
  // path aborting the POST and losing an already accepted backend ID.
  await settings();await page.locator('[data-solver-continuous]').check();
  await page.locator('[data-live-mode]').selectOption('fast');await field('mode').selectOption('steady');
  const submitBefore=physical(await savedOwner()),submission=await holdReply('**/api/v1/runs?background=true');
  let cancelledId;
  try{
    await nav('workbench');await page.locator('.runbar [data-command="step"]').click();
    const accepted=await submission.received;cancelledId=accepted.result.run_id;
    expect(accepted.request.start_paused).toBe(true);expect(accepted.request.duration_s).toBeNull();
    await status(cancelledId,'paused',0);
    await expect(page.locator('.runbar [data-command="run"]')).toBeDisabled();
    await expect(page.locator('.runbar [data-command="stop"]')).toBeEnabled();
    await settings();await enabled(solverSelectors,false);
    await syntheticChange('[data-solver-field="mode"]','dynamic');
    await syntheticChange('[data-solver-field="dt"]',2);
    await settings('medium');await enabled(mediumSelectors,false);
    await syntheticChange('[data-project-field="fluid"]','Air');
    const savingSubmission=await savedOwner();
    expect(physical(savingSubmission)).toEqual(submitBefore);
    expect(acceptedResults(savingSubmission.run)).toEqual(startupResults);
    await nav('workbench');await page.locator('.runbar [data-command="stop"]').click();
    await expect(page.locator('#statusbar')).toContainText('求解中');
    submission.release();
    const cancelled=await status(cancelledId,'cancelled');
    expect(cancelled.frame?.time_s).toBe(0);
    expect(appliedActions(cancelled).some(action=>['resume','step'].includes(action))).toBe(false);
    await expect(page.locator('#statusbar')).toContainText('已停止');
  }finally{await submission.close();}
  expect(creationPosts).toBe(1);expect(creationFailures).toEqual([]);
  const submittedStop=await savedOwner();
  expect(acceptedResults(submittedStop.run)).toEqual(startupResults);
  expect(submittedStop.run.runId).toBeNull();expect(submittedStop.run.live).toBeFalsy();
  await settings();await expect(field('mode')).toBeEnabled();await enabled(dynamicSelectors,false);

  // When the response is accepted, Run must resume the paused server session
  // and finish the requested finite timeline, not leave it paused at t=0.
  await field('mode').selectOption('dynamic');await page.locator('[data-solver-continuous]').uncheck();
  await setNumber('duration',1);await setNumber('dt',.5);
  const delayedRun=await holdReply('**/api/v1/runs?background=true');
  try{
    await nav('workbench');await page.locator('.runbar [data-command="run"]').click();
    const accepted=await delayedRun.received;
    expect(accepted.request.start_paused).toBe(true);await status(accepted.result.run_id,'paused',0);
    delayedRun.release();
    const completed=await status(accepted.result.run_id,'completed');
    expect(completed.frame.time_s).toBe(1);
    expect(appliedActions(completed)).toContain('resume');
    await expect(page.locator('#statusbar')).toContainText('已完成');
  }finally{await delayedRun.close();}
  expect(creationFailures).toEqual([]);
  page.off('request',onRequest);page.off('requestfailed',onRequestFailed);
  evidence.pendingCreation={normalizationStopped:true,submissionStopped:true,resultsPreserved:true,delayedRunResumed:true};
  await savedOwner();

  // An incompatible coupling choice must be rejected before it turns a valid
  // moist-air example into an AIR_SOLVER_OPTIONS failure.
  await page.goto(server.base+'/#air');
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
  await page.getByLabel('风侧示例',{exact:true}).selectOption('air-coil-wet');
  await page.getByRole('button',{name:'创建项目',exact:true}).click();
  await expect(page.getByLabel('风侧当前项目')).toContainText('湿盘管除湿');
  await settings();
  const coupling=page.locator('[data-solver-option="property_coupling"]');
  await expect(coupling).toHaveValue('node');
  expect(await coupling.evaluate(element=>element.disabled||element.querySelector('option[value="reference"]').disabled),
    'reference coupling is unavailable for moist air').toBe(true);
  const airBefore=physical(await savedOwner());
  await syntheticChange('[data-solver-option="property_coupling"]','reference');
  await expect(page.locator('#toast')).toContainText(/湿空气/);
  expect(physical(await savedOwner())).toEqual(airBefore);
  const airRun=await start('run');
  expect(airRun.request.project.solver).toMatchObject({moist_air:true,property_coupling:'node'});
  const airRecord=await status(airRun.id,'completed');expect(airRecord.frame.valid).toBe(true);
  evidence.moistAirDependency=true;

  expect(errors).toEqual([]);
  mkdirSync(output,{recursive:true});
  writeFileSync(output+'/summary.json',JSON.stringify({...evidence,errors},null,2)+'\n');
  console.log(JSON.stringify({...evidence,errors},null,2));
}catch(error){
  if(page)await captureFhd(page,output+'/failure.png').catch(()=>{});
  throw error;
}finally{
  if(browser)await browser.close();
  await server.close();
}
