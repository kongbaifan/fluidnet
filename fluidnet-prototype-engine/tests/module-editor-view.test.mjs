import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const button=(name,label,_glyph='',attrs='')=>`<button data-action="${name}" ${attrs}>${esc(label)}</button>`;
function fixture(){
  const host=vm.createContext({window:{}});
  for(const name of ['project-model','module-editor-view'])vm.runInContext(readFileSync(new URL(`../frontend/${name}.js`,import.meta.url),'utf8'),host);
  const m=host.window.FluidNetProjectModel.moduleFromManifest({id:'view_valve',name:'试验阀 <script>',version:1,runtime:'python',solver_model:'generic',category:'阀门',
    content_hash:'source-1',definition_hash:'definition-1',entrypoint:'module:Module',source:{runtime:'def evaluate(ctx):\n    pass',design:'def design(ctx): pass'},
    ports:[{id:'in0',label:'入口',domain:'fluid',direction:'in'},{id:'out0',label:'出口',domain:'fluid',direction:'out'}],
    channels:[{id:'main',name:'有效通路',input_port:'in0',output_port:'out0',relation:'resistance',enabled:true}],
    parameters:[{id:'opening',label:'开度',value_type:'number',default:.5,minimum:0,maximum:1,writable:true}],
    variables:[{id:'result',label:'结果',source:'derived',quantity:'dimensionless'}]});
  let current=m;
  const ui={moduleTab:'drawing',editorPort:'',variableSearch:'',valueSearch:'',bank:0,arrayVar:'system:form',allBanks:false,designIndex:0,codeKind:'runtime',compileOutput:'未检查'};
  const calls=[],models=[];
  const view=host.window.FluidNetModuleEditorView.create({currentModule:()=>current,editorState:()=>ui,models:()=>models,
    parameterDefinitions:()=>[],contractText:value=>JSON.stringify(value.manifest),
    chrome:{esc,icon:()=>'',btn:button,ibtn:button,badge:esc,option:(value,label)=>`<option value="${esc(value)}">${esc(label)}</option>`,number:String},
    constants:{DOMAINS:{fluid:{label:'流体',color:'blue'}},PORT_PREFIX:{fluid:'F'},FLUIDS:[['water','水',125]],
      EDITOR_TABS:['drawing','attributes','values','models','code','channels'].map(id=>[id,id,'']),PARAM_TYPE_LABELS:{number:'数值'}},
    actions:{selectTab:value=>calls.push(['tab',value]),selectPort:value=>calls.push(['port',value]),editLabel:()=>calls.push(['label'])}});
  return {m,ui,calls,models,view,replace:value=>{current=value;}};
}

test('all authoring tabs render through public entry points without changing the module draft',()=>{
  const f=fixture(),before=JSON.stringify(f.m);
  for(const tab of ['drawing','attributes','values','models','code','channels','contract']){
    f.ui.moduleTab=tab;assert.match(f.view.renderEditor(),/试验阀 &lt;script>/);
  }
  assert.equal(JSON.stringify(f.m),before);
  const replacement={...f.m,name:'另一模块'};f.replace(replacement);
  assert.match(f.view.renderEditor(),/另一模块/);
});

test('variable channel labels ignore disabled channels and honor current filter state',()=>{
  const f=fixture();f.m.channels.unshift({...f.m.channels[0],name:'停用通路',enabled:false});
  f.m.variables=[{id:'flow',name:'FLOW',label:'流量',note:'',unit:'kg/s',type:'double',port:'in0',display:true,origin:'runtime'},
    {id:'hidden',name:'OTHER',label:'隐藏',note:'',unit:'1',type:'double',port:'out0',display:false,origin:'runtime'}];
  f.ui.onlyCommon=true;
  const html=f.view.variableRows(f.m);assert.match(html,/有效通路/);assert.doesNotMatch(html,/停用通路|OTHER/);
  f.ui.variableSearch='missing';assert.equal(f.view.variableRows(f.m),'');
});

test('published evidence requires both matching hashes and never approves a draft with stale evidence',()=>{
  const f=fixture();f.m.publishedManifest={definition_hash:'published',content_hash:'source'};f.m.dirty=true;
  f.m.manifest.validation_evidence=[{definition_hash:'published',content_hash:'different',level:'L4',status:'passed'}];
  assert.match(f.view.moduleEvidenceSummary(f.m),/发布版本：验证证据未登记/);
  f.m.manifest.validation_evidence.push({definition_hash:'published',content_hash:'source',level:'L3',status:'passed'});
  assert.match(f.view.moduleEvidenceSummary(f.m),/发布版本：网络验证通过/);
  assert.doesNotMatch(f.view.moduleEvidenceSummary(f.m),/独立解析验证通过/);
});

test('bank differences report writable values only and leave current values untouched',()=>{
  const f=fixture();f.m.variables=[{id:'a',writable:true},{id:'b',writable:false}];
  f.m.values={a:1,b:2};f.m.banks=[{a:3,b:4},{a:1,b:4}];
  assert.deepEqual(Array.from(f.view.bankDiff(f.m),v=>v.id),['a']);
  f.ui.bank=1;assert.equal(f.view.bankDiff(f.m).length,0);assert.deepEqual(f.m.values,{a:1,b:2});
});

test('authoring actions delegate only known commands to supplied shell callbacks',()=>{
  const f=fixture();assert.equal(f.view.action('editor-tab',{dataset:{value:'code'}}),true);
  assert.equal(f.view.action('select-picture',{dataset:{}}),true);assert.equal(f.view.action('edit-drawing-label',{dataset:{}}),true);
  assert.equal(f.view.action('save-module-version',{dataset:{}}),false);
  assert.deepEqual(f.calls,[['tab','code'],['port','picture'],['label']]);
});
