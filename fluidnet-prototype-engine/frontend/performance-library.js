import {EquipmentSelection} from './equipment-selection.js';
import {FluidNetProjectModel} from './project-model.js';
import {FluidNetProjectState} from './project-state.js';
/* Performance files are immutable library versions; adopting one only changes a device draft. */
export const FluidNetPerformanceData = (() => {
  const clone=v=>JSON.parse(JSON.stringify(v));
  function references(node,definition,displayParameters,source='draft'){
    const entries=Object.entries((source==='current'?node.performanceData:node.performanceDataDraft??node.performanceData)||{});
    if(!entries.length||!definition?.parameters)return {};
    const parameters=FluidNetProjectModel.canonicalParameters(definition,displayParameters),result={};
    for(const [key,entry] of entries){
      if(!key||!entry?.parameterValues||!entry.provenance||entry.definitionHash!==definition.definition_hash||entry.contentHash!==definition.content_hash)continue;
      if(Object.entries(entry.parameterValues).every(([id,v])=>JSON.stringify(parameters[id])===JSON.stringify(v)))result[key]=clone(entry);
    }
    return result;
  }
  const pending=node=>JSON.stringify(node.performanceDataDraft??node.performanceData??{})!==JSON.stringify(node.performanceData||{});
  const capture=(node,applyDraft=true)=>({current:clone(node.performanceData||{}),draft:clone((applyDraft?node.performanceDataDraft??node.performanceData:node.performanceData)||{}),applyDraft});
  function commit(node,definition,snapshot){
    const unchanged=JSON.stringify(node.performanceDataDraft??node.performanceData??{})===JSON.stringify(snapshot.draft);
    node.performanceData=references({performanceData:snapshot.draft},definition,node.params,'current');
    if(snapshot.applyDraft&&unchanged)delete node.performanceDataDraft;
  }
  function stage(owner,node,definition,proposal){
    FluidNetProjectState.node(owner,node);
    const draft={};
    for(const [key,v] of Object.entries(proposal.parameters)){
      const spec=definition.parameters.find(p=>p.id===key);
      if(!spec||spec.writable===false)throw Error('资料方案包含不可写参数：'+key);
      draft[key]=FluidNetProjectModel.toDisplay(spec,v);
    }
    const parameterValues=Object.fromEntries(Object.entries(proposal.parameters).filter(([key])=>key.endsWith('_curve')||key==='reference_density_kg_m3'));
    const entry={provenance:clone(proposal.provenance),parameterValues:clone(parameterValues),definitionHash:definition.definition_hash,contentHash:definition.content_hash};
    const map={...(node.performanceDataDraft??node.performanceData),[proposal.provenance.parameter_id||Object.keys(parameterValues)[0]]:entry};
    FluidNetProjectState.setDraft(owner,node,draft);node.performanceDataDraft=map;
    node.draftModelId=null;node.draftModelVersion=null;
  }
  function chart(records,esc){
    if(!records.length)return '';
    const maximumX=Math.max(1,...records.flatMap(r=>r.points_m3_h.map(p=>p[0]))),maximumY=Math.max(1,...records.flatMap(r=>r.points_m3_h.map(p=>p[1])));
    const paths=records.map((r,index)=>`<path d="${r.points_m3_h.map((p,i)=>`${i?'L':'M'}${45+500*p[0]/maximumX},${200-165*p[1]/maximumY}`).join(' ')}" fill="none" stroke="${index?'#bf650e':'#3786ad'}" stroke-width="2"/>`).join('');
    const ticks=[0,.25,.5,.75,1].map(t=>`<path d="M45 ${200-165*t}H545 M${45+500*t} 35V200" stroke="currentColor" opacity=".12"/><text x="38" y="${203-165*t}" text-anchor="end">${Number((maximumY*t).toPrecision(4))}</text><text x="${45+500*t}" y="214" text-anchor="middle">${Number((maximumX*t).toPrecision(4))}</text>`).join('');
    return `<svg viewBox="0 0 600 245" role="img" aria-label="规范单位性能曲线" style="width:100%;max-height:280px"><g fill="currentColor" font-size="10">${ticks}</g><path d="M45 20V200H550" fill="none" stroke="currentColor"/>${paths}<text x="50" y="15" fill="currentColor">${esc(records[0].canonical_value_unit)}</text><text x="420" y="238" fill="currentColor">Q m³/h</text></svg>`;
  }
  function create({engine,getState,project,instance,moduleOf,ownerOfInstance,openDialog,esc,msg,download,persist,dirty,renderFloats}){
    let serial=0;
    const kinds={pump_head:'泵扬程曲线',fan_pressure:'风机压升曲线',efficiency:'效率曲线'};
    const button=(action,text,attrs='')=>`<button type="button" class="btn small" data-performance-action="${action}" ${attrs}>${text}</button>`;
    const field=(name,label,value,attrs='')=>`<label class="field"><span>${label}</span><input name="${name}" value="${esc(value??'')}" ${attrs}></label>`;
    const pick=(name,label,choices,value)=>`<label class="field"><span>${label}</span><select name="${name}" aria-label="${label}">${choices.map(([id,label])=>`<option value="${id}" ${value===id?'selected':''}>${label}</option>`).join('')}</select></label>`;
    const active=token=>!!document.querySelector(`[data-performance-token="${token}"]`);
    function loading(token,title){openDialog(title,'',`<p data-performance-token="${token}">正在读取…</p>`);}
    async function open(targetId){
      const token=++serial;loading(token,'性能资料库');
      try{
        const list=await engine.request('/performance-data');if(!active(token))return;
        openDialog('性能资料库',targetId?'选择已保存版本，预览后填入设备草稿。':'导入用户提供的曲线，保留源文件、单位、适用范围和版本。',
          `<div data-performance-token="${token}">${list.persistent?'':'<p class="notice">当前服务未配置持久化目录，资料只在本次服务中保留。</p>'}<div class="row">${button('import','导入CSV / JSON')}${button('compare','比较两份资料')}</div>
          <div class="table-wrap"><table><thead><tr><th>资料 / 版本</th><th>类型</th><th>工质 / 参考转速</th><th>来源</th><th>操作</th></tr></thead><tbody>${list.items.map((r,i)=>`<tr data-performance-record="${esc(r.id)}" data-performance-version="${r.version}"><td>${esc(r.name)} · v${r.version}<small>${esc(r.manufacturer+' '+r.model_name)}</small></td><td>${esc(kinds[r.kind]||r.kind)}</td><td>${esc(r.reference_fluid)} · ${r.reference_speed_rpm} rpm</td><td>${esc(r.source)}</td><td>${button('view','查看',`data-index="${i}"`)}${button('version','导入新版本',`data-index="${i}"`)}${targetId?button('apply','用于此设备',`data-index="${i}"`):''}</td></tr>`).join('')||'<tr><td colspan="5">尚无资料，请导入有来源的曲线文件。</td></tr>'}</tbody></table></div></div>`,null,'',true);
        document.querySelector(`[data-performance-token="${token}"]`).addEventListener('click',e=>{
          const action=e.target.closest('[data-performance-action]');if(!action)return;
          const row=list.items[Number(action.dataset.index)];
          if(action.dataset.performanceAction==='import')importForm(targetId).catch(error=>msg(error.message,true));
          if(action.dataset.performanceAction==='view')view(row,targetId);
          if(action.dataset.performanceAction==='version')importForm(targetId,row,Math.max(...list.items.filter(x=>x.id===row.id).map(x=>x.version))).catch(error=>msg(error.message,true));
          if(action.dataset.performanceAction==='apply')apply(row,targetId).catch(error=>msg(error.message,true));
          if(action.dataset.performanceAction==='compare')compare(list.items,targetId);
        });
      }catch(e){if(active(token))openDialog('资料库读取失败','',`<p>${esc(e.message)}</p>`);}
    }
    async function importForm(targetId,previous,latest=0){
      const token=++serial;
      if(previous){loading(token,'读取上版资料声明');const record=await engine.request(`/performance-data/${encodeURIComponent(previous.id)}/versions/${previous.version}`);if(!active(token))return;previous=record.import_data;}
      const defaults=previous||{id:'user_curve',name:'用户性能曲线',kind:'pump_head',source:'用户提供的设计资料',reference_fluid:'Water',reference_density_kg_m3:998.2,reference_speed_rpm:1450};
      openDialog('导入性能资料',previous?`${previous.id} 将新增 v${latest+1}，旧版本保留。`:'CSV需恰有两列；JSON为点对数组或含points的对象。UTF-8，最多2MiB。',
        `<div data-performance-token="${token}"><label class="field"><span>曲线文件</span><input type="file" data-performance-file accept=".csv,.json" aria-label="性能曲线文件" required></label><div class="fields">
        ${field('id','资料标识',defaults.id,`required pattern="[A-Za-z][A-Za-z0-9_-]{0,79}" ${previous?'readonly':''}`)}${field('name','资料名称',defaults.name,'required')}
        ${pick('kind','资料类型',Object.entries(kinds),defaults.kind)}${pick('format','文件格式',[['csv','CSV'],['json','JSON']],defaults.format||'csv')}
        ${pick('flow_unit','源流量单位',[['m3/h','m³/h'],['m3/s','m³/s'],['L/s','L/s']],defaults.flow_unit||'m3/h')}
        ${pick('value_unit','源纵轴单位',[['m','m（扬程）'],['Pa','Pa'],['kPa','kPa'],['1','1（效率比）'],['%','%（效率）']],defaults.value_unit||(defaults.kind==='fan_pressure'?'Pa':defaults.kind==='efficiency'?'%':'m'))}
        ${field('flow_column','CSV流量列名',defaults.flow_column||'flow','required')}${field('value_column','CSV数值列名',defaults.value_column||'value','required')}
        ${field('source','资料来源及适用条件',defaults.source,'required maxlength="1000"')}${field('manufacturer','制造商（可留空）',defaults.manufacturer||'')}${field('model_name','设备型号（可留空）',defaults.model_name||'')}
        ${field('reference_fluid','参考工质',defaults.reference_fluid,'required')}${field('reference_density_kg_m3','参考密度 kg/m³',defaults.reference_density_kg_m3,'type="number" step="any" min="0.001" required')}
        ${field('reference_speed_rpm','参考转速 rpm',defaults.reference_speed_rpm,'type="number" step="any" min="0.001" required')}
        ${field('valid_flow_min','有效流量下限（源单位，留空取首点）',defaults.valid_flow_min,'type="number" step="any"')}${field('valid_flow_max','有效流量上限（源单位，留空取末点）',defaults.valid_flow_max,'type="number" step="any"')}
        </div></div>`,data=>{
          const file=document.querySelector('[data-performance-file]').files[0];if(!file)throw Error('请选择曲线文件');if(file.size>2*1024*1024)throw Error('文件超过2MiB');
          const payload={...data,file_name:file.name,expected_latest_version:latest};
          for(const key of ['reference_density_kg_m3','reference_speed_rpm'])payload[key]=Number(data[key]);
          for(const key of ['valid_flow_min','valid_flow_max'])payload[key]=data[key]===''?null:Number(data[key]);
          loading(token,'正在校验性能资料');
          file.arrayBuffer().then(buffer=>{
            const bytes=new Uint8Array(buffer);let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
            payload.content_base64=btoa(binary);return engine.request('/performance-data/preview',payload);
          }).then(result=>{if(active(token))preview(result,payload,targetId,token);})
            .catch(e=>{if(active(token))openDialog('资料校验未通过','原文件和已有版本保持原值',`<p role="alert">${esc(e.message)}</p>`);});
        },'校验与预览',true);
    }
    function preview(result,payload,targetId,token){
      openDialog('性能资料预览',`${result.name} · ${kinds[result.kind]}`,
        `<div data-performance-token="${token}">${chart([result],esc)}<p>规范流量 m³/h · 纵轴 ${esc(result.canonical_value_unit)} · 有效流量 ${esc(result.valid_flow_m3_h.join(' — '))}</p>
        <p>来源：${esc(payload.source)} · ${esc(payload.reference_fluid)} · ${payload.reference_speed_rpm} rpm</p>${result.warnings.map(w=>`<p class="notice">${esc(w)}</p>`).join('')}
        <pre class="code-preview">${esc(JSON.stringify({原始点:result.source_points,规范点:result.points_m3_h,原文件SHA256:result.source_hash},null,2))}</pre></div>`,()=>{
          loading(token,'保存不可变资料版本');engine.request('/performance-data/versions',payload).then(record=>{
            if(active(token)){msg(`性能资料 ${record.id} v${record.version} 已保存`);open(targetId);}
          }).catch(e=>{if(active(token))openDialog('资料未保存','',`<p>${esc(e.message)}</p>`);});
        },'保存资料版本',true);
    }
    async function view(row,targetId){
      const token=++serial;loading(token,'读取性能资料');
      try{const record=await engine.request(`/performance-data/${encodeURIComponent(row.id)}/versions/${row.version}`);if(!active(token))return;
        openDialog('性能资料 · '+record.name,`v${record.version} · ${kinds[record.kind]}`,
          `<div data-performance-token="${token}">${chart([record],esc)}<p>数据哈希 ${esc(record.content_hash)}</p><p>原文件哈希 ${esc(record.source_hash)}</p><pre class="code-preview">${esc(JSON.stringify({...record.import_data,content_base64:undefined},null,2))}</pre><div class="row">${button('export','导出原文件')}${button('back','返回资料库')}</div></div>`,null,'',true);
        document.querySelector(`[data-performance-token="${token}"]`).addEventListener('click',async e=>{
          if(e.target.closest('[data-performance-action="back"]'))open(targetId);
          if(e.target.closest('[data-performance-action="export"]'))try{
            const response=await fetch(`/api/v1/performance-data/${encodeURIComponent(row.id)}/versions/${row.version}/export`,{headers:engine.authHeaders()});
            if(!response.ok)throw Error('原文件导出失败');download(record.import_data.file_name,await response.blob());
          }catch(error){msg(error.message,true);}
        });
      }catch(e){if(active(token))openDialog('资料读取失败','',`<p>${esc(e.message)}</p>`);}
    }
    function compare(items,targetId){
      const token=++serial;const select=(key,label)=>`<label class="field"><span>${label}</span><select name="${key}">${items.map((r,i)=>`<option value="${i}">${esc(r.name)} v${r.version} · ${esc(kinds[r.kind])}</option>`).join('')}</select></label>`;
      openDialog('比较性能资料','只叠加相同类型的规范曲线，工质/密度/转速不同不等于同工况性能差异。',`<div data-performance-token="${token}" class="fields">${select('a','资料A')}${select('b','资料B')}</div>`,data=>{
        const a=items[Number(data.a)],b=items[Number(data.b)];if(!a||!b||a.kind!==b.kind)throw Error('请选择相同类型的两份资料');
        loading(token,'正在比较');engine.request('/performance-data/compare?'+new URLSearchParams({left_id:a.id,left_version:a.version,right_id:b.id,right_version:b.version})).then(result=>{
          const records=[result.left,result.right];
          if(active(token))openDialog('规范曲线对照','蓝色A / 橙色B；曲线保留各自参考密度和转速，不自动换算为相同工况。',
            `<div data-performance-comparison>${chart(records,esc)}${records.map((r,i)=>`<p>${i?'B':'A'}：${esc(r.name)} v${r.version} · ${esc(r.import_data.reference_fluid)} · ${r.import_data.reference_density_kg_m3} kg/m³ · ${r.import_data.reference_speed_rpm} rpm · ${esc(r.import_data.source)}</p>`).join('')}<p>${esc(result.reason)}</p>${result.comparable?`<div class="table-wrap"><table><thead><tr><th>Q m³/h</th><th>A</th><th>B</th><th>B − A</th></tr></thead><tbody>${result.samples.map(p=>`<tr><td>${p.flow_m3_h}</td><td>${p.left}</td><td>${p.right}</td><td>${p.difference} ${esc(p.value_unit)}</td></tr>`).join('')}</tbody></table></div>`:''}</div>`,null,'',true);
        }).catch(e=>{if(active(token))openDialog('对照未完成','',`<p>${esc(e.message)}</p>`);});
      },'比较',true);
    }
    async function apply(row,targetId){
      const node=instance(targetId);if(!node)throw Error('设备已不存在');
      const owner=ownerOfInstance(node),definition=engine.manifestPayload(moduleOf(node)),before=EquipmentSelection.fingerprint(owner,node,definition);
      const token=++serial,keys=definition.parameters.filter(p=>p.value_type==='curve'&&p.writable!==false);
      const fluids=[{label:'项目工质 · '+owner.fluid,config:{...(owner.fluidConfig||{}),fluid:owner.fluid,reference:owner.fluidReference||'mass'}},
        ...(owner.circuitFluids||[]).map(c=>({label:c.id+' · '+c.fluid,config:{...(c.fluidConfig||{}),fluid:c.fluid,reference:c.fluidReference||'mass'}}))];
      const assert=()=>EquipmentSelection.assertCurrent(getState(),owner,node,engine.manifestPayload(moduleOf(node)),before);
      openDialog('选择资料目标参数',`${node.id} · ${row.name} v${row.version}`,
        `<div data-performance-token="${token}">${pick('parameter','曲线参数',keys.map(p=>[p.id,esc(p.label)]),row.kind==='pump_head'?'head_curve':row.kind==='fan_pressure'?'pressure_curve':'efficiency_curve')}${pick('fluid','设备设计工质',fluids.map((f,i)=>[String(i),esc(f.label)]),'0')}<p>原曲线会显示在下一步差异预览中；这里只提交建议参数，不改变已应用值。</p></div>`,data=>{
          assert();if(!fluids[data.fluid])throw Error('请选择有效设计工质');loading(token,'检查曲线兼容性');engine.request('/performance-data/proposal',{id:row.id,version:row.version,module:definition,
            parameter_id:data.parameter,parameters:FluidNetProjectModel.canonicalParameters(definition,node.draft),
            references:Object.fromEntries(Object.entries(references(node,definition,node.draft)).map(([key,entry])=>[key,{id:entry.provenance.id,version:entry.provenance.version,content_hash:entry.provenance.content_hash}])),
            fluid:fluids[data.fluid].config}).then(result=>{
              if(!active(token))return;assert();
              const rows=Object.entries(result.parameters).map(([key,v])=>[key,node.draft[key],FluidNetProjectModel.toDisplay(definition.parameters.find(p=>p.id===key),v)]);
              openDialog('性能资料应用预览',`${node.id} · 仅填入待应用草稿，设计条件和实际运行工况仍需核对。`,
                `<div data-performance-token="${token}">${result.warnings.map(w=>`<p class="notice">${esc(w)}</p>`).join('')}<div class="table-wrap"><table><thead><tr><th>参数</th><th>已有草稿</th><th>资料方案</th></tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${esc(typeof v==='object'?JSON.stringify(v):v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p>资料来源：${esc(result.provenance.source)} · v${row.version}</p><label class="check-label"><input type="checkbox" data-performance-reference-confirm required>确认 ${result.provenance.reference_speed_rpm} rpm 为此曲线的 speed_ratio = 1 基准；当前草稿转速比为 ${esc(node.draft.speed_ratio)}，应用后重新选型。</label></div>`,()=>{
                  assert();stage(owner,node,definition,result);dirty(owner);persist();renderFloats();msg('性能资料已填入设备草稿，请预览并应用后再运行。');
                },'填入设备草稿',true);
            }).catch(e=>{if(active(token))openDialog('资料不能应用','已有设备参数保持原值',`<p role="alert">${esc(e.message)}</p>`);});
        },'预览应用',true);
    }
    return {open};
  }
  return {references,pending,capture,commit,stage,chart,create};
})();

export default FluidNetPerformanceData;
