import {test} from 'node:test';
import assert from 'node:assert/strict';
import {FluidNetWorkbenchGuidance as guidance} from '../frontend/workbench-guidance.js';

const describe = overrides => guidance.describe({nodeCount: 9, status: 'ready', ...overrides});
const esc = value => String(value).replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));

test('empty projects and normal run states render no teaching or save reminder', () => {
  for (const status of ['ready', 'solving', 'running', 'paused', 'completed', 'stopped']) {
    for (const nodeCount of [0, 9]) {
      for (const hasResult of [false, true]) {
        for (const dirty of [false, true]) {
          const model = describe({status, nodeCount, hasResult, dirty, time: 12.5});
          assert.equal(model.title, '', status);
          assert.equal(model.action, '', status);
          assert.equal(guidance.markup(model, {esc}), '', status);
        }
      }
    }
  }
});

test('failure outranks connection loss and drafts even when a last accepted frame exists', () => {
  for (const hasResult of [false, true]) {
    const model = describe({status: 'failed', hasResult, pendingCount: 2, connectionError: true});
    assert.equal(model.title, '本次运行失败');
    assert.equal(model.action, 'diagnostics');
    assert.equal(model.tone, 'error');
    assert.equal(model.detail, hasResult ? '保留失败前结果。' : '尚无有效结果。');
    assert.doesNotMatch(model.title + model.detail, /已就绪|成功|已完成/);
  }
  assert.equal(describe({status: 'failed', hasResult: true, stale: true}).detail, '保留失败前结果。结果已过期。');
  assert.equal(describe({status: 'failed', hasResult: false, stale: true}).detail, '尚无有效结果。');
});

test('lost contact takes precedence over pending and stale data without another curve action', () => {
  for (const hasResult of [false, true]) {
    for (const connectionError of [true, 'Network request failed']) {
      const model = describe({status: 'running', hasResult, connectionError, pendingCount: 2, stale: true});
      assert.equal(model.title, '连接中断，正在重连');
      assert.equal(model.detail, '运行状态暂不可确认。');
      assert.equal(model.action, '');
      assert.doesNotMatch(guidance.markup(model, {esc}), /<button/);
    }
  }
});

test('unapplied edits remain actionable during calculation and take precedence over old results', () => {
  for (const status of ['ready', 'solving', 'running', 'paused', 'completed']) {
    const model = describe({status, hasResult: true, stale: true, pendingCount: 4, pendingDevices: 2});
    assert.equal(model.title, '2 台设备 · 4 项修改尚未应用');
    assert.equal(model.detail, '运行使用已应用参数。');
    assert.equal(model.action, 'pending');
    assert.equal(model.tone, 'warn');
  }
});

test('saved drafts still need applying and device counts do not invent a zero-device prefix', () => {
  const input = Object.freeze({pendingCount: 2, pendingDevices: 1, status: 'completed', hasResult: true, dirty: false});
  const model = guidance.describe(input);
  assert.equal(model.title, '1 台设备 · 2 项修改尚未应用');
  assert.equal(model.detail, '运行使用已应用参数。');
  assert.equal(model.action, 'pending');
  assert.equal(describe({pendingCount: 2, pendingDevices: 0}).title, '2 项修改尚未应用');
  assert.equal(describe({pendingCount: 2, pendingDevices: [{id: 'V1'}]}).title, '1 台设备 · 2 项修改尚未应用');
});

test('only existing results can be stale and the reminder asks for another computation', () => {
  for (const status of ['ready', 'solving', 'running', 'paused', 'completed', 'stopped']) {
    const model = describe({status, hasResult: true, stale: true});
    assert.equal(model.title, '结果已过期');
    assert.equal(model.detail, '重新运行或单步以更新。');
    assert.equal(model.action, '');
    assert.equal(model.tone, 'warn');
    assert.equal(guidance.markup(describe({status, hasResult: false, stale: true}), {esc}), '');
  }
});

test('reminder markup has no steps, escapes its copy and keeps the scoped action', () => {
  const model = {...describe({pendingCount: 1, pendingDevices: 1}), title: '<待应用>', detail: 'A&B', label: '查看"修改"'};
  const html = guidance.markup(model, {esc, icon: () => '<svg aria-hidden="true"></svg>'});
  assert.doesNotMatch(html, /<ol|<li\b|aria-current|workbench-steps/);
  assert.equal((html.match(/<button /g) || []).length, 1);
  assert.match(html, /data-action="workbench-next" data-value="pending"/);
  assert.match(html, /&lt;待应用&gt;/);
  assert.match(html, /A&amp;B/);
  assert.match(html, /查看&quot;修改&quot;/);
  assert.match(html, /<div class="workbench-next"><div class="workbench-next-copy/);
  assert.match(html, /<p>A&amp;B<\/p>/);
  assert.doesNotMatch(html, /<section/);
  assert.match(guidance.markup(describe({status: 'failed'}), {esc}), /data-value="diagnostics"/);
  assert.equal(guidance.markup({...model, title: ''}, {esc}), '');
});
