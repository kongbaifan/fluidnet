/* One optional current-project stream. HTTP remains responsible for history,
 * commands, terminal state and archives; this channel only accepts full samples. */
export const FluidNetLiveReadouts = (() => {
  function create({state,runState,rowFromFrame,refresh,poll,token=()=>'',
    location=()=>globalThis.location.href,supported=()=>typeof globalThis.WebSocket==='function',
    connect=(url,protocols)=>new WebSocket(url,protocols),now=()=>Date.now(),
    schedule=callback=>requestAnimationFrame(callback),cancelScheduled=id=>cancelAnimationFrame(id)}) {
    let binding=null,disposed=false;
    const selected=()=>state().projects.find(owner=>owner.id===state().activeProject);
    const eligible=owner=>owner?.run?.live && owner.run.runId && !['completed','failed','stopped','cancelled','interrupted'].includes(owner.run.status);
    const current=b=>binding===b && selected()===b.owner && runState.isCurrent(state(),b.ticket)
      && b.owner.run.runId===b.id && eligible(b.owner);
    function closeSocket(b) {
      if(b?.paint!=null){cancelScheduled(b.paint);b.paint=null;}
      if(b)b.queued=null;
      const socket=b?.socket;if(!socket)return;
      b.socket=null;
      socket.onopen=socket.onmessage=socket.onerror=socket.onclose=null;
      try{socket.close();}catch{/* The HTTP channel is still available. */}
    }
    function close(){closeSocket(binding);binding=null;}
    function retry(b,socket) {
      if(!current(b)||b.socket!==socket)return;
      closeSocket(b);b.nextAttempt=now()+[500,2000,5000][Math.min(b.attempts-1,2)];
    }
    function open(b) {
      b.attempts++;
      let socket;
      try {
        const url=new URL(`/api/v1/runs/${encodeURIComponent(b.id)}/stream`,location());
        url.protocol=url.protocol==='https:'?'wss:':'ws:';
        url.searchParams.set('full_frame','true');url.searchParams.set('interval_ms','50');
        const secret=token();socket=connect(url.href,secret?['fluidnet.bearer.'+secret]:[]);
        b.socket=socket;b.openedAt=now();
      } catch {b.nextAttempt=now()+[500,2000,5000][Math.min(b.attempts-1,2)];return;}
      socket.onerror=()=>retry(b,socket);
      socket.onclose=()=>retry(b,socket);
      socket.onmessage=event=>{
        if(!current(b)||b.socket!==socket)return;
        let message;
        try{message=JSON.parse(event.data);}catch{retry(b,socket);return;}
        if(message.type==='end') {
          b.blocked=true;closeSocket(b);Promise.resolve(poll(b.owner)).catch(()=>{});return;
        }
        // Older servers ignore full_frame and send the values-only protocol.
        // Do not reinterpret it as a full sample or repeatedly reconnect to it.
        if(message.type==='error'||message.type==='frame'&&!message.frame) {b.blocked=true;closeSocket(b);return;}
        if(message.type!=='frame')return;
        const frame=message.frame;
        if(message.status==='failed'||frame?.valid!==true||frame.full===false||!Number.isFinite(frame.sequence)
          ||!Number.isFinite(frame.time_s)||!frame.variables||typeof frame.variables!=='object')return;
        if(b.queued&&(frame.sequence<b.queued.sequence||frame.parameter_revision<b.queued.parameter_revision))return;
        b.queued=frame;
        if(b.paint==null)b.paint=schedule(()=>{
          b.paint=null;const latest=b.queued;b.queued=null;
          if(!latest||!current(b)||b.socket!==socket)return;
          const row=rowFromFrame(b.owner,latest);
          if(runState.acceptLive(b.owner.run,row))refresh(b.owner);
        });
      };
    }
    function sync() {
      if(disposed)return;
      const owner=selected();
      if(!eligible(owner)||!supported()){close();return;}
      if(!binding||!current(binding)) {
        close();binding={owner,ticket:runState.capture(state(),owner),id:owner.run.runId,socket:null,attempts:0,nextAttempt:0,blocked:false};
      }
      // A handshake that never opens must not occupy the optional channel forever.
      if(binding.socket?.readyState===0&&now()-binding.openedAt>5000)retry(binding,binding.socket);
      if(!binding.socket&&!binding.blocked&&binding.attempts<4&&now()>=binding.nextAttempt)open(binding);
    }
    function dispose(){disposed=true;close();}
    return {sync,dispose};
  }
  return {create};
})();

export default FluidNetLiveReadouts;
