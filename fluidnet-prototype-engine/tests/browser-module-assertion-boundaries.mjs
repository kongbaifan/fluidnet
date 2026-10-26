import {chromium, expect} from '@playwright/test';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {testServer} from './browser-server.mjs';

// Uses the actual page helper in an isolated editor so it can also run inside the
// module workflow without changing the user's selected module or saved workspace.
export async function exerciseModuleAssertionBoundaries(page, base) {
  const response = await page.request.post(base+'/api/v1/modules/from-template', {data:{
    template:'heat_exchanger', id:'boundary_heat_exchanger', name:'Boundary heat exchanger',
  }});
  expect(response.status()).toBe(200);
  const definition = await response.json();
  const schema = await (await page.request.get(base+'/openapi.json')).json();
  const pressureTolerance = schema.components.schemas.SolverOptions.properties.pressure_tolerance_pa.default;
  const source = {testConditions:{
    duration_s:.1, dt_s:.1, inlet_pressure_pa:400000, outlet_pressure_pa:140000, temperature_k:300,
    property_coupling:'reference', fluid:{fluid:'Water', reference:'mole'}, parameters:{ua_w_k:80},
    channel_boundaries:{
      hot:{inlet_pressure_pa:330000, outlet_pressure_pa:170000, inlet_temperature_k:320, outlet_temperature_k:320,
        fluid:{fluid:'Water', phase_policy:'liquid'}},
      cold:{inlet_temperature_k:290, outlet_temperature_k:290, fluid:{fluid:'Water', reference:'mass'}},
    },
  }};
  const run = async cases => {
    const response = await page.request.post(base+'/api/v1/modules/test-suite', {data:{module:definition,cases}});
    const result = await response.json();
    expect(response.status(), JSON.stringify(result)).toBe(200);
    expect(result.passed, JSON.stringify(result.cases.map(c => ({id:c.id,diagnostics:c.diagnostics,assertions:c.assertions})))).toBe(true);
    return result;
  };
  await page.waitForFunction(() => !!window.ModuleTestEditor);
  try {
    const generated = await page.evaluate(({source,definition}) => {
      const initial = window.ModuleTestEditor.cases(source,definition);
      const host = document.createElement('div');
      host.id = 'module-boundary-probe';
      host.style.cssText = 'position:fixed;inset:10px;overflow:auto;z-index:100000;background:white;color:black;padding:16px';
      document.body.appendChild(host);
      window.__moduleBoundaryProbe = {definition,editor:window.ModuleTestEditor.mount(host,initial,definition)};
      return initial;
    }, {source,definition});
    expect(generated.map(c => c.id)).toEqual(['forward','reverse','zero']);
    expect(generated[1].conditions.channel_boundaries.hot).toEqual({
      ...source.testConditions.channel_boundaries.hot, inlet_pressure_pa:170000, outlet_pressure_pa:330000,
    });
    expect(generated[1].conditions.channel_boundaries.cold).toEqual({
      ...source.testConditions.channel_boundaries.cold, inlet_pressure_pa:120000, outlet_pressure_pa:250000,
    });
    expect(generated[2].conditions.channel_boundaries.hot.outlet_pressure_pa).toBe(330000);
    expect(generated[2].conditions.channel_boundaries.cold.outlet_pressure_pa).toBe(250000);
    const defaults = await page.evaluate(() => window.__moduleBoundaryProbe.editor.read());
    for (const c of defaults) {
      c.assertions = ['hot','cold'].map(channel => ({key:`D1.${channel}.pressure_drop_pa`,
        expected:c.conditions.channel_boundaries[channel].inlet_pressure_pa-c.conditions.channel_boundaries[channel].outlet_pressure_pa,
        absolute_tolerance:1e-5}));
    }
    const directions = await run(defaults);
    for (const channel of ['hot','cold']) {
      const key = `D1.${channel}.mass_flow_kg_s`;
      expect(directions.cases[0].result.frame.variables[key]).toBeGreaterThan(0);
      expect(directions.cases[1].result.frame.variables[key]).toBeLessThan(0);
      // A quadratic resistance can converge near zero flow within the pressure
      // residual tolerance. Mass conservation tolerance is not a branch-flow bound.
      const zero = directions.cases[2].result;
      const parameters = zero.evaluation.relations.find(relation => relation.channel === channel).parameters;
      const area = Math.PI * parameters.diameter_m ** 2 / 4;
      const flow = zero.frame.variables[key];
      const pressureDrop = parameters.loss_coefficient * flow ** 2 / (2 * parameters.density_kg_m3 * area ** 2);
      expect(pressureDrop).toBeLessThanOrEqual(pressureTolerance);
    }
    const forward = page.locator('#module-boundary-probe [data-suite-case="0"]');
    const hot = forward.locator('[data-suite-channel="hot"]');
    await expect(forward).toContainText('优先使用下方压力、温度和工质');
    await hot.locator('[data-boundary-field="inlet_pressure_pa"]').fill('340000');
    await hot.locator('[data-boundary-field="outlet_pressure_pa"]').fill('180000');
    await hot.locator('[data-boundary-field="inlet_temperature_k"]').fill('330');
    await hot.locator('[data-boundary-field="outlet_temperature_k"]').fill('331');
    await forward.locator('[data-condition="inlet_pressure_pa"]').fill('480000');
    const edited = await page.evaluate(() => window.__moduleBoundaryProbe.editor.read()[0]);
    expect(edited.conditions.channel_boundaries.hot).toEqual({...source.testConditions.channel_boundaries.hot,
      inlet_pressure_pa:340000, outlet_pressure_pa:180000, inlet_temperature_k:330, outlet_temperature_k:331});
    expect(edited.conditions.channel_boundaries.cold).toEqual(defaults[0].conditions.channel_boundaries.cold);
    expect(edited.conditions.fluid).toEqual(source.testConditions.fluid);
    expect(edited.conditions.parameters).toEqual(source.testConditions.parameters);
    expect(edited.conditions.property_coupling).toBe('reference');
    edited.assertions = [
      {key:'D1.hot_in.pressure_pa', expected:340000, absolute_tolerance:1e-5},
      {key:'D1.hot_out.pressure_pa', expected:180000, absolute_tolerance:1e-5},
      {key:'D1.hot_in.temperature_k', expected:330, absolute_tolerance:1e-5},
    ];
    await run([edited]);
    await hot.locator('[data-suite-action="remove-boundary"]').click();
    const cleared = await page.evaluate(() => window.__moduleBoundaryProbe.editor.read()[0]);
    expect(cleared.conditions.channel_boundaries.hot).toBeUndefined();
    expect(cleared.conditions.channel_boundaries.cold).toEqual(defaults[0].conditions.channel_boundaries.cold);
    cleared.assertions = [{key:'D1.hot_in.pressure_pa', expected:480000, absolute_tolerance:1e-5}];
    await run([cleared]);
    await hot.locator('[data-suite-action="add-boundary"]').click();
    const added = await page.evaluate(() => window.__moduleBoundaryProbe.editor.read()[0]);
    expect(added.conditions.channel_boundaries.hot).toEqual({
      inlet_pressure_pa:480000, outlet_pressure_pa:140000, inlet_temperature_k:300, outlet_temperature_k:300,
      fluid:source.testConditions.fluid,
    });

    // Check the helper's validation independently of HTML maxlength/max attributes,
    // since a restored workspace can contain values that did not come from inputs.
    const validation = await page.evaluate(() => {
      const {definition} = window.__moduleBoundaryProbe;
      const check = c => {
        const host = document.createElement('div');
        try { return {accepted:true, cases:window.ModuleTestEditor.mount(host,[c],definition).read()}; }
        catch (error) { return {accepted:false, message:error.message}; }
      };
      return {
        invalid:[
          {id:'_case'}, {id:'a'.repeat(82)},
          {id:'case', conditions:{duration_s:61}}, {id:'case', conditions:{dt_s:61}},
          {id:'case', conditions:{duration_s:60,dt_s:.01}},
          {id:'case', assertions:[{key:'D1. value',expected:0}]},
          {id:'case', assertions:[{key:'x'.repeat(257),expected:0}]},
        ].map(check),
        limit:check({id:'A'+'x'.repeat(80), conditions:{duration_s:60,dt_s:.03}, assertions:[{key:'D1.hot.mass_flow_kg_s',expected:0}]}),
      };
    });
    expect(validation.invalid.every(result => !result.accepted), JSON.stringify(validation.invalid)).toBe(true);
    expect(validation.limit.accepted, JSON.stringify(validation.limit)).toBe(true);
    expect(validation.limit.cases[0].assertions[0].absolute_tolerance).toBe(0);
    expect(validation.limit.cases[0].assertions[0].relative_tolerance).toBe(0);
    console.log(JSON.stringify({moduleAssertionBoundaries:{directionsVerified:true,channelEditsApplied:true,overridesPreserved:true,clearAndAdd:true,contractLimits:true}}));
  } finally {
    await page.evaluate(() => {document.getElementById('module-boundary-probe')?.remove(); delete window.__moduleBoundaryProbe;});
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const server = await testServer();
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1600,height:1000}});
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto(server.base+'/#modules');
    await exerciseModuleAssertionBoundaries(page,server.base);
    expect(errors).toEqual([]);
  } finally { await browser.close(); await server.close(); }
}
