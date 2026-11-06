/* Canvas controls and frame ownership. No solver writes or training state. */
window.FluidNetCanvasWorkspace = (() => {
  function create(deps) {
    const {getState,project,activePage,moduleOf,ui,esc,btn,links,domains,quick,channels,projectKey,selectedIds,
      engine,openDialog,closeDialog,render,saveUI,locate}=deps;
    const observations=window.FluidNetCanvasObservations;
    let queued=null,frameId=null;
    const owner=page=>getState().projects.find(p=>p.pages.includes(page))||project();
    function context(p) {
      const run=p.run||{},history=run.history||[],row=[...history].reverse().find(r=>!r.partial&&r.valid!==false);
      const stale=!!(history.length||run.diagnostics?.length)&&(!run.parameterKey||run.parameterKey!==projectKey(p));
      const mode=['circuit','flow','temperature','pressure'].includes(ui.canvasModeValue)?ui.canvasModeValue:'circuit';
      const valid=!stale&&run.source==='engine';
      const recent=!valid?null:row?{...row,diagnostics:[...(row.diagnostics||[]),...(run.diagnostics||[])]}:
        run.diagnostics?.length?{t:run.diagnosticTime??run.time,valid:false,canonical:{},diagnostics:run.diagnostics}:null;
      return {row:recent,stale,mode,scale:ui.canvasScales?.[mode],labels:!!ui.canvasLabels,
        animate:ui.canvasAnimate!==false&&run.status==='running'&&valid&&!!row&&history.at(-1)===row,
        partial:!!history.at(-1)?.partial,time:recent?.t,run};
    }
    const view=window.FluidNetCanvasView.create({esc,moduleOf:(p,n)=>p.moduleSnapshots?.[n.moduleId]||moduleOf(n),
      ui:()=>ui,domains,links,quick,channels,context,selectedIds,
      circuit:(p,key)=>{const all=engine().circuits?.(p.id)||[];return all.find(c=>c.ports.includes(key));},
      circuitLabel:c=>`回路 ${c.id+1} · ${c.fluid.fluid}`});
    function diagnostics(p=project()) {
      const ctx=context(p),rows=ctx.row?.diagnostics||(!ctx.stale?ctx.run.diagnostics:[])||[];
      return [...new Map(rows.filter(d=>['warning','error'].includes(d.severity)).map(d=>[JSON.stringify([d.code,d.instance_id,d.message]),d])).values()];
    }
    function legendText(p=project()) {
      const ctx=context(p),scale=observations.legend(ctx.mode,ctx.scale);
      const basis=ctx.stale?'结果已过期 · 着色与流向停用':ctx.row?.valid===false?'运行失败 · 尚无有效完整采样':ctx.row?`采样 ${Number(ctx.time||0).toFixed(2)} s${ctx.partial?' · 最近完整关键帧，动画暂停':''}${ctx.run.status==='failed'?' · 最后接受结果，运行已失败':''}`:'尚无完整采样';
      const range=ctx.mode==='circuit'?'颜色区分工质回路':`${scale.label} ${scale.min} — ${scale.max} ${scale.unit} · 超范围使用端点色`;
      return `${ctx.mode==='circuit'?'':`<i class="canvas-legend-bar" style="background:linear-gradient(90deg,${scale.colors.join(',')})" aria-hidden="true"></i>`}<span>${esc(range)} · ${esc(basis)} · 灰色/—为未知</span>`;
    }
    function tools() {
      const mode=context(project()).mode;
      return `<div class="canvas-visual-tools" aria-label="工程画布显示"><label>连线显示<select data-canvas-mode aria-label="画布物理量">${[['circuit','工质回路'],['flow','质量流量'],['temperature','温度'],['pressure','绝对压力']].map(([v,label])=>`<option value="${v}" ${mode===v?'selected':''}>${label}</option>`).join('')}</select></label><label><input type="checkbox" data-canvas-labels ${ui.canvasLabels?'checked':''}>数值标签</label><label><input type="checkbox" data-canvas-animation ${ui.canvasAnimate===false?'':'checked'}>流动动画</label>${btn('canvas-range','色标范围','SlidersHorizontal',mode==='circuit'?'disabled':'','small')}${btn('canvas-alerts','运行告警 '+diagnostics().length,'Info','data-canvas-alert-count','small')}<div class="canvas-legend" data-canvas-legend>${legendText()}</div></div>`;
    }
    function refresh() {
      if(ui.route!=='workbench')return;
      view.paint(document.getElementById('network'),project(),activePage());
      const legend=document.querySelector('[data-canvas-legend]');if(legend)legend.innerHTML=legendText();
      const count=document.querySelector('[data-canvas-alert-count]');if(count)count.lastChild.textContent='运行告警 '+diagnostics().length;
    }
    function flush() {
      if(frameId!==null)cancelAnimationFrame(frameId);frameId=null;
      if(!queued)return;const item=queued;queued=null;
      if(item.project===project()&&item.page===activePage()&&item.svg.isConnected)view.move(item.svg,item.project,item.page,item.id);
    }
    function move(id) {
      const svg=document.getElementById('network');if(!svg)return;
      queued={svg,project:project(),page:activePage(),id};if(frameId===null)frameId=requestAnimationFrame(flush);
    }
    function action(name,el) {
      if(name==='canvas-range') {
        const mode=context(project()).mode,scale=observations.legend(mode,ui.canvasScales?.[mode]);
        openDialog('画布色标范围',`仅改变显示，单位 ${scale.unit}；超范围用端点色并保留实际读数。`,
          `<div class="fields"><label class="field"><span>下限</span><input name="min" type="number" step="any" required value="${scale.min}"></label><label class="field"><span>上限</span><input name="max" type="number" step="any" required value="${scale.max}"></label></div>`,data=>{
            const min=Number(data.min),max=Number(data.max);if(!Number.isFinite(min)||!Number.isFinite(max)||min>=max||mode==='flow'&&min<0||mode==='pressure'&&min<0)throw Error('请输入有效范围：上限须大于下限，流量幅值与绝压不能为负。');
            ui.canvasScales={...ui.canvasScales,[mode]:{min,max}};saveUI();refresh();
          },'应用色标');return true;
      }
      if(name==='canvas-alerts') {
        const p=project(),ctx=context(p),items=diagnostics(p);
        openDialog('运行告警与诊断',ctx.stale?'当前项目已变更，请重新运行取得对应诊断。':`当前项目 · ${ctx.row?`采样 ${ctx.time} s`:'尚无完整采样'}。结构预检仍使用“检查连接”。`,
          `<div class="canvas-alert-list">${items.map(d=>{const found=d.instance_id&&links.locate(p,d.instance_id);return `<div class="canvas-alert-item"><div class="grow"><strong>${esc(d.severity==='error'?'错误':'警告')} · ${esc(d.code||'')}</strong><p>${esc(d.message)}</p><small>${esc(d.instance_id||'系统诊断')}${d.source_path?' · '+esc(d.source_path):''}</small></div>${found?btn('canvas-locate-alert','定位','ArrowUpRight',`data-id="${esc(d.instance_id)}" data-project="${esc(p.id)}"`,'small'):''}</div>`;}).join('')||'<p>当前没有可显示的运行警告或错误；未采样不代表系统已验证。</p>'}</div>`,null,'',true);return true;
      }
      if(name==='canvas-locate-alert'){if(el.dataset.project!==project().id)throw Error('项目已切换，请重新查看告警。');closeDialog();locate(el.dataset.id);return true;}
      return false;
    }
    function change(el) {
      if('canvasMode'in el.dataset){ui.canvasModeValue=el.value;saveUI();render();return true;}
      if('canvasLabels'in el.dataset){ui.canvasLabels=el.checked;saveUI();refresh();return true;}
      if('canvasAnimation'in el.dataset){ui.canvasAnimate=el.checked;saveUI();refresh();return true;}
      return false;
    }
    return {tools,refresh,move,flush,action,change,context,diagnostics,
      markup:(page,mini)=>view.markup(owner(page),page,mini),endpoint:(page,id,port)=>view.endpoint(owner(page),page,id,port),
      bounds:(page,n)=>view.bounds(owner(page),n)};
  }
  return {create};
})();
