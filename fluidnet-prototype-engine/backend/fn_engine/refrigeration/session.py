"""Implicit room heat balance, sharing accepted-state controls and run commands."""
from collections import deque
from contextlib import contextmanager
import math

from ..compiler import CompilationError
from ..control import ScriptControl
from ..controllers import PID
from ..models import Diagnostic, RunFrame
from ..simulation import SimulationSession
from ..solver import SolveFailed
from ..timestep import (AdaptiveMarch, StepStatistics, TimeStepConfig, TimeStepExhausted, TrialFailure,
                        ensure_supported, normalized_error)


class ThermalSession(SimulationSession):
    """Uses SimulationSession's validated parameter/control methods, not its fluid solver."""

    _segment_fields: tuple[str, ...] = ('temperatures', 'cooling_energy', 'external_energy',
                                       'energy_residual_j', 'frame_residual_j')

    def __init__(self, network, duration_s, dt_s, keep=None):
        if not math.isfinite(dt_s) or dt_s <= 0 or duration_s is not None and (not math.isfinite(duration_s) or duration_s <= 0):
            raise ValueError('运行时长和步长必须为有限正数')
        if keep is None and (duration_s is None or duration_s > 2000 * dt_s):
            raise ValueError('一次返回全部帧的运行最多 2001 帧，且必须设定时长')
        # A0：旧项目缺省 time_step.enabled=False，按原固定步长路径；开启前先检查执行域是否已接入。
        self.timestep = TimeStepConfig.from_solver(network.project.solver)
        if self.timestep.enabled:
            ensure_supported(getattr(network, 'execution_domain', None))
        self.network = network
        # 困液定容（I0–I4）只在通用流体执行域编译；热模型/制冷站的编译结果没有 trapped 字段，
        # 而共用的参数写入路径会读 network.trapped，这里补空集合，行为与引入 I 系列前一致。
        if not hasattr(network, 'trapped'):
            network.trapped = {}
        self.duration, self.dt = duration_s, dt_s
        self.time = 0.
        self.index = self.sequence = self.revision = 0
        self.frames = deque(maxlen=keep) if keep else []
        self.runners, self.controllers, self.scripts = {}, {}, {}
        self.script_owners = {key: script.id for script in network.project.control_scripts if script.enabled for key in script.outputs}
        self.energy_residual_j = 0.
        self.frame_residual_j = 0.
        self.published_time = 0.
        self.diagnostics = []
        self.closed = False
        self._control_base = None
        # 困液定容（I0–I4）只在通用流体执行域启用；热模型/制冷站复用 SimulationSession 的参数与
        # 控制方法但不调用其 __init__，这里保持空状态，使共用参数写入路径与原行为一致。
        self.trapped, self.trapped_ledgers = {}, {}
        self._init_state()
        # 误差控制状态：统计与步长建议只在 accepted state 上推进，拒绝的试算不写入。
        self.march = AdaptiveMarch(self.timestep) if self.timestep.enabled else None
        self.step_stats = self.march.stats if self.march is not None else StepStatistics()

    def _init_state(self):
        network = self.network
        self.temperatures = {room: network.parameters[room]['temperature_k'] for room in network.room_sources}
        self.cooling_energy = {source: 0. for source in network.room_sources.values()}
        self.external_energy = {room: 0. for room in network.room_sources}

    def initialize(self):
        if self.frames:
            return self.frames[-1]
        try:
            for config in self.network.project.controllers:
                value = self.network.parameters[config.instance_id][config.parameter_id]
                self.controllers[config.id] = PID(config.model_copy(deep=True), value)
            for pid in self.controllers.values():
                pid.sample(0., self.snapshot().variables)
            for script in self.network.project.control_scripts:
                if not script.enabled:
                    continue
                runner = ScriptControl(script)
                self.scripts[script.id] = runner
                values = self.snapshot().variables
                missing = set(script.inputs) - values.keys()
                if missing:
                    raise CompilationError('CONTROL_INPUT_UNKNOWN', f'{script.id} 输入不存在：{sorted(missing)}')
                self.diagnostics.extend(Diagnostic.model_validate(d) for d in runner.start(values))
            return self.publish()
        except BaseException:
            self.close()
            raise

    def _powers(self, room, temperature):
        p = self.network.parameters[room]
        source = self.network.parameters[self.network.room_sources[room]]
        envelope = ((p['wall_ua_w_k'] + p['roof_ua_w_k']) * (p['ambient_temperature_k'] - temperature)
                    + p['floor_ua_w_k'] * (p['ground_temperature_k'] - temperature))
        cooling = source['cooling_power_w'] * source['capacity_ratio']
        return envelope, cooling

    def snapshot(self):
        values, storage_power = {}, 0.
        for room, source in self.network.room_sources.items():
            p, temperature = self.network.parameters[room], self.temperatures[room]
            envelope, cooling = self._powers(room, temperature)
            storage_power += envelope + p['heat_input_w'] - cooling
            values.update({f'{room}.state.temperature_k': temperature,
                           f'{room}.envelope_heat_w': envelope, f'{room}.cooling_power_w': cooling,
                           f'{room}.stored_energy_j': p['heat_capacity_j_k'] * (temperature - 273.15),
                           f'{room}.state.external_energy_j': self.external_energy[room],
                           f'{source}.cooling_power_w': cooling,
                           f'{source}.state.cooling_energy_j': self.cooling_energy[source]})
        for iid, parameters in self.network.parameters.items():
            values.update({f'{iid}.param.{key}': value for key, value in parameters.items()})
        for pid in self.controllers.values():
            values.update(pid.variables())
        for script in self.scripts.values():
            values.update(script.variables())
        warning = Diagnostic(code='COLD_ROOM_IDEAL_SOURCE', severity='info',
            message='A1 库房隐式热平衡与理想恒容量冷源；尚未计算货物热状态、制冷循环、电功率或 COP')
        metrics = {'energy_residual_w': self.frame_residual_j / (self.time - self.published_time)
                   if self.time > self.published_time else 0.,
                   'energy_residual_j': self.energy_residual_j, 'storage_power_w': storage_power}
        metrics.update(self.step_stats.frame_metrics(adaptive=self.timestep.enabled,
                                                     fixed_step=self.network.project.solver.dynamic_step_s))
        return RunFrame(status='converged', valid=True, time_s=self.time, variables=values,
            diagnostics=[*self.network.diagnostics, warning, *self.diagnostics],
            metrics=metrics, sequence=self.sequence, parameter_revision=self.revision)

    def publish(self):
        frame = self.snapshot()
        self.frames.append(frame)
        self.sequence += 1
        self.published_time = self.time
        self.frame_residual_j = 0.
        self.step_stats.end_frame()
        self.diagnostics.clear()
        return frame

    def _advance_heat(self, step):
        self._integrate(step)
        for script in self.scripts.values():
            if script.pending:
                self.diagnostics.extend(Diagnostic.model_validate(d) for d in script.pending[0].get('diagnostics', []))
                script.accept()
        self.time += step

    def _step_checkpoint(self):
        # The sequence grows for the whole run; retain its length instead of copying it per segment.
        return ({key: value for key, value in vars(self.step_stats).items() if key != 'sequence'},
                len(self.step_stats.sequence), self.march._next_h if self.march is not None else None)

    def _restore_steps(self, checkpoint):
        values, length, next_h = checkpoint
        # Failed attempts remain observable, but provisional accepted steps must not enter the ledger.
        failures = {'rejected', 'solver_failures', 'min_step_hits', 'max_error_norm',
                    'frame_rejected', 'frame_solver_failures', 'frame_max_error'}
        for key, value in values.items():
            if key not in failures:
                setattr(self.step_stats, key, value)
        del self.step_stats.sequence[length:]
        if self.march is not None:
            self.march._next_h = next_h

    @contextmanager
    def _segment_transaction(self):
        """Accept physics, controls and schedules together at the next control/output boundary."""
        state = {}
        for key in self._segment_fields:
            value = getattr(self, key)
            state[key] = value.copy() if isinstance(value, dict) else value
        step_checkpoint, start = self._step_checkpoint(), self.time
        self._control_base = self._capture_control()
        try:
            yield
        except Exception as error:
            self.time = start
            self._rollback_control()
            for key, value in state.items():
                setattr(self, key, value)
            self._restore_steps(step_checkpoint)
            # Earlier complete segments may precede the next requested output frame. Keep their
            # state and timestamp together, instead of returning only the older output-grid frame.
            if self.frames and self.time > self.frames[-1].time_s:
                self.publish()
            frames = list(self.frames)
            if isinstance(error, SolveFailed):
                error.frames = frames
                raise
            diagnostic = getattr(error, 'diagnostic', None)
            failure = SolveFailed(getattr(error, 'code', diagnostic.code if diagnostic else 'STEP_EXECUTION_FAILED'),
                                  str(error), diagnostic.instance_id if diagnostic else None, frames)
            if diagnostic is not None:
                failure.diagnostic = diagnostic
                failure.diagnostics = getattr(error, 'diagnostics', [diagnostic])
            raise failure from error
        else:
            self._control_base = None

    def _march_adaptive(self, step, trial, accept):
        checkpoint = self._step_checkpoint()
        try:
            self.march.march(segment=step, trial=trial, accept=accept, time=self.time)
        except Exception as error:
            self._restore_steps(checkpoint)
            if isinstance(error, TimeStepExhausted):
                message = f'{error}；本积分段未接受，保留 t={self.time:g}s 的状态'
                raise SolveFailed(error.code, message, None, list(self.frames)) from error
            raise

    def _integrate(self, step):
        """Advance the physical state by `step`; nothing is committed unless the whole step succeeds."""
        if self.timestep.enabled:
            return self._integrate_adaptive(step)
        temperatures, external, cooling = {}, {}, {}
        residual = 0.
        for room, source in self.network.room_sources.items():
            p, old = self.network.parameters[room], self.temperatures[room]
            ua_air = p['wall_ua_w_k'] + p['roof_ua_w_k']
            ua = ua_air + p['floor_ua_w_k']
            _, power = self._powers(room, old)
            rhs = (ua_air * p['ambient_temperature_k'] + p['floor_ua_w_k'] * p['ground_temperature_k']
                   + p['heat_input_w'] - power)
            temperature = (p['heat_capacity_j_k'] * old + step * rhs) / (p['heat_capacity_j_k'] + step * ua)
            if not math.isfinite(temperature) or temperature <= 0:
                raise SolveFailed('THERMAL_STATE_RANGE', f'{room} t={self.time + step:g}s 库温不在模型范围',
                                  room, list(self.frames))
            envelope, power = self._powers(room, temperature)
            heat_in = step * (envelope + p['heat_input_w'])
            heat_out = step * power
            residual += p['heat_capacity_j_k'] * (temperature - old) - (heat_in - heat_out)
            temperatures[room], external[room], cooling[source] = temperature, heat_in, heat_out
        # All rooms must succeed before any state or cumulative counter is committed.
        self.temperatures.update(temperatures)
        for room, energy in external.items():
            self.external_energy[room] += energy
        for source, energy in cooling.items():
            self.cooling_energy[source] += energy
        self.energy_residual_j += residual
        self.frame_residual_j += residual
        self.step_stats.fixed_step(step)

    def _heat_trial(self, temperatures, h):
        """从给定 accepted 温度向量试算 h（纯函数，不写任何状态）；返回细步所需的全部量。"""
        values, external, cooling = {}, {}, {}
        residual = 0.
        for room, source in self.network.room_sources.items():
            p, old = self.network.parameters[room], temperatures[room]
            ua_air = p['wall_ua_w_k'] + p['roof_ua_w_k']
            ua = ua_air + p['floor_ua_w_k']
            _, power = self._powers(room, old)
            rhs = (ua_air * p['ambient_temperature_k'] + p['floor_ua_w_k'] * p['ground_temperature_k']
                   + p['heat_input_w'] - power)
            temperature = (p['heat_capacity_j_k'] * old + h * rhs) / (p['heat_capacity_j_k'] + h * ua)
            if not math.isfinite(temperature) or temperature <= 0:
                raise TrialFailure(f'{room} 库温不在模型范围')
            envelope, power = self._powers(room, temperature)
            heat_in = h * (envelope + p['heat_input_w'])
            heat_out = h * power
            residual += p['heat_capacity_j_k'] * (temperature - old) - (heat_in - heat_out)
            values[room], external[room], cooling[source] = temperature, heat_in, heat_out
        return {'temperatures': values, 'external': external, 'cooling': cooling, 'residual': residual}

    def _integrate_adaptive(self, step):
        """Error-accepted internal steps remain local until the complete segment succeeds."""
        rooms = list(self.network.room_sources)
        temperatures = dict(self.temperatures)
        external, cooling = dict(self.external_energy), dict(self.cooling_energy)
        residual, frame_residual = self.energy_residual_j, self.frame_residual_j

        def trial(h):
            old = {room: temperatures[room] for room in rooms}
            full = self._heat_trial(old, h)
            half = self._heat_trial(old, 0.5 * h)
            fine = self._heat_trial(half['temperatures'], 0.5 * h)
            error = normalized_error(
                [old[room] for room in rooms], [full['temperatures'][room] for room in rooms],
                [fine['temperatures'][room] for room in rooms],
                categories=['temperature'] * len(rooms),
                atol={'temperature': self.timestep.temperature_atol_k}, rtol=self.timestep.rtol)
            return (half, fine), error

        def accept(payload, h, error):
            nonlocal residual, frame_residual
            for candidate in payload:
                temperatures.update(candidate['temperatures'])
                for room, energy in candidate['external'].items():
                    external[room] += energy
                for source, energy in candidate['cooling'].items():
                    cooling[source] += energy
                residual += candidate['residual']
                frame_residual += candidate['residual']

        self._march_adaptive(step, trial, accept)
        self.temperatures, self.external_energy, self.cooling_energy = temperatures, external, cooling
        self.energy_residual_j, self.frame_residual_j = residual, frame_residual

    def advance(self):
        if not self.frames:
            return self.initialize()
        if self.done:
            raise StopIteration
        target = (self.index + 1) * self.dt
        if self.duration is not None:
            target = min(target, self.duration)
        while target - self.time > 1e-12 * max(1., target):
            with self._segment_transaction():
                self._control()
                limit = self.timestep.max_step_s if self.timestep.enabled else self.network.project.solver.dynamic_step_s
                step = min([target - self.time, limit]
                           + [pid.next_s - self.time for pid in self.controllers.values()]
                           + [script.next_s - self.time for script in self.scripts.values()])
                if step <= 0:
                    raise CompilationError('THERMAL_STEP_INVALID', '热系统控制时钟未推进')
                self._advance_heat(step)
        self.time = target
        self.index += 1
        return self.publish()


def solve_thermal_steady(network):
    if network.project.controllers or any(script.enabled for script in network.project.control_scripts):
        raise CompilationError('CONTROL_DYNAMIC_REQUIRED', '热系统控制需要动态运行')
    session = ThermalSession(network, 1., 1.)
    for room in network.room_sources:
        p = network.parameters[room]
        ua_air = p['wall_ua_w_k'] + p['roof_ua_w_k']
        ua = ua_air + p['floor_ua_w_k']
        if ua <= 0:
            raise CompilationError('THERMAL_STEADY_UNDEFINED', f'{room} 没有稳态热参考')
        _, cooling = session._powers(room, p['temperature_k'])
        temperature = (ua_air * p['ambient_temperature_k'] + p['floor_ua_w_k'] * p['ground_temperature_k']
                       + p['heat_input_w'] - cooling) / ua
        if temperature <= 0:
            raise CompilationError('THERMAL_STATE_RANGE', f'{room} 稳态温度不在模型范围')
        session.temperatures[room] = temperature
    return session.snapshot()


def ideal_room_analytic(network, time_s, *, temperature_key='temperature_k'):
    """理想热模型（无控制、恒定容量冷源）的解析解，用于校验 A1 的步长误差估计。

    单库房热平衡为常系数线性 ODE：``C·dT/dt = UA_air·T_amb + UA_floor·T_ground + Q − P − UA·T``，
    初值取项目参数里的库温，因此 ``T(t)`` 为指数解。返回每个库房的
    ``{'temperature_k', 'external_energy_j', 'cooling_energy_j'}``（能量为从 t=0 起的累计值，
    与会话账本定义一致）。仅当无 PID/脚本且 ``capacity_ratio`` 恒定时等于真实轨迹。
    """
    if network.project.controllers or any(script.enabled for script in network.project.control_scripts):
        raise ValueError('解析解只适用于无控制、恒定容量冷源的理想热模型')
    result = {}
    for room, source in network.room_sources.items():
        p = network.parameters[room]
        rated = network.parameters[source]
        ua_air = p['wall_ua_w_k'] + p['roof_ua_w_k']
        ua = ua_air + p['floor_ua_w_k']
        capacity = p['heat_capacity_j_k']
        power = rated['cooling_power_w'] * rated['capacity_ratio']
        rhs = (ua_air * p['ambient_temperature_k'] + p['floor_ua_w_k'] * p['ground_temperature_k']
               + p['heat_input_w'] - power)
        if ua <= 0 or capacity <= 0:
            raise ValueError(f'{room} 的解析解需要正热容与正 UA')
        equilibrium = rhs / ua
        decay = ua / capacity
        delta = p[temperature_key] - equilibrium
        temperature = equilibrium + delta * math.exp(-decay * time_s)
        envelope_integral = (ua_air * (p['ambient_temperature_k'] - equilibrium)
                             + p['floor_ua_w_k'] * (p['ground_temperature_k'] - equilibrium)) * time_s
        envelope_integral -= (ua_air + p['floor_ua_w_k']) * delta * (1. - math.exp(-decay * time_s)) / decay
        result[room] = {'temperature_k': temperature,
                        'external_energy_j': envelope_integral + p['heat_input_w'] * time_s,
                        'cooling_energy_j': power * time_s}
    return result

