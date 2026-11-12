import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const context=vm.createContext({window:{},document:{createElement:()=>({dataset:{},textContent:''})}});
loadFrontend(new URL('../frontend/device-panel.js',import.meta.url),context);

// A parameter row with a retained draft; refresh must change its availability, not its value.
function fixture(owner,frame,specs=[]) {
  const input={dataset:{instanceParam:'opening'},disabled:false,value:'45'};
  const slider={dataset:{instanceParam:'opening'},disabled:false,value:'45'};
  const actual={dataset:{deviceActualParam:'opening'},textContent:''};
  const pending={hidden:false,textContent:'',className:''};
  let pendingValue=1;
  let note;
  const row={
    querySelector:selector=>selector==='[data-parameter-owner]'?note
      :selector==='.param-title'?{append:value=>{note=value;}}:input,
    querySelectorAll:()=>[input,slider],
  };
  const shell={querySelectorAll:selector=>selector==='.parameter-row'?[row]
    :selector==='[data-device-actual-param]'?[actual]:selector==='[data-pending-for]'?[pending]:[]};
  const node={id:'V1',name:'阀门',params:{opening:80},draft:{opening:45}};
  const panel=context.window.createDevicePanel({
    ownerOfInstance:()=>owner,
    moduleOf:()=>({variables:[{id:'param:opening',origin:'parameter',param:'opening',unit:'%'}]}),
    observation:()=>({canonicalKey:'V1.param.opening_ratio',canonicalScale:.01,canonicalOffset:0}),
    panelRow:()=>frame,parameterKey:()=>owner.run.parameterKey,
    esc:String,number:String,btn:()=>'',ibtn:()=>'',option:()=>'',model:()=>null,
    getState:()=>({models:[]}),pendingCount:()=>pendingValue,deviceParamSpecs:()=>specs,
    paramDefs:()=>[['opening','阀门开度','%',0,100,1,80]],
  });
  return {refresh:()=>panel.refresh(shell,node),markup:()=>panel.body({tab:'parameters'},node),
    input,slider,note:()=>note,actual,pending,setPending:value=>{pendingValue=value;},setFrame:value=>{frame=value;}};
}

const script=(id,enabled)=>({id,language:'python',enabled,outputs:['V1.param.opening_ratio']});

test('quiet pending badge becomes visible for unapplied edits and clears after application without changing the input',()=>{
  const view=fixture({run:{live:false},controllers:[]});
  view.setPending(0);view.refresh();assert.equal(view.pending.hidden,true);
  view.setPending(2);view.refresh();assert.equal(view.pending.hidden,false);
  assert.equal(view.pending.textContent,'2 项待应用');assert.equal(view.pending.className,'badge warn');
  view.setPending(0);view.refresh();assert.equal(view.pending.hidden,true);
  assert.equal(view.input.value,'45');
});

test('editing a running script cannot change the current run parameter ownership',()=>{
  const running=script('original',true);
  const owner={run:{live:true,parameterKey:JSON.stringify({controllers:[],controls:[running]})},
    controlPrograms:[script('original',false)]};
  const view=fixture(owner);
  view.refresh();
  assert.equal(view.input.disabled,true);
  assert.equal(view.slider.disabled,true);
  assert.match(view.note().textContent,/original/);
  assert.equal(view.input.value,'45');

  // Once this run ends, the edited (disabled) script no longer owns the next run.
  owner.run.live=false;
  view.refresh();
  assert.equal(view.input.disabled,false);
  assert.equal(view.note().textContent,'');
  assert.equal(view.input.value,'45');
});

test('a script enabled for the next run does not lock the current run parameter',()=>{
  const owner={run:{live:true,parameterKey:JSON.stringify({controllers:[],controls:[]})},
    controlPrograms:[script('next_run',true)]};
  const view=fixture(owner);
  view.refresh();
  assert.equal(view.input.disabled,false);
  assert.equal(view.note().textContent,'');

  owner.run.live=false;
  view.refresh();
  assert.equal(view.input.disabled,false);
  assert.match(view.note().textContent,/下次运行由 控制脚本 next_run/);
});

test('a PID in manual mode still owns its output parameter until the run ends',()=>{
  const owner={run:{live:true,parameterKey:JSON.stringify({controllers:[
    {id:'flow',instance_id:'V1',parameter_id:'opening_ratio',mode:'manual'}],controls:[]})},controllers:[]};
  const view=fixture(owner,{t:1,canonical:{'controller.flow.mode':'manual'}});
  view.refresh();
  assert.equal(view.input.disabled,true);
  assert.match(view.note().textContent,/PID flow · 手动输出/);
});

test('PID ownership stays frozen while its displayed mode follows actual sampled control',()=>{
  const owner={controllers:[],run:{live:true,parameterKey:JSON.stringify({controllers:[
    {id:'flow',instance_id:'V1',parameter_id:'opening_ratio',mode:'auto'}],controls:[]})}};
  const before=JSON.stringify(owner),view=fixture(owner,{t:1,canonical:{'controller.flow.mode':'manual'}});
  view.refresh();assert.match(view.note().textContent,/手动输出/);assert.equal(view.input.disabled,true);
  view.setFrame({t:2,canonical:{}});view.refresh();
  assert.match(view.note().textContent,/模式未记录/);assert.equal(view.input.disabled,true);
  assert.equal(JSON.stringify(owner),before);
});

test('sampled parameter values use the run frame and do not overwrite applied settings or drafts',()=>{
  const owner={run:{live:true,time:1,parameterKey:JSON.stringify({controllers:[],controls:[]})}};
  const view=fixture(owner,{t:1,canonical:{'V1.param.opening_ratio':.65}});
  view.refresh();
  assert.match(view.markup(),/已应用设置 80 %/);
  assert.equal(view.actual.textContent,'采样值 65 %');
  assert.equal(view.input.value,'45');

  // Missing output remains missing rather than falling back to the configured 80%.
  view.setFrame({t:1,canonical:{}});
  view.refresh();
  assert.equal(view.actual.textContent,'采样值 — %');
  view.setFrame(undefined);
  view.refresh();
  assert.equal(view.actual.textContent,'');
});

test('configured controls cannot unlock readonly or non-runtime contract parameters',()=>{
  const owner={run:{live:false},controllers:[]};
  const view=fixture(owner,null,[{id:'opening',value_type:'number',writable:false,runtime:false}]);
  view.refresh();assert.equal(view.input.disabled,true);assert.equal(view.slider.disabled,true);
  const writable=fixture(owner,null,[{id:'opening',value_type:'number',writable:true,runtime:false}]);
  writable.refresh();assert.equal(writable.input.disabled,false);
  owner.run.live=true;writable.refresh();assert.equal(writable.input.disabled,true);
  owner.run.live=false;writable.input.dataset.configReadonly='true';writable.refresh();assert.equal(writable.input.disabled,true);
});
