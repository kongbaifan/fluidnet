import {FluidNetPerformanceData} from './performance-library.js';
import {FluidNetProjectModel} from './project-model.js';
import {FluidNetProjectState} from './project-state.js';
/* Selection proposals use the device's frozen definition and never apply runtime parameters. */
export const EquipmentSelection = (() => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const model = () => FluidNetProjectModel;
  const supported = definition => definition?.runtime === 'python' && typeof definition.source?.design === 'string' && !!definition.source.design.trim();
  const defaults = (definition, draft) => Object.fromEntries(definition.parameters.map(p => [p.id,
    clone(draft[p.id] === undefined ? model().toDisplay(p,p.default) : draft[p.id])]));
  function readInputs(definition, data) {
    const values = {};
    for (const spec of definition.parameters) {
      const raw = data['selection:'+spec.id];
      let value;
      if (spec.value_type === 'boolean') value = raw === 'true';
      else if (spec.value_type === 'curve') {
        try { value = JSON.parse(raw); } catch { throw Error(spec.label+' 必须是 JSON 点对数组。'); }
        if (!Array.isArray(value) || !value.every(row => Array.isArray(row) && row.length===2 && row.every(Number.isFinite))) throw Error(spec.label+' 必须是有限数值点对数组。');
      } else if (spec.value_type === 'text') value = String(raw ?? '');
      else {
        if (raw === undefined || !String(raw).trim() || !Number.isFinite(Number(raw))) throw Error(spec.label+' 必须是有限数值。');
        value = Number(raw);
        const canonical = model().toCanonical(spec,value);
        if (spec.minimum != null && canonical < spec.minimum || spec.maximum != null && canonical > spec.maximum) throw Error(spec.label+' 超出模块声明范围。');
      }
      values[spec.id] = value;
    }
    return values;
  }
  function proposal(definition, parameters) {
    if (definition.parameters.some(p => !(p.id in parameters))) throw Error('设计结果缺少声明参数。');
    return Object.fromEntries(definition.parameters.map(p => [p.id,model().toDisplay(p,parameters[p.id])]));
  }
  function fingerprint(owner,node,definition) {
    return JSON.stringify({params:node.params,draft:node.draft,definition,fluid:owner.fluid,
      fluidConfig:owner.fluidConfig,fluidReference:owner.fluidReference,circuitFluids:owner.circuitFluids,performanceData:node.performanceData,performanceDataDraft:node.performanceDataDraft});
  }
  function assertModelCompatible(item,definition) {
    const entries=Object.values(item?.performanceData||item?.selection?.performanceData||{});
    if(entries.some(entry=>item.moduleId!==definition.id||item.moduleVersion!==definition.version||entry.definitionHash!==definition.definition_hash||entry.contentHash!==definition.content_hash))
      throw Error('性能资料型号绑定的模块版本与目标设备不同，请使用相同版本或重新导入资料。');
    if (!item?.selection) return;
    if (item.moduleId!==definition.id || item.moduleVersion!==definition.version ||
        item.selection.definitionHash && item.selection.definitionHash!==definition.definition_hash ||
        item.selection.contentHash && item.selection.contentHash!==definition.content_hash)
      throw Error('选型型号绑定的模块版本与目标设备不同，请使用相同版本或重新选型。');
  }
  function assertCurrent(state,owner,node,definition,before) {
    FluidNetProjectState.assertCurrent(state,owner);
    FluidNetProjectState.node(owner,node);
    if (state.activeProject !== owner.id || fingerprint(owner,node,definition)!==before) throw Error('设备、草稿或工质已变化，请重新计算选型方案。');
  }
  function create(deps) {
    const {esc,openDialog,instance,moduleOf,ownerOfInstance,engine,getState,uid,markDirty,persist,renderFloats,msg}=deps;
    let serial=0;
    const text = value => typeof value==='object' ? JSON.stringify(value) : String(value);
    function fields(definition,values) {
      const renderItems=items=>items.map(p => {
        const name='selection:'+p.id, value=values[p.id];
        const attrs=`name="${esc(name)}" aria-label="${esc(p.label)}"`;
        const input=p.value_type==='boolean' ? `<select ${attrs}><option value="true" ${value===true?'selected':''}>是</option><option value="false" ${value===false?'selected':''}>否</option></select>`
          :p.value_type==='curve'?`<textarea ${attrs} rows="3" required>${esc(text(value))}</textarea>`
          :`<input ${attrs} type="${p.value_type==='text'?'text':'number'}" step="any" value="${esc(value)}" ${p.value_type==='text'?'':'required'}>`;
        return `<label class="field"><span>${esc(p.label)}${p.unit?' · '+esc(p.unit.display_unit):''}</span>${input}</label>`;
      }).join('');
      const targets=definition.parameters.filter(p=>p.id.startsWith('design_'));
      const performance=definition.parameters.filter(p=>!p.id.startsWith('design_'));
      return `<fieldset><legend>设计目标与参考条件</legend>${renderItems(targets)}</fieldset><fieldset><legend>性能数据与待求运行设置</legend>${renderItems(performance)}</fieldset>`;
    }
    function provenance(id){
      const node=instance(id),item=node&&getState().models.find(m=>m.id===(node.draftModelId||node.modelId));
      if(!node)return;
      const definition=engine.manifestPayload(moduleOf(node)),api=FluidNetPerformanceData;
      const current=api?.references(node,definition,node.params,'current')||{},draft=api?.references(node,definition,node.draft)||{};
      const data={当前参数资料:current,草稿资料:draft,保存型号时的来源:item?.selection||item?.performanceData||null};
      openDialog('型号设计资料',`${node.id} · ${item?.name||'自定义参数'} · 模块v${definition.version}`,`<p>当前与草稿仅列出曲线及参考条件仍一致的资料。型号来源为保存时的记录。</p><pre class="code-preview">${esc(JSON.stringify(data,null,2))}</pre>`,null,'',true);
    }
    function geometry(id){
      const node=instance(id),owner=ownerOfInstance(node),module=moduleOf(node),definition=engine.manifestPayload(module);
      const specs=definition.parameters||[],prefix=specs.some(p=>p.id==='air_side_ua_w_k')?'':specs.some(p=>p.id==='Coil_air_side_ua_w_k')?'Coil_':null;
      if(prefix===null){openDialog('盘管几何设计',node.name,'<p>此入口适用于实际water_coil水盘管及公开Coil参数的AHU/FAHU/FCU。</p>');return;}
      const fields=[['tube_inner_diameter_m','管内径 m',.01],['tube_outer_diameter_m','管外径 m',.012],['tube_length_m','单管长度 m',1],['parallel_tubes','并联管数',20],['face_width_m','迎风宽度 m',.6],['face_height_m','迎风高度 m',.5],['fins','翅片数量',100],['fin_thickness_m','翅片厚度 m',.0001],['fin_efficiency','翅片效率',.8],['air_film_w_m2_k','空气膜系数 W/(m² K)',30],['water_film_w_m2_k','水膜系数 W/(m² K)',1500],['wall_conductivity_w_m_k','壁导热率 W/(m K)',200],['air_free_area_m2','净通风面积 m²',.2],['air_loss_coefficient','风侧局部K',3],['water_darcy_friction_factor','水侧Darcy摩阻因子',.03],['water_minor_loss_coefficient','水侧局部K',2]];
      const before=fingerprint(owner,node,definition),token=String(++serial),active=()=>document.querySelector(`[data-selection-token="${token}"]`);
      openDialog('盘管几何设计 · '+node.id,'干盘管设计点；系数必须填写来源，输出映射到现有水盘管参数。',`<div data-selection-token="${token}" class="fields">${fields.map(([key,label,value])=>`<label class="field"><span>${label}</span><input type="number" step="any" name="${key}" value="${value}" required></label>`).join('')}<label class="field"><span>系数来源/适用工况</span><input name="source" value="教学指定系数，未经厂家标定" required></label></div>`,data=>{
        assertCurrent(getState(),owner,node,engine.manifestPayload(moduleOf(node)),before);
        const inputs=Object.fromEntries(fields.map(([key])=>[key,Number(data[key])]));inputs.source=data.source;
        openDialog('正在计算盘管几何',node.name,`<p data-selection-token="${token}">正在计算面积、热阻和流通面积…</p>`);
        engine.request('/equipment-library/coil-geometry',inputs).then(result=>{
          if(!active())return;assertCurrent(getState(),owner,node,engine.manifestPayload(moduleOf(node)),before);
          const proposed={};for(const [key,value] of Object.entries(result.parameters)){
            const spec=specs.find(p=>p.id===prefix+key);if(!spec)throw Error('设备未公开盘管参数 '+key);
            proposed[spec.id]=model().toDisplay(spec,value);
          }
          openDialog('盘管几何方案预览',node.name,`<div data-selection-token="${token}"><p>有效总UA ${esc(result.effective_ua_w_k)} W/K</p><pre class="code-preview">${esc(JSON.stringify({parameters:result.parameters,areas:result.areas,source:result.source},null,2))}</pre><ul>${result.assumptions.map(t=>`<li>${esc(t)}</li>`).join('')}</ul><p>保存只进入草稿；运行前仍须确认应用，并检查实际工质和工况。</p></div>`,()=>{
            assertCurrent(getState(),owner,node,engine.manifestPayload(moduleOf(node)),before);
            FluidNetProjectState.setDraft(owner,node,proposed);
            node.geometryDesign={inputs,result,definitionHash:definition.definition_hash||null};markDirty(owner);persist();renderFloats();msg('盘管几何方案已填入草稿，请确认应用。');
          },'填入设备草稿',true);
        }).catch(e=>{if(active())openDialog('盘管几何计算未完成',node.name,`<p>${esc(e.message)}</p>`);});
      },'计算几何方案',true);
    }
    function open(id) {
      const node=instance(id);if(!node)return;
      const owner=ownerOfInstance(node),definition=engine.manifestPayload(moduleOf(node));
      if(!supported(definition)) {
        openDialog('设备选型',`${node.id} · ${node.name}`,'<p>此设备的绑定版本尚未提供设计函数。可在模块开发中编写 design.py，声明设计条件参数，发布后显式升级项目模块。</p>');return;
      }
      const before=fingerprint(owner,node,definition),token=String(++serial);
      const fluids=[{label:'项目工质 · '+owner.fluid,config:{...(owner.fluidConfig||{}),fluid:owner.fluid,reference:owner.fluidReference||'mass'}},
        ...(owner.circuitFluids||[]).map(c=>({label:c.id+' · '+c.fluid,config:{...(c.fluidConfig||{}),fluid:c.fluid,reference:c.fluidReference||'mass'}}))];
      const assert=()=>assertCurrent(getState(),owner,node,engine.manifestPayload(moduleOf(node)),before);
      const active=()=>document.querySelector(`[data-selection-token="${token}"]`);
      function form(values=defaults(definition,node.draft),fluidIndex='0',error='') {
        openDialog('设备选型 · '+node.id,`${definition.name} · 绑定版本 v${definition.version}。填写设计条件后计算方案，确认应用才改变设备运行设置。`,
          `<div data-selection-token="${token}">${error?`<p class="notice" role="alert">${esc(error)}</p>`:''}<label class="field"><span>设计工质</span><select name="selection-fluid" aria-label="设计工质">${fluids.map((f,i)=>`<option value="${i}" ${String(i)===fluidIndex?'selected':''}>${esc(f.label)}</option>`).join('')}</select></label><p class="muted">选择本次设计所用工质；所有输入来自当前绑定模块的参数合同。</p><div class="fields">${fields(definition,values)}</div></div>`,data=>{
            assert();const inputs=readInputs(definition,data),index=data['selection-fluid'];
            if(!fluids[index])throw Error('请选择有效设计工质。');
            openDialog('正在计算选型方案',node.name,`<p data-selection-token="${token}" role="status">正在执行绑定版本的设计函数…</p>`);
            engine.request('/modules/design',{module:clone(definition),parameters:model().canonicalParameters(definition,inputs),fluid:clone(fluids[index].config)})
              .then(result=>{
                if(!active())return;assert();
                const params=proposal(definition,result.parameters),state=getState();
                const rows=definition.parameters.map(p=>`<tr><td>${esc(p.label)}</td><td>${esc(text(node.params[p.id]))}</td><td>${esc(text(inputs[p.id]))}</td><td>${esc(text(params[p.id]))}</td><td>${esc(p.unit?.display_unit||'')}</td></tr>`).join('');
                openDialog('选型结果预览 · '+node.id,`${definition.name} v${definition.version} · ${fluids[index].label}。选择保存方式；结果先进入设备草稿。`,
                  `<div data-selection-token="${token}"><div class="table-wrap"><table><thead><tr><th>参数</th><th>已应用</th><th>设计输入</th><th>设计结果</th><th>单位</th></tr></thead><tbody>${rows}</tbody></table></div>${result.diagnostics?.length?`<pre class="code-preview">${esc(result.diagnostics.map(d=>d.message).join('\n'))}</pre>`:''}<label class="field"><span>保存方式</span><select name="selection-destination" aria-label="保存方式"><option value="model">保存型号并填入设备草稿</option><option value="draft">仅填入设备草稿</option></select></label><label class="field"><span>型号名称</span><input name="selection-name" aria-label="型号名称" maxlength="60" value="${esc(node.name+' · 选型方案 '+(state.models.length+1))}"></label></div>`,data=>{
                    assert();let item;
                    if(!['model','draft'].includes(data['selection-destination']))throw Error('请选择保存方式。');
                    if(data['selection-destination']==='model') {
                      const name=data['selection-name'].trim();if(!name)throw Error('请输入型号名称。');
                      if(state.models.length>=500)throw Error('已达到型号数量上限。');
                      if(state.models.some(m=>m.moduleId===definition.id&&m.name===name))throw Error('同一模块已有此型号名称。');
                      const values=Object.fromEntries(Object.entries(params).map(([key,value])=>['param:'+key,clone(value)]));
                      const note=`设备选型 · ${node.id} · ${fluids[index].label}`;
                      item={id:uid('model'),moduleId:definition.id,moduleVersion:definition.version,name,description:note,sourceLabel:note,
                        version:1,params:clone(params),values,bank:1,archived:false,
                        selection:{designHash:result.design_hash,definitionHash:definition.definition_hash||null,contentHash:definition.content_hash||null,
                          fluid:clone(fluids[index].config),inputs:model().canonicalParameters(definition,inputs),performanceData:FluidNetPerformanceData?.references(node,definition,inputs)||{}},
                        versions:[{version:1,note,params:clone(params),values:clone(values)}]};
                    }
                    FluidNetProjectState.setDraft(owner,node,params);
                    FluidNetProjectState.updateNode(owner,node,{draftModelId:item?.id||null,draftModelVersion:item?.version||null});
                    if(item){state.models.push(item);state.selectedModel=item.id;}
                    markDirty(owner);persist();renderFloats();msg(item?'选型型号已保存，结果已填入设备草稿。确认应用后生效。':'选型结果已填入设备草稿。确认应用后生效。');
                  },'保存方案',true);
              }).catch(error=>{if(active())form(inputs,index,'选型未完成：'+error.message);});
          },'计算选型',true);
      }
      form();
    }
    return {open,provenance,geometry};
  }
  return {supported,defaults,readInputs,proposal,fingerprint,assertCurrent,assertModelCompatible,create};
})();

export default EquipmentSelection;
