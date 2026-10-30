import {chromium, expect} from '@playwright/test';
import {mkdirSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {testServer} from './browser-server.mjs';
import {FHD_CONTEXT, captureFhd} from './browser-viewport.mjs';

// PF-1: build on a blank canvas through the public authoring UI, with generated
// instance IDs. Do not import a seed project or write application state in JS.
const server = await testServer();
const browser = await chromium.launch({channel:'msedge', headless:true});
const page = await browser.newPage({...FHD_CONTEXT});
const errors = [], evidence = {};
page.on('pageerror', error => errors.push(error.message));
const output = 'artifacts/platform-extension/pf1';
mkdirSync(output, {recursive:true});
const api = async path => {
  const response = await page.request.get(server.base + '/api/v1' + path);
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
};
const submit = async () => {
  await page.locator('#dialog-form button[type="submit"]').click();
  await expect(page.locator('#dialog-form')).toHaveCount(0);
};
const navigate = async route => {
  await page.locator(`.rail-link[data-route="${route}"]`).click();
};
const save = async () => {
  const receipt = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/workspace' && r.request().method() === 'POST');
  await page.locator('[data-action="save"]').first().click();
  expect((await receipt).status()).toBe(200);
  return page.evaluate(() => JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
};
const active = state => state.projects.find(p => p.id === state.activeProject);
const edit = async id => {
  await navigate('modules');
  await page.locator(`[data-module-id="${id}"] [data-action="edit-module"]`).click();
  await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
};
const publish = async () => {
  const receipt = page.waitForResponse(r => r.url().endsWith('/modules/versions') && r.request().method() === 'POST');
  await page.locator('[data-action="save-module-version"]').click();
  const response = await receipt, release = await response.json();
  expect(response.status(), JSON.stringify(release)).toBe(201);
  await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
  return release.module;
};
const insert = async id => {
  await navigate('modules');
  await page.locator(`[data-module-id="${id}"] [data-action="insert-module"]`).click();
  const owner = active(await save());
  return owner.pages[0].nodes.at(-1);
};
const connect = async (a, ap, b, bp) => {
  await page.locator(`[data-port-node="${a}"][data-port-id="${ap}"]`).click();
  await page.locator(`[data-port-node="${b}"][data-port-id="${bp}"]`).click();
};
const parameter = async (id, key, value) => {
  await page.locator(`[data-node="${id}"]`).dblclick();
  await page.locator(`[data-instance-param="${key}"][data-id="${id}"]`).last().fill(String(value));
  await page.locator(`[data-instance-param="${key}"][data-id="${id}"]`).last().blur();
  await page.locator(`[data-action="apply-instance"][data-id="${id}"]`).last().click();
  await submit();
  await page.locator('[data-action="float-close"]').last().click();
};
const run = async () => {
  await navigate('workbench');
  const receipt = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/runs' && r.request().method() === 'POST');
  await page.locator('[data-action="run-project"][data-command="run"]').first().click();
  const queued = await (await receipt).json();
  let record;
  await expect.poll(async () => {
    record = await api('/runs/' + queued.run_id);
    if (record.status === 'failed') throw Error(JSON.stringify(record.frame?.diagnostics));
    return record.status;
  }, {timeout:45000}).toBe('completed');
  await expect(page.locator('[data-result-status]').first()).toContainText('t = 1.0 s');
  return record;
};
const upgrade = async (id, version) => {
  await navigate('workbench');
  await page.locator('[data-action="wf-upgrades"]').click();
  await page.locator(`[data-action="wf-module-versions"][data-module="${id}"]`).click();
  await page.locator(`[data-action="wf-preview-upgrade"][data-version="${version}"]`).click();
  await expect(page.getByRole('dialog')).toContainText('兼容检查通过');
  await submit();
  await expect(page.locator('#toast')).toContainText('模块版本已更新并保存');
  await expect.poll(() => page.evaluate(moduleId => {
    const state=JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));
    return state.projects.find(p=>p.id===state.activeProject).moduleSnapshots[moduleId].version;
  }, id)).toBe(version);
};

try {
  await page.goto(server.base + '/#modules');
  await expect(page.locator('[data-module-id="programmable_valve"]')).toBeVisible();
  await page.locator('[data-action="new-module"]').click();
  await page.locator('[name="name"]').fill('作者阻力设备');
  await page.locator('[name="code"]').fill('PF1_RESISTOR');
  await page.locator('[name="base"]').selectOption('template:resistance');
  await submit();
  await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
  const contract = JSON.parse(await page.locator('[data-module-contract]').inputValue());
  const coefficient = contract.parameters.find(p => p.id === 'loss_coefficient');
  coefficient.default = 12; coefficient.minimum = 1; coefficient.maximum = 100; coefficient.runtime = true;
  const diameter = contract.parameters.find(p => p.id === 'diameter_m');
  diameter.default = .04;
  diameter.unit = {quantity:'length',canonical_unit:'m',display_unit:'mm',display_scale:.001,display_offset:0};
  await page.locator('[data-module-contract]').fill(JSON.stringify(contract));
  await page.locator('[data-action="validate-module-contract"]').click();
  await expect(page.locator('#module-output')).toContainText('Worker 入口与四阶段方法通过');
  await page.locator('[data-action="configure-module-tests"]').click();
  const forward = page.locator('[data-suite-case="0"]');
  await forward.locator('[data-suite-action="add-assertion"]').click();
  await forward.getByLabel('结果变量', {exact:true}).fill('D1.main.pressure_drop_pa');
  await forward.getByLabel('预期值', {exact:true}).fill('130000');
  await forward.getByLabel('绝对容差', {exact:true}).fill('.1');
  await submit();
  const suiteResponse = page.waitForResponse(r => r.url().endsWith('/modules/test-suite'));
  await page.locator('[data-action="module-test-suite"]').click();
  const suite = await (await suiteResponse).json();
  expect(suite.passed, JSON.stringify(suite)).toBe(true);
  await expect(page.locator('[data-action="module-test-suite"]')).toBeEnabled();
  const v1 = await publish();
  evidence.suite = {passed:suite.passed, cases:suite.cases.length};

  await navigate('projects');
  await page.locator('[data-action="new-project"]').click();
  await page.locator('[name="name"]').fill('自主建模验收');
  await page.locator('[name="template"]').selectOption('blank');
  await submit();
  const inlet = await insert('source'), resistor = await insert(v1.id), outlet = await insert('source');
  expect([inlet.id,resistor.id,outlet.id].some(id => ['B1','B2','D1','V1','P1'].includes(id))).toBe(false);
  expect(resistor.params.diameter_m).toBe(40); // display unit mm, engine unit m
  expect(resistor.params.loss_coefficient).toBe(12);
  await connect(inlet.id,'out0',resistor.id,'in0');
  await connect(resistor.id,'out0',outlet.id,'out0');
  await parameter(inlet.id,'pressure',250);
  await parameter(outlet.id,'pressure',120);
  await navigate('settings');
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="duration"]').fill('1');
  await page.locator('[data-solver-field="duration"]').blur();
  await navigate('controls');
  await page.locator('[data-action="add-pid"]').click();
  await page.locator('[data-pid-field="measurement"]').selectOption(resistor.id + '.loss_coefficient');
  await page.locator('[data-pid-field="target"]').selectOption(resistor.id + '.loss_coefficient');
  await page.locator('[data-pid-field="manual_output"]').fill('12');
  await page.locator('[data-pid-field="manual_output"]').blur();
  await navigate('curves');
  await page.locator('[data-action="add-chart-variable"]').click();
  await page.locator('[name="variable"]').selectOption(resistor.id + '.IN0_FLOW');
  await submit();
  const original = await run(), flowKey = resistor.id + '.main.mass_flow_kg_s';
  const flow = original.frame.variables[flowKey];
  // Independent local-resistance equation: Δp = K m² / (2 ρ A²).
  const density = original.frame.variables[resistor.id + '.density_kg_m3'];
  const reference = Math.PI * .04 ** 2 / 4 * Math.sqrt(2 * density * 130000 / 12);
  expect(Math.abs(flow / reference - 1)).toBeLessThan(1e-6);
  expect(original.request.project.controllers[0].instance_id).toBe(resistor.id);
  await navigate('curves');
  await expect(page.locator('#extra-chart-0 .chart-line')).toHaveAttribute('d', /L/);
  await expect(page.locator('#main-flow-chart .chart-line')).toHaveAttribute('d', /L/);
  await expect(page.locator('.chart-variable-list')).not.toContainText('P1');
  expect(active(await save()).run.history.at(-1).q).toBeCloseTo(flow,7);
  const csvDownload=page.waitForEvent('download');
  await page.locator('[data-action="export"][data-format="csv"]').click();
  const csvFile=join(mkdtempSync(join(tmpdir(),'pf1-curves-')),'curves.csv');
  await (await csvDownload).saveAs(csvFile);
  const csv=readFileSync(csvFile,'utf8');
  expect(csv.split('\n')[0]).toContain(resistor.id + '.mass_flow_kg_s');
  expect(csv.split('\n')[0]).not.toContain('P1');
  expect(csv.split('\n').at(-1).split(',')).toHaveLength(5); // time, flow, pressure, temperature, added variable
  await captureFhd(page, output + '/custom-project.png');
  evidence.original = {project:original.request.project.id,instance:resistor.id,flow,reference};

  await edit(v1.id);
  await page.locator('[data-action="editor-tab"][data-value="code"]').first().click();
  const source = await page.locator('#module-code').inputValue();
  await page.locator('#module-code').fill(source.replace('loss_coefficient=coefficient,','loss_coefficient=coefficient * 4,'));
  await page.locator('[data-action="editor-tab"][data-value="contract"]').first().click();
  const v2 = await publish();
  expect(v2.version).toBe(2);
  await upgrade(v1.id, 2);
  const changed = await run();
  expect(changed.frame.variables[flowKey] / flow).toBeCloseTo(.5, 6);
  expect(changed.request.project.controllers).toEqual(original.request.project.controllers);
  await upgrade(v1.id, 1);
  expect((await run()).frame.variables[flowKey]).toBeCloseTo(flow, 7);
  await page.locator('[data-action="create-composite"]').click();
  await page.locator('[name="id"]').fill('pf1_assembly');
  await page.locator('[name="name"]').fill('作者阻力组合');
  await page.locator(`[name="node_${resistor.id}"]`).check();
  await submit();
  const assembly = await publish();
  expect(assembly.composite.children[0].version).toBe(1);
  expect(assembly.composite.children[0].definition_hash).toBe(v1.definition_hash);
  // Insert the published composite into a second blank project.
  await navigate('projects');
  await page.locator('[data-action="new-project"]').click();
  await page.locator('[name="name"]').fill('组合复用验收');
  await page.locator('[name="template"]').selectOption('blank');
  await submit();
  const left = await insert('source'), group = await insert(assembly.id), right = await insert('source');
  await connect(left.id,'out0',group.id,assembly.ports.find(p => p.direction === 'in').id);
  await connect(group.id,assembly.ports.find(p => p.direction === 'out').id,right.id,'out0');
  await parameter(left.id,'pressure',250);
  await parameter(right.id,'pressure',120);
  await navigate('settings');
  await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="duration"]').fill('1');
  await page.locator('[data-solver-field="duration"]').blur();
  const composed = await run(), groupFlow = group.id + '.main.mass_flow_kg_s';
  expect(composed.frame.variables[groupFlow]).toBeCloseTo(flow, 7);
  // A new assembly release explicitly adopts the new child definition. Merely
  // publishing that child earlier did not alter the existing assembly's result.
  await edit(assembly.id);
  const groupContract=JSON.parse(await page.locator('[data-module-contract]').inputValue());
  groupContract.composite.modules=groupContract.composite.modules.map(module=>module.id===v1.id?v2:module);
  Object.assign(groupContract.composite.children[0],{version:2,content_hash:v2.content_hash,definition_hash:v2.definition_hash});
  await page.locator('[data-module-contract]').fill(JSON.stringify(groupContract));
  const assemblyV2=await publish();
  expect(assemblyV2.version).toBe(2);
  await upgrade(assembly.id,2);
  expect((await run()).frame.variables[groupFlow]/flow).toBeCloseTo(.5,6);
  await upgrade(assembly.id,1);
  expect((await run()).frame.variables[groupFlow]).toBeCloseTo(flow,7);
  const state = await save(), projectId = state.activeProject;
  await navigate('projects');
  await page.locator(`[data-action="wf-manage"][data-id="${projectId}"]`).click();
  const download = page.waitForEvent('download');
  await page.locator('[data-action="wf-export"]').click();
  const file = join(mkdtempSync(join(tmpdir(),'pf1-project-')), 'project.json');
  await (await download).saveAs(file);
  expect(JSON.parse(readFileSync(file)).project.moduleSnapshots[assembly.id].manifest.composite.children[0].version).toBe(1);
  await page.locator('[data-action="close-dialog"]').last().click();
  await page.locator('[data-action="wf-import"]').click();
  await page.getByLabel('单项目文件').setInputFiles(file);
  await submit();
  await expect(page.locator('#toast')).toContainText('项目已导入');
  await save();
  await page.reload();
  await expect(page.locator('#app-header')).toContainText('模块平台');
  const repeated = await run();
  expect(repeated.request.project.id).not.toBe(projectId);
  expect(repeated.frame.variables[groupFlow]).toBeCloseTo(flow, 7);
  evidence.versions = [v1.version,v2.version,1];
  evidence.composite = {instance:group.id,versions:[1,2,1],childVersion:1,flow:repeated.frame.variables[groupFlow],exportReload:true};
  await captureFhd(page, output + '/composite.png');
  expect((await api('/runs/' + original.id)).request.project.modules.find(m => m.id === v1.id).version).toBe(1);
  await navigate('runs');
  await page.locator('[data-action="refresh-archives"]').click();
  await page.locator(`[data-action="open-archive"][data-id="${original.id}"]`).click();
  await page.locator(`[data-action="record-curves"][data-id="${original.id}"]`).click();
  await expect(page.locator('.chart-variable-list')).toContainText(resistor.id);
  await expect(page.locator('.chart-variable-list')).not.toContainText(group.id);
  await expect(page.locator('#main-flow-chart .chart-line')).toHaveAttribute('d', /L/);
  expect(errors).toEqual([]);
  await captureFhd(page, output + '/history.png');
  writeFileSync(output + '/result.json', JSON.stringify({...evidence,errors},null,2));
  console.log(JSON.stringify({...evidence,errors}));
} catch (error) {
  await captureFhd(page, output + '/failure.png').catch(() => {});
  console.error(JSON.stringify({evidence,errors,dialog:await page.locator('#dialog-error').textContent().catch(() => null)}));
  throw error;
} finally {
  await browser.close();
  await server.close();
}
