// 模块编辑采用 Python；source.header 保留为旧存档中的公共代码字段。
function pythonModuleSource(kind, code) {
  return {
    runtime: kind === 'valve'
      ? `# ${code} · 运行函数\n# 参数与端口由模块定义提供\n\ndef run():\n    # 读取当前已生效的设备参数\n    opening = OPENING / 100.0\n\n    # 在此描述设备关系，供全网求解使用\n    return {"opening_ratio": opening}\n`
      : `# ${code} · 运行函数\ndef run():\n    # 在此编辑设备算法\n    pass\n`,
    header: `# ${code} · 公共代码\nfrom dataclasses import dataclass\n\n\n@dataclass\nclass PortState:\n    pressure: float = 0.201325  # MPa\n    temperature: float = 20.0  # °C\n    density: float = 998.2  # kg/m³\n`,
    design: [80, 65, 40].map((opening, i) => kind === 'valve'
      ? `# 库值 ${i + 1} · ${['额定工况', '部分负荷', '调试备份'][i]}\ndef design${i + 1}():\n    return {"OPENING": ${opening}.0, "KV": 16.0}\n`
      : `# ${code} · 库值 ${i + 1}\ndef design${i + 1}():\n    # 返回此方案的设计参数\n    return {}\n`)
  };
}
function legacyModuleSource(kind, code) {
  return {
    runtime: kind === 'valve'
      ? `// ${code} · 运行函数\n// 参数与端口由模块定义提供\n\nvoid Run() {\n  // 读取已接受的端口状态\n  double opening = OPENING / 100.0;\n\n  // 提供设备关系，由全网统一求解\n  // 运行代码在本原型中仅作编辑预览\n}\n`
      : `// ${code} · 运行函数\nvoid Run() {\n  // 在此编辑设备算法\n  // 当前原型不编译或执行代码\n}\n`,
    header: `#pragma once\n\n// ${code} · 公共声明\nstruct PortState {\n  double pressure;    // Pa\n  double temperature; // K\n  double density;     // kg/m³\n};\n`,
    design: [80, 65, 40].map((opening, i) => kind === 'valve'
      ? `// 库值 ${i + 1} · ${['额定工况', '部分负荷', '调试备份'][i]}\nvoid Design${i + 1}() {\n  OPENING = ${opening}.0;\n  KV = 16.0;\n}\n`
      : `// ${code} · 库值 ${i + 1}\nvoid Design${i + 1}() {\n  // 编辑设计参数\n}\n`)
  };
}
function normalizePythonSource(m) {
  if (m.sourceFormat === 'python-v1') return;
  const next = pythonModuleSource(m.kind, m.code);
  const candidates = [m.code, MODULE_SPECS.find(spec => spec[0] === m.kind)?.[2]].filter(Boolean).map(code => legacyModuleSource(m.kind, code));
  const same = (a, b) => typeof a === 'string' && a.replace(/\r\n/g, '\n') === b;
  for (const key of ['runtime', 'header']) if (candidates.some(old => same(m.source[key], old[key]))) m.source[key] = next[key];
  m.source.design = m.source.design.map((source, i) => candidates.some(old => same(source, old.design[i])) ? next.design[i] : source);
  m.sourceFormat = 'python-v1';
}
// 浏览器仅做轻量结构检查：忽略 Python 注释与字符串中的括号，不执行代码。
function pythonCodeIssue(source) {
  const stack = [], pairs = { ')': '(', ']': '[', '}': '{' };
  let i = 0, line = 1, clean = '';
  while (i < source.length) {
    const c = source[i];
    if (c === '\n') { line++; clean += c; i++; continue; }
    if (c === '#') {
      while (i < source.length && source[i] !== '\n') i++;
      continue;
    }
    if (c === '"' || c === "'") {
      const startLine = line, quote = source.slice(i, i + 3) === c.repeat(3) ? c.repeat(3) : c;
      i += quote.length; clean += '0';
      let closed = false;
      while (i < source.length) {
        if (source.slice(i, i + quote.length) === quote) { i += quote.length; closed = true; break; }
        if (source[i] === '\\') { if (source[i + 1] === '\n') { line++; clean += '\n'; } i += 2; continue; }
        if (source[i] === '\n') { if (quote.length === 1) break; line++; clean += '\n'; }
        i++;
      }
      if (!closed) return `第 ${startLine} 行：字符串未闭合。`;
      continue;
    }
    if ('([{'.includes(c)) stack.push({ char: c, line });
    else if (pairs[c] && stack.pop()?.char !== pairs[c]) return `第 ${line} 行：括号不配对。`;
    clean += c; i++;
  }
  if (stack.length) return `第 ${stack.at(-1).line} 行：括号不配对。`;
  const legacyLine = clean.split('\n').findIndex(text => /^\s*(?:void\s+\w+\s*\(|struct\s+\w+|\/\/)/.test(text));
  if (legacyLine >= 0) return `第 ${legacyLine + 1} 行：检测到旧版代码写法，请改为 Python；已保留原文。`;
  return '';
}
