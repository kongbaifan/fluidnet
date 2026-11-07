import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {loadManifest} from '../scripts/browser-groups.mjs';
import {parseNameStatus,selectImpact,inspectChanges} from '../scripts/browser-impact.mjs';
const manifest=loadManifest(),all=Object.keys(manifest.groups),change=(path,status='M')=>({status,paths:['fluidnet-prototype-engine/'+path]});
test('leaf changes narrow groups while cross-domain smoke always runs',()=>{
  const report=selectImpact(manifest,[change('frontend/canvas-routing.js')]);
  assert.deepEqual(report.groups,['smoke','canvas']);assert.equal(report.full,false);assert.ok(report.reasons[0].reason);
  assert.deepEqual(selectImpact(manifest,[]).groups,['smoke']);
  assert.deepEqual(selectImpact(manifest,[change('docs/DEVICE_REGISTRY.md')]).groups,['smoke']);
});
test('shared, unknown, new, removed and renamed inputs fall back to full coverage',()=>{
  for(const item of [change('frontend/studio.js'),change('backend/fn_engine/solver.py'),change('contracts/openapi.json'),
    change('frontend/new.js'),change('frontend/canvas-routing.js','A'),change('frontend/canvas-routing.js','D'),
    {status:'R100',paths:['fluidnet-prototype-engine/frontend/canvas-routing.js','fluidnet-prototype-engine/frontend/new.js']},
    {status:'M',paths:['.github/workflows/ci.yml']},change('tests/browser-server.mjs')]){
    assert.deepEqual(selectImpact(manifest,[item]).groups,all,JSON.stringify(item));
  }
});
test('entry changes select every parameter variant and imported entries remain conservative',()=>{
  const report=selectImpact(manifest,[change('tests/browser-equipment-assembly.mjs')]);
  assert.deepEqual(report.groups,['smoke','equipment-hvac','equipment-refrigeration']);
  assert.deepEqual(selectImpact(manifest,[change('tests/browser-parameter-batch.mjs')]).groups,all);
});
test('NUL records preserve unusual path text and both rename paths',()=>{
  assert.deepEqual(parseNameStatus('M\0a b\n中文.js\0R100\0old\0new\0'),[
    {status:'M',paths:['a b\n中文.js']},{status:'R100',paths:['old','new']}]);
  assert.throws(()=>parseNameStatus('R100\0old\0'),/Incomplete/);assert.throws(()=>parseNameStatus('what\0x\0'),/Invalid/);
});
test('Git comparison uses committed identities and includes deletion/addition without shell parsing',()=>{
  const cwd=mkdtempSync(join(tmpdir(),'fluidnet-impact-')),git=args=>execFileSync('git',args,{cwd,encoding:'utf8',windowsHide:true});
  git(['init','-q']);git(['config','user.email','test@example.invalid']);git(['config','user.name','Impact fixture']);
  writeFileSync(join(cwd,'old.txt'),'base');git(['add','.']);git(['commit','-qm','base']);const base=git(['rev-parse','HEAD']).trim();
  git(['mv','old.txt','new name.txt']);git(['commit','-qm','move']);
  const comparison=inspectChanges({base,cwd});assert.deepEqual(comparison.changes,[{status:'A',paths:['new name.txt']},{status:'D',paths:['old.txt']}]);
  assert.equal(comparison.mergeBase,base);assert.notEqual(comparison.head,base);
  assert.throws(()=>inspectChanges({base:'--bad',cwd}),/Command failed/);
});
