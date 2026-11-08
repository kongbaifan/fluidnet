"""Cold-room moisture/freezing, real frost/hot-gas paths and conserved oil inventories."""
from .._module_schema_v1 import Direction, ParameterSpec
from ..catalog import _celsius, _ratio, _stream, _var, number
from ..catalog_definitions import thermal_catalog as thermal_definitions
from ..model_types.module import ModuleDefinition
from .network_devices import definitions as network_definitions
from .network_devices import expose_parameters


def definitions():
    room = next(m for m in thermal_definitions() if m.id == 'cold_room').model_copy(deep=True, update={
        'id': 'logistics_cold_room', 'name': '冷库库房（货物相变与门热湿）',
        'state_model': 'room_moisture_goods_energy', 'category': '冷库过程',
        'description': '库房总能量与水蒸气质量、独立货物焓状态；门口浮力双向干空气交换；水分/能量随进入、结霜和排液逐项入账。'})
    for p in room.parameters:
        if p.id == 'heat_capacity_j_k': p.label = '空气/围护显热热容（不含独立货物）'
    room.parameters += [number('dry_air_mass_kg', '等效干空气质量', 1000., 'mass', 'kg', minimum=1.),
        _ratio('initial_relative_humidity', '初始相对湿度', .7),
        _ratio('ambient_relative_humidity', '室外相对湿度', .6, runtime=True),
        number('air_pressure_pa', '空气绝压', 101325., 'pressure', 'Pa', 'kPa', 1000., minimum=1000.),
        _ratio('door_opening_ratio', '门开启比例', 0., runtime=True),
        number('door_width_m', '门宽', 2., 'length', 'm', minimum=.01),
        number('door_height_m', '门高', 2.3, 'length', 'm', minimum=.01),
        _ratio('door_discharge_coefficient', '门交换流量系数', .65, minimum=.01),
        _ratio('door_protection_efficiency', '门帘/风幕有效率', 0.),
        number('mechanical_exchange_kg_s', '开门时附加机械干空气交换', 0., 'mass_flow', 'kg/s', minimum=0.),
        number('goods_mass_kg', '独立货物质量', 500., 'mass', 'kg', minimum=0.),
        _celsius('goods_initial_temperature_k', '货物初温', 283.15),
        _celsius('goods_freezing_temperature_k', '货物等效冻结温度', 271.15),
        number('goods_latent_heat_j_kg', '货物冻结潜热', 250500., 'specific_energy', 'J/kg', 'kJ/kg', 1000., minimum=1.),
        number('goods_unfrozen_cp_j_kg_k', '未冻货物比热', 3500., 'specific_heat', 'J/kg/K', minimum=1.),
        number('goods_frozen_cp_j_kg_k', '冻结货物比热', 1800., 'specific_heat', 'J/kg/K', minimum=1.),
        number('goods_ua_w_k', '货物与库房换热UA', 50., 'conductance', 'W/K', minimum=0.),
        ParameterSpec(id='process_source', label='过程参数来源', value_type='text', default='公开基础物性与自定义等效货物/门流量系数')]
    room.variables += [_var('state.room_energy_j', '库房总能量', 'energy', 'J', source='state'),
        _var('state.water_vapor_mass_kg', '库房水蒸气质量', 'mass', 'kg', source='state'),
        _var('state.goods_energy_j', '货物焓库存', 'energy', 'J', source='state'),
        _var('humidity_ratio_kg_kg', '实际含湿量', 'humidity_ratio', 'kg/kg'),
        _var('goods_temperature_k', '货物温度', 'temperature', 'K', '°C', offset=-273.15),
        _var('goods_frozen_ratio', '货物冻结比例', 'ratio', '1', '%', .01),
        _var('door_dry_air_flow_kg_s', '门实际干空气交换', 'mass_flow', 'kg/s'),
        _var('infiltration_heat_w', '门交换热湿焓流', 'power', 'W')]
    cooler = next(m for m in network_definitions() if m.id == 'network_air_cooler').model_copy(deep=True, update={
        'id': 'frost_hotgas_cooler', 'solver_model': 'frost_hotgas_cooler', 'name': '冷风机（霜层与热气融霜）',
        'state_model': 'frost_metal_water_energy', 'category': '冷库过程',
        'description': '霜/水质量和金属/相变能量进入隐式向量；热气与凝液独立真实流股；预排、融霜、滴水、再冷却顺序与剩余霜量可读取。'})
    cooler.ports += [_stream('hot_in', '融霜热气进口', Direction.in_, False),
                     _stream('hot_out', '融霜凝液出口', Direction.out, False)]
    cooler.parameters += [number('initial_frost_mass_kg', '初始霜质量', 1., 'mass', 'kg', minimum=0.),
        _celsius('initial_surface_temperature_k', '盘管表面初温', 248.15),
        number('metal_heat_capacity_j_k', '盘管金属热容', 5000., 'heat_capacity', 'J/K', minimum=1.),
        number('refrigerant_contact_ua_w_k', '冷媒/盘管导热UA', 2000., 'conductance', 'W/K', minimum=0.),
        number('hot_gas_kv_m3_h', '热气通路等效Kv', .002, 'flow_coefficient', 'm³/h', minimum=0.),
        number('hot_gas_ua_w_k', '热气侧UA', 2000., 'conductance', 'W/K', minimum=0.),
        number('surface_area_m2', '结霜有效面积', 10., 'area', 'm²', minimum=.01),
        number('frost_density_kg_m3', '霜密度', 200., 'density', 'kg/m³', minimum=1.),
        number('frost_conductivity_w_m_k', '霜导热率', .2, 'conductivity', 'W/m/K', minimum=.001),
        number('dry_air_flow_kg_s', '冷风机干空气流量', 5., 'mass_flow', 'kg/s', minimum=0.),
        _ratio('deposition_effectiveness', '冷凝沉积有效度', .5),
        _ratio('defrost_request', '融霜请求（上升沿）', 0., runtime=True),
        number('predrain_duration_s', '预排液时间', 5., 'time', 's', minimum=0.),
        number('defrost_duration_s', '融霜最长时间', 300., 'time', 's', minimum=1.),
        number('drip_duration_s', '滴水时间', 30., 'time', 's', minimum=0.),
        number('recool_duration_s', '再冷却时间', 10., 'time', 's', minimum=0.),
        _celsius('defrost_end_temperature_k', '融霜结束表温', 278.15),
        number('drain_time_constant_s', '水排液时间常数', 10., 'time', 's', minimum=.1),
        number('electric_defrost_power_w', '辅助电融霜功率', 0., 'power', 'W', minimum=0.)]
    cooler.variables += [_var('heater_power_w', '辅助电融霜功率', 'power', 'W'),
        _var('state.heater_energy_j', '累计辅助融霜电能', 'energy', 'J', source='state'),
        _var('state.frost_water_mass_kg', '霜/水总质量', 'mass', 'kg', source='state'),
        _var('state.surface_energy_j', '盘管/霜/水能量', 'energy', 'J', source='state'),
        _var('frost_mass_kg', '实际固态霜质量', 'mass', 'kg'), _var('melt_water_mass_kg', '实际融水质量', 'mass', 'kg'),
        _var('surface_temperature_k', '盘管表面温度', 'temperature', 'K', '°C', offset=-273.15),
        _var('frost_thickness_m', '实际霜厚', 'length', 'm', 'mm', .001),
        _var('effective_air_ua_w_k', '霜层后空气UA', 'conductance', 'W/K'),
        _var('hot_gas_heat_w', '实际热气融霜热量', 'power', 'W'),
        _var('defrost_mode', '融霜阶段0冷却/1预排/2热气/3滴水/4再冷却', 'count', '1'),
        _var('state.drained_water_kg', '累计排水', 'mass', 'kg', source='state')]
    oil = ModuleDefinition(id='compressor_oil_system', name='压缩机油分离与回油系统', category='冷库过程',
        solver_model='compressor_oil_system', state_model='oil_mass_energy_network',
        description='独立油槽、油分离器和逐冷风机油库存M/E；携油、分离、回油、油冷却与冷媒传热/油污折减分别入账。回油为可标定一阶模型。',
        ports=[_stream('in0', '压缩机排气', Direction.in_), _stream('out0', '分离后排气', Direction.out)],
        parameters=[number('initial_sump_mass_kg', '初始油槽质量', 60., 'mass', 'kg', minimum=.01),
            number('initial_separator_mass_kg', '初始分离器油量', .2, 'mass', 'kg', minimum=0.),
            _celsius('initial_oil_temperature_k', '初始油温', 303.15),
            number('oil_cp_j_kg_k', '油比热', 2000., 'specific_heat', 'J/kg/K', minimum=1.),
            number('metal_heat_capacity_j_k', '每油库存金属热容', 1000., 'heat_capacity', 'J/K', minimum=1.),
            _ratio('carryover_ratio', '携油/冷媒质量比', .01, maximum=.2),
            _ratio('separation_efficiency', '油分离效率', .95),
            _ratio('return_ratio', '回油阀比例', 1., runtime=True),
            number('sump_draw_time_s', '油槽最短抽取时间', 1., 'time', 's', minimum=.01),
            number('receiver_transport_time_s', '贮液侧油输运时间', 120., 'time', 's', minimum=.01),
            number('oil_reference_flow_kg_s', '携油输运参考冷媒流量', .2, 'mass_flow', 'kg/s', minimum=.001),
            number('separator_return_time_s', '分离器回油时间常数', 300., 'time', 's', minimum=1.),
            number('evaporator_return_time_s', '蒸发器回油时间常数', 1800., 'time', 's', minimum=1.),
            number('gas_contact_ua_w_k', '排气/油换热UA', 20., 'conductance', 'W/K', minimum=0.),
            number('evaporator_contact_ua_w_k', '油/蒸发器换热UA', 2., 'conductance', 'W/K', minimum=0.),
            number('oil_cooler_ua_w_k', '油冷却器UA', 10., 'conductance', 'W/K', minimum=0.),
            _celsius('oil_sink_temperature_k', '油冷却介质温度', 293.15),
            number('fouling_per_kg', '油积聚热阻折减系数', .5, 'inverse_mass', '1/kg', minimum=0.),
            number('diameter_m', '排气通流内径', .04, 'length', 'm', 'mm', .001, minimum=.001),
            number('loss_coefficient', '油分离器压降K', 2., 'ratio', '1', minimum=0.),
            ParameterSpec(id='oil_source', label='油参数来源', value_type='text', default='自定义等效油和一阶携油/回油模型')],
        variables=[_var('state.sump_mass_kg', '油槽质量', 'mass', 'kg', source='state'),
                   _var('state.separator_mass_kg', '分离器油质量', 'mass', 'kg', source='state'),
                   _var('oil_total_mass_kg', '全油路质量', 'mass', 'kg'),
                   _var('oil_energy_j', '全油路储能', 'energy', 'J'),
                   _var('oil_mass_residual_kg', '油路质量残差', 'mass', 'kg'),
                   _var('oil_cooling_w', '油冷却散热', 'power', 'W')])
    result = [room, cooler, oil]
    for definition in result:
        expose_parameters(definition)
    return result
