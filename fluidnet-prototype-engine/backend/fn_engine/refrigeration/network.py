"""Pressure, mass and enthalpy graph solve with dynamic reservoir boundaries.

Two-phase resistance uses an explicitly homogeneous equilibrium mixture. Inventory
is owned by the host M/U vector, never by repeatedly evaluating an algebraic pipe.
"""
from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from scipy.optimize import brentq, least_squares

from ..compiler import CompilationError, DisjointSet
from ..solver import pipe_drop, pump_head
from .cycle import DeviceRangeError
from .devices import air_cooler_point
from .network_devices import NETWORK_KINDS
from .stream_devices import BRIDGES, LINES, RECUPERATOR, RECUPERATOR_PORTS, compressor_point, single_phase
from .vessel_ports import port_state

FLOW_PORTS = {**BRIDGES, 'refrigerant_compressor': ('suction', 'discharge'),
              'performance_compressor': ('suction', 'discharge'), 'expansion_valve': ('in0', 'out0'),
              'refrigerant_pump': ('in0', 'out0'), 'air_cooler': ('in0', 'out0'),
              'evaporative_condenser': ('in0', 'out0'), 'air_cooled_condenser': ('in0', 'out0'),
              **{kind: ('in0', 'out0') for kind in LINES | NETWORK_KINDS}}


@dataclass(frozen=True)
class Edge:
    key: str
    instance_id: str
    kind: str
    start: str
    end: str


@dataclass
class Component:
    edges: list
    nodes: list
    anchors: dict
    owners: dict


@dataclass
class Graph:
    components: list
    instance_ids: set
    owners: dict


def compile_network(kinds, nodes, ports, used):
    if not any(kind in NETWORK_KINDS for kind in kinds.values()):
        return None
    edges = []
    for iid, kind in kinds.items():
        pairs = list(RECUPERATOR_PORTS.items()) if kind == RECUPERATOR else [FLOW_PORTS[kind]] if kind in FLOW_PORTS else []
        if kind == 'frost_hotgas_cooler':
            hot = ((iid, 'hot_in') in used, (iid, 'hot_out') in used)
            if any(hot) and not all(hot):
                raise CompilationError('HOT_GAS_PATH_INCOMPLETE', '热气进口与凝液出口须同时连接', iid)
            if all(hot): pairs += [('hot_in', 'hot_out')]
        for a, b in pairs:
            key = iid + '#' + a.split('_')[0] if kind == RECUPERATOR else iid
            if kind == 'frost_hotgas_cooler' and a == 'hot_in':
                key = iid + '#hotgas'
            edges.append(Edge(key, iid, 'hotgas_path' if key.endswith('#hotgas') else kind, nodes.find((iid, a)), nodes.find((iid, b))))
    sets = DisjointSet({e.start for e in edges} | {e.end for e in edges})
    for edge in edges:
        sets.union(edge.start, edge.end)
    active = {sets.find(e.start) for e in edges if e.kind in NETWORK_KINDS}
    # A recuperator couples two hydraulic components thermally; both must be solved.
    for _ in range(2):
        shared = {e.instance_id for e in edges if e.kind in (RECUPERATOR, 'frost_hotgas_cooler', 'hotgas_path') and sets.find(e.start) in active}
        active.update(sets.find(e.start) for e in edges if e.instance_id in shared)
    grouped = {}
    for edge in edges:
        root = sets.find(edge.start)
        if root in active:
            grouped.setdefault(root, []).append(edge)
    anchors = {}
    for key in used:
        if kinds[key[0]] == 'saturated_vessel':
            root = nodes.find(key)
            if root in anchors:
                raise CompilationError('NETWORK_RESERVOIR_SHORT', '不同容器取口不能直接并成同一网络节点', key[0], key[1])
            anchors[root] = key
    components, owners = [], {}
    for group in grouped.values():
        node_ids = sorted({e.start for e in group} | {e.end for e in group})
        fixed = {node: anchors[node] for node in node_ids if node in anchors}
        if not fixed:
            raise CompilationError('NETWORK_PRESSURE_REFERENCE', '制冷管网连通部分必须连接物理库存容器', group[0].instance_id)
        # Owner is circuit metadata only; actual node pressure/enthalpy is solved below.
        owner = {node: anchor[0] for node, anchor in fixed.items()}
        frontier = list(owner)
        for node in frontier:
            for edge in group:
                other = edge.end if edge.start == node else edge.start if edge.end == node else None
                if other is not None and other not in owner:
                    owner[other] = owner[node]
                    frontier.append(other)
        owners.update(owner)
        components.append(Component(group, node_ids, fixed, owner))
    return Graph(components, {e.instance_id for c in components for e in c.edges},
                 {key: owners[nodes.find(key)] for key in ports if key in nodes.parent and nodes.find(key) in owners})


def mixture(service, pressure, enthalpy):
    state = service.state_ph(pressure, enthalpy)
    quality = state.quality
    if quality is not None and 1e-9 < quality < 1. - 1e-9:
        liquid, vapor = service.state_pq(pressure, 0.), service.state_pq(pressure, 1.)
        specific_volume = (1. - quality) / liquid.density_kg_m3 + quality / vapor.density_kg_m3
        viscosity = 1. / ((1. - quality) / liquid.viscosity_pa_s + quality / vapor.viscosity_pa_s)
        return state, 1. / specific_volume, viscosity
    viscosity = state.viscosity_pa_s
    if viscosity is None and quality is not None:
        viscosity = service.state_pq(pressure, 0. if quality < .5 else 1.).viscosity_pa_s
    if viscosity is None or viscosity <= 0. or state.density_kg_m3 <= 0.:
        raise DeviceRangeError('NETWORK_TRANSPORT_PROPERTIES', '实际流股缺少合法密度或黏度')
    return state, state.density_kg_m3, viscosity


def homogeneous_drop(service, parameters, mass, inlet_p, outlet_p, inlet_h, outlet_h=None):
    """Darcy mixture friction plus homogeneous acceleration; signed by actual flow."""
    if abs(mass) < 1e-14:
        return 0.
    outlet_h = inlet_h if outlet_h is None else outlet_h
    _, rho_in, _ = mixture(service, inlet_p, inlet_h)
    _, rho_out, _ = mixture(service, outlet_p, outlet_h)
    _, rho, viscosity = mixture(service, (inlet_p + outlet_p) / 2., (inlet_h + outlet_h) / 2.)
    area = math.pi * parameters['diameter_m'] ** 2 / 4.
    friction = pipe_drop({'length_m': parameters.get('length_m', 0.), 'diameter_m': parameters['diameter_m'],
                          'roughness_m': parameters.get('roughness_m', 0.)}, abs(mass), rho, viscosity)
    friction += parameters.get('loss_coefficient', 0.) * mass ** 2 / (2. * rho * area ** 2)
    acceleration = (abs(mass) / area) ** 2 * (1. / rho_out - 1. / rho_in)
    return math.copysign(1., mass) * (friction + acceleration)


def _component_point(component, network, service, vessels, temperatures, room_of, warm, exchanges, valve_evaluator, freeze_hydraulics=False):
    parameters = network.parameters
    fixed_p, fixed_h = {}, {}
    for node, (iid, port) in component.anchors.items():
        p, h, _ = port_state(parameters[iid], vessels[iid], port)
        fixed_p[node] = p
        # Every reservoir port supplies its own physical enthalpy when flow
        # leaves the vessel, including backflow through an inlet. Incoming
        # energy is still the upstream edge's outlet enthalpy in the M/U ledger.
        fixed_h[node] = h
    all_p = [v for v in fixed_p.values()]
    seed_p = sum(all_p) / len(all_p)
    seed_h = next(iter(fixed_h.values()), next(iter(vessels.values())).liquid_enthalpy_j_kg)
    free = [n for n in component.nodes if n not in fixed_p]
    enthalpies = {n: fixed_h.get(n, warm.get('h', {}).get(n, seed_h)) for n in component.nodes}
    # Seed every downstream node from a reservoir, including multi-edge suction
    # branches. A single pass from anchors leaves pumps seeded with return vapor.
    seeded = set(fixed_h)
    seed_pressures = dict(fixed_p)
    for _ in component.nodes:
        for edge in component.edges:
            if edge.end not in seeded and edge.start in seeded:
                if edge.end not in warm.get('h', {}): enthalpies[edge.end] = enthalpies[edge.start]
                seed_pressures[edge.end] = max(all_p) if edge.kind in ('enthalpy_compressor', 'refrigerant_compressor', 'performance_compressor') else seed_pressures[edge.start]
                seeded.add(edge.end)
    vector = np.array([warm.get('p', {}).get(n, seed_pressures.get(n, seed_p)) / 1e5 for n in free] +
                      [warm.get('m', {}).get(e.key, .1) for e in component.edges])
    closed = set()
    for edge in component.edges:
        p = parameters[edge.instance_id]
        if (edge.kind in ('enthalpy_valve', 'expansion_valve', 'refrigerant_network_valve') and p['opening_ratio'] == 0.
            or edge.kind in ('air_cooler', 'network_air_cooler', 'frost_hotgas_cooler') and (p['supply_valve_ratio'] == 0. or not p.get('_cooling_enabled', True))
            or edge.kind == 'hotgas_path' and not p.get('_hot_enabled', False)
            or edge.kind in ('refrigerant_compressor', 'enthalpy_compressor', 'performance_compressor')
               and (p['running'] < .5 or p['load_ratio'] == 0. or p.get('speed_ratio', 1.) == 0.)
            or edge.kind == 'refrigerant_pump' and (p['running'] < .5 or p['speed_ratio'] == 0.)):
            closed.add(edge.key)
    forward = {'refrigerant_compressor', 'enthalpy_compressor', 'performance_compressor',
               'refrigerant_pump', 'refrigerant_curve_pump', 'air_cooler', 'network_air_cooler', 'frost_hotgas_cooler', 'hotgas_path',
               'enthalpy_valve', 'expansion_valve', 'refrigerant_network_valve', 'refrigerant_check_valve'}
    blocked = set(closed)
    for _ in component.edges:
        degree = {n: [] for n in free}
        for edge in component.edges:
            if edge.key in blocked: continue
            for node in (edge.start, edge.end):
                if node in degree: degree[node].append(edge.key)
        leaves = {keys[0] for keys in degree.values() if len(keys) == 1}
        if not leaves: break
        blocked.update(leaves)
    # A branch ending at a closed cooler carries no flow. Its open regulating
    # valves equilibrate pressure; solving a sqrt(dp) flow law at exactly zero
    # instead creates a singular corner on every defrost transition.
    idle_valves = {e.key for e in component.edges if e.key in blocked and e.key not in closed and
                   e.kind in ('enthalpy_valve', 'expansion_valve', 'refrigerant_network_valve', 'refrigerant_check_valve')}
    free_columns = {node: i for i, node in enumerate(free)}
    lower = np.array([.001] * len(free) + [0. if e.kind in forward and e.key not in closed else -1000. for e in component.edges])
    mass_equations = {'enthalpy_valve', 'expansion_valve', 'refrigerant_network_valve', 'enthalpy_compressor',
                      'refrigerant_compressor', 'performance_compressor', 'refrigerant_pump', 'hotgas_path', 'refrigerant_check_valve'}
    equation_weights = np.array([1000. if e.kind in mass_equations and e.key not in idle_valves or e.key in closed else 1. for e in component.edges] + [1000.] * len(free))
    residual_norm = lambda values: float(np.max(np.abs(values) * equation_weights))
    for edge in component.edges:
        if edge.kind in ('enthalpy_compressor', 'refrigerant_compressor', 'performance_compressor') and edge.key not in closed and edge.start in fixed_p and edge.end in free_columns:
            lower[free_columns[edge.end]] = fixed_p[edge.start] / 1e5 * (1. + 1e-9)
    pump_signature = {e.key: (parameters[e.instance_id].get('running', 1.), parameters[e.instance_id].get('speed_ratio', 1.))
                      for e in component.edges if e.kind == 'refrigerant_curve_pump'}
    pump_changed = bool(warm) and warm.get('pumps') != pump_signature
    if pump_changed:
        # Restart a parallel pump pair on the appropriate side of its check
        # valves. Keeping zero standby flow as the initial guess at a duty trip
        # leaves the bounded nonlinear solve on the inactive branch's corner.
        groups = {}
        edge_indices = {edge.key: i for i, edge in enumerate(component.edges)}
        for edge in component.edges:
            if edge.kind == 'refrigerant_curve_pump': groups.setdefault(edge.start, []).append(edge)
        for start, pumps in groups.items():
            total = sum(max(0., vector[len(free) + edge_indices[e.key]]) for e in pumps)
            active = [e for e in pumps if pump_signature[e.key][0] >= .5 and pump_signature[e.key][1] > 0.]
            carrying = active or pumps
            pin = fixed_p[start] if start in fixed_p else vector[free_columns[start]] * 1e5
            _, rho, _ = mixture(service, pin, enthalpies[start])
            for edge in pumps:
                p = parameters[edge.instance_id]
                flow = total / len(carrying) if edge in carrying else 0.
                if edge in active:
                    flow = min(flow, p['head_curve'][-1][0] * p['speed_ratio'] * rho / 3600.)
                vector[len(free) + edge_indices[edge.key]] = flow
                if edge in active:
                    rise = rho * 9.80665 * pump_head(p['head_curve'], flow / rho * 3600., p['speed_ratio'])
                else:
                    area = math.pi * p['diameter_m'] ** 2 / 4.
                    rise = -p['stopped_loss_coefficient'] * flow**2 / (2. * rho * area**2)
                if edge.end in free_columns: vector[free_columns[edge.end]] = (pin + rise) / 1e5
                for check in component.edges:
                    if check.kind == 'refrigerant_check_valve' and check.start == edge.end:
                        vector[len(free) + edge_indices[check.key]] = flow
                        if flow and check.end in free_columns:
                            cp = parameters[check.instance_id]
                            drop = cp['cracking_pressure_pa'] + 1e5 * (3600. * flow / cp['kv_m3_h'])**2 / (1000. * rho)
                            vector[free_columns[check.end]] = (pin + rise - drop) / 1e5

    # Active curve pumps use volume flow as their unknown, so the optimizer stays
    # inside the declared curve even when liquid density changes with pressure.
    # Other branches keep mass-flow unknowns; balances and cached flows remain kg/s.
    edge_columns = {edge.key: len(free) + i for i, edge in enumerate(component.edges)}
    volume_pumps = {edge.key: edge for edge in component.edges if edge.kind == 'refrigerant_curve_pump'
                    and parameters[edge.instance_id].get('running', 1.) >= .5
                    and parameters[edge.instance_id].get('speed_ratio', 1.) > 0.}
    volume_layout = tuple(sorted(volume_pumps))
    upper = np.full(len(vector), 1000.)
    for key, edge in volume_pumps.items():
        pin = fixed_p[edge.start] if edge.start in fixed_p else vector[free_columns[edge.start]] * 1e5
        _, density, _ = mixture(service, pin, enthalpies[edge.start])
        column = edge_columns[key]
        upper[column] = parameters[edge.instance_id]['head_curve'][-1][0] * parameters[edge.instance_id]['speed_ratio']
        vector[column] = min(max(0., vector[column] / density * 3600.), upper[column])

    def physical_mass(edge, x, pressures):
        if edge.key in closed:
            return 0.
        value = x[edge_columns[edge.key]]
        if edge.key in volume_pumps:
            _, density, _ = mixture(service, pressures[edge.start], enthalpies[edge.start])
            return value * density / 3600.
        return value

    @lru_cache(maxsize=16384)
    def edge_point(edge, start_p, end_p, q, hin, final):
        iid, kind, p = edge.instance_id, edge.kind, parameters[edge.instance_id]
        upstream, downstream = (edge.start, edge.end) if q >= 0. else (edge.end, edge.start)
        pin, pout = (start_p, end_p) if q >= 0. else (end_p, start_p)
        state, rho, mu = mixture(service, pin, hin)
        hout, heat, power, room_cooling = hin, 0., 0., None
        signed_drop = 0.
        affine = 1.
        extra = {}
        equation = None
        if kind in ('enthalpy_compressor', 'refrigerant_compressor', 'performance_compressor'):
            if q < -1e-10:
                raise DeviceRangeError('NETWORK_COMPRESSOR_DIRECTION', '压缩机不能反向流动', iid)
            if edge.key in closed:
                expected, hout, shaft, electric = 0., hin, 0., 0.
            elif kind == 'performance_compressor':
                from .performance_compressor import compressor_point as mapped_compressor
                suction, phase = single_phase(service, pin, hin)
                if phase not in ('gas', 'supercritical_gas'):
                    raise DeviceRangeError('NETWORK_COMPRESSOR_PHASE', '性能压缩机需要实际气态吸气', iid)
                mapped = mapped_compressor(service, p, pin, pout, check=final, inlet_state=suction)
                expected, hout, shaft, electric = (mapped[k] for k in
                    ('mass_flow_kg_s', 'discharge_enthalpy_j_kg', 'shaft_power_w', 'electric_power_w'))
                extra.update(mapped)
            else:
                expected, hout, shaft, electric = compressor_point(service, p, pin, hin, pout)
            equation = q - expected
            power = shaft
            extra.update(shaft_power_w=shaft, electric_power_w=electric,
                         suction_enthalpy_j_kg=hin, discharge_enthalpy_j_kg=hout,
                         pressure_ratio=pout / pin, discharge_temperature_k=service.state_ph(pout, hout).temperature_k)
        elif kind in ('enthalpy_valve', 'expansion_valve', 'refrigerant_network_valve', 'refrigerant_check_valve'):
            if kind in ('enthalpy_valve', 'expansion_valve') and edge.key not in closed:
                liquid, phase = single_phase(service, pin, hin)
                if phase != 'liquid':
                    raise DeviceRangeError('NETWORK_VALVE_PHASE', '液相节流阀入口必须为液体', iid)
                rho = liquid.density_kg_m3
            difference = start_p - end_p - p.get('cracking_pressure_pa', 0.)
            expected = p['kv_m3_h'] * p.get('opening_ratio', 1.) / 3600. * math.sqrt(max(0., 1000. * rho * difference / 1e5))
            if iid in network.refrigeration_modules:
                source = vessels[component.owners[edge.start]]
                from dataclasses import replace
                source = replace(source, pressure_pa=pin, temperature_k=state.temperature_k,
                                 liquid_enthalpy_j_kg=hin, liquid_density_kg_m3=rho)
                destination = replace(source, pressure_pa=pout)
                expected = valve_evaluator(iid, service, p, source, destination)['mass_flow_kg_s']
            equation = q - expected
            if kind in ('refrigerant_check_valve', 'refrigerant_network_valve') and edge.key not in closed and not final:
                # Enforce q >= 0, gap >= 0 and q*gap = 0 without the square-root
                # kink at opening. A closed standby branch can then open when
                # the duty pump stops. Final checks use the original Kv law.
                gap = ((3600. * q / (p['kv_m3_h'] * p.get('opening_ratio', 1.))) ** 2 / (1000. * rho)
                       - difference / 1e5)
                equation = math.hypot(q, gap) - q - gap
            if edge.key in idle_valves:
                equation = (start_p - end_p) / 1e5
        elif kind in ('refrigerant_curve_pump', 'refrigerant_pump'):
            extra.update(electric_power_w=0., pressure_rise_pa=0.)
            if p.get('running', 1.) < .5 or p.get('speed_ratio', 1.) == 0.:
                area = math.pi * p.get('diameter_m', .04) ** 2 / 4.
                signed_drop = p.get('stopped_loss_coefficient', 5.) * q * abs(q) / (2. * rho * area ** 2)
                if kind == 'refrigerant_curve_pump': extra['pressure_rise_pa'] = -signed_drop
            else:
                if q < -1e-10 or final and (state.quality is not None and state.quality > 1e-8 or state.phase not in ('liquid', 'twophase', 'supercritical_liquid')):
                    raise DeviceRangeError('NETWORK_PUMP_PHASE', '制冷剂液泵必须正向输送液体', iid)
                if kind == 'refrigerant_pump':
                    equation = q - p['rated_mass_flow_kg_s'] * p['speed_ratio']
                    rise = p['rated_pressure_rise_pa'] * p['speed_ratio'] ** 2
                else:
                    flow_m3_h = max(q, 0.) / rho * 3600.
                    if final and flow_m3_h > p['head_curve'][-1][0] * p['speed_ratio'] + 1e-9:
                        raise DeviceRangeError('NETWORK_PUMP_CURVE_RANGE', '液泵工作点超出声明曲线', iid)
                    rise = rho * 9.80665 * pump_head(p['head_curve'], flow_m3_h, p['speed_ratio'])
                    signed_drop = -rise
                power = max(0., q) * rise / rho / p['efficiency_ratio']
                hout = hin + power / q if q > 1e-14 else hin
                extra.update(electric_power_w=power, pressure_rise_pa=rise)
        elif kind in ('network_air_cooler', 'air_cooler', 'frost_hotgas_cooler'):
            if q < -1e-10:
                raise DeviceRangeError('NETWORK_COOLER_DIRECTION', '泵供液冷风机不支持反向流', iid)
            point = air_cooler_point(service, p, min(pin, pout), temperatures[room_of[iid]], max(q, 0.))
            fan = point['fan_power_w']
            fan_ratio = p['fan_ratio'] if p.get('running', 1.) >= .5 else 0.
            ua = p['ua_w_k'] * (p['natural_ua_ratio'] + (1. - p['natural_ua_ratio']) * fan_ratio)
            available = max(0., ua * (temperatures[room_of[iid]] - service.saturation_t(min(pin, pout))))
            outlet_limit = service.state_pq(pout, p['max_outlet_quality']).enthalpy_j_kg
            oil_heat = sum(ua * (t - service.saturation_t(min(pin, pout))) for _, t, ua in p.get('_oil_terms', []))
            air_heat = available
            if kind == 'frost_hotgas_cooler':
                surface = p['_surface_temperature_k']
                air_heat = p['_air_ua_w_k'] * (p['natural_ua_ratio'] + (1. - p['natural_ua_ratio']) * fan_ratio) * (temperatures[room_of[iid]] - surface)
                available = max(0., p['refrigerant_contact_ua_w_k'] * p.get('_contact_factor', 1.) * (surface - service.saturation_t(min(pin, pout))))
            heat = min(max(0., available + oil_heat), max(q, 0.) * max(0., outlet_limit - hin))
            if not p.get('_cooling_enabled', True): heat = 0.
            actual_oil = heat * oil_heat / (available + oil_heat) if available + oil_heat > 0. else 0.
            extra['oil_heat_w'] = actual_oil
            if kind == 'frost_hotgas_cooler': extra['air_sensible_heat_w'] = air_heat
            if p['supply_valve_ratio'] == 0. or not p.get('_cooling_enabled', True):
                equation = q
                heat = 0.
            else:
                resistance = {'diameter_m': p.get('diameter_m', .025),
                              'loss_coefficient': p.get('loss_coefficient', 10.) / p['supply_valve_ratio'] ** 2}
                hout = hin + heat / q if q > 1e-14 else hin
                signed_drop = homogeneous_drop(service, resistance, q, pin, pout, hin, hout)
                if heat < available - 1e-8 and q > 1e-14 and outlet_limit >= hin:
                    affine = 0.
            hout = hin + heat / q if q > 1e-14 else hin
            room_cooling = (air_heat if kind == 'frost_hotgas_cooler' else heat - actual_oil) - fan
            power = fan
            extra.update(refrigerant_heat_w=heat, room_cooling_w=room_cooling,
                         fan_power_w=fan, supply_mass_flow_kg_s=max(q, 0.),
                         evaporating_temperature_k=service.saturation_t(min(pin, pout)))
        elif kind == 'hotgas_path':
            expected = p['hot_gas_kv_m3_h'] / 3600. * math.sqrt(max(0., 1000. * rho * (pin - pout) / 1e5)) if edge.key not in closed else 0.
            equation = q - expected
            if edge.key not in closed and q > 1e-14:
                liquid_h = service.state_pq(pout, 0.).enthalpy_j_kg
                heat = -min(max(0., p['hot_gas_ua_w_k'] * (state.temperature_k - p['_surface_temperature_k'])), q * max(0., hin - liquid_h))
                hout = hin + heat / q
            extra['hot_gas_heat_w'] = -heat
        elif kind == 'compressor_oil_system':
            if abs(q) > 1e-14:
                capacity = abs(q) * max(state.specific_heat_j_kg_k or 2000., 1.)
                heat = capacity * (p['_oil_temperature_k'] - state.temperature_k) * (-math.expm1(-p['gas_contact_ua_w_k'] / capacity))
                hout = hin + heat / abs(q)
            signed_drop = homogeneous_drop(service, p, q, pin, pout, hin, hout)
        elif kind == RECUPERATOR:
            side = edge.key.split('#')[1]
            heat = exchanges.get(iid, 0.) * (-1. if side == 'hot' else 1.)
            hout = hin + heat / abs(q) if abs(q) > 1e-14 else hin
            single_phase(service, pout, hout)
            extra['capacity_w_k'] = abs(q) * state.specific_heat_j_kg_k
        elif kind not in ('evaporative_condenser', 'air_cooled_condenser'):
            if kind in LINES:
                single_phase(service, pin, hin)
            ambient = vessels[network.vessel(iid, 'shell_in')].temperature_k if kind == 'immersed_tube_bundle' else p['ambient_temperature_k']
            if abs(q) > 1e-14:
                heat = p.get('heat_loss_ua_w_k', 0.) * (ambient - state.temperature_k)
                if state.specific_heat_j_kg_k and not (state.quality is not None and 0. < state.quality < 1.):
                    capacity = abs(q) * state.specific_heat_j_kg_k
                    heat = capacity * (ambient - state.temperature_k) * (-math.expm1(-p.get('heat_loss_ua_w_k', 0.) / capacity))
                    affine = math.exp(-p.get('heat_loss_ua_w_k', 0.) / capacity)
                hout = hin + heat / abs(q)
            if kind in LINES:
                single_phase(service, pout, hout)
            signed_drop = homogeneous_drop(service, p, q, pin, pout, hin, hout)
            power = heat if kind != 'immersed_tube_bundle' else 0.
        drop = start_p - end_p
        if edge.key in closed:
            equation = 0.
        outlet = service.state_ph(pout, hout)
        values = {'mass_flow_kg_s': q, 'inlet_pressure_pa': pin, 'outlet_pressure_pa': pout,
            'inlet_enthalpy_j_kg': hin, 'outlet_enthalpy_j_kg': hout, 'heat_w': heat,
            'pressure_drop_pa': drop, 'outlet_quality': outlet.quality,
            'inlet_temperature_k': state.temperature_k, 'outlet_temperature_k': outlet.temperature_k,
            '_external_w': power, '_upstream': upstream, '_downstream': downstream,
            '_affine_a': affine, '_affine_c': hout - affine * hin, **extra}
        return (equation if equation is not None else (drop - signed_drop) / 1e5), values

    def rows(x, final=False):
        pressures = {**fixed_p, **{n: x[i] * 1e5 for i, n in enumerate(free)}}
        mass = {edge.key: physical_mass(edge, x, pressures) for edge in component.edges}
        result = {}
        pressure_residual = []
        balance = dict.fromkeys(free, 0.)
        for edge_index, edge in enumerate(component.edges):
            q = mass[edge.key]
            upstream = edge.start if q >= 0. else edge.end
            hin = enthalpies[upstream]
            equation, values = edge_point(edge, pressures[edge.start], pressures[edge.end], q, hin, final)
            pressure_residual.append(x[len(free) + edge_index] if edge.key in closed else equation)
            if edge.start in balance: balance[edge.start] -= q
            if edge.end in balance: balance[edge.end] += q
            result[edge.key] = dict(values)
        return np.array(pressure_residual + list(balance.values())), pressures, mass, result

    # Acyclic stream graphs can transport enthalpy exactly in flow order for
    # every hydraulic trial. This eliminates an entire set of algebraic unknowns
    # and avoids ill-conditioned energy equations at idle parallel branches.
    def transported_rows(x, final=False):
        pressures = {**fixed_p, **{n: x[i] * 1e5 for i, n in enumerate(free)}}
        mass = {e.key: 0. if e.key in closed else x[len(free) + i] for i, e in enumerate(component.edges)}
        incoming = {n: [] for n in component.nodes}
        outgoing = {n: [] for n in component.nodes}
        for edge in component.edges:
            upstream, downstream = (edge.start, edge.end) if mass[edge.key] >= 0. else (edge.end, edge.start)
            incoming[downstream].append(edge)
            outgoing[upstream].append(edge)
        waiting = {n: len(incoming[n]) for n in free}
        ready = list(fixed_h) + [n for n in free if not waiting[n]]
        processed, points, equations = set(), {}, {}
        for node in ready:
            if node in processed: continue
            processed.add(node)
            if node not in fixed_h:
                flows = [(abs(mass[e.key]), points[e.key]['outlet_enthalpy_j_kg']) for e in incoming[node]]
                total = sum(q for q, _ in flows)
                if total > 1e-12:
                    enthalpies[node] = sum(q * h for q, h in flows) / total
            for edge in outgoing[node]:
                if edge.key in volume_pumps:
                    mass[edge.key] = physical_mass(edge, x, pressures)
                q = mass[edge.key]
                equation, point = edge_point(edge, pressures[edge.start], pressures[edge.end], q, enthalpies[node], final)
                equations[edge.key], points[edge.key] = equation, dict(point)
                downstream = point['_downstream']
                if downstream in waiting:
                    waiting[downstream] -= 1
                    if waiting[downstream] == 0: ready.append(downstream)
        if len(points) != len(component.edges):
            raise DeviceRangeError('NETWORK_TRANSPORT_CYCLE', '当前流向含无库存热循环，需要迭代焓求解')
        balance = dict.fromkeys(free, 0.)
        residual = []
        for i, edge in enumerate(component.edges):
            q = mass[edge.key]
            residual.append(x[len(free) + i] if edge.key in closed else equations[edge.key])
            if edge.start in balance: balance[edge.start] -= q
            if edge.end in balance: balance[edge.end] += q
        return np.array(residual + list(balance.values())), pressures, mass, points

    direct_transport = len(component.edges) >= 20
    if direct_transport:
        try:
            transported_rows(vector)
        except DeviceRangeError as error:
            if error.code != 'NETWORK_TRANSPORT_CYCLE': raise
            direct_transport = False
    if direct_transport:
        if freeze_hydraulics:
            _, pressures, mass, points = transported_rows(vector)
            return points, {'p': pressures, 'h': dict(enthalpies), 'm': mass}, 0., 0.
        vector = np.minimum(upper, np.maximum(vector, lower))
        cached_jac = (warm.get('transport_jac') if warm.get('closed') == closed and not pump_changed
                      and warm.get('pump_volume_variables') == volume_layout else None)
        jac = cached_jac.copy() if cached_jac is not None else None
        previous_norm = math.inf
        for _ in range(24):
            base = transported_rows(vector)[0]
            norm = residual_norm(base)
            if norm < 1e-9: break
            if jac is None or norm > .5 * previous_norm:
                jac = np.empty((len(vector), len(vector)))
                for column in range(len(vector)):
                    delta = 1e-7 * max(1., abs(vector[column]))
                    probe = vector.copy(); probe[column] += delta
                    jac[:, column] = (transported_rows(probe)[0] - base) / delta
            previous_norm = norm
            try:
                direction = np.linalg.solve(jac, base)
            except np.linalg.LinAlgError:
                direction = np.linalg.lstsq(jac, base, rcond=1e-13)[0]
            for _ in range(16):
                candidate = np.minimum(upper, np.maximum(lower, vector - direction))
                try:
                    trial_residual = transported_rows(candidate)[0]
                    improving = residual_norm(trial_residual) < norm
                except (DeviceRangeError, ValueError):
                    improving = False
                if improving:
                    displacement = candidate - vector
                    length = float(displacement @ displacement)
                    if length > 1e-24:
                        jac += np.outer(trial_residual - base - jac @ displacement, displacement) / length
                    vector = candidate
                    break
                direction *= .5
            else: break
        if residual_norm(transported_rows(vector)[0]) >= 1e-9:
            solution = least_squares(lambda v: transported_rows(v)[0] * equation_weights, vector,
                bounds=(lower, upper), x_scale='jac', method='dogbox',
                ftol=1e-13, xtol=1e-13, gtol=1e-13, max_nfev=160)
            vector = solution.x
        residual, pressures, mass, points = transported_rows(vector, True)
        mass_error = max([abs(residual[i]) for i, edge in enumerate(component.edges) if edge.kind in mass_equations and edge.key not in idle_valves or edge.key in closed]
                         + [abs(v) for v in residual[len(component.edges):]] + [0.])
        pressure_error = max([abs(residual[i]) * 1e5 for i, edge in enumerate(component.edges) if (edge.kind not in mass_equations or edge.key in idle_valves) and edge.key not in closed] + [0.])
        tolerance = network.project.solver
        if mass_error > tolerance.mass_tolerance_kg_s or pressure_error > tolerance.pressure_tolerance_pa:
            raise DeviceRangeError('NETWORK_NOT_CONVERGED', f'管网残差 {pressure_error:g} Pa / {mass_error:g} kg/s')
        return points, {'p': pressures, 'h': dict(enthalpies), 'm': mass,
                        'transport_jac': jac, 'closed': closed, 'pumps': pump_signature,
                        'pump_volume_variables': volume_layout}, pressure_error, mass_error

    outer_error = math.inf
    previous_outer = math.inf
    for iteration in range(60):
        if freeze_hydraulics:
            pass
        elif not free:
            for index, edge in enumerate(component.edges):
                if edge.key in closed:
                    vector[index] = 0.
                    continue
                def scalar(value):
                    candidate = vector.copy(); candidate[index] = value
                    return rows(candidate)[0][index]
                if abs(scalar(0.)) < 1e-16:
                    vector[index] = 0.
                else:
                    try:
                        vector[index] = brentq(scalar, float(lower[index]), float(upper[index]), xtol=1e-13)
                    except ValueError as error:
                        if getattr(error, 'code', None) is not None:
                            raise
                        raise DeviceRangeError('NETWORK_NOT_CONVERGED',
                            '单支路在声明的求解范围内没有有效工作点', edge.instance_id) from error
        else:
            # A warm network normally needs only a few Newton corrections. Local
            # edge derivatives avoid reevaluating unrelated equipment; the bounded
            # least-squares path remains the fallback for difficult initial guesses.
            vector = np.minimum(upper, np.maximum(vector, lower))
            for _ in range(12):
                base, pressures, mass, values = rows(vector)
                norm = residual_norm(base)
                if norm < 1e-10: break
                jac = np.zeros((len(vector), len(vector)))
                if volume_pumps:
                    # m = rho(p,h) * V / 3600 couples pressure and flow columns.
                    # Differentiate the full physical rows in these coordinates.
                    for column in range(len(vector)):
                        delta = min(1e-6 * max(1., abs(vector[column])), .5 * (upper[column]-lower[column]))
                        if vector[column] + delta > upper[column]: delta = -delta
                        probe = vector.copy(); probe[column] += delta
                        jac[:, column] = (rows(probe)[0]-base) / delta
                else:
                    for i, edge in enumerate(component.edges):
                        flow_column = len(free) + i
                        if edge.key in closed:
                            jac[i, flow_column] = 1.
                            continue
                        q = mass[edge.key]
                        hin = enthalpies[edge.start if q >= 0. else edge.end]
                        start_p, end_p = pressures[edge.start], pressures[edge.end]
                        delta_q = 1e-6 * max(1., abs(q))
                        jac[i, flow_column] = (edge_point(edge, start_p, end_p, q + delta_q, hin, False)[0] - base[i]) / delta_q
                        for node, sign in ((edge.start, -1.), (edge.end, 1.)):
                            if node not in free_columns: continue
                            col = free_columns[node]
                            delta_p = 1e-6 * max(1., abs(vector[col]))
                            a, b = (start_p + delta_p * 1e5, end_p) if node == edge.start else (start_p, end_p + delta_p * 1e5)
                            jac[i, col] = (edge_point(edge, a, b, q, hin, False)[0] - base[i]) / delta_p
                            jac[len(component.edges) + col, flow_column] = sign
                try:
                    direction = np.linalg.solve(jac, base)
                except np.linalg.LinAlgError:
                    break
                for _ in range(12):
                    candidate = np.minimum(upper, np.maximum(lower, vector - direction))
                    try:
                        improving = residual_norm(rows(candidate)[0]) < norm
                    except (DeviceRangeError, ValueError):
                        improving = False
                    if improving:
                        vector = candidate
                        break
                    direction *= .5
                else: break
            if residual_norm(rows(vector)[0]) >= 1e-10:
                solution = least_squares(lambda x: rows(x)[0] * equation_weights, vector, x_scale='jac', method='dogbox',
                                         bounds=(lower, upper),
                                         ftol=1e-12, xtol=1e-12, gtol=1e-13, max_nfev=300)
                vector = solution.x
        # Snap the inactive side of a one-way valve to its exact constitutive
        # zero. Bound-constrained solvers otherwise leave ~1e-10 kg/s, which can
        # spuriously mix enthalpy into a stopped pump's isolated discharge node.
        _, pressures, _, _ = rows(vector)
        inactive = set(closed)
        for i, edge in enumerate(component.edges):
            if edge.kind == 'refrigerant_check_valve' and pressures[edge.start] - pressures[edge.end] <= parameters[edge.instance_id]['cracking_pressure_pa']:
                inactive.add(edge.key)
        # An unanchored dead-end carries exactly no mass. Propagate closed check
        # valves through the idle pump branch instead of transporting roundoff.
        for _ in component.edges:
            degree = dict.fromkeys(free, [])
            for edge in component.edges:
                if edge.key in inactive: continue
                for node in (edge.start, edge.end):
                    if node in degree: degree[node] = degree[node] + [edge.key]
            leaves = {edges[0] for edges in degree.values() if len(edges) == 1}
            if not leaves: break
            inactive.update(leaves)
        for i, edge in enumerate(component.edges):
            if edge.key in inactive: vector[len(free) + i] = 0.
        residual, pressures, mass, result = rows(vector)
        incoming = {n: [] for n in component.nodes}
        for values in result.values():
            if abs(values['mass_flow_kg_s']) > 1e-14:
                incoming[values['_downstream']].append((abs(values['mass_flow_kg_s']), values['outlet_enthalpy_j_kg']))
        unknown_h = [node for node in component.nodes if node not in fixed_h]
        columns = {node: index for index, node in enumerate(unknown_h)}
        matrix, rhs = np.zeros((len(columns), len(columns))), np.zeros(len(columns))
        for node, index in columns.items():
            total = sum(m for m, _ in incoming[node])
            if total < 1e-12:
                matrix[index, index] = 1.; rhs[index] = enthalpies[node]
            else:
                matrix[index, index] = total
        for values in result.values():
            downstream, upstream = values['_downstream'], values['_upstream']
            mass_flow = abs(values['mass_flow_kg_s'])
            if downstream not in columns or mass_flow < 1e-12: continue
            index = columns[downstream]
            a, c = values['_affine_a'], values['_affine_c']
            rhs[index] += mass_flow * c
            if upstream in fixed_h:
                rhs[index] += mass_flow * a * fixed_h[upstream]
            else:
                matrix[index, columns[upstream]] -= mass_flow * a
        try:
            solved_h = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError as error:
            raise DeviceRangeError('NETWORK_THERMAL_REFERENCE', '有流动的热回路缺少焓参考') from error
        targets = dict(zip(unknown_h, solved_h))
        outer_error = max((abs(h - enthalpies[n]) for n, h in targets.items()), default=0.)
        if outer_error <= 1e-7:
            enthalpies.update(targets)
            break
        weight = .5 if outer_error > previous_outer else 1.
        for n, h in targets.items(): enthalpies[n] += weight * (h - enthalpies[n])
        previous_outer = outer_error
    else:
        raise DeviceRangeError('NETWORK_ENTHALPY_NOT_CONVERGED', f'图式管网焓输运未收敛，误差{outer_error:g} J/kg')
    residual, pressures, mass, result = rows(vector, final=True)
    tolerance = network.project.solver
    # Mass-form equations (valves/forced machines) are also checked against the mass tolerance.
    pressure_error, mass_error = 0., max((abs(v) for v in residual[len(component.edges):]), default=0.)
    for i, edge in enumerate(component.edges):
        if edge.key not in idle_valves and edge.kind in ('enthalpy_valve', 'expansion_valve', 'refrigerant_network_valve',
                         'enthalpy_compressor', 'refrigerant_compressor', 'performance_compressor', 'refrigerant_pump', 'hotgas_path',
                         'refrigerant_check_valve'):
            mass_error = max(mass_error, abs(residual[i]))
        else:
            pressure_error = max(pressure_error, abs(residual[i]) * 1e5)
    if not freeze_hydraulics and (pressure_error > tolerance.pressure_tolerance_pa or mass_error > tolerance.mass_tolerance_kg_s):
        raise DeviceRangeError('NETWORK_NOT_CONVERGED', f'图式管网压力/质量残差{pressure_error:g} Pa / {mass_error:g} kg/s')
    return result, {'p': pressures, 'h': enthalpies, 'm': mass, 'pumps': pump_signature,
                    'pump_volume_variables': volume_layout}, pressure_error, mass_error


def evaluate_network(network, services, vessels, temperatures, warm=None, valve_evaluator=None, freeze_hydraulics=False):
    from .stream_devices import counterflow_heat
    graph = network.hydraulic_graph
    warm = warm or {}
    groups = network.room_cooler_groups
    room_of = {c: room for room, coolers in groups.items() for c in coolers}
    exchanges = {iid: 0. for iid in graph.instance_ids if network.kinds[iid] == RECUPERATOR}
    caches, results = {}, {}
    for _ in range(50):
        p_error, m_error = 0., 0.
        for index, component in enumerate(graph.components):
            service = services[next(iter(component.anchors.values()))[0]]
            values, cache, pe, me = _component_point(component, network, service, vessels, temperatures,
                room_of, warm.get(index, {}), exchanges, valve_evaluator, freeze_hydraulics)
            results.update(values); caches[index] = cache
            p_error, m_error = max(p_error, pe), max(m_error, me)
        targets = {}
        for iid in exchanges:
            a, b = results[iid + '#hot'], results[iid + '#cold']
            targets[iid] = counterflow_heat(network.parameters[iid]['ua_w_k'], a['capacity_w_k'], b['capacity_w_k'],
                                            a['inlet_temperature_k'], b['inlet_temperature_k'])
        if all(abs(q - exchanges[iid]) < 1e-4 for iid, q in targets.items()): break
        exchanges = {iid: .5 * exchanges[iid] + .5 * q for iid, q in targets.items()}
        warm = caches
    else:
        raise DeviceRangeError('NETWORK_RECUPERATOR_NOT_CONVERGED', '图式回热器联算未收敛')
    dm, du = dict.fromkeys(network.vessels, 0.), dict.fromkeys(network.vessels, 0.)
    boundary = 0.
    for component in graph.components:
        for edge in component.edges:
            values = results[edge.key]
            m = abs(values['mass_flow_kg_s'])
            for node, sign, h in ((values['_upstream'], -1., values['inlet_enthalpy_j_kg']),
                                  (values['_downstream'], 1., values['outlet_enthalpy_j_kg'])):
                if node in component.anchors:
                    reservoir = component.anchors[node][0]
                    dm[reservoir] += sign * m; du[reservoir] += sign * m * h
            boundary += values.pop('_external_w')
            if edge.kind == 'hotgas_path':
                ports = ('hot_in', 'hot_out')
            elif edge.kind == RECUPERATOR:
                inlet = edge.key.split('#')[1] + '_in'
                ports = (inlet, RECUPERATOR_PORTS[inlet])
            else:
                ports = FLOW_PORTS[edge.kind]
            for port, node, signed_mass in ((ports[0], edge.start, values['mass_flow_kg_s']),
                                             (ports[1], edge.end, -values['mass_flow_kg_s'])):
                upstream = node == values['_upstream']
                values[port + '.mass_flow_kg_s'] = signed_mass
                values[port + '.pressure_pa'] = values['inlet_pressure_pa' if upstream else 'outlet_pressure_pa']
                values[port + '.enthalpy_j_kg'] = values['inlet_enthalpy_j_kg' if upstream else 'outlet_enthalpy_j_kg']
                values[port + '.temperature_k'] = values['inlet_temperature_k' if upstream else 'outlet_temperature_k']
            values.pop('_upstream'); values.pop('_downstream')
            values.pop('_affine_a'); values.pop('_affine_c')
            if edge.kind == 'immersed_tube_bundle':
                shell = network.vessel(edge.instance_id, 'shell_in')
                du[shell] -= values['heat_w']
                values['shell_heat_w'] = -values['heat_w']
    for iid in graph.instance_ids:
        hot = results.pop(iid + '#hotgas', None)
        if hot is not None:
            results[iid]['hot_gas_heat_w'] = hot['hot_gas_heat_w']
            results[iid].update({'hot_' + k: v for k, v in hot.items() if k != 'hot_gas_heat_w'})
            results[iid].update({k: v for k, v in hot.items() if k.startswith(('hot_in.', 'hot_out.'))})
    for iid, heat in exchanges.items():
        values = {'heat_w': heat}
        for side in ('hot', 'cold'):
            values.update({side + '_' + k: v for k, v in results.pop(iid + '#' + side).items() if k != 'capacity_w_k'})
        results[iid] = values
    return dm, du, boundary, results, caches, {'network_pressure_residual_pa': p_error, 'network_mass_residual_kg_s': m_error}
