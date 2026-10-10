import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const output = resolve('.cache/studio-prototype-qa');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const errors = [], checks = [], layouts = [];
const routes = ['home','projects','workbench','modules','editor','nodes','models','curves','runs','controls','settings','help'];
const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
page.on('pageerror', e => errors.push(e.message));
try {
  await page.goto(pathToFileURL(resolve('output/visualizations/fluidnet-studio-prototype.html')).href);
  for (const route of routes) {
    await page.evaluate(route => location.hash = route, route);
    await page.waitForTimeout(80);
    await expect(page.locator('#page')).not.toBeEmpty();
    await expect(page.locator('[data-route="bench"],[data-route="connections"],[data-action="bench-module"],[data-action="bench-device"]')).toHaveCount(0);
    layouts.push(await page.evaluate(route => ({ route, width: innerWidth, outer: document.documentElement.scrollWidth, pageWidth: document.getElementById('page').clientWidth, contentWidth: document.getElementById('page').scrollWidth, text: document.getElementById('page').innerText.slice(0, 100) }), route));
    await page.screenshot({ path: resolve(output, route + '-1366.png') });
  }
  checks.push('12 routes rendered at 1366 × 768 without validation-bench or connection entry points');
  await page.locator('[data-action="page-map"]').first().click();
  await expect(page.locator('.map-link')).toHaveCount(12);
  await expect(page.locator('.map-link[data-route="bench"],.map-link[data-route="connections"]')).toHaveCount(0);
  await page.locator('[data-action="close-dialog"]').first().click();
  for(const retired of ['bench','connections']) {
    await page.goto(pathToFileURL(resolve('output/visualizations/fluidnet-studio-prototype.html')).href+'#'+retired);
    await expect(page).toHaveURL(/#home$/);
    await expect(page.locator('.rail-link[data-route="home"]')).toHaveClass(/active/);
  }
  checks.push('Page map lists current destinations and retired bookmarks recover to the home page');
  await page.evaluate(() => location.hash = 'editor');
  for (const tab of ['drawing','attributes','values','models','code','channels']) {
    await page.locator(`[data-action="editor-tab"][data-value="${tab}"]`).first().click();
    await page.screenshot({ path: resolve(output, 'editor-' + tab + '.png') });
  }
  checks.push('6 module editor tabs rendered, including the combined code page');
  await page.evaluate(() => location.hash = 'settings');
  for (const tab of ['project','medium','solver','appearance','storage']) await page.locator(`[data-action="settings-tab"][data-value="${tab}"]`).click();
  checks.push('5 settings pages rendered');
  for (const width of [1600, 1024, 736, 320]) {
    await page.setViewportSize({ width, height: width === 1600 ? 1000 : 768 });
    for (const route of routes) {
      await page.evaluate(route => location.hash = route, route);
      await page.waitForTimeout(35);
      layouts.push(await page.evaluate(route => ({ route, width: innerWidth, outer: document.documentElement.scrollWidth, pageWidth: document.getElementById('page').clientWidth, contentWidth: document.getElementById('page').scrollWidth }), route));
    }
    await page.screenshot({ path: resolve(output, 'guide-' + width + '.png') });
  }
  checks.push('Layout observations at 1600, 1024, 736 and 320 px');
  await page.evaluate(()=>location.hash='editor');
  await page.locator('[data-action="editor-tab"][data-value="code"]').click();
  for(const width of [1366,1600,1024,736,320]) {
    await page.setViewportSize({width,height:width===1600?1000:768});
    await expect(page.locator('[data-code-pane]')).toHaveCount(3);
    const layout=await page.evaluate(()=>({
      width:innerWidth,outer:document.documentElement.scrollWidth,
      pageWidth:document.getElementById('page').clientWidth,contentWidth:document.getElementById('page').scrollWidth,
      panes:[...document.querySelectorAll('[data-code-pane]')].map(el=>{const r=el.getBoundingClientRect(),area=el.querySelector('textarea');return{kind:el.dataset.codePane,x:r.x,y:r.y,width:r.width,height:r.height,editorHeight:area.clientHeight,editorWidth:area.clientWidth};})
    }));
    layouts.push({route:'editor-code',...layout});
    if(layout.outer>width+1||layout.contentWidth>layout.pageWidth+2||layout.panes.some(p=>p.x<0||p.x+p.width>width+1||p.editorHeight<72||p.editorWidth<p.width-70))throw Error(`Combined code layout overflow at ${width}`);
    if(width>=1024){for(const kind of ['runtime','header','design'])await expect(page.locator(`[data-code-pane="${kind}"] textarea`)).toBeInViewport();}
    else {for(const kind of ['runtime','header','design']){const pane=page.locator(`[data-code-pane="${kind}"]`);await pane.scrollIntoViewIfNeeded();await expect(pane.locator('textarea')).toBeInViewport();}await page.screenshot({path:resolve(output,`editor-code-${width}-design.png`)});}
    await page.locator('.editor-content').evaluate(el=>el.scrollTop=0);
    await page.screenshot({path:resolve(output,`editor-code-${width}.png`)});
  }
  await page.setViewportSize({width:1366,height:768});
  await page.locator('[data-action="theme"]').click();
  await page.screenshot({path:resolve(output,'editor-code-dark.png')});
  checks.push('Combined code editors fit desktop, stack on narrow screens and support dark appearance');
  if (errors.length) throw Error(errors.join('\n'));
} finally {
  await writeFile(resolve(output, 'pages.json'), JSON.stringify({ checks, errors, layouts }, null, 2));
  console.log(JSON.stringify({ checks, errors, overflow: layouts.filter(x => x.outer > x.width + 1 || x.contentWidth > x.pageWidth + 2) }, null, 2));
  await browser.close();
}
