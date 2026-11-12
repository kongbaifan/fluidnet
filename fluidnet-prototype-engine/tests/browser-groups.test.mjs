import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {loadManifest,validateManifest,selectCases,ciMatrix,runCases,parseArguments,projectRoot,launchCase} from '../scripts/browser-groups.mjs';

const clone=value=>structuredClone(value);
test('all registered browser entries and helpers parse without executing them',()=>{
  const manifest=loadManifest();validateManifest(manifest);
  const files=new Set([...manifest.cases.map(item=>item.file),...Object.keys(manifest.helpers)]);
  for(const file of files)execFileSync(process.execPath,['--check',file],{cwd:projectRoot,encoding:'utf8',windowsHide:true});
});

function fixture(){
  const root=mkdtempSync(join(tmpdir(),'fluidnet-browser-manifest-'));
  mkdirSync(join(root,'tests'));mkdirSync(join(root,'examples'));
  writeFileSync(join(root,'tests/browser-one.mjs'),'// fixture, never executed\n');
  writeFileSync(join(root,'tests/browser-helper.mjs'),'export const helper = true;\n');
  writeFileSync(join(root,'examples/recipe.json'),'{}');
  return {root,manifest:{schema:1,groups:{smoke:'Smoke'},helpers:{'tests/browser-helper.mjs':'Imported helper'},
    cases:[{id:'one',group:'smoke',file:'tests/browser-one.mjs',args:['examples/recipe.json']}],suites:{one:['one']}}};
}
test('every browser executable and parameter variant is registered exactly once',()=>{
  const manifest=loadManifest();const counts=validateManifest(manifest);
  assert.ok(counts.files>50);assert.equal(counts.helpers,3);
  const selected=selectCases(manifest);
  for(const id of ['performance-data','open-refrigeration-groups','engineering-canvas','canvas-symbols','canvas-performance',
    'design-library','project-editing','system-inspection','forward-integration','module-replay','parameter-batch','module-assertion-boundaries'])
    assert.ok(selected.some(item=>item.id===id),id+' was omitted');
  assert.deepEqual(selected.filter(item=>item.file==='tests/browser-refrigeration-modular.mjs').map(item=>item.args),[[],['--cascade'],['--equipment']]);
  assert.equal(selected.filter(item=>item.file==='tests/browser-equipment-assembly.mjs').length,25);
  assert.ok(selected.some(item=>item.id==='canvas-performance-live'&&item.args.includes('--live')));
  assert.ok(selected.some(item=>item.id==='equipment-assembly:standard-plant'&&item.args.includes('--standard-plant')));
  assert.deepEqual(selected.filter(item=>item.file==='tests/browser-hvac-plant.mjs').map(item=>item.args),[[],['--multi-page']]);
});
test('all CI groups cover the full plan and the smoke group spans domains',()=>{
  const manifest=loadManifest(),matrix=ciMatrix(manifest),all=selectCases(manifest);
  const grouped=matrix.group.flatMap(group=>selectCases(manifest,{groups:[group]}));
  assert.equal(grouped.length,all.length);assert.deepEqual(new Set(grouped.map(item=>item.id)),new Set(all.map(item=>item.id)));
  const smoke=new Set(selectCases(manifest,{groups:['smoke']}).map(item=>item.id));
  for(const id of ['smoke','workflows','module-workflow','chiller-air-loop','refrigeration-modular'])assert.ok(smoke.has(id));
});
test('legacy npm suites delegate to the same registry, including new P1 and canvas cases',()=>{
  const manifest=loadManifest(),pkg=JSON.parse(readFileSync(resolve(projectRoot,'package.json'),'utf8'));
  for(const [name,command] of Object.entries(pkg.scripts).filter(([name])=>name.startsWith('test:browser:'))){
    const suite=name.slice('test:browser:'.length);
    assert.ok(manifest.suites[suite],name);assert.equal(command,`node scripts/browser-groups.mjs --run --suite ${suite}`);
  }
  assert.match(pkg.scripts['test:browser'],/^npm run test:ui && node scripts\/browser-groups.mjs --run$/);
  assert.deepEqual(selectCases(manifest,{suites:['p1']}).map(item=>item.id),['performance-data','open-refrigeration-groups']);
});
test('new files, missing recipes, helper misuse and duplicate invocations fail the coverage gate',()=>{
  const {root,manifest}=fixture();validateManifest(manifest,root);
  writeFileSync(join(root,'tests/browser-manifest.test.mjs'),'// Node unit test, not a browser entrypoint');validateManifest(manifest,root);
  writeFileSync(join(root,'tests/browser-new.mjs'),'// not yet registered');
  assert.throws(()=>validateManifest(manifest,root),/Unregistered browser file/);
  const registered=clone(manifest);registered.cases.push({id:'new',group:'smoke',file:'tests/browser-new.mjs',args:[]});validateManifest(registered,root);
  const missing=clone(registered);missing.cases[0].args=['examples/missing.json'];assert.throws(()=>validateManifest(missing,root),/Missing recipe/);
  const duplicate=clone(registered);duplicate.cases.push({...duplicate.cases[0],id:'same-command'});assert.throws(()=>validateManifest(duplicate,root),/Duplicate browser invocation/);
  const helper=clone(registered);helper.helpers['tests/browser-new.mjs']='Already executed';assert.throws(()=>validateManifest(helper,root),/Invalid helper/);
  const escaped=clone(registered);escaped.cases[0].file='../browser-elsewhere.mjs';assert.throws(()=>validateManifest(escaped,root),/invalid browser file/);
});
test('selection is a union without duplicate runs, and returned argv cannot mutate the manifest',()=>{
  const manifest=loadManifest(),before=JSON.stringify(manifest);
  const chosen=selectCases(manifest,{groups:['canvas'],suites:['canvas'],ids:['canvas-performance']});
  assert.equal(chosen.filter(item=>item.id==='canvas-performance').length,1);
  chosen[0].args.push('--changed');assert.equal(JSON.stringify(manifest),before);
  assert.throws(()=>selectCases(manifest,{groups:['typo']}),/Unknown browser group/);
  assert.throws(()=>selectCases(manifest,{suites:['typo']}),/Unknown browser suite/);
  assert.throws(()=>selectCases(manifest,{ids:['typo']}),/Unknown browser case/);
});
test('one retry is visible, successful cases are not repeated, permanent failure fails the group',async()=>{
  const cases=['ok','flaky','broken','after'].map(id=>({id,file:'tests/browser-one.mjs',args:[]})),attempts=new Map(),messages=[];
  const outcome=await runCases(cases,{retries:1,ci:true,log:message=>messages.push(message),launch:async item=>{
    const number=(attempts.get(item.id)||0)+1;attempts.set(item.id,number);
    return {code:item.id==='broken'||item.id==='flaky'&&number===1?1:0};
  }});
  assert.deepEqual(Object.fromEntries(attempts),{ok:1,flaky:2,broken:2,after:1});
  assert.equal(outcome.exitCode,1);assert.equal(outcome.results[1].passed,true);assert.equal(outcome.results[2].passed,false);
  assert.ok(messages.some(line=>line.includes('::warning::flaky passed on retry')));
});
test('spawn failures and termination never turn into success, and local retries default off',async()=>{
  let count=0;
  const cases=[{id:'failed',file:'tests/browser-one.mjs',args:[]}];
  const thrown=await runCases(cases,{log:()=>{},launch:async()=>{count++;throw Error('spawn failed');}});
  assert.equal(thrown.exitCode,1);assert.equal(count,1);
  const stopped=await runCases(cases,{log:()=>{},launch:async()=>({code:null,signal:'SIGTERM'})});assert.equal(stopped.exitCode,1);
});
test('launcher passes argv and environment without a shell or a second server harness',async()=>{
  const {root}=fixture();
  writeFileSync(join(root,'tests/browser-one.mjs'),"process.exit(process.argv[2] === 'arg with spaces' && process.argv[3] === '$(literal)' && process.env.FLUIDNET_MANIFEST_PROBE === 'present' ? 0 : 7);\n");
  const item={file:'tests/browser-one.mjs',args:['arg with spaces','$(literal)']};
  const result=await launchCase(item,{root,env:{...process.env,FLUIDNET_MANIFEST_PROBE:'present'}});assert.equal(result.code,0);
  const rejected=await launchCase({...item,args:['different']},{root});assert.equal(rejected.code,7);
});
test('CLI inspection validates without importing or executing browser cases',()=>{
  const matrix=JSON.parse(execFileSync(process.execPath,['scripts/browser-groups.mjs','--matrix'],{cwd:projectRoot,encoding:'utf8',windowsHide:true}));
  assert.deepEqual(matrix,ciMatrix(loadManifest()));
  const cases=JSON.parse(execFileSync(process.execPath,['scripts/browser-groups.mjs','--list','--suite','p1'],{cwd:projectRoot,encoding:'utf8',windowsHide:true}));
  assert.equal(cases.length,2);
  assert.throws(()=>parseArguments(['--run','--list']),/Dry inspection/);
  assert.throws(()=>parseArguments(['--run','--retries','-1']),/Retries/);
  assert.throws(()=>parseArguments(['--group']),/Missing value/);
});
