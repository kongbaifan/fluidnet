/* Read-only, one-device path inspection. Never infer a flow path from layout or port count. */
window.FluidNetPathTrace = (() => {
  function channels(definition) {
    const ports = new Set((definition?.ports || []).map(p => p.id));
    return (definition?.manifest?.channels ?? definition?.channels ?? []).map(c => ({
      id: c.id, name: c.name || c.id, input: c.input_port ?? c.input,
      output: c.output_port ?? c.output, enabled: c.enabled !== false,
    })).filter(c => c.enabled && ports.has(c.input) && ports.has(c.output) && c.input !== c.output);
  }
  function describe(owner, nodeId, portId, definition) {
    const locate = id => {
      for (const page of owner.pages) {
        const node = page.nodes.find(n => n.id === id);
        if (node) return {node, page};
      }
      return null;
    };
    const origin = locate(nodeId);
    if (!origin) return null;
    const module = definition(origin.node), allPorts = module?.ports || [];
    const start = allPorts.find(p => p.id === portId);
    if (portId && !start) return null;
    const declared = channels(module), ids = new Set(start ? [portId] : allPorts.map(p => p.id));
    // Follow only connected declared channels inside the selected device. A heat exchanger's
    // hot/cold paths share a body, but no endpoint: they remain separate.
    if (start) {
      let previous;
      do {
        previous = ids.size;
        for (const c of declared) if (ids.has(c.input) || ids.has(c.output)) {
          ids.add(c.input); ids.add(c.output);
        }
      } while (ids.size !== previous);
    }
    const matched = declared.filter(c => ids.has(c.input) && ids.has(c.output));
    const connections = [];
    for (const page of owner.pages) for (const edge of page.edges) {
      const local = edge[1] === nodeId && ids.has(edge[2]) ? edge.slice(1, 3)
        : edge[3] === nodeId && ids.has(edge[4]) ? edge.slice(3, 5) : null;
      if (!local) continue;
      const remote = edge[1] === nodeId ? edge.slice(3, 5) : edge.slice(1, 3);
      const found = locate(remote[0]);
      const port = found && definition(found.node)?.ports?.find(p => p.id === remote[1]);
      connections.push({id: edge[0], local, remote, valid: !!port,
        pageId: found?.page.id, pageName: found?.page.name || '',
        nodeName: found?.node.name || remote[0], portLabel: port?.label || remote[1],
        crossPage: !!found && found.page.id !== origin.page.id});
    }
    return {nodeId, name: origin.node.name, pageId: origin.page.id, start,
      ports: allPorts.filter(p => ids.has(p.id)), channels: matched, connections};
  }
  function markup(trace, esc) {
    if (!trace) return '';
    const title = trace.start ? `${trace.nodeId} · ${trace.start.label || trace.start.id}` : `${trace.nodeId} · ${trace.name}`;
    const routes = trace.channels.map(c => `${c.name}（${c.input} ↔ ${c.output}）`).join('；');
    return `<div class="path-trace-title"><strong>${esc(title)}</strong><button type="button" data-trace-close aria-label="关闭通路追踪">×</button></div>
      <p>${esc(routes || '未声明内部通路，仅显示已选端口的实际连线。')}</p>
      <p class="path-trace-scope">${trace.start ? '当前设备通路及相邻连接' : '各条内部通路分别显示'} · 连线方向不代表当前流向</p>
      <div class="path-trace-links">${trace.ports.map(p => {
        const connections = trace.connections.filter(c => c.local[1] === p.id);
        return connections.length ? connections.map(c => c.valid
          ? `<button type="button" data-action="jump-page-link" data-id="${esc(c.id)}" data-node="${esc(c.remote[0])}" data-trace-destination="${esc(c.remote.join(':'))}">${esc(p.label || p.id)} ↔ ${c.crossPage ? '跨页 · ' : ''}${esc(c.pageName)} · ${esc(c.remote.join(':'))} ${esc(c.nodeName)} <span aria-hidden="true">↗</span></button>`
          : `<span class="path-trace-invalid">${esc(p.label || p.id)}：连接端点已失效</span>`).join('')
          : `<span>${esc(p.label || p.id)}：未连接</span>`;
      }).join('')}</div>`;
  }
  return {channels, describe, markup};
})();
