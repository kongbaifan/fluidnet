"""Self-defined, traceable graph-network cases with unequal supply/return branches."""
from ..catalog import catalog_map
from ..model_types.domain import Connection, Endpoint, ModuleInstance
from .modular_examples import modular_room_example


def network_example(with_inventory=False):
    project = modular_room_example(room_count=2)
    catalog = catalog_map()
    pump = next(i for i in project.instances if i.id == 'Pump')
    pump.module_id = 'refrigerant_curve_pump'
    pump.parameters = {'running': 1., 'speed_ratio': 1.,
                       'head_curve': [[0., 15.], [.3, 12.], [.6, 7.], [.9, 0.]]}
    for i in range(2):
        cooler = next(device for device in project.instances if device.id == f'Cooler-{i+1}')
        cooler.module_id = 'network_air_cooler'
        for direction in ('Supply', 'Return'):
            pipe_id = f'{direction}Pipe-{i+1}'
            project.instances.append(ModuleInstance(id=pipe_id, module_id='refrigerant_network_pipe', name=f'{direction}管 {i+1}',
                parameters={'length_m': (3. if direction == 'Supply' else 5.) * (1. if i == 0 else 4.),
                            'diameter_m': .018 if direction == 'Supply' else .035}))
            edge = next(edge for edge in project.connections if
                (direction == 'Supply' and edge.target.instance_id == cooler.id and edge.target.port_id == 'in0') or
                (direction == 'Return' and edge.source.instance_id == cooler.id and edge.source.port_id == 'out0'))
            target = edge.target.model_copy(deep=True)
            edge.target = Endpoint(instance_id=pipe_id, port_id='in0')
            project.connections.append(Connection(id=f'{pipe_id}-out',
                source=Endpoint(instance_id=pipe_id, port_id='out0'), target=target))
    if with_inventory:
        project.instances.append(ModuleInstance(id='PipeInventory', module_id='refrigerant_inventory_cell', name='回气管持液库存',
            parameters={'volume_m3': .03, 'temperature_k': 248.15, 'level_ratio': .8}))
        project.instances.append(ModuleInstance(id='InventoryOutlet', module_id='refrigerant_network_pipe', name='库存出口阻力',
            parameters={'length_m': 2., 'diameter_m': .035}))
        edge = next(e for e in project.connections if e.source.instance_id == 'ReturnPipe-2')
        target = edge.target.model_copy(deep=True)
        edge.target = Endpoint(instance_id='PipeInventory', port_id='in0')
        project.connections.extend([
            Connection(id='inventory-out', source=Endpoint(instance_id='PipeInventory', port_id='bulk'),
                       target=Endpoint(instance_id='InventoryOutlet', port_id='in0')),
            Connection(id='inventory-return', source=Endpoint(instance_id='InventoryOutlet', port_id='out0'), target=target),
        ])
    project.modules = [m for key, m in catalog.items() if key in {i.module_id for i in project.instances}]
    project.id = 'refrigerant-network-inventory' if with_inventory else 'refrigerant-network-parallel'
    project.name = '图式供回液管网与持液' if with_inventory else '图式供回液管网与泵工作点'
    project.description = '自定义两库参考工程：两支路长度不同，实际分流由曲线泵和供回液阻力联立决定；HEM均相平衡，系数为参考输入。'
    project.solver.dynamic_step_s = .1
    return project
