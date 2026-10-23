"""C0–C3：受限串联支路压缩与原变量回算。

命中 `SolverOptions.series_compression=True` 时，`solver._solve_hydraulics` 在常规求解前调用
本模块的 :func:`solve_hydraulics_hook`；返回 ``HydraulicResult`` 表示已按压缩方案求解，
返回 ``None`` 表示不适用，交回常规求解路径（数值行为完全不变）。

## 语义

* **C0 识别**：只压缩“在可压缩子图里度数为 2 的未定压节点”之间的串联链；压力参考节点、
  水箱/储量节点、度数 ≠ 2 的节点、紧邻不可压缩支路（关闭阀、未注册模型、Python 支路）的节点
  一律保留为锚点。识别结果（链、成员、锚点、未压缩原因、维数）可导出（:func:`plan_compression`）。
* **C1 方程**：一条链共享一个质量流量未知量 ``q``。链的复合压降为
  ``F(q) = Σ s_i · drop_i(s_i · q)``（``s_i = ±1`` 表示遍历方向与支路自身方向是否一致），
  复合斜率 ``F'(q) = Σ drop'_i(s_i · q)``；用 `hydraulic_derivatives.branch_drop_and_slope`
  逐元件累加，因此同向/反向、不同管径/阻力、泵阀串联都走同一套公式。
* **C2 回算**：约化解逐段恢复原节点压力、原支路流量与压差，并还原
  ``HydraulicResult``（含按**原网络**未知量排布的 ``solution``：未定压节点压力 / 水箱净流入 /
  支路流量，供动态 warm start 复用）、原支路的 ``branch_density/branch_viscosity``、
  ``counters``（原网络开启诊断时）以及方法选择字段；``method_reason`` 追加
  “压缩：链数、未知量 N→M”。
* **C3 缓存**：压缩计划按“拓扑 + 关闭状态 + 压力参考 + 储量节点”签名缓存；关闭阀/参数变化后
  签名变化自动重建，参数值本身不进入签名（复合压降每次求解都读当前参数）。

## 与 `solve_hydraulics` 的关系（重要，如实记录）

复合链不是注册过的内置支路模型（``hydraulic_derivatives.branch_drop_value`` 只支持
valve/pipe/pump_curve/resistance），所以**不能**把约化网络直接交给 ``solve_hydraulics``。
本模块只接管约化后的代数系统，并严格复用常规求解路径的数值约定：残差缩放
（压降 / ``PRESSURE_SCALE``、质量不平衡不缩放）、冷启动初值、零流量热启动保护、warm→cold
回退、``xtol/ftol/gtol=1e-12``、``x_scale='jac'``、``max_nfev``、dense/sparse 选择
（``choose_hydraulic_method``）与收敛门（压力/质量容差 + 正压力 + 有限性 + 泵曲线范围）。
收敛后仍按**原网络**的逐支路压降与原节点质量平衡重新计算残差，避免“约化收敛、原网络不满足”
的漏检。

不适用（返回 ``None``）：多工质网络、有 Python runner、有 ``port_base``、``storage_step``
非空（动态水箱子步）、没有可压缩链、没有压力参考。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import csr_matrix

from .compiler import CompiledBranch, CompiledNetwork
from .hydraulic_derivatives import branch_drop_and_slope, branch_drop_value
from .runtime import RuntimeErrorBase
from .solver import (
    PRESSURE_SCALE,
    HydraulicNotConverged,
    HydraulicResult,
    SolveCounters,
    choose_hydraulic_method,
    reference_properties,
)

#: 允许进入串联链的支路模型（与 `hydraulic_derivatives` 的解析导数集合一致）。
SUPPORTED_MODELS = frozenset({'valve', 'pipe', 'pump_curve', 'resistance'})

#: 计划缓存条目上限；超出后整体清空（缓存只是性能优化，失效不会影响正确性）。
_PLAN_CACHE: dict[tuple, 'CompressionPlan'] = {}
_PLAN_CACHE_LIMIT = 16


@dataclass(frozen=True)
class ChainMember:
    """链中的一段：原支路下标 + 遍历方向（+1 与支路自身方向一致，-1 相反）。"""

    branch: int
    sign: int


@dataclass(frozen=True)
class Chain:
    """一条串联链：成员按遍历顺序排列，``nodes`` 为长度 ``len(members)+1`` 的节点序列。"""

    members: tuple[ChainMember, ...]
    nodes: tuple[int, ...]
    start_node: int
    end_node: int
    loop: bool = False

    @property
    def flow(self) -> int:
        return len(self.members)


@dataclass(frozen=True)
class CompressionPlan:
    """C0 的可导出识别结果；``chains`` 为空时钩子不接管（返回 None）。"""

    chains: tuple[Chain, ...]
    #: 不进链、按单支路保留的原支路下标（含关闭支路与未注册模型）。
    standalone: tuple[int, ...]
    #: 约化网络的节点（锚点，升序），即 ``node_keys`` 的下标。
    anchors: tuple[int, ...]
    #: 锚点里没有固定压力的节点（约化网络的未知压力）。
    unknown_anchors: tuple[int, ...]
    #: (原支路下标, 未压缩原因)，便于报告与诊断。
    excluded: tuple[tuple[int, str], ...]
    signature: tuple
    original_size: int
    reduced_size: int
    reduced_nnz: int

    @property
    def chain_count(self) -> int:
        return len(self.chains)

    @property
    def compressed_branches(self) -> int:
        return sum(chain.flow for chain in self.chains)

    @property
    def saved_unknowns(self) -> int:
        return self.original_size - self.reduced_size

    def as_dict(self) -> dict:
        return {
            'chains': [
                {'members': [(member.branch, member.sign) for member in chain.members],
                 'start_node': chain.start_node, 'end_node': chain.end_node, 'loop': chain.loop}
                for chain in self.chains
            ],
            'standalone': list(self.standalone),
            'anchors': list(self.anchors),
            'unknown_anchors': list(self.unknown_anchors),
            'excluded': [{'branch': index, 'reason': reason} for index, reason in self.excluded],
            'original_size': self.original_size,
            'reduced_size': self.reduced_size,
            'reduced_nnz': self.reduced_nnz,
        }


# --------------------------------------------------------------------------- C0：识别
def _python_instance(network: CompiledNetwork, branch: CompiledBranch) -> bool:
    instance = network.instances.get(branch.instance_id)
    if instance is None:
        return False
    definition = network.modules.get(instance.module_id)
    return definition is not None and definition.runtime == 'python'


def _python_instances(network: CompiledNetwork) -> bool:
    """网络里是否含 Python 模块实例（第一版不压缩 Python 通路，直接交回常规路径）。"""
    return any(definition.runtime == 'python'
               for definition in (network.modules.get(instance.module_id) for instance in network.instances.values())
               if definition is not None)


def _signature(network: CompiledNetwork) -> tuple:
    """计划缓存签名：拓扑 + 关闭状态 + 压力参考 + 储量节点（参数值不进入签名）。"""
    return (
        len(network.node_keys),
        tuple((branch.start_node, branch.end_node, branch.closed, branch.solver_model)
              for branch in network.branches),
        tuple(sorted(network.fixed_pressures)),
        tuple(sorted(network.storage)),
    )


def _components(nodes: set[int], branches, members: set[int]) -> list[set[int]]:
    """可压缩子图（只含 ``members`` 里的支路）的连通分量。"""
    parent = {node: node for node in nodes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for index in members:
        start, end = branches[index].start_node, branches[index].end_node
        left, right = find(start), find(end)
        if left != right:
            parent[left] = right
    groups: dict[int, set[int]] = {}
    for node in nodes:
        groups.setdefault(find(node), set()).add(node)
    return list(groups.values())


def plan_compression(network: CompiledNetwork) -> CompressionPlan | None:
    """构建 C0 压缩计划；不适用（多工质/无压力参考/无可压缩链）时返回 None。"""
    if network.mixed or not network.fixed_pressures:
        return None
    n_nodes = len(network.node_keys)
    branches = network.branches
    m = len(branches)
    if m <= 1:
        return None

    excluded: dict[int, str] = {}
    compressible: set[int] = set()
    for index, branch in enumerate(branches):
        if branch.closed:
            excluded[index] = '关闭支路'
        elif branch.solver_model not in SUPPORTED_MODELS:
            excluded[index] = f'未支持模型 {branch.solver_model}'
        elif _python_instance(network, branch):
            excluded[index] = 'Python 支路'
        else:
            compressible.add(index)

    def build_incident(active: set[int]) -> list[list[int]]:
        incident: list[list[int]] = [[] for _ in range(n_nodes)]
        for index in active:
            branch = branches[index]
            incident[branch.start_node].append(index)
            incident[branch.end_node].append(index)
        return incident

    def excluded_incident(excluded_set: dict[int, str]) -> list[set[int]]:
        attached: list[set[int]] = [set() for _ in range(n_nodes)]
        for index in excluded_set:
            branch = branches[index]
            attached[branch.start_node].add(index)
            attached[branch.end_node].add(index)
        return attached

    # 没有压力参考的可压缩分量（纯环/孤立环）整段退出压缩；原始求解也会报参考缺失。
    active_nodes = {node for index in compressible for node in
                    (branches[index].start_node, branches[index].end_node)}
    for group in _components(active_nodes, branches, compressible):
        anchored = any(node in network.fixed_pressures or node in network.storage for node in group)
        if not anchored:
            attached = excluded_incident(excluded)
            anchored = any(attached[node] for node in group)
        if not anchored:
            for index in [i for i in compressible
                          if branches[i].start_node in group or branches[i].end_node in group]:
                compressible.discard(index)
                excluded[index] = '无压力参考的可压缩分量'

    incident = build_incident(compressible)
    attached = excluded_incident(excluded)
    anchor = [False] * n_nodes
    for node in range(n_nodes):
        anchor[node] = (node in network.fixed_pressures or node in network.storage or bool(attached[node])
                        or len(incident[node]) != 2)
    # 没有任何支路又不是固定压力的节点无法进入约化系统，交回常规路径报原错误。
    for node in range(n_nodes):
        if anchor[node] and not attached[node] and not incident[node] and node not in network.fixed_pressures:
            return None

    visited: set[int] = set()
    chains: list[Chain] = []

    def walk(start_index: int, start_node: int) -> Chain | None:
        members: list[ChainMember] = []
        nodes = [start_node]
        current, index = start_node, start_index
        for _ in range(m + 1):
            if index in visited:
                return None
            visited.add(index)
            branch = branches[index]
            if branch.start_node == current:
                sign, following = 1, branch.end_node
            elif branch.end_node == current:
                sign, following = -1, branch.start_node
            else:  # pragma: no cover - 拓扑自洽时不会发生
                return None
            members.append(ChainMember(index, sign))
            nodes.append(following)
            if following == start_node:
                return Chain(tuple(members), tuple(nodes), start_node, following, loop=True)
            if anchor[following]:
                return Chain(tuple(members), tuple(nodes), start_node, following)
            others = [other for other in incident[following] if other != index]
            if len(others) != 1:  # pragma: no cover - 度数已保证
                return None
            current, index = following, others[0]
        return None

    for node in range(n_nodes):
        if not anchor[node]:
            continue
        for index in incident[node]:
            if index in visited:
                continue
            chain = walk(index, node)
            if chain is not None and chain.flow >= 2:
                chains.append(chain)

    chain_members = {member.branch for chain in chains for member in chain.members}
    standalone = tuple(index for index in range(m) if index not in chain_members)
    anchors = tuple(node for node in range(n_nodes) if anchor[node])
    unknown_anchors = tuple(node for node in anchors if node not in network.fixed_pressures)

    reduced_branches = len(chains) + len(standalone)
    original_size = (n_nodes - len(network.fixed_pressures)) + m
    reduced_size = len(unknown_anchors) + reduced_branches
    nnz = 0
    for chain in chains:
        nnz += 1
        nnz += int(chain.start_node in unknown_anchors) + int(chain.end_node in unknown_anchors)
    for index in standalone:
        branch = branches[index]
        if branch.closed:
            nnz += 1
            continue
        nnz += 1 + int(branch.start_node in unknown_anchors) + int(branch.end_node in unknown_anchors)
    incident_reduced = [0] * n_nodes
    for chain in chains:
        incident_reduced[chain.start_node] += 1
        incident_reduced[chain.end_node] += 1
    for index in standalone:
        incident_reduced[branches[index].start_node] += 1
        incident_reduced[branches[index].end_node] += 1
    nnz += sum(incident_reduced[node] for node in unknown_anchors)

    return CompressionPlan(chains=tuple(chains), standalone=standalone, anchors=anchors,
                           unknown_anchors=unknown_anchors, excluded=tuple(sorted(excluded.items())),
                           signature=_signature(network), original_size=original_size,
                           reduced_size=reduced_size, reduced_nnz=nnz)


def _cached_plan(network: CompiledNetwork) -> CompressionPlan | None:
    """按结构签名取计划；关闭阀/参数修订导致签名变化时重建（C3）。"""
    signature = _signature(network)
    plan = _PLAN_CACHE.get(signature)
    if plan is None:
        plan = plan_compression(network)
        if plan is None:
            return None
        if len(_PLAN_CACHE) >= _PLAN_CACHE_LIMIT:
            _PLAN_CACHE.clear()
        _PLAN_CACHE[signature] = plan
    return plan


# --------------------------------------------------------------------------- C1：约化系统
class _ReducedSolve:
    """约化网络的残差/Jacobian/回算；数值约定与 `solver._solve_hydraulics` 对齐。"""

    def __init__(self, network: CompiledNetwork, plan: CompressionPlan, rho_b, mu_b, method: str):
        self.network = network
        self.plan = plan
        self.rho_b = rho_b
        self.mu_b = mu_b
        self.method = method
        self.n_nodes = len(network.node_keys)
        self.m = len(network.branches)
        self.fixed = network.fixed_pressures
        self.anchors = plan.anchors
        self.anchor_index = {node: position for position, node in enumerate(plan.anchors)}
        self.unknown_anchors = plan.unknown_anchors
        self.unknown_index = {node: position for position, node in enumerate(plan.unknown_anchors)}
        #: ('chain', Chain) 或 ('single', 原支路下标)；两种规格由 kind 区分（mypy 用 isinstance 收窄）。
        self.specs: list[tuple[str, 'Chain | int']] = [('chain', chain) for chain in plan.chains]
        self.specs += [('single', index) for index in plan.standalone]
        self.size = len(self.unknown_anchors) + len(self.specs)
        self.calls = 0

    # -- 复合压降 ------------------------------------------------------------
    def chain_terms(self, chain: Chain, flow: float) -> tuple[float, float]:
        total = 0.0
        slope = 0.0
        for member in chain.members:
            branch = self.network.branches[member.branch]
            params = self.network.parameters[branch.instance_id]
            signed = member.sign * flow
            value, tangent = branch_drop_and_slope(branch.solver_model, params, signed,
                                                   float(self.rho_b[member.branch]),
                                                   float(self.mu_b[member.branch]))
            total += member.sign * value
            slope += tangent
        return total, slope

    def single_terms(self, index: int, flow: float) -> tuple[float, float]:
        branch = self.network.branches[index]
        params = self.network.parameters[branch.instance_id]
        return branch_drop_and_slope(branch.solver_model, params, flow,
                                     float(self.rho_b[index]), float(self.mu_b[index]))

    def guess_flow(self, kind: str, item: 'Chain | int', target_drop: float) -> float:
        """冷启动流量初值：对被动支路用 q≈sqrt(|Δp|/F(1))，泵/病态情形退回 0.1。"""
        if not math.isfinite(target_drop) or target_drop == 0.0:
            return 0.1
        if kind == 'chain':
            assert isinstance(item, Chain)
            models = {self.network.branches[member.branch].solver_model for member in item.members}
        else:
            assert isinstance(item, int)
            models = {self.network.branches[item].solver_model}
        if 'pump_curve' in models or not models <= {'valve', 'pipe', 'resistance'}:
            return 0.1
        try:
            if kind == 'chain':
                assert isinstance(item, Chain)
                value, _ = self.chain_terms(item, 1.0)
            else:
                assert isinstance(item, int)
                value, _ = self.single_terms(item, 1.0)
        except ValueError:
            return 0.1
        if not math.isfinite(value) or value == 0.0:
            return 0.1
        # 被动支路 F(q) 与 q|q| 同号且单调：F(1) 给出尺度，目标压差反推初值。
        guess = math.copysign(math.sqrt(abs(target_drop) / abs(value)), target_drop * value)
        return guess if math.isfinite(guess) else 0.1

    def cold_flows(self, fixed_level: list[float], mass_tolerance_kg_s: float) -> np.ndarray:
        estimate = np.full(self.n_nodes, np.mean(fixed_level))
        for node, pressure in self.fixed.items():
            estimate[node] = pressure
        guesses = np.empty(len(self.specs))
        for position, (kind, item) in enumerate(self.specs):
            if kind == 'chain':
                assert isinstance(item, Chain)
                start, end = item.start_node, item.end_node
            else:
                assert isinstance(item, int)
                branch = self.network.branches[item]
                start, end = branch.start_node, branch.end_node
            guesses[position] = self.guess_flow(kind, item, estimate[start] - estimate[end])
        floor = max(1e-6, 100 * mass_tolerance_kg_s)
        guesses[np.abs(guesses) < floor] = 0.1
        return guesses

    # -- 未知量 ↔ 压力 -------------------------------------------------------
    def pressures(self, vector) -> np.ndarray:
        values = np.empty(self.n_nodes)
        values[:] = np.nan
        for node, pressure in self.fixed.items():
            values[node] = pressure
        for position, node in enumerate(self.unknown_anchors):
            values[node] = vector[position] * PRESSURE_SCALE
        return values

    def flows(self, vector) -> np.ndarray:
        return np.asarray(vector[len(self.unknown_anchors):], dtype=float)

    def residual(self, vector) -> np.ndarray:
        self.calls += 1
        pressure = self.pressures(vector)
        unk = self.unknown_index
        rows = np.empty(len(self.specs) + len(self.unknown_anchors))
        balance = np.zeros(len(self.unknown_anchors))
        flows = self.flows(vector)
        for position, (kind, item) in enumerate(self.specs):
            flow = flows[position]
            if kind == 'chain':
                assert isinstance(item, Chain)
                chain = item
                start, end = chain.start_node, chain.end_node
                drop, _ = self.chain_terms(chain, flow)
                rows[position] = (pressure[start] - pressure[end] - drop) / PRESSURE_SCALE
            else:
                assert isinstance(item, int)
                branch = self.network.branches[item]
                start, end = branch.start_node, branch.end_node
                if branch.closed:
                    rows[position] = flow
                else:
                    drop, _ = self.single_terms(item, flow)
                    rows[position] = (pressure[start] - pressure[end] - drop) / PRESSURE_SCALE
            if start in unk:
                balance[unk[start]] -= flow
            if end in unk:
                balance[unk[end]] += flow
        rows[len(self.specs):] = balance
        return rows

    def jacobian(self, vector):
        unk = self.unknown_index
        flows = self.flows(vector)
        n_branch_rows = len(self.specs)
        size = self.size
        row_index: list[int] = []
        col_index: list[int] = []
        data: list[float] = []

        def add(row, column, value):
            row_index.append(row)
            col_index.append(column)
            data.append(value)

        for position, (kind, item) in enumerate(self.specs):
            flow = flows[position]
            if kind == 'chain':
                assert isinstance(item, Chain)
                start, end = item.start_node, item.end_node
                _, slope = self.chain_terms(item, flow)
            else:
                assert isinstance(item, int)
                branch = self.network.branches[item]
                start, end = branch.start_node, branch.end_node
                if branch.closed:
                    add(position, len(self.unknown_anchors) + position, 1.0)
                    continue
                _, slope = self.single_terms(item, flow)
            if start in unk:
                add(position, unk[start], 1.0)
            if end in unk:
                add(position, unk[end], -1.0)
            # 行方程已除以 PRESSURE_SCALE，而压力列未知量本身就是 p/PRESSURE_SCALE（与 solver 一致）。
            add(position, len(self.unknown_anchors) + position, -slope / PRESSURE_SCALE)
        for node, position in unk.items():
            row = n_branch_rows + position
            for branch_position, (kind, item) in enumerate(self.specs):
                column = len(self.unknown_anchors) + branch_position
                if kind == 'chain':
                    assert isinstance(item, Chain)
                    start, end = item.start_node, item.end_node
                else:
                    assert isinstance(item, int)
                    branch = self.network.branches[item]
                    start, end = branch.start_node, branch.end_node
                if start == node:
                    add(row, column, -1.0)
                if end == node:
                    add(row, column, 1.0)
        matrix = csr_matrix((data, (row_index, col_index)), shape=(size, size))
        return matrix.toarray() if self.method == 'dense' else matrix

    # -- 回算（C2） ---------------------------------------------------------
    def materialize(self, vector) -> tuple[np.ndarray, np.ndarray]:
        pressure = self.pressures(vector)
        flows_reduced = self.flows(vector)
        flows = np.zeros(self.m)
        for position, (kind, item) in enumerate(self.specs):
            if kind == 'chain':
                assert isinstance(item, Chain)
                for member in item.members:
                    flows[member.branch] = member.sign * flows_reduced[position]
            else:
                assert isinstance(item, int)
                flows[item] = flows_reduced[position]
        for chain in self.plan.chains:
            current = chain.start_node
            current_pressure = pressure[current]
            for member, following in zip(chain.members, chain.nodes[1:]):
                branch = self.network.branches[member.branch]
                params = self.network.parameters[branch.instance_id]
                value = branch_drop_value(branch.solver_model, params, float(flows[member.branch]),
                                          float(self.rho_b[member.branch]), float(self.mu_b[member.branch]))
                current_pressure = current_pressure - member.sign * value
                # 锚点（含固定压力与约化未知压力）保留求解值，只回填链内部节点。
                if following not in self.anchor_index:
                    pressure[following] = current_pressure
                current = following
        return pressure, flows

    def original_residuals(self, pressure: np.ndarray, flows: np.ndarray):
        """按原网络逐支路压降与原节点质量平衡重算残差（收敛门用）。"""
        drops = np.empty(self.m)
        balance = np.zeros(self.n_nodes)
        for index, branch in enumerate(self.network.branches):
            flow = float(flows[index])
            if branch.closed:
                drops[index] = 0.0
            else:
                params = self.network.parameters[branch.instance_id]
                drop = branch_drop_value(branch.solver_model, params, flow,
                                         float(self.rho_b[index]), float(self.mu_b[index]))
                drops[index] = float(pressure[branch.start_node] - pressure[branch.end_node] - drop)
            balance[branch.start_node] -= flow
            balance[branch.end_node] += flow
        unknown = [node for node in range(self.n_nodes) if node not in self.fixed]
        closed = [float(flows[index]) for index, branch in enumerate(self.network.branches) if branch.closed]
        pressure_error = float(np.max(np.abs(drops), initial=0.0))
        mass_error = max(float(np.max(np.abs(balance[unknown]), initial=0.0)),
                         max(map(abs, closed), default=0.0))
        return pressure_error, mass_error


def _map_initial(network: CompiledNetwork, plan: CompressionPlan, initial,
                 mass_tolerance_kg_s: float) -> np.ndarray | None:
    """把**原网络**布局的 warm start 向量映射到约化未知量（C2）。"""
    if initial is None:
        return None
    n_nodes = len(network.node_keys)
    original_size = plan.original_size
    if np.shape(initial) != (original_size,) or not np.all(np.isfinite(initial)):
        return None
    fixed = network.fixed_pressures
    original_unknown = [node for node in range(n_nodes) if node not in fixed]
    position = {node: index for index, node in enumerate(original_unknown)}
    pressure_part = initial[:len(original_unknown)]
    flow_part = initial[len(original_unknown):]
    unknown_anchors = np.array([pressure_part[position[node]] for node in plan.unknown_anchors])
    reduced_flows = np.empty(len(plan.chains) + len(plan.standalone))
    for chain_index, chain in enumerate(plan.chains):
        reduced_flows[chain_index] = float(np.mean([flow_part[member.branch] for member in chain.members]))
    for offset, index in enumerate(plan.standalone):
        reduced_flows[len(plan.chains) + offset] = flow_part[index]
    # 与常规路径一致：上一帧为零流量的支路在二次律下斜率为 0，会卡住 gtol。
    floor = max(1e-6, 100 * mass_tolerance_kg_s)
    reduced_flows[np.abs(reduced_flows) < floor] = 0.1
    return np.concatenate((unknown_anchors, reduced_flows))


def _solution_layout(network: CompiledNetwork, pressure: np.ndarray, flows: np.ndarray) -> np.ndarray:
    """按原网络未知量排布还原 warm start 向量：[未知压力/PS, (无水箱净流入), 支路流量]。"""
    unknown = [node for node in range(len(network.node_keys)) if node not in network.fixed_pressures]
    return np.concatenate((np.asarray(pressure, dtype=float)[unknown] / PRESSURE_SCALE,
                           np.asarray(flows, dtype=float)))


def _validate(network: CompiledNetwork, pressure: np.ndarray, flows: np.ndarray, rho_b, mu_b) -> None:
    """泵工作点范围校验：与常规路径同样的错误信息，不允许压缩后静默外推。"""
    for index, branch in enumerate(network.branches):
        if branch.solver_model != 'pump_curve':
            continue
        params = network.parameters[branch.instance_id]
        q_volume = flows[index] / (params.get('density_kg_m3') or float(rho_b[index])) * 3600
        if q_volume < -1e-8 or q_volume > params['head_curve'][-1][0] * params['speed_ratio'] + 1e-8:
            raise ValueError(f'{branch.instance_id} 工作点 {q_volume:.6g} m³/h 超出泵曲线范围；'
                             '反向流和曲线外工况尚未支持')


def _check_reference(network: CompiledNetwork, plan: CompressionPlan) -> None:
    """约化图同样要求每个节点都连到压力参考（与常规路径的检查一致）。"""
    specs: list[tuple[str, 'Chain | int']] = [('chain', chain) for chain in plan.chains]
    specs += [('single', index) for index in plan.standalone]
    adjacency: dict[int, set[int]] = {node: set() for node in plan.anchors}
    for kind, item in specs:
        if kind == 'chain':
            assert isinstance(item, Chain)
            start, end = item.start_node, item.end_node
        else:
            assert isinstance(item, int)
            branch = network.branches[item]
            if branch.closed:
                continue
            start, end = branch.start_node, branch.end_node
        adjacency[start].add(end)
        adjacency[end].add(start)
    reached = set(network.fixed_pressures) & set(plan.anchors)
    pending = list(reached)
    while pending:
        node = pending.pop()
        for other in adjacency[node] - reached:
            reached.add(other)
            pending.append(other)
    if len(reached) != len(plan.anchors):
        raise RuntimeErrorBase('模块通路关系产生了缺少压力参考的子网络')


def _solve_compressed(network: CompiledNetwork, plan: CompressionPlan, options,
                      branch_density, branch_viscosity, initial) -> HydraulicResult:
    started = time.perf_counter()
    density, viscosity = reference_properties(network)
    # 非多工质网络（本路径已排除 mixed）的参考物性是一对常数：直接按支路展开，
    # 避免第二次参考物性/物性后端调用。
    branch_count = len(network.branches)
    rho_b = np.full(branch_count, density) if branch_density is None else np.asarray(branch_density, dtype=float)
    mu_b = np.full(branch_count, viscosity) if branch_viscosity is None else np.asarray(branch_viscosity, dtype=float)

    requested = options.hydraulic_method
    choice = choose_hydraulic_method(requested, plan.reduced_size, plan.reduced_nnz)
    method = choice.effective
    reason = (f'{choice.reason}；压缩：{plan.chain_count} 条链、'
              f'{plan.original_size} → {plan.reduced_size} 未知量（节省 {plan.saved_unknowns}）')
    solve = _ReducedSolve(network, plan, rho_b, mu_b, method)

    fixed_level = list(network.fixed_pressures.values())
    cold = np.concatenate((np.full(len(plan.unknown_anchors), np.mean(fixed_level) / PRESSURE_SCALE),
                           solve.cold_flows(fixed_level, options.mass_tolerance_kg_s)))
    warm = _map_initial(network, plan, initial, options.mass_tolerance_kg_s)
    start = cold if warm is None else warm
    warm_start = warm is not None

    counters = SolveCounters() if options.hydraulic_diagnostics else None
    if counters is not None:
        counters.problem_size = plan.reduced_size
        counters.jacobian_nnz = plan.reduced_nnz

    def attempt(vector):
        if counters is not None:
            counters.solver_attempts += 1
        attempt_started = time.perf_counter()
        sparse_options: dict = {}
        if method == 'sparse':
            sparse_options = {'tr_solver': 'lsmr',
                              'tr_options': {'atol': 1e-13, 'btol': 1e-13,
                                             'maxiter': max(100, plan.reduced_size * 4)}}
        sparse_options['jac'] = solve.jacobian
        before = solve.calls
        result = least_squares(solve.residual, vector, max_nfev=options.max_iterations,
                               xtol=1e-12, ftol=1e-12, gtol=1e-12, x_scale='jac', **sparse_options)
        if counters is not None:
            counters.nfev += int(result.nfev)
            counters.njev += int(getattr(result, 'njev', 0) or 0)
            counters.residual_calls += solve.calls - before
            counters.timing_s['least_squares'] = (counters.timing_s.get('least_squares', 0.0)
                                                  + (time.perf_counter() - attempt_started))
        pressure, flows = solve.materialize(result.x)
        pressure_error, mass_error = solve.original_residuals(pressure, flows)
        ok = (result.success and pressure_error <= options.pressure_tolerance_pa
              and mass_error <= options.mass_tolerance_kg_s)
        return result, pressure, flows, pressure_error, mass_error, ok

    result, pressure, flows, pressure_error, mass_error, ok = attempt(start)
    if warm_start and not ok:
        # 与常规路径一致：warm start 只是提示；失败先回退冷启动再报不收敛。
        result, pressure, flows, pressure_error, mass_error, ok = attempt(cold)
    if not ok:
        raise HydraulicNotConverged(f'水力求解未收敛：压力残差 {pressure_error:.6g} Pa，'
                                    f'质量残差 {mass_error:.6g} kg/s；{result.message}（串联压缩，'
                                    f'{plan.original_size}→{plan.reduced_size} 未知量，未放宽容差）')
    _check_reference(network, plan)
    if np.any(pressure <= 0) or not np.all(np.isfinite(result.x)):
        raise HydraulicNotConverged('求解产生非正绝对压力或非有限结果')
    _validate(network, pressure, flows, rho_b, mu_b)

    counters_result = None
    if counters is not None:
        counters.perturbation_calls = max(0, counters.residual_calls - counters.nfev)
        counters.jacobian_evaluations = counters.njev
        counters.module_evaluations = 0
        counters.timing_s['solve_total'] = time.perf_counter() - started
        counters_result = counters.as_dict()
        counters_result.update({
            'series_compression': True,
            'original_problem_size': plan.original_size,
            'reduced_problem_size': plan.reduced_size,
            'compression_chains': plan.chain_count,
            'compressed_branches': plan.compressed_branches,
            'unknowns_saved': plan.saved_unknowns,
        })
    return HydraulicResult(
        pressure, flows, int(result.nfev), pressure_error, mass_error, density, viscosity,
        {}, [], rho_b, mu_b, {}, _solution_layout(network, pressure, flows), {}, counters_result,
        requested, method, reason, plan.reduced_size, plan.reduced_nnz,
        'analytic', '纯内置关系（J2 解析导数；串联链使用复合压降解析斜率）')


# --------------------------------------------------------------------------- 钩子
def solve_hydraulics_hook(network: CompiledNetwork, runners, time_s, *, branch_density=None,
                          branch_viscosity=None, port_base=None, initial=None, storage_step=None,
                          hooks=frozenset()):
    """C0–C3 入口；返回 ``HydraulicResult`` 表示已压缩求解，``None`` 交回常规路径。"""
    options = network.project.solver
    if not options.series_compression:
        return None
    if network.mixed or runners or port_base is not None or storage_step is not None:
        return None
    if _python_instances(network):
        return None
    plan = _cached_plan(network)
    if plan is None or not plan.chains:
        return None
    return _solve_compressed(network, plan, options, branch_density, branch_viscosity, initial)


__all__ = ['ChainMember', 'Chain', 'CompressionPlan', 'SUPPORTED_MODELS',
           'plan_compression', 'solve_hydraulics_hook']
