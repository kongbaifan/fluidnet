"""Accepted-state supervision and a repeating operating day for the six-room reference plant."""
from ..model_types.domain import ControlScript, Scenario


SUPERVISOR = '''
def initialize(ctx):
    for name in GROUPS:
        ctx.state[name + '_active'] = False
        ctx.state[name + '_since'] = -MIN_OFF_S
        ctx.state[name + '_fault_since'] = None
        ctx.state[name + '_failed_start'] = False
        ctx.state[name + '_starts'] = 0

def step(ctx, dt_s):
    for name, group in GROUPS.items():
        fault = any(ctx.read(i + '.param.running') < .5 or ctx.read(i + '.mass_flow_kg_s') < .001
                    for i in group['duty'])
        key = name + '_fault_since'
        if not fault:
            ctx.state[key] = None
        elif ctx.state[key] is None:
            ctx.state[key] = ctx.time_s
        demanded = fault and ctx.time_s - ctx.state[key] >= CONFIRM_S
        active, since = ctx.state[name + '_active'], ctx.state[name + '_since']
        if active and not ctx.state[name + '_failed_start'] and ctx.time_s - since >= CONFIRM_S and ctx.read(group['standby'] + '.mass_flow_kg_s') < .001:
            ctx.state[name + '_failed_start'] = True
            ctx.log(name + ': standby failed, restart inhibited')
        permitted = (ctx.read('HP.state.pressure_pa') < MAX_PRESSURE_PA
                     and ctx.read(group['vessel'] + '.state.level_ratio') > MIN_LEVEL
                     and not ctx.state[name + '_failed_start'])
        next_active = active
        if not permitted:
            next_active = False
        elif demanded and not active and ctx.time_s - since >= MIN_OFF_S:
            next_active = True
        elif not demanded and active and ctx.time_s - since >= MIN_RUN_S:
            next_active = False
        if next_active != active:
            ctx.state[name + '_since'] = ctx.time_s
            if next_active: ctx.state[name + '_starts'] += 1
            ctx.log(name + (': standby started' if next_active else ': standby stopped'))
        ctx.state[name + '_active'] = next_active
        ctx.write(group['standby'] + '.param.running', float(next_active))
    if COOLERS:
        slot = int((ctx.time_s % DAY_S - 14400.) // 1200.)
        for index, cooler in enumerate(COOLERS):
            requested = index == slot and (ctx.time_s % DAY_S - 14400.) % 1200. < SAMPLE_S
            ctx.write(cooler + '.param.defrost_request', float(requested))

def finalize(ctx):
    pass
'''

DAY = '''
def initialize(ctx):
    ctx.state['day'] = 0
    ctx.state['phase'] = ''

def step(ctx, dt_s):
    t = ctx.time_s % 86400.
    ctx.state['day'] = int(ctx.time_s // 86400.)
    phase = ('load' if 3600. <= t < 7200. else 'cooler-stop' if 10000. <= t < 10600.
             else 'pump-fault' if 36000. <= t < 36600. else 'compressor-fault' if 43200. <= t < 43800.
             else 'normal')
    if phase != ctx.state['phase']:
        ctx.log('operating day: ' + phase)
        ctx.state['phase'] = phase
    ctx.write('F01.param.heat_input_w', BASE_LOAD + (100000. if phase == 'load' else 0.))
    ctx.write('F01_AC1.param.running', float(phase != 'cooler-stop'))
    ctx.write('F01_AC1_VALVE.param.opening_ratio', float(phase != 'cooler-stop'))
    ctx.write('LT_PUMP.param.running', float(phase != 'pump-fault'))
    ctx.write('LT_K1.param.running', float(phase != 'compressor-fault'))
    for index, room in enumerate(ROOMS):
        start = 1800. + index * 1800.
        ctx.write(room + '.param.door_opening_ratio', .2 if start <= t < start + 300. else 0.)

def finalize(ctx):
    pass
'''


def configure_operation(project, metadata, *, processes=True):
    groups = {
        'low_compressors': {'duty': ['LT_K1', 'LT_K2'], 'standby': 'LT_K3', 'vessel': 'LP'},
        'high_compressors': {'duty': ['HT_K1', 'HT_K2'], 'standby': 'HT_K3', 'vessel': 'IP'},
        'low_pumps': {'duty': ['LT_PUMP'], 'standby': 'LT_PUMP2', 'vessel': 'LP'},
        'middle_pumps': {'duty': ['MT_PUMP'], 'standby': 'MT_PUMP2', 'vessel': 'IP'},
    }
    coolers = [f'{room}_AC{i}' for i in (1, 2) for room in metadata['rooms']] if processes else []
    inputs = ['HP.state.pressure_pa', 'LP.state.level_ratio', 'IP.state.level_ratio']
    outputs = []
    for group in groups.values():
        inputs += [iid + suffix for iid in [*group['duty'], group['standby']]
                   for suffix in ('.param.running', '.mass_flow_kg_s')]
        outputs.append(group['standby'] + '.param.running')
    outputs += [c + '.param.defrost_request' for c in coolers]
    prefix = f'GROUPS = {groups!r}\nCOOLERS = {coolers!r}\n'
    prefix += 'CONFIRM_S=30.\nMIN_RUN_S=120.\nMIN_OFF_S=120.\nMAX_PRESSURE_PA=2200000.\nMIN_LEVEL=.08\nDAY_S=86400.\nSAMPLE_S=30.\n'
    project.control_scripts = [ControlScript(id='plant_supervisor', enabled=True, sample_s=30.,
        source=prefix + SUPERVISOR, inputs=inputs, outputs=outputs)]
    day_rooms = list(metadata['rooms']) if processes else []
    source = f'BASE_LOAD={metadata["rooms"]["F01"]["base_heat_input_w"]!r}\nROOMS={day_rooms!r}\n' + DAY
    project.control_scripts.append(ControlScript(id='operating_day', enabled=True, sample_s=30., source=source,
        inputs=[], outputs=['F01.param.heat_input_w', 'F01_AC1.param.running', 'F01_AC1_VALVE.param.opening_ratio',
                           'LT_PUMP.param.running', 'LT_K1.param.running'] +
                          [r + '.param.door_opening_ratio' for r in day_rooms]))
    project.scenarios = [Scenario(id='operating-day', name='循环运行日：开门、增载、错峰融霜、机泵停运恢复')]
    if processes:
        project.scenarios.append(Scenario(id='warm-goods', name='同一工程：冷冻库1有10吨待冻货物', overrides={
            'F01': {'goods_mass_kg': 10000., 'goods_initial_temperature_k': 278.15, 'goods_ua_w_k': 10000.}}))
    metadata['operation'] = {'control_sample_s': 30., 'confirm_s': 30., 'min_standby_run_s': 120.,
        'min_standby_off_s': 120., 'day_s': 86400., 'defrost_order': coolers,
        'threshold_basis': 'reference simulation only; explicit configurable source, not certified machine protection'}
