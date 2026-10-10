from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import (
    CommitStepRequest,
    CommitStepResponse,
    Diagnostic,
    EvaluateRequest,
    EvaluateResponse,
    FluidConfig,
    InitializeRequest,
    ModuleDefinition,
    NetworkRelation,
    PortState,
)
from .properties import property_service


class RuntimeErrorBase(ValueError):
    pass


@dataclass
class ChannelResult:
    mass_flow_kg_s: float = 0.0
    pressure_drop_pa: float = 0.0


class NetworkBuilder:
    def __init__(self):
        self.relations: list[NetworkRelation] = []

    def _add(self, kind: str, channel: str, parameters: dict[str, Any]):
        self.relations.append(NetworkRelation(relation_id=channel, kind=kind, channel=channel, parameters=parameters))

    def pipe(self, *, channel: str, length_m: float, diameter_m: float, roughness_m: float = 0.0,
             density_kg_m3: float | None = None, viscosity_pa_s: float | None = None, height_m: float = 0.0):
        self._add("pipe", channel, {"length_m": length_m, "diameter_m": diameter_m, "roughness_m": roughness_m,
                                     "density_kg_m3": density_kg_m3 or 0.0, "viscosity_pa_s": viscosity_pa_s or 0.0,
                                     "height_m": height_m})

    def valve(self, *, channel: str, kv: float, opening: float, density_kg_m3: float | None = None,
              height_m: float = 0.0):
        self._add("valve", channel, {"kv_m3_h": kv, "opening_ratio": opening,
                                      "density_kg_m3": density_kg_m3 or 0.0, "height_m": height_m})

    def pump(self, *, channel: str, head_curve: list[list[float]], speed_ratio: float = 1.0,
             density_kg_m3: float | None = None):
        self._add("pump", channel, {"head_curve": head_curve, "speed_ratio": speed_ratio,
                                     "density_kg_m3": density_kg_m3 or 0.0})

    def compressor(self, *, channel: str, forced_mass_flow_kg_s: float):
        self._add("compressor", channel, {"forced_mass_flow_kg_s": forced_mass_flow_kg_s})


class ModuleContext:
    def __init__(self, parameters: dict[str, Any], fluid: FluidConfig,
                 ports: dict[str, PortState] | None = None, state: dict[str, Any] | None = None,
                 channels: dict[str, ChannelResult] | None = None):
        self.parameters = parameters
        self.fluid = property_service(fluid)
        self.ports = ports or {}
        self.state = state if state is not None else {}
        self.channels = channels or {}
        self.net = NetworkBuilder()
        self.variables: dict[str, Any] = {}
        self.diagnostics: list[Diagnostic] = []

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


def module_content_hash(definition: ModuleDefinition) -> str:
    return hashlib.sha256(module_source(definition).encode("utf-8")).hexdigest()


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
    """Reference runner used by tests and by the local Worker process."""

    def __init__(self, definition: ModuleDefinition, parameters: dict[str, Any], fluid: FluidConfig,
                 initial_state: dict[str, Any] | None = None):
        self.definition = definition
        self.parameters = parameters
        self.fluid = fluid
        self.state = dict(initial_state or {})
        self.module = _load_module(definition)
        self.initialized = False

    def initialize(self):
        ctx = ModuleContext(self.parameters, self.fluid, state=self.state)
        callback = getattr(self.module, "initialize", None)
        if callback:
            callback(ctx)
        self.state = ctx.state
        self.initialized = True
        return self.state

    def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        if not self.initialized:
            self.initialize()
        ctx = ModuleContext(self.parameters, self.fluid, request.trial_ports, dict(request.readonly_state))
        getattr(self.module, "evaluate")(ctx)
        return EvaluateResponse(relations=ctx.net.relations, variables=ctx.variables, diagnostics=ctx.diagnostics)

    def commit_step(self, request: CommitStepRequest, channels: dict[str, ChannelResult] | None = None) -> CommitStepResponse:
        if not self.initialized:
            self.initialize()
        ctx = ModuleContext(self.parameters, self.fluid, request.converged_ports, self.state, channels=channels)
        callback = getattr(self.module, "commit_step", None)
        if callback:
            callback(ctx, request.dt_s)
        self.state = ctx.state
        return CommitStepResponse(state=self.state, variables=ctx.variables, diagnostics=ctx.diagnostics)

    def finalize(self):
        callback = getattr(self.module, "finalize", None)
        if callback:
            callback(ModuleContext(self.parameters, self.fluid, state=self.state))


class WorkerProcess:
    """Line-delimited JSON Worker RPC for local module execution."""

    def __init__(self, definition: ModuleDefinition, parameters: dict[str, Any], fluid: FluidConfig,
                 initial_state: dict[str, Any] | None = None):
        self.definition = definition
        self.parameters = parameters
        self.fluid = fluid
        self.initial_state = initial_state or {}
        self.process: subprocess.Popen | None = None

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.process is None:
            env = os.environ.copy()
            package_root = str(Path(__file__).resolve().parents[1])
            env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
            self.process = subprocess.Popen(
                [sys.executable, "-m", "fn_engine.worker"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=str(Path(__file__).resolve().parents[2]), env=env,
            )
        assert self.process.stdin and self.process.stdout
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeErrorBase(f"模块 Worker 已退出：{stderr}")
        response = json.loads(line)
        if response.get("error"):
            raise RuntimeErrorBase(response["error"])
        return response

    def initialize(self):
        request = InitializeRequest(run_id="worker", instance_id=self.definition.id,
                                    package={"module_id": self.definition.id, "version": f"1.0.0",
                                             "content_hash": self.definition.content_hash or module_content_hash(self.definition)},
                                    parameters=self.parameters, fluid=self.fluid, initial_state=self.initial_state)
        response = self._request({"action": "initialize", "definition": self.definition.model_dump(mode="json"),
                                  "request": request.model_dump(mode="json")})
        return response.get("state", response)

    def evaluate(self, request: EvaluateRequest):
        return EvaluateResponse.model_validate(self._request({"action": "evaluate", "request": request.model_dump(mode="json")}))

    def commit_step(self, request: CommitStepRequest):
        return CommitStepResponse.model_validate(self._request({"action": "commit_step", "request": request.model_dump(mode="json")}))

    def close(self):
        if self.process:
            try:
                self._request({"action": "finalize"})
            except Exception:
                pass
            self.process.terminate()
            self.process = None
