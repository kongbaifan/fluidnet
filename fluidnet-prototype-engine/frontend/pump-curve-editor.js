/* Pump head curves use the existing [m³/h, m] parameter and draft/apply transaction. */
export const FluidNetPumpCurveEditor=(()=>{
  const supported=(m,spec)=>spec?.id==='head_curve'&&spec.value_type==='curve'&&
    (m?.id==='pump'&&m.runtime!=='python'&&m.manifest?.runtime!=='python'||m?.template==='pump'||m?.manifest?.channels?.some(c=>c.relation==='pump_curve'||c.solver_model==='pump_curve'));
  function inspect(rows){
    const errors=[],points=[];
    if(!Array.isArray(rows)||rows.length<2)errors.push({row:null,message:'至少填写两个数据点。'});
    for(const [i,row] of (Array.isArray(rows)?rows:[]).entries()){
      const valid=Array.isArray(row)&&row.length===2&&row.every(v=>(typeof v==='number'||typeof v==='string'&&v.trim()!=='')&&Number.isFinite(Number(v))&&Number(v)>=0);
      points.push(valid?row.map(Number):null);
      if(!valid)errors.push({row:i,message:`第 ${i+1} 行：流量和扬程必须是非负有限数值，不能留空。`});
    }
    if(points[0]&&points[0][0]!==0)errors.push({row:0,message:'第 1 行：起点流量必须为 0。'});
    if(points.at(-1)&&points.at(-1)[1]!==0)errors.push({row:points.length-1,message:`第 ${points.length} 行：末点扬程必须为 0。`});
    for(let i=1;i<points.length;i++)if(points[i]&&points[i-1]){
      if(points[i][0]<=points[i-1][0])errors.push({row:i,message:`第 ${i+1} 行：流量必须大于上一行，不能重复。`});
      if(points[i][1]>=points[i-1][1])errors.push({row:i,message:`第 ${i+1} 行：扬程必须小于上一行。`});
    }
    return {valid:!errors.length,errors,points};
  }
  function svg(points,esc){
    const maxQ=Math.max(...points.map(p=>p[0])),maxH=Math.max(...points.map(p=>p[1]));
    const x=q=>58+q/maxQ*376,y=h=>246-h/maxH*208,num=v=>Number(v.toPrecision(5)).toString();
    return `<svg viewBox="0 0 460 300" role="img" aria-label="泵基准扬程曲线预览"><title>流量 m³/h 与扬程 m，按点线性连接</title>${[0,.25,.5,.75,1].map(t=>`<path d="M58 ${y(t*maxH)}H434 M${x(t*maxQ)} 38V246" class="pump-curve-grid"/><text x="50" y="${y(t*maxH)+4}" text-anchor="end">${esc(num(t*maxH))}</text><text x="${x(t*maxQ)}" y="265" text-anchor="middle">${esc(num(t*maxQ))}</text>`).join('')}<path d="M58 38V246H434" class="pump-curve-axis"/><polyline points="${points.map(p=>x(p[0])+','+y(p[1])).join(' ')}" class="pump-curve-line"/>${points.map((p,i)=>`<circle cx="${x(p[0])}" cy="${y(p[1])}" r="4"><title>${i+1}：${esc(num(p[0]))} m³/h，${esc(num(p[1]))} m</title></circle>`).join('')}<text x="16" y="19">扬程 / m</text><text x="246" y="292" text-anchor="middle">体积流量 / m³/h</text></svg>`;
  }
  function mount(root,initial,{esc,onValidity=()=>{}}){
    let rows=Array.isArray(initial)?initial.map(p=>Array.isArray(p)?p.slice():['','']):[];
    root.innerHTML='<div class="pump-curve-editor"><div><div class="pump-curve-table table-wrap"><table><thead><tr><th>点</th><th>流量 / m³/h</th><th>扬程 / m</th><th>操作</th></tr></thead><tbody data-curve-rows></tbody></table></div><button type="button" class="btn small" data-curve-add>添加末点</button></div><div class="pump-curve-preview"><div data-curve-plot></div><div data-curve-validation role="status" aria-live="polite"></div></div></div>';
    const table=root.querySelector('[data-curve-rows]');
    function validate(){
      const result=inspect(rows);
      root.querySelector('[data-curve-validation]').innerHTML=result.valid?'<p class="badge good">数据点有效，可以保存为草稿</p>':result.errors.map(e=>`<p class="pump-curve-error">${esc(e.message)}</p>`).join('');
      root.querySelector('[data-curve-plot]').innerHTML=result.valid?svg(result.points,esc):'<div class="pump-curve-empty">补齐并修正数据点后显示曲线预览。</div>';
      for(const input of table.querySelectorAll('[data-curve-row]'))input.setAttribute('aria-invalid',String(result.errors.some(e=>e.row===Number(input.dataset.curveRow))));
      onValidity(result.valid);return result;
    }
    function render(){
      table.innerHTML=rows.map((p,i)=>`<tr><td>${i+1}</td>${[0,1].map(axis=>`<td><input type="number" min="0" step="any" data-curve-row="${i}" data-curve-axis="${axis}" aria-label="第 ${i+1} 行${axis?'扬程':'流量'}" value="${esc(p[axis]??'')}"></td>`).join('')}<td><button type="button" class="btn small" data-curve-insert="${i}" aria-label="第 ${i+1} 行后插入数据点">插入</button><button type="button" class="btn small" data-curve-remove="${i}" aria-label="删除第 ${i+1} 行" ${rows.length<=2?'disabled':''}>删除</button></td></tr>`).join('');
      validate();
    }
    root.addEventListener('input',e=>{
      const input=e.target;if(input.dataset.curveRow===undefined)return;
      rows[Number(input.dataset.curveRow)][Number(input.dataset.curveAxis)]=input.value;validate();
    });
    root.addEventListener('click',e=>{
      const button=e.target.closest('button');if(!button||!root.contains(button))return;
      if(button.hasAttribute('data-curve-add'))rows.push(['','']);
      else if(button.dataset.curveRemove!==undefined){if(rows.length<=2)return;rows.splice(Number(button.dataset.curveRemove),1);}
      else if(button.dataset.curveInsert!==undefined){
        const i=Number(button.dataset.curveInsert),a=rows[i],b=rows[i+1];
        const valid=[a,b].every(p=>p&&p.every(v=>String(v).trim()!==''&&Number.isFinite(Number(v))));
        rows.splice(i+1,0,valid?a.map((v,j)=>Number(v)/2+Number(b[j])/2):['','']);
      }else return;
      render();
    });
    render();
    return {read(){const result=validate();if(!result.valid)throw Error(result.errors[0].message);return result.points.map(p=>p.slice());}};
  }
  return {supported,inspect,mount};
})();
export default FluidNetPumpCurveEditor;
