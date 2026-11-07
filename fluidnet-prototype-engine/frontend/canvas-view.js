import {FluidNetCanvasObservations} from './canvas-observations.js';
import {FluidNetCanvasRouting} from './canvas-routing.js';
import {FluidNetCanvasSymbols} from './canvas-symbols.js';
import {FluidNetSvgDom} from './svg-dom.js';
/* Engineering canvas presentation. Geometry and observations never modify the engine project. */
export const FluidNetCanvasView = (() => {
  const palette=['var(--orange)','#2f80ed','#27ae60','#9b51e0','#eb5757','#b77912','#219653','#1595ae'];
  const rotate=(x,y,degrees)=>{const a=degrees*Math.PI/180;return {x:x*Math.cos(a)-y*Math.sin(a),y:x*Math.sin(a)+y*Math.cos(a)};};
  function create({esc,moduleOf,ui,domains,links,quick,channels,context,circuit,circuitLabel,selectedIds}) {
    const symbols=FluidNetCanvasSymbols,observations=FluidNetCanvasObservations,routing=FluidNetCanvasRouting;
    const geometryCache=new WeakMap();
    function endpoint(owner,page,id,portId) {
      const n=page.nodes.find(item=>item.id===id),m=n&&moduleOf(owner,n),p=m?.ports.find(item=>item.id===portId);
      if(!p)return null;const d=symbols.portOffset(n,m,p),world=rotate(d.x,d.y,n.rotation||0);
      const normal=symbols.portNormal(n,m,p);
      return {x:n.x+world.x,y:n.y+world.y,node:n,nodeId:n.id,port:p,normal:rotate(normal.x,normal.y,n.rotation||0)};
    }
    function bounds(owner,n) {
      const b=symbols.bodyBounds(n,moduleOf(owner,n)),corners=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]].map(([x,y])=>rotate(x,y,n.rotation||0));
      const x=Math.min(...corners.map(p=>p.x)),y=Math.min(...corners.map(p=>p.y));
      return {id:n.id,x:n.x+x,y:n.y+y,width:Math.max(...corners.map(p=>p.x))-x,height:Math.max(...corners.map(p=>p.y))-y};
    }
    function geometry(owner,page) {
      const obstacles=page.nodes.map(n=>bounds(owner,n));
      const edges=page.edges.map(e=>({edge:e,source:endpoint(owner,page,e[1],e[2]),target:endpoint(owner,page,e[3],e[4])})).filter(e=>e.source&&e.target);
      const key=JSON.stringify([obstacles,edges.map(e=>[e.edge,e.source.x,e.source.y,e.source.normal,e.target.x,e.target.y,e.target.normal])]);
      let cached=geometryCache.get(page);
      if(cached?.key!==key){cached={key,obstacles,routes:new Map(edges.map(e=>[e.edge[0],routing.route({...e,obstacles})]))};geometryCache.set(page,cached);}
      return cached;
    }
    function observation(owner,page,edge,ctx) {
      const sourceNode=page.nodes.find(n=>n.id===edge[1]),targetNode=page.nodes.find(n=>n.id===edge[3]);
      return observations.edge({edge,sourceNode,targetNode,sourceModule:moduleOf(owner,sourceNode),targetModule:moduleOf(owner,targetNode),row:ctx.row,mode:ctx.mode,scale:ctx.scale});
    }
    function midpoint(points) {
      const lengths=points.slice(1).map((p,i)=>Math.hypot(p.x-points[i].x,p.y-points[i].y)),total=lengths.reduce((a,b)=>a+b,0);let left=total/2;
      for(let i=0;i<lengths.length;i++){if(left<=lengths[i]&&lengths[i]){const a=points[i],b=points[i+1],t=left/lengths[i];return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,angle:Math.atan2(b.y-a.y,b.x-a.x)*180/Math.PI};}left-=lengths[i];}
      return {x:points[0]?.x||0,y:points[0]?.y||0,angle:0};
    }
    function edgeMarkup(owner,page,edge,route,ctx,mini=false) {
      const id=edge[0],o=observation(owner,page,edge,ctx),c=circuit(owner,edge[1]+':'+edge[2]);
      const color=ctx.mode==='circuit'?(c?palette[c.id%palette.length]:'var(--orange)'):o.color||'var(--muted)';
      const mid=midpoint(route.points),direction=o.direction,known=o.known===true;
      const title=[`${edge[1]}:${edge[2]} ↔ ${edge[3]}:${edge[4]}`,c?circuitLabel(c):'',o.label,o.reason,ctx.stale?'结果与当前项目不一致，物理显示已停用':'',route.blocked?'自动避让未完成：'+route.reason:''].filter(Boolean).join(' · ');
      const animated=!mini&&ctx.animate&&direction&&o.flowKnown&&!route.blocked;
      const arrow=!mini&&o.flowKnown&&direction?`<path data-flow-arrow d="M -5 -3 L 4 0 L -5 3" fill="none" stroke="${color}" stroke-width="1.5" transform="translate(${mid.x},${mid.y}) rotate(${mid.angle+(direction<0?180:0)})"/>`:'';
      const label=!mini&&(ctx.labels||route.blocked)?`<text class="canvas-edge-label" x="${mid.x}" y="${mid.y-9}" text-anchor="middle">${esc(route.blocked?'⚠ 避让未完成':o.label)}</text>`:'';
      return `<title>${esc(title)}</title><path d="${route.path}" data-trace-edge="${esc(id)}" class="net-line${ui().selectedEdge===id?' selected':''}" style="stroke:${color};stroke-width:${ui().selectedEdge===id?3.4:o.width||1.8}"/>${mini?'':`<path d="${route.path}" class="net-hit" data-edge="${esc(id)}" role="button" aria-label="连接 ${esc(edge[1])} 到 ${esc(edge[3])} · ${esc(o.label)}" tabindex="0"/>`}${animated?`<path d="${route.path}" class="canvas-flow-animation" style="stroke:${color};animation-direction:${direction<0?'reverse':'normal'}"/>`:''}${arrow}${label}<metadata data-edge-known="${known}" data-edge-direction="${direction??'unknown'}" data-route-blocked="${!!route.blocked}"/>`;
    }
    const hitRadius=symbols.hitRadius;
    function nodeMarkup(owner,n,ctx,mini) {
      const m=moduleOf(owner,n),local=symbols.hitBounds(n,m),corners=[[local.x,local.y],[local.x+local.width,local.y],[local.x,local.y+local.height],[local.x+local.width,local.y+local.height]].map(([x,y])=>rotate(x,y,n.rotation||0));
      const x=Math.min(...corners.map(p=>p.x)),top=Math.min(...corners.map(p=>p.y)),b={x,y:top,width:Math.max(...corners.map(p=>p.x))-x,height:Math.max(...corners.map(p=>p.y))-top};
      const y=symbols.labelY(n,m),status=observations.node({node:n,module:m,row:ctx.row});
      const chosen=!mini&&(ui().selectedNode===n.id||selectedIds().includes(n.id));
      const ports=m.ports.map(p=>{const d=symbols.portOffset(n,m,p),hit=hitRadius(n,m,p),connected=!!links.atPort(owner,n.id,p.id);
        return `<g transform="rotate(${n.rotation||0})"><g class="port-group${ui().connecting?.nodeId===n.id&&ui().connecting?.portId===p.id?' pending':''}" ${mini?'':`data-port-node="${esc(n.id)}" data-port-id="${esc(p.id)}" role="button" aria-label="${esc(n.id+' '+p.label)}" tabindex="0"`}><title>${esc(n.id+' · '+p.label+' · '+(domains[p.domain]?.label||p.domain))}${connected?' · 已连接':''}</title><circle cx="${d.x}" cy="${d.y}" r="${Math.min(3.5,hit)}" class="net-port${connected?' connected':''}"/>${mini?'':`<circle cx="${d.x}" cy="${d.y}" r="${hit}" class="port-hit"/>`}</g></g>`;}).join('');
      return `<g transform="translate(${n.x},${n.y})" class="net-node${chosen?' selected':''}" ${mini?'':`data-node="${esc(n.id)}" tabindex="0" role="button" aria-label="${esc(n.id+' '+n.name)}"`} data-canvas-state="${status.state}" style="--canvas-device-stroke:${status.color||'var(--muted)'}"><rect class="node-hit" x="${b.x-6}" y="${b.y-6}" width="${b.width+12}" height="${Math.max(b.height+12,y+44-b.y)}" fill="transparent" pointer-events="all"/><rect class="node-selection" x="${b.x-5}" y="${b.y-5}" width="${b.width+10}" height="${b.height+10}" rx="5"/>${symbols.symbol(n,m,{mini,esc})}${mini?'':channels(n)}${ports}${mini?'':`<text class="canvas-device-state" x="0" y="${b.y-10}" text-anchor="middle">${esc(status.label)}</text><text class="node-code" x="0" y="${y}" text-anchor="middle">${esc(n.id)}</text><text class="node-name" x="0" y="${y+16}" text-anchor="middle">${esc(n.name)}</text><g transform="translate(0,${y-44})">${quick(n,m)}</g>`}</g>`;
    }
    function markup(owner,page,mini=false) {
      const ctx=mini?{row:null,mode:'circuit',animate:false,labels:false}:context(owner),g=geometry(owner,page);
      return page.edges.filter(e=>g.routes.has(e[0])).map(e=>`<g data-canvas-edge="${esc(e[0])}">${edgeMarkup(owner,page,e,g.routes.get(e[0]),ctx,mini)}</g>`).join('')+page.nodes.map(n=>nodeMarkup(owner,n,ctx,mini)).join('');
    }
    function paint(svg,owner,page) {
      if(!svg)return;const ctx=context(owner),g=geometry(owner,page),edgeElements=new Map([...svg.querySelectorAll('[data-canvas-edge]')].map(el=>[el.dataset.canvasEdge,el]));
      for(const e of page.edges){const el=edgeElements.get(e[0]),route=g.routes.get(e[0]);if(el&&route){const html=edgeMarkup(owner,page,e,route,ctx);if(el._canvasMarkup!==html){FluidNetSvgDom.patch(el,html);el._canvasMarkup=html;}}}
      const nodes=new Map(page.nodes.map(n=>[n.id,n]));
      for(const el of svg.querySelectorAll('[data-node]')){const n=nodes.get(el.dataset.node);if(!n)continue;
        el.setAttribute('transform',`translate(${n.x},${n.y})`);el.classList.toggle('selected',ui().selectedNode===n.id||selectedIds().includes(n.id));
        for(const port of el.querySelectorAll('[data-port-id]'))port.classList.toggle('pending',ui().connecting?.nodeId===n.id&&ui().connecting?.portId===port.dataset.portId);
        const s=observations.node({node:n,module:moduleOf(owner,n),row:ctx.row});el.dataset.canvasState=s.state;el.style.setProperty('--canvas-device-stroke',s.color||'var(--muted)');const text=el.querySelector('.canvas-device-state');if(text)text.textContent=s.label;}
    }
    function move(svg,owner,page,id) {
      if(!svg)return;const n=page.nodes.find(n=>n.id===id),el=[...svg.querySelectorAll('[data-node]')].find(el=>el.dataset.node===id);if(!n||!el)return;
      el.setAttribute('transform',`translate(${n.x},${n.y})`);el.classList.add('selected');
      const obstacles=page.nodes.map(n=>bounds(owner,n)),ctx=context(owner);
      const edgeElements=new Map([...svg.querySelectorAll('[data-canvas-edge]')].map(el=>[el.dataset.canvasEdge,el]));
      for(const edge of page.edges.filter(e=>e[1]===id||e[3]===id)){const source=endpoint(owner,page,edge[1],edge[2]),target=endpoint(owner,page,edge[3],edge[4]),element=edgeElements.get(edge[0]);if(!source||!target||!element)continue;FluidNetSvgDom.patch(element,edgeMarkup(owner,page,edge,routing.route({source,target,obstacles}),ctx));delete element._canvasMarkup;}
      geometryCache.delete(page);
    }
    return {markup,paint,move,endpoint,bounds,hitRadius};
  }
  return {create};
})();

export default FluidNetCanvasView;
