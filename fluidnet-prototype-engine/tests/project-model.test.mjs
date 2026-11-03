import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const context=vm.createContext({window:{}});
vm.runInContext(readFileSync(new URL('../frontend/project-model.js',import.meta.url),'utf8'),context);
const model=context.window.FluidNetProjectModel;
const plain=value=>JSON.parse(JSON.stringify(value));

test('display and canonical conversions agree for absolute temperatures, differences, opening and power',()=>{
  for(const [unit,canonical,display] of [
    [{display_scale:1,display_offset:-273.15},298.15,25],
    [{display_scale:1,display_offset:0},5,5],
    [{display_scale:.01,display_offset:0},.4,40],
    [{display_scale:1000,display_offset:0},18000,18],
    [{display_scale:1/3600,display_offset:0},.001,3.6],
  ]){
    const spec={value_type:'number',unit};
    assert.ok(Math.abs(model.toDisplay(spec,canonical)-display)<1e-10);
    assert.ok(Math.abs(model.toCanonical(spec,display)-canonical)<1e-10);
  }
});
test('text, booleans, curves and missing values remain distinct from numeric conversion',()=>{
  for(const [type,value] of [['text','equal_percentage'],['boolean',false],['curve',[[0,4],[1,0]]]]){
    const spec={value_type:type};
    assert.deepEqual(plain(model.toDisplay(spec,value)),value);
    assert.deepEqual(plain(model.toCanonical(spec,value)),value);
  }
  assert.equal(model.toDisplay({value_type:'number',unit:{display_scale:1000}},null),null);
});
test('parameter views and defaults use the same units and do not mutate contracts',()=>{
  const manifest={parameters:[{id:'opening',label:'Opening',value_type:'number',default:.8,minimum:0,maximum:1,
    unit:{display_scale:.01,display_offset:0,display_unit:'%'}},{id:'enabled',value_type:'boolean',default:false}]};
  const before=structuredClone(manifest);
  const fields=model.manifestFields(manifest),specs=model.manifestParamSpecs(manifest);
  assert.equal(fields[0][6],80);assert.equal(specs[0].default,80);
  assert.deepEqual(plain(model.manifestParamDefaults(manifest)),{opening:80,enabled:false});
  assert.deepEqual(manifest,before);
});
