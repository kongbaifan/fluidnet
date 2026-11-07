/* Device window layout and presentation. Parameter application remains a separate transaction. */
export const FluidNetDeviceWindows = (() => {
  const clone=value=>value===undefined?undefined:JSON.parse(JSON.stringify(value));
  const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
  const tabs=[['overview','总览'],['parameters','参数与型号'],['variables','全部变量'],['connections','连接']];
  const actionNames=Object.freeze(['float-dock','float-close','float-tab','device-panel-tab','float-pin','float-min','float-max']);
  function create({windows,storage,elements,content,chrome,effects}) {
    const {esc,icon,ibtn}=chrome;
    const find=id=>windows.list().find(f=>f.id===id);
    const width=()=>elements.viewport().width;
    const isDocked=f=>!!f?.docked&&!f.minimized&&width()>=1000;
    function bounds(f) {
      const p=elements.page().getBoundingClientRect(),maxW=Math.max(1,p.width-16),maxH=Math.max(1,p.height-16);
      f.w=clamp(f.w||440,Math.min(320,maxW),maxW);
      f.h=clamp(f.h||520,Math.min(270,maxH),maxH);
      f.x=clamp(f.x??p.right-f.w-20,p.left+8,p.right-f.w-8);
      f.y=clamp(f.y??p.top+28,p.top+8,p.bottom-(f.minimized?46:f.h)-8);
      return f;
    }
    function dockBounds(){const r=elements.dock().getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};}
    function remember(f) {
      if(!f)return;
      storage.write(windows.project(),f.id,{x:f.x,y:f.y,w:f.w,h:f.h,pinned:f.pinned,docked:!!f.docked});
    }
    function syncDockLayout() {
      const workbench=elements.root().querySelector('.workbench');if(!workbench)return;
      const active=windows.list().find(f=>content.node(f.id)&&isDocked(f));
      workbench.classList.toggle('has-docked',!!active);
      workbench.classList.toggle('has-docked-variables',active?.tab==='variables');
    }
    function toggleDock(id) {
      const f=find(id);if(!f)return;
      if(width()<1000&&!f.docked){effects.message('较宽的窗口可将参数停靠到右侧；当前使用浮窗。');return;}
      for(const other of windows.list())if(other.docked&&other!==f){other.docked=false;remember(other);}
      f.docked=!f.docked;f.minimized=false;delete f.restore;
      remember(f);effects.dirty();render();
    }
    function setTab(f,tab) {
      if(!f||!tabs.some(([key])=>key===tab))return;
      f.tab=tab;
      if(tab==='variables'&&!f.variablesOpened){
        const r=elements.page().getBoundingClientRect();f.variablesOpened=true;
        f.w=Math.min(780,r.width-16);f.h=Math.min(650,r.height-16);
        f.x=r.right-f.w-12;f.y=r.top+12;
      }
    }
    function open(id) {
      if(!content.node(id))return;
      windows.select(id);let f=find(id);
      if(!f){f={...clone(storage.read(windows.project(),id)||{}),id,tab:'parameters',order:windows.focus(id)};windows.list().push(f);}
      if(f.docked)for(const other of windows.list())if(other!==f&&other.docked){other.docked=false;remember(other);}
      f.tab='parameters';f.minimized=false;f.order=windows.focus(id);
      effects.selection();render();return f;
    }
    function render() {
      const layer=elements.layer();syncDockLayout();
      let html=windows.route()==='workbench'?windows.list().filter(f=>content.node(f.id)).map(f=>{
        const b=isDocked(f)?dockBounds():bounds(f),n=content.node(f.id),id=esc(f.id);
        return `<section class="floater${isDocked(f)?' docked':''}${windows.front()===f.id?' front':''}${f.minimized?' minimized':''}${f.tab==='variables'?' variables-floater':''}" role="region" aria-label="${esc(n.id+' 设备参数')}" data-float-id="${id}" style="left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${f.minimized?46:b.h}px;z-index:${50+(f.pinned?50:0)+f.order%40}">
          <header class="float-head" data-float-move="${id}">${icon('SlidersHorizontal')}<strong class="float-title">${esc(n.id+' · '+n.name)}</strong>${ibtn('float-dock',f.docked?'取消停靠':'停靠到右侧',f.docked?'ExternalLink':'Columns2',`data-id="${id}" aria-pressed="${!!f.docked}" ${width()<1000&&!f.docked?'hidden':''}`)}${ibtn('float-pin','置顶窗口','Pin',`data-id="${id}" aria-pressed="${!!f.pinned}"`)}${ibtn('float-max','最大化或还原','Maximize2',`data-id="${id}"`)}${ibtn('float-min',f.minimized?'还原窗口':'收起窗口',f.minimized?'ChevronDown':'Minus',`data-id="${id}"`)}${ibtn('float-close','关闭设备窗口','X',`data-id="${id}"`)}</header>
          ${f.minimized?'':`<nav class="tabs float-tabs" aria-label="设备属性页签">${tabs.map(([key,label])=>`<button type="button" data-action="float-tab" data-id="${id}" data-value="${key}" class="${f.tab===key?'active':''}" aria-pressed="${f.tab===key}">${label}</button>`).join('')}</nav><div class="float-body">${content.body(f,n)}</div>${content.footer(f,n)}<button class="float-resize" data-float-resize="${id}" aria-label="调整窗口大小">${icon('Grip')}</button>`}
        </section>`;
      }).join(''):'';
      html+=content.extras();layer.innerHTML=html;effects.rendered();
    }
    function updateBodies(){effects.retainFocus(render);}
    function action(name,el) {
      if(!actionNames.includes(name))return false;
      const f=find(el.dataset.id);if(!f)return true;
      if(name==='float-dock'){toggleDock(f.id);return true;}
      if(name==='float-close'){remember(f);windows.replace(windows.list().filter(item=>item!==f));}
      else if(name==='float-tab'||name==='device-panel-tab')setTab(f,el.dataset.value);
      else if(name==='float-pin'){f.pinned=!f.pinned;remember(f);}
      else if(name==='float-min')f.minimized=!f.minimized;
      else if(name==='float-max'){
        const r=elements.page().getBoundingClientRect();f.docked=false;remember(f);
        if(f.restore){Object.assign(f,f.restore);delete f.restore;}
        else {f.restore={x:f.x,y:f.y,w:f.w,h:f.h};Object.assign(f,{x:r.left+8,y:r.top+8,w:r.width-16,h:r.height-16});}
      }
      render();return true;
    }
    function beginPointer(event) {
      const target=event.target,resize=target.closest('[data-float-resize]'),move=target.closest('[data-float-move]');
      if(!resize&&(!move||target.closest('button,input,select')))return null;
      const id=resize?resize.dataset.floatResize:move.dataset.floatMove,f=find(id);
      // A docked header owns the hit even though it must not start a drag.
      if(!f||isDocked(f))return {blocked:true};
      f.order=windows.focus(id);
      return {kind:resize?'resize':'window',id,projectId:windows.project(),window:f,original:{x:f.x,y:f.y,w:f.w,h:f.h}};
    }
    function current(ticket){return ticket?.window&&ticket.projectId===windows.project()&&find(ticket.id)===ticket.window;}
    function movePointer(ticket,dx,dy) {
      if(!current(ticket)||!Number.isFinite(dx)||!Number.isFinite(dy))return false;
      const f=ticket.window;
      if(ticket.kind==='window'){f.x=ticket.original.x+dx;f.y=ticket.original.y+dy;}
      else if(ticket.kind==='resize'){f.w=ticket.original.w+dx;f.h=ticket.original.h+dy;}
      else return false;
      bounds(f);const el=[...elements.layer().querySelectorAll('[data-float-id]')].find(el=>el.dataset.floatId===f.id);
      if(el)Object.assign(el.style,{left:f.x+'px',top:f.y+'px',width:f.w+'px',height:(f.minimized?46:f.h)+'px'});
      return true;
    }
    function finishPointer(ticket){if(!current(ticket))return false;remember(ticket.window);effects.dirty();render();return true;}
    return {actionNames,isDocked,bounds,dockBounds,syncDockLayout,remember,toggleDock,setTab,open,render,updateBodies,action,beginPointer,movePointer,finishPointer};
  }
  return {create};
})();

export default FluidNetDeviceWindows;
