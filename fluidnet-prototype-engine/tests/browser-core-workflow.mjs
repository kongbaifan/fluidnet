import {expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {coreWorkflow,hash} from './core-workflow-fixture.mjs';

const selected=process.argv[process.argv.indexOf('--case')+1];
if(!['water','cold-room','six-room'].includes(selected))throw Error('Use --case water|cold-room|six-room');
const names={water:'A-pump-valve','cold-room':'B-single-cold-room','six-room':'C-six-room-51'};
const f=await coreWorkflow(names[selected]);
const {page,api,current,nav,submit,save,capture,note,openProject,newProject,insert,panel,parameter,connect,configure,run,stop,metric,charts,roundtrip,closePanels,evidence}=f;

async function pumpValve(id,ids,label){
  await openProject(id);await configure(2,.1);
  const baseline=await run(label+'-baseline'),v=baseline.frame.variables;
  expect(v[ids.pump+'.shaft_power_w']).toBeGreaterThan(0);expect(v[ids.valve+'.mass_flow_kg_s']).toBeGreaterThan(0);
  expect(v[ids.valve+'.pressure_drop_pa']).toBeGreaterThan(0);
  const baselineUI=[await metric(ids.pump,'in0:FLOW',v[ids.pump+'.mass_flow_kg_s']),
    await metric(ids.pump,'runtime:shaft_power_w',v[ids.pump+'.shaft_power_w'],1000),
    await metric(ids.valve,'runtime:pressure_drop_pa',v[ids.valve+'.pressure_drop_pa'],1000)];
  await capture(label+'-baseline-valve');await stop();
  await parameter(ids.valve,'opening',35);const throttled=await run(label+'-valve-35'),t=throttled.frame.variables;
  expect(t[ids.valve+'.param.opening_ratio']).toBeCloseTo(.35,12);
  expect(t[ids.valve+'.mass_flow_kg_s']).toBeLessThan(v[ids.valve+'.mass_flow_kg_s']);
  expect(t[ids.valve+'.pressure_drop_pa']).toBeGreaterThan(v[ids.valve+'.pressure_drop_pa']);
  await metric(ids.valve,'in0:FLOW',t[ids.valve+'.mass_flow_kg_s']);await capture(label+'-throttled');await stop();
  await parameter(ids.pump,'speed',.7);const slowed=await run(label+'-pump-70'),s=slowed.frame.variables;
  expect(s[ids.pump+'.param.speed_ratio']).toBe(.7);expect(s[ids.valve+'.mass_flow_kg_s']).toBeLessThan(t[ids.valve+'.mass_flow_kg_s']);
  expect(s[ids.pump+'.shaft_power_w']).toBeLessThan(t[ids.pump+'.shaft_power_w']);
  expect(Math.abs(s[ids.pump+'.pressure_drop_pa'])).toBeLessThan(Math.abs(t[ids.pump+'.pressure_drop_pa']));
  await metric(ids.pump,'runtime:shaft_power_w',s[ids.pump+'.shaft_power_w'],1000);await capture(label+'-pump-slowed');
  const beforeObservation=await save(),frozenBefore=JSON.stringify(current(beforeObservation).moduleSnapshots),libraryBefore=JSON.stringify(beforeObservation.modules);
  const pump=await panel(ids.pump),observe=pump.locator('[data-device-metric="runtime:shaft_power_w"] [data-action="observe-instance-variable"]');
  await expect(observe).toBeEnabled();await observe.click();await expect(observe).toHaveAttribute('aria-pressed','true');
  const afterObservation=await save(),powerBinding=afterObservation.charts.extra.find(binding=>binding.projectId===id&&binding.canonicalKey===ids.pump+'.shaft_power_w');
  expect(powerBinding).toMatchObject({nodeId:ids.pump,variableId:'runtime:shaft_power_w',unit:'kW',canonicalScale:1000,canonicalOffset:0});
  expect(JSON.stringify(current(afterObservation).moduleSnapshots)).toBe(frozenBefore);expect(JSON.stringify(afterObservation.modules)).toBe(libraryBefore);
  note('observed-pump-power-from-overview',{label,binding:powerBinding.canonicalKey,unit:powerBinding.unit,frozenSnapshotsUnchanged:true,moduleLibraryUnchanged:true});
  await charts([ids.pump+'.shaft_power_w',ids.valve+'.pressure_drop_pa'],label+'-curves',slowed);
  const saved=current(await save());expect(saved.pages.flatMap(pg=>pg.nodes).find(n=>n.id===ids.pump).params.speed).toBe(.7);
  note('verified-pump-valve-physics',{label,ids,baselineUI,flow:[v[ids.valve+'.mass_flow_kg_s'],t[ids.valve+'.mass_flow_kg_s'],s[ids.valve+'.mass_flow_kg_s']],
    valveDropPa:[v[ids.valve+'.pressure_drop_pa'],t[ids.valve+'.pressure_drop_pa']],pumpPowerW:[t[ids.pump+'.shaft_power_w'],s[ids.pump+'.shaft_power_w']]});
  return slowed;
}

async function water(){
  const blank=await newProject('代表工程 A · 空白泵阀管网');expect(blank.pages[0].nodes).toHaveLength(0);
  const ids={};for(const [name,module] of [['inlet','source'],['pump','pump'],['valve','valve'],['pipe','pipe'],['outlet','source']])ids[name]=await insert(module);
  await parameter(ids.inlet,'pressure',201.325);await parameter(ids.outlet,'pressure',120);
  await connect(ids.pump,'in0',ids.inlet+':out0');await connect(ids.pump,'out0',ids.valve+':in0');
  await connect(ids.valve,'out0',ids.pipe+':in0');await connect(ids.pipe,'out0',ids.outlet+':out0');
  let saved=current(await save());expect(saved.pages.flatMap(pg=>pg.nodes)).toHaveLength(5);expect(saved.pages.flatMap(pg=>pg.edges)).toHaveLength(4);
  await page.locator('[data-action="fit"]').first().click();await capture('blank-assembled');
  const assembled=await pumpValve(blank.id,ids,'blank');evidence.assembledRoundtrip=await roundtrip(assembled,'blank');
  const example=await pumpValve('water-net',{pump:'P1',valve:'V1'},'example');evidence.exampleRoundtrip=await roundtrip(example,'example');
  evidence.engineeringChecks={blankDevices:5,blankConnections:4,existingExample:'water-net',valveOpening:.35,pumpSpeedRatio:.7,
    flowDropsWithThrottling:true,powerAndFlowDropWithSpeed:true,displayMatchesCanonical:true};
}

async function enableThermostat(enabled){
  await closePanels();await nav('controls');const control=page.locator('[data-control-enabled]');await f.reveal(control);
  if(enabled)await control.check();else await control.uncheck();
  const owner=current(await save());expect(owner.controlPrograms.find(p=>p.id===owner.selectedControlProgram||p.id==='control')?.enabled??owner.controlEnabled).toBe(enabled);
  note(enabled?'enabled-automatic-thermostat':'selected-manual-control');await nav('workbench');
}
async function coldRoom(){
  await page.locator('[data-action="cs-create"]').click();await expect(page.locator('.cold-storage-summary.cold-room')).toBeVisible();
  let owner=current(await save());expect(owner.pages.flatMap(pg=>pg.nodes).map(n=>n.moduleId).sort()).toEqual(['condensing_unit','storage_room','unit_cooler']);
  expect(owner.pages.flatMap(pg=>pg.edges)).toHaveLength(2);const id=owner.id;
  if(await page.locator('[data-wf-scenario]').count())await page.locator('[data-wf-scenario]').selectOption('');
  await configure(600,30);await enableThermostat(true);
  const initial=await run('automatic-baseline'),a=initial.frame.variables;
  expect(initial.request.project.fluid.fluid).toBe('HEOS::R290');
  expect(a['CU1.state.running']).toBe(1);expect(a['CU1.cooling_power_w']).toBeGreaterThan(0);expect(a['ROOM1.state.temperature_k']).toBeLessThan(263.15);
  await metric('ROOM1','runtime:state.temperature_k',a['ROOM1.state.temperature_k'],1,-273.15);
  await metric('CU1','runtime:electric_power_w',a['CU1.electric_power_w'],1000);
  await capture('automatic-cooling');await stop();
  await parameter('ROOM1','heat_input_w',2);const loaded=await run('automatic-added-load'),l=loaded.frame.variables;
  expect(l['ROOM1.param.heat_input_w']).toBe(2000);expect(l['ROOM1.state.temperature_k']).toBeGreaterThan(a['ROOM1.state.temperature_k']);
  await metric('ROOM1','runtime:net_heat_w',l['ROOM1.net_heat_w'],1000);await capture('added-load');await stop();
  await enableThermostat(false);await parameter('CU1','run_request',0);const manual=await run('manual-stop'),m=manual.frame.variables;
  expect(m['CU1.state.running']).toBe(0);expect(m['CU1.cooling_power_w']).toBe(0);
  let region=await panel('CU1');await expect(region.locator('[data-device-metric="runtime:state.running"] strong')).toHaveText('停止');
  await capture('manual-stopped');await stop();
  await enableThermostat(true);await parameter('ROOM1','heat_input_w',0);await parameter('ROOM1','setpoint_temperature_k',-9);
  const satisfied=await run('automatic-target-satisfied');expect(satisfied.frame.variables['CU1.state.running']).toBe(0);
  await stop();await parameter('ROOM1','setpoint_temperature_k',-18);const final=await run('automatic-lower-target'),v=final.frame.variables;
  expect(v['CU1.state.running']).toBe(1);expect(v['ROOM1.state.temperature_k']).toBeLessThan(satisfied.frame.variables['ROOM1.state.temperature_k']);
  region=await panel('AC1');await expect(region.locator('[data-device-metric="runtime:state.mode"] strong')).toHaveText('制冷阶段');
  await expect(region.locator('[data-device-metric="runtime:state.fan_running"] strong')).toHaveText('运行');await capture('automatic-restored');
  await charts(['ROOM1.state.temperature_k','CU1.electric_power_w'],'temperature-power-curves',final);
  evidence.roundtrip=await roundtrip(final,'single-room');
  evidence.engineeringChecks={projectId:id,devices:3,connections:2,baselineC:a['ROOM1.state.temperature_k']-273.15,addedLoadC:l['ROOM1.state.temperature_k']-273.15,
    manualStopsCooling:true,thermostatTargetsC:[-9,-18],automaticRestoresCooling:true,curves:['temperature','power']};
}

const rooms=['F01','F02','F03','F04','C01','C02'];
async function sixRoomState(record,label){
  await closePanels();await nav('workbench');await expect(page.locator('[data-room-status]')).toHaveCount(6);const states=[];
  for(const id of rooms){
    const row=page.locator(`[data-room-status="${id}"]`);await expect(row).not.toContainText('运行后查看');
    const temperature=Number(await row.locator('td').nth(2).innerText()),expected=record.frame.variables[id+'.state.temperature_k']-273.15;
    expect(temperature,id).toBeCloseTo(expected,1);states.push({id,temperatureC:temperature,status:await row.locator('td').nth(3).innerText()});
  }
  const power=await page.getByText(/各库温度 · 当前总功率/).innerText(),shown=Number(power.match(/总功率\s+([\d.,]+)/)?.[1].replaceAll(',',''));
  expect(shown).toBeCloseTo(record.frame.metrics.electric_power_w/1000,1);
  await page.getByRole('table',{name:'各库温控状态',exact:true}).scrollIntoViewIfNeeded();await capture(label);
  note('verified-six-room-status',{label,states,totalPowerKw:shown});return {states,totalPowerKw:shown};
}
async function sixRoom(){
  const sourceFile='examples/large-cold-store/six-room-controlled.project.json',source=JSON.parse(readFileSync(sourceFile,'utf8'));
  expect(source.instances).toHaveLength(51);evidence.reference={file:sourceFile,sha256:hash(readFileSync(sourceFile)),id:source.id};
  await page.getByRole('button',{name:'六库自动温控',exact:true}).click();await expect(page.locator('[data-room-status]')).toHaveCount(6);
  let owner=current(await save());expect(owner.pages.flatMap(pg=>pg.nodes)).toHaveLength(51);expect(owner.pages.flatMap(pg=>pg.edges)).toHaveLength(72);
  expect(owner.pages).toHaveLength(4);expect(owner.controllers).toHaveLength(19);const originalTargets=Object.fromEntries(owner.controllers.map(c=>[c.id,c.setpoint]));
  for(const pageId of ['plant','frozen-a','frozen-b','chilled']){
    await page.locator(`[data-action="canvas-tab"][data-id="${pageId}"]`).click();await page.locator('[data-action="fit"]').first().click();
    const shown=await page.locator('.net-node').count();expect(shown).toBe(owner.pages.find(pg=>pg.id===pageId).nodes.length);
    await capture('canvas-'+pageId);note('opened-canvas',{pageId,devices:shown});
  }
  await f.locate('F01');await expect(page.getByRole('region',{name:'F01 设备参数',exact:true})).toContainText('冷冻库 1');await capture('located-f01');await closePanels();
  await configure(600,30);const baseline=await run('baseline');expect(baseline.request.project.instances).toHaveLength(51);
  for(const original of source.instances){
    const actual=baseline.request.project.instances.find(node=>node.id===original.id);expect(actual?.module_id,original.id).toBe(original.module_id);
    for(const [key,value] of Object.entries(original.parameters)){
      if(typeof value==='number')expect(Math.abs(actual.parameters[key]-value)/Math.max(1,Math.abs(value)),original.id+'.'+key).toBeLessThan(1e-12);
      else expect(actual.parameters[key],original.id+'.'+key).toEqual(value);
    }
  }
  const links=items=>items.map(edge=>[edge.id,edge.source.instance_id,edge.source.port_id,edge.target.instance_id,edge.target.port_id]).sort((a,b)=>a[0].localeCompare(b[0]));
  expect(links(baseline.request.project.connections)).toEqual(links(source.connections));
  await sixRoomState(baseline,'baseline-six-room-status');await stop();
  await page.locator('[data-action="cs-room-targets"]').click();await page.getByLabel('冷冻库 1 / °C',{exact:true}).fill('-23');await submit();
  owner=current(await save());const changed=owner.controllers.filter(c=>c.measurement==='F01.state.temperature_k');
  expect(changed).toHaveLength(2);expect(changed.every(c=>Math.abs(c.setpoint-250.15)<1e-10)).toBe(true);
  for(const c of owner.controllers.filter(c=>c.measurement!=='F01.state.temperature_k'))expect(c.setpoint,c.id).toBeCloseTo(originalTargets[c.id],10);
  const adjusted=await run('f01-target-minus23'),v=adjusted.frame.variables;
  expect(v['F01.state.temperature_k']).toBeGreaterThan(baseline.frame.variables['F01.state.temperature_k']);
  expect(v['controller.F01_temperature_1.setpoint']).toBeCloseTo(250.15,9);
  await sixRoomState(adjusted,'adjusted-six-room-status');
  await expect(page.locator('[data-room-status="F01"] td').nth(1)).toHaveText('-23.0');
  await charts(rooms.map(id=>id+'.state.temperature_k'),'six-room-curves',adjusted);
  evidence.roundtrip=await roundtrip(adjusted,'six-room');
  await sixRoomState(await api('/runs/'+evidence.runs['six-room-file-imported'].id),'reopened-six-room-status');
  evidence.engineeringChecks={devices:51,connections:72,pages:4,controllers:19,roomTargetChanged:['F01'],otherTargetsPreserved:true,
    sixRoomValuesMatchFrame:true,totalPowerMatchesFrame:true,rawExportRecomputed:true};
}

try{await ({water,'cold-room':coldRoom,'six-room':sixRoom})[selected]();await f.finish();}
catch(error){await f.failure(error);process.exitCode=1;}
finally{await f.close();}
