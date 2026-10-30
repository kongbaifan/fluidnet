import {FHD_CONTEXT} from './browser-viewport.mjs';
import { chromium, expect } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import { testServer } from './browser-server.mjs';

// Exercise the actual browser adapter against a real run. A small UI host lets a
// server-invalid second draft reach the adapter without HTML range validation
// masking the rejection path. The run and all writes use the production API.
export async function verifyParameterBatches(browser, base) {
  const page = await browser.newPage({...FHD_CONTEXT});
  const commands = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/command'))
      commands.push(request.postDataJSON());
  });
  let runId;
  const api = async path => {
    const response = await page.request.get(base + '/api/v1' + path);
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  try {
    await page.route(base + '/parameter-batch-test', route => route.fulfill({
      contentType: 'text/html', body: '<!doctype html><title>Runtime parameter batch regression</title>'
    }));
    await page.goto(base + '/parameter-batch-test');
    await page.addScriptTag({url: base + '/control-programs.js'});
    await page.addScriptTag({url: base + '/project-services.js'});
    await page.addScriptTag({url: base + '/engine-client.js'});
    const project = await api('/examples/cold-storage');
    project.controllers = []; project.control_scripts = [];
    const response = await page.request.post(base + '/api/v1/runs?background=true', {data: {
      project, mode: 'dynamic', duration_s: null, dt_s: .1, start_paused: true,
      execution_mode: 'realtime', speed_ratio: 1
    }});
    expect(response.ok(), await response.text()).toBe(true);
    runId = (await response.json()).run_id;
    await expect.poll(async () => (await api('/runs/' + runId)).status).toBe('paused');
    const before = await api('/runs/' + runId);
    const definition = project.modules.find(module => module.id === 'cold_room');
    const initial = Object.fromEntries(['ambient_temperature_k', 'heat_input_w'].map(key => {
      const spec = definition.parameters.find(parameter => parameter.id === key);
      return [key, before.frame.variables['ROOM1.param.' + key] / spec.unit.display_scale + spec.unit.display_offset];
    }));
    await page.evaluate(({definition, runId, initial}) => {
      const node = {id: 'ROOM1', params: {...initial}, draft: {...initial}};
      const owner = {id: 'batch', pages: [{nodes: [node]}], run: {
        id: runId, runId, live: true, status: 'paused', history: [], offset: 0, events: []
      }};
      const state = {charts: {range: 'window'}, projects: [owner]};
      const messages = [];
      const client = window.createEngineClient({
        state: () => state, project: () => owner,
        moduleOf: () => ({manifest: definition, variables: []}),
        parameterKey: () => JSON.stringify(node.params), persist: () => {},
        render: () => {}, refresh: () => {}, message: text => messages.push(text)
      });
      window.batchTest = {node, owner, client, messages};
    }, {definition, runId, initial});
    const apply = draft => page.evaluate(async draft => {
      const {client, owner, node} = window.batchTest;
      node.draft = {...draft};
      let error = null;
      try { await client.applyParameters(owner, node); }
      catch (failure) { error = failure.message; }
      return {error, params: node.params, draft: node.draft};
    }, draft);
    const command = action => page.evaluate(async action => {
      const {client, owner} = window.batchTest;
      await client.confirmedCommand(owner, {action});
    }, action);
    const advance = async () => {
      const sequence = (await api('/runs/' + runId)).frame.sequence;
      await command('step');
      await expect.poll(async () => (await api('/runs/' + runId)).frame.sequence).toBeGreaterThan(sequence);
      return api('/runs/' + runId);
    };
    const writes = () => commands.filter(command => command.action === 'write' || command.action === 'set');
    const latestWriteEvent = async () => {
      const id = writes().at(-1).command_id;
      return (await api(`/runs/${runId}/events`)).events.findLast(event => event.command_id === id);
    };

    // Empty edits must neither enqueue a command nor create a revision.
    expect(await apply(initial)).toEqual({error: null, params: initial, draft: initial});
    expect(writes()).toHaveLength(0);

    // Paused: two displayed values become one canonical-unit batch and revision.
    const pausedDraft = {ambient_temperature_k: 35, heat_input_w: .5};
    expect(await apply(pausedDraft)).toEqual({error: null, params: pausedDraft, draft: pausedDraft});
    expect(writes()).toHaveLength(1);
    expect(writes()[0]).toMatchObject({action: 'write', values: {
      'ROOM1.param.ambient_temperature_k': 308.15, 'ROOM1.param.heat_input_w': 500
    }});
    expect(await latestWriteEvent()).toMatchObject({command_status: 'applied', parameter_revision: 1});
    const accepted = await advance();
    expect(accepted.frame.parameter_revision).toBe(1);
    expect(accepted.frame.variables['ROOM1.param.ambient_temperature_k']).toBeCloseTo(308.15, 9);
    expect(accepted.frame.variables['ROOM1.param.heat_input_w']).toBe(500);

    // The first value is valid, the second is outside its backend range. Neither
    // the server nor the applied local params may retain a partial update.
    const rejectedDraft = {ambient_temperature_k: 40, heat_input_w: -1};
    const rejected = await apply(rejectedDraft);
    expect(rejected.error).toContain('超出范围');
    expect(rejected.params).toEqual(pausedDraft);
    expect(rejected.draft).toEqual(rejectedDraft);
    expect(writes()).toHaveLength(2);
    expect(await latestWriteEvent()).toMatchObject({command_status: 'rejected', parameter_revision: 1});
    const unchanged = await advance();
    expect(unchanged.frame.parameter_revision).toBe(1);
    expect(unchanged.frame.variables['ROOM1.param.ambient_temperature_k']).toBeCloseTo(308.15, 9);
    expect(unchanged.frame.variables['ROOM1.param.heat_input_w']).toBe(500);

    // Running uses the same batch path; there is no frame with only one change.
    await command('resume');
    await expect.poll(async () => (await api('/runs/' + runId)).status).toBe('running');
    const runningDraft = {ambient_temperature_k: 36, heat_input_w: .75};
    expect(await apply(runningDraft)).toEqual({error: null, params: runningDraft, draft: runningDraft});
    expect(writes()).toHaveLength(3);
    expect(await latestWriteEvent()).toMatchObject({command_status: 'applied', parameter_revision: 2});
    await expect.poll(async () => (await api('/runs/' + runId)).frame.parameter_revision).toBe(2);
    await command('pause');
    const history = await api(`/runs/${runId}/history`);
    for (const row of history.rows.filter(row => row.parameter_revision === 2)) {
      expect(row.variables['ROOM1.param.ambient_temperature_k']).toBeCloseTo(309.15, 9);
      expect(row.variables['ROOM1.param.heat_input_w']).toBe(750);
    }
    expect(await apply(runningDraft)).toEqual({error: null, params: runningDraft, draft: runningDraft});
    expect(writes()).toHaveLength(3);
    expect(errors).toEqual([]);
    expect(await page.evaluate(() => window.batchTest.messages)).toEqual([]);
    return {writes: writes().length, acceptedRevisions: 2, rejectedBatches: 1};
  } finally {
    if (runId) await page.request.post(`${base}/api/v1/runs/${runId}/command`, {data: {action: 'stop'}}).catch(() => {});
    await page.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const server = await testServer();
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try { console.log(JSON.stringify(await verifyParameterBatches(browser, server.base))); }
  finally { await browser.close(); await server.close(); }
}
