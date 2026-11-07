"""Ideal meters on public accepted-frame values, without adding network equations."""
import math

from .model_types.base import Diagnostic


PORT_UNITS = {
    'pressure_pa': ('pressure', 'Pa'), 'temperature_k': ('temperature', 'K'),
    'enthalpy_j_kg': ('specific_enthalpy', 'J/kg'), 'density_kg_m3': ('density', 'kg/m3'),
    'mass_flow_kg_s': ('mass_flow', 'kg/s'),
}
CHANNEL_UNITS = {
    'mass_flow_kg_s': ('mass_flow', 'kg/s'), 'pressure_drop_pa': ('pressure', 'Pa'),
    'heat_w': ('power', 'W'), 'inlet_temperature_k': ('temperature', 'K'),
    'outlet_temperature_k': ('temperature', 'K'),
}


def _unit_name(name):
    return name.replace('³', '3')


def source_unit(key, modules, instances):
    instance_id, _, suffix = key.partition('.')
    instance = instances.get(instance_id)
    if instance is None:
        raise ValueError('引用了未知设备：' + key)
    definition = modules[instance.module_id]
    variable = next((v for v in definition.variables if v.id == suffix), None)
    if variable:
        if not variable.sampleable or variable.source == 'parameter' or variable.unit is None:
            raise ValueError('测点必须引用有单位的可采样数值：' + key)
        return variable.unit.quantity, _unit_name(variable.unit.canonical_unit)
    prefix, _, field = suffix.partition('.')
    if prefix in {p.id for p in definition.ports} and field in PORT_UNITS:
        return PORT_UNITS[field]
    if prefix in {c.id for c in definition.channels if c.enabled} and field in CHANNEL_UNITS:
        return CHANNEL_UNITS[field]
    raise ValueError('引用了未知变量：' + key)


def validate_measurements(project):
    """Validate before composition expansion, against the public equipment contract."""
    from .compiler import CompilationError
    modules = {m.id: m for m in project.modules}
    instances = {i.id: i for i in project.instances}
    identifiers = [meter.id for meter in project.measurements]
    if identifiers and (project.thermal_couplings or any(
            p.domain.value != 'fluid' for i in project.instances for p in modules[i.module_id].ports)):
        raise CompilationError('MEASUREMENT_DOMAIN_UNSUPPORTED',
            '理想测点目前支持单相水力及风水联算项目', field='measurements')
    try:
        if len(set(identifiers)) != len(identifiers) or (identifiers and 'measurement' in instances):
            raise ValueError('测点标识重复或设备占用了 measurement 命名空间')
        for meter in project.measurements:
            aliases = getattr(project, '_composite_maps', {}).get('variables', {})
            units = [source_unit(aliases.get(key, key), modules, instances) for key in meter.sources]
            if meter.kind == 'value':
                expected = units[0]
            elif meter.kind == 'difference':
                if units[0] != units[1]:
                    raise ValueError('两点差值的输入单位必须一致')
                expected = units[0]
            elif meter.kind == 'volume_flow':
                if units != [('mass_flow', 'kg/s'), ('density', 'kg/m3')]:
                    raise ValueError('体积流量须按质量流量 ÷ 密度绑定')
                expected = ('volume_flow', 'm3/s')
            else:
                if units != [('mass_flow', 'kg/s'), ('specific_enthalpy', 'J/kg'), ('specific_enthalpy', 'J/kg')]:
                    raise ValueError('热功率须按质量流量 × 两点比焓差绑定')
                expected = ('power', 'W')
            if (meter.unit.quantity, _unit_name(meter.unit.canonical_unit)) != expected:
                raise ValueError('测点 ' + meter.id + ' 的结果单位与计算类型不一致')
            if meter.kind != 'value' and meter.unit.display_offset != 0:
                raise ValueError('计算测点的显示单位不能带偏移')
    except ValueError as error:
        raise CompilationError('MEASUREMENT_INVALID', str(error), field='measurements') from error


def apply_measurements(project, frame):
    if not project.measurements: return frame
    frame.diagnostics=[d for d in frame.diagnostics if d.code!='MEASUREMENT_UNAVAILABLE']
    for meter in project.measurements:
        values=[frame.variables.get(key) for key in meter.sources]
        reading=None
        if all(isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value) for value in values):
            if meter.kind=='value': reading=values[0]
            elif meter.kind=='difference': reading=values[0]-values[1]
            elif meter.kind=='volume_flow' and values[1]>0: reading=values[0]/values[1]
            elif meter.kind=='thermal_power': reading=values[0]*(values[1]-values[2])
        if reading is not None and not math.isfinite(reading): reading=None
        key='measurement.'+meter.id
        frame.variables[key]=reading
        if reading is None:
            frame.diagnostics.append(Diagnostic(code='MEASUREMENT_UNAVAILABLE',severity='warning',
                message=meter.label+' 缺少有效输入，不以零值代替',field=key))
    return frame
