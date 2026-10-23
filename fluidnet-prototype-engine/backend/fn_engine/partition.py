"""依赖安全的水力分块求解（D0–D2）。

`solver._solve_hydraulics` 在 `SolverOptions.hydraulic_blocks=True` 时延迟导入本模块并调用
`solve_hydraulics_hook(...)`；返回 `HydraulicResult` 表示已处理，返回 `None` 表示不适用
（继续常规全网求解）。

分块依据（D0，纯函数 `build_blocks`）：

- 只有「会传递压力耦合」的支路才把两个节点并到一块。编译期标记为关闭的支路（`branch.closed`）
  只贡献零流量约束，是块边界；水箱节点与压力边界节点是已知/可解的压力参考，不把相邻块耦合。
- Python 实例的通路关系在运行期才确定（可能变成关闭阀或强制流量压缩机），因此**同一 Python
  实例的全部端口所属节点保守同块**；其支路即使运行期不传压力也不拆开（只会让块比必要的大）。
- 内置换热器 `heat_exchanger` 的两侧水力独立、热力耦合：两侧各自成块，块间记录 `thermal`
  依赖边（方向只用于报告，实际热流双向）。
- 任何无法证明独立性（未知支路模型、未知 Python 端口、节点分量信息缺失、跨工质同块等）都
  降级为整网一块（`degraded=True`），`solve_hydraulics_hook` 随即返回 `None`，走原路径。

D1 顺序分块求解：逐块构造 `CompiledNetwork` 子视图（`dataclasses.replace`，不复制 Worker），
用传入的 `runners` 子集调用 `solve_hydraulics(..., hooks=frozenset({'compression'}))`，再把
压力/流量/水箱净流入/`solution` 按**原网络**索引合并；任何块失败都抛出带块号与原设备的异常，
所有块成功后才返回结果。分块只改变求解路径，不改变物理方程与收敛门（3.1 差值门）。

D2 动态与事务：本模块不创建/关闭 Worker，不提交 `commit_step`；块划分按「结构 + 静态闭合
状态 + Python 端口关系」缓存（`plan_signature`），动态阀门状态/模块运行期关系变化只能让耦合
变少（安全方向），不会让已独立的块重新耦合，因此缓存无需按运行期关系失效。
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import time
from dataclasses import dataclass, field

import numpy as np

from .compiler import CompilationError, CompiledNetwork, DisjointSet
from .models import EvaluateResponse
from .runtime import RuntimeErrorBase
from .solver import (PRESSURE_SCALE, HydraulicNotConverged, HydraulicResult, reference_arrays,
                     reference_properties, solve_hydraulics)

# 与 solver._HOOK_MODULES 对齐：分块模块是 D 在 C 的外层，块内仍可继续调用 C。
_HOOK_MODULES = {'compression': 'fn_engine.hydraulic_plan'}

# 内置设备编译出的支路模型；表外模型无法判断是否传递压力耦合，必须降级。
_KNOWN_BRANCH_MODELS = frozenset({'pipe', 'valve', 'pump_curve', 'resistance', 'heat_exchanger'})

# 计划缓存上限：键是结构签名，值只含索引，可跨时间步复用。
_PLAN_CACHE_LIMIT = 64


class HydraulicBlockFailure(HydraulicNotConverged):
    """块级水力不收敛：消息含块号与原设备，仍按可缩步的收敛失败处理。"""

    code = 'HYDRAULIC_NOT_CONVERGED'

    def __init__(self, block_id, total, instances, error):
        self.block_id = block_id
        self.instances = tuple(instances)
        detail = '、'.join(self.instances) if self.instances else '仅节点'
        super().__init__(f'水力分块 {block_id}/{total} 求解未收敛（{detail}）：{error}')


class BlockSolveError(ValueError):
    """块级非收敛失败（泵曲线越界、模块运行错误等），保留原异常 code 的终止语义。"""

    def __init__(self, block_id, total, instances, error):
        self.block_id = block_id
        self.instances = tuple(instances)
        self.code = getattr(error, 'code', 'BLOCK_SOLVE_FAILED')
        detail = '、'.join(self.instances) if self.instances else '仅节点'
        super().__init__(f'水力分块 {block_id}/{total} 求解失败（{detail}）：{error}')


@dataclass
class Block:
    """一个可独立求解的水力块（节点/支路均为原网络索引）。"""

    id: int
    nodes: tuple[int, ...]
    branches: tuple[int, ...]
    # 非关闭支路：参与子网络求解；关闭支路只贡献“流量=0”，合并时直接写 0（详见模块文档）。
    open_branches: tuple[int, ...]
    fixed_nodes: tuple[int, ...]
    tank_nodes: tuple[int, ...]
    # 稳态（水箱当固定压力）与动态（水箱净流入作未知量）的未知量个数。
    unknowns_steady: int
    unknowns_dynamic: int
    circuits: tuple[int, ...]
    instances: tuple[str, ...]
    reason: str
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BlockDependency:
    """块间依赖边。`kind='thermal'`：水力独立、热力耦合（换热器两侧）。"""

    source: int
    target: int
    kind: str
    detail: str


@dataclass
class PartitionPlan:
    blocks: list[Block]
    dependencies: list[BlockDependency]
    degraded: bool
    reason: str
    notes: list[str]
    node_block: list[int]
    branch_block: list[int]
    signature: str = ''

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    @property
    def solvable_blocks(self) -> list[Block]:
        """有非关闭支路的块；只有关闭支路或只有已知边界的块无需求解。"""
        return [block for block in self.blocks if block.open_branches]

    @property
    def total_unknowns_steady(self) -> int:
        return sum(block.unknowns_steady for block in self.blocks)

    @property
    def total_unknowns_dynamic(self) -> int:
        return sum(block.unknowns_dynamic for block in self.blocks)

    def to_json(self) -> dict:
        return {
            'degraded': self.degraded,
            'reason': self.reason,
            'signature': self.signature,
            'block_count': self.block_count,
            'unknowns_steady': self.total_unknowns_steady,
            'unknowns_dynamic': self.total_unknowns_dynamic,
            'nodes': len(self.node_block),
            'branches': len(self.branch_block),
            'notes': list(self.notes),
            'blocks': [
                {'id': block.id, 'nodes': list(block.nodes), 'branches': list(block.branches),
                 'open_branches': list(block.open_branches), 'fixed_nodes': list(block.fixed_nodes),
                 'tank_nodes': list(block.tank_nodes), 'unknowns_steady': block.unknowns_steady,
                 'unknowns_dynamic': block.unknowns_dynamic, 'circuits': list(block.circuits),
                 'instances': list(block.instances), 'reason': block.reason, 'notes': list(block.notes)}
                for block in self.blocks],
            'dependencies': [dataclasses.asdict(edge) for edge in self.dependencies],
        }


_PLAN_CACHE: dict[str, PartitionPlan] = {}


def _node_circuit(network) -> list[int]:
    circuits = list(getattr(network, 'node_circuit', []) or ())
    return circuits if len(circuits) == len(network.node_keys) else [0] * len(network.node_keys)


def _module_of(network, instance_id):
    instance = network.instances.get(instance_id)
    if instance is None:
        return None
    return network.modules.get(instance.module_id)


def plan_signature(network) -> str:
    """结构 + 静态闭合状态 + Python 端口关系的稳定签名（用于计划缓存失效）。

    不含压力/温度数值：同一步内热力外迭代与时间推进只改物性/边界，块划分不变。
    """
    circuits = list(getattr(network, 'circuit_fluids', []) or ())
    payload = {
        'version': 'd0.1',
        'nodes': len(getattr(network, 'node_keys', ()) or ()),
        'components': list(getattr(network, 'node_component', ()) or ()),
        'node_circuit': _node_circuit(network),
        'circuits': [fluid.model_dump(mode='json') for fluid in circuits],
        'mixed': bool(getattr(network, 'mixed', False)),
        'branches': [[branch.instance_id, branch.channel_id, branch.start_node, branch.end_node,
                      branch.closed, branch.solver_model] for branch in network.branches],
        'python': sorted(
            [instance_id, module.runtime, [[port.id, network.port_nodes.get(f'{instance_id}:{port.id}', -1)]
                                           for port in module.ports]]
            for instance_id, module in
            ((instance_id, _module_of(network, instance_id)) for instance_id in network.instances)
            if module is not None and module.runtime == 'python'),
    }
    text = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def clear_plan_cache() -> None:
    """清空计划缓存（测试与诊断用；正常求解不调用）。"""
    _PLAN_CACHE.clear()


def resolve_plan(network) -> PartitionPlan:
    """按签名缓存的分块计划；结构/闭合状态/Python 端口变化时自动重算。"""
    signature = plan_signature(network)
    plan = _PLAN_CACHE.get(signature)
    if plan is None:
        plan = build_blocks(network, signature=signature)
        if len(_PLAN_CACHE) >= _PLAN_CACHE_LIMIT:
            _PLAN_CACHE.clear()
        _PLAN_CACHE[signature] = plan
    return plan


def _unknown_counts(nodes, branches, fixed, tanks):
    steady = sum(1 for node in nodes if node not in fixed) + len(branches)
    dynamic = (sum(1 for node in nodes if node not in fixed and node not in tanks)
               + sum(1 for node in nodes if node in tanks) + len(branches))
    return steady, dynamic


def _degrade(network, reason, notes=()) -> PartitionPlan:
    """整网一块：不满足可证明的分块条件时，分块求解放弃（hook 返回 None）。"""
    n = len(getattr(network, 'node_keys', ()) or ())
    branches = list(getattr(network, 'branches', ()) or ())
    fixed = set(getattr(network, 'fixed_pressures', {}) or {})
    tanks = set(getattr(network, 'storage', {}) or {})
    nodes = tuple(range(n))
    indices = tuple(range(len(branches)))
    open_indices = tuple(index for index in indices if not branches[index].closed)
    steady, dynamic = _unknown_counts(nodes, indices, fixed, tanks)
    block = Block(0, nodes, indices, open_indices, tuple(node for node in nodes if node in fixed),
                  tuple(node for node in nodes if node in tanks), steady, dynamic,
                  tuple(sorted(set(_node_circuit(network)))), tuple(sorted({b.instance_id for b in branches})),
                  f'降级整网一块：{reason}', list(notes))
    return PartitionPlan([block], [], True, f'降级整网一块：{reason}', list(notes),
                         [0] * n, [0] * len(branches), plan_signature(network))


def _reason_for(nodes, indices, branch_models, notes) -> str:
    parts = [f'独立连通分量：{len(nodes)} 节点 / {len(indices)} 支路']
    if branch_models:
        parts.append('支路模型 ' + '/'.join(sorted(branch_models)))
    if notes:
        parts.append('Python 端口保守同块')
    return '；'.join(parts)


def build_blocks(network, signature: str | None = None) -> PartitionPlan:
    """D0：纯函数块划分与依赖图（不求解、不改 network）。"""
    n = len(getattr(network, 'node_keys', ()) or ())
    branches = list(getattr(network, 'branches', ()) or ())
    m = len(branches)
    if n == 0 or m == 0:
        return _degrade(network, '网络没有节点或支路（UNKNOWN_STRUCTURE）')
    fixed = set(getattr(network, 'fixed_pressures', {}) or {})
    tanks = set(getattr(network, 'storage', {}) or {})
    node_component = list(getattr(network, 'node_component', ()) or ())
    port_nodes = getattr(network, 'port_nodes', {}) or {}
    instances = getattr(network, 'instances', {}) or {}
    modules = getattr(network, 'modules', {}) or {}
    circuit = _node_circuit(network)
    mixed = bool(getattr(network, 'mixed', False))

    problems = []
    if len(node_component) != n:
        # 没有编译期分量信息就无法证明独立性：直接整网一块，避免后面按分量索引。
        return _degrade(network, 'NODE_COMPONENT_UNKNOWN：编译期节点分量信息缺失')
    dsu = DisjointSet(range(n))
    python_roots, python_port_nodes = {}, {}
    for instance_id, instance in instances.items():
        module = modules.get(instance.module_id)
        if module is None:
            problems.append(f'MODULE_UNKNOWN：实例 {instance_id} 的模块定义缺失')
            continue
        if module.runtime != 'python':
            continue
        keys = [f'{instance_id}:{port.id}' for port in module.ports]
        missing = [key for key in keys if key not in port_nodes]
        if missing:
            problems.append(f'PYTHON_PORT_UNKNOWN：实例 {instance_id} 的端口 {missing} 没有节点映射')
            continue
        first = port_nodes[keys[0]]
        nodes_of_instance = [port_nodes[key] for key in keys]
        for node in nodes_of_instance[1:]:
            dsu.union(first, node)
        python_roots[instance_id] = frozenset(node_component[node] for node in nodes_of_instance)
        python_port_nodes[instance_id] = tuple(nodes_of_instance)

    branch_models = {}
    for index, branch in enumerate(branches):
        if not (0 <= branch.start_node < n and 0 <= branch.end_node < n):
            problems.append(f'BRANCH_NODE_RANGE：支路 {index} 的节点越界')
            continue
        module = _module_of(network, branch.instance_id)
        if module is None:
            problems.append(f'INSTANCE_UNKNOWN：支路 {index} 的实例 {branch.instance_id} 未注册')
            continue
        branch_models[index] = branch.solver_model
        if module.runtime != 'python' and branch.solver_model not in _KNOWN_BRANCH_MODELS:
            problems.append(f'BRANCH_MODEL_UNKNOWN：支路 {index}（{branch.instance_id}:{branch.channel_id}）'
                            f'模型 {branch.solver_model} 的耦合性质未知')
            continue
        if not branch.closed:
            dsu.union(branch.start_node, branch.end_node)

    if problems:
        return _degrade(network, '未知依赖：' + '；'.join(problems))
    if mixed and len(set(circuit)) > 1:
        for root in {dsu.find(node) for node in range(n)}:
            members = {node for node in range(n) if dsu.find(node) == root}
            if len({circuit[node] for node in members}) > 1:
                return _degrade(network, 'CROSS_CIRCUIT_BLOCK：同一块跨多个工质回路，无法构造单工质子网络',
                                ('Python 实例端口可能跨回路；保守整网求解',))

    groups: dict[int, list[int]] = {}
    for node in range(n):
        groups.setdefault(dsu.find(node), []).append(node)
    order = sorted(groups.values(), key=min)
    blocks, node_block = [], [-1] * n
    for block_id, nodes in enumerate(order):
        nodes_t = tuple(sorted(nodes))
        node_set = set(nodes_t)
        # 每条支路归属其 start_node 所在的块：关闭支路的两端本来就可能分属不同块，
        # 它只贡献“流量=0”，不属于对侧块（对侧块也无需这条支路的平衡行）。
        indices = tuple(index for index, branch in enumerate(branches) if branch.start_node in node_set)
        open_indices = tuple(index for index in indices if not branches[index].closed)
        for node in nodes_t:
            node_block[node] = block_id
        fixed_nodes = tuple(node for node in nodes_t if node in fixed)
        tank_nodes = tuple(node for node in nodes_t if node in tanks)
        steady, dynamic = _unknown_counts(nodes_t, indices, fixed, tanks)
        circuits = tuple(sorted({circuit[node] for node in nodes_t}))
        block_instances = tuple(sorted({branches[index].instance_id for index in indices}))
        notes = []
        if len({node_component[node] for node in nodes_t}) > 1:
            spanning = [instance_id for instance_id, port_nodes_of in python_port_nodes.items()
                        if port_nodes_of[0] in node_set and len(python_roots[instance_id]) > 1]
            for instance_id in spanning:
                notes.append(f'Python 实例 {instance_id} 的 {len(python_port_nodes[instance_id])} 个端口'
                             '跨多个静态回路，保守同块（运行期关系未知）')
        if nodes_t and not (set(nodes_t) & (fixed | tanks)):
            problems.append(f'PRESSURE_REFERENCE_MISSING：块 {block_id} 没有压力参考')
        if not open_indices and not (set(nodes_t) & (fixed | tanks)):
            problems.append(f'PASSIVE_BLOCK_UNKNOWN_PRESSURE：块 {block_id} 无开放支路且无已知压力')
        models = {branch_models.get(index, branches[index].solver_model) for index in indices}
        blocks.append(Block(block_id, nodes_t, indices, open_indices, fixed_nodes, tank_nodes, steady, dynamic,
                            circuits, block_instances, _reason_for(nodes_t, indices, models, notes), notes))

    if problems:
        return _degrade(network, '未知依赖：' + '；'.join(problems))
    dependencies = _thermal_dependencies(network, blocks, node_block)

    expected_steady = sum(1 for node in range(n) if node not in fixed) + m
    expected_dynamic = (sum(1 for node in range(n) if node not in fixed and node not in tanks)
                        + len(tanks) + m)
    actual_steady = sum(block.unknowns_steady for block in blocks)
    actual_dynamic = sum(block.unknowns_dynamic for block in blocks)
    if (sum(len(block.nodes) for block in blocks) != n or sum(len(block.branches) for block in blocks) != m
            or actual_steady != expected_steady or actual_dynamic != expected_dynamic):
        return _degrade(network, 'BLOCK_INTEGRITY：块划分未覆盖全部节点/支路或未知量计数不一致')

    branch_block = [-1] * m
    for block in blocks:
        for index in block.branches:
            branch_block[index] = block.id
    notes = [f'共 {len(blocks)} 块；稳态未知量 {actual_steady}，动态未知量 {actual_dynamic}']
    python_split = sorted(instance_id for instance_id, roots in python_roots.items() if len(roots) > 1)
    if python_split:
        notes.append('Python 多端口实例保守同块：' + '、'.join(python_split))
    return PartitionPlan(blocks, dependencies, False, '按独立连通分量与 Python 端口保守分块',
                         notes, node_block, branch_block, signature or plan_signature(network))


def _thermal_dependencies(network, blocks, node_block) -> list[BlockDependency]:
    """换热器两侧在块间记热力依赖边，并在块说明里标注“水力独立、热力耦合”。"""
    edges = []
    for instance_id, instance in network.instances.items():
        module = _module_of(network, instance_id)
        if module is None or module.runtime != 'builtin':
            continue
        if module.solver_model != 'heat_exchanger' and not module.thermal_model:
            continue
        channels = [branch for branch in network.branches if branch.instance_id == instance_id]
        if len(channels) < 2:
            continue
        by_block: dict[int, list[str]] = {}
        for branch in channels:
            by_block.setdefault(node_block[branch.start_node], []).append(branch.channel_id)
        if len(by_block) < 2:
            continue
        ids = sorted(by_block)
        for left in range(len(ids)):
            for right in range(left + 1, len(ids)):
                first, second = ids[left], ids[right]
                edges.append(BlockDependency(first, second, 'thermal',
                                             f'{instance_id}：{by_block[first]} 与 {by_block[second]} 两侧'))
        for block_id, own in by_block.items():
            others = [f'块 {other}（{"/".join(by_block[other])}）' for other in ids if other != block_id]
            blocks[block_id].notes.append(f'{instance_id} 的 {"/".join(own)} 在本块；对侧 {", ".join(others)}'
                                          '：水力独立、热力耦合')
    return edges


def _layout(network, tank_old):
    tank_old = tank_old or {}
    fixed = {node for node in network.fixed_pressures if node not in tank_old}
    unknown_nodes = [node for node in range(len(network.node_keys))
                     if node not in fixed and node not in tank_old]
    tank_nodes = [node for node in sorted(network.storage) if node in tank_old]
    return unknown_nodes, tank_nodes, len(unknown_nodes) + len(tank_nodes)


def _slice_initial(initial, network, block, tank_old):
    """把原网络未知量向量切成本块子网络的未知量向量；不匹配时返回 None（冷启动）。"""
    if initial is None:
        return None
    array = np.asarray(initial, dtype=float)
    unknown_nodes, tank_nodes, flows_offset = _layout(network, tank_old)
    if array.shape != (flows_offset + len(network.branches),) or not np.all(np.isfinite(array)):
        return None
    tank_old = tank_old or {}
    fixed = {node for node in network.fixed_pressures if node not in tank_old}
    unknown_pos = {node: index for index, node in enumerate(unknown_nodes)}
    tank_pos = {node: index for index, node in enumerate(tank_nodes)}
    pressures = [array[unknown_pos[node]] for node in block.nodes if node not in fixed and node not in tank_old]
    rates = [array[len(unknown_nodes) + tank_pos[node]] for node in block.tank_nodes if node in tank_old]
    flows = [array[flows_offset + index] for index in block.open_branches]
    return np.concatenate((np.array(pressures, dtype=float), np.array(rates, dtype=float),
                           np.array(flows, dtype=float)))


def _local_network(network, block) -> CompiledNetwork:
    """块的 CompiledNetwork 视图：节点/支路/边界/水箱/端口映射全部改成本地索引。"""
    local = {node: index for index, node in enumerate(block.nodes)}
    branches = []
    for index in block.open_branches:
        branch = network.branches[index]
        branches.append(dataclasses.replace(branch, start_node=local[branch.start_node],
                                            end_node=local[branch.end_node]))
    circuits = list(getattr(network, 'circuit_fluids', []) or ())
    sources = list(getattr(network, 'circuit_sources', []) or ())
    circuit = block.circuits[0] if block.circuits else 0
    if getattr(network, 'mixed', False) and circuits:
        circuit_fluids = [circuits[min(circuit, len(circuits) - 1)]]
        circuit_sources = [sources[min(circuit, len(sources) - 1)] if sources else 'project']
        mixed = True
    else:
        circuit_fluids = circuits or [network.project.fluid]
        circuit_sources = sources or ['project']
        mixed = False
    storage = {}
    for node, spec in network.storage.items():
        if node in local:
            storage[local[node]] = dataclasses.replace(spec, node=local[node])
    return dataclasses.replace(
        network,
        branches=branches,
        node_keys=[network.node_keys[node] for node in block.nodes],
        fixed_pressures={local[node]: value for node, value in network.fixed_pressures.items() if node in local},
        fixed_temperatures={local[node]: value for node, value in network.fixed_temperatures.items() if node in local},
        port_nodes={key: local[node] for key, node in network.port_nodes.items() if node in local},
        node_component=[0] * len(block.nodes),
        node_circuit=[0] * len(block.nodes),
        circuit_fluids=circuit_fluids,
        circuit_sources=circuit_sources,
        mixed=mixed,
        storage=storage,
    )


class _RunnerSubset(dict):
    """批量 Worker 的块视图：只为有请求的分片发一个批量 RPC，空闲分片不打扰。

    不创建/关闭任何 Worker；`runners` 始终来自调用方（顶层求解器）。
    """

    def __init__(self, parent, instance_ids):
        super().__init__((instance_id, parent[instance_id]) for instance_id in instance_ids)
        self._parent = parent
        self._rpc_count = 0

    @property
    def request_count(self):
        return self._rpc_count

    def evaluate(self, requests):
        handles = {}
        for key in requests:
            handle = self.get(key)
            worker = getattr(handle, 'worker', None)
            if worker is None:
                # 结构不符合 BatchRunners：退回父对象（仍不创建进程）。
                return self._parent.evaluate(requests)
            handles.setdefault(worker, {})[key] = {
                'action': 'evaluate', 'instance_id': key, 'request': requests[key].model_dump(mode='json')}
        pool = getattr(self._parent, 'pool', None)

        def execute(item):
            worker, items = item
            return worker._request({'action': 'batch', 'items': items})

        self._rpc_count += len(handles)
        results = (list(pool.map(execute, handles.items())) if pool
                   else [execute(item) for item in handles.items()])
        return {key: EvaluateResponse.model_validate(value) for result in results for key, value in result.items()}


def _runner_subset(runners, network, block):
    if runners is None:
        return None
    python_ids = set()
    for index in block.open_branches:
        branch = network.branches[index]
        module = _module_of(network, branch.instance_id)
        if module is not None and module.runtime == 'python':
            python_ids.add(branch.instance_id)
    if not python_ids:
        return {}
    missing = sorted(instance_id for instance_id in python_ids if instance_id not in runners)
    if missing:
        raise RuntimeErrorBase(f'分块求解缺少 Python 实例的 runner：{missing}')
    if hasattr(runners, 'evaluate'):
        return _RunnerSubset(runners, sorted(python_ids))
    return {instance_id: runners[instance_id] for instance_id in sorted(python_ids)}


def _hook_available(name) -> bool:
    module = _HOOK_MODULES.get(name)
    if module is None:
        return False
    try:
        importlib.import_module(module)
    except ImportError:
        return False
    return True


def _merge_counters(items):
    if not items:
        return None
    merged = {}
    fallbacks = []
    for counters in items:
        for key, value in counters.items():
            if key == 'timing_s':
                target = merged.setdefault('timing_s', {})
                for name, seconds in value.items():
                    target[name] = target.get(name, 0.0) + float(seconds)
            elif key == 'method_fallback':
                if value:
                    fallbacks.append(str(value))
            elif key in ('blocks', 'block_count', 'blocks_wall_s', 'plan_degraded'):
                continue
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                merged[key] = merged.get(key, 0) + value
            else:
                merged.setdefault(key, value)
    merged['method_fallback'] = '；'.join(dict.fromkeys(fallbacks))
    return merged


def _solve_subnetwork(subnetwork, runners, time_s, *, hook_fallback, sub_hooks, **options):
    """块内子求解；C 钩子模块缺失时回退到 frozenset()（不递归回 blocks）。"""
    try:
        return solve_hydraulics(subnetwork, runners=runners, time_s=time_s, hooks=sub_hooks, **options)
    except ImportError:
        if not sub_hooks:
            raise
        hook_fallback.extend(sorted(sub_hooks))
        return solve_hydraulics(subnetwork, runners=runners, time_s=time_s, hooks=frozenset(), **options)


def solve_hydraulics_hook(network, runners, time_s, *, branch_density=None, branch_viscosity=None,
                          port_base=None, initial=None, storage_step=None, hooks=frozenset()):
    """D1/D2：按块顺序求解并合并；不适用时返回 None（继续常规求解）。

    只使用传入的 `runners`（不新建/关闭 Worker，不提交任何状态）。块内继续允许 C 压缩钩子，
    但绝不把 `blocks` 传给子求解，避免递归。
    """
    plan = resolve_plan(network)
    if plan.degraded or len(plan.solvable_blocks) <= 1:
        return None
    if runners is None:
        # 直接以 None 调用时不接管：交给常规路径创建/关闭 Worker，避免块内重复创建。
        return None

    options = network.project.solver
    requested_hooks = frozenset(name for name in (hooks or frozenset()) if name != 'blocks')
    sub_hooks = frozenset(name for name in requested_hooks if _hook_available(name))
    hook_fallback = sorted(requested_hooks - sub_hooks)
    started = time.perf_counter()
    n = len(network.node_keys)
    m = len(network.branches)
    dt_s, tank_old = storage_step[:2] if storage_step is not None else (None, {})
    tank_old = tank_old or {}
    unknown_nodes, tank_nodes, flows_offset = _layout(network, tank_old)
    densities = None if branch_density is None else np.asarray(branch_density, dtype=float)
    viscosities = None if branch_viscosity is None else np.asarray(branch_viscosity, dtype=float)

    pressures = np.zeros(n)
    flows = np.zeros(m)
    filled = np.zeros(n, dtype=bool)
    storage_rates = {}
    module_variables, module_diagnostics, relations = {}, [], {}
    pressure_residual = mass_residual = 0.0
    iterations = 0
    matrix_size = matrix_nnz = 0
    counter_inputs, block_records = [], []
    methods, jacobian_modes, reasons = [], [], []
    active = plan.solvable_blocks

    for block in plan.blocks:
        local_index = {node: index for index, node in enumerate(block.nodes)}
        if not block.open_branches:
            # 只有已知边界/关闭支路的块：没有非线性方程，直接写回已知压力（水箱按当前质量），
            # 关闭支路的流量按定义精确为 0。
            for node in block.nodes:
                if node in tank_old and node in network.storage:
                    spec = network.storage[node]
                    storage_rates[node] = 0.0
                    pressures[node] = spec.pressure(tank_old[node].mass_kg)
                else:
                    pressures[node] = network.fixed_pressures[node]
                filled[node] = True
            for index in block.branches:
                flows[index] = 0.0
            continue
        for index in block.branches:
            if network.branches[index].closed:
                flows[index] = 0.0
        subnetwork = _local_network(network, block)
        sub_runners = _runner_subset(runners, network, block)
        sub_initial = _slice_initial(initial, network, block, tank_old)
        sub_storage_step = None
        if tank_old:
            local_tanks = {local_index[node]: state for node, state in tank_old.items() if node in local_index}
            if local_tanks:
                sub_storage_step = (dt_s, local_tanks)
        block_density = None if densities is None else densities[list(block.open_branches)]
        block_viscosity = None if viscosities is None else viscosities[list(block.open_branches)]
        block_started = time.perf_counter()
        try:
            sub = _solve_subnetwork(
                subnetwork, sub_runners, time_s, hook_fallback=hook_fallback, sub_hooks=sub_hooks,
                branch_density=block_density, branch_viscosity=block_viscosity, port_base=port_base,
                initial=sub_initial, storage_step=sub_storage_step)
        except CompilationError:
            raise
        except HydraulicNotConverged as error:
            raise HydraulicBlockFailure(block.id, plan.block_count, block.instances, error) from error
        except Exception as error:  # noqa: BLE001 - 块级失败统一定位，保留原 code 语义
            raise BlockSolveError(block.id, plan.block_count, block.instances, error) from error
        wall_s = time.perf_counter() - block_started
        for index, node in enumerate(block.nodes):
            pressures[node] = sub.pressures[index]
            filled[node] = True
        for position, index in enumerate(block.open_branches):
            flows[index] = sub.flows[position]
        for node in block.tank_nodes:
            if node in tank_old:
                storage_rates[node] = float(sub.storage_rates.get(local_index[node], 0.0))
        if sub.module_variables:
            module_variables.update(sub.module_variables)
        if sub.module_diagnostics:
            module_diagnostics.extend(sub.module_diagnostics)
        if sub.relations:
            relations.update(sub.relations)
        pressure_residual = max(pressure_residual, float(sub.pressure_residual))
        mass_residual = max(mass_residual, float(sub.mass_residual))
        iterations += int(sub.iterations)
        matrix_size = max(matrix_size, int(getattr(sub, 'matrix_size', 0) or 0))
        matrix_nnz += int(getattr(sub, 'matrix_nnz', 0) or 0)
        methods.append(sub.effective_method)
        jacobian_modes.append(sub.jacobian_mode)
        reasons.append(f'块 {block.id} {len(block.nodes)} 节点/{len(block.open_branches)} 开放支路 '
                       f'{wall_s * 1e3:.1f} ms')
        if sub.counters is not None:
            counter_inputs.append(sub.counters)
            block_records.append({'block': block.id, 'nodes': len(block.nodes),
                                  'branches': len(block.branches), 'size': int(sub.matrix_size),
                                  'nfev': int(sub.counters.get('nfev', 0)),
                                  'residual_calls': int(sub.counters.get('residual_calls', 0)),
                                  'wall_s': wall_s, 'pressure_residual': float(sub.pressure_residual),
                                  'mass_residual': float(sub.mass_residual)})

    if not np.all(filled):
        missing = [int(index) for index in np.flatnonzero(~filled)]
        raise BlockSolveError(-1, plan.block_count, (), f'分块合并未覆盖节点 {missing}')

    density, viscosity = reference_properties(network)
    _rho_n, _mu_n, rho_ref, mu_ref = reference_arrays(network)
    rho_b = rho_ref if densities is None else densities
    mu_b = mu_ref if viscosities is None else viscosities
    pressure_part = np.array([pressures[node] for node in unknown_nodes], dtype=float) / PRESSURE_SCALE
    rate_part = np.array([storage_rates.get(node, 0.0) for node in tank_nodes], dtype=float)
    solution = np.concatenate((pressure_part, rate_part, flows))
    counters = _merge_counters(counter_inputs)
    if counters is not None:
        counters['blocks'] = block_records
        counters['block_count'] = len(plan.blocks)
        counters['blocks_wall_s'] = time.perf_counter() - started
        counters['plan_degraded'] = False
    effective = methods[0] if methods and len(set(methods)) == 1 else 'mixed'
    jacobian_mode = jacobian_modes[0] if jacobian_modes and len(set(jacobian_modes)) == 1 else 'mixed'
    method_reason = (f'分块求解 {len(active)}/{plan.block_count} 块（{plan.reason}）；' + '；'.join(reasons))
    if hook_fallback:
        method_reason += f'；钩子模块不可用已回退：{",".join(dict.fromkeys(hook_fallback))}'
    return HydraulicResult(
        pressures, flows, iterations, pressure_residual, mass_residual, density, viscosity,
        module_variables, module_diagnostics, rho_b, mu_b, relations, solution, storage_rates, counters,
        options.hydraulic_method, effective, method_reason, matrix_size, matrix_nnz,
        jacobian_mode, '分块求解：各块独立选择' if jacobian_mode == 'mixed' else '分块求解沿用各块判定')



