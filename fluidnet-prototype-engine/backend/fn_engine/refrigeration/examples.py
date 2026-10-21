"""Product A1 seed; canonical parameters mirror the versioned case assumptions."""
from ..catalog import catalog_map, cold_store_catalog, thermal_catalog
from ..models import (CircuitFluid, Connection, ControlScript, Endpoint, FluidConfig, ModuleInstance, PIDController,
                      Project, Scenario, ScheduleEvent, SolverOptions)


def ideal_room_example():
    return Project(id='cold-room-ideal-v1', name='−18°C 单库房 · A1 理想冷源',
        description='库房热容和围护漏热的开发基准；理想冷源，不含货物状态、制冷循环与能耗。',
        modules=thermal_catalog(),
        instances=[
            ModuleInstance(id='ROOM1', module_id='cold_room', name='冻结物储藏库 · 热节点'),
            ModuleInstance(id='COLD1', module_id='ideal_cold_source', name='理想冷源', parameters={'capacity_ratio': 1.})],
        connections=[Connection(id='heat1', source=Endpoint(instance_id='COLD1', port_id='heat'),
                                target=Endpoint(instance_id='ROOM1', port_id='heat'))],
        controllers=[PIDController(id='room_temperature', measurement='ROOM1.state.temperature_k',
            instance_id='COLD1', parameter_id='capacity_ratio', setpoint=255.15, kp=-.4, ki=-.002,
            sample_s=5., minimum=0., maximum=1.)],
        selected_variables=[],
        solver=SolverOptions(dynamic_step_s=10.))


# Case A thermostat: on/off hysteresis around the room setpoint; with variable capacity a PI on the
# room temperature sets the capacity request (anti-windup: the integral freezes while saturated).
ROOM_CONTROL = '''KP = 1.0       # capacity per K above setpoint
KI = 1 / 600   # capacity per K·s

def initialize(ctx):
    ctx.state["integral"] = 0.0
    ctx.state["request"] = 1.0

def step(ctx, dt_s):
    t = ctx.read("ROOM1.state.temperature_k")
    setpoint = ctx.read("ROOM1.param.setpoint_temperature_k")
    band = ctx.read("ROOM1.param.hysteresis_k")
    if t >= setpoint + band:
        ctx.state["request"] = 1.0
    elif t <= setpoint - band:
        ctx.state["request"] = 0.0
    error = t - setpoint
    raw = KP * error + ctx.state["integral"]
    if 0.0 < raw < 1.0 or raw >= 1.0 and error < 0 or raw <= 0.0 and error > 0:
        ctx.state["integral"] += KI * error * dt_s
    capacity = min(1.0, max(0.0, KP * error + ctx.state["integral"]))
    ctx.write("CU1.param.run_request", ctx.state["request"])
    ctx.write("CU1.param.capacity_ratio", capacity)

def finalize(ctx):
    pass
'''

# A-S01..A-S07 of cases/cold-storage/single-room-minus18/scenarios.json (durations in ROOM_SCENARIO_DURATIONS);
# A-S05 is split into its two control modes. tests/test_refrigeration_cold_store.py keeps them identical.
ROOM_SCENARIO_DURATIONS = {'A-S01': 21600., 'A-S02': 21600., 'A-S03': 28800., 'A-S04': 28800.,
                           'A-S05-onoff': 86400., 'A-S05-variable': 86400., 'A-S06': 86400., 'A-S07': 21600.}


def _room_scenarios():
    door = lambda id, t: ScheduleEvent(id=id, type='door_heat', time_s=t, duration_s=600., heat_w=5000.)
    goods = lambda id, t: ScheduleEvent(id=id, type='goods_addition', time_s=t, mass_kg=500., temperature_k=261.15)
    ambient = lambda id, t, k: ScheduleEvent(id=id, type='ambient_temperature', time_s=t, temperature_k=k)
    s05 = [door('door-1', 7200.), goods('goods-1', 14400.), ambient('ambient-rise', 28800., 311.15),
           door('door-2', 43200.), ambient('ambient-reset', 57600., 305.15)]
    return [
        Scenario(id='A-S01', name='A-S01 基础降温与保温 · 6 h', events=[]),
        Scenario(id='A-S02', name='A-S02 开门扰动 · 6 h', events=[door('door-1', 7200.)]),
        Scenario(id='A-S03', name='A-S03 冻结货物入库 · 8 h', events=[goods('goods-1', 7200.)]),
        Scenario(id='A-S04', name='A-S04 高环境温度 · 8 h', events=[ambient('ambient-1', 7200., 311.15)]),
        Scenario(id='A-S05-onoff', name='A-S05 控制对照 · 定容量启停 · 24 h', events=s05,
                 overrides={'CU1': {'variable_capacity': 0.}}),
        Scenario(id='A-S05-variable', name='A-S05 控制对照 · 变容量 · 24 h', events=s05,
                 overrides={'CU1': {'variable_capacity': 1.}}),
        Scenario(id='A-S06', name='A-S06 定时电融霜 · 24 h',
                 events=[ScheduleEvent(id='defrost-1', type='electric_defrost', time_s=28800.),
                         ScheduleEvent(id='defrost-2', type='electric_defrost', time_s=57600.)]),
        Scenario(id='A-S07', name='A-S07 制冷能力不足 · 6 h', events=[],
                 overrides={'CU1': {'rated_cooling_power_w': 2000.}}),
    ]


def room_example():
    """−18 °C single room (case A): room + goods, unit cooler, R290 single-stage unit, thermostat script."""
    return Project(id='cold-room-minus18-v1', name='−18°C 冻结物储藏库 · 单级 R290 机组',
        description='库房与冻结货物两个热节点、冷风机、单级制冷循环；温控脚本按回差启停，变容量时 PI 调节容量。'
                    '参数为示范假设（cases/cold-storage/single-room-minus18/parameters.json）。',
        fluid=FluidConfig(fluid='HEOS::R290'),
        modules=cold_store_catalog(),
        instances=[
            ModuleInstance(id='ROOM1', module_id='storage_room', name='冻结物储藏库'),
            ModuleInstance(id='AC1', module_id='unit_cooler', name='冷风机'),
            ModuleInstance(id='CU1', module_id='condensing_unit', name='单级制冷机组')],
        connections=[
            Connection(id='cold1', source=Endpoint(instance_id='CU1', port_id='cold'), target=Endpoint(instance_id='AC1', port_id='supply')),
            Connection(id='heat1', source=Endpoint(instance_id='AC1', port_id='heat'), target=Endpoint(instance_id='ROOM1', port_id='heat'))],
        control_scripts=[ControlScript(id='control', enabled=True, source=ROOM_CONTROL, sample_s=5.,
            inputs=['ROOM1.state.temperature_k', 'ROOM1.param.setpoint_temperature_k', 'ROOM1.param.hysteresis_k'],
            outputs=['CU1.param.run_request', 'CU1.param.capacity_ratio'])],
        scenarios=_room_scenarios(),
        solver=SolverOptions(dynamic_step_s=10.))


# Two identical rooms (case B): engineering assumptions sized so three of four compressors carry the load.
ROOM = {'temperature_k': 255.15, 'heat_capacity_j_k': 2e7, 'ambient_temperature_k': 305.15, 'ground_temperature_k': 283.15,
        'wall_ua_w_k': 900., 'roof_ua_w_k': 450., 'floor_ua_w_k': 250., 'heat_input_w': 30000.}


def station_example():
    """NH₃ station (4 compressors, condenser, receiver, valve, LP drum) cooling a CO₂ pumped loop for two rooms."""
    def link(id, a, b):
        return Connection(id=id, source=Endpoint(instance_id=a[0], port_id=a[1]), target=Endpoint(instance_id=b[0], port_id=b[1]))

    instances = [
        ModuleInstance(id='LP1', module_id='lp_drum', name='低压循环桶'),
        ModuleInstance(id='HP1', module_id='hp_receiver', name='高压贮液器'),
        ModuleInstance(id='CD1', module_id='pumped_drum', name='CO₂ 储液器'),
        ModuleInstance(id='SH1', module_id='refrigerant_header', name='吸气集管'),
        ModuleInstance(id='DH1', module_id='refrigerant_header', name='排气集管'),
        *[ModuleInstance(id=f'K{i}', module_id='refrigerant_compressor', name=f'压缩机 {i}',
                         parameters={'running': 0. if i == 4 else 1., 'load_ratio': .8}) for i in range(1, 5)],
        ModuleInstance(id='EC1', module_id='evaporative_condenser', name='蒸发式冷凝器'),
        ModuleInstance(id='EV1', module_id='expansion_valve', name='电磁节流阀', parameters={'opening_ratio': .4}),
        ModuleInstance(id='RH1', module_id='refrigerant_header', name='低压桶回气集管'),
        ModuleInstance(id='HX1', module_id='cascade_exchanger', name='复叠换热器'),
        ModuleInstance(id='PU1', module_id='refrigerant_pump', name='CO₂ 液泵'),
        ModuleInstance(id='FH1', module_id='refrigerant_header', name='供液集管'),
        ModuleInstance(id='BH1', module_id='refrigerant_header', name='湿回气集管'),
        *[ModuleInstance(id=f'AC{i}', module_id='air_cooler', name=f'冷风机 {i}') for i in (1, 2)],
        *[ModuleInstance(id=f'ROOM{i}', module_id='cold_room', name=f'库房 {i}', parameters=dict(ROOM)) for i in (1, 2)],
    ]
    connections = [
        link('s0', ('LP1', 'vapor'), ('SH1', 'in0')),
        *[link(f's{i}', ('SH1', f'out{i - 1}'), (f'K{i}', 'suction')) for i in range(1, 5)],
        *[link(f'd{i}', (f'K{i}', 'discharge'), ('DH1', f'in{i - 1}')) for i in range(1, 5)],
        link('d0', ('DH1', 'out0'), ('EC1', 'in0')),
        link('c1', ('EC1', 'out0'), ('HP1', 'in0')),
        link('v1', ('HP1', 'liquid'), ('EV1', 'in0')),
        link('v2', ('EV1', 'out0'), ('RH1', 'in0')),
        link('v3', ('RH1', 'out0'), ('LP1', 'in0')),
        link('x1', ('LP1', 'liquid'), ('HX1', 'evap_in')),
        link('x2', ('HX1', 'evap_out'), ('RH1', 'in1')),
        link('x3', ('CD1', 'vapor'), ('HX1', 'cond_in')),
        link('x4', ('HX1', 'cond_out'), ('CD1', 'in1')),
        link('p1', ('CD1', 'liquid'), ('PU1', 'in0')),
        link('p2', ('PU1', 'out0'), ('FH1', 'in0')),
        *[link(f'f{i}', ('FH1', f'out{i - 1}'), (f'AC{i}', 'in0')) for i in (1, 2)],
        *[link(f'b{i}', (f'AC{i}', 'out0'), ('BH1', f'in{i - 1}')) for i in (1, 2)],
        link('b0', ('BH1', 'out0'), ('CD1', 'in0')),
        *[link(f'h{i}', (f'AC{i}', 'heat'), (f'ROOM{i}', 'heat')) for i in (1, 2)],
    ]
    return Project(id='cold-storage-nh3co2-v1', name='NH₃/CO₂ 两库房冷库 · 集总制冷站',
        description='4 台单级 NH₃ 压缩机、蒸发式冷凝器、高压贮液器、节流阀、低压循环桶，复叠换热器冷凝 CO₂，'
                    'CO₂ 液泵向两间库房冷风机供液。参数为工程假设；尚未接入五闭环控制。',
        modules=[m for m in catalog_map().values() if m.id in {i.module_id for i in instances}],
        instances=instances, connections=connections,
        circuit_fluids=[CircuitFluid(id='nh3', anchor=Endpoint(instance_id='LP1', port_id='in0'),
                                     fluid=FluidConfig(fluid='Ammonia')),
                        CircuitFluid(id='co2', anchor=Endpoint(instance_id='CD1', port_id='in0'),
                                     fluid=FluidConfig(fluid='CarbonDioxide'))],
        solver=SolverOptions(dynamic_step_s=10.))
