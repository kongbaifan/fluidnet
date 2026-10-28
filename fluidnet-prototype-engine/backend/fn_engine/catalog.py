from __future__ import annotations

from .models import ChannelSpec, Direction, Domain, ModuleDefinition, ParameterSpec, PortSpec, UnitSpec, VariableSpec


def number(id, label, default, quantity, unit, display=None, scale=1.0, minimum=None, maximum=None, runtime=False, offset=0.0):
    return ParameterSpec(id=id, label=label, default=default, minimum=minimum, maximum=maximum, runtime=runtime,
                         unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=display or unit,
                                       display_scale=scale, display_offset=offset))


def ports(*ids):
    return [PortSpec(id=id, label=id, direction=Direction.in_ if id.startswith('in') else Direction.out) for id in ids]


def channel(id, model, inlet='in0', outlet='out0'):
    return ChannelSpec(id=id, name=id, input_port=inlet, output_port=outlet,
                       relation='pump_curve' if model == 'pump_curve' else 'resistance', solver_model=model)


def builtin_catalog() -> list[ModuleDefinition]:
    definitions = [
        ModuleDefinition(id='source', name='压力边界', category='边界与节点', solver_model='pressure_source',
            ports=ports('out0'), parameters=[
                number('pressure_pa', '绝对压力', 201325.0, 'pressure', 'Pa', 'kPa', 1000.0, 1.0),
                # The usable range depends on the fluid; the compiler checks it against the property service.
                number('temperature_k', '边界温度', 293.15, 'temperature', 'K', '°C', minimum=1.0, offset=-273.15)]),
        ModuleDefinition(id='junction', name='连接节点', category='边界与节点', solver_model='junction',
            ports=[p.model_copy(update={'required': False}) for p in ports('in0', 'out0', 'out1')],
            parameters=[number('elevation_m', '标高（当前仅支持零标高）', 0.0, 'length', 'm', minimum=0, maximum=0)]),
        ModuleDefinition(id='pump', name='离心泵', category='流体机械', solver_model='pump_curve',
            ports=ports('in0', 'out0'), channels=[channel('ch0', 'pump_curve')], parameters=[
                number('speed_ratio', '转速比', 1.0, 'ratio', '1', '倍', minimum=0, maximum=2, runtime=True),
                number('efficiency_ratio', '泵效率', .75, 'ratio', '1', '%', .01, .01, 1),
                ParameterSpec(id='head_curve', label='扬程曲线 [m³/h, m]', value_type='curve',
                              default=[[0.,20.],[10.,18.],[20.,12.],[30.,0.]])]),
        ModuleDefinition(id='valve', name='调节阀', category='管道与阻力', solver_model='valve',
            ports=ports('in0', 'out0'), channels=[channel('ch0', 'valve')], parameters=[
                number('opening_ratio', '阀门开度', .8, 'ratio', '1', '%', .01, 0., 1., True),
                number('kv_m3_h', '流量系数 Kv', 16., 'flow_coefficient', 'm³/h', minimum=.001)]),
        ModuleDefinition(id='pipe', name='圆管', category='管道与阻力', solver_model='pipe',
            ports=ports('in0', 'out0'), channels=[channel('ch0', 'pipe')], parameters=[
                number('length_m', '管道长度', 30., 'length', 'm', minimum=.001),
                number('diameter_m', '管道内径', .04, 'length', 'm', 'mm', .001, .001),
                number('roughness_m', '绝对粗糙度', .000045, 'length', 'm', 'mm', .001, 0.),
                number('heat_loss_ua_w_k', '散热能力 UA（0 为绝热）', 0., 'conductance', 'W/K', minimum=0.),
                number('ambient_temperature_k', '环境温度', 293.15, 'temperature', 'K', '°C', minimum=1.0, offset=-273.15),
                # 0 keeps the algebraic pipe of 0.3; N > 0 adds N well-mixed cells of fluid + wall capacity.
                number('thermal_cells', '热容分段数（0 为无热惯性）', 0, 'count', '1', minimum=0, maximum=50),
                number('wall_heat_capacity_j_k', '管壁热容', 0., 'heat_capacity', 'J/K', 'kJ/K', 1000., 0.)]),
        # 矩形风管：沿程阻力按水力直径 Dh=2WH/(W+H) 与 Haaland 湍流摩擦计算，可选向环境散热；
        # 断面参数用 duct_width_m / duct_height_m，避免与 pipe 的高差 height_m 混淆。
        ModuleDefinition(id='duct', name='风管', category='管道与阻力', solver_model='duct',
            description='矩形风管：沿程阻力按水力直径与 Haaland 湍流摩擦计算，可选向环境散热；'
                        '无储热、无局部阻力（弯头/三通/变径等用 duct_fitting 模块）。',
            ports=ports('in0', 'out0'), channels=[channel('ch0', 'duct')], parameters=[
                number('length_m', '风管长度', 10., 'length', 'm', minimum=.001),
                number('duct_width_m', '断面宽', .4, 'length', 'm', 'mm', .001, .01),
                number('duct_height_m', '断面高', .4, 'length', 'm', 'mm', .001, .01),
                number('roughness_m', '绝对粗糙度', .00015, 'length', 'm', 'mm', .001, 0.),
                number('heat_loss_ua_w_k', '散热能力 UA（0 为绝热）', 0., 'conductance', 'W/K', minimum=0.),
                number('ambient_temperature_k', '环境温度', 293.15, 'temperature', 'K', '°C', minimum=1., offset=-273.15)]),
        ModuleDefinition(id='exchanger', name='双侧换热器（水力）', category='热力设备', solver_model='heat_exchanger',
            thermal_model='epsilon_ntu', ports=ports('in0', 'out0', 'in1', 'out1'),
            channels=[channel('ch0', 'resistance'), channel('ch1', 'resistance', 'in1', 'out1')], parameters=[
                number('ua_w_k', '传热能力 UA', 2000., 'conductance', 'W/K', minimum=0.),
                number('loss_coefficient', '局部阻力系数 K', 5., 'ratio', '1', minimum=.001),
                number('diameter_m', '水力等效内径', .04, 'length', 'm', 'mm', .001, .001)]),
        # Open, well-mixed tank: both ports sit on one node at p_surface + g·M/A (see ALGORITHM.md).
        ModuleDefinition(id='tank', name='开式水箱', category='边界与节点', solver_model='tank', state_model='open_tank',
            ports=[p.model_copy(update={'required': False}) for p in ports('in0', 'out0')], parameters=[
                number('level_m', '初始液位', 2., 'length', 'm', minimum=0.),
                number('area_m2', '横截面积', 2.5, 'area', 'm²', minimum=.001),
                number('height_m', '罐高（满箱液位）', 5., 'length', 'm', minimum=.001),
                number('surface_pressure_pa', '液面压力', 101325., 'pressure', 'Pa', 'kPa', 1000., 1.),
                number('temperature_k', '初始温度', 293.15, 'temperature', 'K', '°C', minimum=1.0, offset=-273.15),
                number('heat_input_w', '加热功率（负值为冷却）', 0., 'power', 'W', runtime=True),
                number('heat_loss_ua_w_k', '散热能力 UA（0 为绝热）', 0., 'conductance', 'W/K', minimum=0.),
                number('ambient_temperature_k', '环境温度', 293.15, 'temperature', 'K', '°C', minimum=1.0, offset=-273.15)]),
        # 困液定容原型（I0–I4）：单一均匀液体容积，V/M 固定，由总内能 U 经 state_du 得 p/T。
        # 不用开式水箱的定压储量语义；两端全关的被动段才允许激活（compiler 检查）。
        ModuleDefinition(id='closed_volume', name='封闭定容液腔（原型）', category='边界与节点',
            solver_model='closed_volume', state_model='closed_volume',
            description='刚性封闭液腔：V、M 固定，由总内能 U 经 state_du 得 p/T；仅 HEOS 纯水单相液体、两端阀门全关。'
                        'I0–I4 只交付单容积封闭原型，不包含完整开闭周期（I5–I9）。',
            ports=ports('in0', 'out0'), parameters=[
                number('volume_m3', '有效液体容积', 0., 'volume', 'm³', minimum=0.),
                number('wall_heat_capacity_j_k', '集总管壁热容（与流体同温）', 0., 'heat_capacity', 'J/K', minimum=0.),
                number('initial_temperature_k', '初始温度', 293.15, 'temperature', 'K', '°C', minimum=1.0, offset=-273.15),
                number('initial_pressure_pa', '初始绝对压力', 101325., 'pressure', 'Pa', 'kPa', 1000., 1.),
                number('heat_input_w', '加热功率（负值为冷却）', 0., 'power', 'W', runtime=True),
                number('heat_loss_ua_w_k', '散热能力 UA（0 为绝热）', 0., 'conductance', 'W/K', minimum=0.),
                number('ambient_temperature_k', '环境温度', 293.15, 'temperature', 'K', '°C', minimum=1.0, offset=-273.15)]),
        # 电加热器：理想加热段，把声明功率全部加入流经流体；无热容、无相变，
        # 零流量时拒绝加热（与 Python 模块的 heat_w 语义一致）。水力按局部阻力处理，
        # loss_coefficient=0 表示不产生附加压降。
        ModuleDefinition(id='heater', name='电加热器', category='热力设备', solver_model='heater',
            description='理想加热段：heat_input_w 全部进入流体，按质量流量折算比焓升；'
                        '无储热，零流量时拒绝加热；loss_coefficient=0 时不产生附加压降。',
            ports=ports('in0', 'out0'), channels=[channel('ch0', 'resistance')], parameters=[
                number('heat_input_w', '加热功率（负值为冷却）', 1000., 'power', 'W', 'kW', 1000., runtime=True),
                number('loss_coefficient', '局部阻力系数 K', 0., 'ratio', '1', minimum=0.),
                number('diameter_m', '水力等效内径', .04, 'length', 'm', 'mm', .001, .001)]),
    ]
    for definition in definitions:
        for port in definition.ports:
            # Thermal entries are None when SolverOptions.thermal is off.
            for suffix, label, quantity, unit, display, scale, offset in [
                ('pressure_pa', '绝对压力', 'pressure', 'Pa', 'kPa', 1000., 0.),
                ('mass_flow_kg_s', '端口流量（流入设备为正）', 'mass_flow', 'kg/s', 'kg/s', 1., 0.),
                ('temperature_k', '温度', 'temperature', 'K', '°C', 1., -273.15),
                ('enthalpy_j_kg', '比焓', 'specific_enthalpy', 'J/kg', 'kJ/kg', 1000., 0.),
                ('density_kg_m3', '密度', 'density', 'kg/m³', 'kg/m³', 1., 0.),
                ('viscosity_pa_s', '动力黏度', 'dynamic_viscosity', 'Pa·s', 'mPa·s', .001, 0.),
                ('specific_heat_j_kg_k', '定压比热', 'specific_heat', 'J/(kg·K)', 'kJ/(kg·K)', 1000., 0.),
                ('quality', '干度（单相为空）', 'ratio', '1', '1', 1., 0.),
            ]:
                definition.variables.append(VariableSpec(id=f'{port.id}.{suffix}', label=f'{port.id} {label}',
                    quantity=quantity, unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=display,
                                                     display_scale=scale, display_offset=offset),
                    source='port', port_id=port.id))
        branch_variables = [
            ('mass_flow_kg_s','质量流量','mass_flow','kg/s','kg/s',0.),
            ('volume_flow_m3_h','体积流量','volume_flow','m³/h','m³/h',0.),
            ('inlet_pressure_pa','入口绝对压力','pressure','Pa','Pa',0.),
            ('outlet_pressure_pa','出口绝对压力','pressure','Pa','Pa',0.),
            ('pressure_drop_pa','压降','pressure','Pa','Pa',0.),
            ('inlet_temperature_k','入口温度（上风侧）','temperature','K','°C',-273.15),
            ('outlet_temperature_k','出口温度（下风侧）','temperature','K','°C',-273.15),
            ('heat_w','流体焓流增量（换热+轴功+位能）','power','W','W',0.),
        ]
        for ch in definition.channels:
            for suffix, label, quantity, unit, display, offset in branch_variables:
                definition.variables.append(VariableSpec(id=f'{ch.id}.{suffix}', label=f'{ch.name} {label}', quantity=quantity,
                    unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=display, display_offset=offset), source='derived'))
                if len(definition.channels) == 1:
                    definition.variables.append(definition.variables[-1].model_copy(update={'id':suffix}))
        for param in definition.parameters:
            if param.value_type == 'number':
                assert param.unit is not None, '内置数值参数必须声明单位'
                definition.variables.append(VariableSpec(id=f'param.{param.id}',label=param.label,quantity=param.unit.quantity,
                    unit=param.unit,source='parameter',parameter_id=param.id))
        if definition.solver_model == 'pipe':
            # Present only when thermal_cells > 0 and the thermal layer is on.
            for suffix, label, quantity, unit, display, offset in [
                ('mean_temperature_k', '管内平均温度（热容分段）', 'temperature', 'K', '°C', -273.15),
                ('stored_power_w', '管段储热功率', 'power', 'W', 'W', 0.),
            ]:
                definition.variables.append(VariableSpec(id=f'state.{suffix}', label=label, quantity=quantity,
                    unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=display, display_offset=offset),
                    source='state'))
        if definition.state_model == 'open_tank':
            for suffix, label, quantity, unit, display, scale, offset in [
                ('level_m', '液位', 'length', 'm', 'm', 1., 0.),
                ('mass_kg', '存水质量', 'mass', 'kg', 'kg', 1., 0.),
                ('volume_m3', '存水体积', 'volume', 'm³', 'm³', 1., 0.),
                ('temperature_k', '水温', 'temperature', 'K', '°C', 1., -273.15),
                ('net_inflow_kg_s', '净流入质量流量', 'mass_flow', 'kg/s', 'kg/s', 1., 0.),
            ]:
                definition.variables.append(VariableSpec(id=f'state.{suffix}', label=label, quantity=quantity,
                    unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=display, display_scale=scale,
                                  display_offset=offset), source='state'))
        if definition.state_model == 'closed_volume':
            for suffix, label, quantity, unit, display, scale, offset in [
                ('pressure_pa', '封闭容积压力', 'pressure', 'Pa', 'kPa', 1000., 0.),
                ('temperature_k', '封闭容积温度', 'temperature', 'K', '°C', 1., -273.15),
                ('density_kg_m3', '平均密度 M/V', 'density', 'kg/m³', 'kg/m³', 1., 0.),
                ('mass_kg', '液体质量 M', 'mass', 'kg', 'kg', 1., 0.),
                ('volume_m3', '有效液体容积 V', 'volume', 'm³', 'm³', 1., 0.),
                ('specific_internal_energy_j_kg', '比内能 U/M', 'specific_internal_energy', 'J/kg', 'kJ/kg', 1000., 0.),
                ('internal_energy_j', '流体总内能 U', 'energy', 'J', 'kJ', 1000., 0.),
                ('wall_energy_j', '管壁储能 C_wall·(T−T_ref)', 'energy', 'J', 'kJ', 1000., 0.),
                ('total_energy_j', '总储能 U+管壁储能', 'energy', 'J', 'kJ', 1000., 0.),
                ('cumulative_heat_j', '累计热量收支', 'energy', 'J', 'kJ', 1000., 0.),
                ('heat_flow_w', '当前热流（正为加入）', 'power', 'W', 'W', 1., 0.),
                ('relative_mass_drift', '质量相对漂移', 'ratio', '1', '1', 1., 0.),
            ]:
                definition.variables.append(VariableSpec(id=f'state.{suffix}', label=label, quantity=quantity,
                    unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=display, display_scale=scale,
                                  display_offset=offset), source='state'))
        if definition.solver_model == 'pump_curve':
            definition.variables.append(VariableSpec(id='shaft_power_w',label='估算轴功率',quantity='power',
                unit=UnitSpec(quantity='power',canonical_unit='W',display_unit='W'),source='derived'))
    definitions.extend(thermal_catalog())
    definitions.extend(cold_store_catalog())
    definitions.extend(refrigeration_catalog())
    return definitions


def thermal_catalog() -> list[ModuleDefinition]:
    """A1 heat nodes and an explicitly ideal cold source; no refrigerant network."""
    room = ModuleDefinition(id='cold_room', name='库房热节点', category='冷库案例',
        solver_model='cold_room', state_model='room_temperature',
        description='空气及内部构件等效热容；围护漏热与热负荷。A1 不含货物热节点。',
        ports=[PortSpec(id='heat', label='冷却热接口', domain=Domain.thermal, direction=Direction.in_, circuit='thermal')],
        parameters=[
            number('temperature_k', '初始库温', 263.15, 'temperature', 'K', '°C', minimum=1, offset=-273.15),
            number('heat_capacity_j_k', '等效热容', 1200000., 'heat_capacity', 'J/K', 'kJ/K', 1000., minimum=1),
            number('ambient_temperature_k', '室外温度', 305.15, 'temperature', 'K', '°C', minimum=1, runtime=True, offset=-273.15),
            number('ground_temperature_k', '地面温度', 283.15, 'temperature', 'K', '°C', minimum=1, runtime=True, offset=-273.15),
            number('wall_ua_w_k', '墙体传热 UA', 31.68, 'conductance', 'W/K', minimum=0),
            number('roof_ua_w_k', '屋顶传热 UA', 14.4, 'conductance', 'W/K', minimum=0),
            number('floor_ua_w_k', '地面传热 UA', 20., 'conductance', 'W/K', minimum=0),
            number('heat_input_w', '附加热负荷', 0., 'power', 'W', 'kW', 1000., minimum=0, runtime=True)],
        variables=[
            VariableSpec(id='state.temperature_k', label='库温', source='state', quantity='temperature',
                         unit=UnitSpec(quantity='temperature', canonical_unit='K', display_unit='°C', display_offset=-273.15)),
            VariableSpec(id='envelope_heat_w', label='围护漏热', source='derived', quantity='power',
                         unit=UnitSpec(quantity='power', canonical_unit='W', display_unit='kW', display_scale=1000)),
            VariableSpec(id='stored_energy_j', label='库房储能（相对 273.15 K）', source='state', quantity='energy',
                         unit=UnitSpec(quantity='energy', canonical_unit='J', display_unit='kWh', display_scale=3600000)),
            VariableSpec(id='state.external_energy_j', label='累计外界输入热量', source='state', quantity='energy',
                         unit=UnitSpec(quantity='energy', canonical_unit='J', display_unit='kWh', display_scale=3600000)),
            VariableSpec(id='cooling_power_w', label='冷却功率', source='derived', quantity='power',
                         unit=UnitSpec(quantity='power', canonical_unit='W', display_unit='kW', display_scale=1000))])
    source = ModuleDefinition(id='ideal_cold_source', name='理想恒容量冷源 · A1', category='冷库案例',
        solver_model='ideal_cold_source', description='开发基准：指定制冷功率，不计算制冷循环、压缩功或 COP。',
        ports=[PortSpec(id='heat', label='冷量输出', domain=Domain.thermal, direction=Direction.out, circuit='thermal')],
        parameters=[
            number('cooling_power_w', '额定冷却功率', 10000., 'power', 'W', 'kW', 1000., minimum=0, runtime=True),
            number('capacity_ratio', '容量比例', 1., 'ratio', '1', '%', .01, 0., 1., True)],
        variables=[
            VariableSpec(id='cooling_power_w', label='实际冷却功率', source='derived', quantity='power',
                         unit=UnitSpec(quantity='power', canonical_unit='W', display_unit='kW', display_scale=1000)),
            VariableSpec(id='state.cooling_energy_j', label='累计冷量', source='state', quantity='energy',
                         unit=UnitSpec(quantity='energy', canonical_unit='J', display_unit='kWh', display_scale=3600000))])
    for definition in (room, source):
        for p in definition.parameters:
            assert p.unit is not None, '内置冷库参数必须声明单位'
            definition.variables.append(VariableSpec(id='param.' + p.id, label=p.label, source='parameter',
                parameter_id=p.id, quantity=p.unit.quantity, unit=p.unit))
    return [room, source]


def _heat_port(id, label, direction):
    return PortSpec(id=id, label=label, domain=Domain.thermal, direction=direction, circuit='thermal')


def cold_store_catalog() -> list[ModuleDefinition]:
    """Case-A devices: room + frozen goods, unit cooler, single-stage condensing unit (PLAN 3.1).

    The thermal chain is unit.cold → cooler.supply, cooler.heat → room.heat; the refrigerant is the
    project fluid and its two-phase states stay inside the condensing unit."""
    power = lambda id, label, default, runtime=False: number(id, label, default, 'power', 'W', 'kW', 1000., minimum=0, runtime=runtime)
    duration = lambda id, label, default: number(id, label, default, 'time', 's', 'min', 60., minimum=0)
    switch = lambda id, label, default: number(id, label, default, 'ratio', '1', minimum=0., maximum=1., runtime=True)
    energy = lambda id, label: _var(id, label, 'energy', 'J', 'kWh', 3600000., source='state')
    kw = lambda id, label, source='derived': _var(id, label, 'power', 'W', 'kW', 1000., source=source)
    celsius_var = lambda id, label, source='derived': _var(id, label, 'temperature', 'K', '°C', offset=-273.15, source=source)
    room = ModuleDefinition(id='storage_room', name='冻结物库房', category='冷库案例',
        solver_model='storage_room', state_model='room_goods',
        description='库房空气及内部构件等效热节点 + 冻结货物热节点；围护漏热、照明、开门与入库事件。货物只计冻结状态显热。',
        ports=[_heat_port('heat', '冷风机热接口', Direction.in_)],
        parameters=[
            _celsius('temperature_k', '初始库温', 263.15),
            _celsius('setpoint_temperature_k', '温控设定', 255.15, runtime=True),
            number('hysteresis_k', '温控回差（±）', .5, 'temperature_difference', 'K', minimum=.01, runtime=True),
            _celsius('alarm_temperature_k', '超温报警线', 256.15, runtime=True),
            number('capacity_alarm_delay_s', '满负荷超温报警延时', 3600., 'time', 's', 'min', 60., minimum=0),
            number('heat_capacity_j_k', '空气及构件等效热容', 1200000., 'heat_capacity', 'J/K', 'kJ/K', 1000., minimum=1),
            _celsius('ambient_temperature_k', '室外温度', 305.15, runtime=True),
            _celsius('ground_temperature_k', '地面温度', 283.15, runtime=True),
            number('wall_ua_w_k', '墙体传热 UA', 31.68, 'conductance', 'W/K', minimum=0),
            number('roof_ua_w_k', '屋顶传热 UA', 14.4, 'conductance', 'W/K', minimum=0),
            number('floor_ua_w_k', '地面传热 UA', 20., 'conductance', 'W/K', minimum=0),
            power('lighting_power_w', '照明功率', 100.),
            switch('lighting_on', '照明（1 开 / 0 关）', 0.),
            power('heat_input_w', '其他附加热负荷', 0., runtime=True),
            number('goods_mass_kg', '初始货物质量', 2000., 'mass', 'kg', minimum=0),
            number('goods_specific_heat_j_kg_k', '货物比热（冻结）', 1800., 'specific_heat', 'J/(kg·K)', 'kJ/(kg·K)', 1000., minimum=1),
            _celsius('goods_temperature_k', '初始货温', 258.15),
            number('goods_ua_w_k', '货物与库内换热 UA（初始质量）', 500., 'conductance', 'W/K', minimum=0),
            _celsius('goods_min_temperature_k', '货物冻结模型下限', 253.15),
            _celsius('goods_max_temperature_k', '货物冻结模型上限', 265.15),
            _celsius('energy_reference_temperature_k', '能量参考温度', 253.15)],
        variables=[
            celsius_var('state.temperature_k', '库温', 'state'), celsius_var('state.goods_temperature_k', '货温', 'state'),
            _var('state.goods_mass_kg', '货物质量', 'mass', 'kg', source='state'),
            _var('goods_ua_w_k', '货物换热 UA（按质量）', 'conductance', 'W/K'),
            kw('envelope_heat_w', '围护漏热'), kw('door_heat_w', '开门热负荷'), kw('lighting_heat_w', '照明热量'),
            kw('goods_heat_w', '货物放热（向库内）'), kw('fan_heat_w', '冷风机风机热'), kw('defrost_heat_w', '融霜进入库内热量'),
            kw('cooling_power_w', '冷风机制冷量（制冷剂侧）'), kw('net_heat_w', '库房净得热'),
            energy('stored_energy_j', '库房+货物储能（相对参考温度）'), energy('state.external_energy_j', '累计外界输入热量'),
            energy('state.goods_energy_j', '累计入库货物带入能量'), energy('state.cooling_energy_j', '累计冷风机制冷量'),
            energy('state.lighting_energy_j', '累计照明电量'),
            _var('state.time_above_alarm_s', '累计超温时间', 'time', 's', 'h', 3600., source='state'),
            _var('state.degree_hours_above_alarm', '超温度时', 'temperature_time', 'K·h', source='state'),
            _var('state.service_time_above_alarm_s', '保温期超温时间', 'time', 's', 'h', 3600., source='state'),
            _var('state.service_degree_hours_above_alarm', '保温期超温度时', 'temperature_time', 'K·h', source='state'),
            _var('state.in_service', '已进入保温（库温首次到达设定值）', 'ratio', '1', source='state'),
            _var('state.pulldown_time_s', '降温到设定值用时', 'time', 's', 'h', 3600., source='state'),
            _var('state.goods_pulldown_time_s', '货温到报警线用时', 'time', 's', 'h', 3600., source='state'),
            celsius_var('state.max_service_temperature_k', '保温期最高库温', 'state'),
            celsius_var('state.min_service_temperature_k', '保温期最低库温', 'state')])
    cooler = ModuleDefinition(id='unit_cooler', name='冷风机（库内）', category='冷库案例',
        solver_model='unit_cooler', state_model='cooler_mode',
        description='空气侧 Q = UA·(T_库 − T_蒸发)；风机热留在库内。电融霜：加热（停机停风机）→ 滴水等待 → 恢复制冷。不计霜量。',
        ports=[_heat_port('supply', '制冷剂冷量输入', Direction.in_), _heat_port('heat', '库内冷量输出', Direction.out)],
        parameters=[
            number('ua_w_k', '空气侧 UA（风机运行）', 1000., 'conductance', 'W/K', 'kW/K', 1000., minimum=1),
            power('fan_power_w', '风机功率', 300.),
            switch('fan_continuous', '风机常开（1）/ 随机组启停（0）', 0.),
            power('defrost_heater_power_w', '电融霜加热功率', 1500.),
            duration('defrost_duration_s', '融霜加热时长', 900.),
            duration('drip_duration_s', '滴水等待时长', 300.),
            _ratio('defrost_room_fraction', '融霜热量进入库内比例', 1.)],
        variables=[
            _var('state.mode', '状态（0 制冷 / 1 融霜加热 / 2 滴水）', 'count', '1', source='state'),
            _var('state.fan_running', '风机运行', 'ratio', '1', source='state'),
            kw('refrigerant_heat_w', '空气侧换热量'), kw('fan_power_w', '风机电功率'), kw('heater_power_w', '融霜电功率'),
            _var('state.defrost_count', '已完成融霜次数', 'count', '1', source='state'),
            _var('state.defrost_pending', '融霜等待（最小开机时间）', 'ratio', '1', source='state'),
            energy('state.fan_energy_j', '累计风机电量'), energy('state.heater_energy_j', '累计融霜电量')])
    unit = ModuleDefinition(id='condensing_unit', name='单级制冷机组', category='冷库案例',
        solver_model='condensing_unit', state_model='unit_switching',
        description='压缩—冷凝—节流—蒸发集中循环（工质为项目工质）。排量与冷凝器 UA 在额定点反算一次后固定；'
                    '蒸发/冷凝温度与冷风机、室外温度联立求解。最小开/停机时间由机组状态机保证。',
        ports=[_heat_port('cold', '蒸发冷量输出', Direction.out)],
        parameters=[
            switch('run_request', '运行请求（1 开 / 0 停）', 1.),
            _ratio('capacity_ratio', '容量请求', 1., runtime=True),
            switch('variable_capacity', '变容量（1）/ 定容量启停（0）', 0.),
            _ratio('min_capacity_ratio', '最小运行容量', .35, minimum=.01),
            power('rated_cooling_power_w', '额定制冷量', 10000.),
            _celsius('rated_evaporating_temperature_k', '额定蒸发温度', 245.15),
            _celsius('rated_condensing_temperature_k', '额定冷凝温度', 313.15),
            _celsius('rated_ambient_temperature_k', '额定环境温度（定冷凝器 UA）', 305.15),
            number('superheat_k', '吸气过热度', 5., 'temperature_difference', 'K', minimum=.1),
            number('subcooling_k', '冷凝器出口过冷度', 3., 'temperature_difference', 'K', minimum=.1),
            _ratio('isentropic_efficiency', '等熵效率', .65, minimum=.01),
            _ratio('volumetric_efficiency', '容积效率', .75, minimum=.01),
            _ratio('motor_efficiency', '电机效率', .9, minimum=.01),
            power('condenser_fan_power_w', '冷凝器风机功率', 200.),
            _celsius('ambient_temperature_k', '冷凝器进风温度（室外）', 305.15, runtime=True),
            duration('minimum_on_s', '最小开机时间', 120.),
            duration('minimum_off_s', '最小停机时间', 180.),
            duration('initial_off_elapsed_s', '初始已停机时长', 180.),
            _celsius('min_evaporating_temperature_k', '运行范围：最低蒸发温度', 233.15),
            _celsius('max_evaporating_temperature_k', '运行范围：最高蒸发温度', 263.15),
            _celsius('min_condensing_temperature_k', '运行范围：最低冷凝温度', 298.15),
            _celsius('max_condensing_temperature_k', '运行范围：最高冷凝温度', 323.15),
            _celsius('max_discharge_temperature_k', '运行范围：最高排气温度', 393.15),
            number('max_pressure_ratio', '运行范围：最大压比', 20., 'ratio', '1', minimum=1.)],
        variables=[
            _var('state.running', '运行', 'ratio', '1', source='state'),
            _var('actual_capacity_ratio', '实际容量', 'ratio', '1', '%', .01),
            _var('state.starts', '开机次数', 'count', '1', source='state'),
            _var('state.run_time_s', '累计运行时间', 'time', 's', 'h', 3600., source='state'),
            _var('state.state_elapsed_s', '当前开/停状态持续时间', 'time', 's', 'min', 60., source='state'),
            _var('state.switch_blocked', '启停请求被最小开/停机时间暂缓', 'ratio', '1', source='state'),
            celsius_var('evaporating_temperature_k', '蒸发温度'), celsius_var('condensing_temperature_k', '冷凝温度'),
            _var('evaporating_pressure_pa', '蒸发压力', 'pressure', 'Pa', 'kPa', 1000.),
            _var('condensing_pressure_pa', '冷凝压力', 'pressure', 'Pa', 'kPa', 1000.),
            celsius_var('suction_temperature_k', '吸气温度'), celsius_var('discharge_temperature_k', '排气温度'),
            _var('pressure_ratio', '压比', 'ratio', '1'), _var('mass_flow_kg_s', '质量流量', 'mass_flow', 'kg/s'),
            kw('cooling_power_w', '制冷量'), kw('shaft_power_w', '压缩轴功率'), kw('electric_power_w', '压缩机电功率'),
            kw('condenser_heat_w', '冷凝排热'), kw('condenser_fan_power_w', '冷凝器风机电功率'),
            _var('cop', '机组 COP（制冷量/压缩机电功率）', 'ratio', '1'),
            _var('system_cop', '系统瞬时 COP（制冷量/全部制冷设备电功率）', 'ratio', '1'),
            _var('displacement_m3_s', '额定点反算排量', 'volume_flow', 'm³/s', 'm³/h', 1 / 3600),
            _var('condenser_ua_w_k', '额定点反算冷凝器 UA', 'conductance', 'W/K'),
            *[_var(f'state{i}.{key}', f'状态点 {i} {label}', quantity, unit, display, scale, offset)
              for i in range(1, 5) for key, label, quantity, unit, display, scale, offset in [
                  ('pressure_pa', '压力', 'pressure', 'Pa', 'kPa', 1000., 0.),
                  ('temperature_k', '温度', 'temperature', 'K', '°C', 1., -273.15),
                  ('enthalpy_j_kg', '比焓', 'specific_enthalpy', 'J/kg', 'kJ/kg', 1000., 0.),
                  ('entropy_j_kg_k', '比熵', 'specific_entropy', 'J/(kg·K)', 'kJ/(kg·K)', 1000., 0.),
                  ('quality', '干度（单相为空）', 'ratio', '1', '1', 1., 0.)]],
            energy('state.electric_energy_j', '累计压缩机电量'), energy('state.condenser_fan_energy_j', '累计冷凝器风机电量'),
            energy('state.cooling_energy_j', '累计制冷量'), energy('state.condenser_heat_j', '累计冷凝排热')])
    definitions = [room, cooler, unit]
    for definition in definitions:
        definition.variables.extend(VariableSpec(id='param.' + p.id, label=p.label, source='parameter',
            parameter_id=p.id, quantity=p.unit.quantity, unit=p.unit) for p in definition.parameters if p.unit)
    return definitions


def _stream(id, label, direction, required=True, circuit='refrigerant'):
    return PortSpec(id=id, label=label, domain=Domain.refrigerant, direction=direction, required=required, circuit=circuit)


def _var(id, label, quantity, unit, display=None, scale=1., offset=0., source='derived'):
    return VariableSpec(id=id, label=label, source=source, quantity=quantity,
                        unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=display or unit,
                                      display_scale=scale, display_offset=offset))


def _celsius(id, label, default, runtime=False):
    return number(id, label, default, 'temperature', 'K', '°C', minimum=1, runtime=runtime, offset=-273.15)


def _ratio(id, label, default, runtime=False, minimum=0., maximum=1.):
    return number(id, label, default, 'ratio', '1', '%', .01, minimum, maximum, runtime)


def _switch(label='启停（1 运行 / 0 停机）'):
    return number('running', label, 1., 'ratio', '1', minimum=0., maximum=1., runtime=True)


def refrigeration_catalog() -> list[ModuleDefinition]:
    """Case-B lumped refrigeration-station devices; the fluid comes from each port's circuit."""
    def vessel(id, name, description, defaults, required, extra_inlets=0):
        volume, height, temperature, level = defaults
        labels = ['进液/进气', '进液/进气 2'] + [f'进液/进气 {i + 1}' for i in range(2, 2 + extra_inlets)]
        return ModuleDefinition(id=id, name=name, category='制冷站设备', solver_model='saturated_vessel',
            state_model='saturated_vessel', description=description,
            ports=[_stream(f'in{i}', label, Direction.in_, f'in{i}' in required) for i, label in enumerate(labels)]
                  + [_stream('vapor', '气相出口', Direction.out, 'vapor' in required),
                     _stream('liquid', '液相出口', Direction.out, 'liquid' in required)],
            parameters=[number('volume_m3', '容积', volume, 'volume', 'm³', minimum=.001),
                        number('height_m', '液位换算高度（立式等截面）', height, 'length', 'm', minimum=.01),
                        _celsius('temperature_k', '初始饱和温度', temperature),
                        _ratio('level_ratio', '初始液位（液体体积占比）', level, minimum=.01, maximum=.99),
                        _ratio('min_level_ratio', '模型适用液位下限', .05),
                        _ratio('max_level_ratio', '模型适用液位上限', .95)],
            variables=[_var('state.pressure_pa', '压力', 'pressure', 'Pa', 'MPa', 1e6, source='state'),
                       _var('state.temperature_k', '饱和温度', 'temperature', 'K', '°C', offset=-273.15, source='state'),
                       _var('state.mass_kg', '存量', 'mass', 'kg', source='state'),
                       _var('state.internal_energy_j', '内能', 'energy', 'J', 'MJ', 1e6, source='state'),
                       _var('state.liquid_mass_kg', '液相质量', 'mass', 'kg', source='state'),
                       _var('state.vapor_mass_kg', '气相质量', 'mass', 'kg', source='state'),
                       _var('state.quality', '罐内干度', 'ratio', '1', source='state'),
                       _var('state.level_ratio', '液位（体积占比）', 'ratio', '1', '%', .01, source='state'),
                       _var('state.level_m', '液位高度', 'length', 'm', source='state'),
                       _var('liquid_enthalpy_j_kg', '饱和液比焓', 'specific_enthalpy', 'J/kg', 'kJ/kg', 1000.),
                       _var('vapor_enthalpy_j_kg', '饱和气比焓', 'specific_enthalpy', 'J/kg', 'kJ/kg', 1000.),
                       _var('liquid_density_kg_m3', '饱和液密度', 'density', 'kg/m³'),
                       _var('vapor_density_kg_m3', '饱和气密度', 'density', 'kg/m³'),
                       _var('net_inflow_kg_s', '净流入质量流量', 'mass_flow', 'kg/s')])

    receiver = vessel('hp_receiver', '高压贮液器',
        '饱和两相集总容器：由存量 M、内能 U 与容积反求压力和液位。冷凝液进 in0，供液从 liquid 出。',
        (3., 2., 308.15, .62), {'in0', 'liquid'})
    lp_drum = vessel('lp_drum', '低压循环桶',
        '饱和两相集总容器：节流供液与满液式蒸发器回气进入，压缩机从 vapor 吸气，liquid 向蒸发器供液。',
        (4., 2., 243.15, .4), {'in0', 'vapor'})
    co2_drum = vessel('pumped_drum', '泵供液储液器',
        '载冷侧饱和两相集总容器：冷风机湿回气进入，vapor 去复叠冷凝侧，liquid 供液泵。',
        (3., 2., 247.15, .4), {'in0', 'vapor', 'liquid'})
    receiver_multi = vessel('hp_receiver_multi', '高压贮液器（多支路）',
        '同一饱和容器的四个进口：可接入多台冷凝器或回气支路；vapor/liquid 为气相、液相出口。'
        '集总模型只有一个压力等级，多出口同相态没有额外物理意义，分支请用集管。',
        (3., 2., 308.15, .62), {'in0', 'liquid'}, extra_inlets=2)
    lp_drum_multi = vessel('lp_drum_multi', '低压循环桶（多支路）',
        '同一饱和容器的四个进口：可接入多路回气或供液支路；vapor/liquid 为气相、液相出口。',
        (4., 2., 243.15, .4), {'in0', 'vapor'}, extra_inlets=2)
    compressor = ModuleDefinition(id='refrigerant_compressor', name='压缩机（强制流量）', category='制冷站设备',
        solver_model='refrigerant_compressor', description='吸气为吸气容器的饱和气；流量由排量、载量和容积效率决定，'
            '排气压力取排气侧容器压力。电机损耗排向机房，不进入制冷剂。',
        ports=[_stream('suction', '吸气', Direction.in_), _stream('discharge', '排气', Direction.out)],
        parameters=[_switch(), _ratio('load_ratio', '载量', 1., runtime=True),
                    number('displacement_m3_s', '理论排量', 290 / 3600, 'volume_flow', 'm³/s', 'm³/h', 1 / 3600, minimum=1e-6),
                    _ratio('volumetric_efficiency', '容积效率', .8, minimum=.01),
                    _ratio('isentropic_efficiency', '等熵效率', .72, minimum=.01),
                    _ratio('motor_efficiency', '电机效率', .92, minimum=.01),
                    number('max_pressure_ratio', '单级压比包络', 12., 'ratio', '1', minimum=1.)],
        variables=[_var('mass_flow_kg_s', '质量流量', 'mass_flow', 'kg/s'),
                   _var('shaft_power_w', '轴功率', 'power', 'W', 'kW', 1000.),
                   _var('electric_power_w', '电功率', 'power', 'W', 'kW', 1000.),
                   _var('discharge_temperature_k', '排气温度', 'temperature', 'K', '°C', offset=-273.15),
                   _var('pressure_ratio', '压比', 'ratio', '1'),
                   _var('state.electric_energy_j', '累计电量', 'energy', 'J', 'kWh', 3600000., source='state')])
    condenser = ModuleDefinition(id='evaporative_condenser', name='蒸发式冷凝器', category='制冷站设备',
        solver_model='evaporative_condenser', description='排热 = UA_eff·(T_cond − T_wb)。风机比例与贮液器回气阀开度修正 UA；'
            '回气阀关小时冷凝液积存、有效面积减小。按湿球温差近似，不解喷淋水与空气焓差。',
        ports=[_stream('in0', '排气进口', Direction.in_), _stream('out0', '冷凝液出口', Direction.out)],
        parameters=[number('ua_w_k', '额定 UA（风机全开）', 40000., 'conductance', 'W/K', 'kW/K', 1000., minimum=0.),
                    _ratio('fan_ratio', '风机投入比例', 1., runtime=True),
                    _ratio('natural_ua_ratio', '风机全停时 UA 比例', .2),
                    _celsius('wet_bulb_temperature_k', '室外湿球温度', 300.15, runtime=True),
                    number('fan_power_w', '风机与喷淋泵功率（全开）', 7500., 'power', 'W', 'kW', 1000., minimum=0.),
                    _ratio('return_gas_ratio', '贮液器回气阀开度', 1., runtime=True),
                    _ratio('flooded_ua_ratio', '回气阀全关时 UA 比例', .5)],
        variables=[_var('heat_rejection_w', '排热量', 'power', 'W', 'kW', 1000.),
                   _var('effective_ua_w_k', '有效 UA', 'conductance', 'W/K', 'kW/K', 1000.),
                   _var('condensing_temperature_k', '冷凝温度', 'temperature', 'K', '°C', offset=-273.15),
                   _var('fan_power_w', '风机功率', 'power', 'W', 'kW', 1000.),
                   _var('state.heat_rejected_j', '累计排热', 'energy', 'J', 'kWh', 3600000., source='state'),
                   _var('state.fan_energy_j', '累计风机电量', 'energy', 'J', 'kWh', 3600000., source='state')])
    valve = ModuleDefinition(id='expansion_valve', name='电磁节流阀', category='制冷站设备',
        solver_model='expansion_valve', description='饱和液经 Kv 节流（与调节阀同一 Kv 定义），等焓闪发；只允许正向流动。',
        ports=[_stream('in0', '高压液进口', Direction.in_), _stream('out0', '低压两相出口', Direction.out)],
        parameters=[number('kv_m3_h', '流量系数 Kv', .6, 'flow_coefficient', 'm³/h', minimum=.001),
                    _ratio('opening_ratio', '开度', .5, runtime=True)],
        variables=[_var('mass_flow_kg_s', '质量流量', 'mass_flow', 'kg/s'),
                   _var('pressure_drop_pa', '压差', 'pressure', 'Pa', 'MPa', 1e6),
                   _var('outlet_quality', '出口干度', 'ratio', '1')])
    cascade = ModuleDefinition(id='cascade_exchanger', name='复叠换热器（蒸发/冷凝）', category='制冷站设备',
        solver_model='cascade_exchanger', description='满液式：蒸发侧与冷凝侧均按饱和处理，Q = UA·(T_sat,冷凝 − T_sat,蒸发)。'
            '两侧分属不同回路与工质。',
        ports=[_stream('evap_in', '蒸发侧进液', Direction.in_, circuit='evaporating'),
               _stream('evap_out', '蒸发侧回气', Direction.out, circuit='evaporating'),
               _stream('cond_in', '冷凝侧进气', Direction.in_, circuit='condensing'),
               _stream('cond_out', '冷凝侧出液', Direction.out, circuit='condensing')],
        parameters=[number('ua_w_k', '传热能力 UA', 45000., 'conductance', 'W/K', 'kW/K', 1000., minimum=0.)],
        variables=[_var('heat_w', '换热量', 'power', 'W', 'kW', 1000.),
                   _var('approach_k', '两侧饱和温差', 'temperature_difference', 'K'),
                   _var('evaporated_kg_s', '蒸发侧蒸发量', 'mass_flow', 'kg/s'),
                   _var('condensed_kg_s', '冷凝侧冷凝量', 'mass_flow', 'kg/s')])
    pump = ModuleDefinition(id='refrigerant_pump', name='制冷剂液泵', category='制冷站设备',
        solver_model='refrigerant_pump', description='屏蔽泵：流量 ∝ 转速，压升 ∝ 转速²；电功率全部进入液体。不计汽蚀余量。',
        ports=[_stream('in0', '吸入', Direction.in_), _stream('out0', '排出', Direction.out)],
        parameters=[_switch(), _ratio('speed_ratio', '转速比（变频）', 1., runtime=True, maximum=1.2),
                    number('rated_mass_flow_kg_s', '额定质量流量', 2., 'mass_flow', 'kg/s', minimum=0.),
                    number('rated_pressure_rise_pa', '额定压升', 200000., 'pressure', 'Pa', 'kPa', 1000., minimum=0.),
                    _ratio('efficiency_ratio', '泵与电机效率', .45, minimum=.01)],
        variables=[_var('mass_flow_kg_s', '质量流量', 'mass_flow', 'kg/s'),
                   _var('pressure_rise_pa', '压升', 'pressure', 'Pa', 'kPa', 1000.),
                   _var('electric_power_w', '电功率', 'power', 'W', 'kW', 1000.),
                   _var('state.electric_energy_j', '累计电量', 'energy', 'J', 'kWh', 3600000., source='state')])
    cooler = ModuleDefinition(id='air_cooler', name='冷风机（泵供液）', category='制冷站设备',
        solver_model='air_cooler', description='空气侧 UA·(T_库 − T_蒸发)，受供液量与出口干度上限约束；'
            '风机热量留在库内。供液阀开度决定同一供液集管下各冷风机的分流比例。',
        ports=[_stream('in0', '供液', Direction.in_), _stream('out0', '湿回气', Direction.out),
               PortSpec(id='heat', label='冷量输出', domain=Domain.thermal, direction=Direction.out, circuit='thermal')],
        parameters=[_switch('风机启停（1 运行 / 0 停机）'),
                    number('ua_w_k', '空气侧 UA（风机全开）', 12000., 'conductance', 'W/K', 'kW/K', 1000., minimum=0.),
                    _ratio('fan_ratio', '风量比例', 1., runtime=True),
                    _ratio('natural_ua_ratio', '风机停转时 UA 比例', .1),
                    number('fan_power_w', '风机功率（全开）', 4000., 'power', 'W', 'kW', 1000., minimum=0.),
                    _ratio('supply_valve_ratio', '供液阀开度', 1., runtime=True),
                    _ratio('max_outlet_quality', '出口干度上限', .5, minimum=.01)],
        variables=[_var('refrigerant_heat_w', '制冷剂吸热量', 'power', 'W', 'kW', 1000.),
                   _var('room_cooling_w', '库房净冷量（扣风机热）', 'power', 'W', 'kW', 1000.),
                   _var('fan_power_w', '风机功率', 'power', 'W', 'kW', 1000.),
                   _var('supply_mass_flow_kg_s', '供液量', 'mass_flow', 'kg/s'),
                   _var('outlet_quality', '出口干度', 'ratio', '1'),
                   _var('evaporating_temperature_k', '蒸发温度', 'temperature', 'K', '°C', offset=-273.15),
                   _var('state.cooling_energy_j', '累计库房净冷量', 'energy', 'J', 'kWh', 3600000., source='state'),
                   _var('state.fan_energy_j', '累计风机电量', 'energy', 'J', 'kWh', 3600000., source='state')])
    header = ModuleDefinition(id='refrigerant_header', name='制冷剂集管', category='制冷站设备',
        solver_model='refrigerant_header', description='汇流/分流节点：同一压力等级内的多台设备经集管连到一个容器端口。',
        ports=[_stream(f'in{i}', f'汇入 {i + 1}', Direction.in_, False) for i in range(4)]
              + [_stream(f'out{i}', f'分出 {i + 1}', Direction.out, False) for i in range(4)])
    definitions = [receiver, lp_drum, co2_drum, receiver_multi, lp_drum_multi, compressor, condenser, valve, cascade,
                   pump, cooler, header]
    for definition in definitions:
        definition.variables.extend(VariableSpec(id='param.' + p.id, label=p.label, source='parameter',
            parameter_id=p.id, quantity=p.unit.quantity, unit=p.unit) for p in definition.parameters)
    return definitions


def catalog_map() -> dict[str, ModuleDefinition]:
    return {m.id: m for m in builtin_catalog()}
