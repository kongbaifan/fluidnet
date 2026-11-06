/* Curated editable systems and frozen groups, fetched through public project validation. */
window.createEquipmentLibrary = ({engine,getState,replaceState,emptyRun,uid,openDialog,esc,msg,navigate,persist,dirty}) => {
  let ticket=0;
  async function open(){
    const token=++ticket,catalog=await engine.request('/equipment-library');
    openDialog('设备组与选型参考库','设备组固定子版本；参考系统创建独立可编辑项目，边界和控制显式保留。',
      `<div class="fields"><label class="field"><span>设备组或模板</span><select name="library-name" aria-label="设备组模板">${catalog.items.map(i=>`<option value="${esc(i.id)}">${esc(i.name)} · ${esc(i.kind)}</option>`).join('')}</select></label><label class="field"><span>实例前缀</span><input name="library-prefix" aria-label="实例前缀" value="Own" required pattern="[A-Za-z][A-Za-z0-9_-]{0,15}"></label><label class="field"><span>库房数量（仅泵供液库房模板）</span><input name="library-rooms" type="number" min="1" max="4" value="1"></label><label class="field"><span>压缩机数量（仅泵供液库房模板）</span><input name="library-compressors" type="number" min="1" max="4" value="1"></label></div><details><summary>适用条件与边界</summary>${catalog.items.map(i=>`<p><strong>${esc(i.name)}</strong>：${esc(i.assumptions)}</p>`).join('')}</details>`,data=>{
        const owner=getState();
        engine.request('/equipment-library/project',{name:data['library-name'],prefix:data['library-prefix'],room_count:Number(data['library-rooms']),compressor_count:Number(data['library-compressors'])})
          .then(p=>engine.exchangeDocument(p)).then(doc=>{
            if(token!==ticket||getState()!==owner)throw Error('工作区已变化，请重新创建参考项目');
            doc.project.id=uid('project');doc.project.solver.duration=1;doc.project.solver.dt=.1;
            const next=window.FluidNetProjectState.mergeDocument(owner,doc,emptyRun);
            replaceState(next);dirty();persist();navigate('workbench');msg('设备组参考项目已创建，可修改参数或从模块库插入更多副本。');
          }).catch(e=>msg(e.message,true));
      },'创建参考项目',true);
  }
  return {open};
};
