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

def needed(fan, lower, valve):
    # Return-gas opening that keeps today's UA after dropping one fan group (condenser UA model of EC1).
    ua = (NATURAL + (1 - NATURAL) * fan) * (FLOODED + (1 - FLOODED) * valve)
    return (ua / (NATURAL + (1 - NATURAL) * lower) - FLOODED) / (1 - FLOODED)

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


# B0 design point: cases/cold-storage/nh3-co2/station/references/design_point.json (tests keep them equal).
# Case B upper loop (Python project control). PIDs own: K1 load (suction pressure), EC1 return-gas valve
# (receiver/condensing pressure), EV1 opening (receiver level), AC1/AC2 fan ratio (room temperatures).
STATION_CONTROL = '''MIN_ON, MIN_OFF, CONFIRM = 600.0, 300.0, 300.0   # compressor minimum on/off and staging confirmation, s
START_LOAD, STOP_REMAINING = 0.95, 0.90        # start when the running mean load stays high; stop if the rest stay below
FAN_INTERVAL = 300.0                           # condenser fan group staging, s
NATURAL, FLOODED = 0.2, 0.5                    # EC1 natural_ua_ratio / flooded_ua_ratio
FAN_RAMP = 0.005                               # fan ratio change per 10 s sample (one group in 1000 s)
PUMP_MIN, PUMP_GAIN = 0.3, 0.7                 # loop 5: pump speed from the mean cooler fan ratio
BAND = 1.0                                     # demand satisfaction: room within setpoint ± BAND
FOLLOWERS = ["K2", "K3", "K4"]

def initialize(ctx):
    ctx.state.update({"last_K2": -1e9, "last_K3": -1e9, "last_K4": -1e9, "high_since": -1.0, "low_since": -1.0,
                      "fan_since": -1e9, "fan_high_since": -1.0, "fan_low_since": -1.0, "in_band_1": 0.0, "in_band_2": 0.0,
                      "elapsed": 0.0, "starts": 0.0, "stops": 0.0, "fan_changes": 0.0, "reason": "初始",
                      "infeasible_since": -1.0, "infeasible": 0.0})

def timer(ctx, key, active, t):
    if not active:
        ctx.state[key] = -1.0
        return 0.0
    if ctx.state[key] < 0:
        ctx.state[key] = t
    return t - ctx.state[key]

def needed(fan, lower, valve):
    # Return-gas opening that keeps today's UA after dropping one fan group (condenser UA model of EC1).
    ua = (NATURAL + (1 - NATURAL) * fan) * (FLOODED + (1 - FLOODED) * valve)
    return (ua / (NATURAL + (1 - NATURAL) * lower) - FLOODED) / (1 - FLOODED)

def step(ctx, dt_s):
    s, t = ctx.state, ctx.time_s
    lead = ctx.read("K1.param.load_ratio")
    running = [k for k in FOLLOWERS if ctx.read(k + ".param.running") >= 0.5]
    n = 1 + len(running)
    # Upper loop: number of compressors from the lead load (all running units carry the same load).
    if timer(ctx, "high_since", lead >= START_LOAD, t) >= CONFIRM:
        stopped = [k for k in FOLLOWERS if k not in running and t - s["last_" + k] >= MIN_OFF]
        if stopped:
            running.append(stopped[0]); s["last_" + stopped[0]] = t; s["high_since"] = -1.0
            s["starts"] += 1; s["reason"] = f"t={t:.0f}s 载量 {lead:.2f} 持续偏高，启动 {stopped[0]}"
    remaining = lead * n / (n - 1) if n > 1 else 9.0
    if timer(ctx, "low_since", remaining < STOP_REMAINING, t) >= CONFIRM:
        movable = [k for k in reversed(running) if t - s["last_" + k] >= MIN_ON]
        if movable:
            running.remove(movable[0]); s["last_" + movable[0]] = t; s["low_since"] = -1.0
            s["stops"] += 1; s["reason"] = f"t={t:.0f}s 停一台后载量约 {remaining:.2f}，停止 {movable[0]}"
    for k in FOLLOWERS:
        ctx.write(k + ".param.running", 1.0 if k in running else 0.0)
        ctx.write(k + ".param.load_ratio", lead)
    # Upper loop: condenser fan groups (0, 1/2, 1) from the return-gas valve the pressure PID is using.
    # Upper loop: condenser fan groups (stages 0, 1/2, 1) from the return-gas valve the pressure PID is using;
    # the fan ratio ramps to the stage (FAN_RAMP per sample), as fan motors do.
    fan, valve = ctx.read("EC1.param.fan_ratio"), ctx.read("EC1.param.return_gas_ratio")
    stage = s.setdefault("fan_stage", fan)
    error = ctx.read("HP1.state.pressure_pa") - ctx.read("controller.head.setpoint")
    if t - s["fan_since"] >= FAN_INTERVAL and abs(fan - stage) < 1e-9:
        raise_ok = valve >= 0.98 and error > 2e4 and stage < 1.0
        lower_ok = valve <= 0.6 and error <= 1e4 and stage > 0.0 and needed(stage, stage - 0.5, valve) <= 0.85
        if timer(ctx, "fan_high_since", raise_ok, t) >= 120.0:
            stage = min(1.0, stage + 0.5); s["fan_since"] = t; s["fan_changes"] += 1
            s["reason"] = f"t={t:.0f}s 回气阀全开仍超压，冷凝器风机增至 {stage:.1f}"
        elif timer(ctx, "fan_low_since", lower_ok, t) >= FAN_INTERVAL:
            stage = max(0.0, stage - 0.5); s["fan_since"] = t; s["fan_changes"] += 1
            s["reason"] = f"t={t:.0f}s 回气阀开度低、冷凝能力过剩，冷凝器风机减至 {stage:.1f}"
    s["fan_stage"] = stage
    fan = min(stage, fan + FAN_RAMP) if stage > fan else max(stage, fan - FAN_RAMP)
    ctx.write("EC1.param.fan_ratio", fan)
    # Condensing target not reachable: return-gas valve and fans fully open, pressure still high.
    if timer(ctx, "infeasible_since", valve >= 0.98 and fan >= 1.0 and error > 2e4, t) >= 1800.0 and not s["infeasible"]:
        s["infeasible"] = 1.0
        ctx.log(f"冷凝能力已到上限，目标冷凝压力不可达（实际高出 {error / 1000:.0f} kPa）")
    elif s["infeasible_since"] < 0:
        s["infeasible"] = 0.0
    # Loop 5: CO2 pump speed follows the cooler fans.
    mean_fan = (ctx.read("AC1.param.fan_ratio") + ctx.read("AC2.param.fan_ratio")) / 2
    ctx.write("PU1.param.speed_ratio", min(1.0, max(PUMP_MIN, PUMP_MIN + PUMP_GAIN * mean_fan)))
    # Feedback: demand satisfaction (own definition: time share inside setpoint ± BAND).
    s["elapsed"] += dt_s
    for i in (1, 2):
        if abs(ctx.read(f"ROOM{i}.state.temperature_k") - ctx.read(f"controller.room{i}.setpoint")) <= BAND:
            s[f"in_band_{i}"] += dt_s
    s["satisfaction"] = (s["in_band_1"] + s["in_band_2"]) / (2 * s["elapsed"]) if s["elapsed"] > 0 else 1.0
    s["running"] = float(len(running) + 1)

def finalize(ctx):
    pass
'''
STATION_SCENARIO_DURATIONS = {'B-S01': 86400., 'B-S02': 86400., 'B-S03': 64800., 'B-S04': 72000.}


def station_case():
    """Case B with the five loops and the upper loop; actuators start at the B0 design point."""
    from ..models import ScheduleEvent
    project = station_example()
    design = {'LP1': {'temperature_k': 241.482716507}, 'HP1': {'temperature_k': 308.150214111, 'level_ratio': .633},
              'CD1': {'temperature_k': 245.577548873}, 'EV1': {'opening_ratio': .388}, 'PU1': {'rated_mass_flow_kg_s': 3., 'speed_ratio': .72},
              'EC1': {'return_gas_ratio': .739}, **{f'AC{i}': {'fan_ratio': .6, 'ua_w_k': 15000.} for i in (1, 2)},
              **{f'ROOM{i}': {'heat_input_w': 15000.} for i in (1, 2)},
              **{f'K{i}': {'load_ratio': .826, 'running': 0. if i == 4 else 1., 'displacement_m3_s': 330 / 3600, 'max_pressure_ratio': 14.}
                 for i in range(1, 5)}}
    for instance in project.instances:
        instance.parameters.update(design.get(instance.id, {}))
    pid = lambda id, measurement, iid, parameter, setpoint, kp, ki, lo=0., hi=1.: PIDController(id=id, measurement=measurement,
        instance_id=iid, parameter_id=parameter, setpoint=setpoint, kp=kp, ki=ki, sample_s=10., minimum=lo, maximum=hi)
    project.controllers = [
        pid('suction', 'LP1.state.pressure_pa', 'K1', 'load_ratio', 110000., -2e-5, -2e-5 / 300, .2),
        pid('head', 'HP1.state.pressure_pa', 'EC1', 'return_gas_ratio', 1350000., -4e-6, -4e-6 / 300),
        pid('level', 'HP1.state.level_ratio', 'EV1', 'opening_ratio', .633, -5., -5. / 600),
        *[pid(f'room{i}', f'ROOM{i}.state.temperature_k', f'AC{i}', 'fan_ratio', 255.15, -.3, -.3 / 1200) for i in (1, 2)]]
    reads = ['K1.param.load_ratio', *[f'K{i}.param.running' for i in (2, 3, 4)], 'EC1.param.fan_ratio', 'EC1.param.return_gas_ratio',
             'HP1.state.pressure_pa', 'controller.head.setpoint', 'AC1.param.fan_ratio', 'AC2.param.fan_ratio',
             'ROOM1.state.temperature_k', 'ROOM2.state.temperature_k', 'controller.room1.setpoint', 'controller.room2.setpoint']
    writes = [*[f'K{i}.param.{p}' for i in (2, 3, 4) for p in ('running', 'load_ratio')], 'EC1.param.fan_ratio', 'PU1.param.speed_ratio']
    project.control_scripts = [ControlScript(id='control', enabled=True, source=STATION_CONTROL, sample_s=10., inputs=reads, outputs=writes)]
    set_ = lambda id, t, key, value: ScheduleEvent(id=id, type='set_variable', time_s=t, key=key, value=value)
    project.scenarios = [
        Scenario(id='B-S01', name='B-S01 额定负荷 · 24 h', events=[]),
        Scenario(id='B-S02', name='B-S02 库房 1 负荷阶跃 · 24 h', events=[set_('load-up', 21600., 'ROOM1.param.heat_input_w', 40000.),
                                                                  set_('load-down', 50400., 'ROOM1.param.heat_input_w', 0.)]),
        # Operators move targets in steps; the condensing target is lowered after the wet bulb drops (feasible).
        Scenario(id='B-S03', name='B-S03 改目标蒸发/冷凝压力 · 18 h', events=[
            *[set_(f'evap-{k}', 21600. + 1800 * k, 'controller.suction.setpoint', 110000. + 5000 * (k + 1)) for k in range(3)],
            set_('wb-down', 36000., 'EC1.param.wet_bulb_temperature_k', 293.15),
            *[set_(f'cond-{k}', 37800. + 1800 * k, 'controller.head.setpoint', 1350000. - 50000 * (k + 1)) for k in range(3)]]),
        # Weather changes gradually: 1 K every 20 min, 27 → 20 °C and back.
        Scenario(id='B-S04', name='B-S04 湿球温度变化 · 20 h', events=[
            *[set_(f'wb-down-{k}', 21600. + 1200 * k, 'EC1.param.wet_bulb_temperature_k', 299.15 - k) for k in range(7)],
            *[set_(f'wb-up-{k}', 50400. + 1200 * k, 'EC1.param.wet_bulb_temperature_k', 294.15 + k) for k in range(7)]])]
    project.id, project.name = 'cold-storage-nh3co2-v2', 'NH₃/CO₂ 两库房冷库 · 五闭环 + 上层启停'
    project.description = ('4 台单级 NH₃ 压缩机、蒸发式冷凝器、高压贮液器、节流阀、低压循环桶，复叠换热器冷凝 CO₂，CO₂ 液泵向两库冷风机供液。'
                           '输入目标蒸发/冷凝压力（PID suction/head 的设定值）即可自运行；参数为工程假设（cases/cold-storage/nh3-co2/station）。')
    return project


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
