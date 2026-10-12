"""Thermal algebra layer: node enthalpy transport on a solved hydraulic network.

Ports carry pressure + specific enthalpy (the Baselu P/H port state). The
hydraulic solve fixes pressures and flows; enthalpy then travels with the flow
(upwind), mixes at nodes by mass-weighted average and changes only through
declared heat sources. Properties come from the configured property service and
stay frozen while each linear system is solved; damped Picard iteration updates
them, as in the archived v0.2 kernel.

Unknowns are node enthalpies h[n]. Each flowing branch maps its upwind node to
an outlet stream, h_out = Σ a·h[k] + c, and every free node obeys

    h[n]·(Σ outflow w + absorbed) = Σ inflow w·h_out + supply·h_boundary.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from .compiler import CompilationError, CompiledNetwork
from .models import Diagnostic, FluidState, NetworkRelation
from .properties import PropertyError

GRAVITY = 9.80665
# Floor for "transports enthalpy"; the effective threshold is max(this, mass tolerance), because the
# hydraulic solution cannot tell a flow below its mass tolerance from zero.
FLOW_EPS = 1e-12
DEFAULT_TEMPERATURE_K = 293.15
ENERGY_RTOL = 1e-6
PHASE_LABELS = {'liquid': '液相', 'gas': '气相', 'twophase': '气液两相'}


class ThermalError(CompilationError):
    """Thermal failure with a code and, when known, the instance it belongs to."""


@dataclass
class ThermalResult:
    enthalpies: np.ndarray                 # node specific enthalpy, J/kg
    node_states: list[FluidState]
    flows: np.ndarray                      # branch mass flow used for transport, kg/s
    upstream: list[int]                    # per branch: node the flow comes from
    downstream: list[int]
    outlet_enthalpies: np.ndarray          # per branch: stream leaving into `downstream`
    outlet_states: list[FluidState]
    heat_w: np.ndarray                     # per branch: w·(h_out − h_in), i.e. heat + shaft work + potential
    boundary_supply: dict[int, float]      # fixed node -> kg/s the boundary feeds into the network
    boundary_states: dict[int, FluidState]
    port_states: dict[str, FluidState]     # 'instance:port' -> state seen at that port
    reference_heat_w: float                # heat the fallback temperature reference had to add (negative = removed)
    energy_residual_w: float
    iterations: int
    diagnostics: list[Diagnostic] = field(default_factory=list)


def phase_family(state: FluidState) -> str:
    if state.quality is not None and 0.0 <= state.quality <= 1.0:
        return 'twophase'
    phase = (state.phase or '').lower()
    if 'twophase' in phase or 'two_phase' in phase:
        return 'twophase'
    if 'liquid' in phase:
        return 'liquid'
    if 'gas' in phase or 'supercritical' in phase:
        return 'gas'
    return 'unknown'


def _node_labels(network: CompiledNetwork) -> list[str]:
    """One instance ID per node for diagnostics, preferring real devices over boundaries/junctions."""
    labels = [key.split(':', 1)[0] for key in network.node_keys]
    preferred = set()
    for key, node in network.port_nodes.items():
        instance_id = key.split(':', 1)[0]
        model = network.modules[network.instances[instance_id].module_id].solver_model
        if model not in ('pressure_source', 'junction') and node not in preferred:
            labels[node] = instance_id
            preferred.add(node)
    return labels


def component_temperatures(network: CompiledNetwork) -> tuple[list[float], list[bool]]:
    """Initial node temperature: the node's own boundary, else the first boundary of its hydraulic component."""
    n = len(network.node_keys)
    component = network.node_component if len(network.node_component) == n else list(range(n))
    first: dict[int, float] = {}
    for node in sorted(network.fixed_temperatures):
        first.setdefault(component[node], network.fixed_temperatures[node])
    temperatures, known = [], []
    for node in range(n):
        if node in network.fixed_temperatures:
            temperatures.append(network.fixed_temperatures[node]); known.append(True)
        elif component[node] in first:
            temperatures.append(first[component[node]]); known.append(True)
        else:
            temperatures.append(DEFAULT_TEMPERATURE_K); known.append(False)
    return temperatures, known


def _wrap_property_error(error: PropertyError, instance: str) -> ThermalError:
    if error.code == 'PHASE_UNSUPPORTED':
        return ThermalError('PHASE_UNSUPPORTED', f'{instance} 处：{error}', instance)
    return ThermalError(error.code, f'{instance} 处物性计算失败：{error}', instance)


def _state_pt(service, pressure: float, temperature: float, instance: str) -> FluidState:
    try:
        return service.state_pt(float(pressure), float(temperature))
    except PropertyError as error:
        raise _wrap_property_error(error, instance) from error


def initial_guess(network: CompiledNetwork, service) -> list[FluidState]:
    """Node states before any hydraulic result exists (reference-mode trial ports, first coupling pass).

    Pressure is not known yet, so every node uses the pressure of the boundary its temperature came from.
    """
    n = len(network.node_keys)
    temperatures, _ = component_temperatures(network)
    component = network.node_component if len(network.node_component) == n else list(range(n))
    reference_pressure: dict[int, float] = {}
    for node in sorted(network.fixed_pressures):
        reference_pressure.setdefault(component[node], network.fixed_pressures[node])
    labels = _node_labels(network)
    states = []
    for node in range(n):
        pressure = network.fixed_pressures.get(node, reference_pressure.get(component[node], 101325.0))
        states.append(_state_pt(service, pressure, temperatures[node], labels[node]))
    return states


def solve_thermal(network: CompiledNetwork, service, pressures, flows,
                  relations: dict[tuple[str, str], NetworkRelation] | None = None,
                  shaft_power_w=None, initial_enthalpies=None) -> ThermalResult:
    """Solve node enthalpies for fixed pressures and flows."""
    options = network.project.solver
    relations = relations or {}
    n, branches = len(network.node_keys), network.branches
    m = len(branches)
    pressures = np.asarray(pressures, dtype=float)
    flows = np.asarray(flows, dtype=float)
    shaft = np.zeros(m) if shaft_power_w is None else np.asarray(shaft_power_w, dtype=float)
    labels = _node_labels(network)
    diagnostics: list[Diagnostic] = []

    flow_eps = max(FLOW_EPS, options.mass_tolerance_kg_s)
    # Free-node mass residuals add up at the fixed node of their component; that much "exchange" is noise.
    exchange_eps = max(flow_eps, options.mass_tolerance_kg_s * max(1, n))
    weight = np.abs(flows)
    for j, branch in enumerate(branches):
        relation = relations.get((branch.instance_id, branch.channel_id))
        if branch.closed or (relation is not None and relation.kind == 'valve' and relation.parameters['opening_ratio'] == 0):
            weight[j] = 0.0
    flowing = [j for j in range(m) if weight[j] > flow_eps]
    upstream = [b.start_node if q >= 0 else b.end_node for b, q in zip(branches, flows)]
    downstream = [b.end_node if q >= 0 else b.start_node for b, q in zip(branches, flows)]

    fixed = network.fixed_pressures
    boundary_states = {node: _state_pt(service, fixed[node], network.fixed_temperatures.get(node, DEFAULT_TEMPERATURE_K),
                                       labels[node]) for node in fixed}
    # Allowed single phase per hydraulic component: a vapour line elsewhere must not let a liquid
    # stream silently turn into steam (its hydraulics still assume the liquid density).
    component = network.node_component if len(network.node_component) == n else [0] * n
    allowed_by_component: dict[int, set[str]] = {}
    for node, state in boundary_states.items():
        allowed_by_component.setdefault(component[node], set()).add(phase_family(state))
    for families in allowed_by_component.values():
        families -= {'twophase', 'unknown'}

    def checked_state(pressure: float, enthalpy: float, instance: str, node: int) -> FluidState:
        try:
            state = service.state_ph(float(pressure), float(enthalpy))
        except PropertyError as error:
            raise _wrap_property_error(error, instance) from error
        family = phase_family(state)
        allowed = allowed_by_component.get(component[node], set())
        if family == 'twophase' or (allowed and family != 'unknown' and family not in allowed):
            expected = '、'.join(PHASE_LABELS[f] for f in sorted(allowed)) or '单相'
            quality = f'，干度 {state.quality:.4g}' if state.quality is not None else ''
            raise ThermalError('PHASE_UNSUPPORTED',
                               f'{instance} 处流体进入{PHASE_LABELS.get(family, family)}状态（{state.phase}{quality}）；'
                               f'当前网络只支持与边界一致的单相{expected}流动', instance)
        return state

    # Boundary exchange follows from the branch flows meeting each fixed-pressure node.
    net_out = np.zeros(n)
    for j in flowing:
        net_out[upstream[j]] += weight[j]
        net_out[downstream[j]] -= weight[j]
    supply = {node: float(net_out[node]) for node in fixed if net_out[node] > exchange_eps}
    absorbed = {node: float(-net_out[node]) for node in fixed if net_out[node] < -exchange_eps}

    touched = {upstream[j] for j in flowing} | {downstream[j] for j in flowing}
    stagnant = [node not in touched for node in range(n)]
    temperatures, known = component_temperatures(network)
    h_init = np.array([boundary_states[node].enthalpy_j_kg if node in boundary_states else
                       _state_pt(service, pressures[node], temperatures[node], labels[node]).enthalpy_j_kg
                       for node in range(n)])

    # Static branch classification.
    kinds, heat, gravity = ['isenthalpic'] * m, np.zeros(m), np.zeros(m)
    pipe_ua, ambient_h, ambient_t = np.zeros(m), np.zeros(m), np.zeros(m)
    ambient_family = [''] * m
    exchanger_branches: dict[str, list[int]] = {}
    for j, branch in enumerate(branches):
        instance = network.instances[branch.instance_id]
        definition = network.modules[instance.module_id]
        params = network.parameters[branch.instance_id]
        relation = relations.get((branch.instance_id, branch.channel_id))
        height = float((relation.parameters if relation else params).get('height_m', 0.0) or 0.0)
        # Potential energy: rising along the flow converts enthalpy into elevation.
        gravity[j] = -GRAVITY * height * (1.0 if flows[j] >= 0 else -1.0)
        if relation is not None:
            kinds[j] = 'module'
            heat[j] = float(relation.parameters.get('heat_w', 0.0) or 0.0)
            if heat[j] != 0.0 and weight[j] <= flow_eps:
                raise ThermalError('NO_FLOW_HEAT', f'{branch.instance_id}.{branch.channel_id} 通路流量为零却声明了 '
                                   f'{heat[j]:g} W 的热量；无热容通路不能在零流量下持续加热或冷却',
                                   branch.instance_id, branch.channel_id)
        elif definition.runtime == 'builtin' and definition.solver_model == 'heat_exchanger':
            kinds[j] = 'exchanger'
            exchanger_branches.setdefault(branch.instance_id, []).append(j)
        elif branch.solver_model == 'pipe':
            kinds[j] = 'pipe'
            pipe_ua[j] = float(params.get('heat_loss_ua_w_k', 0.0) or 0.0)
            if pipe_ua[j] > 0 and weight[j] > flow_eps:
                ambient_t[j] = float(params.get('ambient_temperature_k', DEFAULT_TEMPERATURE_K))
                ambient_state = _state_pt(service, pressures[downstream[j]], ambient_t[j], branch.instance_id)
                ambient_h[j], ambient_family[j] = ambient_state.enthalpy_j_kg, phase_family(ambient_state)
        elif branch.solver_model == 'pump_curve':
            kinds[j] = 'pump'

    exchangers = []  # (instance, side a, side b, UA) with both sides flowing
    for instance_id, sides in exchanger_branches.items():
        if len(sides) < 2:
            continue
        a, b, ua = sides[0], sides[1], float(network.parameters[instance_id].get('ua_w_k', 0.0) or 0.0)
        if ua <= 0:
            continue
        if weight[a] > flow_eps and weight[b] > flow_eps:
            exchangers.append((instance_id, a, b, ua))
        else:
            diagnostics.append(Diagnostic(code='THERMAL_EXCHANGER_NO_FLOW', severity='info', instance_id=instance_id,
                                          message=f'{instance_id} 至少一侧无流量，本次不交换热量'))
    nonlinear = bool(exchangers) or any(pipe_ua[j] > 0 for j in flowing)

    # Which nodes does inflow determine? Anything else sits on a closed circulation.
    edges = [(upstream[j], downstream[j]) for j in flowing]
    for _, a, b, _ in exchangers:
        edges += [(upstream[a], downstream[b]), (upstream[b], downstream[a])]
    adjacency = [[] for _ in range(n)]
    for u, v in edges:
        adjacency[u].append(v)

    def reachable(seeds):
        seen, pending = set(seeds), list(seeds)
        while pending:
            node = pending.pop()
            for other in adjacency[node]:
                if other not in seen:
                    seen.add(other)
                    pending.append(other)
        return seen

    # A lossy pipe relaxes towards ambient, which also fixes the level of a closed loop it sits in.
    seeds = set(supply) | {downstream[j] for j in flowing if kinds[j] == 'pipe' and pipe_ua[j] > 0}
    pins: dict[int, float] = {}
    reach = reachable(seeds)
    while True:
        unresolved = [node for node in range(n) if node not in reach and not stagnant[node]]
        if not unresolved:
            break
        index = {node: i for i, node in enumerate(unresolved)}
        inner = [(index[u], index[v]) for u, v in edges if u in index and v in index]
        graph = csr_matrix(([1.0] * len(inner), ([u for u, _ in inner], [v for _, v in inner])),
                           shape=(len(unresolved), len(unresolved)))
        _, scc = connected_components(graph, directed=True, connection='strong')
        fed = {scc[v] for u, v in inner if scc[u] != scc[v]}
        for label in sorted(set(scc) - fed):
            members = [node for node in unresolved if scc[index[node]] == label]
            node = min((k for k in members if k in fixed), default=min(members))
            if not known[node]:
                raise ThermalError('THERMAL_REFERENCE_MISSING', f'{labels[node]} 所在回路没有补水流入，也没有可作温度参考的压力边界',
                                   labels[node])
            pins[node] = (boundary_states[node].enthalpy_j_kg if node in boundary_states else
                          _state_pt(service, pressures[node], temperatures[node], labels[node]).enthalpy_j_kg)
        reach = reachable(seeds | set(pins))
    if pins:
        names = sorted({labels[node] for node in pins})
        diagnostics.append(Diagnostic(code='THERMAL_REFERENCE_FROM_BOUNDARY', severity='warning', instance_id=names[0],
            message=f'闭合回路没有补水流入，温度参考取自压力边界温度（{"、".join(names)}）；'
                    '回路内热源与热汇的不平衡计入 reference_heat_w 指标'))
    held = {node for node in range(n) if stagnant[node]}
    if held:
        names = sorted({labels[node] for node in held})
        shown = '、'.join(names[:5]) + ('等' if len(names) > 5 else '')
        diagnostics.append(Diagnostic(code='THERMAL_STAGNANT_NODE', severity='info', instance_id=names[0],
                                      message=f'{shown} 处没有流动，温度保持边界或初始值'))
    fixed_rows = {**{node: float(h_init[node]) for node in held}, **pins}

    def relations_for(states, h):
        weights = [{upstream[j]: 1.0} for j in range(m)]
        consts = np.zeros(m)
        for j in flowing:
            up, w, c = upstream[j], weight[j], gravity[j]
            if kinds[j] == 'pipe' and pipe_ua[j] > 0:
                cp = states[up].specific_heat_j_kg_k
                a = math.exp(-pipe_ua[j] / (w * cp))
                weights[j] = {up: a}
                if ambient_family[j] == phase_family(states[up]):
                    c += (1.0 - a) * ambient_h[j]
                else:
                    # Ambient lies across the phase boundary (e.g. 110 °C air around a 1.2 bar water
                    # line): only sensible heat crosses the wall, h_env ≈ h_up + cp·(T_amb − T_up).
                    # Using h(p, T_amb) there would count latent heat as transferable.
                    offset = states[up].temperature_k - h[up] / cp
                    c += (1.0 - a) * cp * (ambient_t[j] - offset)
            elif kinds[j] == 'pump':
                c += shaft[j] / w
            elif kinds[j] == 'module':
                # Python pump/compressor relations carry shaft work in `shaft`; heat_w is extra heat.
                c += (heat[j] + shaft[j]) / w
            consts[j] = c
        for _, a, b, ua in exchangers:
            na, nb = upstream[a], upstream[b]
            cpa, cpb = states[na].specific_heat_j_kg_k, states[nb].specific_heat_j_kg_k
            ca, cb = weight[a] * cpa, weight[b] * cpb
            cmin, cmax = min(ca, cb), max(ca, cb)
            ratio, ntu = cmin / cmax, ua / cmin
            # Nominal arrangement is counterflow; with exactly one side reversed the streams run parallel.
            if (flows[a] >= 0) != (flows[b] >= 0):
                effectiveness = (1.0 - math.exp(-ntu * (1.0 + ratio))) / (1.0 + ratio)
            elif abs(1.0 - ratio) < 1e-8:
                effectiveness = ntu / (1.0 + ntu)
            else:
                exponential = math.exp(-ntu * (1.0 - ratio))
                effectiveness = (1.0 - exponential) / (1.0 - ratio * exponential)
            conductance = effectiveness * cmin
            # T ≈ h/cp + offset around the current state; Q = G·(T_a,in − T_b,in) is then linear in h.
            offset = (states[na].temperature_k - h[na] / cpa) - (states[nb].temperature_k - h[nb] / cpb)
            side_a = {na: 1.0 - conductance / ca}
            side_a[nb] = side_a.get(nb, 0.0) + conductance / (weight[a] * cpb)
            side_b = {nb: 1.0 - conductance / cb}
            side_b[na] = side_b.get(na, 0.0) + conductance / (weight[b] * cpa)
            weights[a], weights[b] = side_a, side_b
            consts[a] += -conductance * offset / weight[a]
            consts[b] += conductance * offset / weight[b]
        return weights, consts

    def solve_linear(weights, consts):
        # Mixing form: h[n]·(Σ inflow + supply) = Σ inflow·h_out + supply·h_b. Writing the diagonal from the
        # arriving streams keeps a node well posed even when its outflows differ by the mass residual.
        rows, cols, values, rhs = [], [], [], np.zeros(n)
        for node, value in fixed_rows.items():
            rows.append(node); cols.append(node); values.append(1.0); rhs[node] = value
        for j in flowing:
            down, w = downstream[j], weight[j]
            if down not in fixed_rows:
                rows.append(down); cols.append(down); values.append(w)
                for col, a in weights[j].items():
                    rows.append(down); cols.append(col); values.append(-w * a)
                rhs[down] += w * consts[j]
        for node, amount in supply.items():
            if node not in fixed_rows:
                rows.append(node); cols.append(node); values.append(amount)
                rhs[node] += amount * boundary_states[node].enthalpy_j_kg
        matrix = coo_matrix((values, (rows, cols)), shape=(n, n)).tocsc()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', MatrixRankWarning)
                solution = np.atleast_1d(spsolve(matrix, rhs))
        except (MatrixRankWarning, RuntimeError) as error:
            raise ThermalError('THERMAL_REFERENCE_MISSING', '热力方程欠约束：检查闭式回路的温度参考、热源与热汇') from error
        if not np.all(np.isfinite(solution)):
            raise ThermalError('THERMAL_NOT_FINITE', '热力方程没有有限解')
        return solution

    def node_states(h):
        return [checked_state(pressures[node], h[node], labels[node], node) for node in range(n)]

    if initial_enthalpies is not None and np.shape(initial_enthalpies) == (n,) and np.all(np.isfinite(initial_enthalpies)):
        h = np.array(initial_enthalpies, dtype=float)
    else:
        h = h_init.copy()
    for node, value in fixed_rows.items():
        h[node] = value
    for iterations in range(1, options.max_thermal_iterations + 1):
        states = node_states(h) if nonlinear else None
        weights, consts = relations_for(states, h)
        candidate = solve_linear(weights, consts)
        if not nonlinear:
            h = candidate
            break
        change = max((abs(candidate[k] - h[k]) / (states[k].specific_heat_j_kg_k or 4180.0) for k in range(n)), default=0.0)
        if change < options.thermal_tolerance_k:
            h = candidate
            break
        # The first pass replaces a cold guess outright; later passes are damped as in v0.2.
        h = candidate if iterations == 1 else 0.7 * candidate + 0.3 * h
    else:
        raise ThermalError('THERMAL_NOT_CONVERGED', f'热力迭代 {options.max_thermal_iterations} 次未收敛，请检查换热与散热参数')

    states = node_states(h)
    outlet_h = np.array([h[downstream[j]] for j in range(m)])
    outlet_states = [states[downstream[j]] for j in range(m)]
    heat_w = np.zeros(m)
    for j in flowing:
        outlet_h[j] = sum(a * h[col] for col, a in weights[j].items()) + consts[j]
        outlet_states[j] = checked_state(pressures[downstream[j]], outlet_h[j], branches[j].instance_id, downstream[j])
        heat_w[j] = weight[j] * (outlet_h[j] - h[upstream[j]])

    # Heat the fallback reference injected: residual of the original node balance at pinned rows.
    reference_heat = 0.0
    for node in pins:
        balance = absorbed.get(node, 0.0) * h[node] - supply.get(node, 0.0) * boundary_states[node].enthalpy_j_kg \
            if node in boundary_states else 0.0
        for j in flowing:
            if upstream[j] == node:
                balance += weight[j] * h[node]
            if downstream[j] == node:
                balance -= weight[j] * outlet_h[j]
        reference_heat += balance
    boundary_in = sum(amount * boundary_states[node].enthalpy_j_kg for node, amount in supply.items()) \
        - sum(amount * h[node] for node, amount in absorbed.items())
    residual = float(boundary_in + heat_w.sum() + reference_heat)
    scale = 1.0 + sum(weight[j] * abs(outlet_h[j]) for j in flowing) \
        + sum(amount * abs(boundary_states[node].enthalpy_j_kg) for node, amount in supply.items())
    if abs(residual) > ENERGY_RTOL * scale:
        raise ThermalError('THERMAL_ENERGY_IMBALANCE', f'热力解的能量残差 {residual:.6g} W 超出容差')

    outlet_port: dict[str, int] = {}
    for j in flowing:
        branch = branches[j]
        outlet_port[f'{branch.instance_id}:{branch.output_port if flows[j] >= 0 else branch.input_port}'] = j
    port_states: dict[str, FluidState] = {}
    for key, node in network.port_nodes.items():
        instance_id = key.split(':', 1)[0]
        is_boundary = network.modules[network.instances[instance_id].module_id].solver_model == 'pressure_source'
        if key in outlet_port:
            port_states[key] = outlet_states[outlet_port[key]]
        elif is_boundary and node in supply:
            port_states[key] = boundary_states[node]
        else:
            port_states[key] = states[node]

    return ThermalResult(enthalpies=h, node_states=states, flows=flows, upstream=upstream, downstream=downstream,
                         outlet_enthalpies=outlet_h, outlet_states=outlet_states, heat_w=heat_w,
                         boundary_supply=supply, boundary_states=boundary_states, port_states=port_states,
                         reference_heat_w=float(reference_heat), energy_residual_w=residual, iterations=iterations,
                         diagnostics=diagnostics)
