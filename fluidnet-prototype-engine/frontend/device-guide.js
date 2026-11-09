/* Curated help and default presentation for reviewed built-in devices.
 * These views never modify contracts, parameter values or saved panel layouts. */
export const FluidNetDeviceGuide = (() => {
  const guides={
    pump:{
      summary:'用扬程曲线和转速比描述循环泵，为流体提供压升。',
      ports:{in0:'入口接泵前管路，out0 出口接泵后管路。',out0:'出口接下游设备，通常连接阀门或管道。'},
      adjust:'通常先调转速比。1 倍表示基准曲线；泵效率和扬程曲线在运行前设置。',
      scope:'扬程曲线使用 [体积流量 m³/h, 扬程 m] 数据点。默认曲线用于搭建试算，实际设备应填对应型号资料。',
      primary:[['speed_ratio','speed']],overviewCount:1,
      hints:{speed_ratio:'相对于基准扬程曲线的转速比例。',speed:'相对于基准扬程曲线的转速比例。',efficiency_ratio:'用于估算轴功率；以百分比填写。',efficiency:'用于估算轴功率；以百分比填写。',head_curve:'每个数据点依次填写体积流量 m³/h 和扬程 m。'},
      results:[{port:'in0:FLOW',label:'质量流量'},{port:'in0:PRE',label:'入口绝对压力'},
        {port:'out0:PRE',label:'出口绝对压力'},{key:'shaft_power_w',label:'估算轴功率',unit:'kW',canonical:'W',scale:1000}]
    },
    valve:{
      summary:'通过开度和流量系数 Kv 调节支路阻力与流量。',
      ports:{in0:'入口接上游，出口接下游；两端都需要连接。',out0:'出口接下游管路或设备。'},
      adjust:'日常调节使用阀门开度；80% 表示开度 0.8。Kv 按设备型号填写，运行前设置。',
      scope:'这是基础调节阀模型。需要止回、等百分比或其他特性时，选择相应的专用模块。',
      primary:[['opening_ratio','opening'],['kv_m3_h','kv']],overviewCount:1,
      hints:{opening_ratio:'0% 为关闭，100% 为全开。',opening:'0% 为关闭，100% 为全开。',kv_m3_h:'流量系数，按阀门型号资料填写。',kv:'流量系数，按阀门型号资料填写。'},
      results:[{port:'in0:FLOW',label:'质量流量'},{key:'pressure_drop_pa',label:'入口至出口压降',unit:'kPa',canonical:'Pa',scale:1000},
        {port:'in0:PRE',label:'入口绝对压力'},{port:'out0:PRE',label:'出口绝对压力'}]
    },
    pipe:{
      summary:'根据管长、内径和粗糙度计算圆管阻力，可选与环境换热及管段储热。',
      ports:{in0:'入口接上游设备，out0 出口接下游设备。',out0:'出口接下游；分支需要另外放入连接节点。'},
      adjust:'先填管长和内径，再核对粗糙度。需要散热或热惯性时展开“其他参数”。',
      scope:'内径和粗糙度按显示单位填写。散热 UA 为 0 时绝热；热容分段数为 0 时不启用管段热惯性。',
      primary:[['length_m','length'],['diameter_m','diameter'],['roughness_m','roughness']],overviewCount:2,
      hints:{length_m:'流体经过的实际管长。',length:'流体经过的实际管长。',diameter_m:'使用管道内径，留意显示单位。',diameter:'使用管道内径，以毫米填写。',roughness_m:'绝对粗糙度，以当前显示单位填写。',roughness:'绝对粗糙度，以毫米填写。',heatLoss:'0 表示绝热；大于 0 时与环境换热。',heat_loss_ua_w_k:'0 表示绝热；大于 0 时与环境换热。',thermal_cells:'0 表示不启用热惯性；启用时填写整数。',cells:'0 表示不启用热惯性；启用时填写整数。'},
      results:[{port:'in0:FLOW',label:'质量流量'},{key:'pressure_drop_pa',label:'入口至出口压降',unit:'kPa',canonical:'Pa',scale:1000},
        {port:'in0:TEMP',label:'入口温度'},{port:'out0:TEMP',label:'出口温度'}]
    },
    storage_room:{
      summary:'把库房空气、内部构件和已冻结的货物作为两个热节点，计算库温、货温与热负荷。',
      ports:{heat:'接冷风机的 heat 输出。完整连接为：机组 cold → 冷风机 supply，冷风机 heat → 库房 heat。'},
      adjust:'先设初始库温、初始货温和货物质量，再设室外温度与附加热负荷。温控设定和回差需要由控制页的温控脚本读取并控制机组。',
      scope:'适用于已冻结货物的显热计算，不包含货物冻结潜热。这里的热端口表示冷量连接；运行前在项目设置中选定机组使用的制冷剂。',
      primary:[['setpoint_temperature_k'],['heat_input_w'],['temperature_k'],['ambient_temperature_k'],['goods_mass_kg'],['goods_temperature_k'],['hysteresis_k']],overviewCount:2,
      hints:{setpoint_temperature_k:'温控脚本使用的目标温度；仅填写设定值不会自动启停机组。',heat_input_w:'额外进入库内的热量，按 kW 填写，可用于增加负荷。',temperature_k:'本次运行的初始库温，运行前设置。',ambient_temperature_k:'用于围护漏热计算；机组的冷凝器进风温度需分别核对。',goods_mass_kg:'本次运行开始时已冻结货物的质量。',goods_temperature_k:'应在“其他参数”声明的货物冻结模型温度范围内。',hysteresis_k:'温控设定值上下各留出的温差；0.5 表示 ±0.5 K。'},
      results:[{key:'state.temperature_k',label:'库温',unit:'°C',canonical:'K',offset:-273.15},
        {key:'state.goods_temperature_k',label:'货温',unit:'°C',canonical:'K',offset:-273.15},
        {key:'cooling_power_w',label:'冷风机制冷量',unit:'kW',canonical:'W',scale:1000},
        {key:'net_heat_w',label:'库房净得热',unit:'kW',canonical:'W',scale:1000}]
    },
    unit_cooler:{
      summary:'用空气侧 UA 计算库内空气与制冷剂之间的换热，风机发热计入库内负荷。',
      ports:{supply:'接单级制冷机组的 cold 输出，接收可用冷量。',heat:'接冻结物库房的 heat 输入，向库房提供冷量。'},
      adjust:'先核对空气侧 UA 和风机功率，再选择风机随机组启停（0）或常开（1）。融霜加热功率、时长和滴水时长在“其他参数”中设置。',
      scope:'热端口用于单库房集中循环。电融霜由场景事件触发，按加热、滴水、恢复制冷的顺序执行；本模块不计算结霜量。',
      primary:[['ua_w_k'],['fan_power_w'],['fan_continuous']],overviewCount:2,
      hints:{ua_w_k:'空气侧传热能力，按 kW/K 填写；1 kW/K = 1000 W/K。',fan_power_w:'风机电功率也会成为库内热负荷。',fan_continuous:'0 随机组启停，1 常开；融霜加热和滴水时风机停止。'},
      results:[{key:'state.mode',label:'工作阶段',unit:'',canonical:'1',valueLabels:{0:'制冷阶段',1:'融霜加热',2:'滴水等待'}},
        {key:'state.fan_running',label:'风机状态',unit:'',canonical:'1',valueLabels:{0:'停止',1:'运行'}},
        {key:'refrigerant_heat_w',label:'空气侧换热量',unit:'kW',canonical:'W',scale:1000},
        {key:'heater_power_w',label:'融霜电功率',unit:'kW',canonical:'W',scale:1000}]
    },
    condensing_unit:{
      summary:'在机组内部计算压缩、冷凝、节流和蒸发循环，向冷风机提供冷量。',
      ports:{cold:'接冷风机的 supply 输入，再由冷风机 heat 连接库房 heat。'},
      adjust:'先填额定制冷量并核对额定蒸发、冷凝和环境温度。运行请求 1 为开机、0 为停机；变容量设为 1 后，容量请求参与调节。',
      scope:'使用项目设置中的制冷剂。启停受最小开机、停机时间约束；接入温控脚本后运行请求和容量请求由脚本管理。额定制冷量是额定工况参数，实际冷量随工况变化。',
      primary:[['run_request'],['capacity_ratio'],['variable_capacity'],['rated_cooling_power_w'],['ambient_temperature_k']],overviewCount:2,
      hints:{run_request:'1 请求开机，0 请求停机；实际状态还受最小开/停机时间和融霜影响。',capacity_ratio:'按百分比填写；只有变容量模式才参与容量调节。',variable_capacity:'0 为定容量启停，1 为变容量。',rated_cooling_power_w:'额定工况下的制冷量，按 kW 填写；额定温度在“其他参数”中。',ambient_temperature_k:'冷凝器进风温度，应与采用的环境工况一致。'},
      results:[{key:'state.running',label:'机组状态',unit:'',canonical:'1',valueLabels:{0:'停止',1:'运行'}},
        {key:'state.switch_blocked',label:'启停等待',unit:'',canonical:'1',valueLabels:{0:'无等待',1:'等待最小开/停机时间'}},
        {key:'cooling_power_w',label:'实际制冷量',unit:'kW',canonical:'W',scale:1000},
        {key:'electric_power_w',label:'压缩机电功率',unit:'kW',canonical:'W',scale:1000},
        {key:'evaporating_temperature_k',label:'蒸发温度',unit:'°C',canonical:'K',offset:-273.15},
        {key:'condensing_temperature_k',label:'冷凝温度',unit:'°C',canonical:'K',offset:-273.15}]
    },
    exchanger:{
      summary:'两条独立流路通过传热能力 UA 交换热量，并分别计算水力阻力。',
      ports:{in0:'一次侧入口，与 out0 一次侧出口组成一条流路。',out0:'一次侧出口，接回一次侧管路。',
        in1:'二次侧入口，与 out1 二次侧出口组成另一条流路。',out1:'二次侧出口，接回二次侧管路。'},
      adjust:'通常先设传热能力 UA，再核对阻力系数和水力等效内径。两侧都应连接进出口边界。',
      scope:'本模块用于项目内同一工质的两条流路。各侧吸热功率为流体焓流增量，正值为吸热、负值为放热。',
      primary:[['ua_w_k','ua'],['loss_coefficient','loss'],['diameter_m','diameter']],overviewCount:1,
      hints:{ua_w_k:'总体传热能力；0 表示关闭两侧换热。',ua:'总体传热能力；0 表示关闭两侧换热。',loss_coefficient:'用于两侧水力阻力计算。',loss:'用于两侧水力阻力计算。',diameter_m:'用于水力阻力计算的等效内径。',diameter:'用于水力阻力计算的等效内径，以毫米填写。'},
      results:[{port:'in0:TEMP',label:'入口温度',group:'一次侧'},{port:'out0:TEMP',label:'出口温度',group:'一次侧'},
        {key:'ch0.heat_w',label:'吸热功率',group:'一次侧',unit:'kW',canonical:'W',scale:1000},
        {port:'in1:TEMP',label:'入口温度',group:'二次侧'},{port:'out1:TEMP',label:'出口温度',group:'二次侧'},
        {key:'ch1.heat_w',label:'吸热功率',group:'二次侧',unit:'kW',canonical:'W',scale:1000}]
    }
  };
  function get(m){
    if(!m||m.runtime==='python'||m.manifest?.runtime==='python'||!Object.hasOwn(guides,m.id))return null;
    if(m.kind&&m.kind!==m.id)return null;
    return guides[m.id];
  }
  function parameters(m,specs){
    const guide=get(m);if(!guide)return null;
    const selected=guide.primary.map(ids=>specs.find(p=>ids.includes(p.id))).filter(Boolean);
    return {common:selected,other:specs.filter(p=>!selected.includes(p))};
  }
  function results(m,definition){
    const guide=get(m);if(!guide)return null;
    return guide.results.flatMap(item=>{
      let variable=item.port&&(m.variables||[]).find(v=>v.id===item.port);
      if(item.key){
        const declared=definition?.variables?.find(v=>v.id===item.key&&['derived','state'].includes(v.source));
        if(!declared||declared.unit?.canonical_unit!==item.canonical)return [];
        const existing=(m.variables||[]).find(v=>v.canonicalId===item.key&&v.origin==='runtime');
        variable=existing||{id:'runtime:'+item.key,name:item.key.replace(/[^A-Za-z0-9_]/g,'_').toUpperCase(),origin:'runtime',type:'double',canonicalId:item.key};
        variable={...variable,unit:item.unit,valueLabels:item.valueLabels,unitSpec:{display_unit:item.unit,display_scale:item.scale??1,display_offset:item.offset??0}};
      }
      if(!variable)return [];
      return [{variable:{...variable,label:item.label},group:item.group||'运行结果'}];
    });
  }
  function markup(m,esc,open=false){
    const guide=get(m);if(!guide)return '';
    return `<details class="device-use-guide" data-device-guide="${esc(m.id)}" ${open?'open':''}><summary>怎么连接与调节</summary><p>${esc(guide.summary)}</p><dl>${(m.ports||[]).filter(p=>guide.ports[p.id]).map(p=>`<dt>${esc(p.label||p.id)} <span class="mono">${esc(p.id)}</span></dt><dd>${esc(guide.ports[p.id])}</dd>`).join('')}</dl><p>${esc(guide.adjust)}</p><p class="muted">${esc(guide.scope)}</p></details>`;
  }
  const hint=(m,id)=>get(m)?.hints[id]||'';
  return {get,parameters,results,markup,hint};
})();

export default FluidNetDeviceGuide;
