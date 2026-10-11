from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from .compiler import CompiledBranch, CompiledNetwork
from .models import CommitStepRequest, Diagnostic, EvaluateRequest, PortState, RunFrame, NetworkRelation
from .properties import PropertyError, property_service
from .runtime import ChannelResult, WorkerProcess, RuntimeErrorBase

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


def _solve_hydraulics(network: CompiledNetwork, runners, time_s=0.) -> HydraulicResult:
    n_nodes, fixed = len(network.node_keys), network.fixed_pressures
    unknown = [n for n in range(n_nodes) if n not in fixed]
    options = network.project.solver

    try:
        # Keep the historical incompressible-water regression deterministic.
        # Other configured fluids obtain transport properties from CoolProp.
        if network.project.fluid.fluid.lower() in {'water', 'if97::water'}:
            density, viscosity = RHO_WATER, MU_WATER
        else:
            reference_pressure = float(np.mean(list(fixed.values()))) if fixed else 250000.0
            reference_temperature = 293.15
            for params in network.parameters.values():
                if isinstance(params.get('temperature_k'), (int, float)):
                    reference_temperature = float(params['temperature_k'])
                    break
            state = property_service(network.project.fluid).state_pt(reference_pressure, reference_temperature)
            density, viscosity = state.density_kg_m3, state.viscosity_pa_s
    except PropertyError as error:
        raise ValueError(str(error)) from error

    python_runners = runners
    iteration_id = 0
    module_variables, module_diagnostics = {}, []
    final_relations = {}

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
                ports[port.id] = PortState(
                    pressure_pa=float(pressures[node]),
                    temperature_k=float(network.parameters[instance_id].get('temperature_k', 293.15)),
                    density_kg_m3=density,
                    viscosity_pa_s=viscosity,
                )
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
        for branch, flow in zip(network.branches, flows):
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
                    network, branch, float(flow), density, viscosity, relation))
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

    initial = np.concatenate((np.full(len(unknown), np.mean(list(fixed.values())) / PRESSURE_SCALE), np.full(len(network.branches), .1)))
    result = least_squares(residual, initial, max_nfev=options.max_iterations, xtol=1e-12, ftol=1e-12, gtol=1e-12, x_scale='jac')
    pressures, flows = unpack(result.x)
    drops, balance, closed, constraints = physical_residual(result.x)
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
    for branch, flow in zip(network.branches, flows):
        relation = final_relations.get((branch.instance_id,branch.channel_id))
        if relation and relation.kind == 'pump' or relation is None and branch.solver_model == 'pump_curve':
            params = relation.parameters if relation else network.parameters[branch.instance_id]
            q = flow / (params.get('density_kg_m3') or density) * 3600
            if q < -1e-8 or q > params['head_curve'][-1][0] * params['speed_ratio'] + 1e-8:
                raise ValueError(f'{branch.instance_id} 工作点 {q:.6g} m³/h 超出泵曲线范围；反向流和曲线外工况尚未支持')
    return HydraulicResult(pressures, flows, int(result.nfev), pressure_error, mass_error, density, viscosity,
                           module_variables.copy(), module_diagnostics.copy())


def solve_hydraulics(network: CompiledNetwork, runners=None, time_s=0.) -> HydraulicResult:
    """Solve one hydraulic state, isolating every Python module in a Worker by default."""
    owned = runners is None
    active = _python_runners(network) if owned else runners
    try:
        return _solve_hydraulics(network, active, time_s)
    finally:
        if owned:
            _close_runners(active)


def snapshot(network, result, time_s=0., warning=None):
    variables, port_flows = {}, {}
    density = result.density
    diagnostics = list(network.diagnostics) + result.module_diagnostics + ([warning] if warning else [])
    for branch, flow in zip(network.branches, result.flows):
        q = float(flow)
        prefix = f'{branch.instance_id}.{branch.channel_id}'
        values = {'mass_flow_kg_s': q, 'volume_flow_m3_h': q / density * 3600,
                  'inlet_pressure_pa': float(result.pressures[branch.start_node]),
                  'outlet_pressure_pa': float(result.pressures[branch.end_node]),
                  'pressure_drop_pa': float(result.pressures[branch.start_node] - result.pressures[branch.end_node])}
        variables.update({f'{prefix}.{k}': v for k, v in values.items()})
        if sum(b.instance_id == branch.instance_id for b in network.branches) == 1:
            variables.update({f'{branch.instance_id}.{k}': v for k, v in values.items()})
        for port, value in ((branch.input_port, q), (branch.output_port, -q)):
            key = f'{branch.instance_id}:{port}'
            port_flows[key] = port_flows.get(key, 0.) + value
        if branch.solver_model == 'pump_curve' and network.modules[network.instances[branch.instance_id].module_id].runtime != 'python':
            variables[f'{branch.instance_id}.shaft_power_w'] = -values['pressure_drop_pa'] * q / density / network.parameters[branch.instance_id]['efficiency_ratio']
    # Boundary and junction port flow follows its directly connected equipment port.
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
    for key, node in network.port_nodes.items():
        inst_id, port_id = key.split(':', 1)
        prefix = f'{inst_id}.{port_id}'
        variables[f'{prefix}.pressure_pa'] = float(result.pressures[node])
        variables[f'{prefix}.mass_flow_kg_s'] = port_flows.get(key)
        variables[f'{prefix}.temperature_k'] = network.parameters[inst_id].get('temperature_k')
    for inst, params in network.parameters.items():
        variables.update({f'{inst}.param.{k}': v for k,v in params.items() if isinstance(v, (float,int))})
    conflicts = variables.keys() & result.module_variables.keys()
    if conflicts:
        raise RuntimeErrorBase(f'模块输出不能覆盖网络求解变量：{sorted(conflicts)}')
    variables.update(result.module_variables)
    return RunFrame(status='converged', valid=True, time_s=time_s, variables=variables, diagnostics=diagnostics,
                    metrics={'pressure_residual_pa': result.pressure_residual, 'mass_residual_kg_s': result.mass_residual,
                             'iterations': result.iterations, 'node_count': len(network.node_keys), 'branch_count': len(network.branches)})


def solve_steady(network):
    return snapshot(network, solve_hydraulics(network))


def solve_dynamic(network, duration_s, dt_s, should_cancel=None):
    """Quasi-steady timeline. `should_cancel` is an optional cooperative hook.

    It is polled once per timeline frame, *before* that frame is solved, so the
    frame already in flight always finishes. It may also block (a pause). When
    it reports cancellation the frames computed so far are discarded and
    `SolveCancelled` is raised; the default `None` keeps every existing caller
    byte-for-byte unchanged.
    """
    if not math.isfinite(duration_s) or not math.isfinite(dt_s) or dt_s <= 0 or duration_s <= 0:
        raise ValueError('运行时长和步长必须是有限正数')
    if duration_s > 2000 * dt_s:
        raise ValueError('单次准稳态运行最多 2001 帧')
    count = math.ceil(duration_s / dt_s)
    warning = Diagnostic(code='DYNAMIC_QUASI_STEADY', message='准稳态时间序列：每步求解水力并提交 Python 模块状态；未计算容积和热惯性', severity='warning')
    runners = _python_runners(network)
    frames = []
    try:
        for i in range(count + 1):
            if should_cancel is not None and should_cancel():
                # Completed frames are handed to the caller instead of dropped,
                # so a cancelled run can still report its partial timeline.
                raise SolveCancelled('运行已取消', frames)
            time_s = min(i * dt_s, duration_s)
            result = solve_hydraulics(network, runners, time_s)
            frame = snapshot(network, result, time_s, warning)
            frames.append(frame)
            if i == 0:
                continue
            for instance_id, runner in runners.items():
                definition = network.modules[network.instances[instance_id].module_id]
                ports = {}
                channels = {}
                for port in definition.ports:
                    key = f'{instance_id}:{port.id}'
                    node = network.port_nodes[key]
                    ports[port.id] = PortState(
                        pressure_pa=float(result.pressures[node]),
                        temperature_k=float(network.parameters[instance_id].get('temperature_k', 293.15)),
                        density_kg_m3=result.density,
                        viscosity_pa_s=result.viscosity,
                        mass_flow_kg_s=frame.variables.get(f'{instance_id}.{port.id}.mass_flow_kg_s'),
                    )
                for branch, flow in zip(network.branches, result.flows):
                    if branch.instance_id == instance_id:
                        channels[branch.channel_id] = ChannelResult(mass_flow_kg_s=float(flow),
                                                                     pressure_drop_pa=float(result.pressures[branch.start_node] - result.pressures[branch.end_node]))
                committed = runner.commit_step(CommitStepRequest(run_id='dynamic', instance_id=instance_id,
                    time_s=time_s, dt_s=time_s - frames[-2].time_s, converged_ports=ports), channels=channels)
                if any(d.severity == 'error' for d in committed.diagnostics):
                    raise RuntimeErrorBase('; '.join(d.message for d in committed.diagnostics))
                protected = frame.variables.keys() - result.module_variables.keys()
                if protected & {f'{instance_id}.{k}' for k in committed.variables}:
                    raise RuntimeErrorBase('commit_step 输出不能覆盖网络求解变量')
                frame.variables.update({f'{instance_id}.{k}':v for k,v in committed.variables.items()})
                frame.variables.update({f'{instance_id}.state.{k}':v for k,v in committed.state.items() if isinstance(v,(float,int,str,bool)) or v is None})
                frame.diagnostics.extend(committed.diagnostics)
        return frames
    finally:
        _close_runners(runners)
