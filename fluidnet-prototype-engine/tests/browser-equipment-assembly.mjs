import {chromium,expect} from '@playwright/test';
import {readFileSync,mkdtempSync,mkdirSync,writeFileSync,copyFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,basename} from 'node:path';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const path=process.argv[2];if(!path)throw Error('Provide a recipe or Project file');
const recipe=JSON.parse(readFileSync(path,'utf8')),ids={},errors=[];
const evidenceFlag=process.argv.indexOf('--evidence-dir'),evidenceDir=evidenceFlag<0?null:process.argv[evidenceFlag+1];
if(evidenceFlag>=0&&(!evidenceDir||evidenceDir.startsWith('--')))throw Error('--evidence-dir needs a directory');
if(evidenceDir)mkdirSync(evidenceDir,{recursive:true});
const recipeTiming=process.argv.includes('--use-recipe-timing');
const duration=recipeTiming?recipe.duration_s:1,step=recipeTiming?recipe.dt_s:.1;
if(!Number.isFinite(duration)||duration<=0||!Number.isFinite(step)||step<=0)throw Error('Invalid recipe duration/dt');
const standardPlant=process.argv.includes('--standard-plant');
if(standardPlant&&recipe.id!=='hvac-basic-plant')throw Error('--standard-plant requires the standard HVAC project');
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true});
page.on('pageerror',e=>errors.push(e.message));
const api=async url=>{const response=await page.request.get(server.base+'/api/v1'+url);expect(response.ok(),await response.text()).toBe(true);return response.json();};
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
async function save(){
 const wait=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
 await page.locator('[data-action="save"]').first().click();expect((await wait).ok()).toBe(true);
 return page.evaluate(async () =>{const s=(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));return s.projects.find(p=>p.id===s.activeProject);});
}
async function run(){
 await nav('workbench');const wait=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
 await page.locator('[data-command="run"][data-action="run-project"]').first().click();
 const r=await wait;expect(r.ok(),await r.text()).toBe(true);const rid=(await r.json()).run_id;let record;
 await expect.poll(async()=>{record=await api('/runs/'+rid);if(record.status==='failed')throw Error(JSON.stringify(record.frame?.diagnostics));return record.status;},{timeout:standardPlant?90000:45000}).toBe('completed');
 await expect(page.locator('#statusbar')).toContainText('已完成');return record;
}
async function arrange(id,index){
 const large=recipe.instances.length>36;
 const position=large?{x:110+(index%9)*130,y:110+Math.floor(index/9)*100}:{x:110+(index%6)*210,y:110+Math.floor(index/6)*180};
 if(large)await page.locator('[data-action="fit"]').click();
 let points;
 for(let attempt=0;attempt<12;attempt++){
  points=await page.locator(`[data-node="${id}"]`).evaluate(async (element,position) =>{
   const svg=element.ownerSVGElement,point=svg.createSVGPoint(),box=document.getElementById('network-area').getBoundingClientRect();
   const from=point.matrixTransform(element.getScreenCTM());point.x=position.x;point.y=position.y;
   const to=point.matrixTransform(svg.getScreenCTM()),inside=p=>p.x>box.left+35&&p.x<box.right-35&&p.y>box.top+65&&p.y<box.bottom-90;
   return {from:{x:from.x,y:from.y},to:{x:to.x,y:to.y},visible:inside(from)&&inside(to)};
  },position);
  if(points.visible)break;
  await page.locator('[data-action="zoom-out"]').click();
 }
 expect(points.visible,'drag endpoints must remain inside the canvas').toBe(true);
 await page.mouse.move(points.from.x,points.from.y);await page.mouse.down();
 await page.mouse.move(points.to.x,points.to.y,{steps:8});await page.mouse.up();
 if(large){await page.locator('[data-action="fit"]').click();await page.locator('[data-action="zoom-out"]').click();}
}
async function observe(variable){
 await nav('curves');await page.locator('[data-action="add-chart-variable"]').click();
 await page.getByRole('dialog').locator('[name="variable"]').selectOption(variable);await submit();
 await expect(page.locator('#extra-charts svg path.chart-line').first()).toHaveAttribute('d',/L/);
}
try{
 await page.goto(server.base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v',{timeout:15000});
 const {modules}=await api('/modules'),catalog=await api('/catalog');
 const definitions=[...catalog.modules,...modules];
 await page.locator('[data-action="new-project"]').first().click();
 await page.getByRole('dialog').locator('[name="name"]').fill('组装 '+recipe.name);
 await page.getByRole('dialog').locator('[name="template"]').selectOption('blank');await submit();
 for(const [index,item] of recipe.instances.entries()){
  await nav('modules');await page.locator(`[data-module-id="${item.module_id}"] [data-action="insert-module"]`).click();
  const owner=await save(),n=owner.pages.flatMap(p=>p.nodes).at(-1);ids[item.id]=n.id;
  await arrange(n.id,index);
  const definition=definitions.find(m=>m.id===item.module_id),binding=catalog.prototype_parameter_bindings[item.module_id]||{};
  expect(definition,'definition for '+item.module_id).toBeTruthy();
  await page.locator(`[data-node="${n.id}"]`).dblclick();const panel=page.locator(`[data-float-id="${n.id}"]`);
  for(const [key,value] of Object.entries(item.parameters||{})){
   const spec=definition.parameters.find(p=>p.id===key),uiKey=Object.keys(binding).find(k=>binding[k]===key)||key;
   expect(spec,item.module_id+'.'+key).toBeTruthy();
   const inputs=panel.locator(`input[data-instance-param="${uiKey}"],textarea[data-instance-param="${uiKey}"]`);
   if(!await inputs.count()){
    if(key==='humidity_ratio_kg_kg'&&!recipe.solver?.moist_air)continue;
    throw Error('Missing editor '+item.module_id+'.'+key);
   }
   for(const details of await inputs.last().locator('xpath=ancestor::details').all()){
    if(await details.getAttribute('open')===null)await details.locator(':scope > summary').click();
   }
   if(spec.value_type==='boolean')await inputs.setChecked(value);
   else if(spec.value_type==='curve')await inputs.fill(JSON.stringify(value));
   else if(spec.value_type==='text')await inputs.fill(String(value));
   else await panel.locator(`input[type=number][data-instance-param="${uiKey}"]`).fill(String(spec.unit?value/spec.unit.display_scale+spec.unit.display_offset:value));
   await inputs.last().blur();
  }
  if(await panel.locator('[data-action="apply-instance"]').isEnabled()){await panel.locator('[data-action="apply-instance"]').click();await submit();}
  await panel.locator('[data-action="float-close"]').click();
  const applied=(await save()).pages.flatMap(p=>p.nodes).find(node=>node.id===n.id).params;
  for(const [key,value] of Object.entries(item.parameters||{})){
   if(key==='humidity_ratio_kg_kg'&&!recipe.solver?.moist_air)continue;
   const spec=definition.parameters.find(p=>p.id===key),uiKey=Object.keys(binding).find(k=>binding[k]===key)||key;
   const expected=spec.value_type==='number'&&spec.unit?value/spec.unit.display_scale+spec.unit.display_offset:value;
   if(typeof expected==='number')expect(applied[uiKey],item.id+'.'+key+' applied').toBeCloseTo(expected,10);
   else expect(applied[uiKey],item.id+'.'+key+' applied').toEqual(expected);
  }
 }
 await page.locator('[data-action="fit"]').click();
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
 for(const [key,value] of Object.entries({duration,dt:step,maxIter:recipe.solver?.max_iterations||80})){
  await page.locator(`[data-solver-field="${key}"]`).fill(String(value));await page.locator(`[data-solver-field="${key}"]`).blur();
 }
 if(recipe.solver?.moist_air){
  await nav('air');await page.locator('[data-action="air-config"]').click();
  await page.getByRole('dialog').locator('[name="enabled"]').check();
  if(standardPlant){
   await page.getByRole('dialog').locator('[name="mode"]').selectOption('dynamic');
   await page.getByRole('dialog').locator('[name="maxIterations"]').fill(String(recipe.solver.moist_air_options.max_iterations));
  }
  await page.getByRole('dialog').locator('[name="duration"]').fill(String(duration));await page.getByRole('dialog').locator('[name="dt"]').fill(String(step));await submit();
 }
 if(standardPlant){
  await nav('controls');
  for(const meter of recipe.measurements){
   await page.locator(`[data-action="add-meter"][data-kind="${meter.kind}"]`).click();
   const dialog=page.getByRole('dialog');await dialog.locator('[name="label"]').fill(meter.label);
   for(const [index,source] of meter.sources.entries()){
    const dot=source.indexOf('.'),mapped=ids[source.slice(0,dot)]+source.slice(dot);
    await dialog.locator(`[name="source${index}"]`).selectOption(mapped);
   }
   await submit();
  }
  await expect(page.locator('[data-meter-card]')).toHaveCount(recipe.measurements.length);
  await expect(page.locator('#toast')).not.toContainText('尚未识别此操作');
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
 if(recipeTiming){await nav('controls');await page.locator('[data-live-mode]').selectOption('fast');}
 const first=await run();expect(first.frame.valid).toBe(true);
 for(const item of recipe.instances){
  const actual=first.request.project.instances.find(node=>node.id===ids[item.id]);
  for(const [key,value] of Object.entries(item.parameters||{})){
   if(key==='humidity_ratio_kg_kg'&&!recipe.solver?.moist_air)continue;
   if(typeof value==='number')expect(actual.parameters[key],item.id+'.'+key+' canonical').toBeCloseTo(value,8);
   else expect(actual.parameters[key],item.id+'.'+key+' canonical').toEqual(value);
  }
 }
 let comparison=first;
 if(standardPlant){
  await page.locator('[data-command="stop"][data-action="run-project"]').first().click();
  await page.locator(`[data-node="${ids.Balance1}"]`).dblclick();
  const panel=page.locator(`[data-float-id="${ids.Balance1}"]`),opening=panel.locator('input[type="number"][data-instance-param="opening_ratio"]');
  await expect(opening).toHaveValue('80');await opening.fill('40');await opening.blur();
  await panel.locator('[data-action="apply-instance"]').click();await submit();
  await panel.locator('[data-action="float-close"]').click();comparison=await run();
  expect(comparison.frame.variables[ids.Balance1+'.main.mass_flow_kg_s']).toBeLessThan(first.frame.variables[ids.Balance1+'.main.mass_flow_kg_s']);
  expect(comparison.frame.variables[ids.Balance2+'.main.mass_flow_kg_s']).toBeGreaterThan(first.frame.variables[ids.Balance2+'.main.mass_flow_kg_s']);
  const owner=await save(),meter=owner.measurements.find(m=>m.label==='支路 1 体积流量');
  await observe('measurement.'+meter.id);
  await nav('workbench');
 }
 const snapshot=await save();await captureFhd(page,'artifacts/assembly-'+basename(path).replace(/\.[^.]+$/,'')+'.png');
 if(evidenceDir)await captureFhd(page,join(evidenceDir,'assembled-canvas.png'));
 await page.locator('[data-command="stop"][data-action="run-project"]').first().click();
 await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${snapshot.id}"]`).click();
 const wait=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();
 const file=join(mkdtempSync(join(tmpdir(),'equipment-project-')),'project.json');await(await wait).saveAs(file);
 if(evidenceDir)copyFileSync(file,join(evidenceDir,'ui-built.project.json'));
 await page.locator('[data-action="close-dialog"]').last().click();await page.locator('[data-action="wf-import"]').click();
 await page.getByLabel('单项目文件').setInputFiles(file);await submit();await save();await page.reload();
 await expect(page.locator('#app-header')).toContainText('模块平台 · v',{timeout:15000});const repeated=await run();
 for(const [key,value] of Object.entries(comparison.frame.variables))if(typeof value==='number')expect(repeated.frame.variables[key],key).toBeCloseTo(value,6);
 await nav('runs');await page.locator('[data-action="refresh-archives"]').click();
 await page.locator(`[data-action="open-archive"][data-id="${repeated.id}"]`).click();
 const reports=mkdtempSync(join(tmpdir(),'equipment-reports-'));
 for(const format of ['html','csv']){
  const download=page.waitForEvent('download');
  await page.locator(`[data-action="archive-report"][data-id="${repeated.id}"][data-format="${format}"]`).click();
  const target=join(reports,'report.'+format);await(await download).saveAs(target);
  const contents=readFileSync(target,'utf8');if(format==='html')expect(contents).toContain(repeated.id);else expect(contents.split('\n').length).toBeGreaterThan(1);
  if(evidenceDir)copyFileSync(target,join(evidenceDir,'report.'+format));
  expect(contents).toContain(Object.values(ids).find(id=>Object.keys(repeated.frame.variables).some(key=>key.startsWith(id+'.'))));
 }
 expect(errors).toEqual([]);
 const evidence={path,standardPlant,nodes:Object.keys(ids).length,edges:recipe.connections.length,
  valveChanged:standardPlant,curves:standardPlant,exportReload:true,reports:['html','csv'],duration_s:duration,dt_s:step,ids,errors};
 if(evidenceDir)writeFileSync(join(evidenceDir,'assembly-result.json'),JSON.stringify({...evidence,first,repeated},null,2));
 console.log(JSON.stringify(evidence));
}catch(error){console.error(error,errors,await page.locator('#announcement').textContent(),await page.locator('#toast').textContent());await captureFhd(page,'artifacts/equipment-assembly-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await server.close();}
