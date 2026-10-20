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


def catalog_map() -> dict[str, ModuleDefinition]:
    return {m.id: m for m in builtin_catalog()}
