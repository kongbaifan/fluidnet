import {chromium,expect} from '@playwright/test';
import {mkdtempSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-air-'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const errors=[];
let launched,page;
async function api(path,body) {
  const response=await page.request.fetch(launched.base+'/api/v1'+path,{method:body===undefined?'GET':'POST',data:body});
  expect(response.ok(),await response.text()).toBe(true);return response.json();
}
async function runAir() {
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);const id=(await response.json()).run_id;
  let record;
  await expect(async()=>{record=await api('/runs/'+id);if(record.status==='failed')throw Error(JSON.stringify(record.frame));expect(record.status).toBe('completed');}).toPass({timeout:90000,intervals:[200,500,1000]});
  await expect(page.locator('[data-air-provenance]')).toContainText(id.slice(0,12),{timeout:15000});
  return record;
}
try {
  launched=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  const context=await browser.newContext({...FHD_CONTEXT,acceptDownloads:true});
  page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(launched.base+'/#air');
  await expect(page.getByRole('button',{name:'创建风侧示例',exact:true})).toBeEnabled({timeout:15000});
  await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
  await page.getByLabel('风侧示例',{exact:true}).selectOption('air-coil-wet');
  await page.getByRole('button',{name:'创建项目',exact:true}).click();
  await expect(page.getByLabel('风侧当前项目')).toContainText('湿盘管除湿');
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  await expect(page.locator('[data-air-value="Coil.out0.humidity_ratio_kg_kg"]')).not.toHaveText('—',{timeout:30000});
  await expect(page.locator('[data-air-provenance]')).toContainText('当前运行结果');
  await captureFhd(page,'artifacts/air-distribution.png');
  await page.getByRole('button',{name:'湿空气状态图',exact:true}).click();
  await expect(page.getByRole('img',{name:'湿空气状态图：干球温度与含湿量'})).toBeVisible();
  await captureFhd(page,'artifacts/air-psychrometrics.png');
  await page.getByRole('button',{name:'设备与水耗',exact:true}).click();
  await expect(page.locator('.air-device-grid')).toContainText('凝水');
  const downloaded=page.waitForEvent('download');
  await page.getByRole('button',{name:'HTML 报告',exact:true}).click();
  await (await downloaded).saveAs(join(directory,'report.html'));
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('#toast')).toContainText('风侧项目已保存');
  const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
  const owner=saved.projects.find(p=>p.id===saved.activeProject);
  expect(owner.solverOptions.moist_air_options.contract_version).toBe(1);
  expect(owner.airSideView.active_tab).toBe('moisture');
  mkdirSync('artifacts',{recursive:true});
  writeFileSync('artifacts/air-prototype.json',JSON.stringify({format:'fluidnet-studio-prototype',...saved},null,2));
  await page.reload();
  await expect(page.getByRole('button',{name:'运行计算',exact:true})).toBeEnabled({timeout:15000});
  await page.getByRole('button',{name:'运行计算',exact:true}).click();
  await page.getByRole('button',{name:'风量与状态',exact:true}).click();
  await expect(page.locator('[data-air-value="Coil.out0.humidity_ratio_kg_kg"]')).not.toHaveText('—',{timeout:30000});
  // 修改真实盘管参数，过期保护和新运行比较。
  await page.getByRole('button',{name:'编辑拓扑',exact:true}).click();
  await page.locator('[data-node="Coil"]').first().dblclick();
  const bf=page.getByRole('spinbutton',{name:/Coil.*旁通.*草稿/}).first();
  await bf.fill('0.5');await bf.blur();
  await page.locator('[data-action="apply-instance"][data-id="Coil"]').click();
  if(await page.getByRole('dialog').count())await page.getByRole('dialog').locator('button[type="submit"]').click();
  await page.getByRole('button',{name:'关闭设备窗口',exact:true}).click();
  await page.locator('.rail-link[data-route="air"]').click();
  await expect(page.locator('[data-air-provenance]')).toContainText('过期');
  const changed=await runAir();
  expect(changed.frame.variables['Coil.out0.temperature_k']).toBeGreaterThan(290);
  await page.getByRole('button',{name:'运行对比',exact:true}).click();
  await page.getByLabel('对比变量',{exact:true}).selectOption('Coil.out0.temperature_k');
  const choices=page.locator('[data-air-compare-id]');await expect(choices.first()).toBeVisible();
  await choices.nth(0).check();await choices.nth(1).check();
  await page.getByRole('button',{name:'读取对比曲线',exact:true}).click();
  await expect(page.locator('.air-legend span')).toHaveCount(2);
  await captureFhd(page,'artifacts/air-comparison.png');
  // 延迟旧运行响应后立即切换，旧请求不能覆盖新选择。
  const older=(await api('/runs')).runs.find(r=>r.id!==changed.id&&r.name===changed.request.project.name).id;
  await page.route('**/api/v1/runs/'+older,async route=>{const response=await route.fetch();await new Promise(resolve=>setTimeout(resolve,500));await route.fulfill({response}).catch(()=>{});});
  await page.getByLabel('风侧结果来源',{exact:true}).selectOption(older);
  await page.getByLabel('风侧结果来源',{exact:true}).selectOption(changed.id);
  await expect(page.locator('[data-air-provenance]')).toContainText(changed.id.slice(0,12));
  await page.waitForTimeout(700);
  await expect(page.locator('[data-air-provenance]')).toContainText(changed.id.slice(0,12));
  await page.unroute('**/api/v1/runs/'+older);
  // 所有六个示例都必须从 UI 创建、转换为规范项目并运行。
  mkdirSync('artifacts/air-examples',{recursive:true});
  for(const name of ['air-mixing','ahu-wet','ahu-room','air-parallel-wet','cooling-tower-moist']) {
    await page.getByRole('button',{name:'创建风侧示例',exact:true}).click();
    await page.getByLabel('风侧示例',{exact:true}).selectOption(name);
    await page.getByRole('button',{name:'创建项目',exact:true}).click();
    await expect(page.locator('[data-air-project] option:checked')).toHaveText({'air-mixing':'新回风混合','ahu-wet':'空气处理机组','ahu-room':'房间送回风热湿系统','air-parallel-wet':'并联风侧设备','cooling-tower-moist':'冷却塔水耗'}[name]);
    await expect(page.getByRole('button',{name:'运行计算',exact:true})).toBeEnabled();
    if(name==='ahu-room') {
      await page.getByRole('button',{name:'湿空气设置',exact:true}).click();
      await page.getByLabel('动态运行时长 / s',{exact:true}).fill('4');
      await page.getByRole('button',{name:'应用设置',exact:true}).click();
    }
    const record=await runAir();
    writeFileSync('artifacts/air-examples/'+name+'.project.json',JSON.stringify(record.request.project,null,2));
    await page.getByRole('button',{name:'保存项目',exact:true}).click();
    await expect(page.locator('#toast')).toContainText('风侧项目已保存');
    const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')));
    const current=saved.projects.find(p=>p.id===saved.activeProject);
    const exported={format:'fluidnet-studio-prototype',schema:1,activeProject:current.id,projects:[current],modules:Object.values(current.moduleSnapshots)};
    const normalized=await api('/prototype/normalize',exported);
    expect(normalized.solver.moist_air).toBe(name!=='cooling-tower-moist');
    writeFileSync('artifacts/air-examples/'+name+'.prototype.json',JSON.stringify(exported,null,2));
    if(name==='ahu-room')expect(record.frame.variables['Room.state.moisture_added_kg']).toBeCloseTo(.0004,8);
    if(name==='cooling-tower-moist') {
      await page.getByRole('button',{name:'设备与水耗',exact:true}).click();
      await expect(page.locator('.air-device-grid')).toContainText('补水');
      await captureFhd(page,'artifacts/air-tower.png');
    }
  }
  expect(errors).toEqual([]);
  console.log(JSON.stringify({projectId:owner.id,contract:1,errors}));
} catch(error) {
  console.error(error,errors,await page?.locator('#toast').textContent().catch(()=>''),launched?.log());
  process.exitCode=1;
  await captureFhd(page,'artifacts/air-failure.png').catch(()=>{});
} finally {
  await browser.close();await launched?.stop();
}
