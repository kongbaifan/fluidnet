from __future__ import annotations

import math
from dataclasses import dataclass, field

from .catalog import builtin_catalog
from .models import Diagnostic, Domain, ModuleDefinition, ModuleInstance, Project


class CompilationError(ValueError):
    def __init__(self, code, message, instance_id=None, field=None):
        self.diagnostic = Diagnostic(code=code, message=message, instance_id=instance_id, field=field)
        super().__init__(message)


class DisjointSet:
    def __init__(self, values):
        self.parent = {value: value for value in values}

    def find(self, value):
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while value != root:
            value, self.parent[value] = self.parent[value], root
        return root

    def union(self, left, right):
        self.parent[self.find(right)] = self.find(left)


@dataclass
class CompiledBranch:
    instance_id: str
    channel_id: str
    solver_model: str
    input_port: str
    output_port: str
    start_node: int
    end_node: int
    closed: bool = False


@dataclass
class CompiledNetwork:
    project: Project
    modules: dict[str, ModuleDefinition]
    instances: dict[str, ModuleInstance]
    parameters: dict[str, dict]
    port_nodes: dict[str, int]
    node_keys: list[str]
    branches: list[CompiledBranch]
    fixed_pressures: dict[int, float]
    diagnostics: list[Diagnostic]
    # Boundary temperature per fixed-pressure node and the static hydraulic component of every node.
    fixed_temperatures: dict[int, float] = field(default_factory=dict)
    node_component: list[int] = field(default_factory=list)


def validated_parameters(instance, definition):
    # Registered model constraints remain authoritative for safety limits, while
    # the project definition owns defaults. This keeps custom package defaults
    # from being silently replaced by a same-shaped built-in model.
    registered = next((m for m in builtin_catalog() if m.solver_model == definition.solver_model), None) if definition.runtime == 'builtin' else None
    specs = {p.id: p for p in definition.parameters}
    if registered:
        for registered_spec in registered.parameters:
            current = specs.get(registered_spec.id)
            if current is None:
                specs[registered_spec.id] = registered_spec
            else:
                updates = {}
                if registered_spec.minimum is not None:
                    updates['minimum'] = max(current.minimum, registered_spec.minimum) if current.minimum is not None else registered_spec.minimum
                if registered_spec.maximum is not None:
                    updates['maximum'] = min(current.maximum, registered_spec.maximum) if current.maximum is not None else registered_spec.maximum
                if updates:
                    specs[registered_spec.id] = current.model_copy(update=updates)
    unknown = instance.parameters.keys() - specs.keys()
    if unknown:
        raise CompilationError('UNKNOWN_PARAMETER', f'{instance.id} 未定义参数：{sorted(unknown)}', instance.id)
    values = {p.id: p.default for p in specs.values()} | instance.parameters
    for key, spec in specs.items():
        value = values[key]
        if spec.value_type == 'number':
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise CompilationError('PARAMETER_INVALID', f'{instance.id}.{key} 必须是有限数值', instance.id, key)
            if spec.minimum is not None and value < spec.minimum or spec.maximum is not None and value > spec.maximum:
                raise CompilationError('PARAMETER_RANGE', f'{instance.id}.{key} 超出范围 [{spec.minimum}, {spec.maximum}]', instance.id, key)
        elif spec.value_type == 'boolean' and not isinstance(value, bool):
            raise CompilationError('PARAMETER_INVALID', f'{instance.id}.{key} 必须是布尔值', instance.id, key)
        elif spec.value_type == 'text' and not isinstance(value, str):
            raise CompilationError('PARAMETER_INVALID', f'{instance.id}.{key} 必须是文本', instance.id, key)
        if key == 'head_curve':
            valid = isinstance(value, list) and len(value) >= 2
            valid = valid and all(isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0 for x in p) for p in value)
            valid = valid and value[0][0] == 0 and value[-1][1] == 0
            valid = valid and all(b[0] > a[0] and b[1] < a[1] for a, b in zip(value, value[1:]))
            if not valid:
                raise CompilationError('CURVE_INVALID', f'{instance.id} 扬程曲线需从零流量开始，流量递增、扬程严格递减且末点扬程为零', instance.id, key)
    # 相对粗糙度的分母必须严格为正: 未声明最小值的自定义模块可能传入 0 或负值,
    # 若不拦截会让 ZeroDivisionError 逃出所有处理器并变成 HTTP 500。
    if 'roughness_m' in values and 'diameter_m' in values:
        diameter, roughness = values['diameter_m'], values['roughness_m']
        if isinstance(diameter, bool) or not isinstance(diameter, (int, float)) or not math.isfinite(diameter) or diameter <= 0:
            raise CompilationError('PARAMETER_RANGE', f'{instance.id}.diameter_m 必须大于零', instance.id, 'diameter_m')
        if isinstance(roughness, bool) or not isinstance(roughness, (int, float)) or not math.isfinite(roughness) or roughness < 0:
            raise CompilationError('PARAMETER_RANGE', f'{instance.id}.roughness_m 不能小于零', instance.id, 'roughness_m')
        if roughness / diameter > .05:
            raise CompilationError('ROUGHNESS_RANGE', '相对粗糙度必须不大于 0.05', instance.id, 'roughness_m')
    return values


def compile_project(project: Project) -> CompiledNetwork:
    modules = {m.id: m for m in project.modules}
    instances = {i.id: i for i in project.instances}
    if not instances:
        raise CompilationError('EMPTY_NETWORK', '项目没有设备')
    diagnostics = list(project.import_diagnostics)
    parameters, port_keys = {}, []
    supported = {'pressure_source', 'junction', 'valve', 'pipe', 'pump_curve', 'heat_exchanger'}
    for inst in project.instances:
        definition = modules[inst.module_id]
        if definition.runtime != 'python' and (definition.solver_model not in supported or definition.state_model):
            raise CompilationError('MODEL_NOT_SUPPORTED', f'{inst.id} 的模型 {definition.state_model or definition.solver_model} 尚未实现；不能生成替代计算结果', inst.id)
        if definition.runtime == 'python':
            if not definition.entrypoint:
                raise CompilationError('MODULE_ENTRYPOINT_MISSING', f'{inst.id} 的 Python 模块没有入口', inst.id)
            source = definition.source.get('runtime', '') if definition.source else ''
            if isinstance(source, list):
                source = '\n'.join(source)
            if not source.strip():
                raise CompilationError('MODULE_SOURCE_MISSING', f'{inst.id} 的 Python 模块没有 runtime 源码', inst.id)
            if definition.content_hash:
                import hashlib
                digest = hashlib.sha256(source.encode('utf-8')).hexdigest()
                if digest != definition.content_hash:
                    raise CompilationError('MODULE_HASH_MISMATCH', f'{inst.id} 的模块内容哈希与源码不一致', inst.id)
            if definition.definition_hash:
                from .runtime import module_definition_hash
                if module_definition_hash(definition) != definition.definition_hash:
                    raise CompilationError('MODULE_DEFINITION_HASH_MISMATCH', f'{inst.id} 的模块契约或源码与保存版本不一致', inst.id)
        parameters[inst.id] = validated_parameters(inst, definition)
        if not definition.ports:
            raise CompilationError('PORTS_MISSING', f'{inst.id} 没有端口', inst.id)
        if definition.solver_model == 'pressure_source' and len(definition.ports) != 1:
            raise CompilationError('BOUNDARY_PORT_COUNT', '压力边界必须只有一个端口', inst.id)
        if definition.thermal_model and not project.solver.thermal:
            diagnostics.append(Diagnostic(code='THERMAL_NOT_SOLVED', message=f'{inst.id} 仅计算两侧水力阻力，不计算热量交换和出口温度', severity='warning', instance_id=inst.id))
        for port in definition.ports:
            if port.domain != Domain.fluid:
                raise CompilationError('DOMAIN_NOT_SOLVABLE', f'{inst.id}:{port.id} 不是流体端口', inst.id, port.id)
            port_keys.append(f'{inst.id}:{port.id}')
    dsu = DisjointSet(port_keys)
    used = set()
    for connection in project.connections:
        source = f'{connection.source.instance_id}:{connection.source.port_id}'
        target = f'{connection.target.instance_id}:{connection.target.port_id}'
        if source == target or source in used or target in used:
            raise CompilationError('PORT_REUSED', f'连接端口重复使用：{source} 或 {target}')
        used.update((source, target))
        dsu.union(source, target)
    for inst in project.instances:
        definition = modules[inst.module_id]
        if definition.solver_model == 'junction':
            for p in definition.ports[1:]:
                dsu.union(f'{inst.id}:{definition.ports[0].id}', f'{inst.id}:{p.id}')
        for port in definition.ports:
            if port.required and f'{inst.id}:{port.id}' not in used:
                raise CompilationError('PORT_UNCONNECTED', f'必需端口未连接：{inst.id} · {port.label}', inst.id, port.id)
    roots = sorted({dsu.find(key) for key in port_keys})
    index = {root: n for n, root in enumerate(roots)}
    nodes = {key: index[dsu.find(key)] for key in port_keys}
    branches, fixed, fixed_temperatures = [], {}, {}
    for inst in project.instances:
        definition, params = modules[inst.module_id], parameters[inst.id]
        if definition.solver_model == 'pressure_source':
            node, value = nodes[f'{inst.id}:{definition.ports[0].id}'], params['pressure_pa']
            if node in fixed and not math.isclose(fixed[node], value, rel_tol=0, abs_tol=1e-6):
                raise CompilationError('BOUNDARY_CONFLICT', f'{inst.id} 与同节点压力边界冲突', inst.id)
            temperature = float(params.get('temperature_k', 293.15))
            if (project.solver.thermal and node in fixed_temperatures
                    and not math.isclose(fixed_temperatures[node], temperature, rel_tol=0, abs_tol=1e-9)):
                raise CompilationError('BOUNDARY_TEMPERATURE_CONFLICT', f'{inst.id} 与同节点压力边界的温度不同', inst.id,
                                       'temperature_k')
            fixed[node] = value
            fixed_temperatures.setdefault(node, temperature)
            continue
        if definition.solver_model == 'junction':
            continue
        channels = [c for c in definition.channels if c.enabled]
        covered = {p for c in channels for p in (c.input_port, c.output_port)}
        if covered != {p.id for p in definition.ports}:
            raise CompilationError('CHANNEL_COVERAGE', f'{inst.id} 存在未绑定到有效通路的端口', inst.id)
        for ch in channels:
            expected = 'resistance' if definition.solver_model == 'heat_exchanger' else definition.solver_model
            relation = 'pump_curve' if expected == 'pump_curve' else 'resistance'
            if definition.runtime != 'python' and (ch.solver_model != expected or ch.relation != relation):
                raise CompilationError('CHANNEL_MODEL_INVALID', f'{inst.id}.{ch.id} 未注册的通路关系 {ch.solver_model}/{ch.relation}', inst.id, ch.id)
            start, end = nodes[f'{inst.id}:{ch.input_port}'], nodes[f'{inst.id}:{ch.output_port}']
            if start == end:
                raise CompilationError('BRANCH_SHORTED', f'{inst.id}.{ch.id} 的两端被直接短接', inst.id)
            branches.append(CompiledBranch(inst.id, ch.id, ch.solver_model, ch.input_port, ch.output_port, start, end,
                                            definition.runtime == 'builtin' and ch.solver_model == 'valve' and params['opening_ratio'] == 0))
    if not branches:
        raise CompilationError('NO_BRANCHES', '网络没有可计算支路')
    components = DisjointSet(range(len(roots)))
    for branch in branches:
        if not branch.closed:
            components.union(branch.start_node, branch.end_node)
    referenced = {components.find(n) for n in fixed}
    for node in range(len(roots)):
        if components.find(node) not in referenced:
            raise CompilationError('PRESSURE_REFERENCE_MISSING', f'子网络 {roots[node]} 缺少压力边界（关闭阀门也可能隔离回路）')
    return CompiledNetwork(project, modules, instances, parameters, nodes, roots, branches, fixed, diagnostics,
                           fixed_temperatures, [components.find(n) for n in range(len(roots))])


def validate_scenarios(project: Project, modules: dict[str, ModuleDefinition]) -> list[Diagnostic]:
    # 复用运行链路的同一套参数校验(validated_parameters): 运行时会先
    # apply_scenario 把工况覆盖合并进实例参数,再走 compile_project。校验端
    # 若只跑 compile_project,工况里写错的实例 id 或越界数值就会被静默放过。
    diagnostics: list[Diagnostic] = []
    instances = {i.id: i for i in project.instances}
    for scenario in project.scenarios:
        for instance_id, overrides in scenario.overrides.items():
            instance = instances.get(instance_id)
            if instance is None:
                diagnostics.append(Diagnostic(code='SCENARIO_INSTANCE_MISSING', severity='error',
                                               message=f'工况 {scenario.id} 引用不存在的实例:{instance_id}',
                                               instance_id=instance_id))
                continue
            definition = modules.get(instance.module_id)
            if definition is None:
                continue
            merged = instance.model_copy(update={'parameters': {**instance.parameters, **overrides}})
            try:
                validated_parameters(merged, definition)
            except CompilationError as error:
                error.diagnostic.message = f'工况 {scenario.id}:{error.diagnostic.message}'
                diagnostics.append(error.diagnostic)
    return diagnostics


def validate_project(project: Project) -> list[Diagnostic]:
    try:
        network = compile_project(project)
    except CompilationError as error:
        return [error.diagnostic]
    except ValueError as error:
        return [Diagnostic(code='PROJECT_INVALID', message=str(error))]
    return network.diagnostics + validate_scenarios(project, network.modules)
