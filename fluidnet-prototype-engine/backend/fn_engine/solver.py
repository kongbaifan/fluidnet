from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from .compiler import CompiledBranch, CompiledNetwork
from .models import CommitStepRequest, Diagnostic, EvaluateRequest, FluidState, PortState, RunFrame, NetworkRelation
from .properties import PropertyError, property_service
from .runtime import ChannelResult, WorkerProcess, RuntimeErrorBase
from .thermal import ThermalError, ThermalResult, initial_guess, solve_thermal

# Reference values at 250 kPa / 20 °C. They preserve the public helper's
# backwards-compatible defaults while normal runs use the configured property
# service below.
RHO_WATER = 998.2752462838249
MU_WATER = 1.0015503944484675e-3
GRAVITY = 9.80665
PRESSURE_SCALE = 100000.0


class SolveCancelled(Exception):
    """Raised when a run is cancelled between timeline frames.

    Deliberately not a `ValueError`: callers must be able to tell a user-requested
    cancellation apart from an invalid input or a failed solve. `frames` carries
    the frames completed before the cancellation was observed so the caller can
    keep them as partial results.
    """

    def __init__(self, message: str = '运行已取消', frames=None):
        super().__init__(message)
        self.frames = list(frames or ())


@dataclass
class HydraulicResult:
    pressures: np.ndarray
    flows: np.ndarray
    iterations: int
    pressure_residual: float
    mass_residual: float
    density: float = RHO_WATER
    viscosity: float = MU_WATER
    module_variables: dict = field(default_factory=dict)
    module_diagnostics: list = field(default_factory=list)
    # Per-branch properties used by the solve (all equal to density/viscosity in reference mode).
    branch_density: np.ndarray | None = None
    branch_viscosity: np.ndarray | None = None
    relations: dict = field(default_factory=dict)
    # Solver unknown vector, reused as the next solve's starting point.
    solution: np.ndarray | None = None


@dataclass
class NetworkResult:
    hydraulic: HydraulicResult
    thermal: ThermalResult | None = None
    coupling_iterations: int = 0
    port_states: dict[str, PortState] = field(default_factory=dict)


def pipe_drop(params, flow, density=RHO_WATER, viscosity=MU_WATER):
    length, diameter, roughness = params['length_m'], params['diameter_m'], params['roughness_m']
    area = math.pi * diameter ** 2 / 4
    reynolds = abs(flow) * diameter / (viscosity * area)
    laminar = 32 * viscosity * length * flow / (density * area * diameter ** 2)
    if reynolds <= 2300:
        return laminar
    friction = (-1.8 * math.log10((roughness / diameter / 3.7) ** 1.11 + 6.9 / reynolds)) ** -2
    turbulent = friction * length / diameter * flow * abs(flow) / (2 * density * area ** 2)
    blend = min(1., (reynolds - 2300) / 1700)
    return laminar * (1 - blend) + turbulent * blend


def pump_head(curve, flow_m3_h, speed):
    x = flow_m3_h / speed
    # Linear extrapolation is used only to locate the root. Out-of-curve results are rejected below.
    points = curve
    if x < points[0][0]:
        a, b = points[:2]
    elif x > points[-1][0]:
        a, b = points[-2:]
    else:
        return float(np.interp(x, [p[0] for p in points], [p[1] for p in points])) * speed ** 2
    return (a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])) * speed ** 2


def branch_drop(network: CompiledNetwork, branch: CompiledBranch, flow_kg_s: float, density: float,
                viscosity: float, relation: NetworkRelation | None = None) -> float:
    params, model = network.parameters[branch.instance_id], branch.solver_model
    relation_params = relation.parameters if relation else {}
    if relation:
        model = {'pump':'pump_curve'}.get(relation.kind, relation.kind)
        params = {**params, **relation_params}
        density = relation_params.get('density_kg_m3') or density
        viscosity = relation_params.get('viscosity_pa_s') or viscosity
    volume = flow_kg_s / density * 3600
    if model == 'valve':
        kv = params['kv_m3_h'] * params['opening_ratio']
        return 100000 * (density / 1000) * volume * abs(volume) / kv ** 2 + density * GRAVITY * params.get('height_m', 0)
    if model == 'pipe':
        return pipe_drop(params, flow_kg_s, density, viscosity) + density * GRAVITY * params.get('height_m', 0)
    if model == 'pump_curve':
        if params['speed_ratio'] <= 0:
            raise ValueError(f'{branch.instance_id} 停泵阻力模型尚未定义，转速必须大于零')
        return -density * GRAVITY * pump_head(params['head_curve'], volume, params['speed_ratio'])
    if model == 'resistance':
        area = math.pi * params['diameter_m'] ** 2 / 4
        return params['loss_coefficient'] * flow_kg_s * abs(flow_kg_s) / (2 * density * area ** 2)
    raise ValueError(f'未注册的支路模型：{model}')


def _python_runners(network: CompiledNetwork):
    runners = {}
    try:
        for instance_id, instance in network.instances.items():
            definition = network.modules[instance.module_id]
            if definition.runtime == 'python':
                runner = WorkerProcess(definition, network.parameters[instance_id], network.project.fluid,
                                       initial_state={})
                runners[instance_id] = runner
                runner.initialize()
    except Exception:
        _close_runners(runners)
        raise
    return runners


def _close_runners(runners):
    for runner in runners.values():
        try:
            runner.close()
        except Exception:
            pass


def reference_properties(network: CompiledNetwork) -> tuple[float, float]:
    """Constant density/viscosity used by the hydraulics unless property coupling is 'node'."""
    try:
        # Keep the historical incompressible-water regression deterministic.
        # Other configured fluids obtain transport properties from CoolProp.
        if network.project.fluid.fluid.lower() in {'water', 'if97::water'}:
            return RHO_WATER, MU_WATER
        fixed = network.fixed_pressures
        reference_pressure = float(np.mean(list(fixed.values()))) if fixed else 250000.0
        reference_temperature = 293.15
        for params in network.parameters.values():
            if isinstance(params.get('temperature_k'), (int, float)):
                reference_temperature = float(params['temperature_k'])
                break
        state = property_service(network.project.fluid).state_pt(reference_pressure, reference_temperature)
        return state.density_kg_m3, state.viscosity_pa_s
    except PropertyError as error:
        raise ValueError(str(error)) from error


def _solve_hydraulics(network: CompiledNetwork, runners, time_s=0., branch_density=None, branch_viscosity=None,
                      port_base: dict[str, PortState] | None = None, initial=None) -> HydraulicResult:
    n_nodes, fixed = len(network.node_keys), network.fixed_pressures
    unknown = [n for n in range(n_nodes) if n not in fixed]
    options = network.project.solver
    m = len(network.branches)
    density, viscosity = reference_properties(network)
    rho_b = np.full(m, density) if branch_density is None else np.asarray(branch_density, dtype=float)
    mu_b = np.full(m, viscosity) if branch_viscosity is None else np.asarray(branch_viscosity, dtype=float)

    python_runners = runners
    iteration_id = 0
    module_variables, module_diagnostics = {}, []
    final_relations = {}

    def trial_port(instance_id, port_id, pressure):
        key = f'{instance_id}:{port_id}'
        if port_base is not None and key in port_base:
            return port_base[key].model_copy(update={'pressure_pa': pressure, 'mass_flow_kg_s': None})
        return PortState(pressure_pa=pressure,
                         temperature_k=float(network.parameters[instance_id].get('temperature_k', 293.15)),
                         density_kg_m3=density, viscosity_pa_s=viscosity)

    def evaluate_python_relations(pressures):
        nonlocal iteration_id
        iteration_id += 1
        relations = {}
        module_variables.clear()
        module_diagnostics.clear()
        final_relations.clear()
        for instance_id, runner in python_runners.items():
            instance = network.instances[instance_id]
            definition = network.modules[instance.module_id]
            ports = {}
            for port in definition.ports:
                node = network.port_nodes[f'{instance_id}:{port.id}']
                ports[port.id] = trial_port(instance_id, port.id, float(pressures[node]))
            response = runner.evaluate(EvaluateRequest(run_id='solve', instance_id=instance_id,
                iteration_id=iteration_id, time_s=time_s, trial_ports=ports, readonly_state=runner.state))
            expected = {c.id for c in definition.channels if c.enabled}
            actual = [r.channel for r in response.relations]
            if len(actual) != len(set(actual)) or set(actual) != expected:
                raise RuntimeErrorBase(f'{instance_id} evaluate 必须为每条启用通路提供且仅提供一条关系：{sorted(expected)}')
            for relation in response.relations:
                relations[(instance_id, relation.channel)] = relation
            errors = [item for item in response.diagnostics if item.severity == 'error']
            if errors:
                raise RuntimeErrorBase('; '.join(item.message for item in errors))
            module_variables.update({f'{instance_id}.{k}': v for k,v in response.variables.items()})
            module_variables.update({f'{instance_id}.state.{k}': v for k,v in runner.state.items() if isinstance(v,(float,int,str,bool)) or v is None})
            module_diagnostics.extend(response.diagnostics)
        final_relations.update(relations)
        return relations

    def unpack(vector):
        pressures = np.zeros(n_nodes)
        for node, value in fixed.items():
            pressures[node] = value
        pressures[unknown] = vector[:len(unknown)] * PRESSURE_SCALE
        return pressures, vector[len(unknown):]

    def physical_residual(vector):
        pressures, flows = unpack(vector)
        runtime_relations = evaluate_python_relations(pressures) if python_runners else {}
        drops, balance, closed = [], np.zeros(n_nodes), []
        for idx, (branch, flow) in enumerate(zip(network.branches, flows)):
            relation = runtime_relations.get((branch.instance_id, branch.channel_id))
            runtime_closed = relation is not None and relation.kind == 'valve' and relation.parameters['opening_ratio'] == 0
            if branch.closed or runtime_closed:
                drops.append(0.)
                closed.append(float(flow))
            elif relation is not None and relation.kind == 'compressor':
                drops.append(0.)
                closed.append(float(flow) - relation.parameters['forced_mass_flow_kg_s'])
            else:
                drops.append(pressures[branch.start_node] - pressures[branch.end_node] - branch_drop(
                    network, branch, float(flow), float(rho_b[idx]), float(mu_b[idx]), relation))
            balance[branch.start_node] -= flow
            balance[branch.end_node] += flow
        constraints = {}
        for idx, branch in enumerate(network.branches):
            relation = runtime_relations.get((branch.instance_id,branch.channel_id))
            if branch.closed or (relation and relation.kind == 'valve' and relation.parameters['opening_ratio'] == 0):
                constraints[idx] = flows[idx]
            elif relation and relation.kind == 'compressor':
                constraints[idx] = flows[idx] - relation.parameters['forced_mass_flow_kg_s']
        return np.asarray(drops), balance[unknown], closed, constraints

    def residual(vector):
        drops, balance, _, constraints = physical_residual(vector)
        _, flows = unpack(vector)
        scaled = drops / PRESSURE_SCALE
        for idx, value in constraints.items():
            scaled[idx] = value
        return np.concatenate((scaled, balance))

    size = len(unknown) + m
    cold = np.concatenate((np.full(len(unknown), np.mean(list(fixed.values())) / PRESSURE_SCALE), np.full(m, .1)))
    warm_start = initial is not None and np.shape(initial) == (size,) and np.all(np.isfinite(initial))
    if warm_start:
        start = np.array(initial, dtype=float)
        # Quadratic laws (q·|q|) have zero slope at q=0, so a branch that carried no flow in the
        # previous frame would stall least_squares on gtol; restart such flows from the cold guess.
        flows_start = start[len(unknown):]
        flows_start[np.abs(flows_start) < max(1e-6, 100 * options.mass_tolerance_kg_s)] = .1
    else:
        start = cold

    def attempt(vector):
        result = least_squares(residual, vector, max_nfev=options.max_iterations, xtol=1e-12, ftol=1e-12, gtol=1e-12, x_scale='jac')
        drops, balance, closed, constraints = physical_residual(result.x)
        pressure_error = float(np.max(np.abs(drops), initial=0))
        mass_error = max(float(np.max(np.abs(balance), initial=0)), max(map(abs, closed), default=0.))
        ok = result.success and pressure_error <= options.pressure_tolerance_pa and mass_error <= options.mass_tolerance_kg_s
        return result, drops, balance, closed, constraints, ok

    result, drops, balance, closed, constraints, ok = attempt(start)
    if warm_start and not ok:
        # A warm start is only a hint: fall back to the cold guess before reporting non-convergence.
        result, drops, balance, closed, constraints, ok = attempt(cold)
    pressures, flows = unpack(result.x)
    # Zero-flow and forced-flow relations do not determine a pressure difference.
    # Every pressure component left after removing them needs its own reference.
    reached, pending = set(fixed), list(fixed)
    adjacency = {node: set() for node in range(n_nodes)}
    for idx, branch in enumerate(network.branches):
        if idx not in constraints:
            adjacency[branch.start_node].add(branch.end_node)
            adjacency[branch.end_node].add(branch.start_node)
    while pending:
        node = pending.pop()
        for other in adjacency[node] - reached:
            reached.add(other)
            pending.append(other)
    if len(reached) != n_nodes:
        raise RuntimeErrorBase('模块通路关系产生了缺少压力参考的子网络')
    pressure_error = float(np.max(np.abs(drops), initial=0))
    mass_error = max(float(np.max(np.abs(balance), initial=0)), max(map(abs, closed), default=0.))
    if not result.success or pressure_error > options.pressure_tolerance_pa or mass_error > options.mass_tolerance_kg_s:
        raise ValueError(f'水力求解未收敛：压力残差 {pressure_error:.6g} Pa，质量残差 {mass_error:.6g} kg/s；{result.message}')
    if np.any(pressures <= 0) or not np.all(np.isfinite(result.x)):
        raise ValueError('求解产生非正绝对压力或非有限结果')
    for idx, (branch, flow) in enumerate(zip(network.branches, flows)):
        relation = final_relations.get((branch.instance_id,branch.channel_id))
        if relation and relation.kind == 'pump' or relation is None and branch.solver_model == 'pump_curve':
            params = relation.parameters if relation else network.parameters[branch.instance_id]
            q = flow / (params.get('density_kg_m3') or float(rho_b[idx])) * 3600
            if q < -1e-8 or q > params['head_curve'][-1][0] * params['speed_ratio'] + 1e-8:
                raise ValueError(f'{branch.instance_id} 工作点 {q:.6g} m³/h 超出泵曲线范围；反向流和曲线外工况尚未支持')
    return HydraulicResult(pressures, flows, int(result.nfev), pressure_error, mass_error, density, viscosity,
                           module_variables.copy(), module_diagnostics.copy(), rho_b, mu_b, dict(final_relations),
                           np.array(result.x, copy=True))


def solve_hydraulics(network: CompiledNetwork, runners=None, time_s=0., **options) -> HydraulicResult:
    """Solve one hydraulic state, isolating every Python module in a Worker by default."""
    owned = runners is None
    active = _python_runners(network) if owned else runners
    try:
        return _solve_hydraulics(network, active, time_s, **options)
    finally:
        if owned:
            _close_runners(active)


def shaft_power(network: CompiledNetwork, hydraulic: HydraulicResult) -> np.ndarray:
    """Shaft power delivered to the fluid per branch (W); zero for passive branches.

    Built-in pumps use their efficiency_ratio. Python pump/compressor relations carry no
    efficiency, so their hydraulic power (Δp·q/ρ) is the shaft work; heat_w adds any losses.
    """
    power = np.zeros(len(network.branches))
    densities = hydraulic.branch_density if hydraulic.branch_density is not None else np.full(len(power), hydraulic.density)
    relations = hydraulic.relations or {}
    for idx, (branch, flow) in enumerate(zip(network.branches, hydraulic.flows)):
        drop = float(hydraulic.pressures[branch.start_node] - hydraulic.pressures[branch.end_node])
        relation = relations.get((branch.instance_id, branch.channel_id))
        if relation is not None:
            if relation.kind in ('pump', 'compressor'):
                density = relation.parameters.get('density_kg_m3') or float(densities[idx])
                power[idx] = -drop * float(flow) / density
        elif branch.solver_model == 'pump_curve' and network.modules[network.instances[branch.instance_id].module_id].runtime != 'python':
            power[idx] = -drop * float(flow) / float(densities[idx]) / network.parameters[branch.instance_id]['efficiency_ratio']
    return power


def port_mass_flows(network: CompiledNetwork, flows) -> dict[str, float]:
    """Port mass flow, positive into the device. Boundary/junction ports follow their connected equipment port."""
    port_flows = {}
    for branch, flow in zip(network.branches, flows):
        q = float(flow)
        for port, value in ((branch.input_port, q), (branch.output_port, -q)):
            key = f'{branch.instance_id}:{port}'
            port_flows[key] = port_flows.get(key, 0.) + value
    pairs = [(f'{c.source.instance_id}:{c.source.port_id}', f'{c.target.instance_id}:{c.target.port_id}') for c in network.project.connections]
    pending = list(pairs)
    while pending:
        progress = False
        for a, b in pending[:]:
            if a in port_flows or b in port_flows:
                if a not in port_flows:
                    port_flows[a] = -port_flows[b]
                if b not in port_flows:
                    port_flows[b] = -port_flows[a]
                pending.remove((a,b))
                progress = True
        for inst in network.instances.values():
            if network.modules[inst.module_id].solver_model != 'junction':
                continue
            keys = [f'{inst.id}:{p.id}' for p in network.modules[inst.module_id].ports]
            connected = {key for pair in pairs for key in pair}
            for key in keys:
                if key not in connected:
                    port_flows[key] = 0.
            missing = [key for key in keys if key not in port_flows]
            if len(missing) == 1:
                port_flows[missing[0]] = -sum(port_flows.get(key, 0.) for key in keys)
                progress = True
        if not progress:
            break
    return port_flows


def _fluid_port(state: FluidState, pressure=None, mass_flow=None) -> PortState:
    return PortState(pressure_pa=float(state.pressure_pa if pressure is None else pressure), temperature_k=state.temperature_k,
                     enthalpy_j_kg=state.enthalpy_j_kg, density_kg_m3=state.density_kg_m3,
                     viscosity_pa_s=state.viscosity_pa_s, specific_heat_j_kg_k=state.specific_heat_j_kg_k,
                     mass_flow_kg_s=mass_flow, quality=state.quality)


def build_port_states(network: CompiledNetwork, hydraulic: HydraulicResult,
                      thermal: ThermalResult | None) -> dict[str, PortState]:
    """Converged state of every port, as handed to commit_step and the standalone bench."""
    flows = port_mass_flows(network, hydraulic.flows)
    states = {}
    for key, node in network.port_nodes.items():
        pressure = float(hydraulic.pressures[node])
        if thermal is not None:
            states[key] = _fluid_port(thermal.port_states[key], pressure, flows.get(key))
        else:
            instance_id = key.split(':', 1)[0]
            states[key] = PortState(pressure_pa=pressure,
                                    temperature_k=float(network.parameters[instance_id].get('temperature_k', 293.15)),
                                    density_kg_m3=hydraulic.density, viscosity_pa_s=hydraulic.viscosity,
                                    mass_flow_kg_s=flows.get(key))
    return states


def _node_ports(network: CompiledNetwork, node_states: list[FluidState]) -> dict[str, PortState]:
    """Trial-port base states for Python modules: every port takes its node's state."""
    return {key: _fluid_port(node_states[node]) for key, node in network.port_nodes.items()}


def _branch_properties(network: CompiledNetwork, thermal: ThermalResult) -> tuple[np.ndarray, np.ndarray]:
    """Per-branch density/viscosity: mean of the two end nodes (Baselu DENSITY=(IM0_VOLUME+EX0_VOLUME)/2)."""
    states = thermal.node_states
    rho = np.array([(states[b.start_node].density_kg_m3 + states[b.end_node].density_kg_m3) / 2 for b in network.branches])
    mu = []
    for b in network.branches:
        values = [v for v in (states[b.start_node].viscosity_pa_s, states[b.end_node].viscosity_pa_s) if v]
        if not values:
            raise ThermalError('PROPERTY_FAILURE', f'{b.instance_id} 两端黏度不可用，无法进行物性耦合', b.instance_id)
        mu.append(sum(values) / len(values))
    return rho, np.array(mu)


def solve_network(network: CompiledNetwork, runners=None, time_s=0., warm: NetworkResult | None = None,
                  service=None) -> NetworkResult:
    """Hydraulics, then (if enabled) the thermal layer, coupled according to SolverOptions.property_coupling.

    `warm` is the previous result for the same network (the previous dynamic frame) and only
    seeds the iterations; it never changes what counts as converged.
    """
    owned = runners is None
    active = _python_runners(network) if owned else runners
    try:
        return _solve_network(network, active, time_s, warm, service)
    finally:
        if owned:
            _close_runners(active)


def _solve_network(network, runners, time_s, warm, service) -> NetworkResult:
    options = network.project.solver
    start = warm.hydraulic.solution if warm is not None else None
    if not options.thermal:
        hydraulic = _solve_hydraulics(network, runners, time_s, initial=start)
        return NetworkResult(hydraulic, None, 0, build_port_states(network, hydraulic, None))
    service = service or property_service(network.project.fluid)
    h_start = warm.thermal.enthalpies if warm is not None and warm.thermal is not None else None
    if options.property_coupling == 'reference':
        port_base = None
        if runners:
            density, viscosity = reference_properties(network)
            port_base = {key: state.model_copy(update={'density_kg_m3': density, 'viscosity_pa_s': viscosity})
                         for key, state in _node_ports(network, initial_guess(network, service)).items()}
        hydraulic = _solve_hydraulics(network, runners, time_s, port_base=port_base, initial=start)
        thermal = solve_thermal(network, service, hydraulic.pressures, hydraulic.flows, hydraulic.relations,
                                shaft_power(network, hydraulic), h_start)
        return NetworkResult(hydraulic, thermal, 1, build_port_states(network, hydraulic, thermal))

    # node coupling: properties frozen during each hydraulic solve, updated between passes.
    if warm is not None and warm.thermal is not None and warm.hydraulic.branch_density is not None:
        rho_b, mu_b = warm.hydraulic.branch_density, warm.hydraulic.branch_viscosity
        node_states, previous_t = warm.thermal.node_states, np.array([s.temperature_k for s in warm.thermal.node_states])
    else:
        density, viscosity = reference_properties(network)
        rho_b, mu_b = np.full(len(network.branches), density), np.full(len(network.branches), viscosity)
        node_states, previous_t = initial_guess(network, service), None
    for iteration in range(1, options.max_coupling_iterations + 1):
        hydraulic = _solve_hydraulics(network, runners, time_s, branch_density=rho_b, branch_viscosity=mu_b,
                                      port_base=_node_ports(network, node_states) if runners else None, initial=start)
        thermal = solve_thermal(network, service, hydraulic.pressures, hydraulic.flows, hydraulic.relations,
                                shaft_power(network, hydraulic), h_start)
        new_rho, new_mu = _branch_properties(network, thermal)
        temperatures = np.array([s.temperature_k for s in thermal.node_states])
        density_change = float(np.max(np.abs(new_rho - rho_b) / new_rho, initial=0.0))
        converged = (previous_t is not None and density_change < options.coupling_density_rtol
                     and float(np.max(np.abs(temperatures - previous_t), initial=0.0)) < options.thermal_tolerance_k)
        if converged:
            return NetworkResult(hydraulic, thermal, iteration, build_port_states(network, hydraulic, thermal))
        rho_b, mu_b, previous_t = new_rho, new_mu, temperatures
        node_states, start, h_start = thermal.node_states, hydraulic.solution, thermal.enthalpies
    raise ThermalError('COUPLING_NOT_CONVERGED',
                       f'水力与物性耦合 {options.max_coupling_iterations} 次未收敛（密度相对变化 {density_change:.3g}）')


PORT_THERMAL_FIELDS = ('enthalpy_j_kg', 'density_kg_m3', 'viscosity_pa_s', 'specific_heat_j_kg_k', 'quality')
# Frame keys that exist only when SolverOptions.thermal is on (port fields above + channel results).
THERMAL_ONLY_SUFFIXES = PORT_THERMAL_FIELDS + ('inlet_temperature_k', 'outlet_temperature_k', 'heat_w')


def snapshot(network, result, time_s=0., warning=None):
    """Build a RunFrame from a NetworkResult (or a bare HydraulicResult, i.e. without the thermal layer)."""
    if isinstance(result, NetworkResult):
        hydraulic, thermal, coupling = result.hydraulic, result.thermal, result.coupling_iterations
    else:
        hydraulic, thermal, coupling = result, None, 0
    variables = {}
    density = hydraulic.density
    densities = hydraulic.branch_density if hydraulic.branch_density is not None else np.full(len(network.branches), density)
    diagnostics = (list(network.diagnostics) + hydraulic.module_diagnostics + (list(thermal.diagnostics) if thermal else [])
                   + ([warning] if warning else []))
    power = shaft_power(network, hydraulic)
    for idx, (branch, flow) in enumerate(zip(network.branches, hydraulic.flows)):
        q = float(flow)
        prefix = f'{branch.instance_id}.{branch.channel_id}'
        values = {'mass_flow_kg_s': q, 'volume_flow_m3_h': q / float(densities[idx]) * 3600,
                  'inlet_pressure_pa': float(hydraulic.pressures[branch.start_node]),
                  'outlet_pressure_pa': float(hydraulic.pressures[branch.end_node]),
                  'pressure_drop_pa': float(hydraulic.pressures[branch.start_node] - hydraulic.pressures[branch.end_node])}
        # Without the thermal layer the thermal-only keys are omitted (not None), keeping the
        # pre-0.3 frame size; see THERMAL_ONLY_SUFFIXES.
        if thermal is not None:
            values.update({'inlet_temperature_k': thermal.node_states[thermal.upstream[idx]].temperature_k,
                           'outlet_temperature_k': thermal.outlet_states[idx].temperature_k,
                           'heat_w': float(thermal.heat_w[idx])})
        variables.update({f'{prefix}.{k}': v for k, v in values.items()})
        if sum(b.instance_id == branch.instance_id for b in network.branches) == 1:
            variables.update({f'{branch.instance_id}.{k}': v for k, v in values.items()})
        if branch.solver_model == 'pump_curve' and network.modules[network.instances[branch.instance_id].module_id].runtime != 'python':
            variables[f'{branch.instance_id}.shaft_power_w'] = float(power[idx])
    port_flows = port_mass_flows(network, hydraulic.flows)
    for key, node in network.port_nodes.items():
        inst_id, port_id = key.split(':', 1)
        prefix = f'{inst_id}.{port_id}'
        variables[f'{prefix}.pressure_pa'] = float(hydraulic.pressures[node])
        variables[f'{prefix}.mass_flow_kg_s'] = port_flows.get(key)
        state = thermal.port_states[key] if thermal is not None else None
        variables[f'{prefix}.temperature_k'] = state.temperature_k if state else network.parameters[inst_id].get('temperature_k')
        if state is not None:
            for name in PORT_THERMAL_FIELDS:
                variables[f'{prefix}.{name}'] = getattr(state, name)
    for inst, params in network.parameters.items():
        variables.update({f'{inst}.param.{k}': v for k,v in params.items() if isinstance(v, (float,int))})
    conflicts = variables.keys() & hydraulic.module_variables.keys()
    if conflicts:
        raise RuntimeErrorBase(f'模块输出不能覆盖网络求解变量：{sorted(conflicts)}')
    variables.update(hydraulic.module_variables)
    metrics = {'pressure_residual_pa': hydraulic.pressure_residual, 'mass_residual_kg_s': hydraulic.mass_residual,
               'iterations': hydraulic.iterations, 'node_count': len(network.node_keys), 'branch_count': len(network.branches)}
    if thermal is not None:
        metrics.update({'thermal_iterations': thermal.iterations, 'coupling_iterations': coupling,
                        'energy_residual_w': thermal.energy_residual_w, 'reference_heat_w': thermal.reference_heat_w})
    return RunFrame(status='converged', valid=True, time_s=time_s, variables=variables, diagnostics=diagnostics,
                    metrics=metrics)


def solve_steady(network):
    return snapshot(network, solve_network(network))


def solve_dynamic(network, duration_s, dt_s, should_cancel=None):
    """Quasi-steady timeline. `should_cancel` is an optional cooperative hook.

    It is polled once per timeline frame, *before* that frame is solved, so the
    frame already in flight always finishes. It may also block (a pause). When
    it reports cancellation the frames computed so far are discarded and
    `SolveCancelled` is raised; the default `None` keeps every existing caller
    byte-for-byte unchanged. Every frame warm-starts from the previous one.
    """
    if not math.isfinite(duration_s) or not math.isfinite(dt_s) or dt_s <= 0 or duration_s <= 0:
        raise ValueError('运行时长和步长必须是有限正数')
    if duration_s > 2000 * dt_s:
        raise ValueError('单次准稳态运行最多 2001 帧')
    count = math.ceil(duration_s / dt_s)
    if network.project.solver.thermal:
        text = '准稳态时间序列：每步求解水力与热力并提交 Python 模块状态；未计算容积与管道热容（热惯性）'
    else:
        text = '准稳态时间序列：每步求解水力并提交 Python 模块状态；未计算容积和热惯性'
    warning = Diagnostic(code='DYNAMIC_QUASI_STEADY', message=text, severity='warning')
    runners = _python_runners(network)
    frames = []
    try:
        service = property_service(network.project.fluid) if network.project.solver.thermal else None
        previous = None
        for i in range(count + 1):
            if should_cancel is not None and should_cancel():
                # Completed frames are handed to the caller instead of dropped,
                # so a cancelled run can still report its partial timeline.
                raise SolveCancelled('运行已取消', frames)
            time_s = min(i * dt_s, duration_s)
            result = solve_network(network, runners, time_s, warm=previous, service=service)
            previous = result
            hydraulic = result.hydraulic
            frame = snapshot(network, result, time_s, warning)
            frames.append(frame)
            if i == 0:
                continue
            for instance_id, runner in runners.items():
                definition = network.modules[network.instances[instance_id].module_id]
                ports = {port.id: result.port_states[f'{instance_id}:{port.id}'] for port in definition.ports}
                channels = {}
                for branch, flow in zip(network.branches, hydraulic.flows):
                    if branch.instance_id == instance_id:
                        channels[branch.channel_id] = ChannelResult(mass_flow_kg_s=float(flow),
                                                                     pressure_drop_pa=float(hydraulic.pressures[branch.start_node] - hydraulic.pressures[branch.end_node]))
                committed = runner.commit_step(CommitStepRequest(run_id='dynamic', instance_id=instance_id,
                    time_s=time_s, dt_s=time_s - frames[-2].time_s, converged_ports=ports), channels=channels)
                if any(d.severity == 'error' for d in committed.diagnostics):
                    raise RuntimeErrorBase('; '.join(d.message for d in committed.diagnostics))
                protected = frame.variables.keys() - hydraulic.module_variables.keys()
                if protected & {f'{instance_id}.{k}' for k in committed.variables}:
                    raise RuntimeErrorBase('commit_step 输出不能覆盖网络求解变量')
                frame.variables.update({f'{instance_id}.{k}':v for k,v in committed.variables.items()})
                frame.variables.update({f'{instance_id}.state.{k}':v for k,v in committed.state.items() if isinstance(v,(float,int,str,bool)) or v is None})
                frame.diagnostics.extend(committed.diagnostics)
        return frames
    finally:
        _close_runners(runners)
