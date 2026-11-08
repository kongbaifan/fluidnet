import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const button=(name,label,_glyph='',attrs='')=>`<button data-action="${name}" ${attrs}>${esc(label)}</button>`;
function fixture(){
  const host=vm.createContext({window:{}});loadFrontend(new URL('../frontend/run-results-view.js',import.meta.url),host);
  const project={id:'P',name:'当前工程',run:{}},run={history:[],events:[]},records=[];
  const charts={source:'live',range:'window',series:{q:true,a:true},compare:false},ui={runFilter:'all',selectedRecord:'',archivedRuns:[]};
  const registry=new Map(),calls=[],bindings=[],sampleCalls=[];
  const series={q:{unit:'kg/s',name:'流量',color:'blue',short:'Q'},a:{unit:'kg/s',name:'支路',color:'orange',short:'A'}};
  let overview={q:{label:'主流量',short:'Q',unit:'kg/s'}};
  const view=host.window.FluidNetRunResultsView.create({currentRun:()=>run,currentProject:()=>project,records:()=>records,
    chartState:()=>charts,viewState:()=>ui,overviewSeries:()=>overview,chartBindings:()=>bindings,
    extraValue:(row,v,live)=>{sampleCalls.push(live);return row[v.id]??null;},series,registerChart:(id,data)=>registry.set(id,data),measureWidth:()=>600,
    comparisonMarkup:()=>'',reportAvailable:archive=>!!archive?.report,runControls:()=>'<button>运行</button>',
    chrome:{esc,icon:()=>'',btn:button,ibtn:button,badge:esc,option:(value,label)=>`<option value="${value}">${esc(label)}</option>`,number:String,heading:esc,clockLabel:t=>String(t)},
    actions:{selectRecord:id=>calls.push(['select',id]),recordCurves:id=>calls.push(['curves',id]),toggleSeries:key=>calls.push(['toggle',key]),removeVariable:id=>calls.push(['remove',id])}});
  return {project,run,records,charts,ui,registry,calls,bindings,sampleCalls,view,setOverview:value=>{overview=value;}};
}

test('record filtering and selection follow the current view without modifying archived data',()=>{
  const f=fixture();f.records.push({id:'failed',name:'失败 <script>',projectName:'旧工程',status:'failed',time:1,history:[],params:{x:1},archive:{frame:{diagnostics:[{message:'输入 <invalid>'}]}}},
    {id:'done',name:'完成',projectName:'另一工程',status:'completed',time:2,history:[{t:2,q:3}],params:{}});
  const before=JSON.stringify(f.records);f.ui.runFilter='failed';f.ui.selectedRecord='done';
  const failed=f.view.renderRuns();assert.match(failed,/失败 &lt;script>/);assert.match(failed,/输入 &lt;invalid>/);assert.doesNotMatch(failed,/另一工程/);
  assert.match(failed,/data-action="record-curves"[^>]*disabled/);
  f.ui.runFilter='completed';assert.match(f.view.renderRuns(),/另一工程/);assert.equal(JSON.stringify(f.records),before);
});

test('chart paths preserve gaps, hidden series, time bounds and project-local comparison',()=>{
  const f=fixture(),history=[{t:1,q:2,a:1},{t:2,q:null,a:2},{t:3,q:4,a:3}];
  f.charts.series.a=false;f.records.push({source:'engine',projectId:'other',history:[{t:1,q:999}]},{source:'engine',projectId:'P',history:[{t:0,q:8},{t:1,q:3},{t:3,q:5},{t:4,q:9}]});
  const markup=f.view.chartSvg(history,['q','a'],'chart',true);
  const paths=[...markup.matchAll(/<path\b[^>]*\sd="([^"]*)"/g)].map(match=>match[1]);
  assert.equal(paths.length,2);assert.equal((paths[0].match(/M /g)||[]).length,2);assert.equal((paths[1].match(/[ML] /g)||[]).length,2);
  const data=f.registry.get('chart');assert.equal(data.rows,history);assert.deepEqual(Array.from(data.keys),['q']);assert.equal(data.minT,1);assert.equal(data.maxT,3);
});

test('historical observations use their own data and suppress live edit controls',()=>{
  const f=fixture();f.charts.source='archive';f.run.history=[{t:1,temp:300},{t:2,temp:null}];f.bindings.push({id:'temp',label:'旧温度 <probe>',unit:'K'});
  const before=JSON.stringify(f.run),html=f.view.extraChartsMarkup();assert.match(html,/旧温度 &lt;probe>/);assert.doesNotMatch(html,/data-action="remove-chart-var"/);
  assert.deepEqual(f.sampleCalls,[false,false,false]);assert.equal(f.registry.get('extra-chart-0').rows.length,1);assert.equal(JSON.stringify(f.run),before);
});

test('curves with no physical samples show the empty state and do not fabricate stored results',()=>{
  const f=fixture();f.setOverview({});assert.match(f.view.renderCurves(),/还没有当前运行数据/);
  assert.equal(f.run.history.length,0);assert.equal(f.registry.size,0);
});

test('result actions delegate identities without accepting unknown commands',()=>{
  const f=fixture();for(const [name,data] of [['select-record',{id:'A'}],['record-curves',{id:'B'}],['toggle-series',{value:'q'}],['remove-chart-var',{id:'temp'}]])assert.equal(f.view.action(name,{dataset:data}),true);
  assert.equal(f.view.action('delete-archive',{dataset:{id:'A'}}),false);
  assert.deepEqual(f.calls,[['select','A'],['curves','B'],['toggle','q'],['remove','temp']]);
});

test('checkpoint resume is offered only for terminal dynamic archives with a complete snapshot',()=>{
  const f=fixture(),record={id:'source',name:'旧运行',projectName:'旧项目',status:'completed',time:60,history:[],params:{},
    archive:{mode:'dynamic',checkpoint_available:true,checkpoint_time_s:60}};
  f.records.push(record);
  assert.match(f.view.renderRuns(),/data-action="resume-archive" data-id="source"/);
  assert.match(f.view.renderRuns(),/续算快照/);
  for(const change of [{status:'running'},{status:'completed',archive:{mode:'steady',checkpoint_available:true}},
    {archive:{mode:'dynamic',checkpoint_available:false}}]) {
    Object.assign(record,change);assert.doesNotMatch(f.view.renderRuns(),/data-action="resume-archive"/);
  }
});

function resumeFixture() {
  const host=vm.createContext({window:{}});
  loadFrontend(new URL('../frontend/engine-client.js',import.meta.url),host);
  const original={id:'original',pages:[{nodes:[{draft:{heat:999}}]}],run:{history:[{t:60}],status:'completed'}};
  let state={projects:[original]},resumeDelay=null;
  const record={id:'source',mode:'dynamic',status:'completed',checkpoint_available:true,checkpoint_time_s:60,
    request:{project:{id:'original',name:'旧参数'},dt_s:.5,execution_mode:'fast',speed_ratio:2}};
  const source={id:'original',name:'已接受参数',instances:[{id:'D1',parameters:{heat:123}}]},calls=[],converted=[],polls=[];
  const resume=host.window.createArchiveResumer({state:()=>state,uuid:()=> 'copy',emptyRun:()=>({history:[],events:[]}),
    parameterKey:owner=>JSON.stringify(owner.pages),
    request:async(path,body)=>{calls.push([path,body]);if(path.endsWith('/checkpoint-project'))return source;
      if(path.endsWith('/resume')){if(resumeDelay)await resumeDelay;return {run_id:'child',time_s:60};}return record;},
    exchangeDocument:async project=>{converted.push(project);return {project:{id:project.id,name:project.name,
      pages:[{nodes:[{params:project.instances[0].parameters}]}],solver:{},moduleSnapshots:{frozen:true}},modules:[]};},
    attach:document=>state.projects.push(document.project),poll:async owner=>{polls.push(owner);owner.run.status='paused';}});
  return {resume,record,source,calls,converted,polls,original,state:()=>state,replace:()=>{state={projects:[]};},delay:value=>{resumeDelay=value;}};
}

test('resume creates a paused child bound to an independent accepted-project copy and preserves drafts',async()=>{
  const f=resumeFixture(),before=JSON.stringify(f.original);
  const owner=await f.resume('source',120);
  assert.equal(f.converted[0],f.source);
  assert.equal(owner.id,'resume-copy');assert.equal(owner.name,'已接受参数 · 快照续算');
  assert.equal(owner.solver.duration,120);assert.equal(owner.solver.dt,.5);
  assert.equal(owner.run.id,'child');assert.equal(owner.run.runId,'child');assert.equal(owner.run.live,true);
  assert.equal(owner.run.status,'paused');assert.equal(owner.run.time,60);
  assert.equal(f.polls[0],owner);assert.equal(f.state().projects[1],owner);
  assert.equal(JSON.stringify(f.original),before);
  const post=f.calls.find(([path])=>path.endsWith('/resume'));
  assert.deepEqual(JSON.parse(JSON.stringify(post[1])),{duration_s:120,start_paused:true});
});

test('invalid or missing checkpoint and elapsed end times never submit a child run',async()=>{
  for(const end of [60,59,NaN,604801]) {
    const f=resumeFixture();await assert.rejects(f.resume('source',end),/终止时刻/);
    assert.equal(f.calls.length,1);assert.equal(f.state().projects.length,1);
  }
  const f=resumeFixture();f.record.checkpoint_available=false;
  await assert.rejects(f.resume('source',120),/完整会话快照/);assert.equal(f.calls.length,1);
});

test('concurrent resume submits once and replaced workspace never receives a late child binding',async()=>{
  const f=resumeFixture();let release;f.delay(new Promise(resolve=>{release=resolve;}));
  const one=f.resume('source',120),two=f.resume('source',120);
  while(!f.calls.some(([path])=>path.endsWith('/resume')))await Promise.resolve();
  f.replace();release();
  await assert.rejects(one,/已创建暂停运行 child/);await assert.rejects(two,/已创建暂停运行 child/);
  assert.equal(f.calls.filter(([path])=>path.endsWith('/resume')).length,1);
  assert.equal(f.state().projects.length,0);assert.equal(f.polls.length,0);
});
