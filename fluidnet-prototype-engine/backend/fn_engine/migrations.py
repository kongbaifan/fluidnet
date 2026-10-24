"""Declarative all-or-nothing module migrations; never rewrite arbitrary Python strings."""
from copy import deepcopy
import math

from .models import ModuleMigration, Project, ControlScript
from .packages import package_ref

UNITS = {
    'm': ('length', 1., 0.), 'mm': ('length', .001, 0.), 'cm': ('length', .01, 0.),
    'Pa': ('pressure', 1., 0.), 'kPa': ('pressure', 1000., 0.), 'MPa': ('pressure', 1e6, 0.), 'bar': ('pressure', 1e5, 0.),
    'K': ('temperature', 1., 0.), 'degC': ('temperature', 1., 273.15), '°C': ('temperature', 1., 273.15),
    '1': ('ratio', 1., 0.), '%': ('ratio', .01, 0.),
    'kg/s': ('mass_flow', 1., 0.), 'kg/h': ('mass_flow', 1/3600., 0.),
    'W': ('power', 1., 0.), 'kW': ('power', 1000., 0.),
}


def _table(before, after, explicit, label):
    old, new = {item.id:item for item in before}, {item.id:item for item in after}
    if set(explicit) - old.keys():
        raise ValueError(f'{label} 映射包含不存在的源标识')
    mapping = {name:explicit.get(name, name if name in new else None) for name in old}
    missing = [name for name in old if mapping[name] is None and name not in explicit]
    if missing:
        raise ValueError(f'{label} 被删除，需显式映射或删除声明：{missing}')
    targets = [value for value in mapping.values() if value is not None]
    if set(targets) - new.keys() or len(targets) != len(set(targets)):
        raise ValueError(f'{label} 映射目标不存在或出现多对一冲突')
    return old, new, mapping


def migrate_project(project, target, migration):
    migration = ModuleMigration.model_validate(migration) if isinstance(migration, dict) else migration
    old = next(module for module in project.modules if module.id == target.id)
    old_params, new_params, parameters = _table(old.parameters, target.parameters, migration.parameters, '参数')
    old_ports, new_ports, ports = _table(old.ports, target.ports, migration.ports, '端口')
    _, _, channels = _table(old.channels, target.channels, migration.channels, '通路')
    if set(migration.defaults) - new_params.keys() or set(migration.unit_conversions) - old_params.keys():
        raise ValueError('默认值或单位转换引用未知参数')
    for source, destination in ports.items():
        if destination is None:
            continue
        if any(getattr(old_ports[source], field) != getattr(new_ports[destination], field) for field in ['domain','direction','circuit']):
            raise ValueError(f'端口 {source} 的领域、方向或回路变化不能通过改名迁移')
    for source, destination in parameters.items():
        if destination is None:
            continue
        before, after = old_params[source], new_params[destination]
        if before.value_type != after.value_type:
            raise ValueError(f'参数 {source} 类型变化需要人工处理')
        if before.unit and after.unit and before.unit.quantity != after.unit.quantity:
            raise ValueError(f'参数 {source} 物理量变化不能用单位系数迁移')
        units = (before.unit.canonical_unit if before.unit else None, after.unit.canonical_unit if after.unit else None)
        if units[0] != units[1] or source in migration.unit_conversions:
            conversion = migration.unit_conversions.get(source)
            if conversion is None or (conversion.from_unit, conversion.to_unit) != units or any(unit not in UNITS for unit in units):
                raise ValueError(f'参数 {source} 规范单位改变，需标准单位转换')
            a, b = UNITS[units[0]], UNITS[units[1]]
            expected_scale, expected_offset = a[1]/b[1], (a[2]-b[2])/b[1]
            if a[0] != b[0] or not math.isclose(conversion.scale, expected_scale) or not math.isclose(conversion.offset, expected_offset, abs_tol=1e-12):
                raise ValueError(f'参数 {source} 单位转换不符合标准单位定义；不支持表压与绝压转换')

    def values(items, defaults=False):
        result = ({name:deepcopy(spec.default) for name,spec in new_params.items()} | deepcopy(migration.defaults)) if defaults else {}
        for name, value in items.items():
            if name not in parameters:
                raise ValueError(f'参数库引用了未知源参数 {name}')
            destination = parameters[name]
            if destination is not None:
                conversion = migration.unit_conversions.get(name)
                result[destination] = value*conversion.scale+conversion.offset if conversion else deepcopy(value)
        return result

    candidate, references = project.model_copy(deep=True), []
    affected = {instance.id for instance in project.instances if instance.module_id == target.id}
    def suffixes(module):
        port_fields = ['pressure_pa','temperature_k','enthalpy_j_kg','mass_flow_kg_s','density_kg_m3','viscosity_pa_s','quality']
        branch_fields = ['mass_flow_kg_s','pressure_drop_pa','heat_w','inlet_temperature_k','outlet_temperature_k']
        return {v.id for v in module.variables} | {'param.'+p.id for p in module.parameters} | set(branch_fields) | {
            p.id+'.'+field for p in module.ports for field in port_fields} | {
            c.id+'.'+field for c in module.channels for field in branch_fields}
    old_suffixes, new_suffixes = suffixes(old), suffixes(target)
    if set(migration.variables) - old_suffixes or {name for name in migration.variables.values() if name is not None} - new_suffixes:
        raise ValueError('变量映射源或目标不存在')
    destinations=[name for name in migration.variables.values() if name is not None]
    if len(destinations)!=len(set(destinations)):
        raise ValueError('变量映射存在多对一冲突')

    def variable(key):
        instance, separator, suffix = key.partition('.')
        if not separator or instance not in affected:
            return key
        mapped = migration.variables.get(suffix, suffix)
        if mapped is None:
            raise ValueError(f'引用 {key} 的变量被删除，需要人工处理')
        if suffix not in migration.variables:
            if suffix.startswith('param.'):
                name = suffix[6:]
                mapped_name = parameters.get(name, name)
                if mapped_name is None:
                    raise ValueError(f'控制引用 {key} 的参数被删除')
                mapped = 'param.'+mapped_name
            else:
                prefix, dot, rest = suffix.partition('.')
                mapped_prefix = ports.get(prefix, channels.get(prefix, prefix))
                if mapped_prefix is None:
                    raise ValueError(f'引用 {key} 的端口或通路被删除')
                mapped = mapped_prefix+dot+rest
        result = instance+'.'+mapped
        if mapped not in new_suffixes:
            raise ValueError(f'引用 {key} 在目标模块中不存在，需要显式变量映射')
        if result != key:
            references.append(f'{key} → {result}')
        return result

    for instance in candidate.instances:
        if instance.id in affected:
            instance.parameters, instance.draft_parameters = values(instance.parameters, True), values(instance.draft_parameters, True)
            for bank in instance.banks:
                bank.values = values(bank.values, True)
            instance.package = package_ref(target)
    for connection in candidate.connections:
        for endpoint in [connection.source, connection.target]:
            if endpoint.instance_id in affected:
                destination = ports[endpoint.port_id]
                if destination is None:
                    raise ValueError(f'连接 {connection.id} 引用已删除端口')
                endpoint.port_id = destination
    for circuit in candidate.circuit_fluids:
        if circuit.anchor.instance_id in affected:
            destination = ports[circuit.anchor.port_id]
            if destination is None:
                raise ValueError('工质回路锚点引用已删除端口')
            circuit.anchor.port_id = destination
    for scenario in candidate.scenarios:
        for instance in affected & scenario.overrides.keys():
            scenario.overrides[instance] = values(scenario.overrides[instance])
    candidate.selected_variables = [variable(key) for key in candidate.selected_variables]
    for controller in candidate.controllers:
        controller.measurement = variable(controller.measurement)
        if controller.instance_id in affected:
            source_parameter=controller.parameter_id
            destination = parameters[source_parameter]
            if destination is None:
                raise ValueError(f'PID {controller.id} 的目标参数被删除')
            controller.parameter_id = destination
            conversion=migration.unit_conversions.get(source_parameter)
            if conversion:
                controller.minimum=controller.minimum*conversion.scale+conversion.offset
                controller.maximum=controller.maximum*conversion.scale+conversion.offset
                if controller.manual_output is not None:
                    controller.manual_output=controller.manual_output*conversion.scale+conversion.offset
                controller.kp*=conversion.scale;controller.ki*=conversion.scale;controller.kd*=conversion.scale
    for script in candidate.control_scripts:
        before = script.inputs + script.outputs
        script.inputs, script.outputs = [variable(key) for key in script.inputs], [variable(key) for key in script.outputs]
        source = migration.script_sources.get(script.id, script.source)
        stale = [key for key,mapped in zip(before,script.inputs+script.outputs,strict=True) if key != mapped and key in source]
        if stale:
            raise ValueError(f'脚本 {script.id} 源码仍引用旧标识 {stale}，需手动修改；源码未自动替换')
        script.source, script.content_hash = source, None
        restored = ControlScript.model_validate(script.model_dump())
        script.content_hash = restored.content_hash
    candidate.modules = [target.model_copy(deep=True) if module.id == target.id else module for module in candidate.modules]
    return Project.model_validate(candidate.model_dump()), sorted(set(references))
