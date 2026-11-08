"""Portable cold-room process reference: declared custom inputs, no manufacturer claim."""
from ..catalog import catalog_map
from ..model_types.domain import ModuleInstance, Connection, Endpoint
from .network_examples import network_example


def process_example(hotgas=False, oil=False):
    project = network_example()
    by_id = {i.id: i for i in project.instances}
    by_id['Room-1'].module_id = 'logistics_cold_room'
    by_id['Room-1'].parameters['door_opening_ratio'] = .05
    by_id['Cooler-1'].module_id = 'frost_hotgas_cooler'
    def link(iid, a, b):
        project.connections.append(Connection(id=iid, source=Endpoint(instance_id=a[0], port_id=a[1]),
                                              target=Endpoint(instance_id=b[0], port_id=b[1])))
    if hotgas:
        by_id['Low'].module_id = 'lp_drum_multi'
        link('hot-supply', ('High', 'vapor'), ('Cooler-1', 'hot_in'))
        link('hot-drain', ('Cooler-1', 'hot_out'), ('Low', 'in2'))
    if oil:
        project.instances.append(ModuleInstance(id='Oil', module_id='compressor_oil_system', name='独立油分离回油'))
        connection = next(e for e in project.connections if e.source.instance_id == 'Compressor')
        target = connection.target.model_copy(deep=True)
        connection.target = Endpoint(instance_id='Oil', port_id='in0')
        project.connections.append(Connection(id='oil-out', source=Endpoint(instance_id='Oil', port_id='out0'), target=target))
    catalog = catalog_map()
    project.modules = [catalog[k] for k in sorted({i.module_id for i in project.instances})]
    project.id = 'cold-room-processes'
    project.name = '冷库热湿、冻结、霜层与油路参考工况'
    project.description = '自定义参考：均相制冷管网、独立货物焓、水分与盘管霜水库存；热气/油路可选。所有参数可编辑，不代表厂家设备。'
    return project
