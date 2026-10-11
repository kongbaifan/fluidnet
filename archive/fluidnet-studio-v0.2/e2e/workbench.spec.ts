import { test as base, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const test=base.extend<{pageErrors:void}>({
  pageErrors:[async({page},use)=>{
    const errors:string[]=[];
    page.on('pageerror',error=>errors.push(error.message));
    await use();
    expect(errors,'The workbench must not raise browser errors').toEqual([]);
  },{auto:true}],
});

test('solve a network, change a valve, inspect reserved media and export', async ({page,request})=>{
  await page.goto('/');
  await expect(page.getByTestId('equipment-pump')).toBeVisible();
  const create=page.waitForResponse(r=>r.url().endsWith('/api/v1/runs')&&r.request().method()==='POST');
  await page.getByTestId('run-button').click();
  const rid=(await (await create).json()).run_id;
  await expect(page.locator('.status-bar')).toContainText('已完成');
  const initial=await (await request.get(`/api/v1/runs/${rid}`)).json();
  expect(initial.frame.elements.trunk.mass_flow_kg_s).toBeGreaterThan(0);
  await page.getByTestId('equipment-valve_b').click();
  const opening=page.getByRole('spinbutton',{name:'开度',exact:true});
  await opening.fill('0.2');await opening.press('Tab');
  await expect(page.locator('.stale-banner')).toBeVisible();
  const create2=page.waitForResponse(r=>r.url().endsWith('/api/v1/runs')&&r.request().method()==='POST');
  await page.getByTestId('run-button').click();
  const rid2=(await (await create2).json()).run_id;
  await expect(page.locator('.status-bar')).toContainText('已完成');
  const updated=await (await request.get(`/api/v1/runs/${rid2}`)).json();
  expect(updated.frame.elements.pipe_b.mass_flow_kg_s).toBeLessThan(initial.frame.elements.pipe_b.mass_flow_kg_s);
  await expect(page.getByTestId('trend-chart')).toBeVisible();
  mkdirSync('.cache/qa',{recursive:true});
  await page.screenshot({path:'.cache/qa/workbench.png',fullPage:true});
  await page.locator('.medium-chip').click();
  await expect(page.getByRole('dialog',{name:'介质与流体回路'})).toBeVisible();
  await expect(page.locator('.medium-card')).toHaveCount(6);
  await expect(page.locator('.medium-card.enabled')).toHaveCount(1);
  await page.screenshot({path:'.cache/qa/media.png',fullPage:true});
  await page.getByRole('button',{name:'关闭窗口'}).click();
  const report=await request.get(`/api/v1/runs/${rid2}/results?format=html`);
  expect(report.status()).toBe(200);expect(await report.text()).toContain('计算报告');
});

test('dynamic single-step only advances the simulation clock once',async({page})=>{
  await page.goto('/');await expect(page.getByTestId('equipment-pump')).toBeVisible();
  await page.getByRole('button',{name:'动态运行',exact:true}).click();
  await page.getByRole('button',{name:'单步推进'}).click();
  await expect(page.locator('.status-bar')).toContainText('已暂停');
  await expect(page.locator('.time-value')).toHaveText(/0\s*s/);
  await page.getByRole('button',{name:'单步推进'}).click();
  await expect(page.locator('.time-value')).toHaveText(/0\.1\s*s/);
  await page.waitForTimeout(300);
  await expect(page.locator('.time-value')).toHaveText(/0\.1\s*s/);
  await page.getByRole('button',{name:'停止运行',exact:true}).click();
  await expect(page.locator('.status-bar')).toContainText('已停止');
});

test('a new project can add, connect, solve, undo and save real elements',async({page})=>{
  await page.goto('/');await expect(page.locator('.project-switch')).toBeVisible();
  await page.locator('.project-switch').click();
  await page.getByRole('button',{name:'新建项目',exact:true}).click();
  await expect(page.locator('.canvas-empty')).toBeVisible();
  const canvas=await page.locator('.canvas-area').boundingBox();expect(canvas).not.toBeNull();
  async function add(name:string,x:number,y:number){
    await page.locator('.library-item').filter({has:page.getByText(name,{exact:true})}).click();
    const node=page.locator('.react-flow__node.selected');
    await expect(node).toHaveCount(1);
    await expect(page.getByRole('textbox',{name:'元件名称',exact:true})).toHaveValue(name);
    const id=await node.getAttribute('data-id');
    const box=await node.boundingBox();if(!box||!canvas)throw Error('Missing node bounds');
    await page.mouse.move(box.x+box.width/2,box.y+20);await page.mouse.down();
    await page.mouse.move(canvas.x+x,canvas.y+y,{steps:12});await page.mouse.up();
    return id!;
  }
  const source=await add('定压水源',120,180);
  const pipe=await add('管道',390,180);
  const sink=await add('定压水源',680,180);
  await page.getByRole('spinbutton',{name:'绝对压力',exact:true}).fill('0');
  await page.getByRole('spinbutton',{name:'绝对压力',exact:true}).press('Tab');
  async function link(a:string,portA:string,b:string,portB:string){
    const first=page.locator(`.react-flow__node[data-id="${a}"] .react-flow__handle[data-handleid="${portA}"]`);
    const second=page.locator(`.react-flow__node[data-id="${b}"] .react-flow__handle[data-handleid="${portB}"]`);
    const p=await first.boundingBox(),q=await second.boundingBox();if(!p||!q)throw Error('Missing ports');
    await page.mouse.move(p.x+p.width/2,p.y+p.height/2);await page.mouse.down();
    await page.mouse.move(q.x+q.width/2,q.y+q.height/2,{steps:15});await page.mouse.up();
  }
  await link(source,'p2',pipe,'in');await link(pipe,'out',sink,'p1');
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
  await page.getByTestId('run-button').click();await expect(page.locator('.status-bar')).toContainText('已完成');
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('.save-state')).toContainText('已保存');
  await page.getByTestId('equipment-'+pipe).click();
  await page.keyboard.press('Delete');await expect(page.getByTestId('equipment-'+pipe)).toHaveCount(0);
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('.save-state')).toContainText('已保存');
  await page.keyboard.press('Control+z');await expect(page.getByTestId('equipment-'+pipe)).toBeVisible();
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
  const save=page.waitForResponse(r=>r.url().endsWith('/api/v1/projects')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  expect((await save).status()).toBe(200);
  await expect(page.locator('.save-state')).toContainText('已保存');
  await page.keyboard.press('Control+y');
  await expect(page.getByTestId('equipment-'+pipe)).toHaveCount(0);
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('.save-state')).toContainText('已保存');
  await page.keyboard.press('Control+z');
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('.save-state')).toContainText('已保存');
  await page.reload();
  await expect(page.getByTestId('equipment-'+pipe)).toBeVisible();
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
  await page.getByTestId('run-button').click();
  await expect(page.locator('.status-bar')).toContainText('已完成');
});

test('connections can be selected, deleted and restored without deleting equipment',async({page})=>{
  await page.goto('/');
  await expect(page.getByTestId('equipment-pump')).toBeVisible();
  const edge=page.locator('.react-flow__edge[data-id="source_p2__pump_in"]');
  const path=edge.locator('.react-flow__edge-path');
  await expect(path).toBeAttached();
  const point=await path.evaluate(element=>{
    const path=element as SVGPathElement;
    const point=path.getPointAtLength(path.getTotalLength()/2);
    const screen=new DOMPoint(point.x,point.y).matrixTransform(path.getScreenCTM()!);
    return {x:screen.x,y:screen.y};
  });
  await page.mouse.click(point.x,point.y);
  await expect(edge).toHaveClass(/selected/);
  await page.getByRole('button',{name:'删除选中元件或连接',exact:true}).click();
  await expect(edge).toHaveCount(0);
  await expect(page.getByTestId('equipment-source')).toBeVisible();
  await expect(page.getByTestId('equipment-pump')).toBeVisible();
  await page.keyboard.press('Control+z');
  // A horizontal SVG path has a zero-height box even when its stroke is drawn.
  await expect(path).toHaveAttribute('d',/^M/);
  expect(await path.evaluate(element=>(element as SVGPathElement).getTotalLength())).toBeGreaterThan(0);
  await expect(page.locator('.react-flow__edge')).toHaveCount(10);
});

test('edits made while a project is saving remain visible and can be saved',async({page})=>{
  await page.goto('/');
  await expect(page.getByTestId('equipment-pump')).toBeVisible();
  await page.locator('.project-switch').click();
  await page.getByRole('button',{name:'当前项目另存为副本',exact:true}).click();
  await page.getByTestId('equipment-pump').click();
  let releaseSave!:()=>void;
  let savedOnServer!:()=>void;
  const gate=new Promise<void>(resolve=>{releaseSave=resolve;});
  const saved=new Promise<void>(resolve=>{savedOnServer=resolve;});
  let intercepted=false;
  await page.route('**/api/v1/projects',async route=>{
    if(route.request().method()!=='POST'||intercepted){await route.continue();return;}
    intercepted=true;
    const response=await route.fetch();
    savedOnServer();
    await gate;
    await route.fulfill({response});
  });
  const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/projects')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await saved;
  const name=page.getByRole('textbox',{name:'元件名称',exact:true});
  try {await name.fill('保存期间修改的循环泵');} finally {releaseSave();}
  await response;
  await expect(name).toHaveValue('保存期间修改的循环泵');
  await expect(page.locator('.save-state')).toContainText('未保存');
  await page.getByRole('button',{name:'保存项目',exact:true}).click();
  await expect(page.locator('.save-state')).toContainText('已保存');
  await page.reload();
  await page.getByTestId('equipment-pump').click();
  await expect(name).toHaveValue('保存期间修改的循环泵');
});
