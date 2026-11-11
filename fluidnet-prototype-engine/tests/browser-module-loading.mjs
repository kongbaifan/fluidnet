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
  expect(await page.evaluate(()=>typeof window.createModuleReplayUI)).toBe('undefined');
  expect(await page.evaluate(async()=>typeof (await import('/engine-client.js')).createEngineClient)).toBe('function');
  const paths=scripts.map(response=>new URL(response.url()).pathname);
  expect(new Set(paths).size).toBe(paths.length);
  for(const response of scripts){expect(response.ok()).toBe(true);expect(response.headers()['content-type']).toMatch(/javascript/);}
  expect(errors).toEqual([]);
  // A cached engine predating the optional live-readout hooks must still open.
  const compatible=await browser.newPage(),compatibilityErrors=[];
  compatible.on('pageerror',error=>compatibilityErrors.push(error.message));
  await compatible.route('**/engine-client.js*',route=>{
    const url=new URL(route.request().url());
    if(url.searchParams.has('test-current-factory'))return route.continue();
    return route.fulfill({status:200,contentType:'text/javascript',body:`
      export * from './engine-client.js?test-current-factory=1';
      import {createEngineClient as currentFactory} from './engine-client.js?test-current-factory=1';
      export const createEngineClient = ui => {
        const client=currentFactory(ui);
        delete client.syncLiveReadouts; delete client.dispose;
        return client;
      };
      export default createEngineClient;
    `});
  });
  await compatible.goto(server.base+'/#workbench');
  await expect(compatible.locator('#network')).toBeVisible();
  await expect(compatible.locator('#page [role="alert"]')).toHaveCount(0);
  await compatible.evaluate(()=>{
    dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
    dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
  });
  await expect(compatible.locator('#network')).toBeVisible();
  expect(compatibilityErrors).toEqual([]);
  // A failed dependency must produce a visible failure, not an apparently ready shell.
  const failed=await browser.newPage();
  await failed.route('**/canvas-symbols.js',route=>route.fulfill({status:503,contentType:'text/plain',body:'controlled failure'}));
  await failed.goto(server.base+'/');
  await expect(failed.locator('#page [role="alert"]')).toContainText('工作台加载失败');
  await expect(failed.locator('#network')).toHaveCount(0);
  console.log(JSON.stringify({nativeModules:paths.length,duplicateFetches:0,fluidNetGlobals:0,legacyEngineOpens:true,failureVisible:true,errors}));
}finally{await browser.close();await server.close();}
