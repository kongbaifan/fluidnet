import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import vm from 'node:vm';
import {loadFrontend} from './frontend-module-loader.mjs';

test('the page has one module entry and every feature has a native exported entry',()=>{
  const html=readFileSync(new URL('../frontend/index.html',import.meta.url),'utf8');
  assert.deepEqual([...html.matchAll(/<script\b[^>]*>/g)].map(m=>m[0]),['<script type="module" src="bootstrap.js">']);
  const files=readdirSync(new URL('../frontend/',import.meta.url)).filter(name=>name.endsWith('.js'));
  for(const name of files){
    const source=readFileSync(new URL('../frontend/'+name,import.meta.url),'utf8');
    if(name==='module-replay.js')continue; // User-owned legacy implementation has a dedicated adapter.
    assert.doesNotMatch(source,/window\.(?:FluidNet\w+|create\w+|ModuleTestEditor|EquipmentSelection|DeviceBatchEditor)\s*=/,name);
    if(name!=='bootstrap.js')assert.match(source,/export (?:const|function|default)/,name);
  }
});
test('the entire studio dependency graph links without starting or exporting globals',()=>{
  const host=vm.createContext({window:{}}),entry=loadFrontend(new URL('../frontend/studio.js',import.meta.url),host);
  assert.equal(typeof entry.startStudio,'function');
  // The real equipment/performance cycle must link, including both directions.
  assert.equal(typeof host.window.EquipmentSelection.assertModelCompatible,'function');
  assert.equal(typeof host.window.FluidNetPerformanceData.references,'function');
});
