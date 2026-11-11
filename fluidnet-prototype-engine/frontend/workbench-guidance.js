/* Display-only reminders for states that need attention. Normal operation stays quiet. */
export const FluidNetWorkbenchGuidance = (() => {
  const actionIcons = {pending: 'SlidersHorizontal', diagnostics: 'Info'};
  const count = value => Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;

  function describe({pendingCount = 0, pendingDevices = 0, status = 'ready',
    hasResult = false, stale = false, connectionError = false} = {}) {
    const pending = count(pendingCount);
    const devices = count(Array.isArray(pendingDevices) ? pendingDevices.length : pendingDevices);
    const result = (title = '', detail = '', tone = '', action = '', label = '') => ({step: '', title, detail, tone, action, label});

    if (status === 'failed') return result('本次运行失败',
      `${hasResult ? '保留失败前结果。' : '尚无有效结果。'}${stale && hasResult ? '结果已过期。' : ''}`,
      'error', 'diagnostics', '查看原因');

    if (connectionError) return result('连接中断，正在重连', '运行状态暂不可确认。', 'warn');

    if (pending) return result(`${devices ? `${devices} 台设备 · ` : ''}${pending} 项修改尚未应用`,
      '运行使用已应用参数。', 'warn', 'pending', '查看修改');

    if (stale && hasResult) return result('结果已过期', '重新运行或单步以更新。', 'warn');

    return result();
  }

  function markup(model, {esc, icon = () => ''}) {
    if (!model.title) return '';
    const button = Object.hasOwn(actionIcons, model.action) && model.label
      ? `<button type="button" class="btn small workbench-next-action" data-action="workbench-next" data-value="${esc(model.action)}">${icon(actionIcons[model.action])}${esc(model.label)}</button>` : '';
    return `<div class="workbench-next"><div class="workbench-next-copy ${esc(model.tone || '')}"><strong>${esc(model.title)}</strong><p>${esc(model.detail)}</p></div>${button}</div>`;
  }

  return {describe, markup};
})();

export default FluidNetWorkbenchGuidance;
