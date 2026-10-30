"""A complete air handler, chilled-water loop and condenser-water loop.

Pressure references seed liquid temperatures but supply no heat to the closed loops.
All parameters are reproducible teaching assumptions, not calibrated equipment data.
"""
from .catalog import catalog_map
from .models import CircuitFluid, Connection, ControlScript, Endpoint, FluidConfig, ModuleInstance, PIDController, Scenario


ROOM_CONTROL_EXAMPLES = {
    'room-temperature-control': '房间自动温控 · 初始降温',
    'room-control-load-step': '房间自动温控 · 负荷阶跃',
    'room-control-setpoint-step': '房间自动温控 · 设定变化',
}
ROOM_CONTROL_DURATION_S = 2400.
ROOM_CONTROL_STEP_S = 30.
ROOM_CONTROL_CHANGE_S = 600.


def chiller_air_example():
    from .air_examples import air_example
    project = air_example('ahu-room').model_copy(deep=True)
    project.id, project.name = 'chiller-air-loop', '冷水机组与房间风水联算'
    catalog = catalog_map()
    project.modules = [m for m in project.modules if m.id != 'cooling_coil']
    project.modules.extend(catalog[k] for k in ('water_coil', 'water_chiller', 'pump', 'valve', 'cooling_tower_moist'))
    coil = next(i for i in project.instances if i.id == 'Coil')
    coil.module_id, coil.name, coil.parameters = 'water_coil', '冷水盘管', {}
    # No prescribed reheat/humidification: the room, outside air and water coil determine the load.
    next(i for i in project.instances if i.id == 'Reheat').parameters['heat_input_w'] = 0.
    next(i for i in project.instances if i.id == 'Humidifier').parameters['moisture_addition_kg_kg'] = 0.
    next(i for i in project.instances if i.id == 'Room').parameters.update(sensible_load_w=5000., additional_heat_capacity_j_k=1e6)

    def add(iid, kind, **params):
        project.instances.append(ModuleInstance(id=iid, module_id=kind, name={
            'Chiller':'水冷冷水机组', 'ChilledPump':'冷冻水泵', 'CoolingPump':'冷却水泵',
            'WaterValve':'盘管水阀', 'Tower':'冷却塔'}.get(iid, iid), parameters=params))

    add('Chiller', 'water_chiller')
    add('ChilledPump', 'pump', head_curve=[[0., 6.], [6., 4.], [12., 0.]])
    add('CoolingPump', 'pump', head_curve=[[0., 5.], [8., 3.], [16., 0.]])
    add('WaterValve', 'valve', kv_m3_h=8., opening_ratio=.8)
    add('Tower', 'cooling_tower_moist', air_volume_flow_m3_s=3.)
    add('ChilledRef', 'source', pressure_pa=200000., temperature_k=285.15)
    add('CoolingRef', 'source', pressure_pa=200000., temperature_k=303.15)
    add('ChilledJoin', 'junction')
    add('CoolingJoin', 'junction')
    links = [('ChilledRef:out0','ChilledJoin:in0'), ('ChilledJoin:out0','ChilledPump:in0'),
             ('ChilledPump:out0','Chiller:in0'), ('Chiller:out0','WaterValve:in0'),
             ('WaterValve:out0','Coil:in1'), ('Coil:out1','ChilledJoin:out1'),
             ('CoolingRef:out0','CoolingJoin:in0'), ('CoolingJoin:out0','CoolingPump:in0'),
             ('CoolingPump:out0','Chiller:in1'), ('Chiller:out1','Tower:in0'), ('Tower:out0','CoolingJoin:out1')]
    def endpoint(key):
        iid, port = key.split(':')
        return Endpoint(instance_id=iid, port_id=port)
    project.connections.extend(Connection(id=f'water{i}', source=endpoint(a), target=endpoint(b)) for i,(a,b) in enumerate(links))
    project.circuit_fluids = [CircuitFluid(id=key, anchor=Endpoint(instance_id='Chiller', port_id=port),
                                         fluid=FluidConfig(fluid='Water', phase_policy='liquid'))
                              for key, port in (('chilled-water','in0'), ('condenser-water','in1'))]
    project.solver.moist_air_options.max_iterations = 400
    return project


def room_temperature_example(name='room-temperature-control'):
    """Three repeatable room-control cases using the existing sampled PI and script APIs.

    Temperature is canonical K and the actuator is a dimensionless valve opening.
    This is continuous chiller operation with a nonzero valve floor, not an on/off model.
    """
    if name not in ROOM_CONTROL_EXAMPLES:
        raise KeyError(name)
    project = chiller_air_example()
    project.id, project.name = name, ROOM_CONTROL_EXAMPLES[name]
    project.description = ('室温反馈调节盘管水阀；固定风量、机组连续运行。'
        '初始 30°C，目标 26°C；负荷或设定阶跃发生在 600 s。'
        '建议动态运行 2400 s，输出和控制采样 30 s。参数为可复现工程假设。')
    room = next(i for i in project.instances if i.id == 'Room')
    room.parameters.update(initial_temperature_k=303.15, sensible_load_w=5000.)
    next(i for i in project.instances if i.id == 'WaterValve').parameters['opening_ratio'] = .4
    project.solver.dynamic_step_s = ROOM_CONTROL_STEP_S
    # The independent water book is stricter than the old example's node humidity tolerance.
    # Tighten the iteration stopping condition; conservation thresholds stay unchanged.
    project.solver.moist_air_options.humidity_tolerance_kg_kg = 1e-10
    project.controllers = [PIDController(id='room-temperature', measurement='Room.state.temperature_k',
        instance_id='WaterValve', parameter_id='opening_ratio', setpoint=299.15,
        kp=-.1, ki=-.00006, sample_s=ROOM_CONTROL_STEP_S, minimum=.02, maximum=1.)]
    if name != 'room-temperature-control':
        target, value = (('Room.param.sensible_load_w', 8000.) if name == 'room-control-load-step'
                         else ('controller.room-temperature.setpoint', 298.15))
        source = (
            '# 可编辑的单次工况变化；时间单位 s，温度 K，热负荷 W。\n'
            f'CHANGE_TIME_S = {ROOM_CONTROL_CHANGE_S!r}\n'
            f'TARGET = {target!r}\nVALUE = {value!r}\n\n'
            'def initialize(ctx):\n    ctx.state["applied"] = False\n\n'
            'def step(ctx, dt):\n'
            '    if ctx.time_s >= CHANGE_TIME_S and not ctx.state["applied"]:\n'
            '        ctx.write(TARGET, VALUE)\n'
            '        ctx.state["applied"] = True\n\n'
            'def finalize(ctx):\n    pass\n')
        project.control_scripts = [ControlScript(id='room-scenario', enabled=True, source=source,
            sample_s=ROOM_CONTROL_STEP_S, outputs=[target])]
    # Keep complete accepted frames for the air tables, PID plots, and frozen reports.
    project.selected_variables = []
    project.scenarios = [Scenario(id='normal-load', name='显热负荷 5 kW', overrides={'Room':{'sensible_load_w':5000.}}),
        Scenario(id='higher-load', name='显热负荷 8 kW', overrides={'Room':{'sensible_load_w':8000.}})]
    return project
