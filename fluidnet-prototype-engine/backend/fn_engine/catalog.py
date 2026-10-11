from __future__ import annotations

from .models import ChannelSpec, Direction, ModuleDefinition, ParameterSpec, PortSpec, UnitSpec, VariableSpec


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
                number('temperature_k', '边界温度', 293.15, 'temperature', 'K', '°C', minimum=274.15, maximum=363.15, offset=-273.15)]),
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
                number('ambient_temperature_k', '环境温度', 293.15, 'temperature', 'K', '°C', minimum=274.15, maximum=363.15, offset=-273.15)]),
        ModuleDefinition(id='exchanger', name='双侧换热器（水力）', category='热力设备', solver_model='heat_exchanger',
            thermal_model='epsilon_ntu', ports=ports('in0', 'out0', 'in1', 'out1'),
            channels=[channel('ch0', 'resistance'), channel('ch1', 'resistance', 'in1', 'out1')], parameters=[
                number('ua_w_k', '传热能力 UA', 2000., 'conductance', 'W/K', minimum=0.),
                number('loss_coefficient', '局部阻力系数 K', 5., 'ratio', '1', minimum=.001),
                number('diameter_m', '水力等效内径', .04, 'length', 'm', 'mm', .001, .001)]),
        ModuleDefinition(id='tank', name='储水罐（状态模型待实现）', category='边界与节点', solver_model='tank',
            state_model='well_mixed_volume', ports=ports('in0', 'out0'), parameters=[
                number('level_m', '初始液位', 2., 'length', 'm', minimum=0.),
                number('area_m2', '横截面积', 2.5, 'area', 'm²', minimum=.001)]),
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
        if definition.solver_model == 'pump_curve':
            definition.variables.append(VariableSpec(id='shaft_power_w',label='估算轴功率',quantity='power',
                unit=UnitSpec(quantity='power',canonical_unit='W',display_unit='W'),source='derived'))
    return definitions


def catalog_map() -> dict[str, ModuleDefinition]:
    return {m.id: m for m in builtin_catalog()}
