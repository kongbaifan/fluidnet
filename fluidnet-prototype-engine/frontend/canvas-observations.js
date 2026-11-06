/* Read-only presentation of accepted engine frames. Nothing here writes a setting or infers a flow from an arrow. */
window.FluidNetCanvasObservations = (() => {
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const definition = module => module?.manifest || module || {};
  const ports = module => definition(module).ports || module?.ports || [];
  const canonical = row => row && !row.stale && row.valid !== false && row.accepted !== false
    ? row.canonical || (row.time_s !== undefined ? row.variables : null) : null;
  const valueAt = (values,key) => values && Object.hasOwn(values,key) && finite(values[key]) ? values[key] : null;
  const number = value => Number(value.toPrecision(5)).toString();
  const EPS = 1e-8;
  const MODES = {
    circuit: {min:0,max:5,unit:'kg/s',label:'回路',colors:['#2b7bba','#ba3d3d'],note:'颜色表示回路；箭头只表示已采样的真实质量流向。'},
    flow: {min:0,max:5,unit:'kg/s',label:'质量流量绝对值',colors:['#2b7bba','#ba3d3d'],note:'色谱与线宽按绝对值；标签正负相对于连接源端 → 目标端。'},
    temperature: {min:-30,max:80,unit:'°C',label:'端点温度',colors:['#2b7bba','#ba3d3d'],note:'采用有真实流量时的上游端点；无流向数据时注明采样端点。'},
    pressure: {min:0,max:1000,unit:'kPa(abs)',label:'端点绝对压力',colors:['#2b7bba','#ba3d3d'],note:'绝压，不是表压；采用有真实流量时的上游端点。'},
  };
  function legend(mode='circuit',scale) {
    const item=MODES[mode] || MODES.circuit;
    const min=finite(scale?.min)?scale.min:item.min,max=finite(scale?.max)?scale.max:item.max;
    return {...item,colors:[...item.colors],min:min<max?min:item.min,max:min<max?max:item.max,
      note:item.note+' 超出色谱范围时仅颜色截断，数值不截断；灰色表示未采样。'};
  }
  function color(value,range) {
    const t=Math.max(0,Math.min(1,(value-range.min)/(range.max-range.min)));
    const a=[43,123,186],b=[186,61,61];
    return {color:`rgb(${a.map((x,i)=>Math.round(x+(b[i]-x)*t)).join(', ')})`,ratio:t,
      outOfRange:value<range.min||value>range.max};
  }
  function portFlow(n,module,port,values) {
    const key=n.id+'.'+port.id+'.mass_flow_kg_s',direct=valueAt(values,key);
    if(direct!==null)return {value:direct,key};
    // Fluid channels have an explicit signed input -> output convention. A many-port
    // vessel, header or refrigeration group has no corresponding aggregate fallback.
    if((port.domain || 'fluid')!=='fluid')return null;
    const channels=(definition(module).channels || module?.channels || []).filter(c=>c.enabled!==false);
    const matches=channels.filter(c=>(c.input_port??c.input)===port.id||(c.output_port??c.output)===port.id);
    if(matches.length!==1)return null;
    const c=matches[0],prefix=n.id+'.'+c.id+'.mass_flow_kg_s';
    let flow=valueAt(values,prefix),source=prefix;
    if(flow===null && channels.length===1){source=n.id+'.mass_flow_kg_s';flow=valueAt(values,source);}
    return flow===null?null:{value:flow*((c.input_port??c.input)===port.id?1:-1),key:source};
  }
  function edge({edge:link,sourceNode,targetNode,sourceModule,targetModule,row,mode='circuit',scale}={}) {
    const range=legend(mode,scale),values=canonical(row);
    const result={known:false,value:null,unit:range.unit,label:'—',direction:null,flowKnown:false,massFlowKgS:null,
      color:null,width:1.8,outOfRange:false,reason:'尚无有效采样',sourceKey:null,targetKey:null,
      observationKey:null,time:finite(row?.t)?row.t:finite(row?.time_s)?row.time_s:null,partial:row?.partial===true||row?.full===false};
    if(!Array.isArray(link)||link.length!==5||!sourceNode||!targetNode||sourceNode.id!==link[1]||targetNode.id!==link[3])
      return {...result,reason:'连接端点不存在或已变化'};
    const a=ports(sourceModule).find(p=>p.id===link[2]),b=ports(targetModule).find(p=>p.id===link[4]);
    if(!a||!b||(a.domain || 'fluid')!==(b.domain || 'fluid'))return {...result,reason:'端口合同不兼容'};
    if(!['fluid','refrigerant'].includes(a.domain || 'fluid'))return {...result,reason:(a.domain==='thermal'
      ?'热连接尚无通用逐口热流符号合同，不推断热量方向':'此连接不是质量流动通路')};
    if(!values)return result;
    const left=portFlow(sourceNode,sourceModule,a,values),right=portFlow(targetNode,targetModule,b,values);
    let flow=left?-left.value:right?right.value:null;
    if(left&&right&&Math.abs(-left.value-right.value)>Math.max(EPS,Math.max(Math.abs(left.value),Math.abs(right.value))*1e-6)){
      flow=null;result.reason='两端质量流量不一致，不显示流向';
    }
    if(flow!==null){
      result.massFlowKgS=Math.abs(flow)<=EPS?0:flow;result.flowKnown=true;
      result.direction=result.massFlowKgS===0?0:result.massFlowKgS>0?1:-1;result.reason='';
    }
    result.sourceKey=left?.key||null;result.targetKey=right?.key||null;
    if(mode==='flow'||mode==='circuit'||!MODES[mode]){
      if(flow===null)return {...result,reason:left||right?result.reason:'此连接未采样质量流量'};
      result.value=result.massFlowKgS;result.known=true;
      result.label=number(result.value)+' kg/s';
      result.observationKey=left?.key||right?.key||null;
    }else{
      const suffix=mode==='temperature'?'temperature_k':'pressure_pa';
      const endpoints=[{key:sourceNode.id+'.'+a.id+'.'+suffix,location:'源端'},
        {key:targetNode.id+'.'+b.id+'.'+suffix,location:'目标端'}];
      if(result.direction===-1)endpoints.reverse();
      const selected=endpoints.find(p=>valueAt(values,p.key)!==null);
      if(!selected)return {...result,reason:'此连接未采样'+range.label};
      const raw=valueAt(values,selected.key);
      // The value belongs to an endpoint, never an invented average along the line.
      result.value=mode==='temperature'?raw-273.15:raw/1000;
      result.known=true;result.observationKey=selected.key;result.location=selected.location;
      result.label=selected.location+' '+number(result.value)+' '+range.unit;
      if(!result.reason || result.reason==='尚无有效采样')result.reason='';
    }
    if(mode!=='circuit' && MODES[mode]){
      const mapped=color(mode==='flow'?Math.abs(result.value):result.value,range);
      result.color=mapped.color;result.outOfRange=mapped.outOfRange;
      if(mode==='flow')result.width=1.8+mapped.ratio*3.2;
    }
    return result;
  }
  const STATES={unknown:['未知','#738292'],running:['运行','#26804a'],stopped:['停止','#738292'],
    defrost:['融霜','#bf650e'],drip:['滴水等待','#bf650e'],warning:['警告','#bf650e'],error:['故障','#ba3d3d']};
  function node({node:instance,module,row}={}) {
    const values=canonical(row),d=definition(module);
    const diagnostics=(row?.stale || row?.accepted===false ? [] : row?.diagnostics || []).filter(item=>item && item.instance_id===instance?.id)
      .map(item=>({...item}));
    const result={known:false,state:'unknown',label:STATES.unknown[0],color:STATES.unknown[1],diagnostics,
      observationKey:null,time:finite(row?.t)?row.t:finite(row?.time_s)?row.time_s:null,partial:row?.partial===true||row?.full===false};
    if(!instance)return result;
    const set=(state,key=null)=>({...result,known:state!=='unknown',state,label:STATES[state][0],color:STATES[state][1],observationKey:key});
    // A solver diagnostic is a real result even when the failure produced no valid physical frame.
    if(diagnostics.some(item=>item.severity==='error'))return set('error');
    if(diagnostics.some(item=>item.severity==='warning'))return set('warning');
    if(!values)return result;
    const declared=(d.variables || module?.variables || []).filter(v=>v.source!=='parameter'&&v.origin!=='parameter')
      .map(v=>v.canonicalId || v.id);
    const kind=d.solver_model || module?.kind || d.id;
    if(['unit_cooler','defrost_air_cooler'].includes(kind)){
      const key=instance.id+'.state.mode',value=valueAt(values,key);
      if(declared.includes('state.mode')&&value===1)return set('defrost',key);
      if(declared.includes('state.mode')&&value===2)return set('drip',key);
    }
    for(const key of ['is_running','actual_running','state.running']){
      if(!declared.includes(key))continue;
      const canonicalKey=instance.id+'.'+key,raw=values[canonicalKey];
      if(raw===true||raw===1)return set('running',canonicalKey);
      if(raw===false||raw===0)return set('stopped',canonicalKey);
    }
    // A fan's running flag does not imply that its cooling circuit is operating.
    return result;
  }
  return {edge,node,legend};
})();
