"""Sampled duty/standby operation with explicit devices and accepted script state."""
from ..catalog import catalog_map
from ..model_types.domain import Connection, ControlScript, Endpoint, ModuleInstance, Scenario, ScheduleEvent
from .modular_examples import modular_room_example


SOURCE = '''
PAIRS = {'pump': ['Pump', 'BackupPump'], 'compressor': ['Compressor-1', 'Compressor-2']}
CONFIRM_S = 0.2
MIN_FLOW_KG_S = 0.001
MAX_HIGH_PRESSURE_PA = 2500000.
MIN_LIQUID_LEVEL = 0.1

def initialize(ctx):
    for group in PAIRS:
        ctx.state[group + '_active'] = 0
        ctx.state[group + '_switches'] = 0
        ctx.state[group + '_since'] = 0.
    ctx.state['tripped'] = False

def step(ctx, dt_s):
    if (ctx.read('High.state.pressure_pa') > MAX_HIGH_PRESSURE_PA
            or ctx.read('Low.state.level_ratio') < MIN_LIQUID_LEVEL):
        ctx.state['tripped'] = True
    for group, pair in PAIRS.items():
        active = ctx.state[group + '_active']
        current = pair[active]
        failed = (ctx.read(current + '.param.running') < .5
                  or ctx.read(current + '.mass_flow_kg_s') < MIN_FLOW_KG_S)
        if not ctx.state['tripped'] and failed and ctx.time_s >= ctx.state[group + '_since'] + CONFIRM_S:
            if ctx.state[group + '_switches']:
                ctx.state['tripped'] = True
            else:
                active = 1 - active
                ctx.state[group + '_active'] = active
                ctx.state[group + '_switches'] += 1
                ctx.state[group + '_since'] = ctx.time_s
                ctx.log(group + ' standby selected')
        for index, instance in enumerate(pair):
            ctx.write(instance + '.param.running', float(index == active and not ctx.state['tripped']))
    # A later group's trip also stops an earlier group's pending output.
    if ctx.state['tripped']:
        for pair in PAIRS.values():
            for instance in pair: ctx.write(instance + '.param.running', 0.)

def finalize(ctx):
    pass
'''


def standby_example():
    project = modular_room_example(room_count=2, compressor_count=2)
    catalog = catalog_map()
    for instance in project.instances:
        if instance.id.startswith('Compressor-'):
            instance.parameters['displacement_m3_s'] *= 2.
            instance.parameters['running'] = float(instance.id == 'Compressor-1')
    pump = next(i for i in project.instances if i.id == 'Pump')
    pump.parameters['running'] = 1.
    backup = pump.model_copy(deep=True, update={'id': 'BackupPump', 'name': '备用液泵'})
    backup.parameters['running'] = 0.
    project.instances.extend([backup, ModuleInstance(id='PumpSuction', module_id='refrigerant_header', name='液泵吸液集管')])
    edge = next(e for e in project.connections if e.target.instance_id == 'Pump')
    edge.target = Endpoint(instance_id='PumpSuction', port_id='in0')
    for number, (source, target) in enumerate([
        (('PumpSuction', 'out0'), ('Pump', 'in0')),
        (('PumpSuction', 'out1'), ('BackupPump', 'in0')),
        (('BackupPump', 'out0'), ('Supply', 'in1')),
    ]):
        project.connections.append(Connection(id=f'standby-{number}',
            source=Endpoint(instance_id=source[0], port_id=source[1]),
            target=Endpoint(instance_id=target[0], port_id=target[1])))
    machines = ['Pump', 'BackupPump', 'Compressor-1', 'Compressor-2']
    project.control_scripts = [ControlScript(id='standby', enabled=True, sample_s=.1, source=SOURCE,
        inputs=['High.state.pressure_pa', 'Low.state.level_ratio'] +
               [f'{iid}.{name}' for iid in machines for name in ('param.running', 'mass_flow_kg_s')],
        outputs=[f'{iid}.param.running' for iid in machines])]
    project.scenarios = [Scenario(id='duty-failure', name='工作机泵在0.4秒停机，备用自动切换', events=[
        ScheduleEvent(id=f'fail-{iid}', type='set_variable', time_s=.4, key=f'{iid}.param.{parameter}', value=0.)
        for iid, parameter in (('Pump', 'speed_ratio'), ('Compressor-1', 'load_ratio'))])]
    project.modules = [m for key, m in catalog.items() if key in {i.module_id for i in project.instances}]
    project.solver.dynamic_step_s = .1
    project.id, project.name = 'refrigeration-standby', '冷库工作机泵与备用切换'
    project.description = ('参考控制：实际流量/运行反馈触发一次备用切换，确认期后备用失败则锁停；'
                           '低液位或高压锁停。阈值及0.2秒确认时间仅用于短时验收，需按实际机组选型配置。')
    return project
