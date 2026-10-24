"""Sampled project controls. Managed state is committed only with an accepted substep."""
from copy import deepcopy
import inspect
import json
import traceback

from .models import ControlScript, Diagnostic, FluidConfig, ModuleDefinition
from .runtime import WorkerProcess, ModuleRuntimeTimeout
from .module_state import checked_state


class ControlContext:
    def __init__(self, script, values, state, time_s, writable=True):
        self._script, self._values, self._writable = script, deepcopy(values), writable
        self.state, self.time_s = deepcopy(state), time_s
        self.writes, self.diagnostics = {}, []

    def read(self, key):
        if key not in self._script.inputs:
            raise ValueError(f'未声明的控制输入：{key}')
        if key not in self._values:
            raise ValueError(f'当前帧没有变量：{key}')
        return self._values[key]

    def write(self, key, value):
        if not self._writable:
            raise ValueError('只允许在 step 中写运行参数')
        if key not in self._script.outputs:
            raise ValueError(f'未声明的控制输出：{key}')
        self.writes[key] = value

    def log(self, message):
        if len(self.diagnostics) >= 20:
            raise ValueError('每次采样最多记录 20 条日志')
        self.diagnostics.append(Diagnostic(code='CONTROL_LOG', severity='info',
            message=f'{self._script.id} t={self.time_s:g}s：{str(message)[:1000]}').model_dump(mode='json'))


class ControlRunner:
    """Loaded only inside fn_engine.worker, including entrypoint validation."""
    def __init__(self, definition):
        self.script = ControlScript.model_validate(definition)
        self.filename = f'control-{self.script.id}.py'
        self.namespace = {'__name__': f'fluidnet_control_{self.script.id}'}
        exec(compile(self.script.source, self.filename, 'exec'), self.namespace)
        for name, count in (('initialize', 1), ('step', 2), ('finalize', 1)):
            callback = self.namespace.get(name)
            if not callable(callback) or inspect.iscoroutinefunction(callback):
                raise ValueError(f'控制脚本必须实现同步函数 {name}')
            inspect.signature(callback).bind(*([None] * count))

    def call(self, name, message):
        ctx = ControlContext(self.script, message.get('values', {}), message.get('state', {}),
                             message.get('time_s', 0.), writable=name == 'step')
        try:
            args = (ctx, message['dt_s']) if name == 'step' else (ctx,)
            self.namespace[name](*args)
            result = {'state': checked_state(ctx.state), 'writes': ctx.writes, 'diagnostics': ctx.diagnostics}
            json.dumps(result, allow_nan=False)
            return result
        except Exception as error:
            frames = [f for f in traceback.extract_tb(error.__traceback__) if f.filename == self.filename]
            line = f'第 {frames[-1].lineno} 行：' if frames else ''
            raise ValueError(f'{self.script.id} {name} {line}{error}') from error


class ScriptControl(WorkerProcess):
    def __init__(self, script):
        super().__init__(ModuleDefinition(id=script.id, name=script.id), {}, FluidConfig(), timeout_s=script.timeout_s)
        self.script = script
        self.next_s, self.last_s, self.samples = 0., None, 0
        self.pending = None
        self.last_values = {}

    def rpc(self, action, **payload):
        from .compiler import CompilationError
        try:
            return self._request({'action': action, **payload})
        except Exception as error:
            code = 'CONTROL_TIMEOUT' if isinstance(error, ModuleRuntimeTimeout) else 'CONTROL_SCRIPT_ERROR'
            raise CompilationError(code, f'脚本 {self.script.id}：{error}', field=f'control_scripts.{self.script.id}') from error

    def start(self, variables):
        self.last_values = dict(variables)
        response = self.rpc('control_initialize', definition=self.script.model_dump(mode='json'), values=variables)
        self.state = checked_state(response['state'])
        return response.get('diagnostics', [])

    def prepare(self, time_s, variables):
        self.last_values = dict(variables)
        response = self.rpc('control_step', values=variables, state=self.state, time_s=time_s,
                            dt_s=0. if self.last_s is None else time_s - self.last_s)
        checked_state(response['state'])
        self.pending = response, time_s
        # An advance can contain several substeps; retries reuse this proposal.
        self.next_s = (self.samples + 1) * self.script.sample_s
        return response

    def accept(self):
        if self.pending is None:
            return
        response, self.last_s = self.pending
        self.state = checked_state(response['state'])
        self.samples += 1
        self.pending = None

    def variables(self):
        prefix = f'script.{self.script.id}'
        return {f'{prefix}.samples': self.samples, f'{prefix}.last_time_s': self.last_s,
                f'{prefix}.content_hash': self.script.content_hash,
                **{f'{prefix}.state.{k}': v for k, v in self.state.items() if v is None or isinstance(v, (str, int, float, bool))}}

    def close(self, force=False):
        if self.process is not None and not force and not self._finalized:
            self._finalized = True
            try:
                self.rpc('control_finalize', state=self.state, values=self.last_values, time_s=self.last_s or 0.)
            except Exception:
                pass
        super().close(force=force)


def validate_scripts(project, modules, instances):
    from .compiler import CompilationError, runtime_parameter
    owners = {}
    pids = {p.id: p for p in project.controllers}
    targets = {f'{p.instance_id}.param.{p.parameter_id}' for p in pids.values()}
    for script in project.control_scripts:
        if not script.enabled:
            continue
        try:
            compile(script.source, f'control-{script.id}.py', 'exec')
        except SyntaxError as error:
            raise CompilationError('CONTROL_SYNTAX', f'{script.id} 第 {error.lineno} 行：{error.msg}') from error
        for key in script.outputs:
            destinations = getattr(project,'_composite_maps',{}).get('parameters',{}).get(key)
            if destinations:
                for instance_id,parameter_id in destinations:
                    concrete = f'{instance_id}.param.{parameter_id}'
                    if concrete in owners or concrete in targets:
                        raise CompilationError('CONTROL_TARGET_CONFLICT',f'{key} 与内部控制目标 {concrete} 冲突')
                    instance = instances[instance_id]
                    runtime_parameter(instance,modules[instance.module_id],parameter_id)
                    owners[concrete] = script.id
                owners[key] = script.id
                continue
            if key in owners or key in targets:
                raise CompilationError('CONTROL_TARGET_CONFLICT', f'{key} 已由 {owners.get(key, "PID")} 控制')
            parts = key.split('.')
            if len(parts) == 3 and parts[1] == 'param' and parts[0] in instances:
                instance = instances[parts[0]]
                runtime_parameter(instance, modules[instance.module_id], parts[2])
            elif not (len(parts) == 3 and parts[0] == 'controller' and parts[1] in pids
                      and parts[2] in {'setpoint', 'mode', 'manual_output'}):
                raise CompilationError('CONTROL_OUTPUT_INVALID', f'{script.id} 的输出 {key} 不可写')
            owners[key] = script.id
