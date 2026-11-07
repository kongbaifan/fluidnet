/* Browser draft persistence is separate from project data and server confirmation. */
export const FluidNetWorkspaceStorage = (() => {
  const clone=value=>JSON.parse(JSON.stringify(value));
  const LOCAL_DRAFT_STEPS=[[200,null],[200,5],[200,1],[50,0]];
function isQuotaError(error){
  if(!error)return false;
  const name=String(error.name||''), message=String(error.message||'');
  return /quota/i.test(name)||name==='NS_ERROR_DOM_QUOTA_REACHED'||error.code===22||error.code===1014
    ||/quota|exceeded the quota|storage space|存储空间/i.test(message);
}
// 在“仅用于存储”的副本上裁剪运行历史：每次运行保留最近 frames 帧，运行快照保留最近 records 条
// （null 表示不裁剪快照）。只改副本；返回是否真的裁掉了内容。
function trimDraft(draft,frames,records){
  let trimmed=false;
  const trim=run=>{if(!run||!Array.isArray(run.history)||run.history.length<=frames)return;run.history=run.history.slice(-frames);trimmed=true;};
  for(const p of draft.projects||[])trim(p.run);
  trim(draft.bench?.run);
  if(Array.isArray(draft.records)){
    if(records!==null&&draft.records.length>records){draft.records=draft.records.slice(0,records);trimmed=true;}
    for(const record of draft.records)trim(record);
  }
  return trimmed;
}
// Only compact a replaceable cache after the server confirms every local frame
// is durable. Explicit RECORD-* snapshots and unsaved bench results are untouched.
function compactArchivedDraft(draft,frames){
  let changed=false;
  for(const owner of draft.projects||[]){
    const run=owner.run,cache=run?.archiveCache,history=run?.history;
    if(run?.source!=='engine'||typeof run.id!=='string'||!run.id
      ||typeof cache?.persisted_at!=='string'||!cache.persisted_at.trim()||cache.id!==run.id
      ||!Array.isArray(history)||!Number.isInteger(cache.rows)||cache.rows<=0||cache.rows<history.length
      ||!Number.isFinite(cache.time_s)||history.some(row=>!Number.isFinite(row.t)||row.t>cache.time_s))continue;
    const tail=history.slice(-frames),full=history.findLast(row=>row.partial!==true);
    if(full&&!tail.includes(full))tail.unshift(full);
    if(tail.length>=history.length)continue;
    run.history=tail;changed=true;
  }
  return changed;
}
function* draftTexts(source){
  let last=JSON.stringify(source);
  yield {frames:null,text:last};
  const cached=clone(source);
  for(const frames of [8,1]){
    if(!compactArchivedDraft(cached,frames))continue;
    const text=JSON.stringify(cached);
    last=text;
    yield {frames,text,archivedOnly:true};
  }
  // Keep the existing visible fallback for older, non-persistent workspaces.
  const draft=clone(source);
  for(const step of LOCAL_DRAFT_STEPS){
    if(!trimDraft(draft,step[0],step[1]))continue;
    const text=JSON.stringify(draft);
    if(text===last)continue;
    last=text;
    yield {frames:step[0],text};
  }
}
  function create({read,write,definitions,validate,normalize,projectState,model,storage,key,draftStore,ready,save,revision,status,changed,message,resetView,render,updateWindows,pending}) {
    let saving=false;
    function fail(text){const repeat=status().localError===text;changed({localError:text,trimmed:false});if(!repeat)message(text,true);return false;}
    function put(target,text){if(draftStore)draftStore.write(storage,target,text);else storage.setItem(target,text);}
    function persist(){
      try{for(const {frames,text,archivedOnly} of draftTexts(read())){
        try{put(key,text);}catch(error){if(isQuotaError(error))continue;return fail('本地草稿保存失败：'+(error.message||'浏览器拒绝写入')+'；内存数据仍在，请导出原型。');}
        if(frames===null){if(status().localError||status().trimmed)changed({localError:'',trimmed:false});return true;}
        const first=!status().trimmed;changed({localError:'',trimmed:true});
        if(first)message(archivedOnly?`浏览器草稿已保存；已归档运行仅缓存末个完整帧及最近 ${frames} 帧，完整结果可从服务端档案读取。`:`浏览器草稿已保存；存储空间不足，运行历史已裁剪为最近 ${frames} 帧，完整曲线仍在内存，请导出原型。`);
        return true;
      }return fail('本地草稿保存失败：存储空间不足，已保留内存数据，请导出原型后清理浏览器存储。');}
      catch(error){return fail('本地草稿保存失败：'+(error.message||'未知错误')+'；内存数据仍在，请导出原型。');}
    }
    function backup(target,source=read()){
      try{for(const {text} of draftTexts(source)){try{put(target,text);return true;}catch(error){if(isQuotaError(error))continue;throw Error('本地草稿备份失败：'+(error.message||'浏览器拒绝写入'));}}}
      catch(error){if(!/^本地草稿备份失败/.test(error.message||''))throw Error('本地草稿备份失败：'+(error.message||'未知错误')+'，请先导出原型再继续。');throw error;}
      throw Error('本地草稿备份失败：存储空间不足，请先导出原型再继续。');
    }
    async function saveAll(){
      if(saving)return;saving=true;let owner=read();changed({phase:'saving',error:''});
      try{await ready();owner=read();const version=revision(),payload=clone(owner);
        payload.dirty=false;payload.savedAt=new Date().toISOString();payload.projects.forEach(p=>p.dirty=false);payload.modules.forEach(m=>{if(m.runtime!=='python')m.dirty=false;});
        changed({phase:'saving'});persist();const receipt=await save(payload);
        if(read()!==owner)return;
        owner.workspaceRevision=receipt.revision;owner.savedAt=receipt.saved_at;
        if(revision()===version){owner.dirty=false;owner.projects.forEach(p=>p.dirty=false);owner.modules.forEach(m=>{if(m.runtime!=='python')m.dirty=false;});}
        persist();changed({phase:'saved'});updateWindows();message(`工作区已保存 · 修订 ${receipt.revision}${owner.dirty?' · 仍有后续修改未保存':''}${pending()?` · ${pending()} 项参数待应用`:''}`);
      }catch(error){if(read()===owner){changed({phase:'error',error:error.message});owner.dirty=true;persist();message('保存失败：'+error.message,true);}}
      finally{saving=false;if(status().phase==='saving')changed({phase:''});}
    }
    function replace(data,beforeReplace=()=>{},afterNormalize=()=>{}){
      const previous=read(),saved=clone(definitions);
      try{return projectState.replaceWorkspace(data,{get:read,set:write,validate:incoming=>{validate(incoming);beforeReplace();},normalize:()=>{normalize();afterNormalize(previous);}});}
      catch(error){for(const key of Object.keys(definitions))delete definitions[key];Object.assign(definitions,saved);throw error;}
    }
    function restore(data){replace(data,()=>{},previous=>{if(!model.workspaceContentEqual(previous,read()))backup(key+'-before-workspace',previous);});resetView();changed({phase:'',error:''});render();}
    return {persist,backup,saveAll,replace,restore,isSaving:()=>saving};
  }
  return {create,isQuotaError,trimDraft,compactArchivedDraft,draftTexts};
})();

export default FluidNetWorkspaceStorage;
