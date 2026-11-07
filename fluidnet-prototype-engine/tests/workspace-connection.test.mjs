import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';


function fixture(serverRevision, message='本地草稿备份失败：存储空间不足') {
  const state={workspaceRevision:4,projectRevisions:{p:2},projects:[],dirty:false};
  const calls=[];
  const context=vm.createContext({window:{FluidNetControls:{}},console});
  loadFrontend(new URL('../frontend/project-model.js',import.meta.url),context);
  loadFrontend(new URL('../frontend/project-services.js',import.meta.url),context);
  const services=context.window.createProjectServices({
    ui:{state:()=>state,restoreWorkspace:()=>{throw Error(message);},parameterKey:()=>'',persist:()=>{}},
    health:()=>({capabilities:{persistent_workspace:true}}),
    request:async(path,body)=>{
      calls.push({path,body});
      if(!body)return {revision:serverRevision,data:{remote:true},project_revisions:{p:9}};
      if(body.expected_revision!==serverRevision)throw Object.assign(Error('conflict'),{status:409});
      return {revision:serverRevision+1,project_revisions:{p:3}};
    },
  });
  return {services,state,calls};
}
test('backup quota failure retains the draft but allows saving against its known revision',async()=>{
  const {services,state,calls}=fixture(4);
  assert.match(await services.loadWorkspace(),/已保留当前草稿/);
  assert.equal(state.workspaceRevision,4);
  assert.deepEqual(state.projectRevisions,{p:2});
  const receipt=await services.saveWorkspace({projects:[],draft:'preserved'});
  assert.equal(receipt.revision,5);
  assert.equal(calls[1].body.expected_revision,4);
  assert.equal(calls[1].body.data.draft,'preserved');
});
test('failed local backup cannot adopt an unseen remote revision or overwrite concurrent work',async()=>{
  const {services,state,calls}=fixture(5);
  await services.loadWorkspace(true);
  await assert.rejects(services.saveWorkspace({projects:[]}),error=>error.status===409);
  assert.equal(calls[1].body.expected_revision,4);
  assert.equal(state.workspaceRevision,4);
  assert.deepEqual(state.projectRevisions,{p:2});
});
test('invalid remote workspace is still rejected rather than treated as a quota warning',async()=>{
  const {services,calls}=fixture(4,'项目合同无效');
  await assert.rejects(services.loadWorkspace(),/项目合同无效/);
  await assert.rejects(services.saveWorkspace({projects:[]}),/工作区尚未连接/);
  assert.equal(calls.length,1);
});
