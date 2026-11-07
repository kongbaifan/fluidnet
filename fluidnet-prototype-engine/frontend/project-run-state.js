/* Run ownership, accepted frame presentation and historical records; no network I/O. */
export const FluidNetProjectRunState = (() => {
  const clone=value=>value===undefined?undefined:JSON.parse(JSON.stringify(value));
  function capture(state,owner) { return {owner,run:owner.run,bench:state.bench===owner}; }
  function isCurrent(state,ticket) {
    return (ticket.bench?state.bench===ticket.owner:state.projects.some(p=>p===ticket.owner)) && ticket.owner.run===ticket.run;
  }
  function assertCurrent(state,ticket) {
    if(!isCurrent(state,ticket))throw Object.assign(Error('项目或运行已被替换，本次响应不再应用。'),{name:'AbortError'});
  }
  function setArchiveCache(run,metadata) { if(metadata)run.archiveCache=metadata;else delete run.archiveCache; }
  function advanceParameterKey(run,before,current,after) {
    if(run.parameterKey===before && current===before)run.parameterKey=after;
  }
  function prepare(run,{overviewBindings,chartBindings,parameterKey}) {
    if(!run.overviewBindings)run.overviewBindings=overviewBindings;
    if(!run.chartBindings)run.chartBindings=clone(chartBindings);
    if(run.parameterKey===undefined)run.parameterKey=parameterKey;
  }
  function present(run,row) {
    run.time=row.t;
    run.values={q:row.q,a:row.a,b:row.b,pressure:row.pressure,temperature:row.temperature};
  }
  function append(run,row) {
    const last=run.history.at(-1);
    if(last && row.t<last.t)return false;
    if(last && row.t===last.t) {
      if(!last.partial && row.partial)return false;
      run.history[run.history.length-1]=row;
    } else run.history.push(row);
    present(run,row);return true;
  }
  function mergeLive(run,data,rows,{totalRows,latest,limit=2001}) {
    for(const row of rows)append(run,row);
    if(run.history.length>limit)run.history.splice(0,run.history.length-limit);
    run.offset=totalRows;
    if(latest && run.history.length && latest.t>=run.time) {
      if(run.history.at(-1).t===latest.t)append(run,latest);else present(run,latest);
    }
    run.events=data.events.map(e=>({t:e.time_s,text:e.message || (e.command_id?`${e.command?.action || '命令'} ${e.command_status} · ${e.command_id}`:e.type)}));
    run.diagnostics=clone(data.frame?.diagnostics||[]);
    run.diagnosticTime=data.frame?.time_s??run.time;
    if(data.status==='failed')run.events.push(...(data.frame?.diagnostics||[]).map(d=>({t:data.frame.time_s,text:d.message})));
    const changed=run.status!==({queued:'solving',cancelled:'stopped',interrupted:'stopped'}[data.status]||data.status);
    run.status=({queued:'solving',cancelled:'stopped',interrupted:'stopped'})[data.status]||data.status;
    run.connectionError='';
    const terminal=['completed','failed','cancelled','interrupted'].includes(data.status);
    if(terminal){run.live=false;run.runId=null;}
    return {changed,terminal};
  }
  function reconcileArchives(state,runs,observed) {
    for(const p of state.projects)if(p.run.live && (!observed || observed.some(t=>t.owner===p&&t.run===p.run)) && !runs.some(r=>r.id===p.run.runId)) {
      p.run.live=false;p.run.runId=null;p.run.status='stopped';p.run.events.push({t:p.run.time,text:'原运行已过期，请新建运行。'});
    }
  }
  function archiveRecord(record,overview,{projectId,overviewBindings,overviewValues,chartBindings}) {
    const source=record.request.project;
    const history=overview.rows.map(frame=>({t:frame.time_s,canonical:frame.variables,variables:{},variableValues:{},diagnostics:frame.diagnostics,metrics:frame.metrics,
      ...overviewValues(overviewBindings,frame.variables)}));
    return {id:record.id,name:source.name,projectName:source.name,projectId,scope:'project',status:record.status,
      mode:record.mode==='steady'?'稳态':'动态',time:record.frame?.time_s||0,history,overviewBindings,
      events:record.events.map(e=>({t:e.time_s,text:e.message||e.type})),params:Object.fromEntries(source.instances.map(n=>[n.id,n.parameters])),
      source:'engine',sample:false,archive:record,archiveStride:overview.stride,totalRows:overview.total_rows,chartBindings};
  }
  function rememberArchive(state,item) {
    state.records=state.records.filter(r=>r.id!==item.id);state.records.unshift(item);state.records=state.records.slice(0,30);
  }
  function archiveCacheMetadata(runId, record, historyRows) {
    if (typeof runId !== 'string' || !runId || record?.id !== runId
        || typeof record.persisted_at !== 'string' || !record.persisted_at.trim()
        || !Number.isInteger(historyRows) || historyRows <= 0
        || !Number.isInteger(record.total_rows) || record.total_rows < historyRows
        || !Number.isInteger(record.persisted_rows) || record.persisted_rows < record.total_rows
        || !Number.isFinite(record.frame?.time_s) || record.frame.time_s < 0) return null;
    return {id:runId,rows:record.persisted_rows,time_s:record.frame.time_s,persisted_at:record.persisted_at};
  }
  return {capture,isCurrent,assertCurrent,archiveCacheMetadata,setArchiveCache,advanceParameterKey,prepare,present,append,mergeLive,
    reconcileArchives,archiveRecord,rememberArchive};
})();

export default FluidNetProjectRunState;
