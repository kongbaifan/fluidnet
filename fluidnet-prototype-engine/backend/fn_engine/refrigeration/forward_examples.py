"""Portable S5/S6 examples built exclusively from declared module ports and parameters."""
from ..catalog import catalog_map
from ..model_types.domain import Connection, Endpoint, ModuleInstance


def link(p,a,b):
    p.connections.append(Connection(id='added-'+str(len(p.connections)),source=Endpoint(instance_id=a[0],port_id=a[1]),target=Endpoint(instance_id=b[0],port_id=b[1])))


def finish(p,name):
    catalog=catalog_map();used={i.module_id for i in p.instances};p.modules=[catalog[k] for k in catalog if k in used]
    p.id=name;p.name=name
    for index,i in enumerate(p.instances):i.position.x=100+(index%5)*200;i.position.y=100+(index//5)*180
    return p


def manifold_example(count=6):
    if not 1<=count<=16:raise ValueError('reference supports 1..16 coolers')
    from .modular_examples import modular_room_example
    p=modular_room_example();base=next(i for i in p.instances if i.id=='Cooler');p.instances.remove(base)
    p.connections=[c for c in p.connections if c.source.instance_id not in ('Pump','Cooler') and c.target.instance_id!='Cooler']
    p.instances.extend([ModuleInstance(id='HeatRoot',name='HeatRoot',module_id='room_heat_manifold'),ModuleInstance(id='Feed',name='Feed',module_id='refrigerant_header'),ModuleInstance(id='Drain',name='Drain',module_id='refrigerant_header')])
    link(p,('Pump','out0'),('Feed','in0'));link(p,('Drain','out0'),('Low','in1'));link(p,('HeatRoot','out0'),('Room','heat'))
    for group in range((count+3)//4):
        # Chained four-port hydraulic headers give an explicit fanout without multiple connections per port.
        supply='Feed'+str(group);drain='Drain'+str(group);heat='Heat'+str(group)
        if group>=4:raise ValueError('reference topology supports up to16 coolers')
        p.instances.extend([ModuleInstance(id=supply,name=supply,module_id='refrigerant_header'),ModuleInstance(id=drain,name=drain,module_id='refrigerant_header'),ModuleInstance(id=heat,name=heat,module_id='room_heat_manifold')])
        link(p,('Feed',f'out{group}'),(supply,'in0'));link(p,(drain,'out0'),('Drain',f'in{group}'));link(p,(heat,'out0'),('HeatRoot',f'in{group}'))
        for local in range(min(4,count-group*4)):
            iid='Cooler'+str(group*4+local)
            node=base.model_copy(deep=True,update={'id':iid,'name':iid});node.parameters['ua_w_k']/=count;node.parameters['fan_power_w']/=count;p.instances.append(node)
            link(p,(supply,f'out{local}'),(iid,'in0'));link(p,(iid,'out0'),(drain,f'in{local}'));link(p,(iid,'heat'),(heat,f'in{local}'))
    return finish(p,'thermal-manifold-'+str(count))


def headed_example():
    from .modular_examples import modular_room_example
    p=modular_room_example();high=next(i for i in p.instances if i.id=='High')
    high.module_id='headed_receiver';high.parameters={'diameter_m':1.,'length_m':2.,'temperature_k':308.15,'level_ratio':.62}
    for c in p.connections:
        if c.source.instance_id=='High' and c.source.port_id=='liquid':c.source.port_id='tap0'
    return finish(p,'headed-tank-tap')


def tube_bundle_example():
    from .stream_example import stream_example
    p=stream_example(True);tube=next(i for i in p.instances if i.id=='Subcooler')
    tube.module_id='immersed_tube_bundle';tube.parameters={'length_m':0.,'heat_loss_ua_w_k':20.}
    p.instances.append(ModuleInstance(id='Shell',name='Shell',module_id='hp_receiver',parameters={'temperature_k':283.15,'volume_m3':.5,'level_ratio':.5}))
    link(p,('Shell','liquid'),('Subcooler','shell_in'));link(p,('Subcooler','shell_out'),('Shell','in0'))
    return finish(p,'held-shell-tube')


def coil_intercooler_example():
    from .two_stage_example import modular_two_stage_example
    p=modular_two_stage_example();valve=next(i for i in p.instances if i.id=='HighValve');valve.module_id='enthalpy_valve'
    p.instances.append(ModuleInstance(id='Coil',name='Coil',module_id='immersed_tube_bundle',parameters={'length_m':0.,'heat_loss_ua_w_k':5.}))
    for c in p.connections:
        if c.target.instance_id=='HighValve':c.target=Endpoint(instance_id='Coil',port_id='in0')
    link(p,('Coil','out0'),('HighValve','in0'));link(p,('Intermediate','liquid'),('Coil','shell_in'))
    # The intermediate liquid supply is shared with the low valve using an explicit header.
    old=next(c for c in p.connections if c.source.instance_id=='Intermediate' and c.target.instance_id=='Valve')
    p.instances.append(ModuleInstance(id='LiquidHeader',name='LiquidHeader',module_id='refrigerant_header'))
    old.source=Endpoint(instance_id='LiquidHeader',port_id='out0')
    shell=next(c for c in p.connections if c.target.instance_id=='Coil' and c.target.port_id=='shell_in')
    shell.source=Endpoint(instance_id='LiquidHeader',port_id='out1')
    link(p,('Intermediate','liquid'),('LiquidHeader','in0'));link(p,('Coil','shell_out'),('Intermediate','in2'))
    return finish(p,'finite-ua-coil-intercooler')


def coupled_buffer_example():
    from .coupling_examples import thermal_coupling_example
    p=thermal_coupling_example();p.coupling_mode='storage_v1'
    p.instances.append(ModuleInstance(id='Buffer',name='Buffer',module_id='closed_buffer_tank',parameters={'mass_kg':100.,'temperature_k':293.15}))
    edge=next(c for c in p.connections if c.source.instance_id=='HX_W');target=edge.target;edge.target=Endpoint(instance_id='Buffer',port_id='in0')
    link(p,('Buffer','out0'),(target.instance_id,target.port_id))
    return finish(p,'coupled-buffer-storage')
