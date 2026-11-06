/* One pointer coordinator for the workspace. Each domain owns its mutations and rendering. */
window.FluidNetWorkspaceInteractions = (() => {
  const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
  const svgPoint=(svg,event)=>new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());
  function create({root,document:doc,getView,canvas,selection,editor,windows,charts,shell,point=svgPoint,now=()=>Date.now()}) {
    let pointer=null,ignoreClickUntil=0,mounted=false;
    const listeners=[];
    const report=error=>shell.error(error);
    const protect=fn=>event=>{try{return fn(event);}catch(error){report(error);cancel();}};
    const current=p=>p&&(!p.owner||canvas.owner()===p.owner&&canvas.page()===p.page)&&(!p.editor||editor.current()===p.editor)&&
      (!p.target||canvas.node(p.id)===p.target)&&(!p.port||p.editor.ports.find(port=>port.id===p.id)===p.port);
    function start(event,details) {
      pointer={...details,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,moved:false};
      event.preventDefault();
    }
    function release(p) {if(p)try{root.releasePointerCapture(p.pointerId);}catch{/* Already released by the browser. */}}
    function cancel(){
      const p=pointer;pointer=null;release(p);p?.box?.remove();canvas.flush();
      // Preserve the last visible geometry and record it like release. A cancelled
      // gesture must never leave changed geometry carrying a saved-state indicator.
      if(p?.moved&&current(p)){
        if(p.kind==='window'){windows.finishPointer(p.windowTicket);return;}
        if(p.kind==='draw-port'){editor.commit();return;}
        if(p.kind==='node'||p.kind==='pan'){canvas.commit();return;}
      }
      if(p)shell.render();
    }
    function pointerdown(event) {
      if(event.button!==0||getView().modal||pointer)return;
      ignoreClickUntil=0;const target=event.target;
      const windowTicket=windows.beginPointer(event);
      if(windowTicket){if(!windowTicket.blocked)start(event,{kind:'window',windowTicket});return;}
      const draw=target.closest('[data-draw-id]');
      if(draw&&draw.dataset.drawId!=='picture'){
        const module=editor.current(),port=module.ports.find(p=>p.id===draw.dataset.drawId);if(!port)return;
        editor.select(port.id);start(event,{kind:'draw-port',id:port.id,editor:module,port,original:{x:port.x,y:port.y},origin:point(editor.svg(),event)});return;
      }
      if(getView().route!=='workbench')return;
      const svg=canvas.svg(),port=target.closest('[data-port-node]'),node=target.closest('[data-node]');
      if(!target.closest('#network'))return;
      const owner=canvas.owner(),page=canvas.page();
      if(event.shiftKey&&!port&&!target.closest('[data-quick-node]')){
        if(node){const ids=new Set(selection.ids());ids.has(node.dataset.node)?ids.delete(node.dataset.node):ids.add(node.dataset.node);selection.group([...ids]);ignoreClickUntil=now()+350;event.preventDefault();return;}
        const box=doc.createElementNS('http://www.w3.org/2000/svg','rect');box.setAttribute('fill','#4488aa22');box.setAttribute('stroke','#4488aa');box.setAttribute('pointer-events','none');svg.append(box);
        start(event,{kind:'box',owner,page,svg,origin:point(svg,event),box});root.setPointerCapture(event.pointerId);return;
      }
      if(port){start(event,{kind:'port',owner,page,nodeId:port.dataset.portNode,portId:port.dataset.portId});return;}
      if(node&&!target.closest('[data-quick-node]')){
        const n=canvas.node(node.dataset.node);if(!n)return;selection.node(n.id);
        start(event,{kind:'node',id:n.id,target:n,owner,page,original:{x:n.x,y:n.y},origin:point(svg,event)});return;
      }
      if(!target.closest('[data-edge]')&&!getView().placing)start(event,{kind:'pan',owner,page,original:[...page.pan],origin:point(svg,event),matrix:svg.getScreenCTM().inverse()});
    }
    function pointermove(event) {
      if(!pointer){charts.hover(event);return;}
      if(pointer.pointerId!==event.pointerId)return;
      if(!current(pointer)){cancel();return;}
      const dx=event.clientX-pointer.startX,dy=event.clientY-pointer.startY;
      if(!pointer.moved&&Math.hypot(dx,dy)>4){pointer.moved=true;root.setPointerCapture(event.pointerId);if(pointer.kind==='node')canvas.remember();}
      if(!pointer.moved)return;
      if(pointer.kind==='window'){windows.movePointer(pointer.windowTicket,dx,dy);return;}
      if(pointer.kind==='node'){
        const n=canvas.node(pointer.id);if(!n){cancel();return;}const p=point(canvas.svg(),event);
        canvas.move(n,Math.round(pointer.original.x+p.x-pointer.origin.x),Math.round(pointer.original.y+p.y-pointer.origin.y));return;
      }
      if(pointer.kind==='pan'){
        const p=point({getScreenCTM:()=>({inverse:()=>pointer.matrix})},event);canvas.pan([pointer.original[0]+p.x-pointer.origin.x,pointer.original[1]+p.y-pointer.origin.y]);return;
      }
      if(pointer.kind==='box'){
        const p=point(pointer.svg,event),a=pointer.origin;
        for(const [key,value] of Object.entries({x:Math.min(p.x,a.x),y:Math.min(p.y,a.y),width:Math.abs(p.x-a.x),height:Math.abs(p.y-a.y)}))pointer.box.setAttribute(key,value);return;
      }
      if(pointer.kind==='draw-port'){
        const p=point(editor.svg(),event),a=pointer.original;
        editor.move(pointer.id,Math.round(clamp(a.x+(p.x-pointer.origin.x)/7.2,5,95)),Math.round(clamp(a.y+(p.y-pointer.origin.y)/4.3,10,85)));
      }
    }
    function pointerup(event) {
      if(!pointer||pointer.pointerId!==event.pointerId)return;
      const p=pointer;pointer=null;release(p);canvas.flush();p.box?.remove();
      if(!current(p))return;
      if(p.kind==='box'){
        const end=point(p.svg,event),a=p.origin;selection.group(p.page.nodes.filter(n=>n.x>=Math.min(a.x,end.x)&&n.x<=Math.max(a.x,end.x)&&n.y>=Math.min(a.y,end.y)&&n.y<=Math.max(a.y,end.y)).map(n=>n.id));ignoreClickUntil=now()+350;return;
      }
      if(!p.moved)return;ignoreClickUntil=now()+100;
      if(p.kind==='window'){windows.finishPointer(p.windowTicket);return;}
      if(p.kind==='port'){
        const hit=doc.elementFromPoint(event.clientX,event.clientY)?.closest('[data-port-node]');
        if(hit){selection.clearConnection();canvas.connect(p.nodeId,p.portId);canvas.connect(hit.dataset.portNode,hit.dataset.portId);}return;
      }
      if(p.kind==='draw-port')editor.commit();else canvas.commit();
    }
    function click(event) {
      const target=event.target,action=target.closest('[data-action]');
      if(now()<ignoreClickUntil&&!action)return;
      if(action&&!action.disabled){shell.clearContext();shell.action(action.dataset.action,action);return;}
      if(getView().modal)return;
      const port=target.closest('[data-port-node]'),quick=target.closest('[data-quick-node]'),node=target.closest('[data-node]'),edge=target.closest('[data-edge]'),draw=target.closest('[data-draw-id]');
      if(port)canvas.connect(port.dataset.portNode,port.dataset.portId);
      else if(quick)windows.open(quick.dataset.quickNode);
      else if(node)selection.single(node.dataset.node);
      else if(edge)selection.edge(edge.dataset.edge);
      else if(draw){editor.select(draw.dataset.drawId);shell.render();}
      else if(target.closest('#network')&&getView().placing)canvas.insert(getView().placing,point(canvas.svg(),event));
      else if(target.closest('[data-chart-hit]'))charts.pin(event);
      else shell.dismissContext();
    }
    function keydown(event) {
      const view=getView();if(view.modal||event.target.matches?.('input,textarea,select,[contenteditable=true]'))return;
      const target=event.target;
      if(event.key==='Enter'||event.key===' '){
        const port=target.closest('[data-port-node]'),node=target.closest('[data-node]'),draw=target.closest('[data-draw-id]');
        if(port||node||draw){event.preventDefault();if(port)canvas.connect(port.dataset.portNode,port.dataset.portId);else if(node)windows.open(node.dataset.node);else{editor.select(draw.dataset.drawId);shell.render();}return;}
      }
      if(view.route==='workbench'){
        const modified=event.ctrlKey||event.metaKey,key=event.key.toLowerCase();
        if(!modified&&!event.altKey&&key==='r'&&view.selectedNode){event.preventDefault();canvas.rotate(view.selectedNode,event.shiftKey?-1:1);}
        else if(modified&&key==='z'){event.preventDefault();canvas.undo(event.shiftKey);}
        else if(modified&&key==='y'){event.preventDefault();canvas.undo(true);}
        else if(modified&&key==='c')canvas.copy();
        else if(modified&&key==='v'){event.preventDefault();canvas.paste();}
        else if(event.key==='Delete'){if(view.selectedNode)canvas.removeNode(view.selectedNode);else if(view.selectedEdge)canvas.removeEdge(view.selectedEdge);}
      }
      if(view.route==='editor'&&view.drawing&&event.key.startsWith('Arrow'))editor.nudge(event);
    }
    function mount(){
      if(mounted)return;mounted=true;
      const on=(surface,name,fn,options)=>{const listener=protect(fn);surface.addEventListener(name,listener,options);listeners.push(()=>surface.removeEventListener(name,listener,options));};
      on(root,'pointerdown',pointerdown);on(root,'pointermove',pointermove);on(root,'pointerup',pointerup);
      on(root,'pointercancel',event=>{if(pointer?.pointerId===event.pointerId)cancel();});
      on(root,'click',click);on(root,'dblclick',event=>{if(getView().modal)return;const n=event.target.closest('[data-node]');if(n&&!event.target.closest('[data-port-node]'))windows.open(n.dataset.node);});
      on(root,'contextmenu',event=>{const n=event.target.closest('[data-node]');if(n){event.preventDefault();selection.node(n.dataset.node);shell.context(n.dataset.node,event.clientX,event.clientY);}});
      on(root,'dragstart',event=>{const el=event.target.closest('[data-drag-module]');if(el){event.dataTransfer.setData('text/plain',el.dataset.dragModule);event.dataTransfer.effectAllowed='copy';}});
      on(root,'dragover',event=>{if(event.target.closest('#network-area')){event.preventDefault();event.dataTransfer.dropEffect='copy';}});
      on(root,'drop',event=>{if(!event.target.closest('#network-area')||getView().modal)return;event.preventDefault();const id=event.dataTransfer.getData('text/plain');if(canvas.hasModule(id))canvas.insert(id,point(canvas.svg(),event));});
      on(doc,'keydown',keydown);
    }
    function destroy(){cancel();for(const remove of listeners.splice(0))remove();mounted=false;}
    const actions={
      'canvas-tab':(_,el)=>canvas.pageSelect(el.dataset.id),
      'select-mode':()=>selection.mode('select'),'connect-mode':()=>selection.mode('connect'),
      'zoom-in':()=>canvas.zoom(1.2),'zoom-out':()=>canvas.zoom(1/1.2),'fit':()=>canvas.fit(),'grid':()=>canvas.grid(),
      'undo':()=>canvas.undo(false),'redo':()=>canvas.undo(true),
      'delete-node':(_,el)=>canvas.removeNode(el.dataset.id||getView().selectedNode),
      'delete-edge':(_,el)=>canvas.removeEdge(el.dataset.id||getView().selectedEdge),
    };
    return {mount,destroy,cancel,actions,busy:()=>!!pointer,pointerdown,pointermove,pointerup,keydown,click};
  }
  return {create,svgPoint};
})();
