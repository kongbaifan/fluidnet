import {chromium,expect} from '@playwright/test';
import {mkdtempSync,readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

// 标准机房基础案例：真实三回路计算、调阀、仪表与报告、保存重载后复算。
const directory=mkdtempSync(join(tmpdir(),'fluidnet-hvac-plant-'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const errors=[];
const multiPage=process.argv.includes('--multi-page');
let partitionedEvidence=null;
let launched,page;
async function api(path,body) {
  const response=await page.request.fetch(launched.base+'/api/v1'+path,
    {method:body===undefined?'GET':'POST',data:body});
  expect(response.ok(),await response.text()).toBe(true);
  return response.json();
}
async function runProject() {
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  const response=await posted;
  expect(response.ok(),await response.text()).toBe(true);
  const id=(await response.json()).run_id;
  let record;
  await expect(async()=>{
    record=await api('/runs/'+id);
    expect(record.status,JSON.stringify(record.frame?.diagnostics)).toBe('completed');
  }).toPass({timeout:90000,intervals:[200,500,1000]});
  await expect(page.locator('[data-air-provenance]')).toContainText(id.slice(0,12),{timeout:15000});
  return record;
}
function verifyPlant(record) {
  const frame=record.frame,v=frame.variables;
  expect(frame.valid,JSON.stringify(frame.diagnostics)).toBe(true);
  expect(record.request.project.circuit_fluids.map(c=>c.id)).toEqual(['chilled-water','condenser-water']);
  expect(record.air_metadata.continuity_basis).toBe('mixed');
  for(const key of ['measurement.branch1-flow','measurement.branch2-flow','measurement.supply-dp','measurement.coil2-power'])
    expect(v[key],key).toBeGreaterThan(0);
  // 用端口质量流量和比焓独立核算，不以同一个设备输出作为参考答案。
  const branchMass=v['Coil.ch1.mass_flow_kg_s']+v['Coil2.ch1.mass_flow_kg_s'];
  const branchResidual=v['Header.common.mass_flow_kg_s']-branchMass;
  expect(Math.abs(branchResidual)).toBeLessThan(1e-7);
  const waterHeat=id=>v[id+'.ch1.mass_flow_kg_s']*(v[id+'.out1.enthalpy_j_kg']-v[id+'.in1.enthalpy_j_kg']);
  const chilledResidual=v['Chiller.cooling_power_w']-waterHeat('Coil')-waterHeat('Coil2')-v['ChilledPump.shaft_power_w'];
  const coolingResidual=v['Tower.heat_rejected_w']-v['Chiller.condenser_heat_w']-v['CoolingPump.shaft_power_w'];
  expect(Math.abs(chilledResidual)).toBeLessThan(.05);
  expect(Math.abs(coolingResidual)).toBeLessThan(.05);
  expect(Math.abs(v['measurement.coil2-power']-waterHeat('Coil2'))).toBeLessThan(.02);
  for(const index of [1,2]) {
    const prefix='Balance'+index;
    const volume=v[prefix+'.main.mass_flow_kg_s']/v[prefix+'.in0.density_kg_m3'];
    expect(v['measurement.branch'+index+'-flow']).toBeCloseTo(volume,10);
  }
  for(const id of ['ChilledRef','CoolingRef'])
    expect(Math.abs(v[id+'.out0.mass_flow_kg_s'])).toBeLessThan(1e-8);
  expect(frame.metrics.reference_heat_w).toBe(0);
  return {run:record.id,snapshot:record.air_metadata.project_snapshot_hash,
    branch1_m3_h:v['measurement.branch1-flow']*3600,branch2_m3_h:v['measurement.branch2-flow']*3600,
    supply_dp_kpa:v['measurement.supply-dp']/1000,coil2_kw:v['measurement.coil2-power']/1000,
    cooling_kw:v['Chiller.cooling_power_w']/1000,tower_kw:v['Tower.heat_rejected_w']/1000,
    chilled_supply_c:v['Chiller.out0.temperature_k']-273.15,
    branch_residual_kg_s:branchResidual,chilled_residual_w:chilledResidual,cooling_residual_w:coolingResidual};
}
async function savedProject() {
  return page.evaluate(()=>{
    const state=JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));
    return state.projects.find(project=>project.id===state.activeProject);
  });
}
async function partitionPlant(){
  const owner=await savedProject(),source=owner.activePage;
  await page.getByRole('button',{name:'编辑拓扑',exact:true}).click();
  async function canvas(name){
    await page.locator('[data-action="new-canvas"]').first().click();
    await page.getByRole('dialog').locator('[name="name"]').fill(name);
    await page.getByRole('dialog').locator('button[type="submit"]').click();
    return page.locator('.canvas-pages [data-action="canvas-tab"].active').getAttribute('data-id');
  }
  const terminal=await canvas('末端'),plant=await canvas('机房');
  for(const [destination,ids] of [[terminal,['Coil','Coil2','Balance1','Balance2','Header','Collector']],
    [plant,['Chiller','ChilledPump','CoolingPump','Tower','ChilledRef','CoolingRef','ChilledJoin','CoolingJoin','Strainer','Reducer','Isolation']]]){
    for(const id of ids){
      await page.locator('[data-action="canvas-tab"][data-id="'+source+'"]').click();
      await page.getByRole('button',{name:'适应画布',exact:true}).click();
      await page.locator('[data-node="'+id+'"]').click();
      await page.locator('[data-action="move-device-page"][data-id="'+id+'"]').click();
      await page.getByRole('dialog').locator('[name="page"]').selectOption(destination);
      await page.getByRole('dialog').locator('button[type="submit"]').click();
    }
  }
  await page.locator('[data-action="page-links"]').click();
  await expect(page.locator('[data-page-link]')).toHaveCount(4);
  await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click();
  await captureFhd(page,'artifacts/hvac-multi-page-topology.png');
  await page.locator('.rail-link[data-route="air"]').click();
}
try {
  launched=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  page=await (await browser.newContext({...FHD_CONTEXT,acceptDownloads:true})).newPage();
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(launched.base+'/#air');
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled({timeout:15000});
  await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
  await page.getByLabel('风侧示例',{exact:true}).selectOption('hvac-basic-plant');
  await page.getByRole('button',{name:'创建项目',exact:true}).click();
  await expect(page.getByLabel('风侧当前项目')).toContainText('双盘管冷水机房');
  // 主流程先用稳态检查水力和热平衡；启停控制另由联锁专项用例覆盖。
  await page.getByRole('button',{name:'湿空气设置',exact:true}).click();
  await page.getByRole('dialog').locator('[name="mode"]').selectOption('steady');
  await page.getByRole('button',{name:'应用设置',exact:true}).click();
  const baseline=await runProject(),baselineEvidence=verifyPlant(baseline);
  expect(baseline.mode).toBe('steady');
  if(multiPage){
    await partitionPlant();const partitioned=await runProject();partitionedEvidence=verifyPlant(partitioned);
    expect(new Set(partitioned.request.project.instances.map(node=>node.page_id)).size).toBe(3);
    for(const meter of baseline.request.project.measurements)
      expect(partitioned.frame.variables['measurement.'+meter.id]).toBeCloseTo(baseline.frame.variables['measurement.'+meter.id],6);
  }
  await expect(page.getByRole('heading',{name:'空气回路',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'液体回路',exact:true})).toBeVisible();
  await expect(page.locator('[data-air-value="Chiller.out0.temperature_k"]')).not.toHaveText('—');
  expect(await page.locator('[data-air-value="Chiller.out0.humidity_ratio_kg_kg"]').count()).toBe(0);
  await captureFhd(page,(multiPage?'artifacts/hvac-multi-page-':'artifacts/hvac-plant-')+'circuits.png');
  await page.locator('.rail-link[data-route="controls"]').click();
  await expect(page.locator('[data-meter-card]')).toHaveCount(4);
  for(const id of ['branch1-flow','branch2-flow','supply-dp','coil2-power'])
    await expect(page.locator('[data-meter-value="'+id+'"]')).not.toHaveText('—',{timeout:15000});
  await expect(page.locator('[data-meter-card="branch1-flow"]')).toContainText('m³/h');
  await expect(page.locator('[data-meter-card="supply-dp"]')).toContainText('kPa');
  await expect(page.locator('[data-meter-card="coil2-power"]')).toContainText('kW');
  await captureFhd(page,(multiPage?'artifacts/hvac-multi-page-':'artifacts/hvac-plant-')+'meters.png');
  await page.locator('[data-action="meter-curve"][data-id="branch1-flow"]').click();
  await expect(page.locator('.chart-variable-list')).toContainText('支路 1 体积流量');
  // This case is steady: a real sampled point is valid; do not fabricate a trend segment.
  await expect(page.locator('#extra-charts svg path.chart-line').first()).toHaveAttribute('d',/M/);
  await captureFhd(page,(multiPage?'artifacts/hvac-multi-page-':'artifacts/hvac-plant-')+'curves.png');
  await page.locator('.rail-link[data-route="air"]').click();
  mkdirSync('artifacts',{recursive:true});
  for(const [name,extension] of [['HTML 报告','html'],['CSV','csv']]) {
    const pending=page.waitForEvent('download');
    await page.getByRole('button',{name,exact:true}).click();
    const target=(multiPage?'artifacts/hvac-multi-page-':'artifacts/hvac-plant-')+'report.'+extension;
    await (await pending).saveAs(target);
    const report=readFileSync(target,'utf8');
    for(const meter of baseline.request.project.measurements) {
      expect(report).toContain('measurement.'+meter.id);
      expect(report).toContain(meter.label);
      expect(report).toContain(meter.unit.display_unit);
    }
  }
  // 经普通设备面板把支路 1 平衡阀由 80% 调到 40%，真实网络应重新分配水量。
  await page.getByRole('button',{name:'编辑拓扑',exact:true}).click();
  const valvePage=(await savedProject()).pages.find(pg=>pg.nodes.some(node=>node.id==='Balance1'));
  await page.locator('[data-action="canvas-tab"][data-id="'+valvePage.id+'"]').click();
  await page.getByRole('button',{name:'适应画布',exact:true}).click();
  await page.locator('[data-node="Balance1"]').first().dblclick();
  const valve=page.getByRole('region',{name:'Balance1 设备参数',exact:true});
  const opening=valve.locator('input[type="number"][data-instance-param="opening_ratio"]');
  await expect(opening).toHaveValue('80');
  await opening.fill('40');
  await opening.blur();
  await valve.locator('[data-action="apply-instance"][data-id="Balance1"]').click();
  if(await page.getByRole('dialog').count())await page.getByRole('dialog').locator('button[type="submit"]').click();
  await valve.getByRole('button',{name:'关闭设备窗口',exact:true}).click();
  await page.locator('.rail-link[data-route="air"]').click();
  await expect(page.locator('[data-air-provenance]')).toContainText('过期');
  const changed=await runProject(),changedEvidence=verifyPlant(changed);
  const changedValve=changed.request.project.instances.find(instance=>instance.id==='Balance1');
  expect(changedValve.parameters.opening_ratio).toBe(.4);
  expect(changedEvidence.branch1_m3_h).toBeLessThan(baselineEvidence.branch1_m3_h);
  expect(changedEvidence.branch2_m3_h).toBeGreaterThan(baselineEvidence.branch2_m3_h);
  expect(changedEvidence.snapshot).not.toBe(baselineEvidence.snapshot);
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('#toast')).toContainText('风侧项目已保存');
  const owner=await savedProject();
  const exported={format:'fluidnet-studio-prototype',schema:1,activeProject:owner.id,
    projects:[owner],modules:Object.values(owner.moduleSnapshots)};
  const normalized=await api('/prototype/normalize',exported);
  expect(normalized.circuit_fluids).toEqual(changed.request.project.circuit_fluids);
  expect(normalized.measurements).toEqual(changed.request.project.measurements);
  expect(normalized.instances.find(instance=>instance.id==='Balance1').parameters.opening_ratio).toBe(.4);
  writeFileSync((multiPage?'artifacts/hvac-multi-page.':'artifacts/hvac-plant.')+'prototype.json',JSON.stringify(exported,null,2)+'\n');
  writeFileSync((multiPage?'artifacts/hvac-multi-page.':'artifacts/hvac-plant.')+'project.json',JSON.stringify(normalized,null,2)+'\n');
  await page.reload();
  await expect(page.getByRole('button',{name:'运行计算',exact:true})).toBeEnabled({timeout:15000});
  const reloaded=await runProject(),reloadedEvidence=verifyPlant(reloaded);
  for(const meter of normalized.measurements)
    expect(reloaded.frame.variables['measurement.'+meter.id]).toBeCloseTo(changed.frame.variables['measurement.'+meter.id],6);
  await page.locator('.rail-link[data-route="controls"]').click();
  await expect(page.locator('[data-meter-card]')).toHaveCount(4);
  await captureFhd(page,(multiPage?'artifacts/hvac-multi-page-':'artifacts/hvac-plant-')+'reloaded.png');
  expect(errors).toEqual([]);
  const evidence={case:'hvac-basic-plant',mode:'steady',baseline:baselineEvidence,
    partitioned:partitionedEvidence,valve40:changedEvidence,reloaded:reloadedEvidence,meters:normalized.measurements.length,curves:true,errors};
  writeFileSync((multiPage?'artifacts/hvac-multi-page-':'artifacts/hvac-plant-')+'validation.json',JSON.stringify(evidence,null,2)+'\n');
  console.log(JSON.stringify(evidence));
} catch(error) {
  console.error(error,errors,launched?.log());
  process.exitCode=1;
  await captureFhd(page,(multiPage?'artifacts/hvac-multi-page-':'artifacts/hvac-plant-')+'failure.png').catch(()=>{});
} finally {
  await browser.close();
  await launched?.stop();
}
