"""Resumable simulation; one owner advances a session, commands run at frame boundaries."""
from __future__ import annotations

import dataclasses
import json
from copy import copy, deepcopy

import numpy as np

from . import solver as s
from .compiler import CompilationError
from .session_base import SessionBase
from .controllers import PID
from .model_types.base import Diagnostic
from .module_execution import mark_module_accepted
from .module_diagnostics import merge_diagnostics
from .properties import property_service
from .control import ScriptControl
from .timestep import AdaptiveMarch, StepStatistics, TimeStepConfig, ensure_supported
from . import trapped as tr


class SimulationSession(SessionBase):
    def __init__(self, network, duration_s, dt_s, keep=None):
        """`duration_s=None` runs until stopped. `keep` bounds the frames held here (the caller
        publishes them); without it every frame is kept and the run is limited to 2001 frames."""
        super().__init__(network,duration_s,dt_s,keep)
        self.timestep = TimeStepConfig.from_solver(network.project.solver)
        if self.timestep.enabled:
            ensure_supported(getattr(network, 'execution_domain', 'fluid'))
            if any(network.modules[i.module_id].runtime == 'python' for i in network.instances.values()):
                raise CompilationError('TIMESTEP_AUTHOR_STATE_UNSUPPORTED',
                    '流体作者模块的半步状态重放尚未接入；请使用固定步长，不能忽略作者状态进行误差估计')
        self.march = AdaptiveMarch(self.timestep) if self.timestep.enabled else None
        self.step_stats = self.march.stats if self.march else StepStatistics()
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
        self.view = network
        self.last_accepted_frame = None


    def initialize(self):
        try:
            self.runners = s._python_runners(self.network)
            initial_view = dataclasses.replace(self.network,air_room_step=(0.,self.air_rooms)) if self.air_rooms else self.network
            self.result = s.solve_network(initial_view, self.runners, 0., service=self.service if self.network.project.solver.thermal else None)
            self.air_rooms = {node:item.state for node,item in getattr(self.result.thermal,'air_room_results',{}).items()}
            self.cells = dict(self.result.thermal.cell_enthalpies) if self.result.thermal else {}
            if self.timestep.enabled:
                from .simulation_adaptive import initialize_coordinates
                initialize_coordinates(self)
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


    def validate_parameter_values(self,instance_id,parameters):
        definition=self.network.modules[self.network.instances[instance_id].module_id]
        if definition.solver_model == 'coupled_tower_pool':
            from .coupled_tower_pool import validate_parameters
            validate_parameters(parameters)
        if definition.solver_model == 'pump_curve' and parameters.get('speed_ratio', 1) <= 0:
            raise CompilationError('PARAMETER_RANGE', '当前泵模型转速必须大于零')
        if self.network.project.solver.moist_air or definition.solver_model in ('cooling_tower_moist', 'water_chiller'):
            from .air_compile import validate_air_parameters
            validate_air_parameters(self.network,{instance_id:parameters},check_boundary_conflicts=False)
        if parameters != self.network.parameters[instance_id] and self.trapped and definition.runtime == 'builtin' and definition.solver_model == 'valve' \
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

    def validate_parameter_batch(self,candidates):
        if self.network.project.solver.moist_air:
            from .air_compile import validate_air_parameters
            validate_air_parameters(self.network,candidates)

    def apply_parameter_changes(self,instance_id,parameters):
        definition=self.network.modules[self.network.instances[instance_id].module_id]
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

    def capture_parameter_effects(self):
        return {'closed':[branch.closed for branch in self.network.branches],
                'storage':deepcopy(self.network.storage),'trapped':deepcopy(self.network.trapped)}

    def restore_parameter_effects(self,effects):
        self.network.storage,self.network.trapped=effects['storage'],effects['trapped']
        for branch,closed in zip(self.network.branches,effects['closed'],strict=True):
            branch.closed=closed

    def close_domain_resources(self):
        s._close_runners(self.runners)

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
            if not self.timestep.enabled:
                preview.step_stats = deepcopy(self.step_stats)
                preview.step_stats.fixed_step(h)
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
                      'air_rooms','air_accumulators', 'step_stats'):
            setattr(self, field, getattr(preview, field))
        for key, script in self.scripts.items():
            for field in ('state', 'pending', 'next_s', 'last_s', 'samples', 'last_values'):
                setattr(script, field, getattr(preview.scripts[key], field))
        self._control_base = None
        self.last_accepted_frame = frame
        transaction.synchronize()

    def snapshot(self):
        frame = s._with_states(self.view, s.snapshot(self.view, self.result, self.time, self.warning), self.result, self.tanks, self.service)
        from .tower_pool import PoolStorage
        for spec in self.network.storage.values():
            if isinstance(spec, PoolStorage):
                # Rates are fixed project inputs, so accepted time is their exact integral.
                frame.variables[f'{spec.instance_id}.state.evaporated_kg'] = self.time*spec.evaporation_kg_s
                frame.variables[f'{spec.instance_id}.state.drift_kg'] = self.time*spec.drift_kg_s
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
        step_metrics = self.step_stats.frame_metrics(adaptive=self.timestep.enabled,
            fixed_step=self.network.project.solver.dynamic_step_s)
        if not self.timestep.enabled:
            # Fixed fluid histories predate adaptive control. Keep useful physical
            # step statistics without repeating four inapplicable zeros per frame.
            for key in ('internal_rejections', 'internal_rejections_total',
                        'boundary_truncations', 'local_error_norm_max'):
                step_metrics.pop(key)
        frame.metrics.update(step_metrics)
        from .composites import map_frame
        from .measurements import apply_measurements
        return apply_measurements(self.network.project,map_frame(self.network,frame))

    def publish(self):
        frame = self.snapshot()
        self.last_accepted_frame = frame
        self.frames.append(frame)
        self.sequence += 1
        self.committed.clear()
        self.diagnostics.clear()
        self.step_stats.end_frame()
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
                failure.replay=getattr(error,'replay',None)
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
            if self.timestep.enabled:
                from .simulation_adaptive import advance_segment
                advance_segment(self, h)
                continue
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
