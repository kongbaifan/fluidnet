import {chromium,expect} from '@playwright/test';
import {readFileSync,mkdtempSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

// The recipe supplies equipment parameters only. Build every node/edge through the public UI.
const variant=process.argv.includes('--equipment')?'air-cooled':process.argv.includes('--cascade')?'cascade':'single-room';
const recipe=JSON.parse(readFileSync(`examples/refrigeration-modular/${variant}.recipe.json`,'utf8'));
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true}),errors=[],ids={};
page.on('pageerror',e=>errors.push(e.message));
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();};
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
const current=state=>state.projects.find(p=>p.id===state.activeProject);
async function save(){
  const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await pending).ok()).toBe(true);
  return page.evaluate(()=>window.FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
}
async function parameters(id,values,definition){
  await page.locator(`[data-node="${id}"]`).dblclick();
  const panel=page.locator(`[data-float-id="${id}"]`);
  for(const [key,value] of Object.entries(values)) {
    const spec=definition.parameters.find(p=>p.id===key);
    const displayed=spec.unit?value/(spec.unit.display_scale||1)+(spec.unit.display_offset||0):value;
    const input=panel.locator(`input[type="number"][data-instance-param="${key}"]`);
    await input.fill(String(displayed));await input.blur();
  }
  if(await panel.locator('[data-action="apply-instance"]').isEnabled()) {
    await panel.locator('[data-action="apply-instance"]').click();await submit();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }
  await panel.locator('[data-action="float-close"]').click();
}
async function run(){
  await nav('workbench');
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);const rid=(await response.json()).run_id;
  let record;
  await expect.poll(async()=>{record=await api('/runs/'+rid);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:40000}).toBe('completed');
  await expect(page.locator('#statusbar')).toContainText('已完成');return record;
}
async function stop(){
  const button=page.locator('[data-action="run-project"][data-command="stop"]').first();
  if(await button.isEnabled()){await button.click();await expect(button).toBeDisabled();}
}
try {
  await page.goto(server.base+'/#projects');
  await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="new-project"]').first().click();
  await page.getByRole('dialog').locator('[name="name"]').fill(variant==='air-cooled'?'卧式容器与风冷冷凝器':variant==='cascade'?'逐台组装的 NH₃/CO₂ 冷库':'逐台组装的单库房');
  await page.getByRole('dialog').locator('[name="template"]').selectOption('cold-storage-blank');await submit();
  expect(current(await save()).pages[0].nodes).toHaveLength(0);
  const catalog=(await api('/catalog')).modules;
  for(const item of recipe.instances) {
    await nav('modules');
    await page.locator(`[data-module-id="${item.module_id}"] [data-action="insert-module"]`).click();
    const owner=current(await save()),node=owner.pages[0].nodes.at(-1);ids[item.id]=node.id;
    expect(node.id).not.toBe(item.id);
    await parameters(node.id,item.parameters,catalog.find(m=>m.id===item.module_id));
  }
  // Arrange the independently inserted symbols by dragging, without editing application state.
  for(const item of recipe.instances) {
    const points=await page.locator(`[data-node="${ids[item.id]}"]`).evaluate((element,position)=>{
      const svg=element.ownerSVGElement,point=svg.createSVGPoint();
      const from=point.matrixTransform(element.getScreenCTM());
      point.x=position.x;point.y=80+(position.y-120)*.7;
      const to=point.matrixTransform(svg.getScreenCTM());return {from:{x:from.x,y:from.y},to:{x:to.x,y:to.y}};
    },item.position);
    await page.mouse.move(points.from.x,points.from.y);await page.mouse.down();
    await page.mouse.move(points.to.x,points.to.y,{steps:8});await page.mouse.up();
  }
  await page.locator('[data-action="fit"]').click();
  for(const [index,edge] of recipe.connections.entries()) {
    const a=ids[edge.source.instance_id],b=ids[edge.target.instance_id];
    await page.locator(`[data-port-node="${a}"][data-port-id="${edge.source.port_id}"]`).click();
    await page.locator(`[data-port-node="${b}"][data-port-id="${edge.target.port_id}"]`).click();
    await expect(page.locator('#network [data-edge]'),await page.locator('#announcement').textContent()).toHaveCount(index+1);
  }
  let owner=current(await save());expect(owner.pages[0].edges).toHaveLength(recipe.connections.length);
  expect(owner.caseId).toBeFalsy();
  await nav('settings');await page.locator('[data-action="settings-tab"][data-value="medium"]').click();
  await page.locator('[data-project-field="fluid"]').fill(recipe.fluid.fluid);
  await page.locator('[data-project-field="fluid"]').blur();
  for(const [index,circuit] of (recipe.circuit_fluids||[]).entries()) {
    await page.locator('[data-action="add-circuit-fluid"]').click();
    await page.locator(`[data-circuit-field="anchor"][data-index="${index}"]`).selectOption(ids[circuit.anchor.instance_id]+':'+circuit.anchor.port_id);
    await page.locator(`[data-circuit-field="fluid"][data-index="${index}"]`).fill(circuit.fluid.fluid);
    await page.locator(`[data-circuit-field="fluid"][data-index="${index}"]`).blur();
  }
  await nav('workbench');
  await page.locator('[data-action="validate"]').click();
  await expect(page.getByRole('dialog')).not.toContainText('必连端口未连接');
  await page.getByRole('dialog').locator('[data-action="close-dialog"]').first().click();
  await nav('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="duration"]').fill('60');await page.locator('[data-solver-field="duration"]').blur();
  await page.locator('[data-solver-field="dt"]').fill('10');await page.locator('[data-solver-field="dt"]').blur();
  const first=await run(),roomId=ids.Room,compressorId=ids.Compressor;
  expect(first.request.project.fluid.fluid).toContain(recipe.fluid.fluid);
  expect(first.frame.valid).toBe(true);
  expect(first.frame.variables[roomId+'.state.temperature_k']).toBeCloseTo(255.15,4);
  expect(first.frame.variables[compressorId+'.electric_power_w']).toBeGreaterThan(0);
  expect(Math.abs(first.frame.metrics.mass_residual_kg_circuit0)).toBeLessThan(1e-7);
  if(variant==='cascade') {
    expect(Math.abs(first.frame.metrics.mass_residual_kg_circuit1)).toBeLessThan(1e-7);
    expect(first.frame.variables[ids.Cascade+'.heat_w']).toBeGreaterThan(0);
  }
  if(variant==='air-cooled') {
    expect(first.frame.variables[ids.Low+'.state.level_height_ratio']).not.toBeCloseTo(.4,2);
    expect(first.frame.variables[ids.Low+'.volume_m3']).toBeCloseTo(.6,7);
    expect(first.frame.variables[ids.Condenser+'.air_outlet_temperature_k']).toBeGreaterThan(293.15);
    expect(first.frame.variables[ids.Condenser+'.fan_power_w']).toBe(300);
    await expect(page.locator(`[data-modular-cold-key="${ids.Low}.state.level_m"]`)).not.toHaveText('—');
    await expect(page.locator(`[data-modular-cold-key="${ids.Condenser}.air_outlet_temperature_k"]`)).not.toHaveText('—');
  }
  expect(Math.abs(first.frame.metrics.energy_residual_j)).toBeLessThan(.01);
  await expect(page.locator('[data-modular-cold-summary]')).toContainText(roomId);
  await stop();
  await parameters(roomId,{heat_input_w:6000},catalog.find(m=>m.id==='cold_room'));
  const changed=await run();expect(changed.frame.variables[roomId+'.state.temperature_k']).toBeGreaterThan(first.frame.variables[roomId+'.state.temperature_k']);
  await save();await captureFhd(page,`artifacts/refrigeration-modular-${variant}-assembled.png`);
  await stop();owner=current(await save());
  await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${owner.id}"]`).click();
  const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
  const file=join(mkdtempSync(join(tmpdir(),'fluidnet-modular-export-')),'assembled.json');await(await download).saveAs(file);
  await page.locator('[data-action="close-dialog"]').last().click();
  await page.locator('[data-action="wf-import"]').click();await page.getByLabel('单项目文件').setInputFiles(file);await submit();
  await expect(page.locator('#toast')).toContainText('项目已导入');await save();
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  const repeated=await run();expect(repeated.request.project.id).not.toBe(owner.id);
  expect(repeated.frame.variables[roomId+'.state.temperature_k']).toBeCloseTo(changed.frame.variables[roomId+'.state.temperature_k'],7);
  expect(repeated.request.project.modules).toEqual(changed.request.project.modules);
  const comparedVariables=Object.entries(changed.frame.variables).filter(([,value])=>typeof value==='number');
  for(const [key,value] of comparedVariables)expect(repeated.frame.variables[key],key).toBeCloseTo(value,6);
  await nav('curves');await page.locator('[data-action="add-chart-variable"]').click();
  await page.getByRole('dialog').locator('[name="variable"]').selectOption(roomId+'.STATE_TEMPERATURE_K');await submit();
  await expect(page.locator('#extra-charts svg path.chart-line').first()).toHaveAttribute('d',/L/);
  await expect(page.locator('#extra-charts')).toContainText(roomId+'.STATE_TEMPERATURE_K');
  await captureFhd(page,`artifacts/refrigeration-modular-${variant}-curves.png`);
  await nav('runs');await page.locator('[data-action="refresh-archives"]').click();
  await page.locator(`[data-action="open-archive"][data-id="${repeated.id}"]`).click();
  const reports=mkdtempSync(join(tmpdir(),'fluidnet-cold-reports-'));
  for(const format of ['html','csv']){
    const downloaded=page.waitForEvent('download');
    await page.locator(`[data-action="archive-report"][data-id="${repeated.id}"][data-format="${format}"]`).click();
    const target=join(reports,variant+'.'+format);await(await downloaded).saveAs(target);
    const content=readFileSync(target,'utf8');expect(content).toContain(roomId);
    if(format==='html')expect(content).toContain(repeated.id);else expect(content.split('\n').length).toBeGreaterThan(1);
  }
  expect(errors).toEqual([]);
  console.log(JSON.stringify({variant,nodes:Object.keys(ids).length,edges:recipe.connections.length,arbitraryIds:ids,initialRoomK:first.frame.variables[roomId+'.state.temperature_k'],loadedRoomK:changed.frame.variables[roomId+'.state.temperature_k'],exportReload:true,
    frozenModulesEqual:true,numericVariablesCompared:comparedVariables.length,curves:true,reports:['html','csv'],errors}));
}catch(error){console.error(error,errors);await captureFhd(page,`artifacts/refrigeration-modular-${variant}-failure.png`).catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
