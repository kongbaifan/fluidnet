// 分组独立于模块保存，空分组也可恢复；旧存档从模块分类补齐分组。
const DEFAULT_MODULE_GROUPS = [...new Set(MODULE_SPECS.map(spec => spec[3]))];
const groupNameKey = name => name.normalize('NFC').toLocaleLowerCase();
function moduleGroupNames(data = state) {
  return [...new Set([...DEFAULT_MODULE_GROUPS, ...(data.moduleGroups || []),
    ...data.modules.map(m => m.category).filter(name => typeof name === 'string' && name.trim())])];
}

function checkGroupName(value, except = '') {
  const name = String(value || '').trim().normalize('NFC');
  if (!name) throw Error('请输入分组名称。');
  if (name.length > 32) throw Error('分组名称最多 32 个字符。');
  if (/[\u0000-\u001f\u007f]/.test(name)) throw Error('分组名称不能包含换行或控制字符。');
  if (name === '全部模块' || moduleGroupNames().some(group => group !== except && groupNameKey(group) === groupNameKey(name))) throw Error('此分组名称已存在，请换一个名称。');
  return name;
}

function collectModuleGroups(data) {
  const groups = moduleGroupNames(data).filter(name => !DEFAULT_MODULE_GROUPS.includes(name));
  if (groups.length > 64) throw Error('最多保留 64 个自建模块分组。');
  return groups;
}

function validateModuleGroups(data) {
  if (data.moduleGroups !== undefined && (!Array.isArray(data.moduleGroups) || data.moduleGroups.length > 64)) throw Error('模块分组列表不合法。');
  const names = data.moduleGroups || [];
  const validName = name => typeof name === 'string' && !!name.trim() && name === name.trim() && name.length <= 32 && !/[\u0000-\u001f\u007f]/.test(name) && name !== '全部模块';
  if (names.some(name => !validName(name) || DEFAULT_MODULE_GROUPS.includes(name)) || new Set(names.map(groupNameKey)).size !== names.length) throw Error('模块分组名称不合法或重复。');
  if (data.modules.some(m => m.category !== undefined && !validName(m.category))) throw Error('模块所属分组不合法。');
  collectModuleGroups(data);
}

function normalizeModuleGroups() {
  for (const m of state.modules) if (!m.category) m.category = '自定义模块';
  state.moduleGroups = collectModuleGroups(state);
  if (ui.category !== '全部模块' && !moduleGroupNames().includes(ui.category)) ui.category = '全部模块';
}

function moduleGroupDialog(previous = '') {
  if (previous && !state.moduleGroups.includes(previous)) throw Error('内置分类保留原名称。');
  openDialog(previous ? '重命名分组' : '新增分组', previous ? '组内模块会同步更新分类，项目设备与型号保持原引用。' : '创建一个空分组，随后可在组内新建模块或移入已有模块。',
    field('groupName', '分组名称', previous, 'required maxlength="32" placeholder="例如：冷却水系统"'), data => {
      const name = checkGroupName(data.groupName, previous);
      if (!previous && state.moduleGroups.length >= 64) throw Error('最多保留 64 个自建模块分组。');
      if (previous) {
        state.moduleGroups = state.moduleGroups.map(group => group === previous ? name : group);
        for (const m of state.modules) if (m.category === previous) m.category = name;
      } else state.moduleGroups.push(name);
      ui.category = name; ui.moduleSearch = ''; markDirty(); render();
      msg(previous ? '分组已重命名；保存原型后保留。' : '分组已创建，可新建模块或将已有模块移入。');
    }, previous ? '保存名称' : '创建分组');
}

function removeModuleGroup(name) {
  if (!state.moduleGroups.includes(name)) throw Error('内置分类不能删除。');
  if (state.modules.some(m => m.category === name)) throw Error('请先将组内模块移到其他分组，再删除空分组。');
  confirmChange('删除空分组', `删除“${name}”，现有模块、型号和项目设备保持原样。`, () => {
    if (state.modules.some(m => m.category === name)) throw Error('分组中仍有模块，请先调整所属分组。');
    state.moduleGroups = state.moduleGroups.filter(group => group !== name);
    ui.category = '全部模块'; markDirty(); render(); msg('空分组已删除。');
  }, '删除分组');
}

function moveModuleGroup(id) {
  const m = state.modules.find(m => m.id === id);
  if (!m) return;
  openDialog('调整模块分组', `${m.name} · 仅改变模块库中的归类。`,
    selectField('category', '所属分组', moduleGroupNames().map(name => [name, name]), m.category), data => {
      if (!moduleGroupNames().includes(data.category)) throw Error('请选择已有分组。');
      if (m.category !== data.category) { m.category = data.category; markDirty(); }
      ui.category = m.category; ui.moduleSearch = ''; render(); msg(`${m.name} 已归入“${m.category}”。`);
    }, '确认分组');
}

function moduleGroupSidebar() {
  const categories = ['全部模块', ...moduleGroupNames()];
  return `<aside class="side-nav module-group-nav" aria-label="模块分类">
    <div class="module-group-heading"><span>模块分类</span>${btn('new-module-group', '新增分组', 'Plus', '', 'ghost small')}</div>
    <div class="module-group-list">${categories.map(name => {
      const count = name === '全部模块' ? state.modules.length : state.modules.filter(m => m.category === name).length;
      return `<button data-action="module-category" data-value="${esc(name)}" class="${ui.category === name ? 'active' : ''}" aria-pressed="${ui.category === name}" title="${esc(name)}">${icon(name === '全部模块' ? 'Boxes' : 'Folder')}<span>${esc(name)}</span><small class="push muted">${count}</small></button>`;
    }).join('')}</div><div class="spacer"></div><div class="module-group-links"><button data-action="nav" data-route="nodes">${icon('Waypoints')}节点与端口定义</button><button data-action="page-map">${icon('LayoutDashboard')}页面导航</button></div>
  </aside>`;
}

function renderModules() {
  const groups = moduleGroupNames();
  if (ui.category !== '全部模块' && !groups.includes(ui.category)) ui.category = '全部模块';
  const members = state.modules.filter(m => ui.category === '全部模块' || m.category === ui.category);
  const list = members.filter(m => (m.name + m.code).toLowerCase().includes(ui.moduleSearch.toLowerCase()));
  const custom = state.moduleGroups.includes(ui.category), blankGroup = ui.category !== '全部模块' && !members.length;
  return `<div class="page-shell">${heading('模块库', '定义可复用的设备：图形、端口、通路、变量与算法。', btn('nav', '节点定义', 'Waypoints', 'data-route="nodes"') + btn('new-module', '新建模块', 'Plus', '', 'primary'))}
    <div class="split-view">${moduleGroupSidebar()}<div class="module-content">
      ${ui.category !== '全部模块' ? `<div class="module-group-context"><div class="grow"><h2>${esc(ui.category)}</h2><small>${custom ? '自建分组' : '内置分类'} · ${members.length} 个模块</small></div>${custom ? btn('rename-module-group', '重命名', 'Pencil', `data-value="${esc(ui.category)}"`, 'small') + btn('delete-module-group', '删除分组', 'Trash2', `data-value="${esc(ui.category)}" ${members.length ? 'disabled title="请先将组内模块移到其他分组"' : ''}`, 'small') : ''}</div>` : ''}
      <div class="filterbar"><label class="search">${icon('Search')}<input data-filter="moduleSearch" aria-label="搜索模块" placeholder="名称或模块标识" value="${esc(ui.moduleSearch)}"></label><span class="push muted">${list.length} 个模块</span><div class="segmented" role="group" aria-label="模块库视图">${[['cards', '卡片视图', 'Grid2X2'], ['list', '紧凑列表', 'List']].map(([value, label, glyph]) => `<button data-action="module-view" data-value="${value}" aria-label="${label}" title="${label}" aria-pressed="${ui.moduleView === value}" class="${ui.moduleView === value ? 'active' : ''}">${icon(glyph)}</button>`).join('')}</div>${btn('compile-preview', '批量检查预览', 'CheckCheck', '', 'small')}</div>
      <div id="module-results" class="module-grid${ui.moduleView === 'list' ? ' module-compact-list' : ''}">${list.map(m => `<article class="module-card" data-module-id="${m.id}"><div class="row module-card-title"><span class="object-icon">${icon(m.icon)}</span><div class="grow"><h3>${esc(m.name)}</h3><small class="muted mono">${esc(m.code)}</small></div>${badge('v' + m.version)}</div><button class="module-group-chip" data-action="move-module-group" data-id="${m.id}" aria-label="调整 ${esc(m.name)} 的分组" title="调整所属分组">${icon('Folder')}<span>${esc(m.category)}</span>${icon('ChevronDown')}</button><p>${esc(m.description)}</p><div class="stat-line"><span>${m.ports.length} 个端口</span><span>${m.channels.length} 条通路</span><span>${m.variables.length} 个变量</span></div><div class="card-footer">${btn('edit-module', '编辑模块', 'Pencil', `data-id="${m.id}"`, 'small')}<span class="push"></span>${ibtn('insert-module', '插入项目 ' + m.name, 'Plus', `data-id="${m.id}"`)}</div></article>`).join('') || (blankGroup ? empty('分组已建好，添加第一个模块', '可在此分组中新建模块，也可从“全部模块”的模块卡片调整所属分组。', btn('new-module', '在此分组新建模块', 'Plus', '', 'primary')) : empty('没有匹配的模块', '尝试其他分类或关键词。'))}</div>
    </div></div></div>`;
}
