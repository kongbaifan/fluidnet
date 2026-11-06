/* Presentation-only geometry: no mutation of module contracts, instances or physical ports. */
window.FluidNetCanvasSymbols = (() => {
  const SCALE=.15, PORT_GAP=12;
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const value=(input,fallback,minimum=-Infinity,maximum=Infinity)=>{
    const n=typeof input==='number'?input:typeof input==='string'&&input.trim()?Number(input):NaN;
    return Number.isFinite(n)?Math.min(maximum,Math.max(minimum,n)):fallback;
  };
  const kind=m=>String(m?.manifest?.solver_model||m?.solver_model||m?.kind||m?.id||'');
  function family(m){
    const type=kind(m),id=String(m?.kind||m?.id||'');
    if(m?.manifest?.composite||m?.composite)return 'group';
    if(type==='pressure_source'||id==='source'||/boundary|pressure_reference/.test(id))return 'source';
    if(type==='junction'||id==='junction')return 'junction';
    if(/compressor|condensing_unit/.test(type+' '+id))return 'compressor';
    if(/heat_pump/.test(type+' '+id))return 'heat-pump';
    if(/chiller/.test(type+' '+id))return 'chiller';
    if(/horizontal|headed_receiver/.test(type+' '+id))return 'horizontal-tank';
    if(/tank|vessel|receiver|drum|tower_pool/.test(type+' '+id))return 'tank';
    if(/cold_room|storage_room|air_room|room_thermal/.test(type+' '+id))return 'room';
    if(/header|collector|manifold|branch_box|mixing_box/.test(type+' '+id))return 'header';
    if(/cooling_tower/.test(type+' '+id))return 'tower';
    if(/condenser/.test(type+' '+id))return 'condenser';
    if(/fancoil|fan_coil|fcu_|ahu|fahu|coil|air_cooler|evaporator/.test(type+' '+id))return 'coil';
    if(/check_valve/.test(type+' '+id)||id==='check')return 'check';
    if(/valve|damper/.test(type+' '+id))return 'valve';
    if(/pump/.test(type+' '+id))return 'pump';
    if(/fan/.test(type+' '+id))return 'fan';
    if(/exchanger|recuperator|tube_bundle|recovery|subcooler/.test(type+' '+id))return 'exchanger';
    if(/filter/.test(type+' '+id))return 'filter';
    if(/heater|boiler/.test(type+' '+id))return 'heater';
    if(/pipe|duct|refrigerant_line|capillary|bend/.test(type+' '+id))return 'pipe';
    if(/pid|controller/.test(type+' '+id))return 'controller';
    if(/sensor|meter/.test(type+' '+id))return 'sensor';
    return 'module';
  }
  function customized(m){
    const d=m?.drawing;
    return !!d&&(d.shape&&d.shape!=='rectangle'||value(d.width,32)!==32||value(d.height,30)!==30||
      d.label!=null&&String(d.label)!==String(m.name||''));
  }
  const sizes={source:[34,34],junction:[10,10],pump:[38,44],compressor:[48,44],fan:[40,40],
    valve:[34,24],check:[36,32],pipe:[44,10],tank:[40,54],'horizontal-tank':[60,40],
    room:[48,44],header:[36,42],tower:[44,48],condenser:[52,38],coil:[52,38],exchanger:[52,42],
    'heat-pump':[54,40],chiller:[54,40],filter:[36,36],heater:[50,38],controller:[50,38],sensor:[30,30],
    group:[54,42],module:[50,38]};
  function bodyBounds(n,m){
    const d=m?.drawing||{},custom=customized(m),size=custom
      ? [value(d.width,32,15,60)*6*SCALE,value(d.height,30,15,55)*4*SCALE]
      : sizes[family(m)];
    return {x:-size[0]/2,y:-size[1]/2,width:size[0],height:size[1]};
  }
  const layouts=new WeakMap();
  function portLayout(n,m){
    if(!m||typeof m!=='object')return [];
    const key=JSON.stringify([family(m),customized(m),/^B[24](?:-|$)/.test(n?.id||''),/^N2(?:-|$)/.test(n?.id||''),
      (m.ports||[]).map(p=>[p.id,p.direction,p.x,p.y])]);
    const prior=layouts.get(m);if(prior?.key===key)return prior.points;
    const points=computePorts(n,m);layouts.set(m,{key,points});return points;
  }
  function computePorts(n,m){
    const ports=m?.ports||[],type=family(m);
    if(type==='source'&&!customized(m)&&ports.length===1&&
      (!Number.isFinite(ports[0].x)||[78,80].includes(ports[0].x))&&(!Number.isFinite(ports[0].y)||ports[0].y===50))
      return [{id:ports[0].id,x:/^B[24](?:-|$)/.test(n?.id||'')?-28:28,y:0}];
    if(type==='junction'&&!customized(m)&&ports.length===3&&ports.every(p=>{
      const expected={in0:[20,50],out0:[80,30],out1:[80,70]}[p.id];
      return expected&&(!Number.isFinite(p.x)||p.x===expected[0])&&(!Number.isFinite(p.y)||p.y===expected[1]);
    })){
      const flip=/^N2(?:-|$)/.test(n?.id||'')?-1:1;
      return ports.map(p=>({id:p.id,x:p.id==='in0'?-24*flip:24*flip,y:p.id==='out0'?-18:p.id==='out1'?18:0}));
    }
    const points=ports.map(p=>{
      const siblings=ports.filter(q=>q.direction===p.direction),index=siblings.indexOf(p);
      const x=value(p.x,p.direction==='in'?20:80,5,95),y=value(p.y,siblings.length>1?30+40*index/(siblings.length-1):50,10,85);
      const distances=[['left',x],['right',100-x],['top',y],['bottom',100-y]];
      const side=distances.reduce((best,next)=>next[1]<best[1]?next:best)[0];
      return {id:p.id,x:(x-50)*720/100*SCALE,y:(y-50)*430/100*SCALE,side};
    });
    for(const side of ['left','right','top','bottom']){
      const axis=side==='left'||side==='right'?'y':'x',group=points.filter(p=>p.side===side).sort((a,b)=>a[axis]-b[axis]);
      if(group.length<2)continue;
      const oldCenter=(group[0][axis]+group.at(-1)[axis])/2;
      for(let i=1;i<group.length;i++)group[i][axis]=Math.max(group[i][axis],group[i-1][axis]+PORT_GAP);
      const shift=(group[0][axis]+group.at(-1)[axis])/2-oldCenter;
      group.forEach(p=>{p[axis]-=shift;});
    }
    // Different side groups can meet at a corner. Separate only actual collisions.
    for(let i=0;i<points.length;i++)for(let attempts=0;attempts<ports.length*3;attempts++){
      if(points.slice(0,i).every(p=>Math.hypot(p.x-points[i].x,p.y-points[i].y)>=PORT_GAP-.001))break;
      if(points[i].side==='top'||points[i].side==='bottom')points[i].x+=PORT_GAP;
      else points[i].y+=PORT_GAP;
    }
    return points.map(({id,x,y,side})=>({id,x,y,side}));
  }
  function portOffset(n,m,p){
    const point=portLayout(n,m).find(item=>item.id===p?.id);
    return point?{x:point.x,y:point.y}:{x:0,y:0};
  }
  function portNormal(n,m,p){
    const point=portLayout(n,m).find(item=>item.id===p?.id);
    const normals={left:{x:-1,y:0},right:{x:1,y:0},top:{x:0,y:-1},bottom:{x:0,y:1}};
    return point?.side?{...normals[point.side]}:{x:point?.x<0?-1:1,y:0};
  }
  function hitRadius(n,m,p){
    const a=portOffset(n,m,p),distances=(m.ports||[]).filter(q=>q!==p).map(q=>{const b=portOffset(n,m,q);return Math.hypot(a.x-b.x,a.y-b.y);});
    return Math.min(10,Math.max(1,Math.min(...distances)*.44));
  }
  function hitBounds(n,m){
    const box=bodyBounds(n,m),ports=portLayout(n,m),pad=10;
    const left=Math.min(box.x,...ports.map(p=>p.x)),right=Math.max(box.x+box.width,...ports.map(p=>p.x));
    const top=Math.min(box.y,...ports.map(p=>p.y)),bottom=Math.max(box.y+box.height,...ports.map(p=>p.y));
    return {x:left-pad,y:top-pad,width:right-left+2*pad,height:bottom-top+2*pad};
  }
  const labelY=(n,m)=>{
    const box=hitBounds(n,m),angle=value(n?.rotation,0,-36000,36000)*Math.PI/180;
    const corners=[[box.x,box.y],[box.x+box.width,box.y],[box.x,box.y+box.height],[box.x+box.width,box.y+box.height]];
    return Math.max(...corners.map(([x,y])=>x*Math.sin(angle)+y*Math.cos(angle)))+6;
  };
  function copyPresentation(source,target){
    if(!source||!target)return target;
    if(source.drawing&&typeof source.drawing==='object'&&!Array.isArray(source.drawing))
      target.drawing={shape:source.drawing.shape==='circle'?'circle':'rectangle',width:value(source.drawing.width,32,15,60),
        height:value(source.drawing.height,30,15,55),label:String(source.drawing.label??source.name??'').slice(0,200)};
    for(const p of target.ports||[]){
      const original=source.ports?.find(q=>q.id===p.id&&q.domain===p.domain&&q.direction===p.direction);
      if(original){p.x=value(original.x,p.x,5,95);p.y=value(original.y,p.y,10,85);}
    }
    return target;
  }
  function glyph(type,short){
    const box='<rect x="-24" y="-18" width="48" height="36" rx="4"/>';
    switch(type){
      case 'junction':return '<circle r="5" fill="var(--canvas-device-stroke,var(--orange))"/>';
      case 'source':return '<circle r="17"/><text y="4">P</text>';
      case 'pump':return '<circle r="17"/><path d="M-5-9 10 0-5 9Z M-13 21H13"/>';
      case 'compressor':return '<path d="M-23-17H23V17H-23Z M-16-10 16 0-16 10Z M-8-17V-21H8V-17"/>';
      case 'fan':return '<circle r="19"/><circle r="3"/><path d="M0-3C-13-17 16-17 3 0 M3 0C20 7 6 22 0 3 M0 3C-17 10-20-10-3 0"/>';
      case 'valve':return '<path d="M-17-12 17 12V-12L-17 12Z"/>';
      case 'check':return '<path d="M-17-12 17 12V-12L-17 12Z M0-15V15"/>';
      case 'pipe':return '<rect x="-22" y="-5" width="44" height="10" rx="2"/>';
      case 'tank':return '<rect x="-19" y="-26" width="38" height="52" rx="7"/><path d="M-17 1Q-8-5 0 1T17 1 M-19-17Q0-11 19-17"/>';
      case 'horizontal-tank':return '<rect x="-29" y="-15" width="58" height="30" rx="14"/><path d="M-20 3H20 M-17 14V19 M17 14V19 M-15-14V14 M15-14V14"/>';
      case 'room':return '<path d="M-23-13 0-22 23-13V21H-23Z M9 21V2H-1V21 M-15-5H-6V4H-15Z"/>';
      case 'header':return '<rect x="-8" y="-20" width="16" height="40" rx="5"/><path d="M-17-12H-8 M-17 0H-8 M-17 12H-8 M8-12H17 M8 0H17 M8 12H17"/>';
      case 'tower':return '<path d="M-13-23H13L20 22H-20Z M-17 13H17 M-15 4H15 M-13-5H13"/><circle cy="-15" r="5"/><path d="M-4-18 4-12 M4-18-4-12"/>';
      case 'condenser':return box+'<path d="M-18-10V10H-8V-10H2V10H12V-10H18"/><circle cx="15" cy="-12" r="4"/>';
      case 'coil':return box+'<path d="M-19-11H16Q22-6 16-2H-16Q-22 3-16 7H18 M-12-14V14 M0-14V14 M12-14V14"/>';
      case 'exchanger':return box+'<path d="M-19-10H19 M-19 10H19 M-12-14 5 14 M-2-14 15 14"/>';
      case 'heat-pump':return box+'<path d="M-16 0H16 M10-5 16 0 10 5 M-8-9V9 M-12-5-4 5 M-12 5-4-5"/><path d="M5-10C12-2 0-1 7 8"/>';
      case 'chiller':return box+'<path d="M0-12V12 M-11-6 11 6 M-11 6 11-6 M-4-8 0-4 4-8 M-4 8 0 4 4 8"/>';
      case 'filter':return '<path d="M-17-17H17V17H-17Z M-12-16 16 12 M-17-8 8 17 M-5-17 17 5"/>';
      case 'heater':return box+'<path d="M0-13C8-5 13 0 8 9S-9 15-10 5C-11-2-6-3-5-8C-4-3 0-2 0-13Z"/>';
      case 'controller':return box+'<text y="4">PID</text>';
      case 'sensor':return '<circle r="14"/><path d="M-8 5 6-6"/><circle cy="5" r="2"/>';
      case 'group':return '<rect x="-25" y="-20" width="50" height="40" rx="5" stroke-dasharray="4 2"/><rect x="-17" y="-7" width="12" height="14" rx="2"/><rect x="5" y="-7" width="12" height="14" rx="2"/><path d="M-5 0H5 M-21-14H-7"/>';
      default:return box+`<text y="4">${short}</text>`;
    }
  }
  function symbol(n,m,{mini=false}={}){
    const type=family(m),box=bodyBounds(n,m),custom=customized(m),rotation=value(n?.rotation,0,-36000,36000);
    const label=String(m?.drawing?.label??m?.name??m?.code??m?.id??'模块'),short=escape([...label].slice(0,custom?Math.max(2,Math.floor(box.width/9)):4).join(''));
    const stems=portLayout(n,m).map(p=>{
      const x=Math.max(box.x,Math.min(box.x+box.width,p.x)),y=Math.max(box.y,Math.min(box.y+box.height,p.y));
      return x===p.x&&y===p.y?'':`<path d="M${x} ${y}L${p.x} ${p.y}"/>`;
    }).join('');
    const shape=custom?(m.drawing.shape==='circle'
      ?`<ellipse rx="${box.width/2}" ry="${box.height/2}"/>`
      :`<rect x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" rx="4"/>`)+(!mini?`<text y="3" font-size="9">${short}</text>`:'')
      :glyph(type,mini?'':short);
    const rendered=shape.replaceAll('<path ','<path fill="none" ').replaceAll('<text ','<text text-anchor="middle" fill="var(--canvas-device-stroke,var(--text))" stroke="none" ');
    return `<g data-canvas-family="${type}" transform="rotate(${rotation})" stroke="var(--canvas-device-stroke,var(--muted))" fill="var(--surface)" font-size="11" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><title>${escape(label)}</title><g fill="none">${stems}</g><g class="canvas-device-glyph">${rendered}</g></g>`;
  }
  return {symbol,portOffset,portNormal,hitRadius,bodyBounds,hitBounds,labelY,copyPresentation,family};
})();
