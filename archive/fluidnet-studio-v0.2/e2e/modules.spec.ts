import {test as base,expect,type Page,type APIRequestContext} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {readFile} from 'node:fs/promises';

const test=base.extend<{pageErrors:void}>({pageErrors:[async({page},use)=>{const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await use();expect(errors).toEqual([]);},{auto:true}]});

async function openProject(page:Page,request:APIRequestContext,empty=false){
  const examples=await (await request.get('/api/v1/examples')).json();
  const project=examples.find((p:{id:string})=>p.id==='example_parallel');
  project.id='modules_'+randomUUID().replaceAll('-','');project.name='组合验收';project.revision=0;
  if(empty){project.elements=[];project.connections=[];project.groups=[];project.scenarios=[];project.selected_variables=[];}
  const saved=await request.post('/api/v1/projects',{data:project});expect(saved.ok()).toBeTruthy();
  await page.addInitScript(id=>localStorage.setItem('fluidnet:last-project',id),project.id);
  await page.goto('/');await expect(page.locator('.project-switch')).toContainText('组合验收');
  if(!empty)await expect(page.getByTestId('equipment-pump')).toBeVisible();
  return project.id;
}
async function saveProject(page:Page){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/projects')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  const saved=await response;expect(saved.status()).toBe(200);await expect(page.locator('.save-state')).toContainText('已保存');return saved.json();
}
async function groupPump(page:Page){
  await page.getByTestId('equipment-pump').click();
  await page.getByTestId('equipment-trunk').click({modifiers:['Control']});
  await expect(page.locator('.react-flow__node.selected')).toHaveCount(2);
  await page.getByRole('button',{name:'封装选中元件',exact:true}).click();
  await page.getByRole('textbox',{name:'组合名称',exact:true}).fill('测试泵组');
  await page.getByRole('checkbox',{name:'暴露参数 主管 长度',exact:true}).check();
  const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/modules/group'));
  await page.getByRole('button',{name:'封装为组合设备',exact:true}).click();
  const result=await (await response).json();
  expect(result.group_id).toBeTruthy();await expect(page.getByTestId('group-'+result.group_id)).toBeVisible();
  return result.group_id as string;
}
async function solve(page:Page,request:APIRequestContext){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/runs')&&r.request().method()==='POST');
  await page.getByTestId('run-button').click();const rid=(await (await response).json()).run_id;
  await expect(page.locator('.status-bar')).toContainText('已完成');
  return (await (await request.get('/api/v1/runs/'+rid)).json()).frame;
}

test('group shell keeps the solution, moves members, opens internally, copies and restores',async({page,request})=>{
  await openProject(page,request);
  const before=await solve(page,request);const gid=await groupPump(page);
  await expect(page.getByTestId('equipment-pump')).toHaveCount(0);
  const after=await solve(page,request);expect(after.elements).toEqual(before.elements);
  const stored=await saveProject(page);
  const card=page.getByTestId('group-'+gid);const box=await card.boundingBox();expect(box).not.toBeNull();
  await page.mouse.move(box!.x+box!.width/2,box!.y+15);await page.mouse.down();await page.mouse.move(box!.x+box!.width/2+70,box!.y+65,{steps:12});await page.mouse.up();
  const moved=await saveProject(page);
  const oldGroup=stored.groups.find((g:{id:string})=>g.id===gid),newGroup=moved.groups.find((g:{id:string})=>g.id===gid);
  expect(newGroup.position.x).not.toBe(oldGroup.position.x);
  for(const id of oldGroup.element_ids){const a=stored.elements.find((e:{id:string})=>e.id===id),b=moved.elements.find((e:{id:string})=>e.id===id);expect(b.position.x-a.position.x).toBeCloseTo(newGroup.position.x-oldGroup.position.x,6);}
  await card.dblclick();await expect(page.getByTestId('module-breadcrumb')).toContainText('测试泵组');await expect(page.getByTestId('equipment-pump')).toBeVisible();
  await page.getByRole('button',{name:'主画布',exact:true}).click();await expect(card).toBeVisible();
  await card.click();await page.keyboard.press('Control+c');await page.keyboard.press('Control+v');
  await expect(page.locator('.react-flow__node-groupDevice')).toHaveCount(2);
  const cloneId=await page.locator('.react-flow__node-groupDevice.selected').getAttribute('data-id');expect(cloneId).not.toBe('group:'+gid);
  await page.keyboard.press('Delete');await expect(page.locator('.react-flow__node-groupDevice')).toHaveCount(1);
  await page.keyboard.press('Control+z');await expect(page.locator('.react-flow__node-groupDevice')).toHaveCount(2);
  await page.locator(`.react-flow__node[data-id="${cloneId}"]`).click();await page.keyboard.press('Delete');
  await saveProject(page);await page.reload();await expect(card).toBeVisible();
  expect((await solve(page,request)).elements).toEqual(before.elements);
  await page.screenshot({path:'.cache/qa/modules-workbench.png',fullPage:true});
});

test('internal editing reconnects a new member and publishes its exposed parameter',async({page,request})=>{
  const pid=await openProject(page,request);const before=await solve(page,request);const gid=await groupPump(page);
  await page.getByTestId('group-'+gid).dblclick();
  const breadcrumb=page.getByTestId('module-breadcrumb');await expect(breadcrumb).toBeVisible();
  const edge=page.locator('.react-flow__edge');await expect(edge).toHaveCount(1);
  const point=await edge.locator('.react-flow__edge-path').evaluate(element=>{
    const path=element as SVGPathElement,point=path.getPointAtLength(path.getTotalLength()/2);
    const screen=new DOMPoint(point.x,point.y).matrixTransform(path.getScreenCTM()!);return {x:screen.x,y:screen.y};
  });
  await page.mouse.click(point.x,point.y);await expect(edge).toHaveClass(/selected/);
  await page.getByRole('button',{name:'删除选中元件或连接',exact:true}).click();await expect(edge).toHaveCount(0);
  await page.locator('.library-item').filter({has:page.getByText('局部阻力',{exact:true})}).click();
  const node=page.locator('.react-flow__node.selected');await expect(node).toHaveCount(1);
  const resistanceId=(await node.getAttribute('data-id'))!;
  const box=await node.boundingBox(),canvas=await page.locator('.canvas-area').boundingBox();expect(box&&canvas).toBeTruthy();
  await page.mouse.move(box!.x+box!.width/2,box!.y+15);await page.mouse.down();
  await page.mouse.move(canvas!.x+canvas!.width/2,canvas!.y+canvas!.height*.7,{steps:12});await page.mouse.up();
  async function link(a:string,portA:string,b:string,portB:string){
    const p=await page.locator(`.react-flow__node[data-id="${a}"] .react-flow__handle[data-handleid="${portA}"]`).boundingBox();
    const q=await page.locator(`.react-flow__node[data-id="${b}"] .react-flow__handle[data-handleid="${portB}"]`).boundingBox();expect(p&&q).toBeTruthy();
    await page.mouse.move(p!.x+p!.width/2,p!.y+p!.height/2);await page.mouse.down();
    await page.mouse.move(q!.x+q!.width/2,q!.y+q!.height/2,{steps:12});await page.mouse.up();
  }
  await link('pump','out',resistanceId,'in');await link(resistanceId,'out','trunk','in');await expect(edge).toHaveCount(2);
  await breadcrumb.getByRole('button',{name:'配置接口',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'组合设备接口'});
  await expect(dialog.getByRole('checkbox',{name:'暴露端口 循环泵 in',exact:true})).toBeDisabled();
  const exposed=dialog.getByRole('checkbox',{name:'暴露参数 局部阻力 局部阻力系数 K',exact:true});await exposed.check();
  await exposed.locator('xpath=ancestor::tr').getByRole('textbox').fill('过滤器阻力系数');
  await page.getByRole('button',{name:'应用接口配置',exact:true}).click();
  await page.getByRole('button',{name:'主画布',exact:true}).click();
  const coefficient=page.getByRole('spinbutton',{name:'过滤器阻力系数',exact:true});await coefficient.fill('50');await coefficient.press('Tab');
  await page.getByRole('button',{name:'保存到型号库',exact:true}).click();
  await page.getByRole('textbox',{name:'型号名称',exact:true}).fill('内部编辑验收 '+pid.slice(-8));
  const published=page.waitForResponse(r=>r.url().endsWith('/api/v1/templates')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存型号',exact:true}).click();const template=await (await published).json();
  expect(template.body.elements).toHaveLength(3);expect(Object.values(template.interface.parameter_labels)).toContain('过滤器阻力系数');
  await page.getByRole('button',{name:'关闭窗口',exact:true}).click();
  const saved=await saveProject(page);const group=saved.groups.find((g:{id:string})=>g.id===gid);
  expect(group.element_ids).toContain(resistanceId);expect(group.template_id).toBe(template.id);expect(Object.keys(group.exposed_ports)).toHaveLength(2);
  expect(saved.connections).toHaveLength(11);expect(saved.elements.find((e:{id:string})=>e.id===resistanceId).parameters.loss_coefficient).toBe(50);
  const after=await solve(page,request);expect(after.valid).toBeTruthy();expect(after.elements.trunk.mass_flow_kg_s).toBeLessThan(before.elements.trunk.mass_flow_kg_s);
  await page.getByTestId('group-'+gid).dblclick();await expect(page.getByTestId('equipment-'+resistanceId)).toBeVisible();
  await page.screenshot({path:'.cache/qa/module-internal.png',fullPage:true});
});

test('new template versions remain independent until explicitly previewed and applied',async({page,request})=>{
  const pid=await openProject(page,request);const gid=await groupPump(page);
  await page.getByRole('button',{name:'保存到型号库',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'型号编辑与独立验证'})).toBeVisible();
  await page.getByRole('textbox',{name:'型号名称',exact:true}).fill('型号验收 '+pid.slice(-8));
  const create=page.waitForResponse(r=>r.url().endsWith('/api/v1/templates')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存型号',exact:true}).click();const template=await (await create).json();expect(template.revision).toBe(1);
  await page.locator('.module-parameters summary').filter({hasText:'主管'}).click();
  const length=page.getByRole('spinbutton',{name:'长度',exact:true});await length.fill('80');await length.press('Tab');
  const update=page.waitForResponse(r=>r.url().endsWith('/api/v1/templates/'+template.id)&&r.request().method()==='PUT');
  await page.getByRole('button',{name:'保存新版本',exact:true}).click();expect((await (await update).json()).revision).toBe(2);
  await page.getByRole('button',{name:'关闭窗口',exact:true}).click();
  let saved=await saveProject(page);expect(saved.elements.find((e:{id:string})=>e.id==='trunk').parameters.length_m).toBe(20);
  expect(saved.groups.find((g:{id:string})=>g.id===gid).template_revision).toBe(1);
  await page.getByRole('button',{name:'型号管理与验证',exact:true}).click();
  const entry=page.getByTestId('template-'+template.id);await entry.getByRole('button',{name:'应用到选中实例',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'应用型号版本'})).toContainText('80');
  await page.getByRole('button',{name:'应用此版本',exact:true}).click();saved=await saveProject(page);
  expect(saved.elements.find((e:{id:string})=>e.id==='trunk').parameters.length_m).toBe(80);
  expect(saved.groups.find((g:{id:string})=>g.id===gid).template_revision).toBe(2);
  await page.keyboard.press('Control+z');saved=await saveProject(page);expect(saved.elements.find((e:{id:string})=>e.id==='trunk').parameters.length_m).toBe(20);
  await page.getByRole('button',{name:'型号管理与验证',exact:true}).click();await entry.getByRole('button',{name:'编辑与验证',exact:true}).click();
  await page.getByRole('combobox',{name:'型号版本',exact:true}).selectOption('1');
  await expect(page.getByRole('button',{name:'应用此版本到选中实例',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'应用此版本到选中实例',exact:true}).click();await page.getByRole('button',{name:'应用此版本',exact:true}).click();
  await page.getByRole('button',{name:'型号管理与验证',exact:true}).click();await entry.getByRole('button',{name:'归档',exact:true}).click();await expect(entry).toHaveCount(0);
  await page.getByRole('button',{name:'关闭窗口',exact:true}).click();expect((await solve(page,request)).valid).toBeTruthy();
});

test('a module bench steps independently and never adds boundaries to the active project',async({page,request})=>{
  const pid=await openProject(page,request,true);
  await page.getByRole('button',{name:'型号管理与验证',exact:true}).click();
  await page.getByTestId('template-builtin_tank_group').getByRole('button',{name:'编辑与验证',exact:true}).click();
  await page.getByRole('button',{name:'独立验证',exact:true}).click();
  await page.getByRole('combobox',{name:'验证运行模式',exact:true}).selectOption('dynamic');
  await page.getByRole('button',{name:'验证单步',exact:true}).click();await expect(page.getByTestId('bench-status')).toHaveText(/已暂停.*0 s/);
  await page.getByRole('button',{name:'验证单步',exact:true}).click();await expect(page.getByTestId('bench-status')).toHaveText(/已暂停.*0\.1 s/);
  await page.getByRole('button',{name:'停止验证',exact:true}).click();await expect(page.getByTestId('bench-status')).toHaveText(/已停止.*0\.1 s/);
  await expect(page.locator('.bench-metrics')).toContainText('质量残差');
  await page.screenshot({path:'.cache/qa/module-bench.png',fullPage:true});
  await page.getByRole('button',{name:'关闭窗口',exact:true}).click();
  await expect(page.locator('.canvas-empty')).toBeVisible();const stored=await (await request.get('/api/v1/projects/'+pid)).json();expect(stored.elements).toEqual([]);expect(stored.groups).toEqual([]);
});

test('template JSON round-trips while invalid legacy definitions stay visible',async({page,request})=>{
  await page.route('**/api/v1/templates',async route=>{
    if(route.request().method()!=='GET'){await route.continue();return;}
    const response=await route.fetch(),templates=await response.json();
    await route.fulfill({response,json:[...templates,{id:'invalid_legacy',name:'旧型号待修复',kind:'group',body:{},revision:1,updated:1,archived:false,interface:{exposed_ports:{},exposed_parameters:{},port_labels:{},parameter_labels:{}},test_conditions:{},validation_error:'组合模板至少需要一个元件'}]});
  });
  const pid=await openProject(page,request,true);await page.getByRole('button',{name:'型号管理与验证',exact:true}).click();
  const invalid=page.getByTestId('template-invalid_legacy');await expect(invalid.getByRole('alert')).toContainText('组合模板至少需要一个元件');
  await expect(invalid.getByRole('button',{name:'编辑与验证',exact:true})).toBeDisabled();await expect(invalid.getByRole('button',{name:'插入',exact:true})).toBeDisabled();
  const downloaded=page.waitForEvent('download');await page.getByTestId('template-builtin_pump_group').getByRole('button',{name:'导出',exact:true}).click();
  const download=await downloaded,path=await download.path();expect(path).toBeTruthy();
  const definition=JSON.parse(await readFile(path!,'utf8'));expect(definition.kind).toBe('group');expect(definition.revision).toBe(0);
  definition.name='导入验收 '+pid.slice(-8);
  const imported=page.waitForResponse(r=>r.url().endsWith('/api/v1/templates')&&r.request().method()==='POST');
  await page.getByRole('dialog',{name:'型号管理与验证'}).locator('input[type=file]').setInputFiles({name:'pump.fluidnet-template.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(definition))});
  const response=await imported;expect(response.status()).toBe(200);const template=await response.json();expect(template.id).not.toBe('builtin_pump_group');
  const entry=page.getByTestId('template-'+template.id);await expect(entry).toContainText(definition.name);await entry.getByRole('button',{name:'插入',exact:true}).click();
  await expect(page.locator('.react-flow__node-groupDevice')).toHaveCount(1);const saved=await saveProject(page);
  expect(saved.elements).toHaveLength(3);expect(saved.groups[0].template_id).toBe(template.id);expect(Object.keys(saved.groups[0].exposed_ports)).toHaveLength(2);
});
