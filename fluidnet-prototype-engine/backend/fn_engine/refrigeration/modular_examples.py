"""Build small refrigeration projects from public device contracts and explicit port connections.

No station-case IDs or control program are required. The example's design point is a
teaching assumption; topology, fluid and device parameters remain ordinary Project data.
"""
import math

from ..catalog import catalog_map
from ..models import CircuitFluid, Connection, Endpoint, FluidConfig, ModuleInstance, Position, Project, SolverOptions
from ..properties import property_service
from . import devices


def modular_room_example(room_count=1, compressor_count=1):
    """One pumped R134a circuit, 1–4 independent rooms and 1–4 parallel compressors."""
    if (type(room_count) is not int or type(compressor_count) is not int
            or not 1 <= room_count <= 4 or not 1 <= compressor_count <= 4):
        raise ValueError('单组四进四出集管示例支持 1–4 个库房和 1–4 台压缩机')
    catalog = catalog_map()
    fluid = FluidConfig(fluid='R134a', phase_policy='any')
    service = property_service(fluid)
    low, high = 248.15, 308.15
    vapor = service.state_tq(low, 1.)
    liquid = service.state_tq(high, 0.)
    pump_params = {p.id:p.default for p in catalog['refrigerant_pump'].parameters} | {
        'rated_mass_flow_kg_s':.12*room_count, 'rated_pressure_rise_pa':80000., 'speed_ratio':1.}
    pump = devices.pump_point(service, pump_params, vapor.pressure_pa)
    cooling = 5400.*room_count + pump['heat_to_fluid_w']
    mass = cooling/(vapor.enthalpy_j_kg-liquid.enthalpy_j_kg)
    displacement = mass/(compressor_count*.75*.8*vapor.density_kg_m3)
    compressor_params = {p.id:p.default for p in catalog['refrigerant_compressor'].parameters} | {
        'displacement_m3_s':displacement, 'load_ratio':.75}
    compressor = devices.compressor_point(service, compressor_params, vapor.pressure_pa, liquid.pressure_pa)
    rejection = cooling + compressor_count*compressor['shaft_power_w']
    kv = mass*3600./(.5*math.sqrt(1000.*liquid.density_kg_m3*(liquid.pressure_pa-vapor.pressure_pa)/1e5))
    # Freeze design inputs at the precision used by portable reference examples across BLAS/CPU builds.
    precision = lambda value: float(format(value, '.10g'))
    instances, connections = [], []

    def add(iid, module_id, name, x, y, **parameters):
        instances.append(ModuleInstance(id=iid, module_id=module_id, name=name, parameters=parameters,
                                        position=Position(x=x, y=y)))

    def link(a, b):
        connections.append(Connection(id=f'link-{len(connections)+1}',
            source=Endpoint(instance_id=a[0], port_id=a[1]), target=Endpoint(instance_id=b[0], port_id=b[1])))

    add('Low', 'lp_drum', '低压循环桶', 100, 320, volume_m3=.6*room_count, height_m=1.5,
        temperature_k=low, level_ratio=.4)
    add('High', 'hp_receiver', '高压贮液器', 640, 120, volume_m3=.3*room_count, height_m=1.5,
        temperature_k=high, level_ratio=.5)
    add('Condenser', 'evaporative_condenser', '蒸发式冷凝器', 460, 120,
        ua_w_k=precision(rejection/15.), wet_bulb_temperature_k=293.15, fan_power_w=300.*room_count,
        fan_ratio=1., return_gas_ratio=1.)
    add('Valve', 'expansion_valve', '供液节流阀', 640, 320, kv_m3_h=precision(kv), opening_ratio=.5)
    add('Pump', 'refrigerant_pump', '制冷剂液泵', 280, 520,
        rated_mass_flow_kg_s=.12*room_count, rated_pressure_rise_pa=80000., speed_ratio=1.)
    if compressor_count > 1:
        add('Suction', 'refrigerant_header', '吸气集管', 100, 120)
        add('Discharge', 'refrigerant_header', '排气集管', 460, 40)
        link(('Low', 'vapor'), ('Suction', 'in0'))
        link(('Discharge', 'out0'), ('Condenser', 'in0'))
    for i in range(compressor_count):
        iid = 'Compressor' if compressor_count == 1 else f'Compressor-{i+1}'
        add(iid, 'refrigerant_compressor', f'压缩机 {i+1}', 280, 120+i*110,
            displacement_m3_s=precision(displacement), load_ratio=.75)
        link(('Low', 'vapor') if compressor_count == 1 else ('Suction', f'out{i}'), (iid, 'suction'))
        link((iid, 'discharge'), ('Condenser', 'in0') if compressor_count == 1 else ('Discharge', f'in{i}'))
    link(('Condenser', 'out0'), ('High', 'in0'))
    link(('High', 'liquid'), ('Valve', 'in0'))
    link(('Valve', 'out0'), ('Low', 'in0'))
    link(('Low', 'liquid'), ('Pump', 'in0'))
    if room_count > 1:
        add('Supply', 'refrigerant_header', '供液集管', 460, 520)
        add('Return', 'refrigerant_header', '回气集管', 100, 680)
        link(('Pump', 'out0'), ('Supply', 'in0'))
        link(('Return', 'out0'), ('Low', 'in1'))
    for i in range(room_count):
        cooler = 'Cooler' if room_count == 1 else f'Cooler-{i+1}'
        room = 'Room' if room_count == 1 else f'Room-{i+1}'
        add(cooler, 'air_cooler', f'冷风机 {i+1}', 640, 520+i*140,
            ua_w_k=precision(5400./7.), fan_power_w=400., fan_ratio=1.)
        add(room, 'cold_room', f'库房 {i+1}', 820, 520+i*140, temperature_k=255.15, heat_capacity_j_k=2e6,
            ambient_temperature_k=305.15, ground_temperature_k=283.15, wall_ua_w_k=30., roof_ua_w_k=20.,
            floor_ua_w_k=10., heat_input_w=2220.)
        link(('Pump', 'out0') if room_count == 1 else ('Supply', f'out{i}'), (cooler, 'in0'))
        link((cooler, 'out0'), ('Low', 'in1') if room_count == 1 else ('Return', f'in{i}'))
        link((cooler, 'heat'), (room, 'heat'))
    used = {i.module_id for i in instances}
    return Project(id=f'modular-refrigeration-{room_count}r-{compressor_count}c',
        name=f'模块组装 · {room_count} 库房 / {compressor_count} 压缩机',
        description='由独立设备及端口连接组装的泵供液单工质制冷回路；默认 R134a，设计负荷每库 5 kW。'
                    '无固定案例控制脚本，初态为设计平衡点；模型不含管路压降、DX 过热控制或真实设备选型。',
        modules=[m for key,m in catalog.items() if key in used], instances=instances, connections=connections,
        fluid=fluid, solver=SolverOptions(dynamic_step_s=10.))


def modular_cascade_example():
    """Extend the single-room device graph with an NH3/CO2 cascade, without case-specific controls."""
    project = modular_room_example()
    catalog = catalog_map()
    ammonia = property_service(FluidConfig(fluid='Ammonia', phase_policy='any'))
    carbon_dioxide = property_service(FluidConfig(fluid='CarbonDioxide', phase_policy='any'))
    by_id = {i.id:i for i in project.instances}
    low, high, secondary = 243.15, 298.15, 248.15
    vapor = ammonia.state_tq(low, 1.)
    liquid = ammonia.state_tq(high, 0.)
    secondary_liquid = carbon_dioxide.state_tq(secondary, 0.)
    parameters = lambda iid: {p.id:p.default for p in catalog[by_id[iid].module_id].parameters} | by_id[iid].parameters
    pump = devices.pump_point(carbon_dioxide, parameters('Pump'), secondary_liquid.pressure_pa)
    transfer = 5400. + pump['heat_to_fluid_w']
    mass = transfer/(vapor.enthalpy_j_kg-liquid.enthalpy_j_kg)
    displacement = mass/(.75*.8*vapor.density_kg_m3)
    compressor = devices.compressor_point(ammonia, parameters('Compressor') | {'displacement_m3_s':displacement},
                                          vapor.pressure_pa, liquid.pressure_pa)
    kv = mass*3600./(.5*math.sqrt(1000.*liquid.density_kg_m3*(liquid.pressure_pa-vapor.pressure_pa)/1e5))
    precision = lambda value: float(format(value, '.10g'))
    by_id['Low'].parameters['temperature_k'] = low
    by_id['High'].parameters['temperature_k'] = high
    by_id['Compressor'].parameters['displacement_m3_s'] = precision(displacement)
    by_id['Valve'].parameters['kv_m3_h'] = precision(kv)
    by_id['Condenser'].parameters['ua_w_k'] = precision((transfer+compressor['shaft_power_w'])/5.)
    by_id['Pump'].name = 'CO₂ 供液泵'
    by_id['Cooler'].name = 'CO₂ 冷风机'
    project.instances.extend([
        ModuleInstance(id='Secondary', module_id='pumped_drum', name='CO₂ 储液器',
            parameters={'temperature_k':secondary, 'volume_m3':.6, 'height_m':1.5, 'level_ratio':.4},
            position=Position(x=460,y=520)),
        ModuleInstance(id='Cascade', module_id='cascade_exchanger', name='NH₃/CO₂ 复叠换热器',
            parameters={'ua_w_k':precision(transfer/(secondary-low))}, position=Position(x=280,y=320))])
    for connection in project.connections:
        if connection.source.instance_id == 'Low' and connection.source.port_id == 'liquid':
            connection.source.instance_id = 'Secondary'
        if connection.source.instance_id == 'Cooler' and connection.source.port_id == 'out0':
            connection.target = Endpoint(instance_id='Secondary', port_id='in0')
    for a, b in ((('Low','liquid'),('Cascade','evap_in')), (('Cascade','evap_out'),('Low','in1')),
                 (('Secondary','vapor'),('Cascade','cond_in')), (('Cascade','cond_out'),('Secondary','in1'))):
        project.connections.append(Connection(id=f'link-{len(project.connections)+1}',
            source=Endpoint(instance_id=a[0],port_id=a[1]), target=Endpoint(instance_id=b[0],port_id=b[1])))
    used = {i.module_id for i in project.instances}
    project.modules = [m for key,m in catalog.items() if key in used]
    project.fluid = FluidConfig(fluid='Ammonia',phase_policy='any')
    project.circuit_fluids = [
        CircuitFluid(id='primary', anchor=Endpoint(instance_id='Low',port_id='in0'), fluid=project.fluid),
        CircuitFluid(id='secondary', anchor=Endpoint(instance_id='Secondary',port_id='in0'),
            fluid=FluidConfig(fluid='CarbonDioxide',phase_policy='any'))]
    project.id, project.name = 'modular-refrigeration-cascade', '模块组装 · NH₃/CO₂ 复叠单库'
    project.description = ('由单库设备组合增加 CO₂ 储液器与复叠换热器；NH₃ -30°C 蒸发/25°C 冷凝，CO₂ -25°C 泵供液，'
                           '库温 -18°C、净负荷 5 kW。工程教学初态，无固定案例控制，非倍思鹿原工程数值复现。')
    return project


def modular_air_cooled_example():
    """Replace the single-room vessels and condenser with independently registered equipment."""
    project = modular_room_example()
    catalog = catalog_map()
    nodes = {i.id:i for i in project.instances}
    for iid, module_id in (('Low', 'horizontal_drum'), ('High', 'horizontal_receiver')):
        node = nodes[iid]
        volume = node.parameters.pop('volume_m3')
        node.parameters.pop('height_m')
        node.module_id = module_id
        node.name = catalog[module_id].name
        node.parameters.update(diameter_m=.8, length_m=volume/(math.pi*.8**2/4))
    # Same design pressure and heat rejection as the original balanced point.
    condenser = nodes['Condenser']
    conductance = condenser.parameters['ua_w_k']
    capacity = 5.*1006.
    condenser.module_id = 'air_cooled_condenser'
    condenser.name = '风冷冷凝器'
    condenser.parameters = {'ua_w_k':float(format(-capacity*math.log1p(-conductance/capacity), '.10g')),
        'rated_air_mass_flow_kg_s':5., 'air_specific_heat_j_kg_k':1006., 'air_inlet_temperature_k':293.15,
        'fan_ratio':1., 'fan_power_w':300., 'natural_ua_w_k':0.}
    used = {i.module_id for i in project.instances}
    project.modules = [m for key,m in catalog.items() if key in used]
    project.id, project.name = 'modular-air-cooled-horizontal', '设备扩展 · 卧式容器与风冷冷凝器'
    project.description = ('R134a 单库设备组合，卧式圆筒容器按直径与长度计算容积和液位；风冷冷凝器按有限空气热容量排热。'
                           '初始设计点净库负荷5kW，无自动温控；不含封头、管路压降、厂家性能图。')
    return project


def assembly_recipe(room_count=1, compressor_count=1, *, cascade=False, air_cooled=False):
    """Minimal canvas instructions; no serialized module definitions or hidden solver state."""
    if cascade and air_cooled:
        raise ValueError('请选择单独的复叠或风冷设备组装示例')
    project = modular_air_cooled_example() if air_cooled else modular_cascade_example() if cascade else modular_room_example(room_count, compressor_count)
    return {'name':project.name, 'fluid':project.fluid.model_dump(mode='json'), 'duration_s':600., 'dt_s':60.,
            **({'circuit_fluids':[c.model_dump(mode='json') for c in project.circuit_fluids]} if project.circuit_fluids else {}),
            'solver':project.solver.model_dump(mode='json'),
            'instances':[i.model_dump(mode='json', exclude_none=True) for i in project.instances],
            'connections':[c.model_dump(mode='json') for c in project.connections]}
