import {execFileSync} from 'node:child_process';
import {mkdirSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {loadManifest,validateManifest,projectRoot} from './browser-groups.mjs';

// Only reviewed leaf changes can narrow coverage. Shared and unknown inputs stay full.
const leafGroups={
  'frontend/canvas-routing.js':['canvas'],
  'frontend/canvas-symbols.js':['canvas','authoring','equipment-hvac','equipment-refrigeration'],
  'frontend/canvas-observations.js':['canvas'],
  'frontend/canvas-view.js':['canvas'],
  'frontend/canvas-view.css':['canvas'],
  'frontend/path-trace.js':['canvas'],
  'frontend/air-side.css':['hvac','equipment-hvac'],
  'frontend/cold-storage.js':['refrigeration','equipment-refrigeration'],
  'frontend/air-side.js':['hvac','equipment-hvac','refrigeration'],
  'frontend/equipment-selection.js':['workflows'],
  'frontend/performance-library.js':['workflows','equipment-hvac','equipment-refrigeration'],
  'frontend/module-replay.js':['workflows'],
  'frontend/panel-layout.js':['workflows','canvas'],
  'frontend/api-examples.js':['workflows'],
};
const prefix='fluidnet-prototype-engine/';
export function parseNameStatus(text){
  const tokens=text.split('\0');if(tokens.at(-1)==='')tokens.pop();
  const changes=[];
  for(let i=0;i<tokens.length;){
    const status=tokens[i++];
    if(!/^[ACDMRTUXB][0-9]*$/.test(status))throw Error('Invalid git change status');
    const count=/^[RC]/.test(status)?2:1,paths=tokens.slice(i,i+count);i+=count;
    if(paths.length!==count||paths.some(path=>!path))throw Error('Incomplete git change path');
    changes.push({status,paths});
  }
  return changes;
}
export function selectImpact(manifest,changes,{forceFull=false,reason='Full coverage requested'}={}){
  const all=Object.keys(manifest.groups),selected=new Set(['smoke']),reasons=[];
  if(!all.includes('smoke'))throw Error('The cross-domain smoke group is required');
  let full=forceFull;
  if(forceFull)reasons.push({path:null,reason,groups:all});
  for(const change of changes){
    for(const path of change.paths){
      const local=path.startsWith(prefix)?path.slice(prefix.length):null;
      let groups=null,why='Shared or unclassified input';
      if(change.status!=='M'){why='Added, removed, renamed or otherwise changed identity';}
      else if((local?.startsWith('docs/')&&/\.md$/.test(local))||path==='README.md'||local==='README.md'){
        groups=[];why='Documentation only; smoke retained';
      }else if(local&&leafGroups[local]){groups=leafGroups[local];why='Reviewed frontend leaf';}
      else if(local){
        const cases=manifest.cases.filter(item=>item.file===local);
        if(cases.length&&!Object.hasOwn(manifest.helpers,local)){
          groups=[...new Set(cases.map(item=>item.group))];why='All registered variants of this browser entry';
          // These entry files are also imported by other cases.
          if(['tests/browser-parameter-batch.mjs','tests/browser-module-assertion-boundaries.mjs'].includes(local))groups=null;
        }else if(local.startsWith('examples/hvac-basic/')){
          groups=['hvac','equipment-hvac'];why='HVAC reference inputs';
        }
      }
      if(groups===null){full=true;groups=all;}
      for(const group of groups){if(!all.includes(group))throw Error('Impact rule references missing group: '+group);selected.add(group);}
      reasons.push({path,status:change.status,reason:why,groups});
    }
  }
  const groups=full?all:all.filter(group=>selected.has(group));
  return {schema:1,full,groups,matrix:{group:groups},reasons};
}
export function inspectChanges({base,head='HEAD',cwd=projectRoot,git=execFileSync}={}){
  const run=args=>git('git',args,{cwd,encoding:'utf8',windowsHide:true,maxBuffer:8*1024*1024});
  const resolvedBase=run(['rev-parse','--verify','--end-of-options',`${base}^{commit}`]).trim();
  const resolvedHead=run(['rev-parse','--verify','--end-of-options',`${head}^{commit}`]).trim();
  const mergeBase=run(['merge-base',resolvedBase,resolvedHead]).trim();
  const changes=parseNameStatus(run(['diff','--name-status','-z','--no-renames',mergeBase,resolvedHead,'--']));
  return {base:resolvedBase,head:resolvedHead,mergeBase,changes};
}
export function main(args=process.argv.slice(2)){
  const options={};
  for(let i=0;i<args.length;i++){
    const arg=args[i];
    if(arg==='--all'||arg==='--matrix')options[arg.slice(2)]=true;
    else if(['--base','--head','--output'].includes(arg)){
      const value=args[++i];if(!value||value.startsWith('--'))throw Error('Missing value for '+arg);options[arg.slice(2)]=value;
    }else throw Error('Unknown argument: '+arg);
  }
  const manifest=loadManifest();validateManifest(manifest);
  let report;
  if(options.all||!options.base)report=selectImpact(manifest,[],{forceFull:true,reason:'No PR comparison requested'});
  else{
    try{const comparison=inspectChanges(options);report={...selectImpact(manifest,comparison.changes),comparison};}
    catch(error){report=selectImpact(manifest,[],{forceFull:true,reason:'Cannot establish comparison: '+error.message});}
  }
  if(options.output){const output=resolve(options.output);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');}
  console.log(JSON.stringify(options.matrix?report.matrix:report));
  return report;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  try{main();}catch(error){console.error(error.message);process.exitCode=1;}
}
