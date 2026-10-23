"""数值优化专项共享样例工厂（B1）。

覆盖六类拓扑，每类小/中/大三档：

================  ============================================  ==============================
拓扑              说明                                          规模参数
================  ============================================  ==============================
series            串联链（兼容原 100/500/1000 实例入口）        实例数
parallel          两路并联（两条链经两个汇合节点）              实例数
mesh              二维多环网格（junction + 水平/垂直管道）      网格行列数
components        多独立连通分量（每段自带压力参考）            分量数 × 每段链长
thermal-dual-loop 热耦合双回路（换热器连接冷/热两种工质）      每侧串联管道数
python-multiport  Python 多端口依赖实例（双通道 Python 模块）    模块实例数
================  ============================================  ==============================

本模块只构造 ``Project``，不改变任何求解器默认值；规模统计在编译后进行，
不把“实例数”当作“水力未知量”。计数口径见 :func:`describe`。
"""
from __future__ import annotations

from pathlib import Path

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import (
    ChannelSpec,
    CircuitFluid,
    Connection,
    Endpoint,
    FluidConfig,
    ModuleDefinition,
    ModuleInstance,
    ParameterSpec,
    PortSpec,
    Project,
)

ROOT = Path(__file__).resolve().parents[1]
MEG30 = 'INCOMP::MEG[0.3]'

FAMILIES = ('series', 'parallel', 'mesh', 'components', 'thermal-dual-loop', 'python-multiport')
TIERS = ('small', 'medium', 'large')

# 各拓扑自己的三档规模。series 直接沿用原基准的 100/500/1000 实例。
SERIES_INSTANCES = {'small': 100, 'medium': 500, 'large': 1000}
PARALLEL_INSTANCES = {'small': 12, 'medium': 52, 'large': 200}
MESH_GRID = {'small': (3, 3), 'medium': (6, 6), 'large': (10, 10)}
COMPONENT_LAYOUT = {'small': (2, 3), 'medium': (4, 11), 'large': (8, 30)}
DUAL_LOOP_LENGTH = {'small': 2, 'medium': 8, 'large': 20}
PYTHON_MULTIPORT_COUNT = {'small': 4, 'medium': 16, 'large': 48}


def endpoint(text):
    instance, port = text.split(':')
    return Endpoint(instance_id=instance, port_id=port)


def custom_kind_ids():
    """样例工厂自己注册的模块 ID；``assemble`` 不会从内置目录里取它们。"""
    return {'grid_junction', PYTHON_MULTIPORT_ID}


def assemble(name, nodes, edges, extra_modules=()):
    """按 ``(实例 ID, 内置模块 ID, 参数)`` 与 ``源端口:目标端口`` 组装项目。"""
    catalog = catalog_map()
    extra = {module.id: module for module in extra_modules}
    kinds = sorted({kind for _, kind, _ in nodes})
    missing = [kind for kind in kinds if kind not in catalog and kind not in extra]
    if missing:
        raise KeyError(f'未知模块类型：{missing}')
    definitions = [catalog[kind] for kind in kinds if kind in catalog]
    definitions.extend(extra[kind] for kind in kinds if kind in extra)
    return Project(
        id=name,
        name=name,
        modules=definitions,
        instances=[ModuleInstance(id=i, name=i, module_id=kind, parameters=params) for i, kind, params in nodes],
        connections=[Connection(id=f'e{n}', source=endpoint(a), target=endpoint(b)) for n, (a, b) in enumerate(edges)],
    )


def grid_junction(port_count=4):
    """四端口汇合节点：二维网格内部节点的实际度数，端口可留空。

    内置 junction 的端口变量绑定在 in0/out0/out1 上，替换端口后必须同步重建这组
    变量，否则 ``Project`` 校验会报“变量引用了不存在的端口”。
    """
    base = catalog_map()['junction'].model_copy(deep=True)
    base.id = 'grid_junction'
    base.name = '网格节点'
    template = [variable.model_copy(deep=True) for variable in base.variables if variable.port_id == 'out0']
    kept = [variable.model_copy(deep=True) for variable in base.variables if variable.port_id is None]
    base.ports = [PortSpec(id=f'p{i}', label=f'支路{i + 1}', direction='in' if i % 2 == 0 else 'out',
                           required=False) for i in range(port_count)]
    for i in range(port_count):
        port_id = f'p{i}'
        for variable in template:
            clone = variable.model_copy(deep=True)
            clone.id = variable.id.replace('out0', port_id)
            clone.label = variable.label.replace('out0', port_id)
            clone.port_id = port_id
            kept.append(clone)
    base.variables = kept
    return base


PYTHON_MULTIPORT_ID = 'python_twoport'

PYTHON_MULTIPORT_SOURCE = '''class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("throughput_kg", 0.0)
        ctx.state.setdefault("commit_count", 0)

    def evaluate(self, ctx):
        for channel in ("a", "b"):
            ctx.net.valve(channel=channel, kv=ctx.parameter("kv_m3_h"),
                          opening=ctx.parameter("opening_ratio"))
        for port in ("in0", "in1"):
            state = ctx.port(port)
            ctx.var("rho_" + port, ctx.fluid_at(port).state_pt(
                state.pressure_pa, state.temperature_k).density_kg_m3)

    def commit_step(self, ctx, dt_s):
        flow = abs(ctx.channel("a").mass_flow_kg_s) + abs(ctx.channel("b").mass_flow_kg_s)
        ctx.state["throughput_kg"] += flow * dt_s
        ctx.state["commit_count"] += 1

    def finalize(self, ctx):
        pass
'''


def python_multiport_module():
    """双通道 Python 模块：一次 evaluate 同时读 4 个端口、写 2 条阻力关系。"""
    return ModuleDefinition(
        id=PYTHON_MULTIPORT_ID,
        name='Python 双通道模块',
        runtime='python',
        entrypoint='module:Module',
        solver_model='python_x',
        source={'runtime': PYTHON_MULTIPORT_SOURCE},
        ports=[PortSpec(id='in0', label='A 入口', direction='in'),
               PortSpec(id='out0', label='A 出口', direction='out'),
               PortSpec(id='in1', label='B 入口', direction='in'),
               PortSpec(id='out1', label='B 出口', direction='out')],
        parameters=[ParameterSpec(id='kv_m3_h', label='流量系数 Kv', default=16.0, minimum=0.001),
                    ParameterSpec(id='opening_ratio', label='阀门开度', default=0.8,
                                  minimum=0.0, maximum=1.0)],
        channels=[ChannelSpec(id='a', name='A 通路', input_port='in0', output_port='out0',
                              relation='resistance', solver_model='python_x'),
                  ChannelSpec(id='b', name='B 通路', input_port='in1', output_port='out1',
                              relation='resistance', solver_model='python_x')],
    )


# ---------------------------------------------------------------- 六类拓扑


def series_project(instances, python_fraction=0.0):
    """原 benchmark_scaling.make_network 的等价实现（串联链 + 可选 Python 阀）。"""
    from fn_engine.packages import load_module_package

    catalog = catalog_map()
    count = max(instances - 2, 0)
    definitions = [catalog['source'], catalog['pipe']]
    module = load_module_package(ROOT / 'modules/programmable_valve')
    if python_fraction:
        definitions.append(module)
    nodes = [ModuleInstance(id='B1', module_id='source', name='in', parameters={'pressure_pa': 250000})]
    for i in range(count):
        custom = i < int(count * python_fraction)
        nodes.append(ModuleInstance(
            id=f'N{i}', module_id=module.id if custom else 'pipe', name=str(i),
            parameters={'opening_ratio': .8, 'kv_m3_h': 16} if custom else {'length_m': 1.}))
    nodes.append(ModuleInstance(id='B2', module_id='source', name='out', parameters={'pressure_pa': 120000}))
    links = []
    for i, (a, b) in enumerate(zip(nodes, nodes[1:])):
        links.append(Connection(
            id=f'e{i}',
            source=Endpoint(instance_id=a.id, port_id='out0'),
            target=Endpoint(instance_id=b.id, port_id='out0' if b.id == 'B2' else 'in0')))
    return Project(id='scale', name=f'{instances} instances', modules=definitions, instances=nodes,
                   connections=links)


def parallel_project(instances):
    if instances < 6:
        raise ValueError('并联样例至少需要 6 个实例（2 边界 + 2 汇合 + 2 管道）')
    count = instances - 4
    first, second = count // 2, count - count // 2
    nodes = [('B1', 'source', {'pressure_pa': 250000}), ('J0', 'junction', {}), ('J1', 'junction', {}),
             ('B2', 'source', {'pressure_pa': 120000})]
    edges = [('B1:out0', 'J0:in0'), ('J1:in0', 'B2:out0')]
    for branch, number in enumerate((first, second)):
        port = 'out' + str(branch)
        previous = f'J0:{port}'
        for i in range(number):
            name = f'L{branch}_{i}'
            nodes.append((name, 'pipe', {'length_m': 1.0 if branch == 0 else 1.3}))
            edges.append((previous, name + ':in0'))
            previous = name + ':out0'
        edges.append((previous, f'J1:{port}'))
    return assemble('scale-parallel', nodes, edges)


def mesh_project(rows, cols):
    """二维多环网格；参数即行列数，内部节点度数为 4，独立环数 = (rows-1)(cols-1)。"""
    if rows < 2 or cols < 2:
        raise ValueError('二维网格至少 2×2，否则会退化成单链')
    nodes = [('B1', 'source', {'pressure_pa': 250000}), ('B2', 'source', {'pressure_pa': 120000})]
    edges = []
    for r in range(rows):
        for c in range(cols):
            nodes.append((f'G{r}_{c}', 'grid_junction', {}))
    for r in range(rows):
        for c in range(cols - 1):
            name = f'H{r}_{c}'
            nodes.append((name, 'pipe', {'length_m': 1}))
            edges.append((f'G{r}_{c}:p1', name + ':in0'))
            edges.append((name + ':out0', f'G{r}_{c + 1}:p0'))
    for r in range(rows - 1):
        for c in range(cols):
            name = f'V{r}_{c}'
            nodes.append((name, 'pipe', {'length_m': 1}))
            edges.append((f'G{r}_{c}:p3', name + ':in0'))
            edges.append((name + ':out0', f'G{r + 1}_{c}:p2'))
    # 两个压力参考放在对角，避免任何一行/列成为孤立长链。
    edges.append(('B1:out0', 'G0_0:p2'))
    edges.append(('B2:out0', f'G{rows - 1}_{cols - 1}:p1'))
    return assemble('scale-mesh', nodes, edges, [grid_junction()])


def components_project(count, length):
    """互不连通的多段链，每段自带高压/低压边界；用于验证连通分量与按块求解。"""
    if count < 1 or length < 1:
        raise ValueError('独立分量样例需要 >=1 个分量且每段 >=1 根管道')
    nodes, edges = [], []
    for k in range(count):
        hi, lo = f'H{k}', f'L{k}'
        nodes.extend([(hi, 'source', {'pressure_pa': 250000}), (lo, 'source', {'pressure_pa': 120000})])
        previous = f'{hi}:out0'
        for i in range(length):
            name = f'P{k}_{i}'
            nodes.append((name, 'pipe', {'length_m': 1}))
            edges.append((previous, name + ':in0'))
            previous = name + ':out0'
        edges.append((previous, f'{lo}:out0'))
    return assemble('scale-components', nodes, edges)


def dual_loop_project(length):
    """热耦合双回路：热侧水、冷侧乙二醇，经一台换热器交换热量。"""
    if length < 1:
        raise ValueError('双回路样例每侧至少 1 根管道')
    nodes = [('BH', 'source', {'pressure_pa': 208486.8, 'temperature_k': 353.15}),
             ('BC', 'source', {'pressure_pa': 208099.8, 'temperature_k': 278.15}),
             ('HX', 'exchanger', {'ua_w_k': 4000.}),
             ('SH', 'source', {'pressure_pa': 201325., 'temperature_k': 323.15}),
             ('SC', 'source', {'pressure_pa': 201325., 'temperature_k': 283.15})]
    edges = []
    for side, inlet, outlet in (('h', 'BH:out0', 'SH:out0'), ('c', 'BC:out0', 'SC:out0')):
        previous = inlet
        for i in range(length):
            name = f'P{side}{i}'
            nodes.append((name, 'pipe', {'length_m': 2}))
            edges.append((previous, name + ':in0'))
            previous = name + ':out0'
        index = 0 if side == 'h' else 1
        edges.append((previous, f'HX:in{index}'))
    edges.append(('HX:out0', 'SH:out0'))
    edges.append(('HX:out1', 'SC:out0'))
    project = assemble('scale-dual-loop', nodes, edges)
    project.circuit_fluids = [CircuitFluid(id='brine', anchor=Endpoint(instance_id='BC', port_id='out0'),
                                           fluid=FluidConfig(fluid=MEG30))]
    return project


def python_multiport_project(count):
    """两套串联管网通过 ``count`` 个双通道 Python 实例耦合。"""
    if count < 1:
        raise ValueError('Python 多端口样例至少 1 个实例')
    nodes = [('SH1', 'source', {'pressure_pa': 250000}), ('SL1', 'source', {'pressure_pa': 120000}),
             ('SH2', 'source', {'pressure_pa': 240000}), ('SL2', 'source', {'pressure_pa': 130000})]
    nodes.extend((f'M{i}', PYTHON_MULTIPORT_ID, {}) for i in range(count))
    edges = []
    for side, source, sink in ((0, 'SH1:out0', 'SL1:out0'), (1, 'SH2:out0', 'SL2:out0')):
        previous = source
        for i in range(count):
            edges.append((previous, f'M{i}:in{side}'))
            previous = f'M{i}:out{side}'
        edges.append((previous, sink))
    return assemble('scale-python-multiport', nodes, edges, [python_multiport_module()])


# ---------------------------------------------------------------- 规模与计数


def build_project(family, tier):
    if tier not in TIERS:
        raise KeyError(f'未知档位：{tier}')
    if family == 'series':
        return series_project(SERIES_INSTANCES[tier])
    if family == 'parallel':
        return parallel_project(PARALLEL_INSTANCES[tier])
    if family == 'mesh':
        return mesh_project(*MESH_GRID[tier])
    if family == 'components':
        return components_project(*COMPONENT_LAYOUT[tier])
    if family == 'thermal-dual-loop':
        return dual_loop_project(DUAL_LOOP_LENGTH[tier])
    if family == 'python-multiport':
        return python_multiport_project(PYTHON_MULTIPORT_COUNT[tier])
    raise KeyError(f'未知拓扑：{family}')


def _graph_shape(network):
    """支路图的节点数、独立分量数与独立环数（E − V + C）。"""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for branch in network.branches:
        union(branch.start_node, branch.end_node)
    components = len({find(node) for node in parent})
    nodes = len(parent)
    cycles = len(network.branches) - nodes + components if nodes else 0
    return {'graph_nodes': nodes, 'graph_components': components, 'independent_loops': cycles}


def describe(network):
    """编译后的真实规模；口径与 §2 一致，不用实例数冒充未知量。

    - ``nodes``/``branches``：编译后的节点数与支路数。
    - ``hydraulic_unknowns``：稳态水力未知量 = 支路流量 + 未定压节点压力。
    - ``hydraulic_unknowns_dynamic``：再加水箱净流入变量（本工厂的静态样例为 0）。
    - ``dependency_edges``：依赖图边数 = 连接边 + 每个多端口实例内部端口两两依赖。
      模块 evaluate 可同时读取其全部端口，分块时必须视为互相依赖。
    """
    project = network.project
    unknown_pressures = len(network.node_keys) - len(network.fixed_pressures)
    dependency_edges = len(project.connections)
    for instance in project.instances:
        definition = network.modules[instance.module_id]
        ports = len(definition.ports)
        dependency_edges += ports * (ports - 1) // 2
    counts = {
        'instances': len(project.instances),
        'connections': len(project.connections),
        'nodes': len(network.node_keys),
        'branches': len(network.branches),
        'fixed_pressure_nodes': len(network.fixed_pressures),
        'unknown_pressures': unknown_pressures,
        'hydraulic_unknowns': len(network.branches) + unknown_pressures,
        'hydraulic_unknowns_dynamic': len(network.branches) + unknown_pressures + len(network.storage),
        'storage_nodes': len(network.storage),
        'dependency_edges': dependency_edges,
        'python_instances': sum(1 for i in project.instances if network.modules[i.module_id].runtime == 'python'),
    }
    counts.update(_graph_shape(network))
    return counts


def measure_project(project):
    return describe(compile_project(project))


def matrix(families=FAMILIES, tiers=TIERS):
    """枚举样例矩阵；返回 ``{'family','tier','project','counts'}``。"""
    rows = []
    for family in families:
        for tier in tiers:
            project = build_project(family, tier)
            rows.append({'family': family, 'tier': tier, 'project': project, 'counts': measure_project(project)})
    return rows


def rows_by_family():
    return {family: [row for row in matrix(families=(family,))] for family in FAMILIES}
