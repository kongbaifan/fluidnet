"""Implicit room heat balance, sharing accepted-state controls and run commands."""
from collections import deque
import math

from ..compiler import CompilationError
from ..control import ScriptControl
from ..controllers import PID
from ..models import Diagnostic, RunFrame
from ..simulation import SimulationSession
from ..solver import SolveFailed


class ThermalSession(SimulationSession):
    """Uses SimulationSession's validated parameter/control methods, not its fluid solver."""

    def __init__(self, network, duration_s, dt_s, keep=None):
        if not math.isfinite(dt_s) or dt_s <= 0 or duration_s is not None and (not math.isfinite(duration_s) or duration_s <= 0):
            raise ValueError('运行时长和步长必须为有限正数')
        if keep is None and (duration_s is None or duration_s > 2000 * dt_s):
            raise ValueError('一次返回全部帧的运行最多 2001 帧，且必须设定时长')
        self.network = network
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
        self._init_state()

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
        return RunFrame(status='converged', valid=True, time_s=self.time, variables=values,
            diagnostics=[*self.network.diagnostics, warning, *self.diagnostics],
            metrics={'energy_residual_w': self.frame_residual_j / (self.time - self.published_time)
                     if self.time > self.published_time else 0.,
                     'energy_residual_j': self.energy_residual_j, 'storage_power_w': storage_power},
            sequence=self.sequence, parameter_revision=self.revision)

    def publish(self):
        frame = self.snapshot()
        self.frames.append(frame)
        self.sequence += 1
        self.published_time = self.time
        self.frame_residual_j = 0.
        self.diagnostics.clear()
        return frame

    def _advance_heat(self, step):
        self._integrate(step)
        for script in self.scripts.values():
            if script.pending:
                self.diagnostics.extend(Diagnostic.model_validate(d) for d in script.pending[0].get('diagnostics', []))
                script.accept()
        self.time += step

    def _integrate(self, step):
        """Advance the physical state by `step`; nothing is committed unless the whole step succeeds."""
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

    def advance(self):
        if not self.frames:
            return self.initialize()
        if self.done:
            raise StopIteration
        target = (self.index + 1) * self.dt
        if self.duration is not None:
            target = min(target, self.duration)
        while target - self.time > 1e-12 * max(1., target):
            self._control()
            step = min([target - self.time, self.network.project.solver.dynamic_step_s]
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
