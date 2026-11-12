import {chromium,expect} from '@playwright/test';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {launchEngine} from './browser-server.mjs';
import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';

const directory=mkdtempSync(join(tmpdir(),'fluidnet-cross-page-'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const errors=[],runPosts=[];let launched,page;
const state=()=>page.evaluate(async()=>{const {FluidNetDraftStore}=await import('/draft-store.js');return FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1'));});
const owner=s=>s.projects.find(p=>p.id===s.activeProject);
const navigate=route=>page.locator('.rail-link[data-route="'+route+'"]').click();
const submit=()=>page.getByRole('dialog').locator('button[type="submit"]').click();
async function api(path){const response=await page.request.get(launched.base+'/api/v1'+path);expect(response.ok(),await response.text()).toBe(true);return response.json();}
async function mode(value){
  await navigate('settings');await page.locator('[data-action="settings-tab"][data-value="solver"]').click();
  await page.locator('[data-solver-field="mode"]').selectOption(value);
  if(value==='dynamic'){
    await page.locator('[data-solver-field="duration"]').fill('10');await page.locator('[data-solver-field="duration"]').blur();
    await page.locator('[data-solver-field="dt"]').fill('1');await page.locator('[data-solver-field="dt"]').blur();
  }else{
    await expect(page.locator('[data-solver-field="duration"]')).toBeDisabled();
  }
}
async function run(command='run'){
  await navigate('workbench');
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');
  await page.locator('[data-action="run-project"][data-command="'+command+'"]').first().click();
  const response=await posted;expect(response.ok(),await response.text()).toBe(true);const id=(await response.json()).run_id;
  let record;await expect.poll(async()=>{record=await api('/runs/'+id);return record.status;},{timeout:45000}).toBe(command==='step'?'paused':'completed');
  await expect(page.locator('#statusbar')).toContainText(command==='step'?'已暂停':'已完成');
  await save();
  return record;
}
async function addCanvas(name){
  await page.locator('[data-action="new-canvas"]').first().click();await page.getByRole('dialog').locator('[name="name"]').fill(name);await submit();
  return (await save()).activePage;
}
async function move(id,source,target){
  await page.locator('[data-action="canvas-tab"][data-id="'+source+'"]').click();
  await page.getByRole('button',{name:'适应画布',exact:true}).click();
  await page.locator('.net-node[data-node="'+id+'"]').click();
  await page.locator('[data-action="move-device-page"][data-id="'+id+'"]').click();
  await page.getByRole('dialog').locator('[name="page"]').selectOption(target);await submit();
}
async function save(){
  const posted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');
  await page.locator('[data-action="save"]').first().click();expect((await posted).ok()).toBe(true);
  await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');return owner(await state());
}
async function exportProject(id,action,name){
  await navigate('projects');await page.locator('[data-action="wf-manage"][data-id="'+id+'"]').click();
  const pending=page.waitForEvent('download');await page.locator('[data-action="'+action+'"]').click();
  const path=join(directory,name);await(await pending).saveAs(path);await page.locator('[data-action="close-dialog"]').last().click();return path;
}
async function importProject(path){
  await navigate('projects');await page.locator('[data-action="wf-import"]').click();
  await page.getByRole('dialog').locator('input[type="file"]').setInputFiles(path);
  await page.getByRole('dialog').locator('[name="mode"]').selectOption('replace');await submit();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('#toast')).toContainText('项目已导入');
  await mode('steady');
}
try{
  launched=await launchEngine({args:['--data-dir',join(directory,'data')],env:{FLUIDNET_MODULE_STORE:join(directory,'modules')}});
  page=await(await browser.newContext({...FHD_CONTEXT,acceptDownloads:true})).newPage();
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(new URL(request.url()).pathname==='/api/v1/runs'&&request.method()==='POST')runPosts.push(request.url());});
  await page.goto(launched.base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  await page.locator('[data-action="new-project"]').first().click();
  await page.getByRole('dialog').locator('[name="name"]').fill('跨页水网络');
  await page.getByRole('dialog').locator('[name="template"]').selectOption('water');await submit();
  await mode('steady');const baseline=await run(),initial=owner(await state()),main=initial.activePage;
  const terminal1=await addCanvas('末端 1'),terminal2=await addCanvas('末端 2');
  for(const id of ['V1','L1'])await move(id,main,terminal1);
  for(const id of ['V2','L2'])await move(id,main,terminal2);
  const split=await run();expect(split.frame.valid).toBe(true);
  for(const [key,value] of Object.entries(baseline.frame.variables))if(typeof value==='number')expect(split.frame.variables[key],key).toBeCloseTo(value,6);
  expect(new Set(split.request.project.instances.map(node=>node.page_id)).size).toBe(3);
  await page.locator('[data-action="canvas-tab"][data-id="'+main+'"]').click();
  await expect(page.locator('[aria-label="当前画布跨页连接"] button')).toHaveCount(4);
  const cross=owner(await state()).pages.flatMap(pg=>pg.edges).find(edge=>edge[3]==='V1'&&edge[4]==='in0');
  expect(cross).toBeTruthy();
  await page.locator('[data-action="jump-page-link"][data-id="'+cross[0]+'"]').click();
  await expect(page.getByRole('region',{name:'V1 设备参数',exact:true})).toBeVisible();
  await save();
  expect(owner(await state()).activePage).toBe(terminal1);
  const floater=page.getByRole('region',{name:'V1 设备参数',exact:true});
  await floater.locator('[data-action="float-tab"][data-value="connections"]').click();
  await expect(floater).toContainText(initial.pages[0].name);
  await floater.locator('[data-action="delete-edge"][data-id="'+cross[0]+'"]').click();
  await expect(page.locator('[aria-label="当前画布跨页连接"] button')).toHaveCount(1);
  await floater.locator('[data-action="connect-device-port"][data-port="in0"]').click();
  await page.getByRole('dialog').locator('[name="targetPage"]').selectOption(main);
  await page.getByRole('dialog').locator('[name="target"]').selectOption(cross[1]+':'+cross[2]);await submit();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('[aria-label="当前画布跨页连接"] button')).toHaveCount(2);
  const currentEdge=owner(await state()).pages.flatMap(pg=>pg.edges).find(edge=>edge[1]==='V1'&&edge[2]==='in0');
  await floater.locator('[data-action="edit-page-link"][data-id="'+currentEdge[0]+'"]').click();
  await expect(page.getByRole('dialog')).toContainText('修改跨页连接');await submit();
  await floater.locator('[data-action="delete-edge"][data-id="'+currentEdge[0]+'"]').click();
  await floater.getByRole('button',{name:'关闭设备窗口',exact:true}).click();
  // The ordinary two-click port workflow also keeps its source while switching canvases.
  await page.locator('[data-port-node="V1"][data-port-id="in0"]').click();
  await page.locator('[data-action="canvas-tab"][data-id="'+main+'"]').click();
  await page.locator('[data-port-node="'+cross[1]+'"][data-port-id="'+cross[2]+'"]').click();
  await page.locator('[data-action="canvas-tab"][data-id="'+terminal1+'"]').click();
  await expect(page.locator('[aria-label="当前画布跨页连接"] button')).toHaveCount(2);
  await page.locator('[data-action="page-links"]').click();await expect(page.locator('[data-page-link]')).toHaveCount(4);
  await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click();
  mkdirSync('artifacts',{recursive:true});await captureFhd(page,'artifacts/cross-page-terminals.png');
  const restoredLinks=await run();expect(restoredLinks.frame.variables['V1.mass_flow_kg_s']).toBeCloseTo(baseline.frame.variables['V1.mass_flow_kg_s'],6);
  // Deleting a cross-page endpoint clears both canvases; undo restores the complete network.
  await page.locator('[data-action="canvas-tab"][data-id="'+terminal1+'"]').click();
  await page.locator('.net-node[data-node="V1"]').click();
  await page.locator('[data-action="delete-node"][data-id="V1"]').first().click();
  await expect(page.locator('.net-node[data-node="V1"]')).toHaveCount(0);
  await save();const deleted=(await api('/workspace')).data.projects.find(p=>p.id===initial.id);
  expect(deleted.pages.flatMap(pg=>pg.nodes).some(n=>n.id==='V1')).toBe(false);
  expect(deleted.pages.flatMap(pg=>pg.edges).some(e=>e[1]==='V1'||e[3]==='V1')).toBe(false);
  await page.locator('[data-action="canvas-tab"][data-id="'+main+'"]').click();
  await expect(page.locator('[aria-label="当前画布跨页连接"] button')).toHaveCount(3);
  await page.locator('[data-action="undo"]').first().click();
  await page.locator('[data-action="canvas-tab"][data-id="'+main+'"]').click();
  await expect(page.locator('[aria-label="当前画布跨页连接"] button')).toHaveCount(4);
  const afterUndo=await run();expect(afterUndo.frame.variables['V1.mass_flow_kg_s']).toBeCloseTo(baseline.frame.variables['V1.mass_flow_kg_s'],6);
  await mode('dynamic');const paused=await run('step'),posts=runPosts.length;
  for(const id of [main,terminal1,terminal2])await page.locator('[data-action="canvas-tab"][data-id="'+id+'"]').click();
  expect(owner(await state()).run.runId).toBe(paused.id);expect(runPosts.length).toBe(posts);expect((await api('/runs/'+paused.id)).status).toBe('paused');
  await page.locator('[data-action="run-project"][data-command="stop"]').first().click();
  await expect(page.locator('#statusbar')).toContainText('已停止');await save();
  expect(!!owner(await state()).run.live).toBe(false);
  await mode('steady');await navigate('workbench');const saved=await save();
  await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');
  const reloaded=await run();expect(reloaded.frame.variables['V1.mass_flow_kg_s']).toBeCloseTo(baseline.frame.variables['V1.mass_flow_kg_s'],6);
  const single=await exportProject(saved.id,'wf-export','single.json'),canonical=await exportProject(saved.id,'wf-export-canonical','canonical.json');
  for(const file of [single,canonical]){
    await importProject(file);const backup=await page.evaluate(()=>JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1-before-project')));
    expect(backup.format).toBe('fluidnet-project');expect(backup.project.id).toBe(saved.id);expect(backup.project.pages).toHaveLength(3);
    const record=await run();expect(record.frame.variables['V1.mass_flow_kg_s']).toBeCloseTo(baseline.frame.variables['V1.mass_flow_kg_s'],6);
  }
  await navigate('projects');await page.locator('[data-action="duplicate-project"][data-id="'+saved.id+'"]').click();
  await save();const copy=(await api('/workspace')).data.projects.find(p=>p.name==='跨页水网络 副本');expect(copy.pages).toHaveLength(3);
  await page.locator('[data-action="open-project"][data-id="'+copy.id+'"]').last().click();const copied=await run();
  expect(copied.request.project.id).toBe(copy.id);
  expect(copied.frame.variables['V1.mass_flow_kg_s']).toBeCloseTo(baseline.frame.variables['V1.mass_flow_kg_s'],6);
  await page.locator('[data-action="canvas-tab"][data-id="'+terminal1+'"]').click();await page.getByRole('button',{name:'适应画布',exact:true}).click();
  await page.locator('.net-node[data-node="V1"]').dblclick();
  const valve=page.getByRole('region',{name:'V1 设备参数',exact:true});
  await valve.locator('[data-instance-param="opening_ratio"][type="number"]').fill('30');
  await valve.locator('[data-instance-param="opening_ratio"][type="number"]').blur();
  await valve.locator('[data-action="apply-instance"]').click();await submit();
  await valve.getByRole('button',{name:'关闭设备窗口',exact:true}).click();
  const changed=await run();expect(changed.frame.variables['V1.mass_flow_kg_s']).toBeLessThan(baseline.frame.variables['V1.mass_flow_kg_s']);
  const original=(await api('/projects/'+saved.id)).document.project;
  const originalParameters=original.pages.flatMap(pg=>pg.nodes).find(n=>n.id==='V1').params;
  expect(originalParameters.opening_ratio??originalParameters.opening).toBe(initial.pages[0].nodes.find(n=>n.id==='V1').params.opening);
  await page.locator('[data-action="canvas-tab"][data-id="'+main+'"]').click();await captureFhd(page,'artifacts/cross-page-plant.png');
  expect(errors).toEqual([]);
  const evidence={pages:3,links:4,baseline:baseline.id,split:split.id,paused:paused.id,reloaded:reloaded.id,
    valveFlow:baseline.frame.variables['V1.mass_flow_kg_s'],changedFlow:changed.frame.variables['V1.mass_flow_kg_s'],formats:['fluidnet-project','Project'],deleteUndo:true,errors};
  writeFileSync('artifacts/cross-page-validation.json',JSON.stringify(evidence,null,2)+'\n');
  writeFileSync('artifacts/cross-page.project.json',readFileSync(canonical));console.log(JSON.stringify(evidence));
}catch(error){console.error(error,errors,launched?.log());await captureFhd(page,'artifacts/cross-page-failure.png').catch(()=>{});process.exitCode=1;}
finally{await browser.close();await launched?.stop();}
