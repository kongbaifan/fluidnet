/* Editable control programs and their projection into the engine contract. */
window.FluidNetControls = (() => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const names = value => [...new Set((value || '').split(/[\s,，]+/).filter(Boolean))];
  const languageOf = source => /(^|\n)\s*def (initialize|step)\(/.test(source || '') ? 'python' : 'legacy';
  const SOURCE = 'def initialize(ctx):\n    pass\n\n\ndef step(ctx, dt_s):\n    pass\n\n\ndef finalize(ctx):\n    pass\n';
  const FIELDS = ['id', 'language', 'enabled', 'source', 'sample_s', 'inputs', 'outputs', 'timeout_s', 'content_hash'];
  const MAX_PROGRAMS = 16;
  function fromLegacy(owner) {
    const language = owner.controlLanguage || languageOf(owner.control);
    return {id: 'control', name: owner.controlConfig?.name || '控制程序', language,
      enabled: language === 'python' && !!owner.controlEnabled, source: owner.control || '',
      sample_s: Number(owner.controlConfig?.period ?? 100) / 1000,
      inputs: names(owner.controlInputs), outputs: names(owner.controlOutputs),
      timeout_s: Number(owner.controlTimeout ?? 5)};
  }
  function runtime(program) {
    return Object.fromEntries(FIELDS.filter(key => program[key] !== undefined).map(key => [key, clone(program[key])]));
  }
  function projectEditor(owner) {
    const selected = owner.controlPrograms.find(program => program.id === owner.selectedControlId);
    owner.control = selected?.source || '';
    owner.controlLanguage = selected?.language || 'python';
    owner.controlEnabled = !!selected?.enabled;
    owner.controlInputs = (selected?.inputs || []).join('\n');
    owner.controlOutputs = (selected?.outputs || []).join('\n');
    owner.controlTimeout = selected?.timeout_s ?? 5;
    owner.controlConfig = {...owner.controlConfig, name: selected?.name || '', period: (selected?.sample_s ?? .1) * 1000};
    // Legacy text and empty disabled editor drafts are saved with the project,
    // but cannot enter the Python-only, nonempty-source engine contract.
    owner.controlScripts = owner.controlPrograms.filter(program => program.language === 'python'
      && (program.enabled || program.source.length)).map(runtime);
    return selected || null;
  }
  function normalize(owner) {
    if (owner.controlPrograms === undefined) {
      owner.controlPrograms = owner.controlScripts?.length
        ? owner.controlScripts.map(program => ({...clone(program), name: program.id === 'control'
          ? owner.controlConfig?.name || program.id : program.id}))
        : typeof owner.control === 'string' ? [fromLegacy(owner)] : [];
      const single = owner.controlPrograms.length === 1 && owner.controlPrograms[0];
      if (single?.id === 'control' && typeof owner.control === 'string') {
        // The previous editor only refreshed controlScripts when starting a run;
        // its scalar editor fields can contain newer, saved single-script edits.
        const editor = fromLegacy(owner), changed = single.source !== editor.source;
        Object.assign(single, editor, {
          sample_s: owner.controlConfig?.period === undefined ? single.sample_s : editor.sample_s,
          inputs: owner.controlInputs === undefined ? single.inputs : editor.inputs,
          outputs: owner.controlOutputs === undefined ? single.outputs : editor.outputs,
          enabled: owner.controlEnabled === undefined ? single.enabled : editor.enabled,
          timeout_s: owner.controlTimeout === undefined ? single.timeout_s ?? 5 : editor.timeout_s
        });
        if (changed) delete single.content_hash;
      }
    } else if (Array.isArray(owner.controlPrograms) && owner.controlLanguage === undefined && typeof owner.control === 'string') {
      // Old integrations may still replace the single editor field without a
      // language marker. Preserve that text on the selected entry, never drop
      // the other programs while upgrading this legacy shape.
      const selected = owner.controlPrograms.find(program => program.id === owner.selectedControlId) || owner.controlPrograms[0];
      if (selected && selected.source !== owner.control) {
        selected.source = owner.control; selected.language = languageOf(owner.control);
        selected.enabled = false; delete selected.content_hash;
      }
    }
    if (!Array.isArray(owner.controlPrograms) || owner.controlPrograms.length > MAX_PROGRAMS)
      throw Error(`每个项目最多保留 ${MAX_PROGRAMS} 个控制脚本。`);
    const ids = new Set();
    for (const program of owner.controlPrograms) {
      if (!program || typeof program.id !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(program.id) || ids.has(program.id)
        || typeof program.source !== 'string') throw Error('控制脚本标识需合法且唯一，源码必须是文本。');
      ids.add(program.id);
      program.name ??= program.id; program.language ??= 'python';
      if (!['python', 'legacy'].includes(program.language)) throw Error('控制脚本语言不支持。');
      program.enabled = program.language === 'python' && !!program.enabled;
      program.sample_s ??= .1; program.timeout_s ??= 5;
      program.inputs ??= []; program.outputs ??= [];
      if (!Array.isArray(program.inputs) || !Array.isArray(program.outputs)) throw Error('控制脚本输入输出必须是变量列表。');
    }
    if (!ids.has(owner.selectedControlId)) owner.selectedControlId = owner.controlPrograms[0]?.id || '';
    projectEditor(owner);
    return owner.controlPrograms;
  }
  function current(owner) {
    normalize(owner);
    return owner.controlPrograms.find(program => program.id === owner.selectedControlId) || null;
  }
  function select(owner, id) {
    normalize(owner);
    if (!owner.controlPrograms.some(program => program.id === id)) throw Error('控制脚本不存在。');
    owner.selectedControlId = id; projectEditor(owner);
  }
  function update(owner, changes) {
    const program = current(owner);
    if (!program) throw Error('请先新建控制脚本。');
    if ('source' in changes && changes.source !== program.source) delete program.content_hash;
    Object.assign(program, clone(changes));
    if (program.language !== 'python') program.enabled = false;
    projectEditor(owner);
    return program;
  }
  function add(owner, id, name) {
    normalize(owner);
    if (owner.controlPrograms.length >= MAX_PROGRAMS) throw Error(`每个项目最多保留 ${MAX_PROGRAMS} 个控制脚本。`);
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id) || owner.controlPrograms.some(program => program.id === id))
      throw Error('脚本标识须以字母开头，仅含字母、数字、下划线或连字符，且不能重复。');
    owner.controlPrograms.push({id, name: name || id, language: 'python', enabled: false,
      source: SOURCE, sample_s: .1, inputs: [], outputs: [], timeout_s: 5});
    select(owner, id);
  }
  function remove(owner, id) {
    normalize(owner);
    owner.controlPrograms = owner.controlPrograms.filter(program => program.id !== id);
    normalize(owner);
  }
  function replaceScripts(owner, scripts) {
    const old = normalize(owner), byId = new Map(old.map(program => [program.id, program]));
    const projectedIds = new Set(owner.controlScripts.map(program => program.id));
    owner.controlPrograms = scripts.map(program => ({...clone(program), name: byId.get(program.id)?.name || program.id}));
    owner.controlPrograms.push(...old.filter(program => !projectedIds.has(program.id)
      && !owner.controlPrograms.some(next => next.id === program.id)));
    normalize(owner);
  }
  function selectedScript(owner) {
    const program = current(owner);
    if (!program) throw Error('请先新建控制脚本。');
    if (program.language !== 'python') throw Error('请先将旧脚本迁移为 Python，再预览或启用控制。');
    return runtime(program);
  }
  function key(owner) {
    return normalize(owner).map(program => Object.fromEntries(FIELDS.filter(field => field !== 'content_hash')
      .map(field => [field, program[field]])));
  }
  return {normalize, current, select, update, add, remove, replaceScripts, selectedScript, key, names, MAX_PROGRAMS};
})();
