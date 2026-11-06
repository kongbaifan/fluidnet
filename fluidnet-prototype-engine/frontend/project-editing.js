/* Atomic group geometry edits and explicit copy boundaries. */
window.FluidNetProjectEditing=(()=>{
  const clone=x=>JSON.parse(JSON.stringify(x));
  const nodes=p=>p.pages.flatMap(g=>g.nodes);
  function select(p,ids){const set=new Set(ids),found=nodes(p).filter(n=>set.has(n.id));if(found.length!==set.size||!found.length)throw Error('请选择仍存在的设备');return found;}
  function idle(p){if(p.run?.live||['running','solving','paused'].includes(p.run?.status))throw Error('请停止运行后编辑设备组');}
  function refs(value,map){if(typeof value==='string'){for(const [a,b] of Object.entries(map))if(value===a||value.startsWith(a+'.')||value.startsWith(a+':'))return b+value.slice(a.length);return value;}
    if(Array.isArray(value))return value.map(v=>refs(v,map));if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,refs(v,map)]));return value;}
  function copy(p,ids,pageId,uid){
    idle(p);const chosen=select(p,ids),target=p.pages.find(g=>g.id===pageId);if(!target||target.nodes.length+chosen.length>64)throw Error('目标画布每页最多64台设备');
    const map=Object.fromEntries(chosen.map(n=>[n.id,uid('D')])),set=new Set(ids),copyNodes=chosen.map(n=>({...clone(n),id:map[n.id],name:n.name+' 副本',x:n.x+60,y:n.y+60}));
    if(new Set(Object.values(map)).size!==chosen.length||nodes(p).some(n=>Object.values(map).includes(n.id)))throw Error('复制设备标识冲突');
    const all=p.pages.flatMap(g=>g.edges),internal=all.filter(e=>set.has(e[1])&&set.has(e[3])),external=all.filter(e=>set.has(e[1])!==set.has(e[3]));
    const edges=internal.map(e=>[uid('E'),map[e[1]],e[2],map[e[3]],e[4]]);
    const couplings=(p.thermalCouplings||[]).filter(c=>set.has(c.fluid_instance_id)&&set.has(c.refrigerant_vessel_id)).map(c=>({...refs(clone(c),map),id:uid('coupling')}));
    // Measurements are only copied when every explicit source belongs to the selection.
    const measures=(p.measurements||[]).filter(m=>m.sources?.length&&m.sources.every(s=>Object.keys(map).some(id=>s.startsWith(id+'.')))).map(m=>({...refs(clone(m),map),id:uid('measure')}));
    const circuits=(p.circuitFluids||[]).filter(c=>set.has(c.anchor?.instance_id)).map(c=>({...refs(clone(c),map),id:uid('circuit')}));
    return {nodes:copyNodes,edges,couplings,measurements:measures,circuits,map,external,
      warnings:['外部连线不复制，新端口需要重新接线。','控制器、脚本、工况覆盖、历史结果与曲线绑定保留在原设备；副本使用已应用参数和独立初态。'],pageId};
  }
  function commitCopy(p,plan){idle(p);const target=p.pages.find(g=>g.id===plan.pageId);if(!target||target.nodes.length+plan.nodes.length>64)throw Error('目标画布容量已变化');
    if(nodes(p).some(n=>plan.nodes.some(c=>c.id===n.id)))throw Error('复制标识已存在');
    target.nodes.push(...clone(plan.nodes));target.edges.push(...clone(plan.edges));
    if(plan.couplings.length)p.thermalCouplings=[...(p.thermalCouplings||[]),...clone(plan.couplings)];
    if(plan.measurements.length)p.measurements=[...(p.measurements||[]),...clone(plan.measurements)];if(plan.circuits.length)p.circuitFluids=[...(p.circuitFluids||[]),...clone(plan.circuits)];return plan.nodes.map(n=>n.id);}
  function move(p,ids,pageId){idle(p);const chosen=select(p,ids),target=p.pages.find(g=>g.id===pageId);if(!target)throw Error('目标画布不存在');
    const add=chosen.filter(n=>!target.nodes.includes(n));if(target.nodes.length+add.length>64)throw Error('目标画布每页最多64台设备');
    for(const g of p.pages)if(g!==target)g.nodes=g.nodes.filter(n=>!chosen.includes(n));target.nodes.push(...add);window.FluidNetLinks.rehome(p);}
  function align(p,ids,mode){idle(p);const list=select(p,ids);if(list.length<2)throw Error('请至少选择两台设备');
    if(!['left','top','horizontal','vertical'].includes(mode))throw Error('未知对齐方式');
    const axis=mode==='left'||mode==='horizontal'?'x':'y',sorted=[...list].sort((a,b)=>a[axis]-b[axis]),low=sorted[0][axis],high=sorted.at(-1)[axis];
    sorted.forEach((n,i)=>n[axis]=mode==='left'||mode==='top'?low:Math.round(low+(high-low)*i/(sorted.length-1)));}
  function search(p,query,definition,circuits=[]){const q=query.trim().toLocaleLowerCase();return p.pages.flatMap(page=>page.nodes.map(node=>{
    const m=definition(node),circuitsForNode=circuits.filter(c=>(c.ports||[]).some(port=>port.startsWith(node.id+':'))).map(c=>'回路 '+c.id+' '+(c.source||'')+' '+(c.fluid?.fluid||''));
    const labels=(p.circuitFluids||[]).filter(c=>c.anchor?.instance_id===node.id).map(c=>c.id+' '+c.fluid);
    const text=[node.id,node.name,node.moduleId,m?.name,page.name,...circuitsForNode,...labels].join(' ');
    return {node,page,text};})).filter(x=>!q||x.text.toLocaleLowerCase().includes(q));}
  return {select,idle,copy,commitCopy,move,align,search,refs};
})();
