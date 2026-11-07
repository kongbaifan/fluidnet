import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {loadManifest,validateManifest,selectCases,runCases,projectRoot} from './browser-groups.mjs';
import {inspectChanges,selectImpact} from './browser-impact.mjs';

export const loadQuick=()=>JSON.parse(readFileSync(resolve(projectRoot,'scripts/ci-quick.json'),'utf8'));
export function validateQuick(quick,manifest,root=projectRoot){
  if(quick.version!==1||!Array.isArray(quick.backend_core)||!quick.backend_core.length||!quick.backend_groups||!quick.browser_representatives)
    throw Error('Invalid quick CI manifest');
  const targets=[...quick.backend_core,...Object.values(quick.backend_groups).flat()];
  for(const target of targets){
    if(typeof target!=='string'||!/^tests\/test_[a-z0-9_]+\.py(?:::[A-Za-z_][A-Za-z0-9_]*)?$/.test(target)||!existsSync(resolve(root,target.split('::')[0])))
      throw Error('Invalid or missing quick backend target: '+target);
    if(target.includes('::')&&!readFileSync(resolve(root,target.split('::')[0]),'utf8').includes('def '+target.split('::')[1]+'('))
      throw Error('Missing quick backend test: '+target);
  }
  if(new Set(targets).size!==targets.length)throw Error('Duplicate quick backend target');
  if(Object.keys(quick.backend_groups).some(name=>!Array.isArray(quick.backend_groups[name])||!quick.backend_groups[name].length))
    throw Error('Empty backend quick group');
  if(JSON.stringify(Object.keys(quick.browser_representatives).sort())!==JSON.stringify(Object.keys(manifest.groups).sort()))
    throw Error('Every browser group must have quick representatives');
  const chosen=[];
  for(const [group,ids] of Object.entries(quick.browser_representatives)){
    if(!Array.isArray(ids)||!ids.length)throw Error('Empty browser representatives: '+group);
    for(const id of ids){
      if(!manifest.cases.some(item=>item.id===id&&item.group===group))throw Error('Invalid browser representative: '+id);
      chosen.push(id);
    }
  }
  if(new Set(chosen).size!==chosen.length)throw Error('Duplicate browser representative');
  if(chosen.length>=manifest.cases.length)throw Error('Quick CI cannot contain the entire browser chain');
  for(const item of manifest.cases.filter(item=>item.group==='smoke'))if(!chosen.includes(item.id))throw Error('Fixed smoke case omitted: '+item.id);
}

export function buildPlan(manifest,quick,changes,{fallbackReason=null}={}){
  const impact=selectImpact(manifest,changes,{forceFull:!!fallbackReason,reason:fallbackReason||''});
  const backendGroups=new Set(),all=Object.keys(quick.backend_groups),reasons=[];
  const broad=(path,reason)=>{all.forEach(group=>backendGroups.add(group));reasons.push({path,groups:all,reason});};
  if(fallbackReason)broad(null,fallbackReason);
  for(const change of changes)for(const path of change.paths){
    const local=path.startsWith('fluidnet-prototype-engine/')?path.slice('fluidnet-prototype-engine/'.length):path;
    if(change.status!=='M'){broad(path,'Changed identity; cover every quick backend group');continue;}
    if(/^(frontend\/|docs\/)|\.md$/.test(local))continue;
    if(local.startsWith('tests/browser-')||local.endsWith('.test.mjs'))continue;
    let groups;
    if(/(^backend\/fn_engine\/refrigeration\/|refrigeration|cold_store)/.test(local))groups=['refrigeration','thermal'];
    else if(/(^backend\/fn_engine\/(air_|moist_air|water_chiller)|hvac)/.test(local))groups=['hvac','hydraulics','thermal'];
    else if(/hydraulic|analytic_jacobian/.test(local))groups=['hydraulics'];
    else if(/(^backend\/fn_engine\/(thermal|trapped|timestep)|test_(thermal|states))/.test(local))groups=['thermal'];
    else if(/(^backend\/fn_engine\/(module_|worker|runtime|packages|composites)|^modules\/|test_module_)/.test(local))groups=['modules','sessions'];
    else if(/(^backend\/fn_engine\/(simulation|session|jobs|control)|parameter_write)/.test(local))groups=['sessions'];
    if(groups){groups.forEach(group=>backendGroups.add(group));reasons.push({path,groups,reason:'Affected backend domain'});}
    else broad(path,'Shared or unclassified input; cover every quick backend group');
  }
  const groups=all.filter(group=>backendGroups.has(group)),targets=[...quick.backend_core,...groups.flatMap(group=>quick.backend_groups[group])];
  const ids=new Set(impact.groups.flatMap(group=>quick.browser_representatives[group]));
  // Directly edited browser entries are represented by their first registered
  // variant. All remaining variants are explicitly listed for the manual workflow.
  for(const change of changes)for(const path of change.paths){
    const file=path.replace(/^fluidnet-prototype-engine\//,'');
    const first=manifest.cases.find(item=>item.file===file);if(first)ids.add(first.id);
  }
  // Even a change touching every test must not silently start the full chain.
  if(ids.size===manifest.cases.length){ids.clear();Object.values(quick.browser_representatives).flat().forEach(id=>ids.add(id));}
  const cases=manifest.cases.filter(item=>ids.has(item.id));
  const browserGroups=Object.keys(manifest.groups).filter(group=>cases.some(item=>item.group===group));
  return {schema:1,mode:'quick',fullSuiteRun:false,comparisonFallback:fallbackReason,
    backend:{groups,targets,reasons,coverage:false},
    browser:{ids:cases.map(item=>item.id),matrix:{group:browserGroups},impact,
      deferred:manifest.cases.filter(item=>!ids.has(item.id)).map(item=>item.id)},
    manualWorkflow:'ci-full.yml'};
}

export function validatePlan(plan,manifest,quick){
  if(plan.schema!==1||plan.mode!=='quick'||plan.fullSuiteRun!==false||plan.backend?.coverage!==false)
    throw Error('Not a quick CI plan');
  if(!Array.isArray(plan.backend.groups)||new Set(plan.backend.groups).size!==plan.backend.groups.length||plan.backend.groups.some(group=>!Object.hasOwn(quick.backend_groups,group)))throw Error('Unknown or duplicate backend plan group');
  const expected=[...quick.backend_core,...plan.backend.groups.flatMap(group=>quick.backend_groups[group])];
  if(JSON.stringify(plan.backend.targets)!==JSON.stringify(expected))throw Error('Backend plan targets differ from the reviewed manifest');
  const ids=plan.browser?.ids;
  if(!Array.isArray(ids)||!ids.length||new Set(ids).size!==ids.length||ids.length>=manifest.cases.length)throw Error('Invalid quick browser selection');
  selectCases(manifest,{ids});
  for(const id of quick.browser_representatives.smoke)if(!ids.includes(id))throw Error('Quick plan omitted fixed smoke: '+id);
  const groups=Object.keys(manifest.groups).filter(group=>manifest.cases.some(item=>item.group===group&&ids.includes(item.id)));
  if(JSON.stringify(groups)!==JSON.stringify(plan.browser.matrix.group))throw Error('Browser matrix does not match selected cases');
  const deferred=manifest.cases.filter(item=>!ids.includes(item.id)).map(item=>item.id);
  if(JSON.stringify(deferred)!==JSON.stringify(plan.browser.deferred))throw Error('Deferred browser list does not match selection');
}

export function runBackend(plan,{launch=spawnSync}={}){
  const result=launch('python',['-m','pytest','-q',...plan.backend.targets],{cwd:projectRoot,stdio:'inherit',shell:false,windowsHide:true});
  return result.error||result.signal?1:result.status??1;
}
export async function main(args=process.argv.slice(2)){
  const options={};
  for(let i=0;i<args.length;i++){
    const arg=args[i];
    if(['--check','--matrix','--run-backend','--run-browser','--ci'].includes(arg))options[arg.slice(2)]=true;
    else if(['--base','--head','--output','--plan','--group'].includes(arg)){
      const value=args[++i];if(!value||value.startsWith('--'))throw Error('Missing value for '+arg);options[arg.slice(2)]=value;
    }else throw Error('Unknown argument: '+arg);
  }
  const manifest=loadManifest(),quick=loadQuick();validateManifest(manifest);validateQuick(quick,manifest);
  const executing=options['run-backend']||options['run-browser'];
  if(options['run-backend']&&options['run-browser']||executing&&!options.plan||executing&&(options.matrix||options.check||options.base||options.head||options.output))
    throw Error('Execution requires a saved plan and one runner');
  if(options.group&&!options['run-browser'])throw Error('--group requires --run-browser');
  if(options.check&&(options.plan||options.base||options.head||options.output||options.matrix))throw Error('--check cannot be combined with plan arguments');
  if(options.plan&&(options.base||options.head))throw Error('Use either a saved plan or a Git comparison');
  if(options.check){console.log('Quick CI manifest valid; complete suites are manual only.');return 0;}
  let plan;
  if(options.plan)plan=JSON.parse(readFileSync(resolve(options.plan),'utf8'));
  else{
    let comparison,reason=null;
    try{if(options.base&&options.head)comparison=inspectChanges(options);else reason='No comparison supplied; all quick domains selected';}
    catch(error){reason='Comparison unavailable; all quick domains selected: '+error.message;}
    plan={...buildPlan(manifest,quick,comparison?.changes||[],{fallbackReason:reason}),comparison:comparison||null};
  }
  validatePlan(plan,manifest,quick);
  if(options['run-backend'])return runBackend(plan);
  if(options['run-browser']){
    if(!options.group||!plan.browser.matrix.group.includes(options.group))throw Error('Browser group not selected');
    const cases=selectCases(manifest,{ids:plan.browser.ids}).filter(item=>item.group===options.group);
    return (await runCases(cases,{retries:options.ci?1:0,ci:!!options.ci})).exitCode;
  }
  if(options.output){const file=resolve(options.output);mkdirSync(dirname(file),{recursive:true});writeFileSync(file,JSON.stringify(plan,null,2)+'\n');}
  console.log(JSON.stringify(options.matrix?plan.browser.matrix:plan));return 0;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  try{process.exitCode=await main();}catch(error){console.error(error.message);process.exitCode=1;}
}
