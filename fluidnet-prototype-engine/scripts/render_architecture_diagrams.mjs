/** Render the tagged Mermaid blocks in docs/ARCHITECTURE_AND_SEQUENCE.md.
 * Usage: node scripts/render_architecture_diagrams.mjs [--mermaid-js path]
 * Requires the project's Playwright dependency and a local Microsoft Edge.
 */
import { readFile, writeFile, mkdir, access } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'docs', 'diagrams');
const cache = path.join(root, 'tmp', 'architecture-render');
const version = '11.12.2';
const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--mermaid-js')) {
  throw new Error('Usage: node scripts/render_architecture_diagrams.mjs [--mermaid-js path]');
}
let library = args.length ? path.resolve(args[1]) : path.join(cache, `mermaid-${version}.min.js`);
await mkdir(output, { recursive: true });
await mkdir(cache, { recursive: true });
try {
  await access(library);
} catch (error) {
  if (args.length || error.code !== 'ENOENT') throw error;
  const response = await fetch(`https://cdn.jsdelivr.net/npm/mermaid@${version}/dist/mermaid.min.js`,
    { signal: AbortSignal.timeout(60000) });
  if (!response.ok) throw new Error(`Mermaid download failed: HTTP ${response.status}`);
  await writeFile(library, new Uint8Array(await response.arrayBuffer()));
}
const source = await readFile(path.join(root, 'docs', 'ARCHITECTURE_AND_SEQUENCE.md'), 'utf8');
const blocks = [...source.matchAll(/<!-- diagram: ([a-z0-9-]+) -->\s*```mermaid\r?\n([\s\S]*?)\r?\n```/g)];
const diagramCount = [...source.matchAll(/^```mermaid\s*$/gm)].length;
if (!blocks.length || blocks.length !== diagramCount || new Set(blocks.map(b => b[1])).size !== blocks.length) {
  throw new Error(`Every Mermaid diagram needs a unique diagram marker: ${blocks.length} markers for ${diagramCount} diagrams`);
}

const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1800, height: 1200 }, deviceScaleFactor: 1.5 });
  await page.setContent('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>body{margin:0;background:#fff}#diagram{display:inline-block;padding:24px;background:#fff}svg{display:block;max-width:none!important}</style><div id="diagram"></div></html>');
  await page.addScriptTag({ path: library });
  await page.evaluate(() => mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    htmlLabels: false,
    markdownAutoWrap: false,
    fontFamily: 'Microsoft YaHei, Segoe UI, sans-serif',
    themeVariables: {
      fontFamily: 'Microsoft YaHei, Segoe UI, sans-serif', fontSize: '16px',
      primaryColor: '#edf5ff', primaryTextColor: '#18324f', primaryBorderColor: '#86a6c8',
      secondaryColor: '#f0f7f4', tertiaryColor: '#faf7ee', lineColor: '#61788f',
      mainBkg: '#edf5ff', nodeBorder: '#86a6c8', clusterBkg: '#f7f9fc', clusterBorder: '#c6d2df',
      titleColor: '#18324f', edgeLabelBackground: '#ffffff',
      actorBkg: '#edf5ff', actorBorder: '#86a6c8', actorTextColor: '#18324f',
      actorLineColor: '#b5c3d1', signalColor: '#39536d', signalTextColor: '#18324f',
      labelBoxBkgColor: '#f0f4f8', labelBoxBorderColor: '#c6d2df', labelTextColor: '#18324f',
      loopTextColor: '#18324f', noteBkgColor: '#fff8e5', noteBorderColor: '#d5c28c',
      noteTextColor: '#51482d', activationBkgColor: '#dce9f6', sequenceNumberColor: '#ffffff',
    },
    flowchart: { htmlLabels: false, curve: 'linear', nodeSpacing: 35, rankSpacing: 40, padding: 16, wrappingWidth: 280, useMaxWidth: false },
    sequence: { useMaxWidth: false, actorMargin: 48, diagramMarginX: 24, diagramMarginY: 20,
      messageMargin: 24, noteMargin: 14, boxMargin: 10, mirrorActors: false,
      actorFontSize: 16, messageFontSize: 16, noteFontSize: 15, wrap: false },
  }));
  const manifest = [];
  for (const [, name, diagram] of blocks) {
    const dimensions = await page.evaluate(async ({ name, diagram }) => {
      const host = document.getElementById('diagram');
      host.replaceChildren();
      const { svg } = await mermaid.render(`fn-${name}`, diagram);
      host.innerHTML = svg;
      await document.fonts.ready;
      const node = host.querySelector('svg');
      if (!node || host.querySelector('.error-icon')) throw new Error(`Invalid diagram ${name}`);
      if (node.querySelector('foreignObject')) throw new Error(`${name}: SVG contains nonportable HTML labels`);
      const box = node.viewBox.baseVal;
      node.setAttribute('width', String(Math.ceil(box.width)));
      node.setAttribute('height', String(Math.ceil(box.height)));
      node.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      node.setAttribute('style', 'background:#ffffff;max-width:none');
      const clipped = [...node.querySelectorAll('text')].filter(text => {
        const bounds = text.getBoundingClientRect();
        const frame = node.getBoundingClientRect();
        return bounds.left < frame.left - 2 || bounds.top < frame.top - 2
          || bounds.right > frame.right + 2 || bounds.bottom > frame.bottom + 2;
      }).map(text => text.textContent);
      if (clipped.length) throw new Error(`${name}: text outside SVG: ${clipped.join(', ')}`);
      return { width: Math.ceil(box.width), height: Math.ceil(box.height), svg: new XMLSerializer().serializeToString(node) };
    }, { name, diagram });
    await writeFile(path.join(output, `${name}.mmd`), `${diagram}\n`);
    await writeFile(path.join(output, `${name}.svg`), dimensions.svg);
    await page.locator('#diagram').screenshot({ path: path.join(output, `${name}.png`), animations: 'disabled', timeout: 30000 });
    manifest.push({ name, width: dimensions.width, height: dimensions.height });
    console.log(`${name}: ${dimensions.width} x ${dimensions.height}`);
  }
  await writeFile(path.join(cache, 'render-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`Rendered ${manifest.length} diagrams to ${output}`);
} finally {
  await browser.close();
}
