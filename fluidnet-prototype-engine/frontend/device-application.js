/* Device parameter application boundary. It owns the preview ticket and the
 * asynchronous acknowledgement guard; the shell supplies project/model adapters. */
window.FluidNetDeviceApplication = (() => {
  function create({state, projectRunState, projectState, engine, performance, clone, sameValue,
    ownerOfInstance, moduleOf, instanceWritable, ensureInstanceVariables, validateInstanceEdits,
    markDirty, remember, render}) {
    const pending = new WeakSet();

    function capture(node, values, bank = -1) {
      const owner = ownerOfInstance(node), variables = moduleOf(node).variables.filter(instanceWritable);
      const parameters = bank < 0
        ? clone(node.draft)
        : Object.fromEntries(variables.filter(v => v.origin === 'parameter').map(v => [v.param, clone(values[v.id])]));
      return {
        ticket: projectRunState.capture(state(), owner), values: clone(values), parameters,
        performance: performance?.capture(node, bank < 0), applied: clone(node.params), variables,
        bank, draftModelId: node.draftModelId, modelId: bank < 0 ? node.draftModelId : null,
        modelVersion: bank < 0 ? node.draftModelVersion : null,
      };
    }

    async function apply(owner, node, application) {
      if (pending.has(node) || engine.isApplyingParameters?.(node)) throw Error('设备参数正在应用，请等待确认后再提交。');
      projectRunState.assertCurrent(state(), application.ticket);
      projectState.assertCurrent(state(), owner);
      projectState.node(owner, node);
      if (!sameValue(node.params, application.applied)) throw Error('设备参数已变化，请重新预览后应用。');
      if (application.performance && !sameValue(node.performanceData || {}, application.performance.current)) {
        throw Error('已应用性能资料已变化，请重新预览。');
      }
      validateInstanceEdits(node, application.values);
      const beforeDraft = clone(node.draft), beforeCustom = clone(ensureInstanceVariables(node).draft);
      const parameters = Object.fromEntries(Object.entries(application.parameters)
        .filter(([key, value]) => !sameValue(value, node.params[key])));
      const finish = () => {
        // Values typed while awaiting the acknowledgement remain drafts.
        const drafts = Object.fromEntries(Object.entries(application.parameters)
          .filter(([key]) => sameValue(node.draft[key], beforeDraft[key])));
        projectState.setDraft(owner, node, drafts);
        const data = clone(node.variableState);
        for (const variable of application.variables.filter(v => v.origin === 'custom')) {
          data.values[variable.id] = clone(application.values[variable.id]);
          if (sameValue(data.draft[variable.id], beforeCustom[variable.id])) {
            data.draft[variable.id] = clone(application.values[variable.id]);
          }
        }
        projectState.updateNode(owner, node, {variableState: data});
        if (application.performance) performance.commit(node, engine.manifestPayload(moduleOf(node)), application.performance);
        if (application.modelId) projectState.updateNode(owner, node, {modelId: application.modelId, modelVersion: application.modelVersion});
        if (node.draftModelId === application.draftModelId) projectState.updateNode(owner, node, {draftModelId: null, draftModelVersion: null});
        markDirty(owner);
      };
      pending.add(node);
      try {
        if (owner.run.live) await engine.applyParameters(owner, node, parameters, finish);
        else { remember(); projectState.applyParameters(owner, node, parameters); finish(); render(); }
      } finally { pending.delete(node); }
    }

    return {capture, apply, isPending: node => pending.has(node)};
  }
  return {create};
})();
