import {chromium,expect} from '@playwright/test';
import {mkdtempSync,writeFileSync,readFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';import {tmpdir} from 'node:os';
import {testServer} from './browser-server.mjs';import {FHD_CONTEXT,captureFhd} from './browser-viewport.mjs';
const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({...FHD_CONTEXT,acceptDownloads:true});
const errors=[],metrics=[];page.on('pageerror',e=>errors.push(e.message));
const nav=r=>page.locator(`.rail-link[data-route="${r}"]`).click(),submit=()=>page.locator('#dialog-form button[type="submit"]').click();
const api=async path=>{const r=await page.request.get(server.base+'/api/v1'+path);expect(r.ok()).toBe(true);return r.json();};
async function save(){const start=performance.now(),pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');await page.locator('[data-action="save"]').first().click();expect((await pending).ok()).toBe(true);await expect(page.locator('[data-save-status]')).not.toContainText('正在保存');return performance.now()-start;}
const active=async()=>{const s=(await api('/workspace')).data;return s.projects.find(p=>p.id===s.activeProject);};
async function group(action,ids,target){await page.locator('[data-action="project-group-tools"]').click();const dialog=page.getByRole('dialog');
 for(const cb of await dialog.locator('input[type="checkbox"]').all())await cb.uncheck();
 for(const id of ids)await page.getByLabel('组选择 '+id,{exact:true}).check();
 await dialog.locator('[name="group-action"]').selectOption(action);if(target)await page.getByLabel('设备组目标画布').selectOption(target);await submit();}
try{
 await page.goto(server.base+'/#projects');await expect(page.locator('#app-header')).toContainText('模块平台 · v');
 const {modules}=await api('/catalog'),definitions=modules.filter(m=>['source','pipe'].includes(m.id)),directory=mkdtempSync(join(tmpdir(),'fluidnet-size-'));
 for(const count of [30,100,300]){
  const p={schema_version:1,id:'size-'+count,name:'规模参考 '+count,fluid:{fluid:'Water',phase_policy:'liquid'},modules:definitions,instances:[],connections:[],solver:{thermal:false,hydraulic_method:'auto'}};
  for(let i=0;i<count;i++)p.instances.push({id:'Part'+i,module_id:i===0||i===count-1?'source':'pipe',name:'设备 '+i,page_id:'page'+Math.floor(i/60),parameters:i===0?{pressure_pa:250000}:i===count-1?{pressure_pa:120000}:{length_m:1,diameter_m:.05},position:{x:90+(i%6)*150,y:90+(Math.floor(i/6)%10)*130}});
  for(let i=1;i<count;i++)p.connections.push({id:'edge'+i,source:{instance_id:'Part'+(i-1),port_id:'out0'},target:{instance_id:'Part'+i,port_id:i===count-1?'out0':'in0'}});
  const solveStart=performance.now(),solved=await page.request.post(server.base+'/api/v1/solve',{data:p,timeout:120000});expect(solved.ok(),await solved.text()).toBe(true);const frame=await solved.json();expect(frame.valid).toBe(true);const solveMs=performance.now()-solveStart;
  const file=join(directory,'size-'+count+'.json');writeFileSync(file,JSON.stringify(p));
  await nav('projects');await page.locator('[data-action="wf-import"]').click();const start=performance.now();await page.getByLabel('单项目文件').setInputFiles(file);await submit();await expect(page.locator('#toast')).toContainText('项目已导入');const imported=performance.now()-start;
  const saveMs=await save();const current=await active();expect(current.pages.flatMap(g=>g.nodes)).toHaveLength(count);
  await nav('workbench');await page.locator('[data-action="project-find"]').click();await page.getByLabel('全项目查找关键词').fill('Part'+(count-1));await page.locator(`[data-action="project-find-node"][data-id="Part${count-1}"]`).click();await expect(page.locator(`[data-float-id="Part${count-1}"]`)).toBeVisible();await page.locator('[data-action="float-close"]').last().click();
  const begin=performance.now();await group('top',['Part1','Part2']);const editMs=performance.now()-begin;await save();
  await nav('projects');await page.locator(`[data-action="wf-manage"][data-id="${current.id}"]`).click();const download=page.waitForEvent('download');await page.locator('[data-action="wf-export"]').click();const out=join(directory,'export-'+count+'.json');await(await download).saveAs(out);expect(JSON.parse(readFileSync(out)).project.pages.flatMap(g=>g.nodes)).toHaveLength(count);await page.locator('[data-action="close-dialog"]').last().click();
  const reloadStart=performance.now();await page.reload();await expect(page.locator('#app-header')).toContainText('模块平台 · v');await expect(page.locator('#toast')).toContainText('已连接');const reloadMs=performance.now()-reloadStart;
  const stored=await page.evaluate(async () =>({rawChars:localStorage.getItem('fluidnet-prototype-engine-v1').length,format:JSON.parse(localStorage.getItem('fluidnet-prototype-engine-v1')).format||'legacy',heap:performance.memory?.usedJSHeapSize||null}));
  const workspace=(await api('/workspace')).data;const projectBytes=JSON.stringify(await active()).length;const sections=Object.fromEntries(['modules','projects','records','models'].map(k=>[k,JSON.stringify(workspace[k]||[]).length]));metrics.push({count,solveMs,sections,workspaceChars:JSON.stringify(workspace).length,importMs:imported,saveMs,editMs,reloadMs,projectChars:projectBytes,...stored});
 }
 await nav('workbench');await page.locator('[data-action="canvas-tab"][data-id="page0"]').click();
 // First page is full: copy onto a new page, internal connection only, and undo/redo.
 await page.locator('[data-action="new-canvas"]').first().click();await page.locator('[name="name"]').fill('设备组副本');await submit();await save();const target=(await active()).activePage;
 await group('copy',['Part1','Part2'],target);await expect(page.getByRole('dialog')).toContainText('1 条内部连线');await submit();await save();let current=await active(),copied=current.pages.find(g=>g.id===target).nodes;expect(copied).toHaveLength(2);expect(current.pages.find(g=>g.id===target).edges).toHaveLength(1);
 await page.locator('[data-action="undo"]').click();await save();expect((await active()).pages.find(g=>g.id===target).nodes).toHaveLength(0);await page.locator('[data-action="redo"]').click();await save();expect((await active()).pages.find(g=>g.id===target).nodes).toHaveLength(2);
 await page.locator(`.net-node[data-node="${copied[0].id}"]`).click({modifiers:['Shift']});await page.locator('[data-action="project-group-tools"]').click();await expect(page.getByLabel('组选择 '+copied[0].id,{exact:true})).not.toBeChecked();await page.locator('[data-action="close-dialog"]').last().click();
 // A true Shift-drag rectangle selects both copied devices from their visible bounds.
 const bounds=await page.locator('#network [data-node]').evaluateAll(xs=>xs.map(x=>{const b=x.getBoundingClientRect();return {x:b.x,y:b.y,right:b.right,bottom:b.bottom};}));
 const left=Math.min(...bounds.map(b=>b.x))-12,top=Math.min(...bounds.map(b=>b.y))-12,right=Math.max(...bounds.map(b=>b.right))+12,bottom=Math.max(...bounds.map(b=>b.bottom))+12;
 await page.keyboard.down('Shift');await page.mouse.move(left,top);await page.mouse.down();await page.mouse.move(right,bottom,{steps:8});await page.mouse.up();await page.keyboard.up('Shift');
 await page.locator('[data-action="project-group-tools"]').click();for(const n of copied)await expect(page.getByLabel('组选择 '+n.id,{exact:true})).toBeChecked();await page.locator('[data-action="close-dialog"]').last().click();
 await group('move',copied.map(n=>n.id),'page0');await save();expect((await active()).pages.find(g=>g.id===target).nodes).toHaveLength(0);
 await page.locator('[data-action="undo"]').click();await save();expect((await active()).pages.find(g=>g.id===target).nodes.map(n=>n.id)).toEqual(copied.map(n=>n.id));
 await captureFhd(page,'artifacts/project-group-editing.png');
 // Exercise actual browser quota and lossless recovery independently of live application state.
 const capacity=await page.evaluate(async () =>{const source=JSON.parse(JSON.stringify({payload:'z'.repeat(800000),values:[1,2,3]})),draft={schema:1,modules:Array.from({length:12},()=>source),draft:{opening:37}},key='capacity-probe';const old='keep-until-write';localStorage.setItem(key,old);const result=(await import('/draft-store.js')).FluidNetDraftStore.write(localStorage,key,JSON.stringify(draft));const restored=(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem(key));restored.modules[0].values[0]=99;const independent=restored.modules[1].values[0]===1;localStorage.removeItem(key);return {...result,independent,opening:restored.draft.opening};});
 expect(capacity.packed).toBe(true);expect(capacity.independent).toBe(true);expect(capacity.opening).toBe(37);
 const backups=await page.evaluate(async () =>{
  const {FluidNetDraftStore}=await import('/draft-store.js');
  return Object.keys(localStorage).filter(k=>k.includes('before-workspace')).map(k=>({key:k,format:JSON.parse(localStorage.getItem(k)).format||'legacy',hasProjects:Array.isArray(FluidNetDraftStore.parse(localStorage.getItem(k)).projects)}));
 });
 expect(backups.every(b=>b.hasProjects)).toBe(true);
 // A dirty draft must recover from packed local storage even when the server cannot save or load it.
 await page.locator(`.net-node[data-node="${copied[0].id}"]`).dblclick();
 await page.locator(`[data-float-id="${copied[0].id}"] input[data-instance-param="length_m"]`).fill('2');
 await page.route('**/api/v1/workspace',route=>route.fulfill({status:507,contentType:'application/json',body:JSON.stringify({detail:'injected workspace unavailable'})}));
 const refused=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/workspace'&&r.request().method()==='POST');await page.locator('[data-action="save"]').first().click();expect((await refused).status()).toBe(507);await expect(page.locator('[data-save-status]')).toContainText('保存失败');
 await page.reload();await expect(page.locator('.net-node[data-node="'+copied[0].id+'"]')).toBeVisible();await page.locator('.net-node[data-node="'+copied[0].id+'"]').dblclick();
 await expect(page.locator(`[data-float-id="${copied[0].id}"] input[data-instance-param="length_m"]`)).toHaveValue('2');
 const recovered=await page.evaluate(async id =>{const s=(await import('/draft-store.js')).FluidNetDraftStore.parse(localStorage.getItem('fluidnet-prototype-engine-v1')),p=s.projects.find(p=>p.id===s.activeProject);return p.pages.flatMap(g=>g.nodes).find(n=>n.id===id);},copied[0].id);
 expect(recovered.params.length_m).toBe(1);expect(recovered.draft.length_m).toBe(2);await page.unroute('**/api/v1/workspace');
 expect(errors).toEqual([]);mkdirSync('artifacts',{recursive:true});writeFileSync('artifacts/project-capacity-metrics.json',JSON.stringify({date:'2026-11-06',viewport:FHD_CONTEXT,metrics,capacity,offlineDirtyRecovery:true,errors},null,2));console.log(JSON.stringify({metrics,capacity,offlineDirtyRecovery:true,errors}));
}catch(e){console.error(e);await captureFhd(page,'artifacts/project-editing-failure.png').catch(()=>{});process.exitCode=1;}finally{await browser.close();await server.close();}
