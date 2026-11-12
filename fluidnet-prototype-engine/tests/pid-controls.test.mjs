import {test} from 'node:test';
import assert from 'node:assert/strict';
import {FluidNetControls as controls} from '../frontend/control-programs.js';

const controller=()=>({id:'room',instance_id:'coil',parameter_id:'fan_ratio',measurement:'Room.temperature_k',
  setpoint:255.15,mode:'auto',manual_output:null,minimum:0,maximum:1,sample_s:.1,kp:-1,ki:0,kd:0});
function fixture(){
  const c=controller(),script={id:'supervisor',language:'python',enabled:true,
    outputs:['controller.room.setpoint','controller.room.mode','controller.room.manual_output']};
  const owner={controllers:[c],controlPrograms:[{...script,enabled:false}],
    run:{live:true,status:'paused',parameterKey:JSON.stringify({controllers:[c],controls:[script]})}};
  const values={'controller.room.setpoint':260.15,'controller.room.mode':'manual','controller.room.manual_output':.4};
  return {c,owner,values};
}

test('PID inputs reject empty and nonfinite values without converting them to zero',()=>{
  const c=controller(),original=structuredClone(c);
  for(const field of ['setpoint','manual_output','kp','ki','kd','sample_s','minimum','maximum'])
    for(const raw of ['', ' ', null, undefined, NaN, Infinity, -Infinity, 'NaN', 'Infinity', true])
      assert.throws(()=>controls.controllerValue(c,field,raw),/有效数值/);
  assert.deepEqual(c,original);
  assert.equal(controls.controllerValue(c,'setpoint','0'),0);
  assert.equal(controls.controllerValue(c,'manual_output','0'),0);
});

test('PID updates respect sampling limits, output bounds and manual output as one configuration',()=>{
  const c=controller();
  assert.equal(controls.controllerValue(c,'sample_s','60'),60);
  for(const raw of ['0','-1','60.1'])assert.throws(()=>controls.controllerValue(c,'sample_s',raw),/采样周期/);
  assert.throws(()=>controls.controllerValue(c,'minimum',1),/下限必须小于/);
  assert.throws(()=>controls.controllerValue(c,'maximum',0),/下限必须小于/);
  for(const raw of ['-.01','1.01'])assert.throws(()=>controls.controllerValue(c,'manual_output',raw),/手动输出超出范围/);
  assert.throws(()=>controls.controllerValue({...c,manual_output:.8},'maximum',.7),/手动输出超出范围/);
  assert.equal(controls.controllerValue(c,'mode','manual'),'manual');
  assert.throws(()=>controls.controllerValue(c,'mode',''),/自动或手动/);
});

test('live PID fields show sampled values and frozen script ownership without rewriting initial settings',()=>{
  const {c,owner,values}=fixture(),before=JSON.stringify(owner);
  const view=controls.controllerView(owner,c,values);
  assert.equal(view.fields.setpoint.value,260.15);assert.equal(view.fields.setpoint.initial,255.15);
  assert.equal(view.fields.mode.value,'manual');assert.equal(view.fields.mode.initial,'auto');
  assert.equal(view.fields.manual_output.value,.4);assert.equal(view.fields.manual_output.initial,null);
  for(const field of controls.controllerRuntimeFields){assert.equal(view.fields[field].owner,'supervisor');assert.equal(view.fields[field].editable,false);}
  assert.equal(JSON.stringify(owner),before);
});

test('missing sampled values remain unknown and differ from an explicit unset manual output',()=>{
  const {c,owner}=fixture();
  const unknown=controls.controllerView(owner,c,{});
  for(const field of controls.controllerRuntimeFields){assert.equal(unknown.fields[field].known,false);assert.equal(unknown.fields[field].value,undefined);assert.equal(unknown.fields[field].editable,false);}
  const unset=controls.controllerView(owner,c,{'controller.room.manual_output':null});
  assert.equal(unset.fields.manual_output.known,true);assert.equal(unset.fields.manual_output.value,null);
});

test('editing the next script cannot seize or release fields in an existing PID run',()=>{
  const {c,owner,values}=fixture();
  owner.controlPrograms=[];assert.equal(controls.controllerView(owner,c,values).fields.mode.owner,'supervisor');
  owner.run.parameterKey=JSON.stringify({controllers:[c],controls:[]});
  owner.controlPrograms=[{id:'next',enabled:true,language:'python',outputs:['controller.room.mode']}];
  const active=controls.controllerView(owner,c,values);
  assert.equal(active.fields.mode.owner,'');assert.equal(active.fields.mode.editable,true);
  owner.run.live=false;owner.run.status='stopped';
  const next=controls.controllerView(owner,c,values);
  assert.equal(next.fields.mode.value,'auto');assert.equal(next.fields.mode.editable,true);
});

test('starting and legacy paused tasks keep controller settings locked',()=>{
  const c=controller();
  for(const status of ['solving','running','paused']){
    const view=controls.controllerView({run:{status,live:false},controllers:[c]},c,{});
    assert.equal(view.active,true);assert.ok(controls.controllerRuntimeFields.every(field=>!view.fields[field].editable));
  }
  const legacy=controls.controllerView({run:{live:true,parameterKey:'unknown'},controllers:[c]},c,
    {'controller.room.setpoint':260.15,'controller.room.mode':'manual','controller.room.manual_output':.4});
  assert.equal(legacy.ownershipKnown,false);assert.equal(legacy.fields.setpoint.editable,false);
});

test('accepted settings survive an older paused sample but cannot replace missing or newer observations',()=>{
  const {c,owner,values}=fixture();owner.run.parameterKey=JSON.stringify({controllers:[c],controls:[]});
  owner.run.controllerReceipts={room:{setpoint:{value:261.15,parameterRevision:4,time:1}}};
  const before=JSON.stringify(owner);
  const pending=controls.controllerView(owner,c,values,{parameterRevision:3,t:1});
  assert.equal(pending.fields.setpoint.value,261.15);assert.equal(pending.fields.setpoint.awaitingSample,true);
  const current=controls.controllerView(owner,c,values,{parameterRevision:4,t:2});
  assert.equal(current.fields.setpoint.value,260.15);assert.equal(current.fields.setpoint.awaitingSample,false);
  const missing=controls.controllerView(owner,c,{}, {parameterRevision:5,t:3});
  assert.equal(missing.fields.setpoint.value,undefined);assert.equal(missing.fields.setpoint.known,false);
  assert.equal(JSON.stringify(owner),before);
});
