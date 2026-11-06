import {chromium,expect} from '@playwright/test';
import {readFileSync,mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,basename} from 'node:path';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const path=process.argv[2];if(!path)throw Error('Provide a recipe or Project file');
const recipe=JSON.parse(readFileSync(path,'utf8')),ids={},errors=[];
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true});
page.on('pageerror',e=>errors.push(e.message));
const api=async url=>{const response=await page.request.get(server.base+'/api/v1'+url);expect(response.ok(),await response.text()).toBe(true);return response.json();};
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
async function save(){
 const wait=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
 await page.locator('[data-action="save"]').first().click();expect((await wait).ok()).toBe(true);
 return page.evaluate(()=>{const s=window.FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));return s.projects.find(p=>p.id===s.activeProject);});
}
async function run(){
 await nav('workbench');const wait=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
 await page.locator('[data-command="run"][data-action="run-project"]').first().click();
 const r=await wait;expect(r.ok(),await r.text()).toBe(true);const rid=(await r.json()).run_id;let record;
 await expect.poll(async()=>{record=await api('/runs/'+rid);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:45000}).toBe('completed');
 await expect(page.locator('#statusbar')).toContainText('已完成');return record;
}
try{
 await page.goto(server.base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v',{timeout:15000});
 const {modules}=await api('/modules'),catalog=await api('/catalog');
 await page.locator('[data-action="new-project"]').first().click();
 await page.getByRole('dialog').locator('[name="name"]').fill('组装 '+recipe.name);
 await page.getByRole('dialog').locator('[name="template"]').selectOption('blank');await submit();
 for(const item of recipe.instances){
  await nav('modules');await page.locator(`[data-module-id="${item.module_id}"] [data-action="insert-module"]`).click();
  const owner=await save(),n=owner.pages.flatMap(p=>p.nodes).at(-1);ids[item.id]=n.id;
  const definition=modules.find(m=>m.id===item.module_id),binding=catalog.prototype_parameter_bindings[item.module_id]||{};
  await page.locator(`[data-node="${n.id}"]`).dblclick();const panel=page.locator(`[data-float-id="${n.id}"]`);
  for(const [key,value] of Object.entries(item.parameters||{})){
   const spec=definition.parameters.find(p=>p.id===key),uiKey=Object.keys(binding).find(k=>binding[k]===key)||key;
   const inputs=panel.locator(`[data-instance-param="${uiKey}"]`);
   if(!await inputs.count()){
    if(key==='humidity_ratio_kg_kg'&&!recipe.solver?.moist_air)continue;
    throw Error('Missing editor '+item.module_id+'.'+key);
   }
   if(spec.value_type==='boolean')await inputs.setChecked(value);
   else if(spec.value_type==='curve')await inputs.fill(JSON.stringify(value));
   else if(spec.value_type==='text')await inputs.fill(String(value));
   else await panel.locator(`input[type=number][data-instance-param="${uiKey}"]`).fill(String(spec.unit?value/spec.unit.display_scale+spec.unit.display_offset:value));
   await inputs.last().blur();
  }
  if(await panel.locator('[data-action="apply-instance"]').isEnabled()){await panel.locator('[data-action="apply-instance"]').click();await submit();}
  await panel.locator('[data-action="float-close"]').click();
 }
 for(const edge of recipe.connections){
  for(const endpoint of [edge.source,edge.target])await page.locator(`[data-port-node="${ids[endpoint.instance_id]}"][data-port-id="${endpoint.port_id}"]`).click();
 }
 expect((await save()).pages[0].edges).toHaveLength(recipe.connections.length);
 await nav('settings');await page.locator('[data-action="settings-tab"][data-value="medium"]').click();
 await page.locator('[data-project-field="fluid"]').fill(recipe.fluid?.fluid||'Water');await page.locator('[data-project-field="fluid"]').blur();
 await page.getByLabel('项目相态策略').selectOption(recipe.fluid?.phase_policy||'single_phase');
 for(const [i,c] of (recipe.circuit_fluids||[]).entries()){
  await page.locator('[data-action="add-circuit-fluid"]').click();
  await page.locator(`[data-circuit-field="anchor"][data-index="${i}"]`).selectOption(ids[c.anchor.instance_id]+':'+c.anchor.port_id);
  await page.locator(`[data-circuit-field="fluid"][data-index="${i}"]`).fill(c.fluid.fluid);await page.locator(`[data-circuit-field="fluid"][data-index="${i}"]`).blur();
 }
 await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
 await page.locator('[data-solver-option="property_coupling"]').selectOption(recipe.solver?.property_coupling||'reference');
 for(const [key,value] of Object.entries({duration:1,dt:.1,maxIter:recipe.solver?.max_iterations||80})){
  await page.locator(`[data-solver-field="${key}"]`).fill(String(value));await page.locator(`[data-solver-field="${key}"]`).blur();
 }
 if(recipe.solver?.moist_air){
  await nav('air');await page.locator('[data-action="air-config"]').click();
  await page.getByRole('dialog').locator('[name="enabled"]').check();
  await page.getByRole('dialog').locator('[name="duration"]').fill('1');await page.getByRole('dialog').locator('[name="dt"]').fill('.1');await submit();
 }
 if(recipe.coupling_mode==='storage_v1'){
  await nav('workbench');await page.locator('[data-action="cs-coupling-mode"]').click();
  await page.getByRole('dialog').locator('[name="mode"]').selectOption('storage_v1');await submit();
 }
 for(const [index,link] of (recipe.thermal_couplings||[]).entries()){
  await nav('workbench');await page.locator('[data-action="cs-coupling"]').click();
  if(index)await page.getByRole('dialog').locator('[data-action="cs-add-coupling"]').click();
  const dialog=page.getByRole('dialog');
  await dialog.locator('[name="id"]').fill(link.id);
  await dialog.locator('[name="fluid_instance_id"]').selectOption(ids[link.fluid_instance_id]);
  await dialog.locator('[name="fluid_channel_id"]').selectOption(link.fluid_channel_id);
  await dialog.locator('[name="refrigerant_vessel_id"]').selectOption(ids[link.refrigerant_vessel_id]);
  await dialog.locator('[name="ua"]').fill(String(link.ua_w_k));await submit();
 }
 const first=await run();expect(first.frame.valid).toBe(true);
 const snapshot=await save();await captureFhd(page,'artifacts/assembly-'+basename(path).replace(/\.[^.]+$/,'')+'.png');
 await page.locator('[data-command="stop"][data-action="run-project"]').first().click();
 await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${snapshot.id}"]`).click();
 const wait=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
 const file=join(mkdtempSync(join(tmpdir(),'equipment-project-')),'project.json');await(await wait).saveAs(file);
 await page.locator('[data-action="close-dialog"]').last().click();await page.locator('[data-action="wf-import"]').click();
 await page.getByLabel('单项目文件').setInputFiles(file);await submit();await save();await page.reload();
 await expect(page.locator('#app-header')).toContainText('模块平台 · v',{timeout:15000});const repeated=await run();
 for(const [key,value] of Object.entries(first.frame.variables))if(typeof value==='number')expect(repeated.frame.variables[key],key).toBeCloseTo(value,6);
 await nav('runs');await page.locator('[data-action="refresh-archives"]').click();
 await page.locator(`[data-action="open-archive"][data-id="${repeated.id}"]`).click();
 const reports=mkdtempSync(join(tmpdir(),'equipment-reports-'));
 for(const format of ['html','csv']){
  const download=page.waitForEvent('download');
  await page.locator(`[data-action="archive-report"][data-id="${repeated.id}"][data-format="${format}"]`).click();
  const target=join(reports,'report.'+format);await(await download).saveAs(target);
  const contents=readFileSync(target,'utf8');if(format==='html')expect(contents).toContain(repeated.id);else expect(contents.split('\n').length).toBeGreaterThan(1);
  expect(contents).toContain(Object.values(ids).find(id=>Object.keys(repeated.frame.variables).some(key=>key.startsWith(id+'.'))));
 }
 expect(errors).toEqual([]);console.log(JSON.stringify({path,nodes:Object.keys(ids).length,edges:recipe.connections.length,exportReload:true,reports:['html','csv'],errors}));
}catch(error){console.error(error,errors,await page.locator('#announcement').textContent(),await page.locator('#toast').textContent());await captureFhd(page,'artifacts/equipment-assembly-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
