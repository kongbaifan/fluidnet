import {readFileSync,readdirSync,existsSync} from 'node:fs';
import {dirname,resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';

export const projectRoot=resolve(dirname(fileURLToPath(import.meta.url)),'..');
export function loadManifest(root=projectRoot){return JSON.parse(readFileSync(resolve(root,'scripts/browser-groups.json'),'utf8'));}
const safeId=value=>typeof value==='string'&&/^[a-z][a-z0-9_.:-]*$/.test(value);
function localFile(root,file){
  if(typeof file!=='string'||isAbsolute(file)||file.includes('\\'))return false;
  const local=relative(root,resolve(root,file));
  return local!==''&&!local.startsWith('..')&&!isAbsolute(local)&&existsSync(resolve(root,file));
}
export function validateManifest(manifest,root=projectRoot){
  const errors=[];
  if(manifest?.schema!==1||!manifest.groups||!Array.isArray(manifest.cases)||!manifest.helpers||!manifest.suites)
    throw Error('Invalid browser group manifest structure');
  const groupNames=Object.keys(manifest.groups),ids=new Set(),calls=new Set(),files=new Set();
  if(!groupNames.length||groupNames.some(name=>!safeId(name)))errors.push('Invalid group names');
  for(const item of manifest.cases){
    if(!safeId(item.id)||ids.has(item.id))errors.push(`Invalid or duplicate case id: ${item.id}`);
    ids.add(item.id);
    if(!groupNames.includes(item.group))errors.push(`Unknown group for ${item.id}: ${item.group}`);
    if(!/^tests\/browser-[a-z0-9-]+\.mjs$/.test(item.file||'')||!localFile(root,item.file))errors.push(`Missing or invalid browser file: ${item.file}`);
    files.add(item.file);
    if(!Array.isArray(item.args)||item.args.some(arg=>typeof arg!=='string'||/[\r\n\0]/.test(arg)))errors.push(`Invalid argv for ${item.id}`);
    else for(const arg of item.args)if(arg.endsWith('.json')&&!localFile(root,arg))errors.push(`Missing recipe for ${item.id}: ${arg}`);
    const call=JSON.stringify([item.file,item.args]);if(calls.has(call))errors.push(`Duplicate browser invocation: ${item.id}`);calls.add(call);
  }
  for(const group of groupNames)if(!manifest.cases.some(item=>item.group===group))errors.push(`Empty group: ${group}`);
  const helpers=Object.entries(manifest.helpers);
  for(const [file,reason] of helpers){
    if(files.has(file)||!localFile(root,file)||typeof reason!=='string'||!reason.trim())errors.push(`Invalid helper exemption: ${file}`);
  }
  for(const name of readdirSync(resolve(root,'tests')).filter(name=>/^browser-.*\.mjs$/.test(name)&&!name.endsWith('.test.mjs'))){
    const file='tests/'+name;
    if(!files.has(file)&&!Object.hasOwn(manifest.helpers,file))errors.push(`Unregistered browser file: ${file}`);
  }
  for(const [name,members] of Object.entries(manifest.suites)){
    if(!safeId(name)||!Array.isArray(members)||!members.length||new Set(members).size!==members.length)errors.push(`Invalid suite: ${name}`);
    else for(const id of members)if(!ids.has(id))errors.push(`Unknown case in suite ${name}: ${id}`);
  }
  if(errors.length)throw Error(errors.join('\n'));
  return {groups:groupNames.length,cases:manifest.cases.length,files:files.size,helpers:helpers.length};
}
export function selectCases(manifest,{groups=[],suites=[],ids=[]}={}){
  for(const group of groups)if(!Object.hasOwn(manifest.groups,group))throw Error('Unknown browser group: '+group);
  for(const suite of suites)if(!Object.hasOwn(manifest.suites,suite))throw Error('Unknown browser suite: '+suite);
  const wanted=new Set([...ids,...suites.flatMap(name=>manifest.suites[name])]);
  for(const id of wanted)if(!manifest.cases.some(item=>item.id===id))throw Error('Unknown browser case: '+id);
  return manifest.cases.filter(item=>!groups.length&&!suites.length&&!ids.length||groups.includes(item.group)||wanted.has(item.id))
    .map(item=>({...item,args:[...item.args]}));
}
export function ciMatrix(manifest){return {group:Object.keys(manifest.groups)};}
export function launchCase(item,{root=projectRoot,env=process.env}={}){
  return new Promise(resolveDone=>{
    const child=spawn(process.execPath,[item.file,...item.args],{cwd:root,env,stdio:'inherit',shell:false,windowsHide:true});
    child.once('error',error=>resolveDone({code:1,error:error.message}));
    child.once('close',(code,signal)=>resolveDone({code:code??1,signal}));
  });
}
export async function runCases(cases,{launch=launchCase,retries=0,log=console.log,ci=false}={}){
  if(!Number.isInteger(retries)||retries<0||retries>1)throw Error('Retries must be 0 or 1');
  const results=[];
  for(const item of cases){
    log(ci?`::group::${item.id}`:`[browser] ${item.id}`);
    const attempts=[];
    for(let attempt=0;attempt<=retries;attempt++){
      log(`node ${[item.file,...item.args].map(arg=>JSON.stringify(arg)).join(' ')}`);
      let receipt;try{receipt=await launch(item);}catch(error){receipt={code:1,error:error.message};}
      attempts.push(receipt);
      if(receipt.code===0)break;
      log(`Attempt ${attempt+1} failed (${receipt.code})${receipt.error?': '+receipt.error:''}`);
      if(attempt<retries)log(ci?`::warning::${item.id} failed; retrying once`:`Retrying ${item.id} once`);
    }
    const passed=attempts.at(-1).code===0;results.push({id:item.id,passed,attempts});
    if(passed&&attempts.length>1)log(ci?`::warning::${item.id} passed on retry; investigate flaky behavior`:`${item.id} passed on retry; investigate flaky behavior`);
    if(ci)log('::endgroup::');
    // Continue independent cases, then fail the group if any case never passed.
  }
  return {results,exitCode:results.some(result=>!result.passed)?1:0};
}
export function parseArguments(args){
  const result={groups:[],suites:[],ids:[],retries:0};
  for(let i=0;i<args.length;i++){
    const arg=args[i];
    if(['--check','--list','--matrix','--run','--ci'].includes(arg))result[arg.slice(2)]=true;
    else if(['--group','--suite','--case','--retries'].includes(arg)){
      const value=args[++i];if(!value||value.startsWith('--'))throw Error('Missing value for '+arg);
      if(arg==='--retries'){if(!/^[01]$/.test(value))throw Error('Retries must be 0 or 1');result.retries=Number(value);}
      else result[{'--group':'groups','--suite':'suites','--case':'ids'}[arg]].push(value);
    }else throw Error('Unknown argument: '+arg);
  }
  if(result.run&&(result.list||result.matrix||result.check))throw Error('Dry inspection flags cannot be combined with --run');
  return result;
}
export async function main(args=process.argv.slice(2)){
  const options=parseArguments(args),manifest=loadManifest(),counts=validateManifest(manifest),cases=selectCases(manifest,options);
  if(options.matrix){console.log(JSON.stringify(ciMatrix(manifest)));return 0;}
  if(options.list){console.log(JSON.stringify(cases,null,2));return 0;}
  if(options.check){console.log(`Browser manifest valid: ${counts.cases} invocations, ${counts.files} executable files, ${counts.groups} groups, ${counts.helpers} helper exemptions`);return 0;}
  if(!options.run){console.log('Use --check, --list, --matrix, or --run [--group name | --suite name | --case id] [--retries 1].');return 0;}
  const outcome=await runCases(cases,{retries:options.retries,ci:options.ci});
  console.log(JSON.stringify({browserResults:outcome.results}));return outcome.exitCode;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  try{process.exitCode=await main();}catch(error){console.error(error.message);process.exitCode=1;}
}
