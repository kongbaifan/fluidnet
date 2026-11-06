import {chromium,expect} from '@playwright/test';
import {mkdtempSync,readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';import {tmpdir} from 'node:os';
import {testServer} from './browser-server.mjs';import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const nav=route=>page.locator(`.rail-link[data-route="${route}"]`).click();
const submit=()=>page.locator('#dialog-form button[type="submit"]').click();
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok(),await r.text()).toBe(true);return r.json();};
async function save(){const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');await page.locator('[data-action="save"]').first().click();expect((await pending).ok()).toBe(true);const state=(await api('/workspace')).data;return state.projects.find(p=>p.id===state.activeProject);}
async function run(){const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');await page.locator('[data-action="run-project"][data-command="run"]').first().click();const r=await pending;expect(r.ok(),await r.text()).toBe(true);const rid=(await r.json()).run_id;let record;await expect.poll(async()=>{record=await api('/runs/'+rid);if(record.status==='failed')throw Error(JSON.stringify(record.frame.diagnostics));return record.status;},{timeout:45000}).toBe('completed');await expect(page.locator('#statusbar')).toContainText('已完成');return record;}
const groups=[
 {id:'open_compressor_pack',name:'双压缩机组',children:['Ref-Suction','Ref-Compressor-1','Ref-Compressor-2','Ref-Discharge']},
 {id:'open_supply_pack',name:'供液泵与集管',children:['Ref-Pump','Ref-Supply']},
 {id:'open_cooler_pack',name:'开放冷风机组',children:['Ref-Cooler-1']},
];
try{
 await page.goto(server.base+'/#modules');await expect(page.locator('[data-action="equipment-library"]')).toBeVisible();
 await page.locator('[data-action="equipment-library"]').click();await page.getByLabel('设备组模板',{exact:true}).selectOption('modular-room');await page.getByLabel('实例前缀',{exact:true}).fill('Ref');
 await page.locator('[name="library-rooms"]').fill('2');await page.locator('[name="library-compressors"]').fill('2');await submit();await expect(page.locator('[data-node="Ref-Compressor-1"]')).toBeVisible();
 const source=await save();
 for(const group of groups){
  await nav('workbench');await page.locator('[data-action="create-composite"]').click();await page.locator('[name="id"]').fill(group.id);await page.locator('[name="name"]').fill(group.name);
  for(const cb of await page.getByRole('dialog').locator('input[type="checkbox"]').all())await cb.uncheck();for(const child of group.children)await page.locator(`[name="node_${child}"]`).check();await submit();
  await expect(page.locator('[data-module-contract]')).toBeVisible();const manifest=JSON.parse(await page.locator('[data-module-contract]').inputValue());expect(manifest.sdk.capabilities).toContain('composite.refrigeration.open.v1');expect(manifest.ports.length).toBeGreaterThan(0);
  await page.locator('[data-action="configure-module-tests"]').click();await expect(page.getByRole('dialog')).toContainText('宿主工况');await expect(page.getByRole('dialog').locator('[data-suite-case]')).toHaveCount(1);await expect(page.getByRole('dialog').locator('[data-condition="inlet_pressure_pa"]')).toHaveCount(0);await submit();
  const publishing=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');await page.locator('[data-action="save-module-version"]').click();const response=await publishing;expect(response.status(),await response.text()).toBe(201);group.release=await response.json();expect(group.release.test_conditions.host_project.name).toBe(source.name);await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
  await page.locator('[data-action="test-module"]').click();await expect(page.locator('[data-host-project]')).toHaveText(source.name);await expect(page.locator('[data-bench-boundary]')).toHaveCount(0);
  const testing=page.waitForResponse(r=>r.url().endsWith('/modules/test')&&r.request().method()==='POST');await page.locator('[data-action="run-bench"][data-command="run"]').click();const tested=await testing;expect(tested.ok(),await tested.text()).toBe(true);expect(tested.request().postDataJSON().host_project.name).toBe(source.name);await expect(page.locator('#bench-results')).toContainText('宿主网络试算完成');
  if(group===groups[2]){
   await captureFhd(page,'artifacts/open-refrigeration-group-host-bench.png');await page.locator('[data-action="edit-module"]').click();
   const republishing=page.waitForResponse(r=>r.url().endsWith('/modules/versions')&&r.request().method()==='POST');await page.locator('[data-action="save-module-version"]').click();const saved=await republishing;expect(saved.status(),await saved.text()).toBe(201);group.release=await saved.json();expect(saved.request().postDataJSON().test.host_project.name).toBe(source.name);await expect(page.locator('[data-action="save-module-version"]')).toBeEnabled();
  }
 }
 // The original project remains connected until all three reusable group versions are published.
 await nav('workbench');await page.locator('[data-action="fit"]').click();const removed=groups.flatMap(g=>g.children).concat('Ref-Cooler-2');
 for(const id of removed){await page.locator(`[data-node="${id}"]`).click();await page.locator(`[data-action="delete-node"][data-id="${id}"]`).click();}
 const replacements=[];
 for(const group of [...groups,groups[2]]){await nav('modules');await page.locator(`[data-module-id="${group.id}"] [data-action="insert-module"]`).click();const owner=await save();replacements.push({group,id:owner.pages[0].nodes.at(-1).id});}
 await page.locator('[data-action="fit"]').click();
 for(const [i,[x,y]] of [[280,120],[400,520],[640,520],[640,660]].entries()){
  const coordinates=await page.locator(`[data-node="${replacements[i].id}"]`).evaluate((node,point)=>{const svg=node.ownerSVGElement,local=svg.createSVGPoint();local.x=point.x;local.y=point.y;const target=local.matrixTransform(svg.getScreenCTM()),origin=node.getScreenCTM();return {from:{x:origin.e,y:origin.f},to:{x:target.x,y:target.y}};},{x,y});
  await page.mouse.move(coordinates.from.x,coordinates.from.y);await page.mouse.down();await page.mouse.move(coordinates.to.x,coordinates.to.y,{steps:12});await page.mouse.up();
 }
 await page.locator('[data-action="fit"]').click();
 const replaceEndpoint=(iid,port)=>{
  const replacement=iid==='Ref-Cooler-2'?replacements[3]:replacements.find(item=>item.group.children.includes(iid));
  if(!replacement)return [iid,port];
  const child=iid==='Ref-Cooler-2'?'Ref-Cooler-1':iid;
  const publicPort=Object.entries(replacement.group.release.module.composite.external_ports).find(([,ref])=>ref.instance_id===child&&ref.port_id===port)?.[0];
  if(!publicPort)return [replacement.id,null];
  return [replacement.id,publicPort];
 };
 let connected=0;
 for(const edge of source.pages[0].edges){
  if(!removed.includes(edge[1])&&!removed.includes(edge[3]))continue;
  const a=replaceEndpoint(edge[1],edge[2]),b=replaceEndpoint(edge[3],edge[4]);if(a[0]===b[0])continue;
  expect(a[1]).toBeTruthy();expect(b[1]).toBeTruthy();
  for(const [iid,port] of [a,b])await page.locator(`[data-port-node="${iid}"][data-port-id="${port}"]`).click();connected++;
 }
 const assembled=await save();expect(assembled.pages[0].nodes.filter(n=>groups.some(g=>g.id===n.moduleId))).toHaveLength(4);expect(assembled.pages[0].edges).toHaveLength(source.pages[0].edges.length-5);
 const initial=await run(),coolerIds=replacements.slice(2).map(item=>item.id);
 const valueKey=coolerIds[0]+'.Ref-Cooler-1.room_cooling_w';expect(initial.frame.variables[valueKey]).toBeGreaterThan(0);
 expect(valueKey).toBeTruthy();const secondKey=valueKey.replace(coolerIds[0]+'.',coolerIds[1]+'.');expect(initial.frame.variables[valueKey]).toBeCloseTo(initial.frame.variables[secondKey],7);
 await page.locator('[data-action="run-project"][data-command="stop"]').first().click();await page.locator(`[data-node="${coolerIds[0]}"]`).dblclick();const panel=page.locator(`[data-float-id="${coolerIds[0]}"]`),parameter=groups[2].release.module.parameters.find(p=>p.id==='Ref-Cooler-1_fan_ratio');expect(parameter).toBeTruthy();
 await panel.locator(`[data-instance-param="${parameter.id}"]`).fill(String((parameter.default*.8)/(parameter.unit?.display_scale||1)+(parameter.unit?.display_offset||0)));await panel.locator('[data-action="apply-instance"]').click();await submit();await panel.locator('[data-action="float-close"]').click();
 const changed=await run();expect(changed.frame.variables[valueKey]).not.toBe(changed.frame.variables[secondKey]);const owner=await save();expect(owner.pages[0].nodes.find(n=>n.id===coolerIds[1]).params[parameter.id]).toBe(parameter.default/(parameter.unit?.display_scale||1)+(parameter.unit?.display_offset||0));await captureFhd(page,'artifacts/open-refrigeration-groups-assembled.png');
 await page.locator('[data-action="run-project"][data-command="stop"]').first().click();await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${owner.id}"]`).click();const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();const file=join(mkdtempSync(join(tmpdir(),'open-refrigeration-')),'project.json');await(await download).saveAs(file);for(const group of groups)expect(JSON.parse(readFileSync(file)).project.moduleSnapshots[group.id].manifest.sdk.capabilities).toContain('composite.refrigeration.open.v1');
 await page.locator('[data-action="close-dialog"]').last().click();await page.locator('[data-action="wf-import"]').click();await page.getByLabel('单项目文件').setInputFiles(file);await submit();await expect(page.locator('#toast')).toContainText('项目已导入');await save();await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');await nav('workbench');const repeated=await run();for(const [key,value] of Object.entries(changed.frame.variables))if(typeof value==='number')expect(repeated.frame.variables[key],key).toBeCloseTo(value,6);
 await page.locator('[data-action="run-project"][data-command="stop"]').first().click();await nav('modules');await page.locator(`[data-module-id="${groups[2].id}"] [data-action="module-example"]`).click();await expect(page.locator('[data-node="D1"]')).toBeVisible();const example=await run();expect(example.request.project.instances.find(n=>n.id==='D1').module_id).toBe(groups[2].id);expect(example.frame.variables['D1.Ref-Cooler-1.room_cooling_w']).toBeGreaterThan(0);
 expect(errors).toEqual([]);mkdirSync('artifacts',{recursive:true});const evidence={groups:groups.map(g=>({id:g.id,version:g.release.module.version,children:g.children,ports:g.release.module.ports.map(p=>p.id),host:g.release.test_conditions.host_project.name})),uiConnections:connected,instances:replacements.map(item=>item.id),independent:true,reloadedEqual:true,hostExample:true,errors};writeFileSync('artifacts/open-refrigeration-groups-ui.json',JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}catch(error){console.error(error);await captureFhd(page,'artifacts/open-refrigeration-groups-failure.png').catch(()=>{});process.exitCode=1;}finally{await browser.close();await server.close();}
