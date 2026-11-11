/* Live run transport. Accepted frame/state rules remain in project-run-state. */
export const FluidNetRunCommands = (() => {
  function create({state,request,runState,pending,key,parameterKey,normalize,runMetadata,trendVariables,
    emptyRun,prepareRun,rowFromFrame,confirmArchiveCache,persist,render,refresh,message,liveRows=2001,
    now=()=>Date.now(),uuid=()=>crypto.randomUUID(),delay=ms=>new Promise(resolve=>setTimeout(resolve,ms)),
    abortController=()=>new AbortController()}) {
    const polling=new WeakMap(),overviewLoading=new WeakMap(),overviews=new Map(),creations=new WeakMap();
    const current=ticket=>runState.isCurrent(state(),ticket);
    const aborted=()=>Object.assign(Error('本次运行请求已取消。'),{name:'AbortError'});
    function assertActive(ticket,controller) {
      runState.assertCurrent(state(),ticket);
      if(controller?.signal.aborted)throw aborted();
    }
    function pollLive(owner) {
      const ticket=runState.capture(state(),owner),id=ticket.run.runId;
      if(!id)return Promise.resolve();
      if(polling.has(ticket.run))return polling.get(ticket.run);
      const work=(async()=>{
        try {
          const data=await request('/runs/'+id);
          if(!current(ticket)||ticket.run.runId!==id)return;
          const history=await request(`/runs/${id}/history?offset=${ticket.run.offset||0}`);
          if(!current(ticket)||ticket.run.runId!==id)return;
          await confirmArchiveCache(owner,ticket.run,data,history.total_rows,['completed','failed','cancelled','interrupted'].includes(data.status));
          if(!current(ticket)||ticket.run.runId!==id)return;
          prepareRun(owner);
          const beforeSample=runState.sampleKey(runState.completeRow(ticket.run));
          const beforeMeta=JSON.stringify([ticket.run.events,ticket.run.diagnostics,ticket.run.connectionError||'']);
          const outcome=runState.mergeLive(ticket.run,data,history.rows.map(frame=>rowFromFrame(owner,frame)),{
            totalRows:history.total_rows,latest:data.frame?.valid?rowFromFrame(owner,data.frame):null,limit:liveRows});
          if(state().charts?.range==='all'&&now()-(overviews.get(id)?.at||0)>2000)loadOverview(owner);
          if(outcome.terminal)persist();
          if(outcome.changed)render();
          else if(history.rows.length||beforeSample!==runState.sampleKey(runState.completeRow(ticket.run))
            ||beforeMeta!==JSON.stringify([ticket.run.events,ticket.run.diagnostics,ticket.run.connectionError||'']))refresh();
        } catch(error) {
          if(!current(ticket)||ticket.run.runId!==id)return;
          ticket.run.connectionError=error.message;message('运行连接中断，正在重连：'+error.message,true);
        }
      })();
      polling.set(ticket.run,work);
      return work.finally(()=>{if(polling.get(ticket.run)===work)polling.delete(ticket.run);});
    }
    async function confirmedCommand(owner,body) {
      const ticket=runState.capture(state(),owner),id=ticket.run.runId;
      if(!id)throw Error('没有活动运行');
      runState.assertCurrent(state(),ticket);
      const receipt=await request(`/runs/${id}/command`,{command_id:uuid(),...body});
      runState.assertCurrent(state(),ticket);
      if(receipt.command_status==='rejected')throw Error(receipt.message);
      for(let i=0;i<200;i++) {
        runState.assertCurrent(state(),ticket);
        const {events}=await request(`/runs/${id}/events`);
        runState.assertCurrent(state(),ticket);
        const event=events.findLast(item=>item.command_id===receipt.command_id);
        if(event?.command_status==='rejected')throw Error(event.message);
        if(event?.command_status==='applied') {
          await pollLive(owner);
          runState.assertCurrent(state(),ticket);
          return event;
        }
        await delay(50);
      }
      throw Error('命令已接收，尚未确认生效；请查看运行事件，勿重复提交。');
    }
    function isCreating(owner) {
      const creation=creations.get(owner);
      return !!creation&&!creation.attached&&current(creation.ticket);
    }
    async function stopCreatedRun(id) {
      // Cleanup belongs to the server ID, not to a possibly replaced UI owner.
      // Creation starts paused, so even a lost response cannot start a timeline.
      try {
        const receipt=await request(`/runs/${id}/command`,{command_id:uuid(),action:'stop'});
        if(receipt.command_status==='rejected')throw Error(receipt.message);
        if(receipt.command_status==='applied'||['completed','failed','cancelled','interrupted'].includes(receipt.status))return;
        for(let i=0;i<200;i++) {
          const record=await request('/runs/'+id);
          if(['completed','failed','cancelled','interrupted'].includes(record.status))return;
          await delay(50);
        }
        throw Error('停止命令尚未确认生效');
      } catch(error) {
        if(error.code!=='RUN_ALREADY_FINISHED')throw error;
      }
    }
    async function liveCommand(owner,action) {
      let ticket=runState.capture(state(),owner),controller=null,creation=null;
      try {
        runState.assertCurrent(state(),ticket);
        const activeCreation=creations.get(owner);
        if(action==='stop'&&activeCreation?.attached&&activeCreation.id===ticket.run.runId)activeCreation.stopped=true;
        if(isCreating(owner)) {
          const active=creations.get(owner);
          if(action==='stop') {
            active.stopped=true;active.controller.abort();
            // Abort normalization, but let an already submitted POST return its
            // ID. The creator confirms cleanup before releasing the UI lock.
            await active.finished;
          }
          return;
        }
        if(owner.run.live&&owner.run.runId) {
          try {await confirmedCommand(owner,{action:action==='run'?'resume':action});return;}
          catch(error) {
            if(error.code!=='RUN_ALREADY_FINISHED')throw error;
            await pollLive(owner);
            runState.assertCurrent(state(),ticket);
            owner.run.live=false;owner.run.runId=null;persist();
            if(action==='pause'){render();return;}
          }
        }
        if(action==='stop'||action==='pause') {
          // Keep completed results and editable drafts when closing the local task.
          if(action==='stop'&&!owner.run.live&&!owner.run.runId&&!pending.has(owner.id)) {
            owner.run.status='stopped';persist();render();
          }
          return;
        }
        if(pending.has(owner.id))return;
        controller=abortController();pending.set(owner.id,controller);
        const before=key(owner),parameters=parameterKey(owner);
        let finish;
        creation={ticket,controller,previousStatus:ticket.run.status,parameters,id:null,attached:false,stopped:false,
          finished:new Promise(resolve=>{finish=resolve;}),finish:()=>finish()};
        creations.set(owner,creation);
        // Preserve prior accepted frames while making startup visible to settings
        // guards and the stop button. Failure restores this same result object.
        ticket.run.status='solving';render();
        const project=await normalize(owner,controller.signal);
        assertActive(ticket,controller);
        if(before!==key(owner))throw Error('请求期间项目已变化，请重新运行。');
        // Never abort an accepted creation POST and lose its ID. The run cannot
        // advance until this UI has claimed the response and confirms resume/step.
        const result=await request('/runs?background=true',{project,mode:'dynamic',...runMetadata(owner),
          duration_s:owner.solver.continuous?null:owner.solver.duration,dt_s:owner.solver.dt,
          execution_mode:owner.solver.executionMode||'realtime',speed_ratio:owner.solver.speedRatio||1,
          start_paused:true,history:'trend',trend_variables:trendVariables(owner),
          ...(owner.solver.historyWindow?{history_window:Math.min(20001,Math.max(10,owner.solver.historyWindow))}:{})});
        creation.id=result.run_id;
        if(!creation.id)throw Error('计算服务未返回运行编号。');
        assertActive(ticket,controller);
        if(before!==key(owner))throw Error('请求期间项目已变化，原请求可在运行档案查看，请重新运行。');
        owner.run={...emptyRun(),source:'engine',status:'solving',id:result.run_id,runId:result.run_id,live:true,offset:0,parameterKey:parameters};
        creation.attached=true;
        ticket=runState.capture(state(),owner);
        persist();render();
        await confirmedCommand(owner,{action:action==='step'?'step':'resume'});
        assertActive(ticket,controller);
        await pollLive(owner);
      } catch(error) {
        let cleanupError;
        if(creation?.id&&(!creation.attached||!current(ticket)||controller.signal.aborted)) {
          try {await stopCreatedRun(creation.id);}
          catch(failure){cleanupError=failure;}
        }
        if(cleanupError) {
          const explanation=`启动未完成，停止运行 ${creation.id} 尚未确认：${cleanupError.message}。请在该运行中重试停止。`;
          if(current(ticket)) {
            if(!creation.attached) {
              owner.run={...emptyRun(),source:'engine',status:'paused',id:creation.id,runId:creation.id,
                live:true,offset:0,parameterKey:creation.parameters};
              creation.attached=true;ticket=runState.capture(state(),owner);
            }
            ticket.run.connectionError=explanation;persist();render();
          }
          message(explanation,true);
        } else if(creation&&!creation.attached&&current(ticket)) {
          ticket.run.status=creation.stopped||controller.signal.aborted?'stopped':creation.previousStatus;
          persist();render();
        } else if(creation?.attached&&controller?.signal.aborted&&current(ticket))await pollLive(owner);
        if(!cleanupError&&current(ticket)&&!creation?.stopped&&!controller?.signal.aborted&&error.name!=='AbortError')message(error.message,true);
      } finally {
        if(controller&&pending.get(owner.id)===controller)pending.delete(owner.id);
        if(creation) {
          if(creations.get(owner)===creation)creations.delete(owner);
          creation.finish();
        }
      }
    }
    function loadOverview(owner) {
      const ticket=runState.capture(state(),owner),id=ticket.run.id;
      if(!id||ticket.run.source!=='engine')return Promise.resolve(null);
      if(overviewLoading.has(ticket.run))return overviewLoading.get(ticket.run);
      const work=(async()=>{
        try {
          const data=await request(`/runs/${id}/overview`);
          if(!current(ticket))return null;
          const entry={rows:data.rows.map(frame=>rowFromFrame(owner,frame)),stride:data.stride,total:data.total_rows,at:now()};
          overviews.set(id,entry);refresh();return entry;
        } catch(error) {
          if(current(ticket))overviews.set(id,{rows:null,error:error.message,at:now()});
          return null;
        }
      })();
      overviewLoading.set(ticket.run,work);
      return work.finally(()=>{if(overviewLoading.get(ticket.run)===work)overviewLoading.delete(ticket.run);});
    }
    return {pollLive,confirmedCommand,liveCommand,isCreating,loadOverview,overview:id=>overviews.get(id)};
  }
  return {create};
})();

export default FluidNetRunCommands;
