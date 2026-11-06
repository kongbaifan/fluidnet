"""A real suction line and external subcooler alter the actual compressor/valve enthalpies."""
from ..catalog import catalog_map
from ..models import ModuleInstance, Connection, Endpoint
from .modular_examples import modular_room_example


def stream_example(subcooling=False):
    project=modular_room_example(); catalog=catalog_map()
    compressor=next(i for i in project.instances if i.id=='Compressor')
    compressor.module_id='enthalpy_compressor'
    line=ModuleInstance(id='SuctionLine',module_id='refrigerant_line',name='有热损吸气管',
        parameters={'length_m':3.,'diameter_m':.04,'heat_loss_ua_w_k':2.,'ambient_temperature_k':293.15})
    project.instances.append(line)
    edge=next(c for c in project.connections if c.target.instance_id=='Compressor')
    edge.target=Endpoint(instance_id='SuctionLine',port_id='in0')
    project.connections.append(Connection(id='suction-line',source=Endpoint(instance_id='SuctionLine',port_id='out0'),
        target=Endpoint(instance_id='Compressor',port_id='suction')))
    if subcooling:
        valve=next(i for i in project.instances if i.id=='Valve');valve.module_id='enthalpy_valve'
        project.instances.append(ModuleInstance(id='Subcooler',module_id='refrigerant_subcooler',name='外部冷源过冷器',
            parameters={'length_m':0.,'heat_loss_ua_w_k':20.,'ambient_temperature_k':293.15}))
        edge=next(c for c in project.connections if c.target.instance_id=='Valve');edge.target=Endpoint(instance_id='Subcooler',port_id='in0')
        project.connections.append(Connection(id='subcooler-line',source=Endpoint(instance_id='Subcooler',port_id='out0'),target=Endpoint(instance_id='Valve',port_id='in0')))
    project.modules=[m for key,m in catalog.items() if key in {i.module_id for i in project.instances}]
    project.id='modular-stream-subcooling' if subcooling else 'modular-stream-line'
    project.name='有焓流股 · 吸气管与外部过冷' if subcooling else '有焓流股 · 真实吸气管'
    project.description='串联单相局部压降/热交换改变真实入口焓，源容器和目标容器M/U闭合；非通用两相管网，无自动温控。'
    return project


def recuperator_example():
    project=stream_example(True);catalog=catalog_map()
    hx=next(i for i in project.instances if i.id=='Subcooler')
    hx.id,hx.module_id,hx.name,hx.parameters='Recuperator','refrigerant_recuperator','吸液回热器',{'ua_w_k':4.}
    for edge in project.connections:
        for endpoint in (edge.source,edge.target):
            if endpoint.instance_id=='Subcooler':
                endpoint.instance_id='Recuperator';endpoint.port_id='hot_in' if endpoint.port_id=='in0' else 'hot_out'
    edge=next(c for c in project.connections if c.target.instance_id=='Compressor')
    edge.target=Endpoint(instance_id='Recuperator',port_id='cold_in')
    project.connections.append(Connection(id='recuperator-suction',source=Endpoint(instance_id='Recuperator',port_id='cold_out'),
        target=Endpoint(instance_id='Compressor',port_id='suction')))
    project.modules=[m for key,m in catalog.items() if key in {i.module_id for i in project.instances}]
    project.id,project.name='modular-stream-recuperator','有焓流股 · 吸液回热器'
    return project
