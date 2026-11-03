/* Project editing operations. Rendering, HTTP and backup policy belong to callers. */
window.FluidNetProjectState = (() => {
  const clone=value=>value===undefined?undefined:JSON.parse(JSON.stringify(value));
  const links=window.FluidNetLinks;
  function assertCurrent(state,owner) {
    if(state.projects.find(p=>p.id===owner.id)!==owner)throw Error('项目已被替换，请重新打开当前项目。');
    return owner;
  }
  function node(owner,target) {
    const id=typeof target==='string'?target:target.id;
    const found=owner.pages.flatMap(p=>p.nodes).find(n=>n.id===id);
    if(!found || (typeof target!=='string' && found!==target))throw Error('设备已被删除或替换，请重新选择。');
    return found;
  }
  function markDirty(state,owner) { state.dirty=true;if(owner)owner.dirty=true; }
  function setDraft(owner,target,values) {
    const n=node(owner,target),candidate=clone(values);
    n.draft={...n.draft,...candidate};return n;
  }
  function applyParameters(owner,target,values) {
    const n=node(owner,target),candidate=clone(values);
    n.params={...n.params,...candidate};return n;
  }
  function updateNode(owner,target,patch) {
    const n=node(owner,target),candidate=clone(patch);
    Object.assign(n,candidate);return n;
  }
  function commitEdits(owner,target,values,variables,specs) {
    const n=node(owner,target),params=clone(n.params),draft=clone(n.draft),data=clone(n.variableState);
    for(const v of variables) {
      if(v.origin==='parameter')params[v.param]=draft[v.param]=clone(values[v.id]);
      else { data.values[v.id]=clone(values[v.id]);data.draft[v.id]=clone(values[v.id]); }
    }
    for(const spec of specs)if(spec.id in draft)params[spec.id]=clone(draft[spec.id]);
    Object.assign(n,{params,draft,variableState:data});return n;
  }
  function setVariableDraft(owner,target,variable,source,value) {
    const n=node(owner,target),candidate=clone(value);
    if(source<0 && variable.origin==='parameter')return setDraft(owner,n,{[variable.param]:candidate});
    const data=n.variableState;
    if(source<0)data.draft[variable.id]=candidate;else data.banks[source][variable.id]=candidate;
    return n;
  }
  function addProject(state,owner) {
    if(state.projects.length>=20)throw Error('最多保存 20 个项目');
    if(state.projects.some(p=>p.id===owner.id))throw Error('项目标识重复');
    state.projects.push(owner);return owner;
  }
  function removeProject(state,id) {
    const next=state.projects.filter(p=>p.id!==id);
    if(!next.length)throw Error('至少保留一个项目');
    state.projects=next;state.charts.extra=state.charts.extra.filter(c=>c.projectId!==id);
    if(state.activeProject===id)state.activeProject=next[0].id;
  }
  function addCanvas(owner,page) {
    if(owner.pages.length>=8)throw Error('每个项目最多八张画布');
    if(owner.pages.some(p=>p.id===page.id))throw Error('画布标识重复');
    owner.pages.push(page);owner.activePage=page.id;return page;
  }
  function addNode(owner,pageId,value) {
    const page=owner.pages.find(p=>p.id===pageId);
    if(!page || page.nodes.length>=64)throw Error('目标画布不存在或已达到设备上限。');
    if(owner.pages.some(p=>p.nodes.some(n=>n.id===value.id)))throw Error('设备标识重复');
    page.nodes.push(value);return value;
  }
  function connect(owner,id,source,target,definition,replacing=false) {
    return links.connect(owner,id,source,target,definition,replacing);
  }
  function moveNode(owner,id,pageId) { return links.move(owner,id,pageId); }
  function removeNodes(owner,ids) { return links.removeNodes(owner,ids); }
  function removeConnection(owner,id) { return links.remove(owner,id); }
  function canvasSnapshot(owner,charts,view) {
    return clone({projectId:owner.id,pages:owner.pages,activePage:owner.activePage,thermalCouplings:owner.thermalCouplings,
      charts:charts.filter(c=>c.projectId===owner.id),workbenchChart:view.workbenchChart,showChart:view.showChart});
  }
  function restoreCanvas(owner,snapshot,charts) {
    if(snapshot.projectId!==owner.id)throw Error('撤销记录属于另一个项目');
    const next=clone(snapshot);
    Object.assign(owner,{pages:next.pages,activePage:next.activePage});
    if('thermalCouplings' in next)owner.thermalCouplings=next.thermalCouplings;else delete owner.thermalCouplings;
    return charts.filter(c=>c.projectId!==owner.id).concat(next.charts);
  }
  function mergeDocument(current,document,emptyRun,receipt) {
    const next=clone(current),p=clone(document.project);
    p.moduleSnapshots={...Object.fromEntries(document.modules.map(m=>[m.id,clone(m)])),...(p.moduleSnapshots||{})};
    p.run=emptyRun();
    const index=next.projects.findIndex(item=>item.id===p.id);
    if(index<0)addProject(next,p);else next.projects[index]=p;
    for(const field of ['modules','models']) {
      const ids=new Set(next[field].map(m=>m.id));next[field].push(...clone(document[field].filter(m=>!ids.has(m.id))));
    }
    next.charts.extra=next.charts.extra.filter(c=>c.projectId!==p.id).concat(clone(document.charts));
    next.activeProject=p.id;
    if(receipt){next.projectRevisions||={};next.projectRevisions[p.id]=receipt.revision;}
    return next;
  }
  function replaceWorkspace(data,{get,set,validate,normalize}) {
    const incoming=clone(data),previous=get();
    validate(incoming);
    try {set(incoming);normalize();}catch(error){set(previous);throw error;}
    return incoming;
  }
  return {assertCurrent,node,markDirty,setDraft,applyParameters,updateNode,commitEdits,setVariableDraft,
    addProject,removeProject,addCanvas,addNode,connect,moveNode,removeNodes,removeConnection,
    canvasSnapshot,restoreCanvas,mergeDocument,replaceWorkspace};
})();
