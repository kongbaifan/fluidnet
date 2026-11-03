"""Shared session commands and lifecycle, independent of concrete physics domains."""
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Mapping
from typing import Any, Protocol, TypedDict, cast
from copy import deepcopy
import math

from .compiler import CompilationError, runtime_parameter, validated_parameters
from .models import Diagnostic, ModuleDefinition, ModuleInstance, ParameterSpec, PIDController, Project, RunFrame
from .controllers import PID
from .control import ScriptControl


Parameters = dict[str, Any]
FrameBuffer = list[RunFrame] | deque[RunFrame]


class SessionNetwork(Protocol):
    """Only the project contract is shared; physical storage belongs to each domain."""
    project: Project
    modules: dict[str, ModuleDefinition]
    instances: dict[str, ModuleInstance]
    parameters: dict[str, Parameters]


class Closable(Protocol):
    def close(self, force: bool = False) -> None: ...


class ParameterExecutor(Closable, Protocol):
    def update_parameters(self, parameters: Parameters) -> None: ...


class ControlCheckpoint(TypedDict):
    parameters: dict[str, Parameters]
    revision: int
    controllers: dict[str, PID]
    diagnostics: list[Diagnostic]
    scripts: dict[str, dict[str, Any]]
    effects: object


def close_resources(resources: Mapping[str, Closable] | Closable) -> None:
    if hasattr(resources,'close'):
        cast(Closable, resources).close()
        return
    for resource in resources.values():
        try:
            resource.close()
        except Exception:
            pass


class SessionBase(ABC):
    report_keys: frozenset[str] = frozenset()
    def __init__(self, network: SessionNetwork, duration_s: float | None, dt_s: float, keep: int | None = None) -> None:
        if not (math.isfinite(dt_s) and dt_s>0) or duration_s is not None and not (math.isfinite(duration_s) and duration_s>0):
            raise ValueError('运行时长和步长必须为有限正数')
        if keep is None and (duration_s is None or duration_s>2000*dt_s):
            raise ValueError('一次返回全部帧的运行最多 2001 帧，且必须设定时长')
        self.network=network
        self.duration,self.dt=duration_s,dt_s
        self.time=0.
        self.index=self.sequence=self.revision=0
        self.frames: FrameBuffer = deque(maxlen=keep) if keep else []
        self.runners: dict[str, ParameterExecutor] = {}
        self.controllers: dict[str, PID] = {}
        self.scripts: dict[str, ScriptControl] = {}
        self.script_owners={key:script.id for script in network.project.control_scripts if script.enabled for key in script.outputs}
        for public,destinations in getattr(network,'composite_maps',{}).get('parameters',{}).items():
            if public in self.script_owners:
                for target,parameter in destinations:
                    self.script_owners[f'{target}.param.{parameter}']=self.script_owners[public]
        self.diagnostics: list[Diagnostic] = []
        self.closed=False
        self._control_base: ControlCheckpoint | None = None

    @abstractmethod
    def initialize(self) -> RunFrame: ...

    @abstractmethod
    def advance(self) -> RunFrame: ...

    @abstractmethod
    def snapshot(self) -> RunFrame: ...

    def preview_control(self, script_id: str) -> dict[str, Any]:
        """Preview one sample on an initialized disposable session, without accepting it."""
        runner = self.scripts.get(script_id)
        if runner is None:
            raise CompilationError('CONTROL_SCRIPT_UNKNOWN', f'控制脚本不存在：{script_id}')
        self._control()
        if runner.pending is None:
            raise CompilationError('CONTROL_PREVIEW_UNAVAILABLE', f'控制脚本没有待接受提案：{script_id}')
        return cast(dict[str, Any], deepcopy(runner.pending[0]))

    def validate_parameter_values(self, instance_id: str, parameters: Parameters) -> None:
        """Validate domain-specific effects before any parameter in a batch changes."""

    def validate_parameter_batch(self, candidates: dict[str, Parameters]) -> None:
        """Validate relationships across all proposed device parameters."""

    def apply_parameter_changes(self, instance_id: str, parameters: Parameters) -> None:
        """Apply already validated physical side effects; parameters are stored by the base."""

    def capture_parameter_effects(self) -> object:
        return None

    def restore_parameter_effects(self, effects: object) -> None:
        """Restore the physical side effects owned by this domain."""

    def close_domain_resources(self) -> None:
        close_resources(self.runners)

    def _apply_parameters(self, instance_id: str, parameters: Parameters) -> bool:
        if parameters==self.network.parameters[instance_id]:
            return False
        if instance_id in self.runners:
            self.runners[instance_id].update_parameters(parameters)
        self.network.parameters[instance_id]=parameters
        self.apply_parameter_changes(instance_id,parameters)
        return True

    @property
    def done(self) -> bool:
        return self.duration is not None and bool(self.frames) and self.time >= self.duration - 1e-12


    def parameter_spec(self, instance_id: str, parameter_id: str) -> ParameterSpec:
        instance = self.network.instances.get(instance_id)
        if instance is None:
            raise CompilationError('PARAMETER_TARGET_MISSING', '目标设备不存在')
        return cast(ParameterSpec, runtime_parameter(instance, self.network.modules[instance.module_id], parameter_id))


    def _candidate_parameters(self, instance_id: str, values: Parameters, controlled: bool = False, script_id: str | None = None) -> Parameters:
        """Validated parameters of an instance after `values`; nothing is changed yet."""
        for parameter_id in values:
            self._check_script_owner(f'{instance_id}.param.{parameter_id}', script_id)
            self.parameter_spec(instance_id, parameter_id)
            # Even in manual mode the PID writes its manual_output every substep, so an outside
            # write would be overwritten; the controller's own fields are the way in.
            owner = next((p.config.id for p in self.controllers.values()
                          if (p.config.instance_id, p.config.parameter_id) == (instance_id, parameter_id)), None)
            if owner and not controlled:
                raise CompilationError('PARAMETER_CONTROLLED', f'{instance_id}.{parameter_id} 由 PID {owner} 控制；'
                                       '请改该控制器的 setpoint，或切到手动后改 manual_output')
        instance = self.network.instances[instance_id]
        definition = self.network.modules[instance.module_id]
        candidate = instance.model_copy(update={'parameters': self.network.parameters[instance_id] | values})
        parameters = cast(Parameters, validated_parameters(candidate, definition))
        self.validate_parameter_values(instance_id,parameters)
        return parameters


    def set_parameter(self, instance_id: str, parameter_id: str, value: Any, controlled: bool = False) -> None:
        destinations = getattr(self.network,'composite_maps',{}).get('parameters',{}).get(f'{instance_id}.param.{parameter_id}')
        if destinations:
            self._check_script_owner(f'{instance_id}.param.{parameter_id}')
            patches: dict[str, Parameters] = {}
            for target, parameter in destinations:
                patches.setdefault(target,{})[parameter] = value
            candidates = {target:self._candidate_parameters(target,values,controlled) for target,values in patches.items()}
        else:
            candidates = {instance_id:self._candidate_parameters(instance_id,{parameter_id:value},controlled)}
        self.validate_parameter_batch(candidates)
        changed = False
        for target, parameters in candidates.items():
            changed = self._apply_parameters(target,parameters) or changed
        if changed:
            self.revision += 1

    def _candidate_controller(self, controller_id: str, values: Parameters) -> PIDController:
        pid = self.controllers.get(controller_id)
        if pid is None or not set(values) <= {'setpoint', 'mode', 'manual_output'}:
            raise CompilationError('PID_COMMAND_INVALID', f'控制器 {controller_id} 或可调字段 {sorted(values)} 不存在'
                                   '（可调：setpoint、mode、manual_output）')
        return PIDController.model_validate(pid.config.model_dump() | values)


    def _apply_controller(self, controller_id: str, config: PIDController) -> None:
        pid = self.controllers[controller_id]
        if config.mode != pid.config.mode:
            pid.reset = True
        pid.config = config
        pid.next_s = self.time


    def update_controller(self, controller_id: str, field: str, value: Any) -> None:
        self._check_script_owner(f'controller.{controller_id}.{field}')
        self._apply_controller(controller_id, self._candidate_controller(controller_id, {field: value}))
        self.revision += 1


    def _check_script_owner(self, key: str, script_id: str | None = None) -> None:
        owner = self.script_owners.get(key)
        if owner and owner != script_id:
            raise CompilationError('PARAMETER_CONTROLLED', f'{key} 由 Python 脚本 {owner} 控制')


    def write_variables(self, values: Parameters, script_id: str | None = None) -> None:
        """Write several variables at one frame boundary: all of them or none.

        Keys follow the frame: `<instance>.param.<parameter>` for runtime parameters and
        `controller.<id>.<setpoint|mode|manual_output>` for PID settings.
        """
        if not values:
            raise CompilationError('VARIABLE_WRITE_EMPTY', '没有要写入的变量')
        parameters: dict[str, Parameters] = {}
        controllers: dict[str, Parameters] = {}
        for key, value in values.items():
            self._check_script_owner(key, script_id)
            destinations = getattr(self.network,'composite_maps',{}).get('parameters',{}).get(key)
            if destinations:
                for target,parameter in destinations:
                    if parameter in parameters.get(target,{}):
                        raise CompilationError('MODULE_PARAMETER_CONFLICT','公开参数和内部参数写入同一目标')
                    parameters.setdefault(target,{})[parameter] = value
                continue
            parts = key.split('.')
            if len(parts) == 3 and parts[0] == 'controller' and parts[1] in self.controllers:
                controllers.setdefault(parts[1], {})[parts[2]] = value
            elif len(parts) == 3 and parts[1] == 'param':
                if parts[0] not in self.network.instances:
                    raise CompilationError('PARAMETER_TARGET_MISSING', f'{key}：设备 {parts[0]} 不存在')
                parameters.setdefault(parts[0], {})[parts[2]] = value
            else:
                raise CompilationError('VARIABLE_NOT_WRITABLE', f'{key} 不能写入；可写的是 <设备>.param.<运行参数> 和 '
                                       'controller.<控制器>.setpoint|mode|manual_output')
        configs = {cid: self._candidate_controller(cid, fields) for cid, fields in controllers.items()}
        candidates = {iid: self._candidate_parameters(iid, fields, script_id=script_id) for iid, fields in parameters.items()}
        self.validate_parameter_batch(candidates)
        changed = False
        for cid, config in configs.items():
            self._apply_controller(cid, config)
            changed = True
        for iid, params in candidates.items():
            changed = self._apply_parameters(iid, params) or changed
        if changed:
            self.revision += 1


    def _control(self) -> None:
        variables = self.snapshot().variables
        for runner in self.scripts.values():
            if runner.next_s <= self.time + 1e-10:
                response = runner.prepare(self.time, variables)
                try:
                    if response['writes']:
                        self.write_variables(response['writes'], script_id=runner.script.id)
                except ValueError as error:
                    raise CompilationError('CONTROL_WRITE_REJECTED', f'{runner.script.id} t={self.time:g}s：{error}') from error
        variables = self.snapshot().variables
        for pid in self.controllers.values():
            if pid.next_s <= self.time + 1e-10:
                pid.sample(self.time, variables)
            self.set_parameter(pid.config.instance_id, pid.config.parameter_id, pid.output, controlled=True)


    def _capture_control(self) -> ControlCheckpoint:
        fields = ('state', 'pending', 'next_s', 'last_s', 'samples', 'last_values')
        return {'parameters': deepcopy(self.network.parameters), 'revision': self.revision,
            'controllers': deepcopy(self.controllers), 'diagnostics': list(self.diagnostics),
            'scripts': {key: {field: deepcopy(getattr(script, field)) for field in fields}
                        for key, script in self.scripts.items()},
            'effects': self.capture_parameter_effects()}


    def _rollback_control(self) -> None:
        base = self._control_base
        if base is None:
            return
        changed = {key for key, value in base['parameters'].items() if value != self.network.parameters[key]}
        self.network.parameters = base['parameters']
        self.revision, self.controllers, self.diagnostics = base['revision'], base['controllers'], base['diagnostics']
        self.restore_parameter_effects(base['effects'])
        for key, fields in base['scripts'].items():
            for field, value in fields.items():
                setattr(self.scripts[key], field, value)
        self._control_base = None
        for key in changed & self.runners.keys():
            try:
                self.runners[key].update_parameters(self.network.parameters[key])
            except Exception:
                worker = getattr(self.runners[key], 'worker', self.runners[key])
                worker.close(force=True)


    def close(self) -> None:
        if not self.closed:
            self.closed = True
            # Both groups must be attempted: a failing runner close must not leak the
            # control-script Workers (they hold real subprocesses).
            try:
                self.close_domain_resources()
            finally:
                close_resources(self.scripts)
