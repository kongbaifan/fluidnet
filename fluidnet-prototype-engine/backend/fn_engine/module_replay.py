"""Replay one frozen callback in a fresh Worker, without solving or committing a project."""
from copy import deepcopy
import json

from .model_types.http import ModuleReplayRequest, ModuleReplayResponse
from .model_types.protocol import ModuleReplaySnapshot
from .module_state import MAX_RESULT_BYTES, checked_result, checked_state

PHASES = {'initialize', 'evaluate', 'thermal', 'observe', 'jacobian', 'commit_step'}


def capture_failure(definition, fluid, port_fluids, execution, inputs, diagnostic):
    """Build bounded transport data from a pre-callback copy, not mutated failure outputs."""
    from .runtime import module_content_hash, module_definition_hash
    if execution.phase not in PHASES:
        return None
    try:
        payload = {'format_version': 1, 'capture_kind': 'callback_input',
            'module': definition.model_dump(mode='json'), 'parameters': inputs['parameters'],
            'state': inputs['state'], 'fluid': fluid.model_dump(mode='json'),
            'port_fluids': {key: value.model_dump(mode='json') for key, value in port_fluids.items()},
            'ports': {key: value.model_dump(mode='json') for key, value in inputs['ports'].items()},
            'channels': {key: value.model_dump(mode='json') for key, value in inputs['channels'].items()},
            'execution': execution.model_dump(mode='json'),
            'content_hash': module_content_hash(definition), 'definition_hash': module_definition_hash(definition),
            'failure': diagnostic.model_dump(mode='json')}
        if inputs['refrigeration'] is not None:
            payload['refrigeration'] = inputs['refrigeration'].model_dump(mode='json')
        if len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_RESULT_BYTES:
            return None
        return payload
    except (TypeError, ValueError, OverflowError):
        # The original failure must survive even if inputs cannot be serialized.
        return None


def failure_snapshot(error):
    """Find a captured callback even when a session wraps it to preserve accepted history."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        snapshot = getattr(error, 'replay', None)
        if snapshot:
            try:
                parsed = ModuleReplaySnapshot.model_validate(snapshot)
                checked_result(parsed)
                return parsed.model_dump(mode='json', exclude_none=True)
            except (ValueError, TypeError):
                pass
        error = error.__cause__ if error.__cause__ is not None else error.__context__
    return None


def validate_snapshot(snapshot):
    from .runtime import module_content_hash, module_definition_hash
    from .module_contracts import check_module_compatibility
    if snapshot.module.runtime != 'python' or snapshot.module.composite is not None:
        raise ValueError('失败复现只执行已捕获的 Python 单模块回调')
    if snapshot.execution.phase not in PHASES:
        raise ValueError('该阶段不支持失败回调复现')
    if snapshot.execution.phase == 'commit_step' and snapshot.execution.dt_s is None:
        raise ValueError('commit_step 复现缺少真实 dt_s')
    if snapshot.execution.time_s is None:
        raise ValueError('失败回调复现缺少真实仿真时刻')
    if snapshot.content_hash != module_content_hash(snapshot.module) or snapshot.definition_hash != module_definition_hash(snapshot.module):
        raise ValueError('失败快照的冻结源码或定义哈希不匹配')
    if snapshot.module.content_hash not in (None, snapshot.content_hash) or snapshot.module.definition_hash not in (None, snapshot.definition_hash):
        raise ValueError('冻结模块声明哈希与失败快照不一致')
    if snapshot.execution.phase in {'thermal', 'observe', 'jacobian'}:
        needed = 'hydraulic.derivatives.v1' if snapshot.execution.phase == 'jacobian' else snapshot.execution.phase+'.v1'
        if not snapshot.module.sdk or needed not in snapshot.module.sdk.capabilities:
            raise ValueError('冻结模块没有声明该复现阶段的能力')
    if snapshot.module.execution_role and snapshot.execution.phase == 'evaluate' and snapshot.refrigeration is None:
        raise ValueError('制冷求值复现缺少原始节流流股输入')
    if snapshot.refrigeration is not None and not snapshot.module.execution_role:
        raise ValueError('普通流体模块不能携带制冷角色输入')
    check_module_compatibility(snapshot.module)
    checked_state(snapshot.state)
    checked_result(snapshot)


def replay_in_worker(payload):
    """Dispatch exactly the captured callback; skip initialize for later lifecycle phases."""
    from .runtime import InProcessModuleRunner, ModuleContext, RuntimeErrorBase
    from .module_diagnostics import exception_diagnostic
    snapshot = ModuleReplaySnapshot.model_validate(payload)
    validate_snapshot(snapshot)
    info = snapshot.execution
    diagnostics = []
    result = {}
    try:
        runner = InProcessModuleRunner(snapshot.module, deepcopy(snapshot.parameters), snapshot.fluid,
            deepcopy(snapshot.state), snapshot.port_fluids, run_id=info.run_id, instance_id=info.instance_id)
        ctx = ModuleContext(deepcopy(snapshot.parameters), snapshot.fluid,
            deepcopy(snapshot.ports), deepcopy(snapshot.state), deepcopy(snapshot.channels), snapshot.port_fluids,
            execution=info, refrigeration_input=deepcopy(snapshot.refrigeration))
        callback = getattr(runner.module, info.phase, None)
        if not callable(callback):
            raise ValueError('冻结模块没有所记录的回调')
        runner._invoke(callback, ctx, *([info.dt_s] if info.phase == 'commit_step' else []))
        diagnostics = ctx.diagnostics
        result = {'variables': ctx.variables, 'state': checked_state(ctx.state),
            'relations': [relation.model_dump(mode='json') for relation in ctx.net.relations],
            'heat_w': ctx.heat_w, 'derivatives': ctx.derivatives}
        if ctx._refrigeration is not None and ctx._refrigeration.result is not None:
            result['refrigeration'] = ctx._refrigeration.result.model_dump(mode='json')
        status = 'failed' if any(d.severity == 'error' for d in diagnostics) else 'completed'
    except Exception as error:
        status = 'failed'
        diagnostics = error.diagnostics if isinstance(error, RuntimeErrorBase) and error.diagnostics else [
            exception_diagnostic(error, snapshot.module, info)]
    failure = snapshot.failure
    matched = any((d.code, d.message, d.source_file, d.source_line, d.phase) ==
                  (failure.code, failure.message, failure.source_file, failure.source_line, failure.phase)
                  for d in diagnostics if d.severity == 'error')
    response = ModuleReplayResponse(module_id=snapshot.module.id, status=status, matched_failure=matched,
        execution=info, content_hash=snapshot.content_hash, definition_hash=snapshot.definition_hash,
        diagnostics=diagnostics, result=result)
    checked_result(response)
    return response.model_dump(mode='json')


def replay_module(request: ModuleReplayRequest):
    from .runtime import WorkerProcess
    snapshot = request.replay
    validate_snapshot(snapshot)
    worker = WorkerProcess(snapshot.module, snapshot.parameters, snapshot.fluid)
    try:
        return ModuleReplayResponse.model_validate(worker._request({
            'action': 'replay', 'replay': snapshot.model_dump(mode='json')}))
    finally:
        # No finalize or commit of original state; terminate this disposable Worker.
        worker.close(force=True)
