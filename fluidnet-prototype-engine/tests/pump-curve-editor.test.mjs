import {loadFrontend} from './frontend-module-loader.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const host=vm.createContext({window:{}});
loadFrontend(new URL('../frontend/pump-curve-editor.js',import.meta.url),host);
const editor=host.window.FluidNetPumpCurveEditor,plain=v=>JSON.parse(JSON.stringify(v));

test('pump point table accepts numeric inputs without mutating the applied curve',()=>{
  const rows=[['0','21'],['10','18'],['20','12'],['30','0']],before=plain(rows),result=editor.inspect(rows);
  assert.equal(result.valid,true);assert.deepEqual(plain(result.points),[[0,21],[10,18],[20,12],[30,0]]);
  result.points[0][1]=40;assert.deepEqual(rows,before);
});

test('invalid, repeated, unordered and missing points identify the offending row',()=>{
  for(const value of ['', ' ',null,true,NaN,Infinity,-1,'abc']){
    const result=editor.inspect([[0,21],[value,12],[30,0]]);
    assert.equal(result.valid,false,String(value));assert.equal(result.errors[0].row,1);
  }
  for(const rows of [null,[],[[0,0]],[[1,20],[20,0]],[[0,20],[20,1]],[[0,20],[0,10],[20,0]],[[0,20],[10,20],[20,0]],[[0,20],[10,21],[20,0]],[[0,20],[10,12,2],[20,0]]])
    assert.equal(editor.inspect(rows).valid,false,JSON.stringify(rows));
  assert.match(editor.inspect([[0,20],[10,10],[10,0]]).errors[0].message,/第 3 行.*流量/);
  assert.match(editor.inspect([[0,20],[10,21],[20,0]]).errors[0].message,/第 2 行.*扬程/);
});

test('point table is used only for identified pump head curves',()=>{
  const spec={id:'head_curve',value_type:'curve'};
  assert.ok(editor.supported({id:'pump',runtime:'builtin'},spec));
  assert.ok(editor.supported({id:'custom',runtime:'python',manifest:{channels:[{solver_model:'pump_curve'}]}},spec));
  assert.ok(!editor.supported({id:'pump',runtime:'python'},spec));
  assert.ok(!editor.supported({id:'pump',manifest:{runtime:'python'}},spec));
  assert.ok(!editor.supported({id:'pump'}, {...spec,id:'pressure_curve'}));
  assert.ok(!editor.supported(null,spec));
});
