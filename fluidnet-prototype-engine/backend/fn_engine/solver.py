from __future__ import annotations

import dataclasses
import importlib
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import csr_matrix, lil_matrix

from .compiler import CompilationError, CompiledBranch, CompiledNetwork, TankState, instance_fluids, service_at
from .hydraulic_derivatives import (GRAVITY, MU_WATER, RHO_WATER, branch_drop_and_slope,
                                    branch_drop_value, pipe_drop, pump_head)
from .models import CommitStepRequest, Diagnostic, EvaluateRequest, FluidState, PortState, RunFrame, NetworkRelation
from .properties import PropertyError, is_pure_water, property_service
from .runtime import ChannelResult, WorkerProcess, RuntimeErrorBase
from .module_execution import begin_module_step, new_identity, set_module_step
from .thermal import ThermalError, ThermalResult, initial_guess, solve_thermal

# 历史公开入口的再导出：测试与脚本从 fn_engine.solver 导入这些物理函数/常量。
__all__ = ['GRAVITY', 'MU_WATER', 'RHO_WATER', 'branch_drop', 'branch_drop_and_slope', 'pipe_drop', 'pump_head']

PRESSURE_SCALE = 100000.0

# C/D 求解前变换的模块名（延迟导入，避免循环依赖）：
#   partition（D0–D2，分块求解）与 hydraulic_plan（C0–C3，串联压缩）。
_HOOK_MODULES = {'blocks': 'fn_engine.partition', 'compression': 'fn_engine.hydraulic_plan'}


class HydraulicNotConverged(ValueError):
    """The hydraulic iteration did not meet its tolerances (a smaller time step may help)."""
    code = 'HYDRAULIC_NOT_CONVERGED'


class SolveFailed(CompilationError):
    """A dynamic run stopped at a step or event; `frames` keeps the accepted timeline up to it."""

    def __init__(self, code, message, instance_id=None, frames=None):
        super().__init__(code, message, instance_id)
        self.frames = list(frames or ())


@dataclass
class SolveCounters:
    """B0 观测器：一次水力求解的真实调用计数（语义见 docs/numerics/B0_COUNTERS.md）。

    - `nfev` / `njev` 是 SciPy `trf` 报告的基础函数/Jacobian 次数；按 SciPy 的约定，它们
      **不含**数值 Jacobian 的扰动调用，因此不能当作“真实残差调用”使用。
    - `residual_calls` 是本模块 `physical_residual` 的真实调用总数（基础调用 + 扰动调用），
      差额 `perturbation_calls` 就是被旧 `iterations` 字段漏掉的 Jacobian 扰动。
    - `rpc_batches` 统计实际 evaluate RPC（每个非空分片一次），`rpc_instances` 统计
      这些 RPC 内的实例数；父进程命中单列为 `parent_cache_hits`，不计入 RPC。
    """

    residual_calls: int = 0
    jacobian_evaluations: int = 0
    perturbation_calls: int = 0
    solver_attempts: int = 0
    nfev: int = 0
    njev: int = 0
    rpc_batches: int = 0
    rpc_instances: int = 0
    parent_cache_hits: int = 0
    worker_requests: int = 0
    module_evaluations: int = 0
    # 未知量总数（压力 + 水箱净流入 + 支路流量）与 Jacobian 非零元数（稀疏模式）。
    problem_size: int = 0
    jacobian_nnz: int = 0
    # S1：auto 回退记录（空字符串表示没有回退）。
    method_fallback: str = ''
    # J2：解析 Jacobian 退化时的一次性回退记录。
    jacobian_fallback: str = ''
    # 仅在开关打开时记录；键名与 3.2 的分项对应，嵌套/重叠计时不相加。
    timing_s: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {name: (dict(value) if isinstance(value, dict) else value)
                for name, value in dataclasses.asdict(self).items()}


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
    # B0 观测器结果（仅 hydraulic_diagnostics 打开时填充）；旧字段含义全部保留。
    counters: dict | None = None
    # S1 选择记录：请求方法、实际方法、矩阵规模与选择原因（始终记录，便于报告追溯）。
    requested_method: str = 'dense'
    effective_method: str = 'dense'
    method_reason: str = ''
    matrix_size: int = 0
    matrix_nnz: int = 0
    # J2：'analytic'（纯内置解析导数）或 'finite_difference'（含原因）。
    jacobian_mode: str = 'finite_difference'
    jacobian_reason: str = ''


@dataclass
class NetworkResult:
    hydraulic: HydraulicResult
    thermal: ThermalResult | None = None
    coupling_iterations: int = 0
    port_states: dict[str, PortState] = field(default_factory=dict)
    module_step_id: str | None = None


def branch_drop(network: CompiledNetwork, branch: CompiledBranch, flow_kg_s: float, density: float,
                viscosity: float, relation: NetworkRelation | None = None) -> float:
    params, model = network.parameters[branch.instance_id], branch.solver_model
    relation_params = relation.parameters if relation else {}
    if relation:
        model = {'pump':'pump_curve'}.get(relation.kind, relation.kind)
        params = {**params, **relation_params}
        density = relation_params.get('density_kg_m3') or density
        viscosity = relation_params.get('viscosity_pa_s') or viscosity
    if model == 'pump_curve' and params['speed_ratio'] <= 0:
        raise ValueError(f'{branch.instance_id} 停泵阻力模型尚未定义，转速必须大于零')
    return branch_drop_value(model, params, flow_kg_s, density, viscosity)


# S0 的 auto 阈值：由 S0 证据（docs/numerics/results/S0.md）里三类拓扑的实测交叉点取保守值。
# 串联在未知量 59 附近交叉（ratio ≈ 1.0），并联在 16–24，二维多环在 63–94；
# 取 64 让最差的小模型（多环 38–63）仍走稠密，避免超过 10% 的小模型回退门。
AUTO_SPARSE_MIN_SIZE = 64
AUTO_SPARSE_MAX_DENSITY = 0.45
# 稠密矩阵的内存量级是 size²；超过该规模即使稀疏度很高也绝不选稠密。
AUTO_DENSE_MAX_SIZE = 3000


@dataclass
class HydraulicMethodChoice:
    requested: str
    effective: str
    size: int
    nnz: int
    density: float
    reason: str


def jacobian_pattern(network: CompiledNetwork, unknown, tanks, python_runners):
    """水力 Jacobian 的稀疏模式（行=方程，列=未知量）；S0 选择器与 S1 稀疏求解共用。"""
    node_columns = {node: column for column, node in enumerate(unknown + tanks)}
    m = len(network.branches)
    size = len(node_columns) + m
    pattern = lil_matrix((size, size), dtype=int)
    for idx, branch in enumerate(network.branches):
        dependencies = {branch.start_node, branch.end_node}
        if branch.instance_id in python_runners:
            definition = network.modules[network.instances[branch.instance_id].module_id]
            declared = definition.hydraulic_dependencies or {}
            names = declared.get(branch.channel_id, [port.id for port in definition.ports]) if definition.dependency_mode == 'tracked' else [port.id for port in definition.ports]
            dependencies.update(network.port_nodes[f'{branch.instance_id}:{name}'] for name in names)
        for node in dependencies:
            if node in node_columns:
                pattern[idx, node_columns[node]] = 1
        pattern[idx, len(node_columns) + idx] = 1
        for node in (branch.start_node, branch.end_node):
            if node in node_columns:
                pattern[m + node_columns[node], len(node_columns) + idx] = 1
    for node in tanks:
        pattern[m + node_columns[node], node_columns[node]] = 1
    return pattern.tocsr()


def choose_hydraulic_method(requested: str, size: int, nnz: int) -> HydraulicMethodChoice:
    """S0/S1 选择器：只依据真实未知量与 Jacobian 稀疏度，不用实例数代替。"""
    density = nnz / (size * size) if size else 1.0
    if requested == 'dense':
        return HydraulicMethodChoice('dense', 'dense', size, nnz, density, '显式请求 dense')
    if requested == 'sparse':
        return HydraulicMethodChoice('sparse', 'sparse', size, nnz, density, '显式请求 sparse')
    if size >= AUTO_DENSE_MAX_SIZE:
        reason = (f'auto：未知量 {size} ≥ {AUTO_DENSE_MAX_SIZE}，稠密矩阵内存不可接受，'
                  '强制稀疏（与稀疏度无关）')
        method = 'sparse'
    elif size < AUTO_SPARSE_MIN_SIZE:
        reason = f'auto：未知量 {size} < {AUTO_SPARSE_MIN_SIZE}，稠密矩阵的固定开销更小'
        method = 'dense'
    elif density > AUTO_SPARSE_MAX_DENSITY:
        reason = (f'auto：稀疏度 {density:.3f} > {AUTO_SPARSE_MAX_DENSITY}'
                  '（多端口模块依赖密集，稀疏分组扰动接近稠密）')
        method = 'dense'
    else:
        reason = (f'auto：未知量 {size} ≥ {AUTO_SPARSE_MIN_SIZE} 且稀疏度 {density:.3f} '
                  f'≤ {AUTO_SPARSE_MAX_DENSITY}')
        method = 'sparse'
    return HydraulicMethodChoice('auto', method, size, nnz, density, reason)


def _python_runners(network: CompiledNetwork):
    run_id = new_identity('run')
    python_instances = [i for i in network.instances.values() if network.modules[i.module_id].runtime == 'python']
    if network.project.solver.batch_modules and len(python_instances) > 1:
        from .batch import BatchRunners
        return BatchRunners(network, python_instances, run_id=run_id)
    runners = {}
    try:
        for instance_id, instance in network.instances.items():
            definition = network.modules[instance.module_id]
            if definition.runtime == 'python':
                fluid, port_fluids = instance_fluids(network, instance_id)
                runner = WorkerProcess(definition, network.parameters[instance_id], fluid,
                                       initial_state={}, port_fluids=port_fluids, run_id=run_id, instance_id=instance_id,
                                       cache_enabled=network.project.solver.module_cache)
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
    if circuit is None:
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
                      port_base: dict[str, PortState] | None = None, initial=None, storage_step=None,
                      hooks: frozenset[str] | None = None) -> HydraulicResult:
    """Solve pressures and branch flows.

    With `storage_step` = (dt_s, {node: TankState}) each listed tank is no longer a fixed pressure:
    its unknown is the net inflow r (kg/s), the balance row becomes Σq_in − r = 0 and the pressure
    follows from implicit Euler, p = p_surface + g/A·(M_old + dt·r). Using r keeps the row in the
    same units as every other mass balance (a tank pressure unknown would need a 1e-14 Pa tolerance).
    """
    n_nodes = len(network.node_keys)
    solve_started = time.perf_counter()
    dt_s, tank_old = storage_step[:2] if storage_step is not None else (None, {})
    tanks = [node for node in sorted(network.storage) if node in tank_old]
    fixed = {node: value for node, value in network.fixed_pressures.items() if node not in tank_old}
    unknown = [n for n in range(n_nodes) if n not in fixed and n not in tank_old]
    options = network.project.solver
    if hooks is None:
        hooks = frozenset(name for name, enabled in
                          (('blocks', options.hydraulic_blocks), ('compression', options.series_compression))
                          if enabled)
    if hooks:
        # D 在 C 外层：先按真正的独立性分块，块内部再按串联链压缩（模块各自递归调用本函数）。
        for name in ('blocks', 'compression'):
            if name not in hooks:
                continue
            module = importlib.import_module(_HOOK_MODULES[name])
            solved = module.solve_hydraulics_hook(
                network, runners, time_s, branch_density=branch_density, branch_viscosity=branch_viscosity,
                port_base=port_base, initial=initial, storage_step=storage_step, hooks=frozenset(hooks - {name}))
            if solved is not None:
                return solved
    counters = SolveCounters() if options.hydraulic_diagnostics else None
    m = len(network.branches)
    density, viscosity = reference_properties(network)
    rho_n, mu_n, rho_ref, mu_ref = reference_arrays(network)
    rho_b = rho_ref if branch_density is None else np.asarray(branch_density, dtype=float)
    mu_b = mu_ref if branch_viscosity is None else np.asarray(branch_viscosity, dtype=float)

    python_runners = runners
    iteration_id = 0
    module_variables: dict = {}
    module_diagnostics: list = []
    derivative_diagnostics: list = []
    final_relations: dict = {}

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
            requests[instance_id] = EvaluateRequest(run_id=runner.execution.run_id if hasattr(runner, 'execution') else 'solve', instance_id=instance_id,
                iteration_id=iteration_id, time_s=time_s, trial_ports=ports, readonly_state=runner.state)
        def runner_count(name):
            if hasattr(python_runners, name):
                return int(getattr(python_runners, name))
            return sum(int(getattr(runner, name, 0)) for runner in python_runners.values())

        if counters is not None:
            requests_before = runner_count('request_count')
            hits_before = runner_count('parent_cache_hits')
        responses = python_runners.evaluate(requests) if hasattr(python_runners, 'evaluate') else {
            key: python_runners[key].evaluate(request) for key, request in requests.items()}
        if counters is not None:
            actual_requests = runner_count('request_count') - requests_before
            hits = runner_count('parent_cache_hits') - hits_before
            counters.rpc_batches += actual_requests
            counters.rpc_instances += len(requests) - hits if actual_requests else 0
            counters.parent_cache_hits += hits
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

    def physical_residual_values(vector):
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

    if counters is None:
        # 开关关闭时保持原来的调用路径：不做逐调用计时，也不做任何额外记账。
        physical_residual = physical_residual_values
    else:
        def physical_residual(vector):
            started = time.perf_counter()
            try:
                return physical_residual_values(vector)
            finally:
                counters.residual_calls += 1
                counters.timing_s['residual'] = counters.timing_s.get('residual', 0.) + (time.perf_counter() - started)

    def residual(vector):
        drops, balance, _, constraints = physical_residual(vector)
        _, flows = unpack(vector)
        scaled = drops / PRESSURE_SCALE
        for idx, value in constraints.items():
            scaled[idx] = value
        return np.concatenate((scaled, balance))

    size = len(unknown) + len(tanks) + m
    node_columns = {node: column for column, node in enumerate(unknown + tanks)}
    requested = options.hydraulic_method
    pattern_csr = None
    nnz = size * size
    if requested != 'dense':
        # 显式 sparse 与 auto 都需要模式；稠密路径不构建，避免给显式请求增加无关开销。
        pattern_csr = jacobian_pattern(network, unknown, tanks, python_runners)
        nnz = int(pattern_csr.nnz)
    choice = choose_hydraulic_method(requested, size, nnz)
    method, reason = choice.effective, choice.reason
    if method != 'sparse':
        pattern_csr = None
    if counters is not None:
        counters.problem_size = size
        counters.jacobian_nnz = nnz

    # Python module rows retain full relation dependencies, using grouped sparse
    # differences; the built-in equations and continuity rows use analytic slopes.
    analytic_models = {'valve', 'pipe', 'duct', 'pump_curve', 'resistance'}
    if python_runners:
        builtins_supported = all(branch.instance_id in python_runners or branch.solver_model in analytic_models for branch in network.branches)
        analytic_supported = options.module_mixed_jacobian and options.analytic_jacobian and builtins_supported
        jacobian_mode = 'mixed' if analytic_supported else 'finite_difference'
        jacobian_reason = '内置解析块和 Python 完整残差有限差分块' if analytic_supported else 'Python 模块的端口关系可能依赖全部试算压力，保留有限差分'
    elif not options.analytic_jacobian:
        analytic_supported, jacobian_mode = False, 'finite_difference'
        jacobian_reason = '项目显式关闭解析 Jacobian'
    else:
        unsupported = sorted({branch.solver_model for branch in network.branches} - analytic_models)
        analytic_supported = not unsupported
        jacobian_mode = 'analytic' if analytic_supported else 'finite_difference'
        jacobian_reason = ('纯内置关系（阀门/管道/泵/阻力）' if analytic_supported
                           else f'内置模型 {unsupported} 未注册解析导数，保留有限差分')

    module_rows = [idx for idx, branch in enumerate(network.branches) if branch.instance_id in python_runners]
    module_row_set = set(module_rows)
    module_difference = None
    if analytic_supported and module_rows:
        from .module_performance import GroupedModuleDifference
        module_pattern = pattern_csr if pattern_csr is not None else jacobian_pattern(network, unknown, tanks, python_runners)
        module_difference = GroupedModuleDifference(module_pattern[module_rows, :])

    def analytic_jacobian(vector):
        rows, cols, data = [], [], []
        base_relations = {}
        if module_difference is not None:
            base = residual(vector)
            base_relations = dict(final_relations)
            difference = module_difference.evaluate(lambda trial: residual(trial)[module_rows], vector, base[module_rows]).tocoo()
            rows.extend(module_rows[row] for row in difference.row)
            cols.extend(difference.col)
            data.extend(difference.data)
        tank_rate_columns = {node: node_columns[node] for node in tanks}
        # 只有 `unknown` 里的节点有独立压力未知量；水箱节点的压力由净流入决定（见下）。
        pressure_columns = {node: column for column, node in enumerate(unknown)}
        _, flows = unpack(vector)
        for idx, (branch, flow) in enumerate(zip(network.branches, flows)):
            if idx in module_row_set:
                continue
            column = len(node_columns) + idx
            if branch.closed:
                rows.append(idx); cols.append(column); data.append(1.0)
                continue
            params = network.parameters[branch.instance_id]
            if branch.solver_model == 'pump_curve' and params['speed_ratio'] <= 0:
                raise ValueError(f'{branch.instance_id} 停泵阻力模型尚未定义，转速必须大于零')
            _, slope = branch_drop_and_slope(branch.solver_model, params, float(flow),
                                             float(rho_b[idx]), float(mu_b[idx]))
            if branch.start_node in pressure_columns:
                rows.append(idx); cols.append(pressure_columns[branch.start_node]); data.append(1.0)
            if branch.end_node in pressure_columns:
                rows.append(idx); cols.append(pressure_columns[branch.end_node]); data.append(-1.0)
            # 水箱节点的压力由隐式步的净流入决定：p = p_surface + g·(M_old + dt·r)/A，
            # 所以支路行对水箱净流入列也有 ∂p/∂r = dt·g/A。
            if branch.start_node in tank_rate_columns:
                rows.append(idx); cols.append(tank_rate_columns[branch.start_node])
                data.append(dt_s * GRAVITY / network.storage[branch.start_node].area_m2 / PRESSURE_SCALE)
            if branch.end_node in tank_rate_columns:
                rows.append(idx); cols.append(tank_rate_columns[branch.end_node])
                data.append(-dt_s * GRAVITY / network.storage[branch.end_node].area_m2 / PRESSURE_SCALE)
            # 行方程已除以 PRESSURE_SCALE，而压力列的未知量本身就是 p/PRESSURE_SCALE。
            rows.append(idx); cols.append(column); data.append(-slope / PRESSURE_SCALE)
        for position, node in enumerate(unknown):
            row = m + position
            for idx, branch in enumerate(network.branches):
                if branch.start_node == node:
                    rows.append(row); cols.append(len(node_columns) + idx); data.append(-1.0)
                if branch.end_node == node:
                    rows.append(row); cols.append(len(node_columns) + idx); data.append(1.0)
        for position, node in enumerate(tanks):
            row = m + len(unknown) + position
            for idx, branch in enumerate(network.branches):
                if branch.start_node == node:
                    rows.append(row); cols.append(len(node_columns) + idx); data.append(-1.0)
                if branch.end_node == node:
                    rows.append(row); cols.append(len(node_columns) + idx); data.append(1.0)
            rows.append(row); cols.append(node_columns[node]); data.append(-1.0)
        matrix = csr_matrix((data, (rows, cols)), shape=(size, size))
        if module_rows:
            from .models import ModulePhaseRequest, ChannelState
            from .module_diagnostics import merge_diagnostics
            replacements = {}
            pressures, actual_flows = unpack(vector)
            for key, runner in python_runners.items():
                definition = network.modules[network.instances[key].module_id]
                if not definition.sdk or 'hydraulic.derivatives.v1' not in definition.sdk.capabilities:
                    continue
                channels = {branch.channel_id:ChannelState(mass_flow_kg_s=float(actual_flows[j]),
                    pressure_drop_pa=float(pressures[branch.start_node]-pressures[branch.end_node]))
                    for j,branch in enumerate(network.branches) if branch.instance_id == key}
                try:
                    response = runner.phase_call('jacobian', ModulePhaseRequest(run_id=runner.execution.run_id,
                        instance_id=key, time_s=time_s, ports={port.id:trial_port(key,port.id,pressures[network.port_nodes[f'{key}:{port.id}']])
                            for port in definition.ports}, channels=channels, context=runner.execution.context()))
                    for j,branch in enumerate(network.branches):
                        derivative = response.derivatives.get(branch.channel_id) if branch.instance_id == key else None
                        if derivative is None or not derivative.smooth or abs(actual_flows[j]) < 100*options.mass_tolerance_kg_s:
                            continue
                        relation = base_relations.get((key,branch.channel_id))
                        if relation is not None and (relation.kind == 'compressor' or relation.kind == 'valve' and relation.parameters['opening_ratio'] == 0):
                            continue
                        row = np.zeros(size)
                        node_gradients = {branch.start_node:1., branch.end_node:-1.}
                        for port, gradient in derivative.port_pressure_derivatives.items():
                            node = network.port_nodes[f'{key}:{port}']
                            node_gradients[node] = node_gradients.get(node,0.) - gradient
                        for node, gradient in node_gradients.items():
                            if node in pressure_columns:
                                row[pressure_columns[node]] += gradient
                            elif node in tank_rate_columns:
                                row[tank_rate_columns[node]] += gradient*dt_s*GRAVITY/network.storage[node].area_m2/PRESSURE_SCALE
                        row[len(node_columns)+j] = -derivative.flow_slope_pa_per_kg_s/PRESSURE_SCALE
                        if np.allclose(row,matrix.getrow(j).toarray().ravel(),rtol=1e-4,atol=1e-6):
                            replacements[j] = csr_matrix(row)
                        else:
                            derivative_diagnostics[:] = merge_diagnostics(derivative_diagnostics, [Diagnostic(
                                code='MODULE_DERIVATIVE_FALLBACK',severity='warning',instance_id=key,
                                message=f'{key}.{branch.channel_id} 声明导数与完整残差差分不符，本次使用有限差分')])
                except ValueError as error:
                    derivative_diagnostics[:] = merge_diagnostics(derivative_diagnostics,[Diagnostic(code='MODULE_DERIVATIVE_FALLBACK',
                        severity='warning',instance_id=key,message=f'{key} 导数校验失败，使用完整残差有限差分：{error}')])
            if replacements:
                amended = matrix.tolil()
                for j, row in replacements.items():
                    amended[j, :] = row
                matrix = amended.tocsr()
        return matrix.toarray() if method == 'dense' else matrix
    # A loop held only by tanks has no fixed pressure left; start from the tanks' current pressures.
    level = list(fixed.values()) or [network.storage[node].pressure(tank_old[node].mass_kg) for node in tanks]
    cold = np.concatenate((np.full(len(unknown), np.mean(level) / PRESSURE_SCALE), np.zeros(len(tanks)), np.full(m, .1)))
    # New passive SDK modules can explicitly opt into a signed fixed-boundary seed.
    # Old saved contracts retain their original initialization and fallback path.
    for index,branch in enumerate(network.branches):
        if branch.instance_id not in python_runners:
            continue
        definition=network.modules[network.instances[branch.instance_id].module_id]
        requirement=getattr(definition,'sdk',None)
        if requirement and 'hydraulic.signed_start.v1' in requirement.capabilities and branch.start_node in fixed and branch.end_node in fixed:
            delta=fixed[branch.start_node]-fixed[branch.end_node]
            cold[len(node_columns)+index]=.1 if delta>0 else -.1 if delta<0 else 0.
    warm_start = initial is not None and np.shape(initial) == (size,) and np.all(np.isfinite(initial))
    if warm_start:
        start = np.array(initial, dtype=float)
        # Quadratic laws (q·|q|) have zero slope at q=0, so a branch that carried no flow in the
        # previous frame would stall least_squares on gtol; restart such flows from the cold guess.
        flows_start = start[len(unknown) + len(tanks):]
        restart=np.abs(flows_start) < max(1e-6,100*options.mass_tolerance_kg_s)
        flows_start[restart]=cold[len(node_columns):][restart]
    else:
        start = cold

    def attempt(vector, numeric_jacobian=False):
        started = time.perf_counter()
        if counters is not None:
            counters.solver_attempts += 1
        sparse_options = {}
        if method == 'sparse':
            sparse_options = {'tr_solver': 'lsmr',
                              'tr_options': {'atol': 1e-13, 'btol': 1e-13, 'maxiter': max(100, size*4)}}
        if analytic_supported and not numeric_jacobian:
            # 解析导数与 x_scale='jac' 不冲突：jac 返回 CSR（稀疏）或 ndarray（稠密）。
            sparse_options['jac'] = analytic_jacobian
        elif method == 'sparse':
            sparse_options['jac_sparsity'] = pattern_csr
        result = least_squares(residual, vector, max_nfev=options.max_iterations, xtol=1e-12, ftol=1e-12, gtol=1e-12, x_scale='jac', **sparse_options)
        if counters is not None:
            counters.nfev += int(result.nfev)
            counters.njev += int(getattr(result, 'njev', 0) or 0)
            # least_squares 的墙钟包含残差与 Jacobian 扰动，和 timing_s['residual'] 重叠，不能相加。
            counters.timing_s['least_squares'] = counters.timing_s.get('least_squares', 0.) + (time.perf_counter() - started)
        drops, balance, closed, constraints = physical_residual_values(result.x)
        pressure_error = float(np.max(np.abs(drops), initial=0))
        mass_error = max(float(np.max(np.abs(balance), initial=0)), max(map(abs, closed), default=0.))
        ok = result.success and pressure_error <= options.pressure_tolerance_pa and mass_error <= options.mass_tolerance_kg_s
        return result, drops, balance, closed, constraints, ok

    result, drops, balance, closed, constraints, ok = attempt(start)
    if warm_start and not ok:
        # A warm start is only a hint: fall back to the cold guess before reporting non-convergence.
        result, drops, balance, closed, constraints, ok = attempt(cold)
    if not ok and choice.requested == 'auto' and method == 'sparse':
        # S1：auto 的稀疏选择只允许一次可诊断回退。不放宽容差、不做无限重试；
        # 回退结果仍然要过同一个收敛门（下方统一检查），失败就如实报错。
        method, pattern_csr = 'dense', None
        reason = f'{reason}；稀疏求解未收敛，已回退 dense（容差未放宽）'
        if counters is not None:
            counters.method_fallback = 'dense'
        result, drops, balance, closed, constraints, ok = attempt(cold)
    if not ok and analytic_supported:
        # 解析 Jacobian 的已知退化：q=0 是 q|q| 项的驻点，Newton 步可能停在零流量假收敛点
        # （gtol 满足但压力残差不为 0）。只允许一次可诊断回退到有限差分，容差不放宽。
        jacobian_mode = 'finite_difference'
        jacobian_reason = '解析 Jacobian 在零流量驻点假收敛，已回退有限差分（仅一次）'
        if counters is not None:
            counters.jacobian_fallback = 'finite_difference'
        result, drops, balance, closed, constraints, ok = attempt(cold, numeric_jacobian=True)
    pressures, flows = unpack(result.x)
    # Zero-flow and forced-flow relations do not determine a pressure difference.
    # Every pressure component left after removing them needs its own reference.
    # A tank row fixes its pressure through the stored mass, so it is a reference as well.
    reached, pending = set(fixed) | set(tanks), list(fixed) + tanks
    adjacency: dict[int, set[int]] = {node: set() for node in range(n_nodes)}
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
    counters_result = None
    if counters is not None:
        counters.module_evaluations = iteration_id
        # 真实残差调用 − SciPy 基础 nfev = 被旧 iterations 字段漏掉的 Jacobian 扰动调用。
        counters.perturbation_calls = max(0, counters.residual_calls - counters.nfev)
        counters.jacobian_evaluations = counters.njev
        if not counters.jacobian_nnz:
            # 稠密路径没有显式稀疏模式：Jacobian 非零元数按满阵计。
            counters.jacobian_nnz = counters.problem_size ** 2
        if hasattr(python_runners, 'request_count'):
            counters.worker_requests = int(python_runners.request_count)
        elif isinstance(python_runners, dict):
            counters.worker_requests = sum(int(getattr(runner, 'request_count', 0)) for runner in python_runners.values())
        counters.timing_s['solve_total'] = time.perf_counter() - solve_started
        counters_result = counters.as_dict()
    return HydraulicResult(pressures, flows, int(result.nfev), pressure_error, mass_error, density, viscosity,
                           module_variables.copy(), module_diagnostics.copy() + derivative_diagnostics, rho_b, mu_b, dict(final_relations),
                           np.array(result.x, copy=True), unpack_rates(result.x), counters_result,
                           requested, method, reason, size, nnz, jacobian_mode, jacobian_reason)


def solve_hydraulics(network: CompiledNetwork, runners=None, time_s=0., **options) -> HydraulicResult:
    """Solve one hydraulic state, isolating every Python module in a Worker by default."""
    owned = runners is None
    active = _python_runners(network) if owned else runners
    begin_module_step(active)
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
    port_flows: dict[str, float] = {}
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
        assert where is not None  # A positive maximum was assigned together with its node.
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
    step_id = begin_module_step(active)
    try:
        result = _solve_network(network, active, time_s, warm, service, storage_step)
        result.module_step_id = step_id
        from .module_phases import observe_modules
        observe_modules(network, active, result, time_s)
        return result
    except RuntimeErrorBase as error:
        from .composites import map_diagnostics
        error.diagnostics = map_diagnostics(network.composite_maps,error.diagnostics)
        raise
    finally:
        if owned:
            _close_runners(active)


def _solve_network(network, runners, time_s, warm, service, storage_step=None) -> NetworkResult:
    from .module_phases import heat_hook
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
                                shaft_power(network, hydraulic), h_start, storage_step,
                                module_heat=heat_hook(network, runners, hydraulic, service, time_s))
        _warn_reference_density(network, thermal, reference_arrays(network)[0] if network.mixed else reference_properties(network)[0])
        return NetworkResult(hydraulic, thermal, 1, build_port_states(network, hydraulic, thermal))

    # node coupling: properties frozen during each hydraulic solve, updated between passes.
    if warm is not None and warm.thermal is not None and warm.hydraulic.branch_density is not None:
        rho_b, mu_b = warm.hydraulic.branch_density, warm.hydraulic.branch_viscosity
        node_states, previous_t = warm.thermal.node_states, np.array([s.temperature_k for s in warm.thermal.node_states])
    else:
        _, _, rho_b, mu_b = reference_arrays(network)
        node_states, previous_t = initial_guess(network, service), None
    # L2：node 外循环加速（默认 none = v0.5.0 的直接替换，旧项目数值不变）。
    coupling_acceleration = getattr(options, 'coupling_acceleration', 'none')
    relaxation = 1.0
    previous_defect = None
    topology_signature = None
    for iteration in range(1, options.max_coupling_iterations + 1):
        hydraulic = _solve_hydraulics(network, runners, time_s, branch_density=rho_b, branch_viscosity=mu_b,
                                      port_base=_node_ports(network, node_states) if runners else None, initial=start,
                                      storage_step=storage_step)
        thermal = solve_thermal(network, service, hydraulic.pressures, hydraulic.flows, hydraulic.relations,
                                shaft_power(network, hydraulic), h_start, storage_step,
                                module_heat=heat_hook(network, runners, hydraulic, service, time_s))
        new_rho, new_mu = _branch_properties(network, thermal)
        temperatures = np.array([s.temperature_k for s in thermal.node_states])
        # 固定点缺陷：目标是“本轮的物性”，与是否松弛无关；L2 不允许用“松弛后步长变小”冒充收敛。
        density_change = float(np.max(np.abs(new_rho - rho_b) / new_rho, initial=0.0))
        converged = (previous_t is not None and density_change < options.coupling_density_rtol
                     and float(np.max(np.abs(temperatures - previous_t), initial=0.0)) < options.thermal_tolerance_k)
        if converged:
            return NetworkResult(hydraulic, thermal, iteration, build_port_states(network, hydraulic, thermal))
        current_signature = (tuple(branch.closed for branch in network.branches),
                             tuple(sorted((key, relation.kind) for key, relation in hydraulic.relations.items())))
        if coupling_acceleration == 'none':
            rho_b, mu_b = new_rho, new_mu
        else:
            if topology_signature is not None and current_signature != topology_signature:
                # 关开阀/模块关系变化：重置加速历史，避免沿用旧工况的松弛系数。
                relaxation, previous_defect = 1.0, None
            defect = new_rho - rho_b
            scale = np.maximum(new_rho, 1e-12)
            relaxation = _coupling_relaxation(coupling_acceleration, relaxation, defect,
                                              previous_defect, scale)
            candidate = rho_b + relaxation * defect
            candidate_mu = mu_b + relaxation * (new_mu - mu_b)
            if not (np.all(np.isfinite(candidate)) and np.all(candidate > 0) and np.all(candidate_mu > 0)):
                relaxation, previous_defect = 1.0, None
                rho_b, mu_b = new_rho, new_mu
            else:
                previous_defect = defect.copy()
                rho_b, mu_b = candidate, candidate_mu
        topology_signature = current_signature
        previous_t = temperatures
        node_states, start, h_start = thermal.node_states, hydraulic.solution, thermal.enthalpies
    raise ThermalError('COUPLING_NOT_CONVERGED',
                       f'水力与物性耦合 {options.max_coupling_iterations} 次未收敛（密度相对变化 {density_change:.3g}）')


def _coupling_relaxation(mode: str, relaxation: float, defect: np.ndarray, previous_defect,
                         scale: np.ndarray) -> float:
    """L2 的有界松弛系数（[0.2, 1.0]）。"""
    if previous_defect is None:
        return 1.0
    if mode == 'adaptive':
        previous_norm = float(np.max(np.abs(previous_defect) / scale, initial=0.0))
        current_norm = float(np.max(np.abs(defect) / scale, initial=0.0))
        if previous_norm == 0.0 or current_norm < previous_norm:
            return min(1.0, max(0.2, relaxation * 1.25))
        return max(0.2, relaxation * 0.5)
    scaled = defect / scale
    previous_scaled = previous_defect / scale
    difference = scaled - previous_scaled
    denominator = float(np.dot(difference, difference))
    if not np.isfinite(denominator) or denominator <= 1e-300:
        return 1.0
    alpha = -relaxation * float(np.dot(previous_scaled, difference)) / denominator
    if not np.isfinite(alpha):
        return 1.0
    return min(1.0, max(0.2, alpha))


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


def tank_states_from(network: CompiledNetwork, result: NetworkResult | None, previous: dict[int, TankState] | None,
                     dt_s: float | None) -> dict[int, TankState]:
    """Tank state after an accepted step (or the initial state when `previous` is None)."""
    states = {}
    for node, spec in network.storage.items():
        if previous is None:
            states[node] = TankState(spec.initial_mass_kg, spec.initial_enthalpy_j_kg)
            continue
        if result is None or dt_s is None:
            raise ValueError('推进水箱状态需要求解结果和时间步长')
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
            humidity = getattr(state, 'humidity_ratio_kg_kg', None)
            if humidity is not None:
                variables[f'{prefix}.humidity_ratio_kg_kg'] = humidity
                from .moist_air import relative_humidity
                variables[f'{prefix}.relative_humidity'] = relative_humidity(
                    state.temperature_k, state.pressure_pa, humidity)
    if thermal is not None and (thermal.coil_outputs or thermal.humidifier_outputs):
        for instance_id, values in thermal.coil_outputs.items():
            variables.update({f'{instance_id}.{key}': value for key, value in values.items()})
        for instance_id, value in thermal.humidifier_outputs.items():
            variables[f'{instance_id}.moisture_addition_kg_s'] = value
    for inst, params in network.parameters.items():
        variables.update({f'{inst}.param.{k}': v for k,v in params.items() if isinstance(v, (float,int))})
    conflicts = variables.keys() & hydraulic.module_variables.keys()
    if conflicts:
        raise RuntimeErrorBase(f'模块输出不能覆盖网络求解变量：{sorted(conflicts)}')
    variables.update(hydraulic.module_variables)
    metrics = {'pressure_residual_pa': hydraulic.pressure_residual, 'mass_residual_kg_s': hydraulic.mass_residual,
               'iterations': hydraulic.iterations, 'node_count': len(network.node_keys), 'branch_count': len(network.branches),
               'matrix_size': hydraulic.matrix_size, 'matrix_nnz': hydraulic.matrix_nnz}
    if thermal is not None:
        metrics.update({'thermal_iterations': thermal.iterations, 'coupling_iterations': coupling,
                        'energy_residual_w': thermal.energy_residual_w, 'reference_heat_w': thermal.reference_heat_w})
        if thermal.humidity_ratio is not None:
            metrics.update({'moisture_residual_kg_s': thermal.moisture_residual_kg_s,
                            'humidifier_moisture_kg_s': thermal.humidifier_moisture_kg_s})
    summary = {'requested_method': hydraulic.requested_method, 'effective_method': hydraulic.effective_method,
               'method_reason': hydraulic.method_reason, 'matrix_size': hydraulic.matrix_size,
               'matrix_nnz': hydraulic.matrix_nnz, 'jacobian_mode': hydraulic.jacobian_mode,
               'jacobian_reason': hydraulic.jacobian_reason}
    frame = RunFrame(status='converged', valid=True, time_s=time_s, variables=variables, diagnostics=diagnostics,
                    metrics=metrics, solve_counters=hydraulic.counters, solve_summary=summary)
    from .composites import map_frame
    return map_frame(network,frame)


def cell_variables(network: CompiledNetwork, result: NetworkResult, service):
    """`<pipe>.state.mean_temperature_k` and `stored_power_w` for pipes with heat capacity."""
    variables, power = {}, 0.0
    thermal = result.thermal
    if thermal is None:
        raise ValueError('管道热容变量需要热力求解结果')
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
    if getattr(network, 'execution_domain', None) == 'coupled':
        from .refrigeration.coupling import solve_coupled_steady
        return solve_coupled_steady(network)
    if getattr(network, 'execution_domain', None) == 'thermal':
        from .refrigeration.session import solve_thermal_steady
        return solve_thermal_steady(network)
    if getattr(network, 'execution_domain', None) == 'refrigeration':
        from .refrigeration.station import solve_station_steady
        return solve_station_steady(network)
    if getattr(network, 'execution_domain', None) == 'cold_store':
        from .refrigeration.cold_store import solve_cold_store_steady
        return solve_cold_store_steady(network)
    if any(script.enabled for script in network.project.control_scripts):
        raise CompilationError('CONTROL_DYNAMIC_REQUIRED', 'Python 控制脚本需要动态运行；请切换运行模式或停用脚本')
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


def solve_dynamic(network, duration_s, dt_s):
    if getattr(network, 'execution_domain', None) in ('thermal', 'refrigeration', 'cold_store', 'coupled'):
        from .sessions import create_session
        session = create_session(network, duration_s, dt_s)
        try:
            session.initialize()
            while not session.done:
                session.advance()
            return list(session.frames)
        finally:
            session.close()
    from .simulation import run_dynamic
    return run_dynamic(network, duration_s, dt_s)


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
    """Prepare all module candidates; the session owns the single acceptance point."""
    from .module_transactions import ModuleStepTransaction
    variables, diagnostics = {}, []
    hydraulic = result.hydraulic
    set_module_step(runners, result.module_step_id)
    transaction = ModuleStepTransaction(runners, result.module_step_id, time_s)
    try:
        for instance_id, runner in runners.items():
            definition = network.modules[network.instances[instance_id].module_id]
            ports = {port.id: result.port_states[f'{instance_id}:{port.id}'] for port in definition.ports}
            channels = {}
            for j, (branch, flow) in enumerate(zip(network.branches, hydraulic.flows)):
                if branch.instance_id == instance_id:
                    channels[branch.channel_id] = ChannelResult(mass_flow_kg_s=float(flow),
                        pressure_drop_pa=float(hydraulic.pressures[branch.start_node] - hydraulic.pressures[branch.end_node]),
                        heat_w=float(result.thermal.heat_w[j]) if result.thermal else 0.)
            committed = transaction.prepare(instance_id, CommitStepRequest(
                run_id=runner.execution.run_id, instance_id=instance_id, time_s=time_s,
                dt_s=dt_s, converged_ports=ports, context=runner.execution.context()), channels)
            variables.update({f'{instance_id}.{k}': v for k, v in committed.variables.items()})
            variables.update({f'{instance_id}.state.{k}': v for k, v in committed.state.items()
                              if isinstance(v, (float, int, str, bool)) or v is None})
            diagnostics.extend(committed.diagnostics)
        transaction.validate()
    except Exception:
        transaction.discard()
        raise
    return variables, diagnostics, transaction


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

