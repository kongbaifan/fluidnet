import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {loadManifest,projectRoot} from '../scripts/browser-groups.mjs';
import {loadQuick,validateQuick,buildPlan,validatePlan,runBackend} from '../scripts/ci-quick.mjs';

const manifest=loadManifest(),quick=loadQuick(),allGroups=Object.keys(quick.backend_groups);
const change=(path,status='M')=>({status,paths:['fluidnet-prototype-engine/'+path]});
const plan=(changes=[],options={})=>buildPlan(manifest,quick,changes,options);
const invoke=args=>spawnSync(process.execPath,['scripts/ci-quick.mjs',...args],{cwd:projectRoot,encoding:'utf8',shell:false,windowsHide:true});

test('quick manifest names existing tests and representatives for every domain',()=>{
  validateQuick(quick,manifest);
  const missing=structuredClone(quick);missing.backend_core.push('tests/test_missing_quick.py');
  assert.throws(()=>validateQuick(missing,manifest),/missing quick backend target/);
  const missingCase=structuredClone(quick);missingCase.backend_core[0]+='::not_a_real_case';
  assert.throws(()=>validateQuick(missingCase,manifest),/Missing quick backend test/);
  const badRepresentative=structuredClone(quick);badRepresentative.browser_representatives.canvas=['module-replay'];
  assert.throws(()=>validateQuick(badRepresentative,manifest),/Invalid browser representative/);
  const missingDomain=structuredClone(quick);delete missingDomain.browser_representatives.hvac;
  assert.throws(()=>validateQuick(missingDomain,manifest),/Every browser group/);
  const duplicate=structuredClone(quick);duplicate.backend_core.push(duplicate.backend_core[0]);
  assert.throws(()=>validateQuick(duplicate,manifest),/Duplicate quick backend target/);
});

test('frontend leaves and documentation keep core transactions plus fixed smoke',()=>{
  const canvas=plan([change('frontend/canvas-routing.js')]);validatePlan(canvas,manifest,quick);
  assert.deepEqual(canvas.backend.targets,quick.backend_core);
  assert.deepEqual(canvas.browser.matrix.group,['smoke','canvas']);
  assert.deepEqual(new Set(canvas.browser.ids),new Set([...quick.browser_representatives.smoke,...quick.browser_representatives.canvas]));
  const docs=plan([change('docs/CI_CHECKS.md')]);
  assert.deepEqual(docs.browser.ids,quick.browser_representatives.smoke);
  assert.deepEqual(docs.backend.targets,quick.backend_core);
});

test('backend changes add domain checks without enabling full pytest or coverage',()=>{
  const cases=[['backend/fn_engine/hydraulics.py',['hydraulics']],
    ['backend/fn_engine/air_compile.py',['hydraulics','thermal','hvac']],
    ['backend/fn_engine/refrigeration/compile.py',['thermal','refrigeration']],
    ['backend/fn_engine/runtime.py',['sessions','modules']]];
  for(const [path,expected] of cases){
    const selected=plan([change(path)]);validatePlan(selected,manifest,quick);
    assert.deepEqual(selected.backend.groups,expected,path);
    assert.equal(selected.backend.coverage,false);assert.equal(selected.fullSuiteRun,false);
    assert.ok(selected.backend.targets.every(target=>target.startsWith('tests/test_')));
  }
});

test('shared, unknown and identity changes conservatively expand only the quick scope',()=>{
  for(const item of [change('backend/fn_engine/solver.py'),change('unknown-input.bin'),
    change('frontend/canvas-routing.js','A'),change('frontend/canvas-routing.js','D'),
    {status:'R100',paths:['old-name.js','new-name.js']},{status:'M',paths:['.github/workflows/ci.yml']}]){
    const selected=plan([item]);validatePlan(selected,manifest,quick);
    assert.deepEqual(selected.backend.groups,allGroups);
    assert.deepEqual(selected.browser.matrix.group,Object.keys(manifest.groups));
    assert.ok(selected.browser.ids.length<manifest.cases.length);
    assert.ok(selected.browser.deferred.length>0);
  }
  const selected=plan([],{fallbackReason:'No comparison'});
  assert.deepEqual(selected.backend.groups,allGroups);assert.equal(selected.comparisonFallback,'No comparison');
  assert.equal(selected.browser.ids.length,Object.values(quick.browser_representatives).flat().length);
});

test('directly edited browser entries add a real variant and explicitly defer the others',()=>{
  const selected=plan([change('tests/browser-equipment-assembly.mjs')]);validatePlan(selected,manifest,quick);
  const variants=manifest.cases.filter(item=>item.file==='tests/browser-equipment-assembly.mjs');
  assert.ok(selected.browser.ids.includes(variants[0].id));
  assert.ok(variants.some(item=>selected.browser.deferred.includes(item.id)));
  assert.deepEqual(new Set([...selected.browser.ids,...selected.browser.deferred]),new Set(manifest.cases.map(item=>item.id)));
});

test('saved plans reject substituted commands, missing smoke and misleading scope reports',()=>{
  for(const mutate of [
    p=>p.backend.targets.push('--cov=fn_engine'),
    p=>p.backend.groups.push('unknown'),
    p=>{p.backend.groups.push('hydraulics','hydraulics');p.backend.targets.push(...quick.backend_groups.hydraulics,...quick.backend_groups.hydraulics);},
    p=>p.browser.ids.push('unknown'),
    p=>p.browser.ids.shift(),
    p=>p.browser.matrix.group.push('canvas'),
    p=>p.browser.deferred.pop(),
    p=>p.fullSuiteRun=true,
  ]){
    const changed=plan();mutate(changed);assert.throws(()=>validatePlan(changed,manifest,quick));
  }
});

test('backend runner uses explicit pytest targets without shell and propagates failure',()=>{
  const selected=plan();let launched;
  assert.equal(runBackend(selected,{launch:(...args)=>{launched=args;return {status:0};}}),0);
  assert.equal(launched[0],'python');assert.deepEqual(launched[1],['-m','pytest','-q',...quick.backend_core]);
  assert.equal(launched[2].shell,false);assert.equal(launched[2].windowsHide,true);assert.equal(launched[2].cwd,projectRoot);
  for(const [result,expected] of [[{status:5},5],[{status:null,signal:'SIGTERM'},1],[{error:Error('spawn failed')},1]])
    assert.equal(runBackend(selected,{launch:()=>result}),expected);
});

test('CLI dry planning, comparison failure and invalid execution remain explicit',()=>{
  const dir=mkdtempSync(join(tmpdir(),'fluidnet-quick-plan-')),file=join(dir,'plan.json');
  const result=invoke(['--matrix','--output',file]);assert.equal(result.status,0,result.stderr);
  const saved=JSON.parse(readFileSync(file,'utf8'));validatePlan(saved,manifest,quick);
  assert.deepEqual(JSON.parse(result.stdout),saved.browser.matrix);
  assert.equal(invoke(['--check']).status,0);
  const unchanged=invoke(['--base','HEAD','--head','HEAD']);assert.equal(unchanged.status,0,unchanged.stderr);
  assert.deepEqual(JSON.parse(unchanged.stdout).browser.matrix.group,['smoke']);
  const unavailable=invoke(['--base','--not-a-value']);assert.notEqual(unavailable.status,0);
  const fallback=invoke(['--base','0000000000000000000000000000000000000000','--head','HEAD']);
  assert.equal(fallback.status,0,fallback.stderr);assert.match(JSON.parse(fallback.stdout).comparisonFallback,/Comparison unavailable/);
  for(const args of [['--run-backend'],['--run-backend','--run-browser','--plan',file],
    ['--run-backend','--plan',file,'--head','HEAD'],['--plan',file,'--base','HEAD'],
    ['--check','--plan',file],['--run-browser','--plan',file,'--group','missing']])
    assert.notEqual(invoke(args).status,0,args.join(' '));
  saved.backend.targets.push('tests');writeFileSync(file,JSON.stringify(saved));
  const tampered=invoke(['--run-backend','--plan',file]);assert.notEqual(tampered.status,0);
  assert.match(tampered.stderr,/differ from the reviewed manifest/);
});
