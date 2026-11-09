import {chromium, expect} from '@playwright/test';
import {mkdirSync, writeFileSync} from 'node:fs';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';

// Use public authoring controls and real canvas ports. Never inject UI state.
const server = await testServer();
const browser = await chromium.launch({channel:'msedge',headless:true});
const page = await browser.newPage({...FHD_CONTEXT});
const errors=[], evidence={};
page.on('pageerror',error=>errors.push(error.message));
const output='artifacts/custom-relations';
mkdirSync(output,{recursive:true});
const api=async path=>{
  const response=await page.request.get(server.base+'/api/v1'+path);
  expect(response.ok(),await response.text()).toBe(true);
  return response.json();
};
const submit=async()=>{
  await page.locator('#dialog-form button[type="submit"]').click();
  await expect(page.locator('#dialog-form')).toHaveCount(0);
};
const navigate=async route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const save=async()=>{
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await receipt).status()).toBe(200);
  return page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
};
const active=state=>state.projects.find(p=>p.id===state.activeProject);
const publish=async()=>{
  const receipt=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');
  await page.locator('[data-action="save-module-version"]').click();
  const response=await receipt, release=await response.json();
  expect(response.status(),JSON.stringify(release)).toBe(201);
  await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
  return release.module;
};
const validate=async()=>{
  await page.locator('[data-action="validate-module-contract"]').click();
  await expect(page.locator('#module-output')).toContainText('Worker 入口与四阶段方法通过');
};
const insert=async id=>{
  await navigate('modules');
  await page.locator(`[data-module-id="${id}"] [data-action="insert-module"]`).click();
  return active(await save()).pages[0].nodes.at(-1);
};
const connect=async(a,ap,b,bp)=>{
  await page.locator(`[data-port-node="${a}"][data-port-id="${ap}"]`).click();
  await page.locator(`[data-port-node="${b}"][data-port-id="${bp}"]`).click();
};
const parameter=async(id,key,value)=>{
  await page.locator(`[data-node="${id}"]`).dblclick();
  const input=page.locator(`[data-instance-param="${key}"][data-id="${id}"]`).last();
  await input.fill(String(value)); await input.blur();
  await page.locator(`[data-action="apply-instance"][data-id="${id}"]`).last().click();
  await submit();
  await page.locator('[data-action="float-close"]').last().click();
};
const run=async()=>{
  await navigate('workbench');
  const receipt=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const response=await receipt, queued=await response.json();
  expect(response.ok(),JSON.stringify(queued)).toBe(true);
  let record;
  await expect.poll(async()=>{
    record=await api('/runs/'+queued.run_id);
    if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));
    return record.status;
  },{timeout:45000}).toBe('completed');
  await expect(page.locator('[data-result-status]').first()).toContainText('t = 1.0 s');
  return record;
};
const upgrade=async(id,version)=>{
  await navigate('workbench');
  await page.locator('[data-action="wf-upgrades"]').click();
  await page.locator(`[data-action="wf-module-versions"][data-module="${id}"]`).click();
  await page.locator(`[data-action="wf-preview-upgrade"][data-version="${version}"]`).click();
  await expect(page.getByRole('dialog')).toContainText('兼容检查通过');
  await submit();
  await expect(page.locator('#toast')).toContainText('模块版本已更新并保存');
  await expect.poll(()=>page.evaluate(moduleId=>{
    const state=JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));
    return state.projects.find(p=>p.id===state.activeProject).moduleSnapshots[moduleId].version;
  },id)).toBe(version);
};
// Independent inverse of the two author laws in series at a 130 kPa boundary.
function reference(multiplier){
  let low=0, high=20;
  for(let i=0;i<100;i++){
    const q=(low+high)/2;
    const filter=multiplier*(12000*q+4000*q*q);
    const valve=Math.min(q,2)*10000+Math.max(0,q-2)*400000;
    if(filter+valve>130000)high=q;else low=q;
  }
  return (low+high)/2;
}

try{
  await page.goto(server.base+'/#modules');
  await expect(page.locator('[data-module-id="flow_limiter"]')).toBeVisible();
  const definitions=[];
  for(const [id,name,base] of [
    ['user_filter_law','用户自写滤芯','template:custom_pressure_drop'],
    ['user_limiter_law','用户自写限流阀','flow_limiter'],
  ]){
    await navigate('modules');
    await page.locator('[data-action="new-module"]').click();
    await page.locator('[name="name"]').fill(name);
    await page.locator('[name="code"]').fill(id.toUpperCase());
    await page.locator('[name="base"]').selectOption(base);
    await submit();
    await page.locator('.editor-tabs [data-action="editor-tab"][data-value="code"]').click();
    const source=await page.locator('#module-code').inputValue();
    const rewritten=id==='user_filter_law'
      ?source.replace('drop = multiplier * (','drop = 1.5 * multiplier * (')
      :source.replace("high = ctx.parameters['high_slope']","high = 2.0 * ctx.parameters['high_slope']");
    expect(rewritten).not.toBe(source);
    await page.locator('#module-code').fill(rewritten);
    await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
    const contract=JSON.parse(await page.locator('[data-module-contract]').inputValue());
    expect(contract.sdk.api_version).toBe('0.8.0');
    await validate();
    definitions.push(await publish());
    console.log(JSON.stringify({author:id,published:true}));
  }

  await navigate('projects');
  await page.locator('[data-action="new-project"]').click();
  await page.locator('[name="name"]').fill('两个自写算法的空白项目');
  await page.locator('[name="template"]').selectOption('blank');
  await submit();
  const inlet=await insert('source'), filter=await insert(definitions[0].id),
    valve=await insert(definitions[1].id), outlet=await insert('source');
  await connect(inlet.id,'out0',filter.id,'in0');
  await connect(filter.id,'out0',valve.id,'in0');
  await connect(valve.id,'out0',outlet.id,'out0');
  await parameter(inlet.id,'pressure',250);
  await parameter(outlet.id,'pressure',120);
  await navigate('settings');
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  const duration=page.locator('[data-solver-field="duration"]');
  await duration.fill('1'); await duration.blur();
  const original=await run(), key=filter.id+'.main.mass_flow_kg_s';
  expect(original.frame.variables[key]).toBeCloseTo(reference(1.5),6);
  expect(original.frame.variables[valve.id+'.main.mass_flow_kg_s']).toBeCloseTo(reference(1.5),6);
  expect(original.frame.variables[filter.id+'.state.transferred_mass_kg']).toBeCloseTo(reference(1.5),6);
  await navigate('curves');
  await expect(page.locator('#main-flow-chart .chart-line').first()).toHaveAttribute('d',/L/);
  await captureFhd(page,output+'/author-results.png');
  await save();

  // Real author edit -> v2; existing project and old run keep v1 until explicit upgrade.
  await navigate('modules');
  await page.locator(`[data-module-id="${definitions[0].id}"] [data-action="edit-module"]`).click();
  await page.locator('[data-action="editor-tab"][data-value="code"]').first().click();
  const previous=await page.locator('#module-code').inputValue();
  const revised=previous.replace('drop = 1.5 * multiplier * (','drop = 2.0 * multiplier * (');
  expect(revised).not.toBe(previous);
  await page.locator('#module-code').fill(revised);
  await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
  await validate();
  expect((await publish()).version).toBe(2);
  const pinned=await run();
  expect(pinned.frame.variables[key]).toBeCloseTo(reference(1.5),6);
  await upgrade(definitions[0].id,2);
  const upgraded=await run();
  expect(upgraded.frame.variables[key]).toBeCloseTo(reference(2),6);
  const historical=await api('/runs/'+original.id);
  expect(historical.frame.variables[key]).toBe(original.frame.variables[key]);
  await upgrade(definitions[0].id,1);
  await save();
  await page.reload();
  await expect(page.locator('[data-action="run-project"][data-command="run"]').first()).toBeVisible();
  const restored=await run();
  expect(restored.frame.variables[key]).toBeCloseTo(reference(1.5),6);
  expect(restored.request.project.modules.find(m=>m.id===definitions[0].id).version).toBe(1);
  expect(errors).toEqual([]);
  evidence.project=original.request.project.id;
  evidence.instances={filter:filter.id,valve:valve.id};
  evidence.flows={original:original.frame.variables[key],pinned:pinned.frame.variables[key],
    upgraded:upgraded.frame.variables[key],restored:restored.frame.variables[key]};
  evidence.reference={v1:reference(1.5),v2:reference(2)};
  evidence.pageErrors=errors;
  writeFileSync(output+'/browser-validation.json',JSON.stringify(evidence,null,2));
  console.log(JSON.stringify(evidence));
}finally{
  await browser.close();
  await server.close();
}
