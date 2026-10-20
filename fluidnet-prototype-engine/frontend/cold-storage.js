/* Case creation and thermal views; all result values come from the shared engine run. */
window.createColdStorageUI = function (ui) {
  const state=ui.state, engine=ui.engine;
  const isCase=p=>p.caseId==='cold-room-ideal-v1';
  const value=(p,key,scale=1,offset=0)=>{
    const raw=p.run.history.at(-1)?.canonical?.[key];
    return typeof raw==='number'?(raw/scale+offset).toFixed(3):'—';
  };
  async function create(){
    if(!engine().catalog || !engine().health?.capabilities?.cold_room_ideal_source)throw Error('请等待支持冷库案例的计算服务连接。');
    if(state().projects.length>=20)throw Error('最多保存 20 个项目');
    const response=await fetch('/api/v1/examples/cold-storage',{headers:engine().authHeaders()});
    if(!response.ok)throw Error('无法读取冷库案例');
    const model=await response.json();
    const nodes=model.instances.map(n=>{
      const definition=model.modules.find(m=>m.id===n.module_id);
      const params=Object.fromEntries(definition.parameters.map(spec=>{
        const raw=n.parameters[spec.id]??spec.default;
        return [spec.id,spec.unit?raw/spec.unit.display_scale+spec.unit.display_offset:raw];
      }));
      return ui.makeInstance(n.id,n.module_id,n.name,n.module_id==='cold_room'?730:430,215,params);
    });
    const pg={id:'main',name:'库房热平衡',zoom:1,pan:[0,0],nodes,
      edges:model.connections.map(c=>[c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id])};
    const p=ui.makeProject(ui.uid('project'),model.name,model.description,pg);
    p.caseId='cold-room-ideal-v1';p.controllers=model.controllers;
    p.solver={...p.solver,duration:7200,dt:30,executionMode:'fast'};
    p.controlInputs='ROOM1.state.temperature_k';p.controlOutputs='controller.room_temperature.setpoint';
    state().projects.push(p);ui.normalizeState();
    const bindings=[
      ['ROOM1','runtime:state.temperature_k','库温','°C','ROOM1.state.temperature_k',1,-273.15],
      ['COLD1','runtime:cooling_power_w','冷却功率','kW','COLD1.cooling_power_w',1000,0],
      ['COLD1','runtime:state.cooling_energy_j','累计冷量','kWh','COLD1.state.cooling_energy_j',3600000,0]
    ];
    for(const [nodeId,variableId,label,unit,canonicalKey,canonicalScale,canonicalOffset] of bindings)
      state().charts.extra.push({id:ui.uid('cold-chart'),projectId:p.id,nodeId,variableId,label,unit,canonicalKey,canonicalScale,canonicalOffset});
    ui.ui().showChart=true;ui.ui().workbenchChart=state().charts.extra.find(c=>c.projectId===p.id).id;
    ui.markDirty(p);ui.persist();ui.openProject(p.id);
    ui.msg('单库房 A1 已创建：库温与冷量可计算，冷源采用理想容量模型。');
  }
  document.addEventListener('click',event=>{
    if(event.target.closest('[data-action="cold-storage-example"]'))create().catch(error=>ui.msg(error.message,true));
  });
  function markup(p){
    if(!isCase(p))return '';
    return `<section class="panel cold-storage-summary" aria-label="冷库运行指标"><div class="panel-head"><strong>−18°C 单库房 · A1</strong><span>理想冷源</span></div><div class="panel-body"><p>库房热容、围护漏热与温度控制。冷源按指定容量供冷，制冷循环、货温与耗电将在后续阶段加入。</p><div class="metric-row"><div class="metric"><span>库温 · °C</span><strong data-cold-temperature>${value(p,'ROOM1.state.temperature_k',1,-273.15)}</strong></div><div class="metric"><span>冷却功率 · kW</span><strong data-cold-power>${value(p,'COLD1.cooling_power_w',1000)}</strong></div><div class="metric"><span>累计冷量 · kWh</span><strong data-cold-energy>${value(p,'COLD1.state.cooling_energy_j',3600000)}</strong></div></div></div></section>`;
  }
  function refresh(p){
    if(!isCase(p))return;
    for(const [selector,key,scale,offset] of [
      ['[data-cold-temperature]','ROOM1.state.temperature_k',1,-273.15],
      ['[data-cold-power]','COLD1.cooling_power_w',1000,0],
      ['[data-cold-energy]','COLD1.state.cooling_energy_j',3600000,0]]){
      const element=document.querySelector(selector);if(element)element.textContent=value(p,key,scale,offset);
    }
  }
  return {markup,refresh};
};
