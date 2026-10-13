from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

from .compiler import CompilationError, CompiledBranch, CompiledNetwork, TankState, instance_fluids, service_at
from .models import CommitStepRequest, Diagnostic, EvaluateRequest, FluidState, PortState, RunFrame, NetworkRelation
from .properties import PropertyError, is_pure_water, property_service
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


class HydraulicNotConverged(ValueError):
    """The hydraulic iteration did not meet its tolerances (a smaller time step may help)."""
    code = 'HYDRAULIC_NOT_CONVERGED'


class SolveFailed(CompilationError):
    """A dynamic run stopped at a step or event; `frames` keeps the accepted timeline up to it."""

    def __init__(self, code, message, instance_id=None, frames=None):
        super().__init__(code, message, instance_id)
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
    # Net inflow (kg/s) of every tank solved as a storage node in this step.
    storage_rates: dict[int, float] = field(default_factory=dict)


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
    python_instances = [i for i in network.instances.values() if network.modules[i.module_id].runtime == 'python']
    if network.project.solver.batch_modules and len(python_instances) > 1:
        from .batch import BatchRunners
        return BatchRunners(network, python_instances)
    runners = {}
    try:
        for instance_id, instance in network.instances.items():
            definition = network.modules[instance.module_id]
            if definition.runtime == 'python':
                fluid, port_fluids = instance_fluids(network, instance_id)
                runner = WorkerProcess(definition, network.parameters[instance_id], fluid,
                                       initial_state={}, port_fluids=port_fluids)
                runners[instance_id] = runner
                runner.initialize()
    except Exception:
        _close_runners(runners)
        raise
    return runners


def _close_runners(runners):
    if hasattr(runners, 'close'):
        runners.close()
        return
    for runner in runners.values():
        try:
            runner.close()
        except Exception:
            pass


def reference_properties(network: CompiledNetwork, circuit: int | None = None) -> tuple[float, float]:
    """Constant density/viscosity used by the hydraulics unless property coupling is 'node'.

    One pair for the whole network, or for one circuit of a multi-fluid network (pressure and
    temperature then come from that circuit's boundaries and devices only); circuit 0 by default.
    """
    if network.mixed and circuit is None:
        circuit = 0
    fluid = network.circuit_fluids[circuit] if network.mixed else network.project.fluid
    inside = (lambda node: network.node_circuit[node] == circuit) if network.mixed else (lambda node: True)
    try:
        # Keep the historical incompressible-water regression deterministic for every
        # spelling of pure water. Other configured fluids obtain properties from CoolProp.
        if is_pure_water(fluid):
            return RHO_WATER, MU_WATER
        # Tank pressures move during a run; the reference must not, so they enter with their initial value.
        fixed = {**network.fixed_pressures, **{node: spec.initial_pressure_pa for node, spec in network.storage.items()}}
        fixed = {node: value for node, value in fixed.items() if inside(node)}
        reference_pressure = float(np.mean(list(fixed.values()))) if fixed else 250000.0
        reference_temperature = 293.15
        for instance_id, params in network.parameters.items():
            ports = network.modules[network.instances[instance_id].module_id].ports
            if ports and not inside(network.port_nodes[f'{instance_id}:{ports[0].id}']):
                continue
            if isinstance(params.get('temperature_k'), (int, float)):
                reference_temperature = float(params['temperature_k'])
                break
        state = property_service(fluid).state_pt(reference_pressure, reference_temperature)
        if state.viscosity_pa_s is None:
            raise PropertyError('PROPERTY_FAILURE', f'{fluid.fluid} 在参考状态下没有黏度（REFPROP 对部分工质和混合物'
                                '没有输运方程），不能用于管网水力计算')
        return state.density_kg_m3, state.viscosity_pa_s
    except PropertyError as error:
        raise ValueError(str(error)) from error


def reference_arrays(network: CompiledNetwork) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Reference density/viscosity per node and per branch (a branch lies inside one circuit)."""
    n, m = len(network.node_keys), len(network.branches)
    if not network.mixed:
        density, viscosity = reference_properties(network)
        return np.full(n, density), np.full(n, viscosity), np.full(m, density), np.full(m, viscosity)
    pairs = [reference_properties(network, c) for c in range(len(network.circuit_fluids))]
    rho_n = np.array([pairs[network.node_circuit[node]][0] for node in range(n)])
    mu_n = np.array([pairs[network.node_circuit[node]][1] for node in range(n)])
    return rho_n, mu_n, rho_n[[b.start_node for b in network.branches]], mu_n[[b.start_node for b in network.branches]]


def _solve_hydraulics(network: CompiledNetwork, runners, time_s=0., branch_density=None, branch_viscosity=None,
                      port_base: dict[str, PortState] | None = None, initial=None, storage_step=None) -> HydraulicResult:
    """Solve pressures and branch flows.

    With `storage_step` = (dt_s, {node: TankState}) each listed tank is no longer a fixed pressure:
    its unknown is the net inflow r (kg/s), the balance row becomes Σq_in − r = 0 and the pressure
    follows from implicit Euler, p = p_surface + g/A·(M_old + dt·r). Using r keeps the row in the
    same units as every other mass balance (a tank pressure unknown would need a 1e-14 Pa tolerance).
    """
    n_nodes = len(network.node_keys)
    dt_s, tank_old = storage_step[:2] if storage_step is not None else (None, {})
    tanks = [node for node in sorted(network.storage) if node in tank_old]
    fixed = {node: value for node, value in network.fixed_pressures.items() if node not in tank_old}
    unknown = [n for n in range(n_nodes) if n not in fixed and n not in tank_old]
    options = network.project.solver
    m = len(network.branches)
    density, viscosity = reference_properties(network)
    rho_n, mu_n, rho_ref, mu_ref = reference_arrays(network)
    rho_b = rho_ref if branch_density is None else np.asarray(branch_density, dtype=float)
    mu_b = mu_ref if branch_viscosity is None else np.asarray(branch_viscosity, dtype=float)

    python_runners = runners
    iteration_id = 0
    module_variables, module_diagnostics = {}, []
    final_relations = {}

    def trial_port(instance_id, port_id, pressure):
        key = f'{instance_id}:{port_id}'
        if port_base is not None and key in port_base:
            return port_base[key].model_copy(update={'pressure_pa': pressure, 'mass_flow_kg_s': None})
        node = network.port_nodes[key]
        return PortState(pressure_pa=pressure,
                         temperature_k=float(network.parameters[instance_id].get('temperature_k', 293.15)),
                         density_kg_m3=float(rho_n[node]), viscosity_pa_s=float(mu_n[node]))

    def evaluate_python_relations(pressures):
        nonlocal iteration_id
        iteration_id += 1
        relations = {}
        module_variables.clear()
        module_diagnostics.clear()
        final_relations.clear()
        requests = {}
        for instance_id, runner in python_runners.items():
            instance = network.instances[instance_id]
            definition = network.modules[instance.module_id]
            ports = {}
            for port in definition.ports:
                node = network.port_nodes[f'{instance_id}:{port.id}']
                ports[port.id] = trial_port(instance_id, port.id, float(pressures[node]))
            requests[instance_id] = EvaluateRequest(run_id='solve', instance_id=instance_id,
                iteration_id=iteration_id, time_s=time_s, trial_ports=ports, readonly_state=runner.state)
        responses = python_runners.evaluate(requests) if hasattr(python_runners, 'evaluate') else {
            key: python_runners[key].evaluate(request) for key, request in requests.items()}
        for instance_id, runner in python_runners.items():
            instance = network.instances[instance_id]
            definition = network.modules[instance.module_id]
            response = responses[instance_id]
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
        rates = vector[len(unknown):len(unknown) + len(tanks)]
        for node, rate in zip(tanks, rates):
            spec = network.storage[node]
            pressures[node] = spec.pressure(tank_old[node].mass_kg + dt_s * float(rate))
        return pressures, vector[len(unknown) + len(tanks):]

    def unpack_rates(vector):
        return {node: float(rate) for node, rate in zip(tanks, vector[len(unknown):len(unknown) + len(tanks)])}

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
        rates = unpack_rates(vector)
        storage_balance = [balance[node] - rates[node] for node in tanks]
        return np.asarray(drops), np.concatenate((balance[unknown], storage_balance)), closed, constraints

    def residual(vector):
        drops, balance, _, constraints = physical_residual(vector)
        _, flows = unpack(vector)
        scaled = drops / PRESSURE_SCALE
        for idx, value in constraints.items():
            scaled[idx] = value
        return np.concatenate((scaled, balance))

    size = len(unknown) + len(tanks) + m
    # A loop held only by tanks has no fixed pressure left; start from the tanks' current pressures.
    level = list(fixed.values()) or [network.storage[node].pressure(tank_old[node].mass_kg) for node in tanks]
    cold = np.concatenate((np.full(len(unknown), np.mean(level) / PRESSURE_SCALE), np.zeros(len(tanks)), np.full(m, .1)))
    warm_start = initial is not None and np.shape(initial) == (size,) and np.all(np.isfinite(initial))
    if warm_start:
        start = np.array(initial, dtype=float)
        # Quadratic laws (q·|q|) have zero slope at q=0, so a branch that carried no flow in the
        # previous frame would stall least_squares on gtol; restart such flows from the cold guess.
        flows_start = start[len(unknown) + len(tanks):]
        flows_start[np.abs(flows_start) < max(1e-6, 100 * options.mass_tolerance_kg_s)] = .1
    else:
        start = cold

    def attempt(vector):
        sparse_options = {}
        if options.hydraulic_method == 'sparse':
            node_columns = {node: column for column, node in enumerate(unknown + tanks)}
            pattern = lil_matrix((size, size), dtype=int)
            for idx, branch in enumerate(network.branches):
                dependencies = {branch.start_node, branch.end_node}
                if branch.instance_id in python_runners:
                    definition = network.modules[network.instances[branch.instance_id].module_id]
                    dependencies.update(network.port_nodes[f'{branch.instance_id}:{p.id}'] for p in definition.ports)
                for node in dependencies:
                    if node in node_columns:
                        pattern[idx, node_columns[node]] = 1
                pattern[idx, len(node_columns) + idx] = 1
                for node in (branch.start_node, branch.end_node):
                    if node in node_columns:
                        pattern[m + node_columns[node], len(node_columns) + idx] = 1
            for node in tanks:
                pattern[m + node_columns[node], node_columns[node]] = 1
            sparse_options = {'jac_sparsity': pattern.tocsr(), 'tr_solver': 'lsmr',
                              'tr_options': {'atol': 1e-13, 'btol': 1e-13, 'maxiter': max(100, size*4)}}
        result = least_squares(residual, vector, max_nfev=options.max_iterations, xtol=1e-12, ftol=1e-12, gtol=1e-12, x_scale='jac', **sparse_options)
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
    # A tank row fixes its pressure through the stored mass, so it is a reference as well.
    reached, pending = set(fixed) | set(tanks), list(fixed) + tanks
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
        raise HydraulicNotConverged(f'水力求解未收敛：压力残差 {pressure_error:.6g} Pa，质量残差 {mass_error:.6g} kg/s；{result.message}')
    if np.any(pressures <= 0) or not np.all(np.isfinite(result.x)):
        raise HydraulicNotConverged('求解产生非正绝对压力或非有限结果')
    for idx, (branch, flow) in enumerate(zip(network.branches, flows)):
        relation = final_relations.get((branch.instance_id,branch.channel_id))
        if relation and relation.kind == 'pump' or relation is None and branch.solver_model == 'pump_curve':
            params = relation.parameters if relation else network.parameters[branch.instance_id]
            q = flow / (params.get('density_kg_m3') or float(rho_b[idx])) * 3600
            if q < -1e-8 or q > params['head_curve'][-1][0] * params['speed_ratio'] + 1e-8:
                raise ValueError(f'{branch.instance_id} 工作点 {q:.6g} m³/h 超出泵曲线范围；反向流和曲线外工况尚未支持')
    return HydraulicResult(pressures, flows, int(result.nfev), pressure_error, mass_error, density, viscosity,
                           module_variables.copy(), module_diagnostics.copy(), rho_b, mu_b, dict(final_relations),
                           np.array(result.x, copy=True), unpack_rates(result.x))


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
            model = network.modules[inst.module_id].solver_model
            if model not in ('junction', 'tank'):
                continue
            keys = [f'{inst.id}:{p.id}' for p in network.modules[inst.module_id].ports]
            connected = {key for pair in pairs for key in pair}
            for key in keys:
                if key not in connected:
                    port_flows[key] = 0.
            if model == 'tank':
                continue  # a tank stores the difference; its port flows do not have to cancel
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
            density, viscosity = (reference_properties(network, network.node_circuit[node]) if network.mixed
                                  else (hydraulic.density, hydraulic.viscosity))
            states[key] = PortState(pressure_pa=pressure,
                                    temperature_k=float(network.parameters[instance_id].get('temperature_k', 293.15)),
                                    density_kg_m3=density, viscosity_pa_s=viscosity,
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


REFERENCE_DENSITY_RTOL = 0.02


def _warn_reference_density(network: CompiledNetwork, thermal: ThermalResult, reference) -> None:
    """reference mode keeps one constant density in the hydraulics; say so when the fluid has moved away from it.

    `reference` is one density, or one per node for a multi-fluid network."""
    worst, where = 0.0, None
    for node, state in enumerate(thermal.node_states):
        ref = float(reference[node]) if np.ndim(reference) else reference
        deviation = abs(state.density_kg_m3 - ref) / ref
        if deviation > worst:
            worst, where = deviation, node
    if worst > REFERENCE_DENSITY_RTOL:
        state = thermal.node_states[where]
        reference = float(reference[where]) if np.ndim(reference) else reference
        instance = network.node_keys[where].split(':', 1)[0]
        thermal.diagnostics.append(Diagnostic(code='REFERENCE_DENSITY_DEVIATION', severity='warning', instance_id=instance,
            message=f'{instance} 处密度 {state.density_kg_m3:.1f} kg/m³（{state.temperature_k - 273.15:.1f} °C）与水力参考密度 '
                    f'{reference:.1f} kg/m³ 相差 {worst:.1%}；reference 模式的流量未计入这一差别，'
                    "需要时把 property_coupling 设为 'node'"))


def solve_network(network: CompiledNetwork, runners=None, time_s=0., warm: NetworkResult | None = None,
                  service=None, storage_step=None) -> NetworkResult:
    """Hydraulics, then (if enabled) the thermal layer, coupled according to SolverOptions.property_coupling.

    `warm` is the previous result for the same network (the previous dynamic frame) and only
    seeds the iterations; it never changes what counts as converged. `storage_step` =
    (dt_s, {node: TankState}) solves the tanks as implicit-Euler storage nodes.
    """
    owned = runners is None
    active = _python_runners(network) if owned else runners
    try:
        return _solve_network(network, active, time_s, warm, service, storage_step)
    finally:
        if owned:
            _close_runners(active)


def _solve_network(network, runners, time_s, warm, service, storage_step=None) -> NetworkResult:
    options = network.project.solver
    start = warm.hydraulic.solution if warm is not None else None
    if not options.thermal:
        hydraulic = _solve_hydraulics(network, runners, time_s, initial=start, storage_step=storage_step)
        return NetworkResult(hydraulic, None, 0, build_port_states(network, hydraulic, None))
    service = service or property_service(network.project.fluid)
    h_start = warm.thermal.enthalpies if warm is not None and warm.thermal is not None else None
    if options.property_coupling == 'reference':
        port_base = None
        if runners:
            rho_n, mu_n, _, _ = reference_arrays(network)
            port_base = {key: state.model_copy(update={'density_kg_m3': float(rho_n[network.port_nodes[key]]),
                                                       'viscosity_pa_s': float(mu_n[network.port_nodes[key]])})
                         for key, state in _node_ports(network, initial_guess(network, service)).items()}
        hydraulic = _solve_hydraulics(network, runners, time_s, port_base=port_base, initial=start,
                                      storage_step=storage_step)
        thermal = solve_thermal(network, service, hydraulic.pressures, hydraulic.flows, hydraulic.relations,
                                shaft_power(network, hydraulic), h_start, storage_step)
        _warn_reference_density(network, thermal, reference_arrays(network)[0] if network.mixed else reference_properties(network)[0])
        return NetworkResult(hydraulic, thermal, 1, build_port_states(network, hydraulic, thermal))

    # node coupling: properties frozen during each hydraulic solve, updated between passes.
    if warm is not None and warm.thermal is not None and warm.hydraulic.branch_density is not None:
        rho_b, mu_b = warm.hydraulic.branch_density, warm.hydraulic.branch_viscosity
        node_states, previous_t = warm.thermal.node_states, np.array([s.temperature_k for s in warm.thermal.node_states])
    else:
        _, _, rho_b, mu_b = reference_arrays(network)
        node_states, previous_t = initial_guess(network, service), None
    for iteration in range(1, options.max_coupling_iterations + 1):
        hydraulic = _solve_hydraulics(network, runners, time_s, branch_density=rho_b, branch_viscosity=mu_b,
                                      port_base=_node_ports(network, node_states) if runners else None, initial=start,
                                      storage_step=storage_step)
        thermal = solve_thermal(network, service, hydraulic.pressures, hydraulic.flows, hydraulic.relations,
                                shaft_power(network, hydraulic), h_start, storage_step)
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


def node_net_inflow(network: CompiledNetwork, flows, node: int) -> float:
    """Σ branch flow arriving at `node` minus Σ leaving it, kg/s."""
    total = 0.0
    for branch, flow in zip(network.branches, flows):
        if branch.end_node == node:
            total += float(flow)
        if branch.start_node == node:
            total -= float(flow)
    return total


def tank_states_from(network: CompiledNetwork, result: NetworkResult, previous: dict[int, TankState] | None,
                     dt_s: float | None) -> dict[int, TankState]:
    """Tank state after an accepted step (or the initial state when `previous` is None)."""
    states = {}
    for node, spec in network.storage.items():
        if previous is None:
            states[node] = TankState(spec.initial_mass_kg, spec.initial_enthalpy_j_kg)
            continue
        mass = previous[node].mass_kg + dt_s * result.hydraulic.storage_rates[node]
        enthalpy = result.thermal.enthalpies[node] if result.thermal is not None else previous[node].enthalpy_j_kg
        states[node] = TankState(mass, float(enthalpy))
    return states


def tank_variables(network: CompiledNetwork, result: NetworkResult, tanks: dict[int, TankState], service):
    """`<tank>.state.*` frame variables and storage metrics for the given tank states."""
    variables, mass_rate, power = {}, 0.0, 0.0
    hydraulic, thermal = result.hydraulic, result.thermal
    for node, spec in network.storage.items():
        tank = tanks[node]
        net = hydraulic.storage_rates.get(node, node_net_inflow(network, hydraulic.flows, node))
        pressure = spec.pressure(tank.mass_kg)
        if thermal is not None:
            state = thermal.node_states[node]
        else:
            # Without the thermal layer the tank keeps its initial temperature.
            state = service_at(network, node, service).state_pt(pressure, spec.initial_temperature_k)
        level = tank.mass_kg / (state.density_kg_m3 * spec.area_m2)
        variables.update({f'{spec.instance_id}.state.mass_kg': tank.mass_kg,
                          f'{spec.instance_id}.state.level_m': level,
                          f'{spec.instance_id}.state.volume_m3': level * spec.area_m2,
                          f'{spec.instance_id}.state.temperature_k': state.temperature_k,
                          f'{spec.instance_id}.state.net_inflow_kg_s': net})
        mass_rate += net
        if thermal is not None:
            power += float(thermal.storage_power_w.get(node, 0.0))
    metrics = {'storage_mass_rate_kg_s': mass_rate}
    if thermal is not None:
        metrics['storage_power_w'] = power
    return variables, metrics


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


def cell_variables(network: CompiledNetwork, result: NetworkResult, service):
    """`<pipe>.state.mean_temperature_k` and `stored_power_w` for pipes with heat capacity."""
    variables, power = {}, 0.0
    thermal = result.thermal
    for j, values in thermal.cell_enthalpies.items():
        branch = network.branches[j]
        pressure = float(result.hydraulic.pressures[branch.start_node] + result.hydraulic.pressures[branch.end_node]) / 2
        try:
            mean = float(np.mean([service_at(network, branch.start_node, service).state_ph(pressure, float(value)).temperature_k
                                  for value in values]))
        except PropertyError as error:
            raise CompilationError(error.code, f'{branch.instance_id} 管段热容状态物性计算失败：{error}',
                                   branch.instance_id) from error
        stored = thermal.cell_power_w[j]
        variables.update({f'{branch.instance_id}.state.mean_temperature_k': mean,
                          f'{branch.instance_id}.state.stored_power_w': stored})
        power += stored
    return variables, power


def _with_states(network, frame: RunFrame, result: NetworkResult, tanks: dict[int, TankState], service) -> RunFrame:
    """Add tank and pipe-cell state variables and the storage metrics to a frame."""
    cells = result.thermal is not None and bool(result.thermal.cell_enthalpies)
    if not network.storage and not cells:
        return frame
    variables, metrics = tank_variables(network, result, tanks, service) if network.storage else ({}, {})
    if cells:
        cell_values, cell_power = cell_variables(network, result, service)
        variables.update(cell_values)
        metrics['storage_power_w'] = metrics.get('storage_power_w', 0.0) + cell_power
    conflicts = frame.variables.keys() & variables.keys()
    if conflicts:
        raise RuntimeErrorBase(f'模块输出不能覆盖状态变量：{sorted(conflicts)}')
    frame.variables.update(variables)
    frame.metrics.update(metrics)
    return frame


def solve_steady(network):
    result = solve_network(network)
    frame = snapshot(network, result)
    if network.storage:
        ids = [spec.instance_id for spec in network.storage.values()]
        names = '、'.join(ids)
        frame.diagnostics.append(Diagnostic(code='STEADY_TANK_AS_RESERVOIR', severity='info', instance_id=ids[0],
            message=f'稳态计算把水箱（{names}）当作液位不变的大容器：压力取初始液位的静压；'
                    'state.net_inflow_kg_s 是液位变化的趋势，液位随时间的变化请用动态计算'))
    if network.storage or has_cells(network):
        service = property_service(network.project.fluid)
        frame = _with_states(network, frame, result, tank_states_from(network, result, None, None), service)
    return frame


# Failures a smaller step can cure. Anything else (module errors, curve limits, invalid input) is final.
RETRYABLE_CODES = {'HYDRAULIC_NOT_CONVERGED', 'THERMAL_NOT_CONVERGED', 'COUPLING_NOT_CONVERGED', 'PHASE_UNSUPPORTED',
                   'PROPERTY_FAILURE', 'THERMAL_NOT_FINITE', 'THERMAL_ENERGY_IMBALANCE'}


def _retryable(error: Exception) -> bool:
    if isinstance(error, HydraulicNotConverged):
        return True
    return isinstance(error, CompilationError) and error.diagnostic.code in RETRYABLE_CODES


def has_cells(network: CompiledNetwork) -> bool:
    """Some pipe declares heat capacity (thermal_cells > 0); it only matters with the thermal layer on."""
    return network.project.solver.thermal and any(
        b.solver_model == 'pipe' and int(network.parameters[b.instance_id].get('thermal_cells', 0) or 0) > 0
        for b in network.branches)


def has_state(network: CompiledNetwork) -> bool:
    """True when the dynamic run must integrate states instead of chaining quasi-steady frames."""
    return bool(network.storage) or has_cells(network)


def solve_dynamic(network, duration_s, dt_s, should_cancel=None):
    from .simulation import run_dynamic
    return run_dynamic(network, duration_s, dt_s, should_cancel)


def _step_network(network: CompiledNetwork, tanks: dict[int, TankState], service) -> CompiledNetwork:
    """Network view for one implicit step: tank boundary entries carry the accepted state.

    The hydraulics drop the tank rows from the fixed set (storage_step); the thermal layer uses
    the boundary entries for the phase check and the starting enthalpy.
    """
    pressures, temperatures = dict(network.fixed_pressures), dict(network.fixed_temperatures)
    for node, spec in network.storage.items():
        pressures[node] = spec.pressure(tanks[node].mass_kg)
        if network.project.solver.thermal:
            try:
                temperatures[node] = service_at(network, node, service).state_ph(pressures[node], tanks[node].enthalpy_j_kg).temperature_k
            except PropertyError as error:
                raise CompilationError(error.code, f'{spec.instance_id} 水箱状态物性计算失败：{error}',
                                       spec.instance_id) from error
    return dataclasses.replace(network, fixed_pressures=pressures, fixed_temperatures=temperatures)


def _commit_modules(network, runners, result: NetworkResult, time_s: float, dt_s: float):
    """commit_step every Python module for an accepted step; returns (variables, diagnostics)."""
    variables, diagnostics = {}, []
    hydraulic = result.hydraulic
    for instance_id, runner in runners.items():
        definition = network.modules[network.instances[instance_id].module_id]
        ports = {port.id: result.port_states[f'{instance_id}:{port.id}'] for port in definition.ports}
        channels = {}
        for branch, flow in zip(network.branches, hydraulic.flows):
            if branch.instance_id == instance_id:
                channels[branch.channel_id] = ChannelResult(mass_flow_kg_s=float(flow),
                    pressure_drop_pa=float(hydraulic.pressures[branch.start_node] - hydraulic.pressures[branch.end_node]))
        committed = runner.commit_step(CommitStepRequest(run_id='dynamic', instance_id=instance_id, time_s=time_s,
                                                         dt_s=dt_s, converged_ports=ports), channels=channels)
        if any(d.severity == 'error' for d in committed.diagnostics):
            raise RuntimeErrorBase('; '.join(d.message for d in committed.diagnostics))
        variables.update({f'{instance_id}.{k}': v for k, v in committed.variables.items()})
        variables.update({f'{instance_id}.state.{k}': v for k, v in committed.state.items()
                          if isinstance(v, (float, int, str, bool)) or v is None})
        diagnostics.extend(committed.diagnostics)
    return variables, diagnostics


def _tank_event(network: CompiledNetwork, tanks: dict[int, TankState], service):
    """(code, spec) of the first tank outside [empty, full] in `tanks`, else None."""
    for node, spec in network.storage.items():
        mass = tanks[node].mass_kg
        if mass < 0:
            return 'TANK_EMPTY', spec
        pressure = spec.pressure(mass)
        try:
            local = service_at(network, node, service)
            density = (local.state_ph(pressure, tanks[node].enthalpy_j_kg) if network.project.solver.thermal
                       else local.state_pt(pressure, spec.initial_temperature_k)).density_kg_m3
        except PropertyError:
            continue
        if mass / (density * spec.area_m2) > spec.height_m:
            return 'TANK_FULL', spec
    return None

