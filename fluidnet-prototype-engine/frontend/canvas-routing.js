/* Deterministic orthogonal routing around device bodies. Geometry only; never changes topology. */
export const FluidNetCanvasRouting = (() => {
  const EPS=1e-7,MAX_RECTS=256,MAX_VISITED=30000;
  const finite=n=>typeof n==='number'&&Number.isFinite(n)&&Math.abs(n)<Number.MAX_SAFE_INTEGER/8;
  const point=p=>p&&finite(p.x)&&finite(p.y);
  const same=(a,b)=>Math.abs(a.x-b.x)<EPS&&Math.abs(a.y-b.y)<EPS;
  const distance=(a,b)=>Math.abs(a.x-b.x)+Math.abs(a.y-b.y);
  const inside=(p,r)=>p.x>r.left+EPS&&p.x<r.right-EPS&&p.y>r.top+EPS&&p.y<r.bottom-EPS;
  const move=(a,b)=>({x:Math.sign(b.x-a.x),y:Math.sign(b.y-a.y)});
  const opposing=(a,b)=>a.x===-b.x&&a.y===-b.y;
  function simplify(input){
    const points=[];
    for(const p of input){
      if(points.length&&same(points.at(-1),p))continue;
      while(points.length>1){
        const a=points.at(-2),b=points.at(-1);
        if((Math.abs(a.x-b.x)<EPS&&Math.abs(b.x-p.x)<EPS||Math.abs(a.y-b.y)<EPS&&Math.abs(b.y-p.y)<EPS)&&
          distance(a,p)+EPS>=distance(a,b)+distance(b,p))points.pop();else break;
      }
      points.push({x:p.x,y:p.y});
    }
    return points;
  }
  const pathOf=points=>points.map((p,i)=>`${i?'L':'M'} ${p.x} ${p.y}`).join(' ');
  function clearSegment(a,b,rects,except){
    if(Math.abs(a.x-b.x)>EPS&&Math.abs(a.y-b.y)>EPS)return false;
    const horizontal=Math.abs(a.y-b.y)<EPS;
    for(const r of rects){
      if(r===except)continue;
      if(horizontal){
        if(a.y>r.top+EPS&&a.y<r.bottom-EPS&&Math.max(a.x,b.x)>r.left+EPS&&Math.min(a.x,b.x)<r.right-EPS)return false;
      }else if(a.x>r.left+EPS&&a.x<r.right-EPS&&Math.max(a.y,b.y)>r.top+EPS&&Math.min(a.y,b.y)<r.bottom-EPS)return false;
    }
    return true;
  }
  function normal(endpoint,own,other){
    const input=endpoint.normal;
    if(point(input)&&(input.x||input.y))return Math.abs(input.x)>=Math.abs(input.y)?{x:Math.sign(input.x),y:0}:{x:0,y:Math.sign(input.y)};
    if(own){
      const sides=[{d:Math.abs(endpoint.x-own.left),x:-1,y:0},{d:Math.abs(endpoint.x-own.right),x:1,y:0},
        {d:Math.abs(endpoint.y-own.top),x:0,y:-1},{d:Math.abs(endpoint.y-own.bottom),x:0,y:1}].sort((a,b)=>a.d-b.d);
      return {x:sides[0].x,y:sides[0].y};
    }
    return Math.abs(other.x-endpoint.x)>=Math.abs(other.y-endpoint.y)
      ?{x:Math.sign(other.x-endpoint.x)||1,y:0}:{x:0,y:Math.sign(other.y-endpoint.y)||1};
  }
  function escape(endpoint,n,own,lead){
    let length=lead;
    if(own)length=Math.max(length,n.x>0?own.right-endpoint.x+1:n.x<0?endpoint.x-own.left+1:n.y>0?own.bottom-endpoint.y+1:endpoint.y-own.top+1);
    return {x:endpoint.x+n.x*length,y:endpoint.y+n.y*length};
  }
  function heap(){
    const data=[];
    const less=(a,b)=>a.f<b.f||a.f===b.f&&(a.g<b.g||a.g===b.g&&a.key<b.key);
    return {get length(){return data.length;},push(value){
      let i=data.length;data.push(value);
      while(i){const p=(i-1)>>1;if(!less(value,data[p]))break;data[i]=data[p];i=p;}data[i]=value;
    },pop(){
      const first=data[0],last=data.pop();if(!data.length)return first;
      let i=0;while(i*2+1<data.length){let c=i*2+1;if(c+1<data.length&&less(data[c+1],data[c]))c++;if(!less(data[c],last))break;data[i]=data[c];i=c;}
      data[i]=last;return first;
    }};
  }
  function route({source,target,obstacles=[],clearance=6,lead=12,maxVisited=12000}={}){
    if(!point(source)||!point(target))return {path:'',points:[],blocked:true,reason:'invalid-endpoint',visited:0};
    const s={x:source.x,y:source.y},t={x:target.x,y:target.y};
    const fallback=reason=>{const points=simplify([s,{x:(s.x+t.x)/2,y:s.y},{x:(s.x+t.x)/2,y:t.y},t]);return {path:pathOf(points),points,blocked:true,reason,visited:0};};
    if(!Array.isArray(obstacles)||obstacles.length>MAX_RECTS)return fallback('obstacle-budget');
    if(obstacles.some(r=>!point(r)||!finite(r.width)||!finite(r.height)||r.width<0||r.height<0))return fallback('invalid-obstacle');
    clearance=finite(clearance)?Math.max(0,Math.min(clearance,100)):6;
    lead=finite(lead)?Math.max(1,Math.min(lead,200)):12;
    maxVisited=Number.isInteger(maxVisited)?Math.max(1,Math.min(maxVisited,MAX_VISITED)):12000;
    const rects=obstacles.map(r=>({id:r.id,left:r.x-clearance,right:r.x+r.width+clearance,top:r.y-clearance,bottom:r.y+r.height+clearance}))
      .sort((a,b)=>a.left-b.left||a.top-b.top||a.right-b.right||a.bottom-b.bottom||String(a.id).localeCompare(String(b.id)));
    const sourceId=source.nodeId??source.node?.id,targetId=target.nodeId??target.node?.id;
    const ownS=sourceId==null?null:rects.find(r=>r.id===sourceId),ownT=targetId==null?null:rects.find(r=>r.id===targetId);
    const ns=normal(source,ownS,t),nt=normal(target,ownT,s),a=escape(s,ns,ownS,lead),b=escape(t,nt,ownT,lead);
    // Only the short stub may cross its own body. Another device never becomes exempt.
    if(!clearSegment(s,a,rects,ownS)||!clearSegment(b,t,rects,ownT)||rects.some(r=>inside(a,r)||inside(b,r)))return fallback('blocked-port');
    const allowed=points=>{
      const compact=simplify(points);
      if(compact.length>1&&(opposing(move(compact[0],compact[1]),ns)||opposing(move(compact.at(-1),compact.at(-2)),nt)))return false;
      return compact.every((p,i)=>!i||clearSegment(compact[i-1],p,rects));
    };
    const finish=(middle,visited=0)=>{const points=simplify([s,...middle,t]);return {path:pathOf(points),points,blocked:false,reason:null,visited};};
    const cost=points=>points.reduce((sum,p,i)=>sum+(i?distance(points[i-1],p):0),0)+Math.max(0,simplify(points).length-2)*12;
    const candidates=[[a,b],[a,{x:b.x,y:a.y},b],[a,{x:a.x,y:b.y},b]];
    // A handful of outer lanes handles common same-side ports and blocked direct lines cheaply.
    const bounds={left:Math.min(a.x,b.x,...rects.map(r=>r.left)),right:Math.max(a.x,b.x,...rects.map(r=>r.right)),
      top:Math.min(a.y,b.y,...rects.map(r=>r.top)),bottom:Math.max(a.y,b.y,...rects.map(r=>r.bottom))};
    for(const y of [(a.y+b.y)/2,bounds.top-lead,bounds.bottom+lead])candidates.push([a,{x:a.x,y},{x:b.x,y},b]);
    for(const x of [(a.x+b.x)/2,bounds.left-lead,bounds.right+lead])candidates.push([a,{x,y:a.y},{x,y:b.y},b]);
    const direct=candidates.filter(allowed).sort((x,y)=>cost(x)-cost(y));
    // Straight or one-bend routes need no search. Outer routes remain a bounded fallback if search is expensive.
    if(direct.length&&simplify(direct[0]).length<=3)return finish(direct[0]);
    const xs=[...new Set([a.x,b.x,bounds.left-lead,bounds.right+lead,...rects.flatMap(r=>[r.left,r.right])])].sort((x,y)=>x-y);
    const ys=[...new Set([a.y,b.y,bounds.top-lead,bounds.bottom+lead,...rects.flatMap(r=>[r.top,r.bottom])])].sort((x,y)=>x-y);
    if(xs.length*ys.length>40000)return direct.length?finish(direct[0]):fallback('grid-budget');
    const width=xs.length,start=ys.indexOf(a.y)*width+xs.indexOf(a.x),goal=ys.indexOf(b.y)*width+xs.indexOf(b.x);
    const coords=index=>({x:xs[index%width],y:ys[Math.floor(index/width)]});
    const key=(index,direction)=>index*3+direction;
    const queue=heap(),best=new Map(),parents=new Map(),segmentCache=new Map();
    const startDirection=ns.x?1:2,startKey=key(start,startDirection);best.set(startKey,0);
    queue.push({index:start,direction:startDirection,key:startKey,g:0,f:distance(a,b)});
    let visited=0;
    while(queue.length&&visited<maxVisited){
      const current=queue.pop();if(current.g!==best.get(current.key))continue;visited++;
      if(current.index===goal){
        const points=[];let cursor=current.key;
        while(cursor!==undefined){points.push(coords(Math.floor(cursor/3)));cursor=parents.get(cursor);}
        return finish(points.reverse(),visited);
      }
      const x=current.index%width,y=Math.floor(current.index/width),p=coords(current.index);
      const neighbors=[];if(x>0)neighbors.push(current.index-1);if(x+1<width)neighbors.push(current.index+1);if(y>0)neighbors.push(current.index-width);if(y+1<ys.length)neighbors.push(current.index+width);
      for(const index of neighbors){
        const q=coords(index),direction=p.y===q.y?1:2,vector=move(p,q);
        if(current.index===start&&opposing(vector,ns)||index===goal&&opposing(move(q,p),nt))continue;
        const segment=current.index<index?current.index+':'+index:index+':'+current.index;
        if(!segmentCache.has(segment))segmentCache.set(segment,clearSegment(p,q,rects));
        if(!segmentCache.get(segment))continue;
        const g=current.g+distance(p,q)+(direction!==current.direction?12:0),nextKey=key(index,direction);
        if(g>=(best.get(nextKey)??Infinity)-EPS)continue;
        best.set(nextKey,g);parents.set(nextKey,current.key);queue.push({index,direction,key:nextKey,g,f:g+distance(q,b)});
      }
    }
    if(direct.length)return finish(direct[0],visited);
    return {...fallback(queue.length?'search-budget':'no-route'),visited};
  }
  return {route};
})();

export default FluidNetCanvasRouting;
