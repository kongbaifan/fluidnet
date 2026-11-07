/* External API examples use the frozen run contract and its actual published keys. */
export const FluidNetApiExamples = (() => {
  function directory(record, values) {
    const project=record.request?.project, metadata=new Map();
    for(const node of project?.instances||[]) {
      const definition=project.modules.find(m=>m.id===node.module_id);
      for(const variable of definition?.variables||[])metadata.set(`${node.id}.${variable.id}`,{
        label:`${node.name||node.id} · ${variable.label}`,unit:variable.unit?.canonical_unit||''});
      for(const spec of definition?.parameters||[]) {
        const key=`${node.id}.param.${spec.id}`;
        const controlled=(project.controllers||[]).some(c=>c.instance_id===node.id&&c.parameter_id===spec.id)
          || (project.control_scripts||[]).some(c=>c.enabled&&(c.outputs||[]).includes(key));
        metadata.set(key,{label:`${node.name||node.id} · ${spec.label}`,unit:spec.unit?.canonical_unit||'',
          writable:!!spec.runtime&&!!spec.writable&&!controlled});
      }
    }
    return Object.entries(values||{}).map(([key,value])=>({key,value,writable:false,...metadata.get(key)}));
  }
  function request(runId,kind,item,value) {
    const path=`/api/v1/runs/${encodeURIComponent(runId)}`;
    if(kind==='status')return {method:'GET',path};
    if(!item)throw Error(kind==='set'?'此运行没有可直接写入的设备参数。':'此运行尚无可读取的变量。');
    if(kind==='set') {
      if(!item.writable)throw Error('所选变量不可直接写入。');
      return {method:'POST',path:path+'/variables',body:{values:{[item.key]:value},wait_s:2}};
    }
    return {method:kind==='stream'?'WS':'GET',path:path+(kind==='stream'?'/stream':'/variables')+'?keys='+encodeURIComponent(item.key)};
  }
  return {directory,request};
})();

export default FluidNetApiExamples;
