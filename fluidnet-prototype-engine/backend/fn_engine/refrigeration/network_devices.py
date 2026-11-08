"""Explicit graph-network devices; legacy saturated/serial definitions are unchanged."""
from ..catalog import _celsius, _ratio, _stream, _switch, _var, number
from ..catalog_definitions import fluid_definitions, refrigeration_catalog as legacy_definitions
from ..model_types.module import ModuleDefinition
from .._module_schema_v1 import Direction, ParameterSpec, VariableSpec

NETWORK_KINDS = frozenset({'refrigerant_network_pipe', 'refrigerant_curve_pump',
                           'network_air_cooler', 'refrigerant_network_valve', 'frost_hotgas_cooler', 'compressor_oil_system'})


def definitions():
    base = {m.id: m for m in legacy_definitions()}
    reference_curve = next(p for m in fluid_definitions() if m.id == 'pump'
                           for p in m.parameters if p.id == 'head_curve').model_copy(deep=True)
    reference_curve.default = [[0., 15.], [5., 12.], [10., 7.], [15., 0.]]
    state = [_var('mass_flow_kg_s', '实际质量流量', 'mass_flow', 'kg/s'),
             _var('inlet_pressure_pa', '实际入口压力', 'pressure', 'Pa', 'kPa', 1000.),
             _var('outlet_pressure_pa', '实际出口压力', 'pressure', 'Pa', 'kPa', 1000.),
             _var('inlet_enthalpy_j_kg', '实际入口比焓', 'specific_enthalpy', 'J/kg', 'kJ/kg', 1000.),
             _var('outlet_enthalpy_j_kg', '实际出口比焓', 'specific_enthalpy', 'J/kg', 'kJ/kg', 1000.),
             _var('outlet_quality', '出口干度', 'ratio', '1'),
             _var('pressure_drop_pa', '总压降', 'pressure', 'Pa', 'kPa', 1000.),
             _var('heat_w', '向制冷剂传热', 'power', 'W', 'kW', 1000.)]
    pipe = ModuleDefinition(id='refrigerant_network_pipe', name='制冷剂图式管路（含两相）',
        category='制冷管网与过程', solver_model='refrigerant_network_pipe',
        description='图式压力/质量/焓联立；均相平衡两相Darcy阻力、加速压降与有限UA。无滑移；持液由独立库存单元表达。',
        ports=[_stream('in0', '入口', Direction.in_), _stream('out0', '出口', Direction.out)],
        parameters=[number('length_m', '长度', 5., 'length', 'm', minimum=0.),
                    number('diameter_m', '内径', .04, 'length', 'm', 'mm', .001, minimum=.001),
                    number('roughness_m', '粗糙度', 1e-5, 'length', 'm', 'mm', .001, minimum=0.),
                    number('loss_coefficient', '局部阻力系数', 0., 'ratio', '1', minimum=0.),
                    number('heat_loss_ua_w_k', '环境换热UA', 0., 'conductance', 'W/K', minimum=0.),
                    _celsius('ambient_temperature_k', '环境温度', 293.15),
                    ParameterSpec(id='coefficient_source', label='阻力系数来源', value_type='text',
                                  default='自定义参考几何；HEM/Darcy模型，非厂家标定')], variables=state)
    pump = ModuleDefinition(id='refrigerant_curve_pump', name='制冷剂液泵（曲线工作点）',
        category='制冷管网与过程', solver_model='refrigerant_curve_pump',
        description='泵曲线与整个供回液网络联立求实际流量；相似律、效率及停泵被动阻力；所有电功进入屏蔽泵流体。',
        ports=[_stream('in0', '吸液', Direction.in_), _stream('out0', '排液', Direction.out)],
        parameters=[_switch(), _ratio('speed_ratio', '转速比', 1., runtime=True, maximum=2.),
            reference_curve,
            _ratio('efficiency_ratio', '泵总效率', .55, minimum=.01),
            number('stopped_loss_coefficient', '停泵通流阻力K', 5., 'ratio', '1', minimum=0.),
            number('diameter_m', '通流内径', .04, 'length', 'm', 'mm', .001, minimum=.001),
            ParameterSpec(id='performance_source', label='性能来源', value_type='text', default='自定义参考曲线')],
        variables=state + [_var('electric_power_w', '液泵电功', 'power', 'W'),
                           _var('pressure_rise_pa', '实际压升', 'pressure', 'Pa'),
                           _var('state.electric_energy_j', '累计电能', 'energy', 'J', 'kWh', 3600000., source='state')])
    cooler = base['air_cooler'].model_copy(deep=True, update={
        'id': 'network_air_cooler', 'name': '冷风机（图式供回液）', 'solver_model': 'network_air_cooler',
        'category': '制冷管网与过程',
        'description': '供液/湿回气管网共同求实际流量；有限UA、两相出口与风机热量；不按开度比例强制分流。'})
    cooler.parameters += [number('diameter_m', '冷媒通流内径', .025, 'length', 'm', 'mm', .001, minimum=.001),
                          number('loss_coefficient', '冷媒局部阻力K', 10., 'ratio', '1', minimum=0.)]
    known = {v.id for v in cooler.variables}
    cooler.variables += [v for v in state if v.id not in known]
    valve = base['enthalpy_valve'].model_copy(deep=True, update={
        'id': 'refrigerant_network_valve', 'name': '制冷管网关断调节阀', 'solver_model': 'refrigerant_network_valve',
        'category': '制冷管网与过程',
        'description': '实际单相/两相入口的均相Kv参考关系，等焓；0开度精确关断。两相阀流量不是临界流/厂家认证关联式。'})
    valve.variables = state
    volume = base['hp_receiver'].model_copy(deep=True, update={
        'id': 'refrigerant_inventory_cell', 'name': '制冷剂持液库存单元',
        'state_model': 'refrigerant_control_volume', 'category': '制冷管网与过程',
        'description': '定容有限体积M/U库存，DU物性反求压力/温度；bulk为真实混合物焓，允许单相/两相转换，和管网同一隐式步联立。'})
    for p in volume.parameters:
        if p.id == 'volume_m3': p.default = .002
        if p.id == 'height_m': p.default = .1
        if p.id == 'temperature_k': p.default = 248.15
        if p.id == 'level_ratio': p.default = .8
        if p.id == 'min_level_ratio': p.default = 0.
        if p.id == 'max_level_ratio': p.default = 1.
    volume.parameters += [number('allow_single_phase', '全相态库存（固定开启）', 1., 'ratio', '1', minimum=1., maximum=1.),
                          number('heat_loss_ua_w_k', '库存向环境换热UA', 0., 'conductance', 'W/K', minimum=0.),
                          _celsius('ambient_temperature_k', '库存环境温度', 293.15)]
    volume.ports = [_stream('in0', '混合物流入', Direction.in_), _stream('bulk', '混合物流出', Direction.out)]
    volume.variables += [_var('bulk_enthalpy_j_kg', '库存混合物比焓', 'specific_enthalpy', 'J/kg')]
    result = [pipe, pump, cooler, valve, volume]
    for definition in result:
        expose_parameters(definition)
    return result


def expose_parameters(definition):
    """Keep runtime parameter observations in the public device contract."""
    known = {v.id for v in definition.variables}
    definition.variables.extend(VariableSpec(id='param.' + p.id, label=p.label, source='parameter',
        parameter_id=p.id, quantity=p.unit.quantity, unit=p.unit)
        for p in definition.parameters if p.unit is not None and 'param.' + p.id not in known)
