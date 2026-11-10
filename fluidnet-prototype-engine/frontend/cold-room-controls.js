/* Simple room controls over existing PID definitions and actual run observations. */
export const FluidNetColdRoomControls=(()=>{
  function groups(project,devices){
    const coolers=new Set(devices.filter(d=>['air_cooler','defrost_air_cooler','network_air_cooler','frost_hotgas_cooler'].includes(d.model)).map(d=>d.node.id));
    return devices.filter(d=>d.model==='cold_room').map(({node})=>({node,controllers:(project.controllers||[])
      .filter(c=>c.measurement===node.id+'.state.temperature_k'&&coolers.has(c.instance_id)&&c.parameter_id==='fan_ratio'&&c.kp<0)}))
      .filter(group=>group.controllers.length);
  }
  function observation(group,read,current){
    const targets=group.controllers.map(c=>c.setpoint),same=targets.every(t=>t===targets[0]);
    const target=same?targets[0]:null,temperature=current?read(group.node.id+'.state.temperature_k'):undefined;
    if(!Number.isFinite(temperature))return {target,temperature:null,status:current?'结果未记录库温':'运行后查看',warning:false};
    const actuators=group.controllers.map(c=>({controller:c,running:read(c.instance_id+'.param.running'),output:read('controller.'+c.id+'.output')}));
    let status='温度正常',warning=false;
    if(!same)status='目标不一致，请调整';
    else if(group.controllers.some(c=>{const mode=Number(read(c.instance_id+'.defrost_mode'));return mode>=1&&mode<=4;}))status='部分冷风机融霜中';
    else if(actuators.every(a=>Number.isFinite(a.running)&&a.running<.5))status='冷风机已停机';
    else if(group.controllers.some(c=>c.mode==='manual'))status='包含手动控制';
    else if(temperature>target+.5){
      const full=actuators.every(a=>(Number.isFinite(a.running)&&a.running<.5)
        ||(a.running>=.5&&Number.isFinite(a.output)&&a.output>=a.controller.maximum-.001));
      status=full?'制冷已到上限，库温仍偏高':'库温偏高，正在降温';warning=full;
    }else if(temperature<target-.5)status='库温偏低，正在减小制冷';
    return {target,temperature,status,warning};
  }
  function applyTargets(project,items,values){
    if(['running','solving'].includes(project.run.status)||project.run.live)throw Error('请先停止运行，再修改目标温度。');
    const updates=items.map(group=>{
      const raw=values[group.node.id],celsius=Number(raw);
      if(raw===undefined||String(raw).trim()===''||!Number.isFinite(celsius)||celsius<=-273.15)throw Error('请输入有效的目标温度。');
      return {group,target:Number((celsius+273.15).toFixed(10))};
    });
    for(const {group,target} of updates)for(const c of group.controllers)c.setpoint=target;
  }
  return {groups,observation,applyTargets};
})();
export default FluidNetColdRoomControls;
