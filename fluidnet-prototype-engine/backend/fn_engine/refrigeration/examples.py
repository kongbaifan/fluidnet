"""Product A1 seed; canonical parameters mirror the versioned case assumptions."""
from ..catalog import catalog_map, thermal_catalog
from ..models import (CircuitFluid, Connection, Endpoint, FluidConfig, ModuleInstance, PIDController, Project,
                      SolverOptions)


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
