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
        if definition.solver_model == 'pump_curve':
            definition.variables.append(VariableSpec(id='shaft_power_w',label='估算轴功率',quantity='power',
                unit=UnitSpec(quantity='power',canonical_unit='W',display_unit='W'),source='derived'))
    definitions.extend(thermal_catalog())
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
        definition.variables.extend(VariableSpec(id='param.' + p.id, label=p.label, source='parameter',
            parameter_id=p.id, quantity=p.unit.quantity, unit=p.unit) for p in definition.parameters)
    return [room, source]


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
    def vessel(id, name, description, defaults, required):
        volume, height, temperature, level = defaults
        return ModuleDefinition(id=id, name=name, category='制冷站设备', solver_model='saturated_vessel',
            state_model='saturated_vessel', description=description,
            ports=[_stream('in0', '进液/进气', Direction.in_, 'in0' in required),
                   _stream('in1', '进液/进气 2', Direction.in_, 'in1' in required),
                   _stream('vapor', '气相出口', Direction.out, 'vapor' in required),
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
                   _var('pressure_ratio', '压比', 'ratio', '1')])
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
                   _var('fan_power_w', '风机功率', 'power', 'W', 'kW', 1000.)])
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
                   _var('electric_power_w', '电功率', 'power', 'W', 'kW', 1000.)])
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
                   _var('evaporating_temperature_k', '蒸发温度', 'temperature', 'K', '°C', offset=-273.15)])
    header = ModuleDefinition(id='refrigerant_header', name='制冷剂集管', category='制冷站设备',
        solver_model='refrigerant_header', description='汇流/分流节点：同一压力等级内的多台设备经集管连到一个容器端口。',
        ports=[_stream(f'in{i}', f'汇入 {i + 1}', Direction.in_, False) for i in range(4)]
              + [_stream(f'out{i}', f'分出 {i + 1}', Direction.out, False) for i in range(4)])
    definitions = [receiver, lp_drum, co2_drum, compressor, condenser, valve, cascade, pump, cooler, header]
    for definition in definitions:
        definition.variables.extend(VariableSpec(id='param.' + p.id, label=p.label, source='parameter',
            parameter_id=p.id, quantity=p.unit.quantity, unit=p.unit) for p in definition.parameters)
    return definitions


def catalog_map() -> dict[str, ModuleDefinition]:
    return {m.id: m for m in builtin_catalog()}
