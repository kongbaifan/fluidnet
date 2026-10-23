from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any

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
    NetworkRelation,
    PortState,
)


class RuntimeErrorBase(ValueError):
    code = "MODULE_RUNTIME_ERROR"


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

    def _add(self, kind: str, channel: str, parameters: dict[str, Any]):
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


class ModuleContext:
    def __init__(self, parameters: dict[str, Any], fluid: FluidConfig,
                 ports: dict[str, PortState] | None = None, state: dict[str, Any] | None = None,
                 channels: dict[str, ChannelResult] | None = None, port_fluids: dict[str, FluidConfig] | None = None):
        self.parameters = parameters
        self.fluid = _LazyPropertyService(fluid)
        self._port_fluids = {port: _LazyPropertyService(config) for port, config in (port_fluids or {}).items()}
        self.ports = ports or {}
        self.state = state if state is not None else {}
        self.channels = channels or {}
        self.net = NetworkBuilder()
        self.variables: dict[str, Any] = {}
        self.diagnostics: list[Diagnostic] = []

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

    def diagnostic(self, code: str, message: str, severity: str = "warning"):
        self.diagnostics.append(Diagnostic(code=code, message=message, severity=severity))


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
    payload = definition.model_dump(mode="json", exclude={"content_hash", "definition_hash", "package_path"})
    # JSON/browser roundtrips do not distinguish 16.0 from 16 (ParameterSpec.default is Any).
    def canonical(value):
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, list):
            return [canonical(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    payload = canonical(payload)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _load_module(definition: ModuleDefinition):
    source = module_source(definition)
    name = f"fluidnet_user_{definition.id}_{definition.version}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, f"<{definition.id}>", "exec"), module.__dict__)
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
                 initial_state: dict[str, Any] | None = None, port_fluids: dict[str, FluidConfig] | None = None):
        self.definition = definition
        self.parameters = parameters
        self.fluid = fluid
        self.port_fluids = dict(port_fluids or {})
        self.state = dict(initial_state or {})
        self.module = _load_module(definition)
        self.initialized = False

    def initialize(self):
        ctx = ModuleContext(self.parameters, self.fluid, state=self.state, port_fluids=self.port_fluids)
        callback = getattr(self.module, "initialize", None)
        if callback:
            callback(ctx)
        self.state = ctx.state
        self.initialized = True
        return self.state

    def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        if not self.initialized:
            self.initialize()
        ctx = ModuleContext(deepcopy(self.parameters), self.fluid, request.trial_ports, deepcopy(request.readonly_state),
                            port_fluids=self.port_fluids)
        getattr(self.module, "evaluate")(ctx)
        return EvaluateResponse(relations=ctx.net.relations, variables=ctx.variables, diagnostics=ctx.diagnostics)

    def commit_step(self, request: CommitStepRequest, channels: dict[str, ChannelResult] | None = None) -> CommitStepResponse:
        if not self.initialized:
            self.initialize()
        ctx = ModuleContext(deepcopy(self.parameters), self.fluid, request.converged_ports, deepcopy(self.state),
                            channels=channels or request.converged_channels, port_fluids=self.port_fluids)
        callback = getattr(self.module, "commit_step", None)
        if callback:
            callback(ctx, request.dt_s)
        self.state = ctx.state
        return CommitStepResponse(state=self.state, variables=ctx.variables, diagnostics=ctx.diagnostics)

    def finalize(self):
        callback = getattr(self.module, "finalize", None)
        if callback:
            callback(ModuleContext(self.parameters, self.fluid, state=self.state, port_fluids=self.port_fluids))


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
                 port_fluids: dict[str, FluidConfig] | None = None):
        self.definition = definition
        self.parameters = parameters
        self.fluid = fluid
        self.port_fluids = dict(port_fluids or {})
        self.state = dict(initial_state or {})
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
        if self.process is not None:
            if self.process.poll() is not None:
                returncode = self.process.returncode
                tail = self._stderr_tail()
                self.close(force=True)
                raise RuntimeErrorBase(f"模块 Worker 已退出，退出码 {returncode}{tail}")
            return
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
            raise RuntimeErrorBase(response["error"])
        return response

    def initialize(self):
        request = InitializeRequest(run_id="worker", instance_id=self.definition.id,
                                    package={"module_id": self.definition.id, "version": f"{self.definition.version}.0.0",
                                             "content_hash": self.definition.content_hash or module_content_hash(self.definition),
                                             "definition_hash": self.definition.definition_hash},
                                    parameters=self.parameters, fluid=self.fluid, port_fluids=self.port_fluids,
                                    initial_state=self.state)
        response = self._request({"action": "initialize", "definition": self.definition.model_dump(mode="json"),
                                  "request": request.model_dump(mode="json")})
        self.state = dict(response.get("state", {}))
        return self.state

    def update_parameters(self, parameters):
        self._request({'action': 'parameters', 'parameters': parameters})
        self.parameters = dict(parameters)

    def validate_entrypoint(self):
        return self._request({"action": "validate", "definition": self.definition.model_dump(mode="json")})

    def evaluate(self, request: EvaluateRequest):
        current = request.model_copy(update={"readonly_state": dict(self.state)})
        return EvaluateResponse.model_validate(self._request({"action": "evaluate", "request": current.model_dump(mode="json")}))

    def commit_step(self, request: CommitStepRequest, channels: dict[str, ChannelResult] | None = None):
        if channels is not None:
            request = request.model_copy(update={"converged_channels": channels})
        payload = {"action": "commit_step", "request": request.model_dump(mode="json")}
        response = CommitStepResponse.model_validate(self._request(payload))
        self.state = dict(response.state)
        return response

    def finalize(self):
        result = self._request({"action": "finalize"})
        self._finalized = True
        return result

    def close(self, force: bool = False):
        process = self.process
        if process is None:
            self._closed = True
            return
        if not force and not self._finalized:
            try:
                assert process.stdin
                process.stdin.write(json.dumps({"action": "finalize"}, ensure_ascii=False) + "\n")
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
