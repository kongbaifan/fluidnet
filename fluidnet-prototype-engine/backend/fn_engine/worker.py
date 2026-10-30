from __future__ import annotations

import json
import os
import sys
import time
from contextlib import redirect_stdout, redirect_stderr

# 启动诊断：时间戳在导入任何 fn_engine 子模块之前采集。--startup-report 会把它写到 stderr
# （stdout 只走 JSON RPC，保持协议不变），startup_report 动作也能读回。
_STARTED_AT = time.perf_counter()

from .models import CommitStepRequest, EvaluateRequest, InitializeRequest, ModuleDefinition, ModuleRequestContext, RefrigerationEvaluateRequest

_IMPORTS_READY_AT = time.perf_counter()
_FIRST_REQUEST_AT: float | None = None


def _startup_snapshot() -> dict:
    properties = sys.modules.get('fn_engine.properties')
    return {
        'module_import_s': round(_IMPORTS_READY_AT - _STARTED_AT, 6),
        'first_request_uptime_s': None if _FIRST_REQUEST_AT is None else round(_FIRST_REQUEST_AT - _STARTED_AT, 6),
        'properties_imported': properties is not None,
        'probe_refprop': None if properties is None else bool(getattr(properties, 'PROBE_REFPROP', True)),
        'python': sys.version.split()[0],
        'pid': os.getpid(),
    }


def _ensure_lazy_properties():
    """把物性导入推迟到第一次真正访问 ``ctx.fluid``/``ctx.fluid_at`` 时。

    Worker 进程不必在初始化阶段就导入 CoolProp：控制 Worker、只做内置关系或纯代数计算的
    Python 模块都不需要物性。`PROBE_REFPROP=False` 仍保留原来的语义（API 进程已探测过，
    Worker 不再重复 REFPROP 预探测），只是在第一次物性访问前设置。

    这里只改写 Worker 进程内的 ``_LazyPropertyService._get``；API 进程不受影响。
    """
    from .runtime import _LazyPropertyService

    if getattr(_LazyPropertyService, '_fluidnet_lazy_properties', False):
        return
    original = _LazyPropertyService._get

    def _get(self):
        from . import properties
        properties.PROBE_REFPROP = False
        return original(self)

    _LazyPropertyService._get = _get
    _LazyPropertyService._fluidnet_lazy_properties = True


def main():
    runners = {}
    control = None

    def dispatch(message):
        # 注意：global 必须写在这里。写在 main() 里不会作用到嵌套的 dispatch，
        # 那样 `_FIRST_REQUEST_AT = ...` 会被当成 dispatch 的局部变量并在读取时报
        # “cannot access local variable”。
        global _FIRST_REQUEST_AT
        nonlocal control
        if _FIRST_REQUEST_AT is None:
            _FIRST_REQUEST_AT = time.perf_counter()
        action = message.get('action')
        if action == 'startup_report':
            return _startup_snapshot()
        if action in ('control_initialize', 'control_validate'):
            from .control import ControlRunner
            control = ControlRunner(message['definition'])
            return control.call('initialize', message) if action == 'control_initialize' else {'ok': True}
        if action in ('control_step', 'control_finalize'):
            if control is None:
                raise ValueError('控制 Worker 尚未初始化')
            return control.call('step' if action == 'control_step' else 'finalize', message)
        if action == 'design':
            _ensure_lazy_properties()
            from .design import run_in_worker
            return run_in_worker(message['definition'], message['parameters'], message['fluid'])
        key = message.get('instance_id', 'default')
        runner = runners.get(key)
        if action == 'batch':
            return {key: dispatch(item) for key, item in message['items'].items()}
        if action == 'finalize':
            errors = []
            for key, runner in runners.items():
                try:
                    context = message.get('contexts', {}).get(key)
                    runner.finalize(ModuleRequestContext.model_validate(context) if context is not None else None)
                except Exception as error:
                    errors.append(str(error))
            if errors:
                raise ValueError('; '.join(errors))
            return {'ok': True}
        if action in ('validate', 'initialize', 'parameters', 'evaluate', 'evaluate_refrigeration', 'commit_step'):
            _ensure_lazy_properties()
        if action == 'validate':
            from .runtime import _load_module, design_source, validate_lifecycle
            definition = ModuleDefinition.model_validate(message['definition'])
            target = _load_module(definition)
            validate_lifecycle(target)
            if design_source(definition).strip():
                from .design import load_design
                load_design(design_source(definition))
            return {'ok': True}
        if action == 'initialize':
            from .runtime import InProcessModuleRunner, RuntimeErrorBase, module_content_hash, module_definition_hash
            definition = ModuleDefinition.model_validate(message['definition'])
            request = InitializeRequest.model_validate(message['request'])
            if definition.execution_role and (request.package.module_id!=definition.id or
                    request.package.version!=f'{definition.version}.0.0' or
                    request.package.content_hash!=module_content_hash(definition) or
                    request.package.definition_hash!=module_definition_hash(definition)):
                raise RuntimeErrorBase('制冷 Worker 初始化的版本或双哈希不匹配',code='MODULE_PACKAGE_MISMATCH')
            runner = InProcessModuleRunner(definition, request.parameters, request.fluid, request.initial_state,
                                           request.port_fluids, run_id=request.run_id, instance_id=request.instance_id,
                                           cache_enabled=request.cache_enabled)
            runners[key] = runner
            return {'state': runner.initialize(request.context)}
        if runner is None:
            raise ValueError('Worker 尚未初始化')
        if action == 'parameters':
            if runner.definition.execution_role:
                from .refrigeration_roles import updated_role_parameters
                runner.parameters = updated_role_parameters(runner.definition,runner.parameters,message['parameters'])
            else:
                runner.parameters = dict(message['parameters'])
            return {'ok': True}
        if action == 'evaluate_refrigeration':
            return runner.evaluate_refrigeration(RefrigerationEvaluateRequest.model_validate(message['request'])).model_dump(mode='json')
        if action == 'evaluate':
            return runner.evaluate(EvaluateRequest.model_validate(message['request'])).model_dump(mode='json')
        if action == 'commit_step':
            return runner.commit_step(CommitStepRequest.model_validate(message['request'])).model_dump(mode='json')
        if action == 'prepare_step':
            return runner.prepare_step(CommitStepRequest.model_validate(message['request']),
                base_revision=message['base_revision'], authoritative_state=message['state']).model_dump(mode='json')
        if action == 'synchronize_state':
            from .models import ModuleStepCandidate
            runner.synchronize_state(ModuleStepCandidate.model_validate(message['candidate']))
            return {'ok': True, 'revision': runner.state_revision}
        if action == 'discard_candidate':
            runner.discard_candidate()
            return {'ok': True}
        if action in ('thermal', 'observe', 'jacobian'):
            from .models import ModulePhaseRequest
            return runner.phase_call(action, ModulePhaseRequest.model_validate(message['request'])).model_dump(mode='json')
        raise ValueError(f'未知 Worker 操作：{action}')

    for line in sys.stdin:
        try:
            message = json.loads(line)
            with open(os.devnull, 'w', encoding='utf-8') as output, redirect_stdout(output), redirect_stderr(output):
                result = dispatch(message)
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + '\n')
            sys.stdout.flush()
            if message.get('action') == 'finalize':
                break
        except Exception as error:
            failure = {'error': str(error), 'code': getattr(error, 'code', 'MODULE_RUNTIME_ERROR'),
                'diagnostics': [item.model_dump(mode='json') for item in getattr(error, 'diagnostics', [])]}
            if getattr(error, 'replay', None) is not None:
                failure['replay'] = error.replay
            sys.stdout.write(json.dumps(failure, ensure_ascii=False, allow_nan=False) + '\n')
            sys.stdout.flush()


if __name__ == "__main__":
    if '--startup-report' in sys.argv[1:]:
        sys.stderr.write('FN_STARTUP ' + json.dumps(_startup_snapshot(), ensure_ascii=False) + '\n')
        sys.stderr.flush()
    main()
