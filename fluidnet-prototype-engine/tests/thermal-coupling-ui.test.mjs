import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

// Exercise the public editor with saved prototype definitions, which can have
// different ports/channels from the server catalog's original built-in pipe.
function editorFixture(enabled = true) {
  const sandbox = {window: {}, document: {getElementById: () => ({addEventListener() {}})}};
  vm.runInNewContext(readFileSync(new URL('../frontend/cold-storage.js', import.meta.url), 'utf8'), sandbox);
  const project = {id: 'custom', run: {status: 'ready', history: []}, thermalCouplings: [],
    pages: [{nodes: [{id: 'Liquid-1', moduleId: 'custom-pipe', params: {}},
      {id: 'Vessel-1', moduleId: 'vessel', params: {}}]}],
    moduleSnapshots: {
      'custom-pipe': {id: 'custom-pipe', kind: 'pipe', ports: [{id: 'in', domain: 'fluid'}, {id: 'out', domain: 'fluid'}],
        channels: [{id: 'saved-route', input: 'in', output: 'out', enabled}]},
      vessel: {id: 'vessel', kind: 'saturated_vessel'},
    }};
  const catalog = {modules: [
    {id: 'pipe', runtime: 'builtin', solver_model: 'pipe', parameters: [],
      ports: [{id: 'in0', domain: 'fluid'}, {id: 'out0', domain: 'fluid'}],
      channels: [{id: 'ch0', enabled: true}]},
    {id: 'saturated_vessel', runtime: 'builtin', solver_model: 'saturated_vessel',
      ports: [{id: 'in0', domain: 'refrigerant'}]},
  ]};
  const state = {modules: [], charts: {extra: []}}, view = {};
  let dialog, remembered = 0;
  const api = sandbox.window.createColdStorageUI({
    state: () => state, project: () => project, engine: () => ({catalog, health: {capabilities: {thermal_coupling: true}}}),
    ui: () => view, esc: value => String(value ?? ''), btn: () => '',
    openDialog: (title, description, body, submit) => {dialog = {title, description, body, submit};},
    projectKey: () => JSON.stringify(project), remember: () => {remembered++;},
    markDirty() {}, persist() {}, render() {}, msg() {},
  });
  api.couplingSettings(project);
  const values = {id: 'Coil_Custom-2', fluid_instance_id: 'Liquid-1', fluid_channel_id: 'saved-route',
    refrigerant_vessel_id: 'Vessel-1', ua: '1800'};
  return {api, project, state, values, get dialog() {return dialog;}, remembered: () => remembered};
}

test('saved built-in channel overrides determine the legal coil and its persisted binding', () => {
  const fixture = editorFixture();
  assert.match(fixture.dialog.body, /value="saved-route"/);
  fixture.dialog.submit(fixture.values);
  assert.equal(fixture.project.thermalCouplings[0].fluid_channel_id, 'saved-route');
  assert.equal(fixture.project.thermalCouplings[0].id, 'Coil_Custom-2');
  assert.equal(fixture.remembered(), 1);
  assert.ok(fixture.state.charts.extra.every(binding => binding.canonicalKey.startsWith('coupling.Coil_Custom-2.')));
});

test('a disabled saved channel is excluded even when the catalog channel is enabled', () => {
  const fixture = editorFixture(false);
  const pipeOptions = fixture.dialog.body.match(/<select id="cs-fluid-pipe"[^>]*>([\s\S]*?)<\/select>/)[1];
  assert.doesNotMatch(pipeOptions, /value="Liquid-1"/);
  assert.throws(() => fixture.dialog.submit(fixture.values), /合法.*圆管/);
  assert.equal(fixture.project.thermalCouplings.length, 0);
  assert.equal(fixture.remembered(), 0);
});

test('IDs outside the backend contract do not mutate the draft', () => {
  for (const id of ['_invalid', 'A'.repeat(82)]) {
    const fixture = editorFixture();
    assert.throws(() => fixture.dialog.submit({...fixture.values, id}), /关系标识/);
    assert.equal(fixture.project.thermalCouplings.length, 0);
    assert.equal(fixture.remembered(), 0);
  }
});

function dualFixture() {
  const fixture = editorFixture();
  fixture.project.pages[0].nodes.push({id: 'Liquid-2', moduleId: 'custom-pipe', params: {}},
    {id: 'Vessel-2', moduleId: 'vessel', params: {}});
  fixture.api.couplingSettings(fixture.project);
  fixture.dialog.submit(fixture.values);
  const firstBindingIds = fixture.state.charts.extra.map(binding => binding.id);
  fixture.api.couplingSettings(fixture.project, null);
  fixture.dialog.submit({...fixture.values, id: 'SecondCoil', fluid_instance_id: 'Liquid-2', ua: '900'});
  return {...fixture, get dialog() {return fixture.dialog;}, firstBindingIds};
}

test('two independently editable relations retain the first curve IDs and add aggregate bindings', () => {
  const fixture = dualFixture();
  assert.equal(fixture.project.thermalCouplings.length, 2);
  assert.equal(fixture.state.charts.extra.filter(binding => binding.couplingTotal).length, 2);
  assert.ok(fixture.firstBindingIds.every(id => fixture.state.charts.extra.some(binding => binding.id === id)));
  const first = JSON.stringify(fixture.project.thermalCouplings[0]);
  fixture.api.couplingSettings(fixture.project, 'SecondCoil');
  fixture.dialog.submit({...fixture.values, id: 'SecondCoil', fluid_instance_id: 'Liquid-2', ua: '700'});
  assert.equal(JSON.stringify(fixture.project.thermalCouplings[0]), first);
  assert.equal(fixture.project.thermalCouplings[1].ua_w_k, 700);
});

test('editing cannot overwrite another relationship, reuse its pipe, or select a different vessel', () => {
  const fixture = dualFixture();
  const before = JSON.stringify(fixture.project.thermalCouplings);
  for (const [update, message] of [
    [{id: fixture.values.id}, /标识/],
    [{fluid_instance_id: 'Liquid-1'}, /通路/],
    [{refrigerant_vessel_id: 'Vessel-2'}, /同一个/],
  ]) {
    fixture.api.couplingSettings(fixture.project, 'SecondCoil');
    assert.throws(() => fixture.dialog.submit({...fixture.values, id: 'SecondCoil',
      fluid_instance_id: 'Liquid-2', ...update}), message);
    assert.equal(JSON.stringify(fixture.project.thermalCouplings), before);
  }
  assert.throws(() => fixture.api.couplingSettings(fixture.project, null), /最多.*两/);
});

test('removing the selected relation retains the other and removes only obsolete aggregate curves', async () => {
  const fixture = dualFixture();
  await fixture.api.action('cs-remove-coupling', {dataset: {coupling: 'SecondCoil'}});
  fixture.dialog.submit({});
  assert.equal(fixture.project.thermalCouplings.length, 1);
  assert.equal(fixture.project.thermalCouplings[0].id, fixture.values.id);
  assert.equal(fixture.state.charts.extra.length, 6);
  assert.ok(fixture.state.charts.extra.every(binding => binding.couplingId === fixture.values.id));
  assert.ok(fixture.firstBindingIds.every(id => fixture.state.charts.extra.some(binding => binding.id === id)));
});
