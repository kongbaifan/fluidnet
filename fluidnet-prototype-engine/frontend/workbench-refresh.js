/* Refresh non-structural workbench state while keeping the canvas and open editors alive. */
export const FluidNetWorkbenchRefresh = (() => {
  function create({root,project,page,ui,viewBox,canvas,selection,chartMarkup,chartRefresh,layout,chrome,icon,history,placingName}){
    function refresh(){
      const owner=project(),current=page(),svg=root.querySelector('#network'),shell=root.querySelector('.workbench');
      if(ui.route!=='workbench'||!svg||!shell||svg.dataset.project!==owner.id||svg.dataset.page!==current.id)return false;
      // Structural edits still use the normal view renderer.
      const nodes=[...svg.querySelectorAll('[data-node]')],edges=[...svg.querySelectorAll('[data-canvas-edge]')];
      const nodeIds=new Set(current.nodes.map(n=>n.id)),visibleEdges=current.edges.filter(edge=>nodeIds.has(edge[1])&&nodeIds.has(edge[3]));
      const edgeIds=new Set(visibleEdges.map(e=>e[0]));
      if(nodes.length!==current.nodes.length||nodes.some(el=>!nodeIds.has(el.dataset.node))||
        edges.length!==visibleEdges.length||edges.some(el=>!edgeIds.has(el.dataset.canvasEdge)))return false;
      svg.setAttribute('viewBox',viewBox(current));
      shell.classList.toggle('show-library',!!ui.showLibrary);shell.classList.toggle('with-chart',!!ui.showChart);
      root.querySelector('#network-area')?.classList.toggle('grid',!!ui.pageGrid);
      const zoom=root.querySelector('.zoom > span');if(zoom)zoom.textContent=Math.round(current.zoom*100)+'%';
      const hint=root.querySelector('[data-canvas-hint]');if(hint)hint.textContent=ui.placing?'点击画布放置 '+placingName():ui.connecting?'可切换画布选择另一个空闲端口 · Esc 取消':'双击设备编辑参数 · 拖动空白处平移';
      for(const button of root.querySelectorAll('.canvas-tools [data-action="toggle-library"]')){
        const label=ui.showLibrary?'收起模块库':'展开模块库';button.setAttribute('aria-label',label);button.setAttribute('title',label);button.setAttribute('aria-expanded',String(!!ui.showLibrary));
        const markup=icon(ui.showLibrary?'PanelLeftClose':'PanelLeftOpen');if(button.innerHTML!==markup)button.innerHTML=markup;
      }
      for(const button of root.querySelectorAll('.runbar [data-action="toggle-chart"]')){
        button.setAttribute('aria-label',ui.showChart?'收起同屏曲线':'展开同屏曲线');button.setAttribute('aria-expanded',String(!!ui.showChart));button.classList.toggle('active',!!ui.showChart);
      }
      for(const action of ['undo','redo'])for(const button of root.querySelectorAll(`[data-action="${action}"]`))button.disabled=!history(action);
      for(const action of ['select','connect'])for(const button of root.querySelectorAll(`[data-action="${action}-mode"]`))button.setAttribute('aria-pressed',String(ui.canvasMode===action));
      for(const button of root.querySelectorAll('.runbar [data-command]')){
        const command=button.dataset.command,status=owner.run.status;
        button.disabled=command==='pause'?status!=='running':command==='stop'?['ready','stopped'].includes(status):['running','solving'].includes(status);
        if(command==='run'){const label=button.querySelector('span');if(label)label.textContent=status==='paused'?'继续':'运行';}
      }
      let chart=root.querySelector('.workbench-chart');
      if(ui.showChart&&!chart){root.querySelector('.canvas-info').insertAdjacentHTML('beforebegin',chartMarkup());chart=root.querySelector('.workbench-chart');}
      if(chart){chart.hidden=!ui.showChart;chart.style.display=ui.showChart?'':'none';}
      selection();canvas().refresh();if(ui.showChart)chartRefresh();chrome();layout();return true;
    }
    return {refresh};
  }
  return {create};
})();

export default FluidNetWorkbenchRefresh;
