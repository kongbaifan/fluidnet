import {chromium,expect} from '@playwright/test';
import {testServer} from './browser-server.mjs';

const server=await testServer(),browser=await chromium.launch({channel:'msedge',headless:true});
try{
  const page=await browser.newPage(),errors=[],scripts=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{if(new URL(response.url()).pathname.endsWith('.js'))scripts.push(response);});
  await page.goto(server.base+'/index.html#workbench');
  await expect(page.locator('#network')).toBeVisible();
  await expect.poll(()=>scripts.length).toBeGreaterThan(40);
  expect(await page.evaluate(()=>Object.keys(window).filter(key=>/^FluidNet/.test(key)))).toEqual([]);
  expect(await page.evaluate(async()=>typeof (await import('/engine-client.js')).createEngineClient)).toBe('function');
  const paths=scripts.map(response=>new URL(response.url()).pathname);
  expect(new Set(paths).size).toBe(paths.length);
  for(const response of scripts){expect(response.ok()).toBe(true);expect(response.headers()['content-type']).toMatch(/javascript/);}
  expect(errors).toEqual([]);
  // A failed dependency must produce a visible failure, not an apparently ready shell.
  const failed=await browser.newPage();
  await failed.route('**/canvas-symbols.js',route=>route.fulfill({status:503,contentType:'text/plain',body:'controlled failure'}));
  await failed.goto(server.base+'/');
  await expect(failed.locator('#page [role="alert"]')).toContainText('工作台加载失败');
  await expect(failed.locator('#network')).toHaveCount(0);
  console.log(JSON.stringify({nativeModules:paths.length,duplicateFetches:0,fluidNetGlobals:0,failureVisible:true,errors}));
}finally{await browser.close();await server.close();}
