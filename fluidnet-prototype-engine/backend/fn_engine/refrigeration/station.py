"""Lumped refrigeration station (case B): topology from connections, implicit Euler on vessel (M, U) and room T.

Connections and headers join ports into stream nodes; pass-through devices (condenser, cascade sides, pump,
coil, vessel) join stream nodes into pressure levels, and every level holds exactly one saturated vessel.
Compressors and expansion valves move mass between levels; they and the levels form a refrigerant circuit,
whose fluid comes from `Project.circuit_fluids`. No fluid-network pressure node is created.
"""
from dataclasses import dataclass, field
from contextlib import contextmanager
import math

import numpy as np

from ..catalog import refrigeration_catalog, thermal_catalog
from ..compiler import CompilationError, DisjointSet, fluid_service, validated_parameters, validate_controllers
from ..control import validate_scripts
from ..models import Diagnostic, Domain, Project, RunFrame
from ..properties import PropertyError, property_service
from ..solver import SolveFailed
from ..timestep import TrialFailure, normalized_error
from . import devices
from .schedule import EPS, apply_set_variable, check_set_variable, check_unique
from .session import ThermalSession

# Ports that take fluid out of a vessel and the vessel phase they must be fed from.
DRAWS = {('refrigerant_compressor', 'suction'): 'vapor', ('expansion_valve', 'in0'): 'liquid',
         ('refrigerant_pump', 'in0'): 'liquid', ('cascade_exchanger', 'evap_in'): 'liquid',
         ('cascade_exchanger', 'cond_in'): 'vapor'}
# Devices whose two stream ports sit on one pressure level.
PASS_THROUGH = {'evaporative_condenser': [('in0', 'out0')], 'refrigerant_pump': [('in0', 'out0')],
                'air_cooler': [('in0', 'out0')], 'cascade_exchanger': [('evap_in', 'evap_out'), ('cond_in', 'cond_out')],
                'saturated_vessel': [('in0', 'in1'), ('in0', 'vapor'), ('in0', 'liquid')]}
# Devices that connect two pressure levels.
BRIDGES = {'refrigerant_compressor': ('suction', 'discharge'), 'expansion_valve': ('in0', 'out0')}


def same_parameter_contract(definition, reference):
    """Types, units, runtime/writable flags and limits of a built-in model; only defaults are project-owned."""
    actual = {p.id: p for p in definition.parameters}
    return actual.keys() == {p.id for p in reference.parameters} and not any(
        actual[p.id].value_type != p.value_type or actual[p.id].unit != p.unit or actual[p.id].runtime != p.runtime
        or actual[p.id].writable != p.writable or actual[p.id].minimum != p.minimum or actual[p.id].maximum != p.maximum
        for p in reference.parameters)


@dataclass
class CompiledStation:
    refrigeration_modules: dict = field(default_factory=dict,kw_only=True)
    project: Project
    modules: dict
    instances: dict
    parameters: dict
    kinds: dict                 # instance -> solver_model
    vessels: list               # vessel instance IDs in project order
    circuit_of: dict            # vessel -> circuit index
    circuit_fluids: list        # FluidConfig per circuit (as configured)
    circuit_sources: list
    vessel_fluids: dict         # vessel -> FluidConfig with phase_policy='any'
    levels: dict                # (instance, port) -> vessel for every connected stream port
    supply: dict                # air cooler -> pump IDs feeding its supply node
    room_coolers: dict          # room -> air cooler
    diagnostics: list = field(default_factory=list)
    events: list = field(default_factory=list)   # set_variable schedule, sorted by time
    branches: list = field(default_factory=list)
    storage: dict = field(default_factory=dict)
    execution_domain: str = 'refrigeration'

    def vessel(self, instance_id, port_id):
        return self.levels[(instance_id, port_id)]


def _fluid_key(config):
    from ..properties import _parse_fluid
    return _parse_fluid(config)


def compile_station(project):
    modules = {m.id: m for m in project.modules}
    instances = {i.id: i for i in project.instances}
    if not instances:
        raise CompilationError('EMPTY_NETWORK', '项目没有设备')
    registered: dict[str, list] = {}
    for definition in (*refrigeration_catalog(), *thermal_catalog()):
        registered.setdefault(definition.solver_model, []).append(definition)
    parameters, kinds, ports, author_modules = {}, {}, {}, {}
    for instance in project.instances:
        definition = modules[instance.module_id]
        if definition.execution_role or definition.schema_version==4:
            from ..refrigeration_roles import require_throttle_role
            try:
                require_throttle_role(definition)
            except ValueError as error:
                raise CompilationError(getattr(error,'code','MODULE_CONTRACT_INVALID'),str(error),instance.id,
                                       getattr(error,'field','execution_role')) from error
            if project.thermal_couplings or project.solver.moist_air:
                raise CompilationError('MODULE_EXECUTION_DOMAIN_UNSUPPORTED',
                    '制冷作者角色仅支持纯集总制冷站',instance.id,'execution_role')
            parameters[instance.id] = validated_parameters(instance,definition)
            kinds[instance.id] = 'expansion_valve'
            author_modules[instance.id] = definition.model_copy(deep=True)
            for port in definition.ports:
                ports[(instance.id,port.id)] = port
            continue
        references = registered.get(definition.solver_model)
        if not references or definition.runtime != 'builtin' or definition.solver_model == 'ideal_cold_source':
            raise CompilationError('REFRIGERATION_MODEL_UNSUPPORTED',
                                   '制冷站只能由内置制冷设备、库房热节点或已声明角色的 Python 模块组成', instance.id)
        # One solver model may register several port layouts (e.g. multi-inlet vessels). Prefer the
        # definition with the same module ID; otherwise the contract check below reports the mismatch.
        reference = next((item for item in references if item.id == definition.id), references[0])
        expected = {(p.id, p.domain, p.direction, p.circuit) for p in reference.ports}
        if definition.channels or definition.state_model != reference.state_model or \
                {(p.id, p.domain, p.direction, p.circuit) for p in definition.ports} != expected:
            raise CompilationError('REFRIGERATION_PORT_INVALID', '设备端口须保持注册的标识、类型、方向与回路', instance.id)
        if not same_parameter_contract(definition, reference):
            raise CompilationError('REFRIGERATION_PARAMETER_CONTRACT', '设备参数类型、单位或可写范围与注册合同不一致', instance.id)
        parameters[instance.id] = validated_parameters(instance, definition)
        kinds[instance.id] = definition.solver_model
        for port in definition.ports:
            ports[(instance.id, port.id)] = port
    # Connections: one per port, same domain, an outlet to an inlet.
    links, used, edge_ids = [], set(), set()
    for edge in project.connections:
        a, b = (edge.source.instance_id, edge.source.port_id), (edge.target.instance_id, edge.target.port_id)
        if edge.id in edge_ids or a not in ports or b not in ports or a[0] == b[0]:
            raise CompilationError('REFRIGERATION_CONNECTION_INVALID', f'连接 {edge.id} 无效、重复或连到设备自身')
        if a in used or b in used:
            raise CompilationError('REFRIGERATION_CONNECTION_INVALID', f'连接 {edge.id}：每个端口只能连接一次，分支请用制冷剂集管')
        if ports[a].domain != ports[b].domain or ports[a].direction == ports[b].direction:
            raise CompilationError('REFRIGERATION_CONNECTION_INVALID', f'连接 {edge.id}：两端须同类型，且出口接入口')
        edge_ids.add(edge.id)
        used.update((a, b))
        links.append((a, b))
    missing = sorted(f'{i}:{p}' for (i, p), port in ports.items() if port.required and (i, p) not in used)
    if missing:
        raise CompilationError('REFRIGERATION_CONNECTION_MISSING', f'必连端口未连接：{missing}', missing[0].split(':')[0])
    room_coolers = {}
    for a, b in links:
        if ports[a].domain == Domain.thermal:
            room, cooler = (a[0], b[0]) if kinds[a[0]] == 'cold_room' else (b[0], a[0])
            room_coolers[room] = cooler
    # Stream nodes: connections plus headers.
    stream = [key for key, port in ports.items() if port.domain == Domain.refrigerant]
    nodes = DisjointSet(stream)
    for a, b in links:
        if ports[a].domain == Domain.refrigerant:
            nodes.union(a, b)
    for iid, kind in kinds.items():
        if kind == 'refrigerant_header':
            header = [key for key in stream if key[0] == iid]
            for key in header[1:]:
                nodes.union(header[0], key)
    vessel_ports = {}
    for key in stream:
        if kinds[key[0]] == 'saturated_vessel' and key in used:
            root = nodes.find(key)
            if root in vessel_ports:
                raise CompilationError('REFRIGERATION_VESSEL_SHORT', f'{vessel_ports[root][0]} 与 {key[0]} 的端口直接相通；'
                                       '两个容器之间须经压缩机、节流阀或换热设备', key[0])
            vessel_ports[root] = key
    for iid, port_id in stream:
        phase = DRAWS.get((kinds[iid], port_id))
        if phase is None:
            continue
        source = vessel_ports.get(nodes.find((iid, port_id)))
        if source is None or source[1] != phase:
            raise CompilationError('REFRIGERATION_PORT_ROLE', f'{iid}.{port_id} 须直接或经集管连到容器的'
                                   f'{"气相" if phase == "vapor" else "液相"}出口', iid, port_id)
    # Pressure levels: stream nodes joined through pass-through devices.
    levels = DisjointSet({nodes.find(key) for key in stream})
    for iid, kind in kinds.items():
        if kind == 'saturated_vessel':
            # Every stream port of a vessel sits on its single pressure level, whatever the layout
            # (the multi-inlet variants add in2/in3 beyond the registered four-port layout).
            pairs = [('in0', key[1]) for key in stream if key[0] == iid and key[1] != 'in0']
        else:
            pairs = PASS_THROUGH.get(kind, ())
        for left, right in pairs:
            levels.union(nodes.find((iid, left)), nodes.find((iid, right)))
    level_vessel = {}
    for iid, kind in kinds.items():
        if kind == 'saturated_vessel':
            root = levels.find(nodes.find((iid, 'in0')))
            if root in level_vessel:
                raise CompilationError('REFRIGERATION_LEVEL_VESSELS', f'{level_vessel[root]} 与 {iid} 处在同一压力等级；'
                                       '每个压力等级只能有一个容器', iid)
            level_vessel[root] = iid
    resolved = {}
    for key in stream:
        if key not in used and kinds[key[0]] in ('refrigerant_header', 'saturated_vessel'):
            continue
        vessel = level_vessel.get(levels.find(nodes.find(key)))
        if vessel is None:
            raise CompilationError('REFRIGERATION_LEVEL_NO_VESSEL', f'{key[0]}.{key[1]} 所在压力等级没有容器，'
                                   '压力无法确定', key[0], key[1])
        resolved[key] = vessel
    for iid, kind in kinds.items():
        if kind in BRIDGES:
            low, high = (resolved[(iid, p)] for p in BRIDGES[kind])
            if low == high:
                raise CompilationError('REFRIGERATION_BRIDGE_SAME_LEVEL', f'{iid} 两端处在同一压力等级（{low}）', iid)
    # Circuits: levels joined through compressors and valves.
    vessels = [iid for iid, kind in kinds.items() if kind == 'saturated_vessel']
    circuits = DisjointSet(vessels)
    for iid, kind in kinds.items():
        if kind in BRIDGES:
            circuits.union(*(resolved[(iid, p)] for p in BRIDGES[kind]))
    for iid, kind in kinds.items():
        if kind == 'cascade_exchanger' and circuits.find(resolved[(iid, 'evap_in')]) == circuits.find(resolved[(iid, 'cond_in')]):
            raise CompilationError('REFRIGERATION_CASCADE_CIRCUIT', f'{iid} 的蒸发侧与冷凝侧在同一制冷剂回路', iid)
    order = {}
    for vessel in vessels:
        order.setdefault(circuits.find(vessel), len(order))
    fluids, sources = [project.fluid] * len(order), ['project'] * len(order)
    for entry in project.circuit_fluids:
        key = (entry.anchor.instance_id, entry.anchor.port_id)
        if key not in resolved:
            raise CompilationError('CIRCUIT_ANCHOR_UNKNOWN', f'回路工质 {entry.id} 的锚点 {key[0]}:{key[1]} 不是已连接的制冷剂端口',
                                   key[0] if key[0] in instances else None, 'circuit_fluids')
        fluid_service(project, entry.fluid, f'回路工质 {entry.id}')
        index = order[circuits.find(resolved[key])]
        if sources[index] != 'project' and _fluid_key(fluids[index]) != _fluid_key(entry.fluid):
            raise CompilationError('FLUID_CONFLICT', f'回路工质 {entry.id} 与 {sources[index]} 指定在同一个制冷剂回路',
                                   key[0], 'circuit_fluids')
        fluids[index], sources[index] = entry.fluid, entry.id
    circuit_of = {vessel: order[circuits.find(vessel)] for vessel in vessels}
    vessel_fluids = {vessel: fluids[circuit_of[vessel]].model_copy(update={'phase_policy': 'any'}) for vessel in vessels}
    for vessel in vessels:
        service = fluid_service(project, vessel_fluids[vessel], f'{vessel} 所在回路工质')
        params = parameters[vessel]
        if params['min_level_ratio'] >= params['max_level_ratio']:
            raise CompilationError('PARAMETER_RANGE', f'{vessel} 液位适用下限须小于上限', vessel, 'min_level_ratio')
        try:
            state = devices.vessel_state(service, params, *devices.vessel_initial(service, params))
            devices.check_vessel(params, state)
        except (devices.DeviceRangeError, PropertyError) as error:
            raise CompilationError('VESSEL_INITIAL_STATE', f'{vessel} 初始状态不可用（{service.fluid}，'
                                   f'{params["temperature_k"] - 273.15:.2f} °C）：{error}', vessel, 'temperature_k') from error
    # Coil supply: the pumps whose outlet shares the coil's supply stream node.
    supply = {}
    for iid, kind in kinds.items():
        if kind == 'air_cooler':
            root = nodes.find((iid, 'in0'))
            pumps = [pid for pid, k in kinds.items() if k == 'refrigerant_pump' and nodes.find((pid, 'out0')) == root]
            if not pumps:
                raise CompilationError('REFRIGERATION_COIL_SUPPLY', f'{iid} 的供液口须直接或经集管连到制冷剂液泵出口', iid, 'in0')
            supply[iid] = pumps
    for iid,definition in author_modules.items():
        from ..refrigeration_roles import role_fluid
        try:
            role_fluid(definition,vessel_fluids[resolved[(iid,'in0')]])
        except ValueError as error:
            raise CompilationError(getattr(error,'code','MODULE_FLUID_UNSUPPORTED'),str(error),iid,
                                   getattr(error,'field','fluid')) from error
    validate_controllers(project, modules, instances)
    validate_scripts(project, modules, instances)
    check_unique(project.events)
    for event in project.events:
        if event.type != 'set_variable':
            raise CompilationError('SCHEDULE_UNSUPPORTED', f'制冷站日程只支持 set_variable（事件 {event.id} 为 {event.type}）',
                                   field='events')
        check_set_variable(project, modules, instances, event)
    return CompiledStation(project.model_copy(deep=True), modules, instances, parameters, kinds, vessels, circuit_of,
                           fluids, sources, vessel_fluids, resolved, supply, room_coolers,
                           refrigeration_modules=author_modules,
                           diagnostics=list(project.import_diagnostics),
                           events=sorted(project.events, key=lambda e: e.time_s))


def station_circuits(network):
    """Fluid circuits for /projects/validate: the connected stream ports of each refrigerant circuit."""
    ports = [[] for _ in network.circuit_fluids]
    for (iid, port_id), vessel in network.levels.items():
        ports[network.circuit_of[vessel]].append(f'{iid}:{port_id}')
    return [{'id': i, 'fluid': fluid, 'source': network.circuit_sources[i], 'ports': sorted(ports[i])}
            for i, fluid in enumerate(network.circuit_fluids)]

def _device(instance_id, call, *args):
    """Device evaluation; range and property failures name the instance."""
    try:
        return call(*args)
    except devices.DeviceRangeError as error:
        raise devices.DeviceRangeError(error.code, f'{instance_id}：{error}', instance_id) from error
    except PropertyError as error:
        raise devices.DeviceRangeError(error.code, f'{instance_id}：{error}', instance_id) from error


def evaluate(network, services, masses, energies, temperatures, *, valve_evaluator=None):
    """Device outputs and the state derivatives (dM/dt, dU/dt per vessel, dT/dt per room) at one state."""
    if network.refrigeration_modules and valve_evaluator is None:
        raise CompilationError('REFRIGERATION_MODULE_CONTEXT_REQUIRED',
            '制冷作者模块需要会话拥有的 Worker 上下文',next(iter(network.refrigeration_modules)))
    p = network.parameters
    vessel = {v: _device(v, devices.vessel_state, services[v], p[v], masses[v], energies[v]) for v in network.vessels}
    dm = dict.fromkeys(network.vessels, 0.)
    du = dict.fromkeys(network.vessels, 0.)
    out, boundary = {}, 0.
    by_kind = {}
    for iid, kind in network.kinds.items():
        by_kind.setdefault(kind, []).append(iid)
    for iid in by_kind.get('refrigerant_compressor', ()):
        low, high = network.vessel(iid, 'suction'), network.vessel(iid, 'discharge')
        r = _device(iid, devices.compressor_point, services[low], p[iid], vessel[low].pressure_pa, vessel[high].pressure_pa)
        dm[low] -= r['mass_flow_kg_s']
        du[low] -= r['mass_flow_kg_s'] * r['suction_enthalpy_j_kg']
        dm[high] += r['mass_flow_kg_s']
        du[high] += r['mass_flow_kg_s'] * r['discharge_enthalpy_j_kg']
        boundary += r['shaft_power_w']
        out[iid] = r
    for iid in by_kind.get('expansion_valve', ()):
        high, low = network.vessel(iid, 'in0'), network.vessel(iid, 'out0')
        r = (_device(iid, devices.valve_flow, services[high], p[iid], vessel[high].pressure_pa, vessel[low].pressure_pa)
             if valve_evaluator is None else
             valve_evaluator(iid, services[high], p[iid], vessel[high], vessel[low]))
        for v, sign in ((high, -1), (low, 1)):
            dm[v] += sign * r['mass_flow_kg_s']
            du[v] += sign * r['mass_flow_kg_s'] * r['enthalpy_j_kg']
        out[iid] = r
    for iid in by_kind.get('evaporative_condenser', ()):
        v = network.vessel(iid, 'in0')
        r = _device(iid, devices.condenser_duty, services[v], p[iid], vessel[v].pressure_pa)
        du[v] -= r['heat_rejection_w']
        boundary -= r['heat_rejection_w']
        out[iid] = r
    for iid in by_kind.get('cascade_exchanger', ()):
        evap, cond = network.vessel(iid, 'evap_in'), network.vessel(iid, 'cond_in')
        r = _device(iid, devices.cascade_duty, services[evap], services[cond], p[iid],
                    vessel[evap].pressure_pa, vessel[cond].pressure_pa)
        du[evap] += r['heat_w']
        du[cond] -= r['heat_w']
        out[iid] = r
    for iid in by_kind.get('refrigerant_pump', ()):
        v = network.vessel(iid, 'in0')
        r = _device(iid, devices.pump_point, services[v], p[iid], vessel[v].pressure_pa)
        du[v] += r['heat_to_fluid_w']
        boundary += r['electric_power_w']
        out[iid] = r
    room_of = {cooler: room for room, cooler in network.room_coolers.items()}
    dt = {}
    for iid in by_kind.get('air_cooler', ()):
        v = network.vessel(iid, 'in0')
        # Every coil on a supply node shares the flow of the pumps on that node, by supply-valve opening.
        share = [c for c, pumps in network.supply.items() if pumps == network.supply[iid]]
        pumped = sum(out[pid]['mass_flow_kg_s'] for pid in network.supply[iid])
        flow = devices.split_supply(pumped, {c: p[c]['supply_valve_ratio'] for c in share})[iid]
        r = _device(iid, devices.air_cooler_point, services[v], p[iid], vessel[v].pressure_pa, temperatures[room_of[iid]], flow)
        du[v] += r['refrigerant_heat_w']
        boundary += r['fan_power_w']
        out[iid] = r
    for room in by_kind.get('cold_room', ()):
        q = p[room]
        envelope = ((q['wall_ua_w_k'] + q['roof_ua_w_k']) * (q['ambient_temperature_k'] - temperatures[room])
                    + q['floor_ua_w_k'] * (q['ground_temperature_k'] - temperatures[room]))
        cooling = out[network.room_coolers[room]]['room_cooling_w']
        dt[room] = (envelope + q['heat_input_w'] - cooling) / q['heat_capacity_j_k']
        boundary += envelope + q['heat_input_w']
        out[room] = {'envelope_heat_w': envelope, 'cooling_power_w': cooling}
    return {'vessels': vessel, 'devices': out, 'dm': dm, 'du': du, 'dt': dt, 'boundary_w': boundary}


SPECIFIC_ENERGY_SCALE = 1e5  # J/kg; vessel energies are compared per unit of stored mass


class StationSession(ThermalSession):
    """Implicit Euler on vessel (M, U) and room temperatures; control and publishing as in A1."""

    _segment_fields: tuple[str, ...] = ('masses', 'energies', 'temperatures', 'counters',
                                       'energy_residual_j', 'frame_residual_j', 'event_index', 'events_applied',
                                       '_controlled', '_jacobian', '_cache', 'last_trial')
    TOLERANCE = 1e-10
    MAX_ITERATIONS = 12
    MAX_HALVINGS = 6

    def __init__(self, network, duration_s, dt_s, keep=None):
        super().__init__(network,duration_s,dt_s,keep)
        self.module_adapter = None
        self._candidate_time = 0.
        self._trial_start_time = None
        self._module_transaction = None
        if network.refrigeration_modules:
            from .module_adapter import RefrigerationModules
            self.module_adapter = RefrigerationModules(network)
            self.runners = self.module_adapter.runners

    def _init_state(self):
        network = self.network
        self.services = {v: property_service(network.vessel_fluids[v]) for v in network.vessels}
        self.masses, self.energies = {}, {}
        for v in network.vessels:
            self.masses[v], self.energies[v] = devices.vessel_initial(self.services[v], network.parameters[v])
        self.temperatures = {iid: network.parameters[iid]['temperature_k']
                             for iid, kind in network.kinds.items() if kind == 'cold_room'}
        self.circuit_mass = [sum(self.masses[v] for v in network.vessels if network.circuit_of[v] == c)
                             for c in range(len(network.circuit_fluids))]
        # A0：能量状态相对这个冻结参考态中心化；物性内能零点改变时 u 与参考同步平移。
        self.energy_reference = dict(self.energies)
        self.last_trial = None
        self.counters = {}
        self.event_index = self.events_applied = 0
        from .report import station_series_keys
        # Kept on every trend-history frame so CSV/HTML reports have the full curves (jobs._publish).
        self.report_keys = frozenset(key for key, _ in station_series_keys(network))
        self.scale = np.array([s for v in network.vessels for s in (self.masses[v], self.masses[v] * SPECIFIC_ENERGY_SCALE)]
                              + [1.] * len(self.temperatures))
        self._jacobian = None
        self._cache = None
        self._controlled = False
        self.nonlinear_iterations = 0  # attempted Newton iterations, including rejected trials

    # --- state vector -------------------------------------------------------------------------
    def _vector(self, masses, energies, temperatures):
        return np.array([x for v in self.network.vessels for x in (masses[v], energies[v])]
                        + [temperatures[r] for r in self.temperatures]) / self.scale

    def _unpack(self, x):
        values = x * self.scale
        n = len(self.network.vessels)
        masses = {v: values[2 * i] for i, v in enumerate(self.network.vessels)}
        energies = {v: values[2 * i + 1] for i, v in enumerate(self.network.vessels)}
        temperatures = {r: values[2 * n + i] for i, r in enumerate(self.temperatures)}
        return masses, energies, temperatures

    def _flux(self, x):
        result = self._evaluate(*self._unpack(x))
        rate = [r for v in self.network.vessels for r in (result['dm'][v], result['du'][v])] + \
               [result['dt'][r] for r in self.temperatures]
        return np.array(rate) / self.scale, result

    def _evaluate(self, masses, energies, temperatures):
        callback = None if self.module_adapter is None else lambda iid,service,parameters,high,low: \
            self.module_adapter.evaluate(iid,service,parameters,high,low,self._candidate_time)
        return evaluate(self.network,self.services,masses,energies,temperatures,valve_evaluator=callback)

    def _solve_at(self, x, h, time_s):
        self._candidate_time = time_s
        return self._solve(x,h)

    def _derivative(self, x, base):
        jac = np.empty((len(x), len(x)))
        for i in range(len(x)):
            probe = x.copy()
            delta = 1e-7 * max(1., abs(x[i]))
            probe[i] += delta
            jac[:, i] = (self._flux(probe)[0] - base) / delta
        return jac

    def _solve(self, x_old, h):
        """Newton on x − x_old − h·f(x) = 0 (scaled); the flux Jacobian is reused across steps until it stalls."""
        x = x_old.copy()
        f, result = self._flux(x)
        refreshed = self._jacobian is None
        if refreshed:
            self._jacobian = self._derivative(x, f)
        previous = math.inf
        for _ in range(self.MAX_ITERATIONS):
            self.nonlinear_iterations += 1
            residual = x - x_old - h * f
            norm = float(np.max(np.abs(residual)))
            if norm < self.TOLERANCE:
                return x, result
            if norm > .5 * previous and not refreshed:
                self._jacobian, refreshed = self._derivative(x, f), True
            previous = norm
            step = np.linalg.solve(np.eye(len(x)) - h * self._jacobian, residual)
            for _ in range(5):
                try:
                    trial = x - step
                    f, result = self._flux(trial)
                    x = trial
                    break
                except devices.DeviceRangeError:
                    step = step / 2
            else:
                raise devices.DeviceRangeError('REFRIGERATION_NOT_CONVERGED', '牛顿迭代离开容器的两相适用区')
        raise devices.DeviceRangeError('REFRIGERATION_NOT_CONVERGED', f'隐式步未收敛（残差 {norm:.2e}）')

    def _integrate(self, step):
        """All substeps of `step` succeed before any state, counter or residual is committed."""
        if self.timestep.enabled:
            return self._integrate_adaptive(step)
        network = self.network
        x = self._vector(self.masses, self.energies, self.temperatures)
        counters, energy_residual = dict(self.counters), 0.
        done, h, halvings = 0., step, 0
        while done < step - 1e-12 * max(1., step):
            h = min(h, step - done)
            try:
                x_new, result = self._solve_at(x,h,self.time+done+h)
                masses, energies, temperatures = self._unpack(x_new)
                for v in network.vessels:
                    _device(v, devices.check_vessel, network.parameters[v], result['vessels'][v])
            except devices.DeviceRangeError as error:
                self._jacobian = None
                final = error.code in ('VESSEL_LEVEL_RANGE',) or halvings >= self.MAX_HALVINGS
                if final:
                    raise SolveFailed(error.code, f't={self.time + done + h:g}s {error}', error.instance_id,
                                      list(self.frames)) from error
                h, halvings = h / 2, halvings + 1
                continue
            stored_old = self._stored(*self._unpack(x))
            energy_residual += self._stored(masses, energies, temperatures) - stored_old - h * result['boundary_w']
            for key, power in self._powers(result).items():
                counters[key] = counters.get(key, 0.) + h * power
            x, done = x_new, done + h
            self.step_stats.fixed_step(h)
        self.masses, self.energies, self.temperatures = self._unpack(x)
        self.counters = counters
        self.energy_residual_j += energy_residual
        self.frame_residual_j += energy_residual
        return result

    # --- A2：可从任意 accepted vector 开始的无提交试算与误差接受控制 --------------------------
    def _check_vessels(self, result):
        for v in self.network.vessels:
            _device(v, devices.check_vessel, self.network.parameters[v], result['vessels'][v])

    def _error_estimate(self, x, x_full, x_fine, result_full, result_fine):
        """按类别归一化的步加倍局部误差估计：质量 kg、能量 J（相对冻结参考态）、温度 K，另查容器压力。"""
        network, config = self.network, self.timestep
        categories, references = [], []
        for v in network.vessels:
            categories += ['mass', 'energy']
            references += [0., self.energy_reference[v]]
        categories += ['temperature'] * len(self.temperatures)
        references += [0.] * len(self.temperatures)
        atol = {'mass': config.mass_atol_kg, 'energy': config.energy_atol_j,
                'temperature': config.temperature_atol_k}
        # 压力不是积分状态，由容器 (M,U) 反演；单独检查，避免能量中心化掩盖容器压力误差。
        pressure = {}
        for v in network.vessels:
            pressure[v] = (result_full['vessels'][v].pressure_pa, result_fine['vessels'][v].pressure_pa,
                           network.project.solver.pressure_tolerance_pa)
        return normalized_error(x, x_full, x_fine, categories=categories, atol=atol, rtol=config.rtol,
                                references=references, extra=pressure)

    def _trial_doubling(self, x, h):
        """从 accepted vector x 试算整步与两个半步；返回 (payload, ErrorEstimate)。

        失败或误差拒绝时把 Newton 扰动缓存恢复原状，accepted state 与账本均未被触碰。
        第二个半步确实从第一个半步的 x_mid 出发。
        """
        saved = (self._jacobian, self._cache)
        half = 0.5 * h
        start = self.time if self._trial_start_time is None else self._trial_start_time
        try:
            x_full, result_full = self._solve_at(x,h,start+h)
            self._check_vessels(result_full)
            x_mid, result_mid = self._solve_at(x,half,start+half)
            self._check_vessels(result_mid)
            x_fine, result_fine = self._solve_at(x_mid,half,start+h)
            self._check_vessels(result_fine)
        except devices.DeviceRangeError as range_error:
            self._jacobian, self._cache = saved
            raise TrialFailure(str(range_error)) from range_error
        error = self._error_estimate(x, x_full, x_fine, result_full, result_fine)
        payload = None
        if error.norm <= 1.:
            stored_x = self._stored(*self._unpack(x))
            stored_mid = self._stored(*self._unpack(x_mid))
            stored_fine = self._stored(*self._unpack(x_fine))
            residual = stored_mid - stored_x - half * result_mid['boundary_w']
            residual += stored_fine - stored_mid - half * result_fine['boundary_w']
            counters = {}
            for result in (result_mid, result_fine):
                for key, power in self._powers(result).items():
                    counters[key] = counters.get(key, 0.) + half * power
            payload = {'x':x_fine,'residual':residual,'counters':counters,'result':result_fine}
            self.last_trial = {'h': h, 'x_full': x_full, 'x_mid': x_mid, 'x_fine': x_fine,
                               'error_norm': error.norm}
            return payload, error
        # 误差超过 1：整步与半步试算都不提交，恢复缓存。
        self._jacobian, self._cache = saved
        self.last_trial = {'h': h, 'x_full': x_full, 'x_mid': x_mid, 'x_fine': x_fine, 'error_norm': error.norm}
        return None, error

    def _integrate_adaptive(self, step):
        """Keep error-accepted states and ledgers local until the complete segment succeeds."""
        masses, energies, temperatures = self.masses, self.energies, self.temperatures
        counters = dict(self.counters)
        residual, frame_residual = self.energy_residual_j, self.frame_residual_j
        caches = self._jacobian, self._cache, self.last_trial
        elapsed, final_result = 0., None

        def trial(h):
            x = self._vector(masses, energies, temperatures)
            self._trial_start_time = self.time+elapsed
            return self._trial_doubling(x, h)

        def accept(payload, h, error):
            nonlocal masses, energies, temperatures, residual, frame_residual, elapsed, final_result
            masses, energies, temperatures = self._unpack(payload['x'])
            for key, energy in payload['counters'].items():
                counters[key] = counters.get(key, 0.) + energy
            residual += payload['residual']
            frame_residual += payload['residual']
            elapsed += h
            final_result = payload['result']

        try:
            self._march_adaptive(step, trial, accept)
        except Exception:
            self._jacobian, self._cache, self.last_trial = caches
            raise
        finally:
            self._trial_start_time = None
        self.masses, self.energies, self.temperatures = masses, energies, temperatures
        self.counters = counters
        self.energy_residual_j, self.frame_residual_j = residual, frame_residual
        return final_result

    def initialize(self):
        if self.closed:
            raise StopIteration
        if self.module_adapter is not None and not self.frames:
            try:
                self.module_adapter.initialize()
            except BaseException:
                self.close()
                raise
        if not self.frames and self.duration is not None:
            self.diagnostics.extend(Diagnostic(code='SCHEDULE_EVENT_AFTER_RUN', severity='warning', field='events',
                message=f'事件 {e.id} 在 t={e.time_s:g}s，超出本次运行时长 {self.duration:g}s，不会执行')
                for e in self.network.events if e.time_s >= self.duration)
        return super().initialize()

    @contextmanager
    def _segment_transaction(self):
        if self.module_adapter is None:
            with super()._segment_transaction():
                yield
            return
        from ..module_execution import begin_module_step
        from ..runtime import RuntimeErrorBase
        self._module_step_id = begin_module_step(self.runners)
        self._module_transaction = None
        try:
            with super()._segment_transaction():
                try:
                    yield
                    self._module_transaction.promote()
                except RuntimeErrorBase as error:
                    failure = SolveFailed(error.code,str(error),None,list(self.frames))
                    if error.diagnostics:
                        failure.diagnostic = error.diagnostics[0].model_copy(update={'code':error.code})
                        failure.diagnostics = error.diagnostics
                    raise failure from error
        except Exception:
            if self._module_transaction is not None:
                self._module_transaction.discard()
            self.close()
            raise
        try:
            self._module_transaction.synchronize()
        except RuntimeErrorBase as error:
            if not self.frames or self.frames[-1].time_s<self.time:
                self.publish()
            self.close()
            failure = SolveFailed(error.code,str(error),None,list(self.frames))
            if error.diagnostics:failure.diagnostic=error.diagnostics[0]
            raise failure from error

    def _advance_heat(self, step):
        if self.module_adapter is None:
            return super()._advance_heat(step)
        result = self._integrate(step)
        for script in self.scripts.values():
            if script.pending:
                self.diagnostics.extend(Diagnostic.model_validate(d) for d in script.pending[0].get('diagnostics',[]))
                script.accept()
        self.time += step
        self._cache = self._cache_key(),result
        self._module_transaction = self.module_adapter.prepare(self._module_step_id,self.time,step,result)
        frame = self.snapshot()
        frame.variables.update(self.module_adapter.variables(result,self._module_transaction.candidates))
        RunFrame.model_validate_json(frame.model_dump_json())

    def advance(self):
        """ThermalSession.advance plus the schedule: due events apply before the control sample of that instant."""
        if self.closed:
            raise StopIteration
        if not self.frames:
            return self.initialize()
        if self.done:
            raise StopIteration
        target = (self.index + 1) * self.dt
        if self.duration is not None:
            target = min(target, self.duration)
        events = self.network.events
        while target - self.time > 1e-12 * max(1., target):
            with self._segment_transaction():
                while self.event_index < len(events) and events[self.event_index].time_s <= self.time + EPS:
                    apply_set_variable(self, events[self.event_index])
                    self.event_index += 1
                    self.events_applied += 1
                self._control()
                upcoming = [e.time_s - self.time for e in events[self.event_index:self.event_index + 1]]
                limit = self.timestep.max_step_s if self.timestep.enabled else self.network.project.solver.dynamic_step_s
                step = min([target - self.time, limit, *upcoming]
                           + [pid.next_s - self.time for pid in self.controllers.values()]
                           + [script.next_s - self.time for script in self.scripts.values()])
                if step <= 0:
                    raise CompilationError('THERMAL_STEP_INVALID', '制冷站控制时钟未推进')
                self._advance_heat(step)
        self.time = target
        self.index += 1
        return self.publish()

    def _control(self):
        """Skip the frame snapshot when no PID or script is due; their outputs are unchanged then."""
        due = any(r.next_s <= self.time + 1e-10 for r in self.scripts.values()) or \
            any(p.next_s <= self.time + 1e-10 for p in self.controllers.values())
        if due or not getattr(self, '_controlled', False):
            self._controlled = True
            super()._control()

    def _stored(self, masses, energies, temperatures):
        return sum(energies.values()) + sum(self.network.parameters[r]['heat_capacity_j_k'] * t for r, t in temperatures.items())

    def _powers(self, result):
        """Rates integrated into the cumulative `state.*_energy_j` counters."""
        powers = {}
        for iid, r in result['devices'].items():
            kind = self.network.kinds[iid]
            if kind in ('refrigerant_compressor', 'refrigerant_pump'):
                powers[(iid, 'electric_energy_j')] = r['electric_power_w']
            elif kind == 'evaporative_condenser':
                powers[(iid, 'heat_rejected_j')] = r['heat_rejection_w']
                powers[(iid, 'fan_energy_j')] = r['fan_power_w']
            elif kind == 'air_cooler':
                powers[(iid, 'cooling_energy_j')] = r['room_cooling_w']
                powers[(iid, 'fan_energy_j')] = r['fan_power_w']
            elif kind == 'cold_room':
                powers[(iid, 'external_energy_j')] = r['envelope_heat_w'] + self.network.parameters[iid]['heat_input_w']
            if iid in self.network.refrigeration_modules:
                powers[(iid,'transferred_mass_kg')] = r['mass_flow_kg_s']
        return powers

    def _cache_key(self):
        return (self.time,self.revision,tuple(self.masses.values()),tuple(self.energies.values()),tuple(self.temperatures.values()))

    def _current(self):
        key = self._cache_key()
        if self._cache is None or self._cache[0] != key:
            try:
                self._candidate_time = self.time
                self._cache = key, self._evaluate(self.masses, self.energies, self.temperatures)
            except devices.DeviceRangeError as error:
                raise SolveFailed(error.code, f't={self.time:g}s {error}', error.instance_id, list(self.frames)) from error
        return self._cache[1]

    def snapshot(self):
        network, result = self.network, self._current()
        values = {}
        for v in network.vessels:
            values.update(result['vessels'][v].variables(v))
            values[f'{v}.net_inflow_kg_s'] = result['dm'][v]
        exported = {'refrigerant_compressor': ('mass_flow_kg_s', 'shaft_power_w', 'electric_power_w',
                                               'discharge_temperature_k', 'pressure_ratio'),
                    'evaporative_condenser': ('heat_rejection_w', 'effective_ua_w_k', 'condensing_temperature_k', 'fan_power_w'),
                    'expansion_valve': ('mass_flow_kg_s', 'pressure_drop_pa', 'outlet_quality'),
                    'cascade_exchanger': ('heat_w', 'approach_k', 'evaporated_kg_s', 'condensed_kg_s'),
                    'refrigerant_pump': ('mass_flow_kg_s', 'pressure_rise_pa', 'electric_power_w'),
                    'air_cooler': ('refrigerant_heat_w', 'room_cooling_w', 'fan_power_w', 'supply_mass_flow_kg_s',
                                   'outlet_quality', 'evaporating_temperature_k')}
        for iid, r in result['devices'].items():
            kind = network.kinds[iid]
            values.update({f'{iid}.{key}': r[key] for key in exported.get(kind, ())})
        for room, temperature in self.temperatures.items():
            q, r = network.parameters[room], result['devices'][room]
            values.update({f'{room}.state.temperature_k': temperature, f'{room}.envelope_heat_w': r['envelope_heat_w'],
                           f'{room}.cooling_power_w': r['cooling_power_w'],
                           f'{room}.stored_energy_j': q['heat_capacity_j_k'] * (temperature - 273.15)})
        for (iid, key) in self._powers(result):
            values[f'{iid}.state.{key}'] = self.counters.get((iid, key), 0.)
        for iid, parameters in network.parameters.items():
            values.update({f'{iid}.param.{key}': value for key, value in parameters.items()
                           if isinstance(value, (int, float, bool, str))})
        for pid in self.controllers.values():
            values.update(pid.variables())
        for script in self.scripts.values():
            values.update(script.variables())
        if self.module_adapter is not None:
            values.update(self.module_adapter.variables(result))
        scope = Diagnostic(code='REFRIGERATION_STATION', severity='info',
            message='集总制冷站：压力只在饱和容器中，设备为容器状态的代数关系；不计管路压降、换热器持液与过冷/过热')
        envelope = [d.model_copy(update={'instance_id': iid}) for iid, r in result['devices'].items()
                    for d in r.get('diagnostics', ())]
        electric = sum(r.get('electric_power_w', 0.) + r.get('fan_power_w', 0.) for iid, r in result['devices'].items()
                       if network.kinds[iid] != 'cold_room')
        metrics = {'energy_residual_w': self.frame_residual_j / (self.time - self.published_time)
                   if self.time > self.published_time else 0.,
                   'energy_residual_j': self.energy_residual_j, 'storage_power_w': result['boundary_w'],
                   'electric_power_w': electric, 'events_applied': self.events_applied}
        metrics.update(self.step_stats.frame_metrics(adaptive=self.timestep.enabled,
                                                     fixed_step=self.network.project.solver.dynamic_step_s))
        for c, initial in enumerate(self.circuit_mass):
            metrics[f'mass_residual_kg_circuit{c}'] = sum(self.masses[v] for v in network.vessels
                                                          if network.circuit_of[v] == c) - initial
        return RunFrame(status='converged', valid=True, time_s=self.time, variables=values,
                        diagnostics=[*network.diagnostics, scope, *envelope, *self.diagnostics], metrics=metrics,
                        sequence=self.sequence, parameter_revision=self.revision)


def solve_station_steady(network):
    raise CompilationError('REFRIGERATION_DYNAMIC_REQUIRED', '制冷站的容器存量随时间变化，只能动态运行')
