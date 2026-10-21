"""Case-A cold store: room + frozen goods, unit cooler and single-stage condensing unit (PLAN 3.3, 4.2).

Each chain unit.cold → cooler.supply, cooler.heat → room.heat is advanced by implicit Euler on the room
and goods temperatures. While the unit runs, the unknown evaporating/condensing temperatures are solved
with the new room state in one Newton iteration:

    Q_coil = UA_e·(T_room' − T_evap),   T_room' linear in Q_coil (implicit room/goods step)
    Q_coil = m(T_evap, T_cond)·(h1 − h3),   UA_c·(T_cond − T_amb) = m·(h2 − h3)

Discrete state (unit on/off with minimum on/off times, cooler cooling/defrost/drip) changes only at
substep starts; substeps are cut at events, control samples, defrost phase ends and the instant a
blocked start/stop becomes allowed. Schedule events apply once, at their simulation time, before the
control sample of that instant.
"""
from dataclasses import dataclass, field
import math

import numpy as np

from ..catalog import cold_store_catalog
from ..compiler import CompilationError, validated_parameters, validate_controllers
from ..control import validate_scripts
from ..models import Diagnostic, Project, RunFrame
from ..properties import PropertyError, property_service
from ..solver import SolveFailed
from .cycle import DeviceRangeError, check_envelope, cycle_point, cycle_rates, rated_design, superheat_warning
from .session import ThermalSession
from .station import same_parameter_contract

MODELS = {'storage_room', 'unit_cooler', 'condensing_unit'}
COOLING, DEFROST, DRIP = 0, 1, 2
EPS = 1e-9


@dataclass
class CompiledColdStore:
    project: Project
    modules: dict
    instances: dict
    parameters: dict
    kinds: dict
    chains: list                # (unit, cooler, room) per one-to-one thermal chain
    designs: dict               # unit -> {'displacement_m3_s', 'condenser_ua_w_k'} fixed at the rated point
    fluid: object               # project FluidConfig with phase_policy='any'
    events: list                # ScheduleEvent sorted by time (stable), instance targets resolved
    targets: dict               # event id -> list of instance IDs
    diagnostics: list = field(default_factory=list)
    branches: list = field(default_factory=list)
    storage: dict = field(default_factory=dict)
    room_sources: dict = field(default_factory=dict)
    execution_domain: str = 'cold_store'


def uses_cold_store(project):
    used = {instance.module_id for instance in project.instances}
    return any(m.solver_model in MODELS for m in project.modules if m.id in used)


def resolve_events(project, kinds, parameters):
    """Event targets by type; one matching device may be implicit. Checks goods temperatures against the room."""
    by_kind = {}
    for iid, kind in kinds.items():
        by_kind.setdefault(kind, []).append(iid)
    wanted = {'door_heat': 'storage_room', 'goods_addition': 'storage_room', 'electric_defrost': 'unit_cooler'}
    seen, targets = set(), {}
    for event in project.events:
        if event.id in seen:
            raise CompilationError('SCHEDULE_EVENT_INVALID', f'日程事件 ID 重复：{event.id}', field='events')
        seen.add(event.id)
        if event.type == 'ambient_temperature':
            candidates = [iid for iid, kind in kinds.items() if kind in ('storage_room', 'condensing_unit')]
        else:
            candidates = by_kind.get(wanted[event.type], [])
        if event.instance_id is not None:
            if event.instance_id not in candidates:
                raise CompilationError('SCHEDULE_EVENT_TARGET', f'事件 {event.id}（{event.type}）的设备 {event.instance_id} '
                                       '不存在或类型不符', event.instance_id, 'events')
            chosen = [event.instance_id]
        elif event.type == 'ambient_temperature':
            chosen = candidates
        elif len(candidates) == 1:
            chosen = candidates
        else:
            raise CompilationError('SCHEDULE_EVENT_TARGET', f'事件 {event.id} 有 {len(candidates)} 台可选设备，请指定 instance_id',
                                   field='events')
        if event.type == 'goods_addition':
            p = parameters[chosen[0]]
            if not p['goods_min_temperature_k'] <= event.temperature_k <= p['goods_max_temperature_k']:
                raise CompilationError('SCHEDULE_EVENT_INVALID', f'事件 {event.id} 的货温 {event.temperature_k - 273.15:.2f} °C '
                                       '超出冻结货物模型范围（不计冻结潜热）', chosen[0], 'events')
        targets[event.id] = chosen
    return sorted(project.events, key=lambda e: e.time_s), targets


def _parameter_checks(iid, kind, p):
    if kind == 'storage_room':
        if not p['goods_min_temperature_k'] < p['goods_max_temperature_k']:
            raise CompilationError('PARAMETER_RANGE', f'{iid} 货物模型温度下限须小于上限', iid, 'goods_min_temperature_k')
        if not p['goods_min_temperature_k'] <= p['goods_temperature_k'] <= p['goods_max_temperature_k']:
            raise CompilationError('PARAMETER_RANGE', f'{iid} 初始货温超出冻结货物模型范围', iid, 'goods_temperature_k')
        if p['goods_mass_kg'] <= 0:
            raise CompilationError('PARAMETER_RANGE', f'{iid} 货物质量须为正（空库可把货物换热 UA 设为 0）', iid, 'goods_mass_kg')
    elif kind == 'condensing_unit':
        if not p['min_evaporating_temperature_k'] < p['max_evaporating_temperature_k'] or \
                not p['min_condensing_temperature_k'] < p['max_condensing_temperature_k']:
            raise CompilationError('PARAMETER_RANGE', f'{iid} 运行范围下限须小于上限', iid, 'min_evaporating_temperature_k')


def compile_cold_store(project):
    modules = {m.id: m for m in project.modules}
    instances = {i.id: i for i in project.instances}
    if not project.solver.thermal:
        raise CompilationError('THERMAL_REQUIRED', '冷库系统需要启用热力计算')
    if project.circuit_fluids:
        raise CompilationError('COLD_STORE_TOPOLOGY', '单级机组的制冷剂取项目工质，不使用回路工质配置', field='circuit_fluids')
    registered = {m.solver_model: m for m in cold_store_catalog()}
    parameters, kinds, ports = {}, {}, {}
    for instance in project.instances:
        definition = modules[instance.module_id]
        reference = registered.get(definition.solver_model)
        if reference is None or definition.runtime != 'builtin':
            raise CompilationError('COLD_STORE_MODEL_UNSUPPORTED', '冷库系统只能由冻结物库房、冷风机和单级制冷机组组成'
                                   '（不能混入流体设备、A1 理想冷源、制冷站设备或 Python 模块）', instance.id)
        expected = {(p.id, p.domain, p.direction, p.circuit) for p in reference.ports}
        if definition.channels or definition.state_model != reference.state_model or \
                {(p.id, p.domain, p.direction, p.circuit) for p in definition.ports} != expected:
            raise CompilationError('COLD_STORE_PORT_INVALID', '设备端口须保持注册的标识、类型与方向', instance.id)
        if not same_parameter_contract(definition, reference):
            raise CompilationError('COLD_STORE_PARAMETER_CONTRACT', '设备参数类型、单位或可写范围与注册合同不一致', instance.id)
        parameters[instance.id] = validated_parameters(instance, definition)
        kinds[instance.id] = definition.solver_model
        _parameter_checks(instance.id, kinds[instance.id], parameters[instance.id])
        for port in definition.ports:
            ports[(instance.id, port.id)] = port
    peer, edge_ids = {}, set()
    for edge in project.connections:
        a, b = (edge.source.instance_id, edge.source.port_id), (edge.target.instance_id, edge.target.port_id)
        if edge.id in edge_ids or a not in ports or b not in ports or a[0] == b[0] or a in peer or b in peer \
                or ports[a].direction == ports[b].direction:
            raise CompilationError('COLD_STORE_CONNECTION_INVALID', f'连接 {edge.id} 无效、重复、连到自身或方向相同；'
                                   '每个热端口一对一，出口接入口')
        edge_ids.add(edge.id)
        peer[a], peer[b] = b, a
    missing = sorted(f'{i}:{p}' for i, p in ports if (i, p) not in peer)
    if missing:
        raise CompilationError('COLD_STORE_CONNECTION_MISSING', f'热端口未连接：{missing}', missing[0].split(':')[0])
    chains = []
    for iid, kind in kinds.items():
        if kind != 'condensing_unit':
            continue
        cooler, port = peer[(iid, 'cold')]
        if kinds[cooler] != 'unit_cooler' or port != 'supply':
            raise CompilationError('COLD_STORE_TOPOLOGY', f'{iid} 的冷量输出须接冷风机的制冷剂冷量输入', iid, 'cold')
        room, port = peer[(cooler, 'heat')]
        if kinds[room] != 'storage_room' or port != 'heat':
            raise CompilationError('COLD_STORE_TOPOLOGY', f'{cooler} 的库内冷量输出须接冻结物库房', cooler, 'heat')
        chains.append((iid, cooler, room))
    covered = {i for chain in chains for i in chain}
    if covered != kinds.keys():
        orphan = sorted(kinds.keys() - covered)
        raise CompilationError('COLD_STORE_TOPOLOGY', f'设备 {orphan} 不在“机组 → 冷风机 → 库房”链中', orphan[0])
    fluid = project.fluid.model_copy(update={'phase_policy': 'any'})
    try:
        service = property_service(fluid)
    except PropertyError as error:
        raise CompilationError(error.code, f'项目工质 {project.fluid.fluid} 无法用于制冷循环：{error}', field='fluid') from error
    designs = {}
    for unit, _, _ in chains:
        try:
            designs[unit] = rated_design(service, parameters[unit])
        except DeviceRangeError as error:
            raise CompilationError('CYCLE_DESIGN_INVALID', f'{unit} 额定工作点不可用（项目工质 {project.fluid.fluid}）：'
                                   f'{error}；单级机组需要可在额定蒸发/冷凝温度饱和的制冷剂（如 HEOS::R290）',
                                   unit, error.field or 'rated_evaporating_temperature_k') from error
    validate_controllers(project, modules, instances)
    validate_scripts(project, modules, instances)
    events, targets = resolve_events(project, kinds, parameters)
    return CompiledColdStore(project.model_copy(deep=True), modules, instances, parameters, kinds, chains, designs,
                             fluid, events, targets, diagnostics=list(project.import_diagnostics))


def check_event_conflicts(network):
    """Ambient events write runtime parameters; a PID or enabled script must not own the same parameter."""
    project = network.project
    owned = {f'{c.instance_id}.param.{c.parameter_id}' for c in project.controllers}
    owned |= {key for script in project.control_scripts if script.enabled for key in script.outputs}
    for event in network.events:
        if event.type == 'ambient_temperature':
            for iid in network.targets[event.id]:
                if f'{iid}.param.ambient_temperature_k' in owned:
                    raise CompilationError('SCHEDULE_EVENT_CONFLICT', f'事件 {event.id} 要写的 {iid}.ambient_temperature_k '
                                           '已由 PID 或控制脚本控制', iid, 'events')


class ColdStoreSession(ThermalSession):
    """Room/goods implicit Euler coupled with the cycle; controls, commands and publishing as in A1."""

    TOLERANCE = 1e-9          # coil and condenser balances relative to the rated cooling power
    MAX_ITERATIONS = 40
    MAX_HALVINGS = 6

    def _init_state(self):
        network = self.network
        self.service = property_service(network.fluid)
        self.temperatures, self.goods, self.goods_mass, self.counters = {}, {}, {}, {}
        self.rooms, self.units, self.coolers, self.last = {}, {}, {}, {}
        for unit, cooler, room in network.chains:
            p = network.parameters[room]
            self.temperatures[room], self.goods[room] = p['temperature_k'], p['goods_temperature_k']
            self.goods_mass[room] = p['goods_mass_kg']
            self.rooms[room] = {'in_service': False, 'pulldown_s': None, 'goods_pulldown_s': None, 'max': None,
                                'min': None, 'shortfall_since': None}
            self.units[unit] = {'running': False, 'since': -network.parameters[unit]['initial_off_elapsed_s'],
                                'starts': 0, 'blocked': False, 'guess': None, 'jacobian': None, 'point': None}
            self.coolers[cooler] = {'mode': COOLING, 'since': 0., 'pending': False, 'count': 0}
        self.event_index, self.events_applied, self.doors = 0, 0, []
        for chain in network.chains:
            self.last[chain[2]] = self._trial(chain, 0.)
        from .report import series_keys
        # Kept on every trend-history frame so CSV/HTML reports have the full curves (jobs._publish).
        self.report_keys = frozenset(key for key, _ in series_keys(network.chains))
        self.frame_warnings = {}
        self._controlled = False

    # --- discrete state ----------------------------------------------------------------------
    def initialize(self):
        if not self.frames and self.duration is not None:
            for event in self.network.events:
                if event.time_s >= self.duration:
                    self.diagnostics.append(Diagnostic(code='SCHEDULE_EVENT_AFTER_RUN', severity='warning', field='events',
                        message=f'事件 {event.id} 在 t={event.time_s:g}s，超出本次运行时长 {self.duration:g}s，不会执行'))
        return super().initialize()

    def _apply_events(self):
        events = self.network.events
        while self.event_index < len(events) and events[self.event_index].time_s <= self.time + EPS:
            event = events[self.event_index]
            self.event_index += 1
            targets = self.network.targets[event.id]
            text = {'door_heat': f'开门附加 {event.heat_w or 0:g} W，持续 {event.duration_s or 0:g} s',
                    'goods_addition': f'入库 {event.mass_kg or 0:g} kg、{(event.temperature_k or 0) - 273.15:.2f} °C 冻结货物',
                    'ambient_temperature': f'室外温度变为 {(event.temperature_k or 0) - 273.15:.2f} °C',
                    'electric_defrost': '请求电融霜'}[event.type]
            if event.type == 'door_heat':
                self.doors.append((event.time_s + event.duration_s, targets[0], event.heat_w))
            elif event.type == 'goods_addition':
                room = targets[0]
                p = self.network.parameters[room]
                mass = self.goods_mass[room]
                self.goods[room] = (mass * self.goods[room] + event.mass_kg * event.temperature_k) / (mass + event.mass_kg)
                self.goods_mass[room] = mass + event.mass_kg
                self._count(room, 'goods_energy_j', event.mass_kg * p['goods_specific_heat_j_kg_k']
                            * (event.temperature_k - p['energy_reference_temperature_k']))
            elif event.type == 'ambient_temperature':
                for iid in targets:
                    self._apply_parameters(iid, self._candidate_parameters(iid, {'ambient_temperature_k': event.temperature_k},
                                                                           controlled=True))
            else:
                cooler = self.coolers[targets[0]]
                if cooler['mode'] != COOLING or cooler['pending']:
                    self.diagnostics.append(Diagnostic(code='DEFROST_REQUEST_IGNORED', severity='warning', instance_id=targets[0],
                        message=f't={self.time:g}s 事件 {event.id}：上一融霜周期未结束，本次请求忽略'))
                    continue
                cooler['pending'] = True
            self.events_applied += 1
            self.diagnostics.append(Diagnostic(code='SCHEDULE_EVENT', severity='info',
                instance_id=targets[0] if len(targets) == 1 else None, message=f't={event.time_s:g}s 执行 {event.id}：{text}'))
        self.doors = [door for door in self.doors if door[0] > self.time + EPS]

    def _switch(self):
        """Cooler defrost phases, then unit start/stop under minimum on/off times; only at substep starts."""
        for unit, cooler, _ in self.network.chains:
            pu, pc = self.network.parameters[unit], self.network.parameters[cooler]
            u, c = self.units[unit], self.coolers[cooler]
            elapsed = self.time - u['since']
            if c['mode'] == COOLING and c['pending'] and (not u['running'] or elapsed >= pu['minimum_on_s'] - EPS):
                if u['running']:
                    u['running'], u['since'] = False, self.time
                c['mode'], c['since'], c['pending'] = DEFROST, self.time, False
            if c['mode'] == DEFROST and self.time - c['since'] >= pc['defrost_duration_s'] - EPS:
                c['mode'], c['since'] = DRIP, self.time
            if c['mode'] == DRIP and self.time - c['since'] >= pc['drip_duration_s'] - EPS:
                c['mode'], c['since'], c['count'] = COOLING, self.time, c['count'] + 1
            want = pu['run_request'] >= .5 and c['mode'] == COOLING and not c['pending']
            elapsed = self.time - u['since']
            u['blocked'] = False
            if want != u['running']:
                if elapsed >= (pu['minimum_off_s'] if want else pu['minimum_on_s']) - EPS:
                    u['running'], u['since'] = want, self.time
                    u['starts'] += want
                else:
                    u['blocked'] = True

    def _boundaries(self):
        """Times (> now) at which the discrete state may change; substeps end there."""
        times = [e.time_s for e in self.network.events[self.event_index:self.event_index + 1]]
        times += [door[0] for door in self.doors]
        for unit, cooler, _ in self.network.chains:
            pu, pc = self.network.parameters[unit], self.network.parameters[cooler]
            u, c = self.units[unit], self.coolers[cooler]
            if c['mode'] == DEFROST:
                times.append(c['since'] + pc['defrost_duration_s'])
            elif c['mode'] == DRIP:
                times.append(c['since'] + pc['drip_duration_s'])
            if u['blocked'] or c['pending'] and u['running']:
                times.append(u['since'] + (pu['minimum_on_s'] if u['running'] else pu['minimum_off_s']))
        return [t - self.time for t in times if t > self.time + EPS]

    def _control(self):
        """Same sampling/writes as SimulationSession; skipped when no PID or script is due (outputs unchanged)."""
        due = any(r.next_s <= self.time + 1e-10 for r in self.scripts.values()) or \
            any(p.next_s <= self.time + 1e-10 for p in self.controllers.values())
        if due or not self._controlled:
            self._controlled = True
            super()._control()

    def advance(self):
        if not self.frames:
            return self.initialize()
        if self.done:
            raise StopIteration
        target = (self.index + 1) * self.dt
        if self.duration is not None:
            target = min(target, self.duration)
        while target - self.time > 1e-12 * max(1., target):
            # Same-instant order: schedule inputs → control sample → discrete state → physics.
            self._apply_events()
            self._control()
            self._switch()
            step = min([target - self.time, self.network.project.solver.dynamic_step_s, *self._boundaries()]
                       + [pid.next_s - self.time for pid in self.controllers.values()]
                       + [script.next_s - self.time for script in self.scripts.values()])
            if step <= 0:
                raise CompilationError('THERMAL_STEP_INVALID', '冷库控制时钟未推进')
            self._advance_heat(step)
        self.time = target
        self.index += 1
        return self.publish()

    # --- physics -----------------------------------------------------------------------------
    def _capacity(self, unit):
        p = self.network.parameters[unit]
        request = p['capacity_ratio'] if p['variable_capacity'] >= .5 else 1.
        return max(p['min_capacity_ratio'], request)

    def _trial(self, chain, h):
        """Room, goods and (if running) cycle state after substep h from the accepted state; nothing is committed."""
        unit, cooler, room = chain
        pr, pc = self.network.parameters[room], self.network.parameters[cooler]
        running, mode = self.units[unit]['running'], self.coolers[cooler]['mode']
        fan_on = mode == COOLING and (running or pc['fan_continuous'] >= .5)
        door = sum(heat for end, target, heat in self.doors if target == room and end > self.time + EPS)
        lighting = pr['lighting_power_w'] if pr['lighting_on'] >= .5 else 0.
        fan = pc['fan_power_w'] if fan_on else 0.
        heater = pc['defrost_heater_power_w'] if mode == DEFROST else 0.
        defrost_heat = heater * pc['defrost_room_fraction']
        gains = door + lighting + pr['heat_input_w'] + fan + defrost_heat
        ua_air = pr['wall_ua_w_k'] + pr['roof_ua_w_k']
        mass = self.goods_mass[room]
        ua_goods = pr['goods_ua_w_k'] * mass / pr['goods_mass_kg']
        t_old, g_old = self.temperatures[room], self.goods[room]
        # Goods: C_g(G' − G) = h·UA_g(T' − G')  →  G' = a·T' + (1 − a)·G; then the room is linear in Q_coil.
        a = h * ua_goods / (mass * pr['goods_specific_heat_j_kg_k'] + h * ua_goods)
        denominator = pr['heat_capacity_j_k'] + h * (ua_air + pr['floor_ua_w_k'] + ua_goods * (1 - a))
        numerator = pr['heat_capacity_j_k'] * t_old + h * (ua_air * pr['ambient_temperature_k']
                    + pr['floor_ua_w_k'] * pr['ground_temperature_k'] + gains + ua_goods * (1 - a) * g_old)
        trial = {'running': running, 'fan_on': fan_on, 'door_heat_w': door, 'lighting_heat_w': lighting, 'fan_heat_w': fan,
                 'heater_power_w': heater, 'defrost_heat_w': defrost_heat, 'point': None,
                 'capacity': self._capacity(unit) if running else 0., 'coil_heat_w': 0., 'coupling_residual_w': 0.}
        if running:
            ua_e = pc['ua_w_k']
            free, factor = numerator / denominator, 1 + h * ua_e / denominator
            try:
                point = self._solve_unit(unit, ua_e, free, factor, trial['capacity'])
            except DeviceRangeError as error:
                raise DeviceRangeError(error.code, f'{unit}：{error}', unit, error.field) from error
            coil = ua_e * (free - point['evaporating_temperature_k']) / factor
            trial.update(point=point, coil_heat_w=coil, coupling_residual_w=coil - point['cooling_power_w'])
        temperature = (numerator - h * trial['coil_heat_w']) / denominator
        goods = a * temperature + (1 - a) * g_old
        envelope = ua_air * (pr['ambient_temperature_k'] - temperature) + pr['floor_ua_w_k'] * (pr['ground_temperature_k'] - temperature)
        trial.update(temperature=temperature, goods_temperature=goods, envelope_heat_w=envelope, goods_ua_w_k=ua_goods,
                     goods_heat_w=ua_goods * (goods - temperature), external_w=envelope + door + lighting + pr['heat_input_w'],
                     net_heat_w=envelope + gains - trial['coil_heat_w'])
        if not (math.isfinite(temperature) and temperature > 0):
            raise DeviceRangeError('THERMAL_STATE_RANGE', f'{room} 库温不在模型范围', room)
        if not pr['goods_min_temperature_k'] - 1e-9 <= goods <= pr['goods_max_temperature_k'] + 1e-9:
            raise DeviceRangeError('GOODS_TEMPERATURE_RANGE', f'{room} 货温 {goods - 273.15:.2f} °C 超出冻结货物模型范围 '
                                   f'[{pr["goods_min_temperature_k"] - 273.15:.2f}, {pr["goods_max_temperature_k"] - 273.15:.2f}] °C'
                                   '（A 版不计冻结潜热）', room, 'goods_max_temperature_k')
        return trial

    def _solve_unit(self, unit, ua_e, free, factor, capacity):
        """Newton on the coil and condenser balances in (T_evap, T_cond); warm start and Jacobian reuse per unit."""
        p, u = self.network.parameters[unit], self.units[unit]
        design, ambient, scale = self.network.designs[unit], p['ambient_temperature_k'], p['rated_cooling_power_w']

        def residual(x):
            r = cycle_rates(self.service, p, design['displacement_m3_s'], x[0], x[1], capacity)
            return np.array([(ua_e * (free - x[0]) / factor - r['cooling_w']) / scale,
                             (design['condenser_ua_w_k'] * (x[1] - ambient) - r['rejection_w']) / scale])

        def jacobian(x, f):
            jac = np.empty((2, 2))
            for i in range(2):
                probe = x.copy()
                probe[i] += 1e-4
                jac[:, i] = (residual(probe) - f) / 1e-4
            return jac

        load = scale * capacity
        guesses = [np.array(u['guess'])] if u['guess'] is not None else []
        guesses.append(np.array([free - load * factor / ua_e, ambient + 1.6 * load / design['condenser_ua_w_k']]))
        last_error = None
        for x in guesses:
            try:
                x, jac = self._newton(residual, jacobian, x, u['jacobian'])
            except DeviceRangeError as error:
                last_error = error
                continue
            point = cycle_point(self.service, p, design['displacement_m3_s'], x[0], x[1], capacity)
            check_envelope(p, point)
            u['trial_guess'], u['trial_jacobian'] = x.tolist(), jac
            return point
        raise DeviceRangeError('COLD_STORE_NOT_CONVERGED', f'蒸发/冷凝温度联立未收敛（{last_error}）')

    def _newton(self, residual, jacobian, x, jac):
        f = residual(x)
        fresh = jac is None
        if fresh:
            jac = jacobian(x, f)
        for _ in range(self.MAX_ITERATIONS):
            norm = float(np.max(np.abs(f)))
            if norm < self.TOLERANCE:
                return x, jac
            step = np.linalg.solve(jac, f)
            step *= min(1., 5. / max(1e-12, float(np.max(np.abs(step)))))   # at most 5 K per iteration
            accepted = None
            for _ in range(8):
                try:
                    trial = x - step
                    f_trial = residual(trial)
                    if float(np.max(np.abs(f_trial))) < norm:
                        accepted = trial, f_trial
                        break
                except DeviceRangeError:
                    pass
                step = step / 2
            if accepted is None:
                if fresh:
                    break
                jac, fresh = jacobian(x, f), True
                continue
            x, f = accepted
            fresh = False
            if float(np.max(np.abs(f))) > .5 * norm:
                jac, fresh = jacobian(x, f), True
        raise DeviceRangeError('COLD_STORE_NOT_CONVERGED', f'残差 {float(np.max(np.abs(f))):.2e}')

    FINAL = {'REFRIGERATION_ENVELOPE', 'GOODS_TEMPERATURE_RANGE', 'THERMAL_STATE_RANGE'}

    def _integrate(self, step):
        """Substeps of `step`; a failed trial is retried with half the step (discrete state stays fixed)."""
        done, h, halvings = 0., step, 0
        while done < step - 1e-12 * max(1., step):
            h = min(h, step - done)
            try:
                trials = [(chain, self._trial(chain, h)) for chain in self.network.chains]
            except DeviceRangeError as error:
                for u in self.units.values():
                    u.pop('trial_guess', None), u.pop('trial_jacobian', None)
                if error.code in self.FINAL or halvings >= self.MAX_HALVINGS:
                    failure = SolveFailed(error.code, f't={self.time + done + h:g}s {error}', error.instance_id, list(self.frames))
                    failure.diagnostic.field = error.field
                    raise failure from error
                h, halvings = h / 2, halvings + 1
                continue
            for chain, trial in trials:
                self._commit(chain, trial, h, self.time + done + h)
            done += h

    def _stored(self, room):
        p = self.network.parameters[room]
        ref = p['energy_reference_temperature_k']
        return (p['heat_capacity_j_k'] * (self.temperatures[room] - ref)
                + self.goods_mass[room] * p['goods_specific_heat_j_kg_k'] * (self.goods[room] - ref))

    def _count(self, iid, key, value):
        self.counters[(iid, key)] = self.counters.get((iid, key), 0.) + value

    def _commit(self, chain, trial, h, end):
        unit, cooler, room = chain
        pr = self.network.parameters[room]
        u, r = self.units[unit], self.rooms[room]
        before = self._stored(room)
        self.temperatures[room], self.goods[room] = trial['temperature'], trial['goods_temperature']
        if 'trial_guess' in u:
            u['guess'], u['jacobian'] = u.pop('trial_guess'), u.pop('trial_jacobian')
        self.last[room] = trial
        point = trial['point'] or {}
        electric, condenser_fan = point.get('electric_power_w', 0.), self.network.parameters[unit]['condenser_fan_power_w'] if trial['running'] else 0.
        for iid, key, power in [(room, 'external_energy_j', trial['external_w']), (room, 'cooling_energy_j', trial['coil_heat_w']),
                                (room, 'lighting_energy_j', trial['lighting_heat_w']),
                                (cooler, 'fan_energy_j', trial['fan_heat_w']), (cooler, 'heater_energy_j', trial['heater_power_w']),
                                (unit, 'electric_energy_j', electric), (unit, 'condenser_fan_energy_j', condenser_fan),
                                (unit, 'cooling_energy_j', point.get('cooling_power_w', 0.)),
                                (unit, 'condenser_heat_j', point.get('condenser_heat_w', 0.))]:
            self._count(iid, key, h * power)
        if trial['running']:
            self._count(unit, 'run_time_s', h)
        # Implicit Euler: the stored-energy change equals h·(boundary heat at the new state) up to round-off.
        residual = self._stored(room) - before - h * trial['net_heat_w']
        self.energy_residual_j += residual
        self.frame_residual_j += residual
        if point:
            warning = superheat_warning(self.network.parameters[unit], trial['temperature'], point['evaporating_temperature_k'])
            if warning:
                self.frame_warnings[(unit, warning.code)] = warning.model_copy(update={'instance_id': unit})
        # Service bookkeeping at the accepted end-of-substep state.
        temperature, alarm = trial['temperature'], pr['alarm_temperature_k']
        if temperature > alarm:
            self._count(room, 'time_above_alarm_s', h)
            self._count(room, 'degree_hours_above_alarm', h * (temperature - alarm) / 3600)
            if r['in_service']:
                self._count(room, 'service_time_above_alarm_s', h)
                self._count(room, 'service_degree_hours_above_alarm', h * (temperature - alarm) / 3600)
        # Holding (service) starts when the room first reaches its setpoint.
        if not r['in_service'] and temperature <= pr['setpoint_temperature_k']:
            r['in_service'], r['pulldown_s'] = True, end
        if r['in_service']:
            r['max'] = temperature if r['max'] is None else max(r['max'], temperature)
            r['min'] = temperature if r['min'] is None else min(r['min'], temperature)
        if r['goods_pulldown_s'] is None and trial['goods_temperature'] <= alarm:
            r['goods_pulldown_s'] = end
        full = trial['running'] and trial['capacity'] >= 1. - 1e-12
        if full and temperature > alarm:
            if r['shortfall_since'] is None:
                r['shortfall_since'] = end - h
        else:
            r['shortfall_since'] = None

    COUNTERS = {'storage_room': ('external_energy_j', 'goods_energy_j', 'cooling_energy_j', 'lighting_energy_j',
                                 'time_above_alarm_s', 'degree_hours_above_alarm', 'service_time_above_alarm_s',
                                 'service_degree_hours_above_alarm'),
                'unit_cooler': ('fan_energy_j', 'heater_energy_j'),
                'condensing_unit': ('electric_energy_j', 'condenser_fan_energy_j', 'cooling_energy_j', 'condenser_heat_j',
                                    'run_time_s')}
    POINT = ('evaporating_temperature_k', 'condensing_temperature_k', 'evaporating_pressure_pa', 'condensing_pressure_pa',
             'suction_temperature_k', 'discharge_temperature_k', 'pressure_ratio', 'cop',
             *[f'state{i}.{k}' for i in range(1, 5) for k in ('pressure_pa', 'temperature_k', 'enthalpy_j_kg',
                                                              'entropy_j_kg_k', 'quality')])

    def snapshot(self):
        network, values = self.network, {}
        electric = lighting = storage = coupling = 0.
        shortfall = []
        for unit, cooler, room in network.chains:
            pr, pu = network.parameters[room], network.parameters[unit]
            t, r, u, c = self.last[room], self.rooms[room], self.units[unit], self.coolers[cooler]
            point = t['point'] if t['running'] else None
            condenser_fan = pu['condenser_fan_power_w'] if t['running'] else 0.
            system = (point['electric_power_w'] if point else 0.) + condenser_fan + t['fan_heat_w'] + t['heater_power_w']
            values.update({
                f'{room}.state.temperature_k': self.temperatures[room], f'{room}.state.goods_temperature_k': self.goods[room],
                f'{room}.state.goods_mass_kg': self.goods_mass[room], f'{room}.goods_ua_w_k': t['goods_ua_w_k'],
                f'{room}.envelope_heat_w': t['envelope_heat_w'], f'{room}.door_heat_w': t['door_heat_w'],
                f'{room}.lighting_heat_w': t['lighting_heat_w'], f'{room}.goods_heat_w': t['goods_heat_w'],
                f'{room}.fan_heat_w': t['fan_heat_w'], f'{room}.defrost_heat_w': t['defrost_heat_w'],
                f'{room}.cooling_power_w': t['coil_heat_w'], f'{room}.net_heat_w': t['net_heat_w'],
                f'{room}.stored_energy_j': self._stored(room), f'{room}.state.in_service': 1. if r['in_service'] else 0.,
                f'{room}.state.pulldown_time_s': r['pulldown_s'], f'{room}.state.goods_pulldown_time_s': r['goods_pulldown_s'],
                f'{room}.state.max_service_temperature_k': r['max'], f'{room}.state.min_service_temperature_k': r['min'],
                f'{cooler}.state.mode': float(c['mode']), f'{cooler}.state.fan_running': 1. if t['fan_on'] else 0.,
                f'{cooler}.refrigerant_heat_w': t['coil_heat_w'], f'{cooler}.fan_power_w': t['fan_heat_w'],
                f'{cooler}.heater_power_w': t['heater_power_w'], f'{cooler}.state.defrost_count': float(c['count']),
                f'{cooler}.state.defrost_pending': 1. if c['pending'] else 0.,
                f'{unit}.state.running': 1. if t['running'] else 0., f'{unit}.actual_capacity_ratio': t['capacity'],
                f'{unit}.state.starts': float(u['starts']), f'{unit}.state.state_elapsed_s': self.time - u['since'],
                f'{unit}.state.switch_blocked': 1. if u['blocked'] else 0.,
                f'{unit}.mass_flow_kg_s': point['mass_flow_kg_s'] if point else 0.,
                f'{unit}.cooling_power_w': point['cooling_power_w'] if point else 0.,
                f'{unit}.shaft_power_w': point['shaft_power_w'] if point else 0.,
                f'{unit}.electric_power_w': point['electric_power_w'] if point else 0.,
                f'{unit}.condenser_heat_w': point['condenser_heat_w'] if point else 0.,
                f'{unit}.condenser_fan_power_w': condenser_fan,
                f'{unit}.system_cop': point['cooling_power_w'] / system if point and system > 0 else None,
                f'{unit}.displacement_m3_s': network.designs[unit]['displacement_m3_s'],
                f'{unit}.condenser_ua_w_k': network.designs[unit]['condenser_ua_w_k'],
                **{f'{unit}.{key}': point[key] if point else None for key in self.POINT}})
            electric += system
            lighting += t['lighting_heat_w']
            storage += t['net_heat_w']
            coupling = max(coupling, abs(t['coupling_residual_w']))
            if r['shortfall_since'] is not None and self.time - r['shortfall_since'] >= pr['capacity_alarm_delay_s'] - EPS:
                shortfall.append(Diagnostic(code='COLD_ROOM_CAPACITY_SHORTFALL', severity='warning', instance_id=room,
                    message=f'{room} 机组满容量运行仍高于超温报警线 {pr["alarm_temperature_k"] - 273.15:.1f} °C，'
                            f'持续超过 {pr["capacity_alarm_delay_s"] / 60:g} min；制冷能力不足'))
        for (iid, kind) in network.kinds.items():
            for key in self.COUNTERS[kind]:
                values[f'{iid}.state.{key}'] = self.counters.get((iid, key), 0.)
        for iid, parameters in network.parameters.items():
            values.update({f'{iid}.param.{key}': value for key, value in parameters.items()})
        for pid in self.controllers.values():
            values.update(pid.variables())
        for script in self.scripts.values():
            values.update(script.variables())
        scope = Diagnostic(code='COLD_STORE_MODEL', severity='info',
            message='单级准稳态循环 + 库房/货物隐式热平衡；不计制冷剂管路压降与存量动态、冻结潜热、湿度与结霜')
        metrics = {'energy_residual_w': self.frame_residual_j / (self.time - self.published_time)
                   if self.time > self.published_time else 0.,
                   'energy_residual_j': self.energy_residual_j, 'storage_power_w': storage,
                   'electric_power_w': electric, 'lighting_power_w': lighting, 'coupling_residual_w': coupling,
                   'events_applied': self.events_applied}
        return RunFrame(status='converged', valid=True, time_s=self.time, variables=values,
                        diagnostics=[*network.diagnostics, scope, *self.frame_warnings.values(), *shortfall, *self.diagnostics],
                        metrics=metrics, sequence=self.sequence, parameter_revision=self.revision)

    def publish(self):
        frame = super().publish()
        self.frame_warnings = {}
        return frame


def solve_cold_store_steady(network):
    raise CompilationError('COLD_STORE_DYNAMIC_REQUIRED', '冷库机组按最小开/停机时间启停、库温随时间变化，只能动态运行；'
                           '单个工作点请用机组工作点验证台')


def unit_workpoint(definition, parameters, fluid, evaporating_k, condensing_k, capacity_ratio):
    """Standalone condensing-unit bench at given saturation temperatures; same functions as the coupled run."""
    from ..models import ModuleInstance
    instance = ModuleInstance(id='BENCH', module_id=definition.id, name='bench', parameters=parameters)
    p = validated_parameters(instance, definition)
    _parameter_checks('BENCH', 'condensing_unit', p)
    service = property_service(fluid.model_copy(update={'phase_policy': 'any'}))
    try:
        design = rated_design(service, p)
        point = cycle_point(service, p, design['displacement_m3_s'], evaporating_k, condensing_k, capacity_ratio)
    except DeviceRangeError as error:
        raise CompilationError(error.code, str(error), field=error.field) from error
    diagnostics = []
    try:
        check_envelope(p, point)
    except DeviceRangeError as error:
        diagnostics.append(Diagnostic(code=error.code, severity='warning', field=error.field, message=str(error)))
    electric = point['electric_power_w'] + p['condenser_fan_power_w']
    return {'design': design, 'point': point, 'diagnostics': diagnostics,
            'unit_electric_power_w': electric, 'unit_cop': point['cooling_power_w'] / electric}
