"""Compile the bounded room/cold-source heat topology without fluid pressure nodes."""
from dataclasses import dataclass, field

from ..catalog import thermal_catalog
from ..compiler import CompilationError, validated_parameters, validate_controllers
from ..control import validate_scripts
from ..models import Domain, Project


@dataclass
class CompiledThermal:
    project: Project
    modules: dict
    instances: dict
    parameters: dict
    room_sources: dict[str, str]
    diagnostics: list = field(default_factory=list)
    branches: list = field(default_factory=list)
    storage: dict = field(default_factory=dict)
    execution_domain: str = 'thermal'


def compile_thermal_project(project):
    modules = {m.id: m for m in project.modules}
    instances = {i.id: i for i in project.instances}
    if not instances:
        raise CompilationError('EMPTY_NETWORK', '项目没有设备')
    if not project.solver.thermal:
        raise CompilationError('THERMAL_REQUIRED', '库房热系统需要启用热力计算')
    if project.circuit_fluids:
        raise CompilationError('THERMAL_TOPOLOGY_UNSUPPORTED', 'A1 热系统不使用流体回路配置')
    registered = {m.solver_model: m for m in thermal_catalog()}
    parameters, ports = {}, {}
    for instance in project.instances:
        definition = modules[instance.module_id]
        reference = registered.get(definition.solver_model)
        if reference is None or definition.runtime != 'builtin':
            raise CompilationError('THERMAL_MODEL_UNSUPPORTED', 'A1 热系统只支持库房热节点与理想冷源', instance.id)
        if definition.state_model != reference.state_model or definition.channels:
            raise CompilationError('THERMAL_TOPOLOGY_UNSUPPORTED', '热节点状态类型或内部通路不匹配', instance.id)
        if len(definition.ports) != 1 or definition.ports[0].model_dump() != reference.ports[0].model_dump():
            raise CompilationError('THERMAL_PORT_INVALID', '热接口须保持注册的类型、方向与必连接要求', instance.id)
        # Built-in equations own parameter units/type/runtime flags. Defaults remain project-owned.
        actual = {p.id: p for p in definition.parameters}
        if actual.keys() != {p.id for p in reference.parameters} or any(
                actual[p.id].value_type != p.value_type or actual[p.id].unit != p.unit
                or actual[p.id].runtime != p.runtime or actual[p.id].writable != p.writable
                or actual[p.id].minimum != p.minimum or actual[p.id].maximum != p.maximum
                for p in reference.parameters):
            raise CompilationError('THERMAL_PARAMETER_CONTRACT', '热模型参数类型、单位或可写范围与注册合同不一致', instance.id)
        parameters[instance.id] = validated_parameters(instance, definition)
        ports[(instance.id, 'heat')] = definition.ports[0]
    connected, room_sources, edge_ids = set(), {}, set()
    for edge in project.connections:
        a = (edge.source.instance_id, edge.source.port_id)
        b = (edge.target.instance_id, edge.target.port_id)
        if edge.id in edge_ids or a not in ports or b not in ports or a == b:
            raise CompilationError('THERMAL_CONNECTION_INVALID', f'连接 {edge.id} 无效或重复')
        edge_ids.add(edge.id)
        if a in connected or b in connected:
            raise CompilationError('THERMAL_CONNECTION_INVALID', 'A1 每个热端口只能连接一个设备')
        if ports[a].domain != Domain.thermal or ports[a].direction == ports[b].direction:
            raise CompilationError('THERMAL_CONNECTION_INVALID', '热连接需要冷源输出连接库房输入')
        room, source = (a[0], b[0]) if modules[instances[a[0]].module_id].solver_model == 'cold_room' else (b[0], a[0])
        room_sources[room] = source
        connected.update((a, b))
    if connected != ports.keys():
        missing = sorted(f'{i}:{p}' for i, p in ports.keys() - connected)
        raise CompilationError('THERMAL_CONNECTION_MISSING', f'热端口未连接：{missing}')
    validate_controllers(project, modules, instances)
    validate_scripts(project, modules, instances)
    return CompiledThermal(project.model_copy(deep=True), modules, instances, parameters, room_sources,
                           diagnostics=list(project.import_diagnostics))
