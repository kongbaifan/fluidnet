import {test} from 'node:test';
import assert from 'node:assert/strict';
import {FluidNetColdRoomControls as controls} from '../frontend/cold-room-controls.js';
const fixture=()=>{
 const p={run:{status:'ready'},controllers:[1,2].map(i=>({id:'feedback-'+i,measurement:'North.state.temperature_k',instance_id:'Coil-'+i,parameter_id:'fan_ratio',kp:-.8,maximum:1,mode:'auto',setpoint:249.15}))};
 const devices=[{node:{id:'North',name:'北库'},model:'cold_room'},...[1,2].map(i=>({node:{id:'Coil-'+i},model:'air_cooler'}))];
 return {p,groups:controls.groups(p,devices)};
};
test('targets bind actual rooms and update both coolers atomically in Celsius',()=>{
 const {p,groups}=fixture();assert.equal(groups.length,1);controls.applyTargets(p,groups,{North:-22});
 assert.ok(p.controllers.every(c=>c.setpoint===251.15));
 for(const value of ['',Infinity,-273.15]){assert.throws(()=>controls.applyTargets(p,groups,{North:value}));assert.equal(p.controllers[0].setpoint,251.15);}
 p.run.live=true;assert.throws(()=>controls.applyTargets(p,groups,{North:-24}),/停止/);
});
test('capacity notice needs real high temperature and saturated or stopped coolers',()=>{
 const {groups}=fixture(),values={'North.state.temperature_k':250.15,'Coil-1.param.running':0,'Coil-2.param.running':1,'controller.feedback-2.output':1};
 const observe=()=>controls.observation(groups[0],k=>values[k],true);
 assert.equal(observe().warning,true);assert.match(observe().status,/上限/);
 values['controller.feedback-2.output']=.8;assert.equal(observe().warning,false);
 delete values['controller.feedback-2.output'];assert.equal(observe().warning,false);
 assert.equal(controls.observation(groups[0],k=>values[k],false).temperature,null);
 values['North.state.temperature_k']=249.15;assert.equal(observe().status,'温度正常');
});
test('different targets or manual loops do not claim automatic success',()=>{
 const {p,groups}=fixture();p.controllers[0].setpoint=248.15;
 assert.match(controls.observation(groups[0],()=>249.15,true).status,/不一致/);
 p.controllers[0].setpoint=249.15;p.controllers[0].mode='manual';
 assert.match(controls.observation(groups[0],()=>249.15,true).status,/手动/);
});

test('graph coolers retain shared room controls and show actual defrost stages',()=>{
 const {p}=fixture(),devices=[{node:{id:'North'},model:'cold_room'},
  {node:{id:'Coil-1'},model:'frost_hotgas_cooler'},{node:{id:'Coil-2'},model:'network_air_cooler'}];
 const groups=controls.groups(p,devices);assert.equal(groups[0].controllers.length,2);
 const values={'North.state.temperature_k':249.15,'Coil-1.defrost_mode':2,'Coil-2.defrost_mode':0};
 assert.equal(controls.observation(groups[0],key=>values[key],true).status,'部分冷风机融霜中');
 values['Coil-1.defrost_mode']=0;
 assert.equal(controls.observation(groups[0],key=>values[key],true).status,'温度正常');
});
