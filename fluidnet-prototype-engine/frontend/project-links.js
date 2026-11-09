/* Connections belong to the project; their source canvas stores the existing edge tuple. */
export const FluidNetLinks = (() => {
  const all = owner => owner.pages.flatMap(page => page.edges);
  function locate(owner, id) {
    for (const page of owner.pages) {
      const node = page.nodes.find(node => node.id === id);
      if (node) return {page, node};
    }
    return null;
  }
  const find = (owner, id) => all(owner).find(edge => edge[0] === id);
  const atPort = (owner, id, port, excluding) => all(owner).find(edge => edge[0] !== excluding &&
    ((edge[1] === id && edge[2] === port) || (edge[3] === id && edge[4] === port)));
  function check(owner, source, target, definition, excluding) {
    const start = locate(owner, source[0]), end = locate(owner, target[0]);
    const a = start && definition(start.node).ports.find(port => port.id === source[1]);
    const b = end && definition(end.node).ports.find(port => port.id === target[1]);
    if (!a || !b) throw Error('连接设备或端口已不存在，请重新选择。');
    if (source[0] === target[0]) throw Error('请选择另一台设备的端口。');
    if (a.domain !== b.domain) throw Error('两端的物理类型必须相同。');
    if (a.domain !== 'fluid' && a.direction === b.direction) throw Error('此类端口需要输入与输出相连。');
    if (atPort(owner, ...source, excluding) || atPort(owner, ...target, excluding))
      throw Error('此端口已经连接。请先断开原连接，或使用连接节点分支。');
    return {start, end, a, b};
  }
  function remove(owner, id) {
    for (const page of owner.pages) page.edges = page.edges.filter(edge => edge[0] !== id);
  }
  function candidates(owner, source, definition, {pageId, excluding} = {}) {
    return owner.pages.filter(page => !pageId || page.id === pageId).flatMap(page =>
      page.nodes.flatMap(node => definition(node).ports.flatMap(port => {
        try { check(owner, source, [node.id, port.id], definition, excluding); }
        catch { return []; }
        return [{page, node, port}];
      })));
  }
  function connect(owner, id, source, target, definition, replacing = false) {
    if (find(owner, id) && !replacing) throw Error('连接标识重复。');
    const {start, end, a} = check(owner, source, target, definition, replacing ? id : undefined);
    // Directed domains always serialize output → input, even when the user starts at the input.
    // Fluid connections retain the chosen orientation for reversible flow.
    const reverse = a.domain !== 'fluid' && a.direction === 'in';
    if (replacing) remove(owner, id);
    const edge = reverse ? [id, ...target, ...source] : [id, ...source, ...target];
    (reverse ? end : start).page.edges.push(edge);
    return edge;
  }
  function rehome(owner) {
    const edges = all(owner);
    for (const page of owner.pages) page.edges = [];
    for (const edge of edges) {
      const source = locate(owner, edge[1]);
      // Keep invalid references for diagnostics rather than silently dropping a connection.
      (source?.page || owner.pages[0]).edges.push(edge);
    }
  }
  function move(owner, id, pageId) {
    const source = locate(owner, id), target = owner.pages.find(page => page.id === pageId);
    if (!source || !target) throw Error('设备或目标画布不存在。');
    if (source.page === target) return;
    if (target.nodes.length >= 64) throw Error('目标画布已达到 64 台设备上限。');
    source.page.nodes = source.page.nodes.filter(node => node.id !== id);
    target.nodes.push(source.node);
    rehome(owner);
  }
  function removeNodes(owner, ids) {
    const removed = new Set(ids);
    for (const page of owner.pages) {
      page.nodes = page.nodes.filter(node => !removed.has(node.id));
      page.edges = page.edges.filter(edge => !removed.has(edge[1]) && !removed.has(edge[3]));
    }
  }
  function cross(owner, pageId) {
    return all(owner).flatMap(edge => {
      const source = locate(owner, edge[1]), target = locate(owner, edge[3]);
      if (!source || !target || source.page === target.page) return [];
      if (!pageId || source.page.id === pageId)
        return [{edge, local: edge.slice(1, 3), remote: edge.slice(3, 5), localPage: source.page, remotePage: target.page}];
      if (target.page.id === pageId)
        return [{edge, local: edge.slice(3, 5), remote: edge.slice(1, 3), localPage: target.page, remotePage: source.page}];
      return [];
    });
  }
  function validate(owner, definition, required = true) {
    const errors = [], used = new Set(), ids = new Set();
    for (const page of owner.pages) for (const edge of page.edges) {
      if (!Array.isArray(edge) || edge.length !== 5) {
        errors.push({text: '连接格式无效。', page: page.id}); continue;
      }
      const [id, na, pa, nb, pb] = edge;
      if (ids.has(id)) errors.push({text: `${id}：连接标识重复。`, page: page.id, node: na});
      ids.add(id);
      const a = locate(owner, na), b = locate(owner, nb);
      const ap = a && definition(a.node)?.ports.find(port => port.id === pa);
      const bp = b && definition(b.node)?.ports.find(port => port.id === pb);
      if (!ap || !bp) errors.push({text: `${id}：连接端口不存在。`, page: page.id, node: na});
      else if (ap.domain !== bp.domain || (ap.domain !== 'fluid' && ap.direction === bp.direction))
        errors.push({text: `${id}：两端物理类型或方向不兼容。`, page: page.id, node: na});
      for (const key of [na + ':' + pa, nb + ':' + pb]) {
        if (used.has(key)) errors.push({text: `${key}：端口重复连接。`, page: page.id, node: na});
        used.add(key);
      }
    }
    if (required) for (const page of owner.pages) for (const node of page.nodes)
      for (const port of definition(node).ports)
        if (port.required !== false && !used.has(node.id + ':' + port.id))
          errors.push({text: `${node.id} · ${port.label} 尚未连接。`, page: page.id, node: node.id});
    return errors;
  }
  return {all, locate, find, atPort, check, candidates, connect, remove, rehome, move, removeNodes, cross, validate};
})();

export default FluidNetLinks;
