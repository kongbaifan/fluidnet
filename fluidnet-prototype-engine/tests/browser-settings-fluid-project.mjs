import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT}),errors=[];
page.setDefaultTimeout(15000);
page.on('pageerror',error=>errors.push(error.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const current=workspace=>workspace.projects.find(project=>project.id===workspace.activeProject);
const projectField=name=>page.locator(`[data-project-field="${name}"]`);
const circuitField=name=>page.locator(`[data-circuit-field="${name}"][data-index="0"]`);
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
async function settings(tab){await nav('settings');await page.locator(`[data-action="settings-tab"][data-value="${tab}"]`).click();}
async function api(path){const response=await page.request.get(server.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();}
async function save(){
  const pending=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/v1/workspace'&&response.request().method()==='POST');
  // Click the page button directly while an edited field may still have focus.
  // An eager blur render used to swallow the first click before it reached save.
  await page.locator('#page [data-action="save"]').first().click();
  const response=await pending;expect(response.ok(),await response.text()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');
  return (await api('/workspace')).data;
}
async function normalize(workspace){
  const response=await page.request.post(server.base+'/api/v1/prototype/normalize',{data:{...workspace,format:'fluidnet-studio-prototype'}});
  expect(response.ok(),await response.text()).toBe(true);return response.json();
}
async function importPrototype(workspace){
  await settings('storage');await page.locator('#page [data-action="import"]').click();
  await page.getByLabel('选择原型 JSON').setInputFiles({name:'settings-regression.json',mimeType:'application/json',
    buffer:Buffer.from(JSON.stringify({...workspace,format:'fluidnet-studio-prototype'}))});
  await expect(page.locator('#import-preview')).toContainText('个项目');
  await submit();await expect(page.getByRole('dialog')).toHaveCount(0);
}
async function reloadSettings(tab){
  const loaded=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/v1/workspace'&&response.request().method()==='GET');
  await page.reload();expect((await loaded).ok()).toBe(true);await settings(tab);
}
async function addModule(id){await nav('modules');await page.locator(`[data-module-id="${id}"] [data-action="insert-module"]`).click();}

try {
  await page.goto(server.base+'/#projects');
  await page.locator('[data-action="open-project"][data-id="heat-loop"]').first().click();
  await settings('project');
  const name='设置回归 · 双侧换热';
  await projectField('name').fill(name);let workspace=await save();expect(current(workspace).name).toBe(name);
  await expect(page.locator('.project-picker span')).toHaveText(name);
  for(const blank of ['', '   ']){
    await projectField('name').fill(blank);await projectField('name').blur();
    workspace=await save();expect(current(workspace).name).toBe(name);
  }
  const description='编辑项目说明后直接点击保存，一次操作即写入工作区。';
  await projectField('description').fill(description);workspace=await save();
  expect(current(workspace).description).toBe(description);

  const pageCount=current(workspace).pages.length;
  await page.locator('[data-action="new-canvas"]').click();
  await page.getByRole('dialog').locator('[name="name"]').fill('   ');await submit();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').locator('[data-action="close-dialog"]').last().click();
  workspace=await save();expect(current(workspace).pages).toHaveLength(pageCount);
  await page.locator('[data-action="new-canvas"]').click();
  await page.getByRole('dialog').locator('[name="name"]').fill('辅助画布');await submit();
  workspace=await save();expect(current(workspace).pages).toHaveLength(pageCount+1);
  const canvas=current(workspace).pages.find(item=>item.name==='辅助画布');expect(canvas).toBeTruthy();
  await page.locator(`[data-action="rename-canvas"][data-id="${canvas.id}"]`).click();
  await page.getByRole('dialog').locator('[name="name"]').fill('辅助画布 · 已改名');await submit();
  workspace=await save();expect(current(workspace).pages.find(item=>item.id===canvas.id).name).toBe('辅助画布 · 已改名');
  await reloadSettings('project');
  await expect(projectField('name')).toHaveValue(name);await expect(projectField('description')).toHaveValue(description);
  await expect(page.getByText('辅助画布 · 已改名',{exact:true})).toBeVisible();

  const config={backend:'coolprop',fluid:'REFPROP::R32[0.5]&R125[0.5]',reference:'mole',phase_policy:'liquid',composition:{}};
  const owner=current(workspace);owner.medium='water';owner.fluidConfig=structuredClone(config);
  delete owner.fluid;delete owner.fluidReference;
  owner.circuitFluids=[{id:'secondary',anchor:{instance_id:'B3',port_id:'out0'},medium:'meg30',
    fluidConfig:{...structuredClone(config),fluid:'REFPROP::R32[0.4]&R125[0.6]'}}];
  await importPrototype(workspace);await settings('medium');
  await expect(projectField('fluid')).toHaveValue(config.fluid);await expect(projectField('fluidReference')).toHaveValue('mole');
  await expect(page.locator('[data-project-phase-policy]')).toHaveValue('liquid');
  await expect(circuitField('fluid')).toHaveValue(owner.circuitFluids[0].fluidConfig.fluid);
  await expect(circuitField('fluidReference')).toHaveValue('mole');
  workspace=await save();let canonical=await normalize(workspace);
  expect(canonical.fluid).toEqual(config);expect(canonical.circuit_fluids[0].fluid).toEqual(owner.circuitFluids[0].fluidConfig);
  await reloadSettings('medium');await expect(projectField('fluid')).toHaveValue(config.fluid);
  await expect(circuitField('fluidReference')).toHaveValue('mole');

  await projectField('fluidReference').selectOption('mass');
  await page.locator('[data-project-phase-policy]').selectOption('gas');
  await circuitField('fluidReference').selectOption('mass');workspace=await save();canonical=await normalize(workspace);
  expect(canonical.fluid.reference).toBe('mass');expect(canonical.fluid.phase_policy).toBe('gas');
  expect(canonical.circuit_fluids[0].fluid.reference).toBe('mass');
  await reloadSettings('medium');await expect(projectField('fluidReference')).toHaveValue('mass');
  await expect(page.locator('[data-project-phase-policy]')).toHaveValue('gas');

  // Clearing an imported override must return to the selected preset even though
  // the preserved physical config still contains the original mixture string.
  await projectField('fluid').fill('');workspace=await save();
  await page.locator('[data-project-phase-policy]').selectOption('liquid');
  await circuitField('fluid').fill('');workspace=await save();canonical=await normalize(workspace);
  expect(current(workspace).fluid).toBe('');expect(current(workspace).circuitFluids[0].fluid).toBe('');
  expect(canonical.fluid.fluid).toBe('Water');expect(canonical.circuit_fluids[0].fluid.fluid).toBe('INCOMP::MEG[0.3]');
  await reloadSettings('medium');await expect(projectField('fluid')).toHaveValue('');await expect(circuitField('fluid')).toHaveValue('');
  workspace=await save();canonical=await normalize(workspace);
  expect(canonical.fluid.fluid).toBe('Water');expect(canonical.circuit_fluids[0].fluid.fluid).toBe('INCOMP::MEG[0.3]');

  current(workspace).circuitFluids[0].anchor={instance_id:'DeletedDevice',port_id:'gone'};
  await importPrototype(workspace);await settings('medium');
  await expect(circuitField('anchor')).toHaveValue('DeletedDevice:gone');
  await expect(circuitField('anchor').locator('option:checked')).toContainText('失效');
  workspace=await save();expect(current(workspace).circuitFluids[0].anchor).toEqual({instance_id:'DeletedDevice',port_id:'gone'});
  await circuitField('anchor').selectOption('B3:out0');workspace=await save();canonical=await normalize(workspace);
  expect(canonical.circuit_fluids[0].anchor).toEqual({instance_id:'B3',port_id:'out0'});

  await nav('projects');await page.locator('[data-action="new-project"]').first().click();
  await page.getByRole('dialog').locator('[name="name"]').fill('回路端口筛选');
  await page.getByRole('dialog').locator('[name="template"]').selectOption('cold-storage-blank');await submit();
  await settings('medium');await expect(page.locator('[data-action="add-circuit-fluid"]')).toBeDisabled();
  await addModule('cold_room');await settings('medium');
  await expect(page.locator('[data-action="add-circuit-fluid"]')).toBeDisabled();await expect(page.locator('[data-circuit-row]')).toHaveCount(0);
  await addModule('lp_drum');await addModule('source');await settings('medium');
  await expect(page.locator('[data-action="add-circuit-fluid"]')).toBeEnabled();await page.locator('[data-action="add-circuit-fluid"]').click();
  const values=await circuitField('anchor').locator('option').evaluateAll(options=>options.map(option=>option.value));
  workspace=await save();const selected=current(workspace),nodes=selected.pages.flatMap(item=>item.nodes);
  const domains=values.map(value=>{const [id,port]=value.split(':'),node=nodes.find(item=>item.id===id);
    const definition=selected.moduleSnapshots?.[node.moduleId]||workspace.modules.find(item=>item.id===node.moduleId);
    return definition.ports.find(item=>item.id===port).domain;});
  expect([...new Set(domains)].sort()).toEqual(['fluid','refrigerant']);expect(values.some(value=>value.endsWith(':heat'))).toBe(false);
  await page.locator('[data-action="remove-circuit-fluid"]').click();await expect(page.locator('[data-circuit-row]')).toHaveCount(0);
  expect(errors).toEqual([]);
  await captureFhd(page,'artifacts/settings-fluid-project.png');
  console.log(JSON.stringify({projectNameValidation:true,singleClickSave:true,canvasRoundtrip:true,configOnlyFluidRoundtrip:true,
    phaseAndReferenceRoundtrip:true,clearedFluidUsesPreset:true,invalidAnchorRetained:true,circuitPortDomains:[...new Set(domains)].sort(),errors}));
} catch(error){console.error(error);await captureFhd(page,'artifacts/settings-fluid-project-failure.png').catch(()=>{});process.exitCode=1;}
finally {await browser.close();await server.close();}
