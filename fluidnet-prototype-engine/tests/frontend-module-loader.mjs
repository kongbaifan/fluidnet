import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const contexts=new WeakMap();
const frontendRoot=new URL('../frontend/',import.meta.url);
// Existing adapter fixtures replace only these external services. Product modules
// always use their real imports; the substitution is confined to the test VM.
const mockExports={'project-services.js':'createProjectServices','control-programs.js':'FluidNetControls'};
export function loadFrontend(url,host){
  if(!vm.SourceTextModule)throw Error('Use Node 24.8+ with --experimental-vm-modules for isolated frontend module tests');
  const context=vm.isContext(host)?host:vm.createContext(host);
  let state=contexts.get(context);
  if(!state){state={modules:new Map(),mocks:{...host.window}};contexts.set(context,state);}
  function getModule(target){
    const id=target.href;if(!id.startsWith(frontendRoot.href))throw Error('Frontend fixture import escaped its directory: '+id);
    if(state.modules.has(id))return state.modules.get(id);
    const name=mockExports[id.slice(frontendRoot.href.length)];let module;
    if(name&&Object.hasOwn(state.mocks,name)){
      const value=state.mocks[name];module=new vm.SyntheticModule([name,'default'],function(){this.setExport(name,value);this.setExport('default',value);},{context,identifier:id});
      state.modules.set(id,module);return module;
    }
    module=new vm.SourceTextModule(readFileSync(target,'utf8'),{context,identifier:id,
      initializeImportMeta(meta){meta.url=id;}});
    state.modules.set(id,module);
    if(module.hasTopLevelAwait())throw Error('Synchronous feature fixtures cannot load top-level await: '+id);
    const dependencies=module.moduleRequests.map(request=>{
      if(!request.specifier.startsWith('./'))throw Error('Unsupported frontend fixture import: '+request.specifier);
      return getModule(new URL(request.specifier,target));
    });
    module.linkRequests(dependencies);return module;
  }
  const module=getModule(url);
  if(module.status==='unlinked')module.instantiate();
  // All feature modules are synchronous. Keep each fixture isolated, including
  // cyclic imports, using the native ESM linker rather than rewriting source.
  const evaluated=module.evaluate();evaluated.catch(()=>{});
  if(module.status==='errored')throw module.error;
  if(module.status!=='evaluated')throw Error('Frontend fixture evaluation did not complete synchronously');
  for(const entry of state.modules.values())if(entry.status==='evaluated'){
    for(const name of Object.getOwnPropertyNames(entry.namespace))if(name!=='default')host.window[name]=entry.namespace[name];
  }
  return module.namespace;
}
