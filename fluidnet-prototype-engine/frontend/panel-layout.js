/* Presentation settings are independent of executable module contracts and hashes. */
export const FluidNetPanelLayout = (() => {
  const clone=value=>JSON.parse(JSON.stringify(value));
  function binding(m) {
    const d=m.manifest;
    return {id:m.id,version:d?.version||m.version||1,contentHash:d?.content_hash||null,
      definitionHash:d?.definition_hash||null,fields:JSON.stringify({
        parameters:d?.parameters?.map(p=>[p.id,p.value_type,p.unit,p.minimum,p.maximum,p.runtime,p.writable])||m.parameterDefs?.map(p=>p.slice(0,6))||[],
        variables:(m.variables||[]).filter(v=>['parameter','runtime','port'].includes(v.origin)).map(v=>[v.id,v.param,v.unit,v.canonicalId])})};
  }
  const results=m=>(m.variables||[]).filter(v=>v.origin==='runtime'||v.origin==='port'&&/:(FLOW|PRE|TEMP|ENTHALPY|VOLUME|Q)$/.test(v.id));
  function widgets(spec){
    const type=spec.value_type||'number';
    if(type==='number')return ['number',...(Number.isFinite(spec.minimum)&&Number.isFinite(spec.maximum)&&spec.minimum<spec.maximum?['slider']:[]),
      ...(spec.minimum===0&&spec.maximum===1?['switch']:[]),'display'];
    return type==='boolean'?['switch','display']:type==='curve'?['curve','display']:['text','display'];
  }
  function validate(layout,m,specs) {
    if(!layout||layout.schema!==1||JSON.stringify(layout.binding)!==JSON.stringify(binding(m)))throw Error('面板配置绑定的模块版本或字段已变化，请重新配置。');
    for(const [key,items] of [['parameters',specs],['results',results(m)]]) {
      const rows=layout[key];
      if(!Array.isArray(rows)||rows.length>160||new Set(rows.map(r=>r.id)).size!==rows.length)throw Error('面板字段重复或数量超限。');
      for(const row of rows){
        const item=items.find(p=>p.id===row.id);
        if(!item||typeof row.group!=='string'||row.group.length>40||!Number.isInteger(row.order)||row.order<0||row.order>999)throw Error('面板字段或分组不合法。');
        if(key==='parameters'&&!widgets(item).includes(row.widget))throw Error('面板控件不适合该参数类型或范围。');
      }
    }
    if(layout.parameters.length>12||layout.results.length>12)throw Error('总览最多配置12个常用参数和12个结果。');
    return clone(layout);
  }
  function resolved(m,specs) {
    if(!m.panelLayout)return {layout:null,warning:''};
    try{return {layout:validate(m.panelLayout,m,specs),warning:''};}
    catch{return {layout:null,warning:'面板配置与当前模块版本或字段不兼容，已显示默认面板。请重新配置。'};}
  }
  function groups(rows){
    const out=[];
    for(const row of [...rows].sort((a,b)=>a.order-b.order)){
      let group=out.find(g=>g.name===row.group);if(!group){group={name:row.group,items:[]};out.push(group);}group.items.push(row);
    }
    return out;
  }
  function copy(source,target){
    if(source?.panelLayout&&JSON.stringify(source.panelLayout.binding)===JSON.stringify(binding(target)))target.panelLayout=clone(source.panelLayout);
    return target;
  }
  function editor({m,specs,esc,openDialog,onSave}){
    const prior=resolved(m,specs),saved=prior.layout;
    const defaults=specs.slice(0,1).map((p,i)=>({id:p.id,widget:widgets(p)[0],group:'常用操作',order:i}));
    const selected={parameters:saved?.parameters??defaults,results:saved?.results??results(m).slice(0,4).map((v,i)=>({id:v.id,group:'运行结果',order:i}))};
    const rows=(key,items)=>items.map((p,i)=>{
      const row=selected[key].find(r=>r.id===p.id),base=`layout:${key}:${i}`;
      return `<tr data-panel-config-row="${esc(p.id)}"><td><label><input type="checkbox" name="${base}:show" aria-label="显示 ${esc(p.label)}" ${row?'checked':''}>${esc(p.label)}<small class="mono">${esc(p.id)}</small></label></td><td>${key==='parameters'?`<select name="${base}:widget" aria-label="${esc(p.label)}控件">${widgets(p).map(w=>`<option value="${w}" ${w===row?.widget?'selected':''}>${{number:'数值框',slider:'滑块＋数值',switch:'开关',text:'文本框',curve:'曲线JSON',display:'只读显示'}[w]}</option>`).join('')}</select>`:esc(p.unit||'')}</td><td><input name="${base}:group" aria-label="${esc(p.label)}分组" value="${esc(row?.group||(key==='parameters'?'常用操作':'运行结果'))}" maxlength="40"></td><td><input type="number" name="${base}:order" aria-label="${esc(p.label)}顺序" value="${row?.order??i}" min="0" max="999" step="1" required style="width:72px"></td></tr>`;
    }).join('');
    openDialog('配置设备面板',`${m.name} · v${m.version}。只配置显示顺序与控件，参数单位、写入权限仍由模块合同决定。`,
      `<div data-panel-config><p>${esc(prior.warning||'勾选总览常用字段，顺序从小到大；完整参数仍可在“参数与型号”页查看。')}</p><label class="check-label"><input type="checkbox" name="layout:reset">恢复默认布局</label>${[['parameters','常用参数',specs],['results','结果与读数',results(m)]].map(([key,label,items])=>`<h3>${label}</h3><div class="table-wrap"><table><thead><tr><th>字段</th><th>控件 / 单位</th><th>分组</th><th>顺序</th></tr></thead><tbody>${rows(key,items)}</tbody></table></div>`).join('')}</div>`,data=>{
        if(data['layout:reset']){onSave(null);return;}
        const value={schema:1,binding:binding(m),parameters:[],results:[]};
        for(const [key,items] of [['parameters',specs],['results',results(m)]])items.forEach((p,i)=>{
          const base=`layout:${key}:${i}`;if(!data[base+':show'])return;
          value[key].push({id:p.id,group:String(data[base+':group']).trim(),order:Number(data[base+':order']),...(key==='parameters'?{widget:data[base+':widget']}:{})});
        });
        onSave(validate(value,m,specs));
      },'保存面板配置',true);
  }
  return {binding,results,widgets,validate,resolved,groups,copy,editor};
})();

export default FluidNetPanelLayout;
