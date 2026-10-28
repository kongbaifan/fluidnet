import assert from 'node:assert/strict';
import {mkdirSync, writeFileSync} from 'node:fs';
import {dirname} from 'node:path';

export const FHD_VIEWPORT = Object.freeze({width: 1920, height: 1080});
export const FHD_CONTEXT = Object.freeze({
  viewport: FHD_VIEWPORT, screen: FHD_VIEWPORT, deviceScaleFactor: 1,
});

export async function captureFhd(page, target) {
  if (!page) return;
  assert.deepEqual(page.viewportSize(), FHD_VIEWPORT, '验收视口必须为 1920×1080');
  const geometry = await page.evaluate(() => ({
    width: innerWidth, height: innerHeight, pixelRatio: devicePixelRatio,
    screenWidth: screen.width, screenHeight: screen.height,
    userAgent: navigator.userAgent,
  }));
  assert.equal(geometry.width, 1920);
  assert.equal(geometry.height, 1080);
  assert.equal(geometry.pixelRatio, 1);
  const path = target.replace(/(?:-1080p)?\.png$/, '-1080p.png');
  mkdirSync(dirname(path), {recursive: true});
  const png = await page.screenshot({path, fullPage: false});
  assert.equal(png.readUInt32BE(16), 1920);
  assert.equal(png.readUInt32BE(20), 1080);
  const evidence = {...geometry, capturedAt: new Date().toISOString(),
    browserVersion: page.context().browser()?.version(), url: page.url(), screenshot: path};
  writeFileSync(path + '.json', JSON.stringify(evidence, null, 2) + '\n');
  return evidence;
}
