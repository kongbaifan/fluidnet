"""A complete air handler, chilled-water loop and condenser-water loop.

Pressure references seed liquid temperatures but supply no heat to the closed loops.
All parameters are reproducible teaching assumptions, not calibrated equipment data.
"""
from .catalog import catalog_map
from .models import CircuitFluid, Connection, Endpoint, FluidConfig, ModuleInstance


def chiller_air_example():
    from .air_examples import air_example
    project = air_example('ahu-room').model_copy(deep=True)
    project.id, project.name = 'chiller-air-loop', '冷水机组与房间风水联算'
    catalog = catalog_map()
    project.modules = [m for m in project.modules if m.id != 'cooling_coil']
    project.modules.extend(catalog[k] for k in ('water_coil', 'water_chiller', 'pump', 'valve', 'cooling_tower_moist'))
    coil = next(i for i in project.instances if i.id == 'Coil')
    coil.module_id, coil.name, coil.parameters = 'water_coil', '冷水盘管', {}
    # No prescribed reheat/humidification: the room, outside air and water coil determine the load.
    next(i for i in project.instances if i.id == 'Reheat').parameters['heat_input_w'] = 0.
    next(i for i in project.instances if i.id == 'Humidifier').parameters['moisture_addition_kg_kg'] = 0.
    next(i for i in project.instances if i.id == 'Room').parameters.update(sensible_load_w=5000., additional_heat_capacity_j_k=1e6)

    def add(iid, kind, **params):
        project.instances.append(ModuleInstance(id=iid, module_id=kind, name={
            'Chiller':'水冷冷水机组', 'ChilledPump':'冷冻水泵', 'CoolingPump':'冷却水泵',
            'WaterValve':'盘管水阀', 'Tower':'冷却塔'}.get(iid, iid), parameters=params))

    add('Chiller', 'water_chiller')
    add('ChilledPump', 'pump', head_curve=[[0., 6.], [6., 4.], [12., 0.]])
    add('CoolingPump', 'pump', head_curve=[[0., 5.], [8., 3.], [16., 0.]])
    add('WaterValve', 'valve', kv_m3_h=8., opening_ratio=.8)
    add('Tower', 'cooling_tower_moist', air_volume_flow_m3_s=3.)
    add('ChilledRef', 'source', pressure_pa=200000., temperature_k=285.15)
    add('CoolingRef', 'source', pressure_pa=200000., temperature_k=303.15)
    add('ChilledJoin', 'junction')
    add('CoolingJoin', 'junction')
    links = [('ChilledRef:out0','ChilledJoin:in0'), ('ChilledJoin:out0','ChilledPump:in0'),
             ('ChilledPump:out0','Chiller:in0'), ('Chiller:out0','WaterValve:in0'),
             ('WaterValve:out0','Coil:in1'), ('Coil:out1','ChilledJoin:out1'),
             ('CoolingRef:out0','CoolingJoin:in0'), ('CoolingJoin:out0','CoolingPump:in0'),
             ('CoolingPump:out0','Chiller:in1'), ('Chiller:out1','Tower:in0'), ('Tower:out0','CoolingJoin:out1')]
    def endpoint(key):
        iid, port = key.split(':')
        return Endpoint(instance_id=iid, port_id=port)
    project.connections.extend(Connection(id=f'water{i}', source=endpoint(a), target=endpoint(b)) for i,(a,b) in enumerate(links))
    project.circuit_fluids = [CircuitFluid(id=key, anchor=Endpoint(instance_id='Chiller', port_id=port),
                                         fluid=FluidConfig(fluid='Water', phase_policy='liquid'))
                              for key, port in (('chilled-water','in0'), ('condenser-water','in1'))]
    project.solver.moist_air_options.max_iterations = 400
    return project
