"""Two independent pumped air coolers connected to a single physical room heat capacity."""
from ..catalog import catalog_map
from ..model_types.domain import Connection, Endpoint, ModuleInstance
from .modular_examples import modular_room_example


def multi_cooler_example():
    project=modular_room_example()
    catalog=catalog_map(); nodes={i.id:i for i in project.instances}
    nodes['Room'].module_id='cold_room_multi'
    nodes['Cooler'].parameters['ua_w_k']/=2.
    nodes['Cooler'].parameters['fan_power_w']/=2.
    second=nodes['Cooler'].model_copy(deep=True,update={'id':'CoolerB','name':'冷风机 B'})
    project.instances.extend([second,ModuleInstance(id='Supply',module_id='refrigerant_header',name='供液分配'),
        ModuleInstance(id='Return',module_id='refrigerant_header',name='回液汇集')])
    project.connections=[c for c in project.connections if not (c.source.instance_id in ('Pump','Cooler'))]
    links=[(('Pump','out0'),('Supply','in0')), (('Return','out0'),('Low','in1'))]
    for index,iid in enumerate(('Cooler','CoolerB')):
        links.extend([(('Supply',f'out{index}'),(iid,'in0')),((iid,'out0'),('Return',f'in{index}')),
                      ((iid,'heat'),('Room',f'heat{index}'))])
    for index,(a,b) in enumerate(links):
        project.connections.append(Connection(id=f'multi-{index}',source=Endpoint(instance_id=a[0],port_id=a[1]),
                                              target=Endpoint(instance_id=b[0],port_id=b[1])))
    project.modules=[m for key,m in catalog.items() if key in {i.module_id for i in project.instances}]
    project.id,project.name='modular-multiple-coolers','模块组装 · 同库双冷风机'
    project.description='两个独立泵供液冷风机连接同一个库房热容，各自净冷量相加；不复制库房储热，无隐藏控制脚本。'
    return project
