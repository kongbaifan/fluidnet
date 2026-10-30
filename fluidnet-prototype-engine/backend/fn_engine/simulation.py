"""Resumable simulation; one owner advances a session, commands run at frame boundaries."""
from __future__ import annotations

from collections import deque
import dataclasses
import math
import json
from copy import copy, deepcopy

import numpy as np

from . import solver as s
from .compiler import CompilationError, runtime_parameter, validated_parameters
from .controllers import PID
from .models import Diagnostic, PIDController
from .module_execution import mark_module_accepted
from .module_diagnostics import merge_diagnostics
from .properties import property_service
from .control import ScriptControl
from .timestep import TimeStepConfig, ensure_supported
from . import trapped as tr


class SimulationSession:
    # 困液状态（I0–I4）：只有通用流体执行域的 __init__ 会填充；
    # ThermalSession/StationSession/ColdStoreSession 不调用父类 __init__，因此这里给类级空默认。
    trapped: dict = {}
    trapped_ledgers: dict = {}

    def __init__(self, network, duration_s, dt_s, keep=None):
        """`duration_s=None` runs until stopped. `keep` bounds the frames held here (the caller
        publishes them); without it every frame is kept and the run is limited to 2001 frames."""
        if not (math.isfinite(dt_s) and dt_s > 0) or duration_s is not None and not (math.isfinite(duration_s) and duration_s > 0):
            raise ValueError('运行时长和步长必须为有限正数')
        if keep is None and (duration_s is None or duration_s > 2000 * dt_s):
            raise ValueError('一次返回全部帧的运行最多 2001 帧，且必须设定时长')
        # A0：通用流体执行域尚未接入误差接受控制；显式开启时明确拒绝，不静默忽略。
        self.timestep = TimeStepConfig.from_solver(network.project.solver)
        if self.timestep.enabled:
            ensure_supported(getattr(network, 'execution_domain', None))
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
        for public, destinations in network.composite_maps.get('parameters',{}).items():
            if public in self.script_owners:
                for target,parameter in destinations:
                    self.script_owners[f'{target}.param.{parameter}'] = self.script_owners[public]
        self.service = property_service(network.project.fluid)
        # 困液定容容积（I0–I4）：初态即“关阀捕获”的 accepted state；M/U 在此冻结，之后只有热量收支。
        self.trapped = tr.initial_states(network)
        self.trapped_ledgers = tr.initial_ledgers(
            network, self.trapped, lambda node: s.service_at(network, node, self.service))
        self.stateful = s.has_state(network) or bool(self.trapped)
        self.warning = Diagnostic(code='DYNAMIC_IMPLICIT_EULER' if self.stateful else 'DYNAMIC_QUASI_STEADY',
            severity='info' if self.stateful else 'warning', message='隐式 Euler 时间推进，一阶精度，失败子步减半' if self.stateful
            else '准稳态时间序列：每步求解水力与热力并提交模块状态；未计算容积和热惯性')
        self.result = None
        self.tanks = s.tank_states_from(network, None, None, None)
        self.cells = {}
        from .air_ledger import initial_accumulators
        self.air_rooms = {node:spec.initial_state for node,spec in network.air_rooms.items()}
        self.air_accumulators = initial_accumulators(network)
        self.committed = {}
        self.diagnostics = []
        self.view = network
        self.closed = False
        self._control_base = None
        self.last_accepted_frame = None

    @property
    def done(self):
        return self.duration is not None and bool(self.frames) and self.time >= self.duration - 1e-12

    def initialize(self):
        try:
            self.runners = s._python_runners(self.network)
            initial_view = dataclasses.replace(self.network,air_room_step=(0.,self.air_rooms)) if self.air_rooms else self.network
            self.result = s.solve_network(initial_view, self.runners, 0., service=self.service if self.network.project.solver.thermal else None)
            self.air_rooms = {node:item.state for node,item in getattr(self.result.thermal,'air_room_results',{}).items()}
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
            frame = self.publish()
            self.last_accepted_frame = frame
            mark_module_accepted(self.runners, self.time)
            return frame
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
        if self.network.project.solver.moist_air or definition.solver_model in ('cooling_tower_moist', 'water_chiller'):
            from .air_compile import validate_air_parameters
            validate_air_parameters(self.network,{instance_id:parameters},check_boundary_conflicts=False)
        return parameters

    def _apply_parameters(self, instance_id, parameters):
        if parameters == self.network.parameters[instance_id]:
            return False
        definition = self.network.modules[self.network.instances[instance_id].module_id]
        if self.trapped and definition.runtime == 'builtin' and definition.solver_model == 'valve' \
                and float(parameters.get('opening_ratio', 0.)) > 0:
            # 开阀请求必须在生效前拒绝：困液库存还没释放给相邻节点（I5–I9），不能把新压力硬塞回网络。
            for branch in self.network.branches:
                if branch.instance_id != instance_id:
                    continue
                nodes = [node for node in (branch.start_node, branch.end_node) if node in self.trapped]
                if nodes:
                    spec = self.network.trapped[nodes[0]]
                    message = tr.open_rejection_message(
                        s.service_at(self.network, nodes[0], self.service), spec, self.trapped[nodes[0]],
                        f'{instance_id}.opening_ratio')
                    raise CompilationError('TRAPPED_OPEN_UNSUPPORTED', message, instance_id, 'opening_ratio')
        if instance_id in self.runners:
            self.runners[instance_id].update_parameters(parameters)
        self.network.parameters[instance_id] = parameters
        for branch in self.network.branches:
            if branch.instance_id == instance_id and definition.runtime == 'builtin' and branch.solver_model == 'valve':
                branch.closed = parameters['opening_ratio'] == 0
        for spec in self.network.storage.values():
            if spec.instance_id == instance_id:
                spec.heat_input_w = parameters.get('heat_input_w', spec.heat_input_w)
        for spec in getattr(self.network, 'trapped', {}).values():
            if spec.instance_id == instance_id:
                spec.heat_input_w = parameters.get('heat_input_w', spec.heat_input_w)
                spec.heat_loss_ua_w_k = parameters.get('heat_loss_ua_w_k', spec.heat_loss_ua_w_k)
                spec.ambient_temperature_k = parameters.get('ambient_temperature_k', spec.ambient_temperature_k)
        return True

    def set_parameter(self, instance_id, parameter_id, value, controlled=False):
        destinations = getattr(self.network,'composite_maps',{}).get('parameters',{}).get(f'{instance_id}.param.{parameter_id}')
        if destinations:
            self._check_script_owner(f'{instance_id}.param.{parameter_id}')
            candidates = {target:self._candidate_parameters(target,{parameter:value},controlled) for target,parameter in destinations}
            if any(self._apply_parameters(target,parameters) for target,parameters in candidates.items()):
                self.revision += 1
            return
        candidate = self._candidate_parameters(instance_id, {parameter_id: value}, controlled)
        if self.network.project.solver.moist_air:
            from .air_compile import validate_air_parameters
            validate_air_parameters(self.network,{instance_id:candidate})
        if self._apply_parameters(instance_id, candidate):
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
        if self.network.project.solver.moist_air:
            from .air_compile import validate_air_parameters
            validate_air_parameters(self.network,candidates)
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

    def _capture_control(self):
        fields = ('state', 'pending', 'next_s', 'last_s', 'samples', 'last_values')
        return {'parameters': deepcopy(self.network.parameters), 'revision': self.revision,
            'controllers': deepcopy(self.controllers), 'diagnostics': list(self.diagnostics),
            'scripts': {key: {field: deepcopy(getattr(script, field)) for field in fields}
                        for key, script in self.scripts.items()},
            'closed': [branch.closed for branch in self.network.branches],
            'storage': deepcopy(self.network.storage), 'trapped': deepcopy(self.network.trapped)}

    def _rollback_control(self):
        base = self._control_base
        if base is None:
            return
        changed = {key for key, value in base['parameters'].items() if value != self.network.parameters[key]}
        self.network.parameters = base['parameters']
        self.revision, self.controllers, self.diagnostics = base['revision'], base['controllers'], base['diagnostics']
        self.network.storage, self.network.trapped = base['storage'], base['trapped']
        for branch, closed in zip(self.network.branches, base['closed'], strict=True):
            branch.closed = closed
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
        humidity = dict(view.fixed_humidities)
        for inst in view.instances.values():
            definition = view.modules[inst.module_id]
            if definition.solver_model == 'pressure_source':
                node = view.port_nodes[f'{inst.id}:{definition.ports[0].id}']
                params = view.parameters[inst.id]
                pressure[node],temperature[node] = params['pressure_pa'],params['temperature_k']
                if node in view.air_nodes:
                    humidity[node] = params.get('humidity_ratio_kg_kg',0.)
        # 困液定容容积：每一步的边界压力/温度来自 accepted 积分状态，而不是编译初值或保压近似。
        for node, spec in view.trapped.items():
            state = self.trapped[node]
            fluid = tr.state_of(s.service_at(view, node, self.service), spec, state)
            pressure[node] = fluid.pressure_pa
            temperature[node] = fluid.temperature_k
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
        return dataclasses.replace(view, fixed_pressures=pressure, fixed_temperatures=temperature,
                                   fixed_humidities=humidity, diagnostics=diagnostics)

    def _trial(self, h):
        view = self._view()
        if self.air_rooms:
            view = dataclasses.replace(view,air_room_step=(h,self.air_rooms))
        warm = self.result
        if self.network.storage and warm.hydraulic.solution is not None and not warm.hydraulic.storage_rates:
            n_free = len([n for n in range(len(self.network.node_keys)) if n not in self.network.fixed_pressures])
            solution = np.insert(warm.hydraulic.solution, n_free, np.zeros(len(self.network.storage)))
            warm = dataclasses.replace(warm, hydraulic=dataclasses.replace(warm.hydraulic, solution=solution))
        result = s.solve_network(view, self.runners, self.time + h, warm=warm,
            service=self.service if view.project.solver.thermal else None,
            storage_step=(h, self.tanks, self.cells) if self.stateful else None)
        result.parameter_revision=self.revision
        tanks = s.tank_states_from(view, result, self.tanks, h) if view.storage else {}
        cells = dict(result.thermal.cell_enthalpies) if result.thermal else {}
        # 封闭容积没有边界质量交换：失败/越界在 _trial 内抛出，绝不会留下半提交状态。
        if view.trapped:
            try:
                trapped = tr.step_network(view, self.trapped, self.trapped_ledgers, result.hydraulic.flows, h,
                                          lambda node: s.service_at(view, node, self.service))
            except tr.TrappedError as error:
                raise CompilationError(error.code, str(error), error.instance_id, error.field) from error
        else:
            trapped = (self.trapped, self.trapped_ledgers)
        return view, result, tanks, cells, trapped

    def _accept(self, h, view, result, tanks, cells, trapped):
        transaction = None
        try:
            if getattr(result,'parameter_revision',None) is not None and result.parameter_revision != self.revision:
                raise CompilationError('MODULE_PARAMETER_REVISION_CONFLICT','试算之后参数修订已变化，旧结果不能接受')
            values, diagnostics, transaction = s._commit_modules(self.network, self.runners, result, self.time + h, h)
            # Preview the complete frame and script acceptance on copies before promotion.
            preview = copy(self)
            preview.time = self.time + h
            preview.view, preview.result, preview.tanks, preview.cells = view, result, tanks, cells
            preview.trapped, preview.trapped_ledgers = trapped
            preview.air_rooms = {node:item.state for node,item in getattr(result.thermal,'air_room_results',{}).items()}
            from .air_ledger import advance_accumulators
            preview.air_accumulators = advance_accumulators(view,self.air_accumulators,result,h) if self.air_accumulators else {}
            preview.committed = self.committed | values
            preview.diagnostics = merge_diagnostics(self.diagnostics, diagnostics)
            preview.scripts = {key: copy(script) for key, script in self.scripts.items()}
            for script in preview.scripts.values():
                if script.pending:
                    preview.diagnostics = merge_diagnostics(preview.diagnostics,
                        [Diagnostic.model_validate(d) for d in script.pending[0].get('diagnostics', [])])
                    script.accept()
            frame = preview.snapshot()
            if not frame.valid or any(item.severity == 'error' for item in frame.diagnostics):
                raise CompilationError('MODULE_FRAME_INVALID', '候选帧包含错误，子步未接受')
            json.dumps(frame.model_dump(mode='json'), allow_nan=False)
            transaction.validate()
        except Exception:
            if transaction is not None:
                transaction.discard()
            self._rollback_control()
            raise
        transaction.promote()
        for field in ('time', 'view', 'result', 'tanks', 'cells', 'trapped', 'trapped_ledgers', 'committed', 'diagnostics',
                      'air_rooms','air_accumulators'):
            setattr(self, field, getattr(preview, field))
        for key, script in self.scripts.items():
            for field in ('state', 'pending', 'next_s', 'last_s', 'samples', 'last_values'):
                setattr(script, field, getattr(preview.scripts[key], field))
        self._control_base = None
        self.last_accepted_frame = frame
        transaction.synchronize()

    def snapshot(self):
        frame = s._with_states(self.view, s.snapshot(self.view, self.result, self.time, self.warning), self.result, self.tanks, self.service)
        protected = frame.variables.keys() - self.result.hydraulic.module_variables.keys()
        if protected & self.committed.keys():
            raise CompilationError('MODULE_OUTPUT_CONFLICT', 'commit_step 输出不能覆盖网络求解变量')
        frame.variables.update(self.committed)
        for iid,ledger in self.air_accumulators.items():
            frame.variables.update({f'{iid}.state.{key}':value for key,value in ledger.items()})
        trapped_specs = getattr(self.network, 'trapped', {})
        if trapped_specs:
            for node, spec in trapped_specs.items():
                service = s.service_at(self.view, node, self.service)
                variables, metrics = tr.frame_terms(service, spec, self.trapped[node], self.trapped_ledgers[node])
                frame.variables.update(variables)
                frame.metrics.update(metrics)
                diagnostic = tr.ledger_diagnostic(
                    self.trapped_ledgers[node], spec, self.trapped[node], tr.state_of(service, spec, self.trapped[node]))
                if diagnostic is not None:
                    frame.diagnostics.append(diagnostic)
        frame.diagnostics.extend(self.diagnostics)
        for pid in self.controllers.values():
            frame.variables.update(pid.variables())
        for runner in self.scripts.values():
            frame.variables.update(runner.variables())
        frame.sequence = self.sequence
        frame.parameter_revision = self.revision
        from .composites import map_frame
        return map_frame(self.network,frame)

    def publish(self):
        frame = self.snapshot()
        self.frames.append(frame)
        self.sequence += 1
        self.committed.clear()
        self.diagnostics.clear()
        return frame

    def advance(self):
        try:
            return self._advance()
        except Exception as error:
            self._rollback_control()
            if self.last_accepted_frame is not None and self.frames and self.time > self.frames[-1].time_s:
                frames = list(self.frames) + [self.last_accepted_frame]
                diagnostic=getattr(error,'diagnostic',None)
                code=getattr(error,'code',diagnostic.code if diagnostic else 'STEP_EXECUTION_FAILED')
                failure=s.SolveFailed(code,str(error),frames=frames)
                if getattr(error,'diagnostics',None):
                    failure.diagnostics=error.diagnostics
                    failure.diagnostic=error.diagnostics[0]
                elif diagnostic is not None:
                    failure.diagnostic=diagnostic
                raise failure from error
            raise

    def _advance(self):
        if not self.frames:
            return self.initialize()
        if self.done:
            raise StopIteration
        # Frame times are index·dt (no accumulated rounding), so a continuous run never drifts.
        target = (self.index + 1) * self.dt if self.duration is None else min((self.index + 1) * self.dt, self.duration)
        while target - self.time > 1e-12 * max(1., target):
            self._control_base = self._capture_control()
            self._control()
            h = min([target - self.time] + [p.next_s - self.time for p in self.controllers.values()]
                    + [script.next_s - self.time for script in self.scripts.values()])
            for attempt in range(self.network.project.solver.max_step_halvings + 1):
                try:
                    trial = self._trial(h)
                    break
                except CompilationError as error:
                    # 困液的越相/超压/能量步失败是物理边界，不靠缩步“成功”；先不提交，直接停止。
                    if error.diagnostic.code.startswith('TRAPPED_'):
                        raise s.SolveFailed(error.diagnostic.code, str(error), error.diagnostic.instance_id,
                                             list(self.frames)) from error
                    if not self.stateful or not s._retryable(error):
                        raise
                    if attempt == self.network.project.solver.max_step_halvings:
                        raise s.SolveFailed('STEP_NOT_CONVERGED', f't={self.time:g} s：缩步后仍未收敛：{error}',
                                            frames=list(self.frames)) from error
                    h /= 2
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
        from .air_variables import is_air_project
        if session.frames and (error.diagnostic.code.startswith('CONTROL_') or is_air_project(network.project)):
            raise s.SolveFailed(error.diagnostic.code, str(error), frames=list(session.frames)) from error
        raise
    finally:
        session.close()
