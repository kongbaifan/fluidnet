from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import queue
import subprocess
import sys
import threading
from collections import deque, OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Any
from collections.abc import Mapping
from fn_sdk import DiagnosticSeverity, RelationKind

from .module_contracts import check_module_compatibility, definition_hash
from .module_execution import InvocationState
from .module_performance import ParentEvaluateCache
from .module_diagnostics import exception_diagnostic, merge_diagnostics, MAX_MESSAGE_CHARS
from .models import (
    CommitStepRequest,
    CommitStepResponse,
    ChannelState,
    Diagnostic,
    EvaluateRequest,
    EvaluateResponse,
    FluidConfig,
    InitializeRequest,
    ModuleDefinition,
    ModuleExecutionInfo,
    ModuleRequestContext,
    ModuleStepCandidate,
    ModulePhaseRequest, ModuleThermalResponse,
    ModuleDerivativeResponse,
    NetworkRelation,
    PortState,
)
from .module_state import checked_state,checked_result


class RuntimeErrorBase(ValueError):
    code = "MODULE_RUNTIME_ERROR"

    def __init__(self, message, *, diagnostics=None, replay=None, code=None):
        super().__init__(message)
        self.diagnostics = diagnostics or []
        self.replay = replay
        if code is not None:
            self.code = code


class ModuleRuntimeTimeout(RuntimeErrorBase):
    code = "MODULE_RUNTIME_TIMEOUT"


ChannelResult = ChannelState


class _LazyPropertyService:
    def __init__(self, config: FluidConfig):
        self.config = config
        self._service = None

    def _get(self):
        if self._service is None:
            from .properties import property_service
            self._service = property_service(self.config)
        return self._service

    def __getattr__(self, name):
        return getattr(self._get(), name)


class NetworkBuilder:
    def __init__(self):
        self.relations: list[NetworkRelation] = []

    def _add(self, kind: RelationKind, channel: str, parameters: dict[str, Any]):
        self.relations.append(NetworkRelation(relation_id=channel, kind=kind, channel=channel, parameters=parameters))

    # heat_w is heat added to the fluid in this channel (W, negative = removed);
    # the thermal layer applies it as outlet enthalpy += heat_w / |mass flow|.
    def pipe(self, *, channel: str, length_m: float, diameter_m: float, roughness_m: float = 0.0,
             density_kg_m3: float | None = None, viscosity_pa_s: float | None = None, height_m: float = 0.0,
             heat_w: float = 0.0):
        self._add("pipe", channel, {"length_m": length_m, "diameter_m": diameter_m, "roughness_m": roughness_m,
                                     "density_kg_m3": density_kg_m3 or 0.0, "viscosity_pa_s": viscosity_pa_s or 0.0,
                                     "height_m": height_m, "heat_w": heat_w})

    def valve(self, *, channel: str, kv: float, opening: float, density_kg_m3: float | None = None,
              height_m: float = 0.0, heat_w: float = 0.0):
        self._add("valve", channel, {"kv_m3_h": kv, "opening_ratio": opening,
                                      "density_kg_m3": density_kg_m3 or 0.0, "height_m": height_m, "heat_w": heat_w})

    def pump(self, *, channel: str, head_curve: list[list[float]], speed_ratio: float = 1.0,
             density_kg_m3: float | None = None, heat_w: float = 0.0):
        self._add("pump", channel, {"head_curve": head_curve, "speed_ratio": speed_ratio,
                                     "density_kg_m3": density_kg_m3 or 0.0, "heat_w": heat_w})

    def compressor(self, *, channel: str, forced_mass_flow_kg_s: float):
        self._add("compressor", channel, {"forced_mass_flow_kg_s": forced_mass_flow_kg_s})

    def resistance(self, *, channel: str, diameter_m: float, loss_coefficient: float,
                   density_kg_m3: float | None = None, heat_w: float = 0.0):
        self._add("resistance", channel, {"diameter_m": diameter_m, "loss_coefficient": loss_coefficient,
            "density_kg_m3": 0.0 if density_kg_m3 is None else density_kg_m3, "heat_w": heat_w})


class ModuleContext:
    def __init__(self, parameters: dict[str, Any], fluid: FluidConfig,
                 ports: dict[str, PortState] | None = None, state: dict[str, Any] | None = None,
                 channels: dict[str, ChannelResult] | None = None, port_fluids: dict[str, FluidConfig] | None = None,
                 *, execution: ModuleExecutionInfo | None = None):
        self._execution = execution if execution is not None else ModuleExecutionInfo()
        self._identity_read = False
        self.parameters = parameters
        self.fluid = _LazyPropertyService(fluid)
        self._port_fluids = {port: _LazyPropertyService(config) for port, config in (port_fluids or {}).items()}
        self.ports:Mapping[str,PortState] = ports or {}
        self.state = state if state is not None else {}
        self.channels = channels or {}
        self.net = NetworkBuilder()
        self.variables: dict[str, Any] = {}
        self.diagnostics: list[Diagnostic] = []
        self.heat_w: dict[str, float] = {}
        self.derivatives:dict[str,dict[str,Any]] = {}

    @property
    def execution(self):
        self._identity_read = True
        return self._execution

    @property
    def phase(self):
        return self._execution.phase

    @property
    def time_s(self):
        return self._execution.time_s

    def fluid_at(self, port_id: str):
        """Property service of the circuit a port belongs to (differs from ctx.fluid across an exchanger)."""
        return self._port_fluids.get(port_id, self.fluid)

    def parameter(self, name: str, default: Any = None):
        return self.parameters.get(name, default)

    def port(self, name: str) -> PortState:
        return self.ports.get(name, PortState())

    def channel(self, name: str) -> ChannelResult:
        return self.channels.get(name, ChannelResult())

    def var(self, name: str, value: Any):
        self.variables[name] = value

    def diagnostic(self, code: str, message: str, severity: DiagnosticSeverity = "warning"):
        self.diagnostics = merge_diagnostics(self.diagnostics, [Diagnostic(code=code,
            message=message[:MAX_MESSAGE_CHARS], severity=severity, instance_id=self.execution.instance_id,
            phase=self.phase, time_s=self.time_s)])

    def log(self, message: str, level: DiagnosticSeverity = 'info'):
        self.diagnostic('MODULE_LOG', str(message), level)

    def heat(self, channel: str, heat_w: float):
        if channel in self.heat_w:
            raise ValueError(f'通路热流重复返回：{channel}')
        self.heat_w[channel] = heat_w

    def derivative(self, channel: str, flow_slope_pa_per_kg_s: float,
                   port_pressure_derivatives, smooth: bool = True):
        if channel in self.derivatives:
            raise ValueError('通路导数重复返回')
        self.derivatives[channel] = {'flow_slope_pa_per_kg_s':flow_slope_pa_per_kg_s,
            'port_pressure_derivatives':dict(port_pressure_derivatives), 'smooth':smooth}


def module_source(definition: ModuleDefinition) -> str:
    source = definition.source.get("runtime", "") if definition.source else ""
    if isinstance(source, list):
        source = "\n".join(source)
    if not source:
        raise RuntimeErrorBase(f"模块 {definition.id} 没有 runtime 源码")
    return source


def design_source(definition: ModuleDefinition) -> str:
    """design.py of a Python module; empty when the module has no design function."""
    source = definition.source.get("design", "") if definition.source else ""
    if not isinstance(source, str):
        raise RuntimeErrorBase(f"design.py 必须是单个 Python 文本（模块 {definition.id}）")
    return source


def module_content_hash(definition: ModuleDefinition) -> str:
    return hashlib.sha256(module_source(definition).encode("utf-8")).hexdigest()


def module_definition_hash(definition: ModuleDefinition) -> str:
    return definition_hash(definition)


def _load_module(definition: ModuleDefinition):
    check_module_compatibility(definition)
    source = module_source(definition)
    name = f"fluidnet_user_{definition.id}_{definition.version}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    if spec is None:
        raise RuntimeErrorBase(f'无法为模块 {definition.id} 创建加载描述')
    module = importlib.util.module_from_spec(spec)
    try:
        exec(compile(source, f"<{definition.id}>", "exec"), module.__dict__)
    except Exception as error:
        raise RuntimeErrorBase(str(error),diagnostics=[exception_diagnostic(error,definition)]) from error
    entrypoint = definition.entrypoint.rsplit(":", 1)[-1] if definition.entrypoint else "Module"
    target = getattr(module, entrypoint, None)
    if target is None:
        if all(callable(getattr(module, name, None)) for name in ("initialize", "evaluate", "commit_step", "finalize")):
            target = module
        else:
            raise RuntimeErrorBase(f"模块 {definition.id} 找不到入口 {entrypoint}")
    return target() if isinstance(target, type) else target


class InProcessModuleRunner:
    """Reference runner used inside the isolated Worker process and by focused tests."""

    def __init__(self, definition: ModuleDefinition, parameters: dict[str, Any], fluid: FluidConfig,
                 initial_state: dict[str, Any] | None = None, port_fluids: dict[str, FluidConfig] | None = None,
                 *, run_id=None, instance_id=None, cache_enabled=False):
        self.definition = definition
        self.parameters = parameters
        self.fluid = fluid
        self.port_fluids = dict(port_fluids or {})
        self.state = checked_state(initial_state or {})
        self.module = _load_module(definition)
        self.initialized = False
        self.execution = InvocationState(run_id, instance_id or definition.id)
        self._last_committed_time_s: float | None = None
        self.state_revision = 0
        self._pending_candidate = None
        self._accepted_candidate = None
        self._pending_digest = None
        self._accepted_digest = None
        self.cache_enabled = cache_enabled
        self._evaluate_cache:OrderedDict[str,EvaluateResponse] = OrderedDict()
        self._source_hashes = (module_content_hash(definition), module_definition_hash(definition))

    def _info(self, phase, time_s, context: ModuleRequestContext | None = None, *, run_id=None, instance_id=None,
              iteration_id=None, dt_s=None, port_data='unavailable', channel_data='unavailable', state_data='unavailable'):
        context = context if context is not None else self.execution.context()
        self.execution.step_id = context.step_id
        self.execution.accepted_time_s = context.accepted_time_s
        return ModuleExecutionInfo(phase=phase, time_s=time_s, run_id=run_id or self.execution.run_id,
            instance_id=instance_id or self.execution.instance_id, request_id=context.request_id,
            step_id=context.step_id if phase in {'evaluate', 'thermal', 'observe', 'jacobian', 'commit_step'} else None,
            accepted_time_s=context.accepted_time_s,
            iteration_id=iteration_id, dt_s=dt_s, port_data=port_data,
            channel_data=channel_data, state_data=state_data)

    def _invoke(self, callback, ctx, *args):
        from .module_scope import check_scope_configuration, scope_diagnostics
        check_scope_configuration(self.definition, self.fluid)
        for fluid in self.port_fluids.values():
            check_scope_configuration(self.definition, fluid)
        ports = getattr(ctx.ports, '_values', ctx.ports)
        ctx.diagnostics = merge_diagnostics(ctx.diagnostics, scope_diagnostics(self.definition, ports,
            ctx.channels, ctx.phase, ctx.execution.instance_id, ctx.time_s))
        if any(d.severity == 'error' for d in ctx.diagnostics):
            raise RuntimeErrorBase('; '.join(d.message for d in ctx.diagnostics), diagnostics=ctx.diagnostics)
        if not callback:
            return
        ctx._identity_read = False
        try:
            if inspect.iscoroutinefunction(callback):
                raise ValueError('模块生命周期回调必须是同步函数')
            callback(ctx, *args)
        except Exception as error:
            if isinstance(error, RuntimeErrorBase) and error.diagnostics:
                raise
            diagnostic = exception_diagnostic(error, self.definition, ctx.execution)
            replay = {'module': self.definition.model_dump(mode='json'), 'parameters': deepcopy(ctx.parameters),
                'state': deepcopy(self.state), 'fluid': self.fluid.model_dump(mode='json'),
                'port_fluids': {key: config.model_dump(mode='json') for key, config in self.port_fluids.items()},
                'ports': {key: value.model_dump(mode='json') for key, value in ctx.ports.items()},
                'channels': {key: value.model_dump(mode='json') for key, value in ctx.channels.items()},
                'execution': ctx.execution.model_dump(mode='json'),
                'content_hash': module_content_hash(self.definition), 'definition_hash': module_definition_hash(self.definition)}
            raise RuntimeErrorBase(str(error), diagnostics=[diagnostic], replay=replay, code=diagnostic.code) from error

    def initialize(self, context=None):
        info = self._info('initialize', 0., context, state_data='initial')
        ctx = ModuleContext(self.parameters, self.fluid, state=self.state, port_fluids=self.port_fluids, execution=info)
        callback = getattr(self.module, "initialize", None)
        self._invoke(callback, ctx)
        self.state = checked_state(ctx.state)
        self.initialized = True
        self._last_committed_time_s = 0.
        return self.state

    def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        if not self.initialized:
            self.initialize()
        if request.state_revision is not None:
            if request.state_revision != self.state_revision:
                raise RuntimeErrorBase('计算请求的状态修订不匹配',code='MODULE_REVISION_CONFLICT')
            request=request.model_copy(update={'readonly_state':deepcopy(self.state)})
        context = request.context if request.context is not None else self.execution.context()
        info = self._info('evaluate', request.time_s, context, run_id=request.run_id, instance_id=request.instance_id,
            iteration_id=request.iteration_id, port_data=context.port_data if request.trial_ports else 'unavailable',
            state_data='input_copy')
        ctx = ModuleContext(deepcopy(self.parameters), self.fluid, request.trial_ports, deepcopy(request.readonly_state),
                            port_fluids=self.port_fluids, execution=info)
        cache_key = None
        if self.cache_enabled and self.definition.pure_evaluate:
            payload = {'inputs':request.model_dump(mode='json', exclude={'context', 'iteration_id'}),
                'parameters':self.parameters, 'state_revision':self.state_revision, 'hashes':self._source_hashes,
                'fluid':self.fluid.model_dump(mode='json'),
                'port_fluids':{key:value.model_dump(mode='json') for key,value in self.port_fluids.items()}}
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')
            cache_key = hashlib.sha256(encoded).hexdigest()
            if cache_key in self._evaluate_cache:
                cached = self._evaluate_cache.pop(cache_key)
                self._evaluate_cache[cache_key] = cached
                return cached.model_copy(deep=True, update={'cache_hit':True})
        accessed:set[str] = set()
        if self.definition.dependency_mode == 'tracked':
            from .module_performance import TrackedPorts
            ctx.ports = TrackedPorts(ctx.ports, accessed)
        self._invoke(getattr(self.module, "evaluate"), ctx)
        if self.definition.dependency_mode == 'tracked':
            declared = self.definition.hydraulic_dependencies or {}
            for relation in ctx.net.relations:
                allowed = set(declared.get(relation.channel, [port.id for port in self.definition.ports]))
                if accessed - allowed:
                    raise RuntimeErrorBase(f'通路 {relation.channel} 读取了越声明端口 {sorted(accessed-allowed)}',
                                           code='MODULE_DEPENDENCY_VIOLATION')
        response = EvaluateResponse(relations=ctx.net.relations, variables=ctx.variables, diagnostics=ctx.diagnostics,
                                    accessed_ports=sorted(accessed))
        checked_result(response)
        if cache_key is not None:
            if ctx.state != request.readonly_state:
                raise RuntimeErrorBase('纯函数 evaluate 修改了受管理状态', code='MODULE_PURITY_VIOLATION')
            if not ctx._identity_read and len(response.model_dump_json().encode('utf-8')) <= 16384:
                self._evaluate_cache[cache_key] = response.model_copy(deep=True)
                while len(self._evaluate_cache) > 64:
                    self._evaluate_cache.popitem(last=False)
        return response

    def _commit_candidate(self, request: CommitStepRequest, channels: dict[str, ChannelResult] | None = None) -> CommitStepResponse:
        if not self.initialized:
            self.initialize()
        actual_channels = channels or request.converged_channels
        info = self._info('commit_step', request.time_s, request.context, run_id=request.run_id,
            instance_id=request.instance_id, dt_s=request.dt_s,
            port_data='converged' if request.converged_ports else 'unavailable',
            channel_data='converged' if actual_channels else 'unavailable', state_data='candidate')
        ctx = ModuleContext(deepcopy(self.parameters), self.fluid, request.converged_ports, deepcopy(self.state),
                            channels=actual_channels, port_fluids=self.port_fluids, execution=info)
        callback = getattr(self.module, "commit_step", None)
        self._invoke(callback, ctx, request.dt_s)
        response = CommitStepResponse(state=checked_state(ctx.state), variables=ctx.variables, diagnostics=ctx.diagnostics)
        checked_result(response)
        if any(item.severity == 'error' for item in response.diagnostics):
            raise RuntimeErrorBase('; '.join(item.message for item in response.diagnostics if item.severity == 'error'),
                                   diagnostics=response.diagnostics)
        return response

    def prepare_step(self, request, channels=None, *, base_revision=None, authoritative_state=None):
        if not self.initialized:
            self.initialize()
        base_revision = self.state_revision if base_revision is None else base_revision
        if base_revision != self.state_revision:
            raise RuntimeErrorBase('模块状态修订不匹配', code='MODULE_REVISION_CONFLICT')
        if authoritative_state is not None and checked_state(authoritative_state) != self.state:
            raise RuntimeErrorBase('模块权威状态不匹配', code='MODULE_REVISION_CONFLICT')
        if channels is not None:
            request = request.model_copy(update={'converged_channels': channels})
        context = request.context if request.context is not None else self.execution.context()
        step_id = context.step_id or context.request_id
        payload = request.model_dump(mode='json')
        # Request IDs may differ on transport retry; the step and all physical inputs must match.
        payload.pop('context', None)
        payload['parameters']=self.parameters
        payload['source_hashes']=self._source_hashes
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        previous = self._accepted_candidate
        if previous is not None and previous.step_id == step_id:
            if self._accepted_digest != digest:
                raise RuntimeErrorBase('同一子步身份对应不同输入', code='MODULE_REQUEST_CONFLICT')
            return previous
        pending = self._pending_candidate
        if pending is not None and pending.step_id == step_id and pending.base_revision == base_revision:
            if self._pending_digest != digest:
                raise RuntimeErrorBase('同一子步身份对应不同输入', code='MODULE_REQUEST_CONFLICT')
            return pending
        if previous is not None and context.step_id is not None and request.time_s <= previous.time_s:
            raise RuntimeErrorBase('已接受时刻不能作为新子步重复提交',code='MODULE_STEP_STALE')
        result = self._commit_candidate(request, channels)
        candidate = ModuleStepCandidate(candidate_id=f'candidate-{base_revision}-{digest[:24]}',
            step_id=step_id, base_revision=base_revision, time_s=request.time_s, result=result,
            content_hash=self._source_hashes[0],definition_hash=self._source_hashes[1])
        self._pending_candidate, self._pending_digest = candidate, digest
        return candidate

    def synchronize_state(self, candidate):
        if self._accepted_candidate is not None and candidate == self._accepted_candidate:
            return
        if candidate.base_revision != self.state_revision or candidate != self._pending_candidate:
            raise RuntimeErrorBase('模块候选状态已过期或未准备', code='MODULE_REVISION_CONFLICT')
        self.state = checked_state(candidate.result.state)
        self.state_revision += 1
        self._accepted_candidate, self._pending_candidate = candidate, None
        self._accepted_digest = self._pending_digest
        self._last_committed_time_s = candidate.time_s

    def discard_candidate(self):
        self._pending_candidate = None

    def phase_call(self, phase, request: ModulePhaseRequest):
        if not self.initialized:
            self.initialize()
        capabilities = set(self.definition.sdk.capabilities) if self.definition.sdk else set()
        capability = 'hydraulic.derivatives.v1' if phase == 'jacobian' else f'{phase}.v1'
        if capability not in capabilities:
            raise RuntimeErrorBase(f'模块未声明 {phase} 能力', code='MODULE_CAPABILITY_UNSUPPORTED')
        callback = getattr(self.module, phase, None)
        if not callable(callback):
            raise RuntimeErrorBase(f'模块未实现 {phase} 回调', code='MODULE_CALLBACK_MISSING')
        context = request.context if request.context is not None else self.execution.context()
        info = self._info(phase, request.time_s, context, run_id=request.run_id, instance_id=request.instance_id,
            port_data='trial' if phase in {'thermal','jacobian'} else 'converged',
            channel_data='hydraulic_trial' if phase in {'thermal','jacobian'} else 'converged', state_data='input_copy')
        ctx = ModuleContext(deepcopy(self.parameters), self.fluid, request.ports, deepcopy(self.state),
            request.channels, self.port_fluids, execution=info)
        self._invoke(callback, ctx)
        if ctx.state != self.state:
            raise RuntimeErrorBase(f'{phase} 回调修改了只读状态', code='MODULE_READONLY_STATE')
        if ctx.net.relations or phase != 'thermal' and ctx.heat_w:
            raise RuntimeErrorBase(f'{phase} 回调不能修改水力关系或供热', code='MODULE_PHASE_OUTPUT_INVALID')
        if any(item.severity == 'error' for item in ctx.diagnostics):
            raise RuntimeErrorBase('; '.join(item.message for item in ctx.diagnostics), diagnostics=ctx.diagnostics)
        if phase == 'thermal':
            result:ModuleThermalResponse|ModuleDerivativeResponse|EvaluateResponse
            expected = {channel.id for channel in self.definition.channels if channel.enabled}
            if set(ctx.heat_w) != expected:
                raise RuntimeErrorBase('热回调必须返回每条启用通路热流', code='MODULE_HEAT_MISSING')
            result = ModuleThermalResponse(heat_w=ctx.heat_w, diagnostics=ctx.diagnostics)
        elif phase == 'jacobian':
            expected = {channel.id for channel in self.definition.channels if channel.enabled}
            if set(ctx.derivatives) - expected:
                raise RuntimeErrorBase('导数包含未知通路', code='MODULE_DERIVATIVE_INVALID')
            result = ModuleDerivativeResponse.model_validate({'derivatives':ctx.derivatives,'diagnostics':ctx.diagnostics})
            ports = {port.id for port in self.definition.ports}
            if any(set(item.port_pressure_derivatives) - ports for item in result.derivatives.values()):
                raise RuntimeErrorBase('导数包含未知压力端口', code='MODULE_DERIVATIVE_INVALID')
        else:
            result = EvaluateResponse(variables=ctx.variables, diagnostics=ctx.diagnostics)
        checked_result(result)
        return result

    def commit_step(self, request, channels=None):
        # Legacy direct callers still accept one instance; the engine uses prepare/promote/sync.
        candidate = self.prepare_step(request, channels)
        self.synchronize_state(candidate)
        return candidate.result

    def finalize(self, context=None):
        callback = getattr(self.module, "finalize", None)
        if callback:
            info = self._info('finalize', self._last_committed_time_s, context,
                              state_data='module_committed' if self.initialized else 'initial')
            self._invoke(callback, ModuleContext(self.parameters, self.fluid, state=self.state, port_fluids=self.port_fluids,
                                                execution=info))


class WorkerProcess:
    """Line-delimited JSON RPC runner for user modules in a separate process."""

    # The child's stderr is drained into a bounded tail: a chatty module must neither
    # fill the pipe (which would block its own write and look like a timeout) nor grow
    # memory. The tail is appended to worker faults so the cause is visible in the run.
    STDERR_TAIL_LINES = 40
    STDERR_LINE_CHARS = 500
    STDERR_MESSAGE_CHARS = 2000

    def __init__(self, definition: ModuleDefinition, parameters: dict[str, Any], fluid: FluidConfig,
                 initial_state: dict[str, Any] | None = None, timeout_s: float = 10.0,
                 port_fluids: dict[str, FluidConfig] | None = None, *, run_id=None, instance_id=None, cache_enabled=False):
        check_module_compatibility(definition)
        self.definition = definition
        self.parameters = parameters
        self.fluid = fluid
        self.port_fluids = dict(port_fluids or {})
        self.state = dict(initial_state or {})
        self.state_revision = 0
        self._accepted_candidate = None
        self.cache_enabled = cache_enabled
        self.execution = InvocationState(run_id, instance_id or definition.id)
        self._parent_cache = ParentEvaluateCache()
        self._invocations: dict[str, InvocationState] = {}
        self._definitions:dict[str,ModuleDefinition] = {}
        self.timeout_s = timeout_s
        self.process: subprocess.Popen | None = None
        self._responses: queue.Queue[str | BaseException] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_lines: deque[str] = deque(maxlen=self.STDERR_TAIL_LINES)
        self._stderr_thread: threading.Thread | None = None
        self._closed = False
        self._finalized = False
        # B0 观测器：这一 Worker 实际收发的 RPC 数（含 initialize/parameters/commit_step）。
        self.request_count = 0

    def _ensure_process(self):
        if self._closed:
            raise RuntimeErrorBase('模块 Worker 已关闭，不能继续执行', code='MODULE_WORKER_CLOSED')
        if self.process is not None:
            if self.process.poll() is not None:
                returncode = self.process.returncode
                tail = self._stderr_tail()
                self.close(force=True)
                raise RuntimeErrorBase(f"模块 Worker 已退出，退出码 {returncode}{tail}")
            return
        check_module_compatibility(self.definition)
        env = os.environ.copy()
        package_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        self._stderr_lines.clear()
        self.process = subprocess.Popen(
            [sys.executable, "-m", "fn_engine.worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", cwd=str(Path(__file__).resolve().parents[2]), env=env,
        )
        self._responses = queue.Queue()
        stream, stderr, responses = self.process.stdout, self.process.stderr, self._responses

        def read_responses():
            assert stream
            try:
                for line in stream:
                    responses.put(line)
            except BaseException as error:  # pragma: no cover - defensive thread boundary
                responses.put(error)
            finally:
                responses.put("")

        self._reader_thread = threading.Thread(target=read_responses, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._read_stderr, args=(stderr,), daemon=True)
        self._stderr_thread.start()

    def _read_stderr(self, stream):
        """Drain fd 2 into the bounded tail; closing the stream is a normal shutdown."""
        if stream is None:  # pragma: no cover - Popen(stderr=PIPE) always provides it
            return
        try:
            for line in stream:
                text = line.rstrip('\r\n')
                if text:
                    self._stderr_lines.append(text[:self.STDERR_LINE_CHARS])
        except (ValueError, OSError):  # stream closed while close() is joining us
            return
        except BaseException:  # pragma: no cover - defensive thread boundary
            return

    def _stderr_tail(self, wait: float = 0.2) -> str:
        """Tail of the child's stderr for an error message, waiting briefly for the drain."""
        thread = self._stderr_thread
        if wait and thread is not None and thread.is_alive():
            thread.join(timeout=wait)
        lines = list(self._stderr_lines)
        if not lines:
            return ''
        text = '\n'.join(lines)
        if len(text) > self.STDERR_MESSAGE_CHARS:
            text = text[-self.STDERR_MESSAGE_CHARS:]
        return f'；stderr 尾部：{text}'

    def _readline(self) -> str:
        assert self.process and self._responses
        try:
            line = self._responses.get(timeout=self.timeout_s)
        except queue.Empty as error:
            raise ModuleRuntimeTimeout(f"模块 Worker 响应超时（>{self.timeout_s:g}s）{self._stderr_tail()}") from error
        if isinstance(line, BaseException):
            raise RuntimeErrorBase(f"读取模块 Worker 失败：{line}{self._stderr_tail()}")
        if not line:
            returncode = self.process.poll() if self.process else None
            exit_text = f"（退出码 {returncode}）" if returncode is not None else ''
            raise RuntimeErrorBase(f"模块 Worker 已退出或关闭了输出通道{exit_text}{self._stderr_tail()}")
        return line

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._request_impl(payload)
        except RuntimeErrorBase as error:
            self._annotate_request_error(error, payload)
            raise

    def _annotate_request_error(self, error: RuntimeErrorBase, payload: dict[str, Any]) -> None:
        if not error.diagnostics:
            request = payload.get('request', {})
            action = payload.get('action')
            instance = request.get('instance_id', payload.get('instance_id', self.execution.instance_id))
            info = ModuleExecutionInfo(phase='commit_step' if action == 'prepare_step' else
                action if action in {'initialize', 'evaluate', 'commit_step', 'finalize'} else 'manual',
                instance_id=instance, time_s=request.get('time_s'))
            definition = self._definitions.get(payload.get('instance_id','default'),self.definition)
            error.diagnostics = [exception_diagnostic(error, definition, info)]
        else:
            request=payload.get('request',{})
            error.diagnostics=[diagnostic.model_copy(update={'instance_id':request.get('instance_id',payload.get('instance_id',self.execution.instance_id)),
                'phase':payload.get('action') if diagnostic.phase=='load' else diagnostic.phase}) if diagnostic.instance_id is None else diagnostic
                for diagnostic in error.diagnostics]

    def _check_cache_process(self, request: EvaluateRequest, instance_id: str = 'default') -> None:
        try:
            self._ensure_process()
        except RuntimeErrorBase as error:
            self._annotate_request_error(error, {'action': 'evaluate', 'instance_id': instance_id,
                                                'request': request.model_dump(mode='json')})
            raise

    def _request_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.request_count += 1
        self._ensure_process()
        assert self.process and self.process.stdin
        try:
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            self.close(force=True)
            raise RuntimeErrorBase(f"模块 Worker 通信失败：{error}{self._stderr_tail()}") from error
        try:
            line = self._readline()
        except RuntimeErrorBase:
            # Timeout/EOF/read fault: the worker is not usable, so terminate it here
            # instead of leaving the subprocess (and its pipe handles) behind.
            self.close(force=True)
            raise
        try:
            response = json.loads(line)
        except json.JSONDecodeError as error:
            self.close(force=True)
            raise RuntimeErrorBase(f"模块 Worker 通信失败：{error}{self._stderr_tail()}") from error
        if response.get("error"):
            raise RuntimeErrorBase(response["error"], code=response.get('code'), replay=response.get('replay'),
                                   diagnostics=[Diagnostic.model_validate(item) for item in response.get('diagnostics', [])])
        return response

    def initialize(self):
        self._parent_cache.clear()
        self._invocations['default'] = self.execution
        self._definitions['default'] = self.definition
        request = InitializeRequest(run_id=self.execution.run_id, instance_id=self.execution.instance_id,
                                    package={"module_id": self.definition.id, "version": f"{self.definition.version}.0.0",
                                             "content_hash": self.definition.content_hash or module_content_hash(self.definition),
                                             "definition_hash": self.definition.definition_hash},
                                    parameters=self.parameters, fluid=self.fluid, port_fluids=self.port_fluids,
                                    initial_state=self.state, context=self.execution.context(), cache_enabled=self.cache_enabled)
        response = self._request({"action": "initialize", "definition": self.definition.model_dump(mode="json"),
                                  "request": request.model_dump(mode="json")})
        self.state = dict(response.get("state", {}))
        return self.state

    def update_parameters(self, parameters):
        self._request({'action': 'parameters', 'parameters': parameters})
        self.parameters = dict(parameters)
        self._parent_cache.clear()

    def validate_entrypoint(self):
        return self._request({"action": "validate", "definition": self.definition.model_dump(mode="json")})

    def evaluate(self, request: EvaluateRequest):
        compact=self.cache_enabled and self.definition.pure_evaluate
        current = request.model_copy(update={"readonly_state": {} if compact else deepcopy(self.state),
            'state_revision':self.state_revision if compact else None,
            "context": request.context if request.context is not None else self.execution.context()})
        key = self._parent_cache.key(current) if compact else None
        if key is not None:
            self._check_cache_process(current)  # Keep failure diagnostics even without an RPC.
            cached = self._parent_cache.get(key)
            if cached is not None:
                return cached
        response = EvaluateResponse.model_validate(self._request({"action": "evaluate", "request": current.model_dump(mode="json")}))
        if key is not None:
            self._parent_cache.remember(key, response)
        return response

    @property
    def parent_cache_hits(self):
        return self._parent_cache.hits

    def commit_step(self, request: CommitStepRequest, channels: dict[str, ChannelResult] | None = None):
        candidate=self.prepare_step(request,channels)
        if candidate != self._accepted_candidate:
            if candidate.base_revision != self.state_revision:
                raise RuntimeErrorBase('模块候选已过期',code='MODULE_REVISION_CONFLICT')
            self.state=checked_state(candidate.result.state)
            self.state_revision+=1
            self._accepted_candidate=candidate
        self.synchronize_state(candidate)
        return candidate.result

    def prepare_step(self, request, channels=None):
        if channels is not None:
            request = request.model_copy(update={'converged_channels': channels})
        request = request.model_copy(update={'context': request.context if request.context is not None else self.execution.context()})
        return ModuleStepCandidate.model_validate(self._request({'action': 'prepare_step',
            'request': request.model_dump(mode='json'), 'base_revision': self.state_revision,
            'state': checked_state(self.state)}))

    def synchronize_state(self, candidate):
        response=self._request({'action': 'synchronize_state', 'candidate': candidate.model_dump(mode='json')})
        if response.get('ok') is not True or response.get('revision') != candidate.base_revision+1:
            raise RuntimeErrorBase('Worker 状态同步回执无效',code='MODULE_SYNC_ACK_INVALID')

    def discard_candidate(self):
        self._request({'action': 'discard_candidate'})

    def phase_call(self, phase, request):
        response = self._request({'action': phase, 'request': request.model_dump(mode='json')})
        parser = {'thermal':ModuleThermalResponse, 'jacobian':ModuleDerivativeResponse}.get(phase, EvaluateResponse)
        return parser.model_validate(response)

    def finalize(self):
        result = self._request(self._finalize_payload())
        self._finalized = True
        return result

    def _finalize_payload(self):
        return {'action': 'finalize', 'contexts': {
            key: invocation.context().model_dump(mode='json') for key, invocation in self._invocations.items()}}

    def close(self, force: bool = False):
        process = self.process
        if process is None:
            self._closed = True
            return
        if not force and not self._finalized:
            try:
                assert process.stdin
                process.stdin.write(json.dumps(self._finalize_payload(), ensure_ascii=False) + "\n")
                process.stdin.flush()
                self._readline()
            except Exception:
                pass
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
        finally:
            # Both readers must see EOF before their streams are closed; closing a stream
            # that a reader still owns raises, and teardown must not turn into a failure.
            for thread in (self._reader_thread, self._stderr_thread):
                if thread is not None:
                    thread.join(timeout=1.0)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
            self.process = None
            self._responses = None
            self._reader_thread = None
            self._stderr_thread = None
            self._closed = True
