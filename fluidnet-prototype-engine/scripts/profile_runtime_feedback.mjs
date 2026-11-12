/* Browser feedback A/B: same isolated backend and Edge process; UI operations only.
 * Prepare studio.js, run-commands.js, engine-client.js and project-run-state.js in
 * tmp/runtime-feedback-before (or --before-dir <snapshot-directory>) first.
 * node scripts/profile_runtime_feedback.mjs --after-ready artifacts/runtime-feedback/after.ready
 * The before sample finishes first; create the marker when the after frontend is ready.
 * To verify final frontend changes without replacing the baseline:
 * node scripts/profile_runtime_feedback.mjs --after-only --after-name after-final
 */
import {chromium,expect} from '@playwright/test';
import {createHash} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {testServer} from '../tests/browser-server.mjs';
import {FHD_CONTEXT} from '../tests/browser-viewport.mjs';

const output=resolve('artifacts/runtime-feedback');mkdirSync(output,{recursive:true});
const argument=(name,fallback)=>{
  const index=process.argv.indexOf(name);if(index<0)return fallback;
  const value=process.argv[index+1];if(!value||value.startsWith('--'))throw Error('Missing value for '+name);
  return value;
};
const readyFile=resolve(argument('--after-ready','artifacts/runtime-feedback/after.ready'));
const beforeDir=resolve(argument('--before-dir','tmp/runtime-feedback-before'));
const beforeFiles=['studio.js','run-commands.js','engine-client.js','project-run-state.js'];
const sleep=ms=>new Promise(done=>setTimeout(done,ms));
const digest=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
const stats=values=>{
  const ordered=[...values].sort((a,b)=>a-b),n=ordered.length;
  return {count:n,min:n?ordered[0]:null,median:n?ordered[Math.floor(n/2)]:null,p95:n?ordered[Math.min(n-1,Math.ceil(n*.95)-1)]:null,max:n?ordered.at(-1):null};
};
const intervals=rows=>stats(rows.slice(1).map((row,i)=>row.at-rows[i].at));
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const backendHashes=Object.fromEntries(['api.py','jobs.py','simulation.py'].map(file=>[file,digest('backend/fn_engine/'+file)]));

async function sample(phase){
  const context=await browser.newContext(FHD_CONTEXT),page=await context.newPage(),errors=[];
  const frontendHashes=Object.fromEntries(beforeFiles.map(file=>[file,digest((phase==='before'?beforeDir:resolve('frontend'))+'/'+file)]));
  const loadedFrontendHashes={},scriptLoads=[];
  page.setDefaultTimeout(30000);page.on('pageerror',error=>errors.push(error.message));
  const api=async path=>{const response=await fetch(server.base+'/api/v1'+path);if(!response.ok)throw Error(await response.text());return response.json();};
  const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
  const run=command=>page.locator(`[data-action="run-project"][data-command="${command}"]`).first();
  const readState=()=>page.evaluate(async()=>{const {FluidNetDraftStore}=await import('/draft-store.js');return FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));});
  if(phase==='before')for(const file of beforeFiles){
    const body=readFileSync(beforeDir+'/'+file,'utf8');
    await page.route(url=>!url.pathname.startsWith('/api/')&&url.pathname.endsWith('/'+file),route=>route.fulfill({status:200,contentType:'text/javascript',body}));
  }
  const http=new Map(),ws=[];let parameter={};
  const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');
  cdp.on('Network.requestWillBeSent',event=>{
    const url=new URL(event.request.url);if(url.pathname.startsWith('/api/v1/'))http.set(event.requestId,{at:Date.now(),path:url.pathname+url.search,method:event.request.method,bytes:0});
  });
  cdp.on('Network.loadingFinished',event=>{const request=http.get(event.requestId);if(request)request.bytes=event.encodedDataLength;});
  cdp.on('Network.webSocketFrameReceived',event=>ws.push({at:Date.now(),bytes:Buffer.byteLength(event.response.payloadData)}));
  page.on('request',request=>{
    if(request.method()!=='POST')return;
    const data=request.postDataJSON();
    if(data?.values?.['V1.param.opening_ratio']===.4)parameter={...parameter,sentAt:Date.now(),commandId:data.command_id||null,path:new URL(request.url()).pathname};
  });
  page.on('response',async response=>{
    const pathname=new URL(response.url()).pathname,file=pathname.split('/').at(-1);
    if(!pathname.startsWith('/api/')&&[...beforeFiles,'live-readouts.js'].includes(file))scriptLoads.push(response.body().then(body=>{loadedFrontendHashes[file]=createHash('sha256').update(body).digest('hex');}));
    if(response.request().method()!=='POST')return;
    const data=response.request().postDataJSON();
    if(data?.values?.['V1.param.opening_ratio']===.4){
      try{const result=await response.json();parameter={...parameter,receiptAt:Date.now(),commandId:result.command_id||parameter.commandId,receiptStatus:result.command_status};}catch{}
    }
  });
  let id;
  try{
    await page.goto(server.base);await expect(page.locator('#app-header')).toContainText('模块平台 · v');
    await page.locator('[data-action="start-modeling"]').first().click();
    await nav('controls');
    const programs=page.locator('[data-control-program]');
    const programIds=await programs.count()?await programs.locator('option').evaluateAll(options=>options.map(option=>option.value)):[];
    for(const programId of programIds){await programs.selectOption(programId);const enabled=page.locator('[data-control-enabled]');if(await enabled.count()&&await enabled.isChecked())await enabled.uncheck();}
    const enabled=page.locator('[data-control-enabled]');if(await enabled.count()&&await enabled.isChecked())await enabled.uncheck();
    await page.locator('[data-live-mode]').selectOption('realtime');await page.locator('[data-live-speed]').fill('1');await page.locator('[data-live-speed]').blur();
    await nav('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
    await page.locator('[data-solver-field="mode"]').selectOption('dynamic');await page.locator('[data-solver-field="dt"]').fill('0.02');await page.locator('[data-solver-field="dt"]').blur();
    await page.locator('[data-solver-continuous]').check();
    const save=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/v1/workspace'&&response.request().method()==='POST');
    await page.locator('[data-action="save"]').first().click();expect((await save).ok()).toBe(true);
    const state=await readState(),project=state.projects.find(item=>item.id===state.activeProject);
    await nav('workbench');
    const region=page.getByRole('region',{name:'V1 设备参数',exact:true});
    if(!await region.isVisible())await page.locator('.net-node[data-node="V1"]').dblclick();
    await region.locator('[data-action="float-tab"][data-value="overview"]').click();
    const created=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/v1/runs'&&response.request().method()==='POST');
    await run('run').click();const response=await created,request=response.request().postDataJSON();id=(await response.json()).run_id;
    expect(request.dt_s).toBe(.02);expect(request.duration_s).toBeNull();expect(request.execution_mode).toBe('realtime');expect(request.speed_ratio).toBe(1);
    expect((request.project.control_scripts||[]).filter(program=>program.enabled!==false)).toHaveLength(0);
    await expect.poll(async()=>{const record=await api('/runs/'+id);return record.frame?.sequence??0;},{timeout:30000}).toBeGreaterThan(25);
    await expect(region.locator('[data-device-result-source]')).toContainText('当前计算结果');
    await page.evaluate(()=>{
      const probe={samples:[],last:null};
      const sample=()=>{
        const shell=document.querySelector('[data-float-id="V1"]'),source=shell?.querySelector('[data-device-result-source]')?.textContent||'';
        const flowText=shell?.querySelector('[data-device-metric="in0:FLOW"] strong')?.textContent||'';
        const matched=source.match(/t = ([\d,.]+) s/),simTime=matched?Number(matched[1].replaceAll(',','')):null;
        const flow=Number(flowText.replaceAll(',','')),key=source+'|'+flowText;
        if(key===probe.last||simTime===null)return;probe.last=key;
        probe.samples.push({at:Date.now(),simTime,flow:Number.isFinite(flow)?flow:null,source});
      };
      probe.observer=new MutationObserver(sample);probe.observer.observe(document.body,{subtree:true,childList:true,characterData:true});sample();
      window.__runtimeFeedbackProbe=probe;
    });
    const beginning=await api('/runs/'+id),startedAt=Date.now();
    await sleep(4000);
    const endedAt=Date.now(),ending=await api('/runs/'+id);
    const observed=await page.evaluate(({startedAt,endedAt})=>window.__runtimeFeedbackProbe.samples.filter(row=>row.at>=startedAt&&row.at<=endedAt),{startedAt,endedAt});
    // The "latest complete frame" suffix can change while the displayed frame is unchanged.
    const stable=observed.filter((row,index)=>!index||row.simTime!==observed[index-1].simTime||row.flow!==observed[index-1].flow);
    const baselineFlow=Number((await region.locator('[data-device-metric="in0:FLOW"] strong').textContent()).replaceAll(',',''));
    await region.locator('input[type="number"][data-instance-param="opening"]').fill('40');await region.locator('input[type="number"][data-instance-param="opening"]').blur();
    await region.locator('[data-action="apply-instance"]').click();
    parameter.preview=await page.getByRole('dialog').innerText();
    const waitApplied=(async()=>{
      const until=Date.now()+30000;
      while(Date.now()<until){
        if(parameter.commandId){const {events}=await api('/runs/'+id+'/events');const event=events.findLast(item=>item.command_id===parameter.commandId);
          if(event?.command_status==='rejected')throw Error('Parameter rejected: '+event.message);
          if(event?.command_status==='applied'){parameter.appliedObservedAt=Date.now();parameter.appliedEvent=event;return;}}
        await sleep(20);
      }throw Error('Parameter applied event timed out');
    })();
    await page.getByRole('dialog').locator('button[type="submit"]').click();
    await Promise.all([waitApplied,page.waitForFunction(({baselineFlow})=>window.__runtimeFeedbackProbe.samples.some(row=>row.flow!==null&&row.flow<baselineFlow*.9),{baselineFlow},{timeout:30000})]);
    await expect(page.getByRole('dialog')).toHaveCount(0,{timeout:30000});
    const samples=await page.evaluate(()=>window.__runtimeFeedbackProbe.samples),drop=samples.find(row=>row.at>=parameter.sentAt&&row.flow!==null&&row.flow<baselineFlow*.9);
    if(!drop)throw Error('No real flow decrease observed after parameter request');
    parameter={...parameter,baselineFlow,drop,requestToAppliedMs:parameter.appliedObservedAt-parameter.sentAt,requestToReadoutMs:drop.at-parameter.sentAt,appliedToReadoutMs:drop.at-parameter.appliedObservedAt};
    await page.screenshot({path:output+'/browser-'+phase+'.png',fullPage:false});
    await run('stop').click();await expect.poll(async()=>(await api('/runs/'+id)).status,{timeout:30000}).toBe('cancelled');
    await page.evaluate(()=>window.__runtimeFeedbackProbe.observer.disconnect());
    const requests=[...http.values()].filter(item=>item.at>=startedAt&&item.at<=endedAt),frames=ws.filter(item=>item.at>=startedAt&&item.at<=endedAt);
    const byPath={};for(const item of requests){const key=item.path.split('?')[0].replace(id,'{run_id}');const group=byPath[key]||={requests:0,bytes:0};group.requests++;group.bytes+=item.bytes;}
    await Promise.all(scriptLoads);
    const report={phase,generatedAt:new Date().toISOString(),browserVersion:browser.version(),base:server.base,backendHashes,
      frontendHashes,loadedFrontendHashes,
      configuration:{projectId:project.id,instances:request.project.instances.length,dt_s:request.dt_s,duration_s:request.duration_s,execution_mode:request.execution_mode,speed_ratio:request.speed_ratio,controls:request.project.control_scripts||[],controllers:request.project.controllers||[],solver:project.solver},
      runId:id,window:{startedAt,endedAt,wallMs:endedAt-startedAt,startSequence:beginning.frame.sequence,endSequence:ending.frame.sequence,startSimulationTime:beginning.frame.time_s,endSimulationTime:ending.frame.time_s,
        acceptedFrames:ending.frame.sequence-beginning.frame.sequence,acceptedFramesPerSecond:(ending.frame.sequence-beginning.frame.sequence)/(endedAt-startedAt)*1000},
      display:{sourceTextChanges:observed.length,distinctFullFrameTimes:stable.length,changesPerSecond:stable.length/(endedAt-startedAt)*1000,intervalMs:intervals(stable),samples:stable,observedSamples:observed},
      network:{requests:requests.length,httpEncodedBytes:requests.reduce((sum,item)=>sum+item.bytes,0),websocketMessages:frames.length,websocketPayloadBytes:frames.reduce((sum,item)=>sum+item.bytes,0),byPath},parameter,errors,
      notes:['Display cadence counts changes to the visible device result-source time (two decimals), not solver iterations.','HTTP bytes are CDP Network.loadingFinished encodedDataLength; WebSocket bytes are UTF-8 payload lengths.','Applied time is the first observation of the server applied event, with 20 ms polling plus response latency; it is not an exact server wall-clock timestamp.','Before and after use separate browser contexts in the same Edge process and the same isolated backend process.']};
    writeFileSync(output+'/browser-'+phase+'.json',JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({phase,window:report.window,display:{changesPerSecond:report.display.changesPerSecond,intervalMs:report.display.intervalMs},network:report.network,parameter:{requestToAppliedMs:parameter.requestToAppliedMs,requestToReadoutMs:parameter.requestToReadoutMs,appliedToReadoutMs:parameter.appliedToReadoutMs},errors}));
    expect(errors).toEqual([]);return report;
  }catch(error){
    await page.screenshot({path:output+'/browser-'+phase+'-failure.png',fullPage:false}).catch(()=>{});
    writeFileSync(output+'/browser-'+phase+'-failure.json',JSON.stringify({error:String(error),errors,parameter,url:page.url(),toast:await page.locator('#toast').textContent().catch(()=>''),dialog:await page.locator('#dialog-layer').textContent().catch(()=>'')},null,2));throw error;
  }finally{
    if(id)await fetch(server.base+'/api/v1/runs/'+id+'/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'stop'})}).catch(()=>{});
    await context.close();
  }
}

try{
  if(!process.argv.includes('--after-only')){
    await sample('before');
    console.log('BEFORE_COMPLETE_WAITING_FOR_AFTER '+readyFile);
    const deadline=Date.now()+15*60*1000;
    while(!existsSync(readyFile)){if(Date.now()>deadline)throw Error('After-ready marker timed out');await sleep(500);}
  }
  await sample(argument('--after-name','after'));
}finally{await browser.close();await server.close();}
