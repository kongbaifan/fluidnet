"""Resumable simulation; one owner advances a session, commands run at frame boundaries."""
from __future__ import annotations

from collections import deque
import dataclasses
import math

import numpy as np

from . import solver as s
from .compiler import CompilationError, runtime_parameter, validated_parameters
from .controllers import PID
from .models import Diagnostic, PIDController
from .properties import property_service
from .control import ScriptControl


class SimulationSession:
    def __init__(self, network, duration_s, dt_s, keep=None):
        """`duration_s=None` runs until stopped. `keep` bounds the frames held here (the caller
        publishes them); without it every frame is kept and the run is limited to 2001 frames."""
        if not (math.isfinite(dt_s) and dt_s > 0) or duration_s is not None and not (math.isfinite(duration_s) and duration_s > 0):
            raise ValueError('运行时长和步长必须为有限正数')
        if keep is None and (duration_s is None or duration_s > 2000 * dt_s):
            raise ValueError('一次返回全部帧的运行最多 2001 帧，且必须设定时长')
        self.network = network
        self.duration, self.dt = duration_s, dt_s
        self.time = 0.0
        self.index = 0
        self.revision = 0
        self.frames = deque(maxlen=keep) if keep else []
        self.sequence = 0  # frames published so far; the next frame's RunFrame.sequence
        self.runners = {}
        self.controllers = {}
        self.scripts = {}
        self.script_owners = {key: script.id for script in network.project.control_scripts if script.enabled for key in script.outputs}
        self.service = property_service(network.project.fluid)
        self.stateful = s.has_state(network)
        self.warning = Diagnostic(code='DYNAMIC_IMPLICIT_EULER' if self.stateful else 'DYNAMIC_QUASI_STEADY',
            severity='info' if self.stateful else 'warning', message='隐式 Euler 时间推进，一阶精度，失败子步减半' if self.stateful
            else '准稳态时间序列：每步求解水力与热力并提交模块状态；未计算容积和热惯性')
        self.result = None
        self.tanks = s.tank_states_from(network, None, None, None)
        self.cells = {}
        self.committed = {}
        self.diagnostics = []
        self.view = network
        self.closed = False

    @property
    def done(self):
        return self.duration is not None and bool(self.frames) and self.time >= self.duration - 1e-12

    def initialize(self):
        try:
            self.runners = s._python_runners(self.network)
            self.result = s.solve_network(self.network, self.runners, 0., service=self.service if self.network.project.solver.thermal else None)
            self.cells = dict(self.result.thermal.cell_enthalpies) if self.result.thermal else {}
            # Targets and limits were checked by compile_project (validate_controllers).
            for config in self.network.project.controllers:
                current = self.network.parameters[config.instance_id][config.parameter_id]
                self.controllers[config.id] = PID(config.model_copy(deep=True), min(config.maximum, max(config.minimum, current)))
            frame = self.snapshot()
            for pid in self.controllers.values():
                pid.sample(0., frame.variables)
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

    def parameter_spec(self, instance_id, parameter_id):
        instance = self.network.instances.get(instance_id)
        if instance is None:
            raise CompilationError('PARAMETER_TARGET_MISSING', '目标设备不存在')
        return runtime_parameter(instance, self.network.modules[instance.module_id], parameter_id)

    def _candidate_parameters(self, instance_id, values, controlled=False, script_id=None):
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
        parameters = validated_parameters(candidate, definition)
        if definition.solver_model == 'pump_curve' and parameters.get('speed_ratio', 1) <= 0:
            raise CompilationError('PARAMETER_RANGE', '当前泵模型转速必须大于零')
        return parameters

    def _apply_parameters(self, instance_id, parameters):
        if parameters == self.network.parameters[instance_id]:
            return False
        definition = self.network.modules[self.network.instances[instance_id].module_id]
        if instance_id in self.runners:
            self.runners[instance_id].update_parameters(parameters)
        self.network.parameters[instance_id] = parameters
        for branch in self.network.branches:
            if branch.instance_id == instance_id and definition.runtime == 'builtin' and branch.solver_model == 'valve':
                branch.closed = parameters['opening_ratio'] == 0
        for spec in self.network.storage.values():
            if spec.instance_id == instance_id:
                spec.heat_input_w = parameters.get('heat_input_w', spec.heat_input_w)
        return True

    def set_parameter(self, instance_id, parameter_id, value, controlled=False):
        if self._apply_parameters(instance_id, self._candidate_parameters(instance_id, {parameter_id: value}, controlled)):
            self.revision += 1

    def _candidate_controller(self, controller_id, values):
        pid = self.controllers.get(controller_id)
        if pid is None or not set(values) <= {'setpoint', 'mode', 'manual_output'}:
            raise CompilationError('PID_COMMAND_INVALID', f'控制器 {controller_id} 或可调字段 {sorted(values)} 不存在'
                                   '（可调：setpoint、mode、manual_output）')
        return PIDController.model_validate(pid.config.model_dump() | values)

    def _apply_controller(self, controller_id, config):
        pid = self.controllers[controller_id]
        if config.mode != pid.config.mode:
            pid.reset = True
        pid.config = config
        pid.next_s = self.time

    def update_controller(self, controller_id, field, value):
        self._check_script_owner(f'controller.{controller_id}.{field}')
        self._apply_controller(controller_id, self._candidate_controller(controller_id, {field: value}))
        self.revision += 1

    def _check_script_owner(self, key, script_id=None):
        owner = self.script_owners.get(key)
        if owner and owner != script_id:
            raise CompilationError('PARAMETER_CONTROLLED', f'{key} 由 Python 脚本 {owner} 控制')

    def write_variables(self, values, script_id=None):
        """Write several variables at one frame boundary: all of them or none.

        Keys follow the frame: `<instance>.param.<parameter>` for runtime parameters and
        `controller.<id>.<setpoint|mode|manual_output>` for PID settings.
        """
        if not values:
            raise CompilationError('VARIABLE_WRITE_EMPTY', '没有要写入的变量')
        parameters, controllers = {}, {}
        for key, value in values.items():
            self._check_script_owner(key, script_id)
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
        changed = False
        for cid, config in configs.items():
            self._apply_controller(cid, config)
            changed = True
        for iid, params in candidates.items():
            changed = self._apply_parameters(iid, params) or changed
        if changed:
            self.revision += 1

    def _control(self):
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

    def _view(self):
        view = s._step_network(self.network, self.tanks, self.service) if self.stateful else self.network
        # Reference-free islands created at runtime get one deterministic pressure anchor.
        adjacency = {i: set() for i in range(len(view.node_keys))}
        for branch in view.branches:
            if not branch.closed:
                adjacency[branch.start_node].add(branch.end_node)
                adjacency[branch.end_node].add(branch.start_node)
        unseen = set(adjacency)
        pressure, temperature = dict(view.fixed_pressures), dict(view.fixed_temperatures)
        diagnostics = list(view.diagnostics)
        while unseen:
            group, pending = set(), [min(unseen)]
            while pending:
                node = pending.pop()
                if node in group:
                    continue
                group.add(node)
                pending.extend(adjacency[node] - group)
            unseen -= group
            if group & pressure.keys():
                continue
            branches = [b for b in view.branches if not b.closed and b.start_node in group]
            if any(b.solver_model not in {'pipe', 'valve', 'resistance', 'heat_exchanger'} or
                   view.modules[view.instances[b.instance_id].module_id].runtime == 'python' for b in branches):
                raise CompilationError('ISOLATED_ACTIVE_NETWORK', '隔离网络包含主动或自定义设备，不能采用被动管段保压近似')
            anchor = min(group, key=lambda n: view.node_keys[n])
            pressure[anchor] = float(self.result.hydraulic.pressures[anchor])
            temperature[anchor] = self.result.thermal.node_states[anchor].temperature_k if self.result.thermal else 293.15
            diagnostics.append(Diagnostic(code='ISOLATED_PRESSURE_HELD', severity='info', message='被动隔离管段采用零流量保压近似；不计算热膨胀'))
        return dataclasses.replace(view, fixed_pressures=pressure, fixed_temperatures=temperature, diagnostics=diagnostics)

    def _trial(self, h):
        view = self._view()
        warm = self.result
        if self.network.storage and warm.hydraulic.solution is not None and not warm.hydraulic.storage_rates:
            n_free = len([n for n in range(len(self.network.node_keys)) if n not in self.network.fixed_pressures])
            solution = np.insert(warm.hydraulic.solution, n_free, np.zeros(len(self.network.storage)))
            warm = dataclasses.replace(warm, hydraulic=dataclasses.replace(warm.hydraulic, solution=solution))
        result = s.solve_network(view, self.runners, self.time + h, warm=warm,
            service=self.service if view.project.solver.thermal else None,
            storage_step=(h, self.tanks, self.cells) if self.stateful else None)
        tanks = s.tank_states_from(view, result, self.tanks, h) if view.storage else {}
        cells = dict(result.thermal.cell_enthalpies) if result.thermal else {}
        return view, result, tanks, cells

    def _accept(self, h, view, result, tanks, cells):
        values, diagnostics = s._commit_modules(self.network, self.runners, result, self.time + h, h)
        for runner in self.scripts.values():
            if runner.pending:
                self.diagnostics.extend(Diagnostic.model_validate(d) for d in runner.pending[0].get('diagnostics', []))
                runner.accept()
        self.time += h
        self.view, self.result, self.tanks, self.cells = view, result, tanks, cells
        self.committed.update(values)
        self.diagnostics.extend(diagnostics)

    def snapshot(self):
        frame = s._with_states(self.view, s.snapshot(self.view, self.result, self.time, self.warning), self.result, self.tanks, self.service)
        protected = frame.variables.keys() - self.result.hydraulic.module_variables.keys()
        if protected & self.committed.keys():
            raise CompilationError('MODULE_OUTPUT_CONFLICT', 'commit_step 输出不能覆盖网络求解变量')
        frame.variables.update(self.committed)
        frame.diagnostics.extend(self.diagnostics)
        for pid in self.controllers.values():
            frame.variables.update(pid.variables())
        for runner in self.scripts.values():
            frame.variables.update(runner.variables())
        frame.sequence = self.sequence
        frame.parameter_revision = self.revision
        return frame

    def publish(self):
        frame = self.snapshot()
        self.frames.append(frame)
        self.sequence += 1
        self.committed.clear()
        self.diagnostics.clear()
        return frame

    def advance(self):
        if not self.frames:
            return self.initialize()
        if self.done:
            raise StopIteration
        # Frame times are index·dt (no accumulated rounding), so a continuous run never drifts.
        target = (self.index + 1) * self.dt if self.duration is None else min((self.index + 1) * self.dt, self.duration)
        while target - self.time > 1e-12 * max(1., target):
            self._control()
            h = min([target - self.time] + [p.next_s - self.time for p in self.controllers.values()]
                    + [script.next_s - self.time for script in self.scripts.values()])
            for attempt in range(self.network.project.solver.max_step_halvings + 1):
                try:
                    trial = self._trial(h)
                    break
                except ValueError as error:
                    if not self.stateful or not s._retryable(error):
                        raise
                    if attempt == self.network.project.solver.max_step_halvings:
                        raise s.SolveFailed('STEP_NOT_CONVERGED', f't={self.time:g} s：缩步后仍未收敛：{error}', frames=list(self.frames)) from error
                    h /= 2
            event = s._tank_event(self.network, trial[2], self.service)
            if event:
                lo, hi, found = 0., h, None
                while hi - lo > 1e-6 * self.dt:
                    mid = (lo + hi) / 2
                    try:
                        candidate = self._trial(mid)
                        if s._tank_event(self.network, candidate[2], self.service):
                            hi = mid
                        else:
                            lo, found = mid, candidate
                    except ValueError as error:
                        if not s._retryable(error):
                            raise
                        hi = mid
                if found is not None:
                    self._accept(lo, *found)
                if self.time > self.frames[-1].time_s:
                    self.publish()
                code, spec = event
                raise s.SolveFailed(code, f'{spec.instance_id} 在 t={self.time:g} s 达到液位边界，运行停止', spec.instance_id, list(self.frames))
            self._accept(h, *trial)
        self.time = target
        self.index += 1
        return self.publish()

    def close(self):
        if not self.closed:
            self.closed = True
            # Both groups must be attempted: a failing runner close must not leak the
            # control-script Workers (they hold real subprocesses).
            try:
                s._close_runners(self.runners)
            finally:
                s._close_runners(self.scripts)


def run_dynamic(network, duration_s, dt_s):
    session = SimulationSession(network, duration_s, dt_s)
    try:
        while not session.done:
            session.advance()
        return session.frames
    except CompilationError as error:
        if session.frames and error.diagnostic.code.startswith('CONTROL_'):
            raise s.SolveFailed(error.diagnostic.code, str(error), frames=list(session.frames)) from error
        raise
    finally:
        session.close()
