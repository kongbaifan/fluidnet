"""Open flash intercooling assembled from the ordinary three-pressure-level devices.

Only the example's design inputs are calculated here. Vessel mass/energy, stream
enthalpies and both compressor stages are evaluated by the generic station solver.
"""
import math

from ..catalog import catalog_map
from ..model_types.domain import Connection, Endpoint, ModuleInstance, Position
from ..properties import property_service
from . import devices
from .modular_examples import modular_room_example


def modular_two_stage_example():
    """R134a pumped single room with a saturated, completely open flash intercooler."""
    project = modular_room_example()
    catalog = catalog_map()
    service = property_service(project.fluid)
    nodes = {instance.id: instance for instance in project.instances}
    low, middle, high = 248.15, 268.15, 308.15
    vapor_low = service.state_tq(low, 1.)
    liquid_middle, vapor_middle = service.state_tq(middle, 0.), service.state_tq(middle, 1.)
    liquid_high = service.state_tq(high, 0.)
    defaults = lambda module_id: {p.id: p.default for p in catalog[module_id].parameters}
    pump = devices.pump_point(service, defaults('refrigerant_pump') | nodes['Pump'].parameters,
                              vapor_low.pressure_pa)
    cooling = 5400. + pump['heat_to_fluid_w']
    low_mass = cooling / (vapor_low.enthalpy_j_kg - liquid_middle.enthalpy_j_kg)
    compressor = defaults('refrigerant_compressor') | {'load_ratio': .75}
    low_displacement = low_mass / (.75 * compressor['volumetric_efficiency'] * vapor_low.density_kg_m3)
    low_point = devices.compressor_point(service, compressor | {'displacement_m3_s': low_displacement},
                                          vapor_low.pressure_pa, vapor_middle.pressure_pa)
    # Middle-vessel balance: mL*h2L + mH*hfH = mL*hfM + mH*hgM.
    high_mass = low_mass * (low_point['discharge_enthalpy_j_kg'] - liquid_middle.enthalpy_j_kg) / (
        vapor_middle.enthalpy_j_kg - liquid_high.enthalpy_j_kg)
    high_displacement = high_mass / (.75 * compressor['volumetric_efficiency'] * vapor_middle.density_kg_m3)
    high_point = devices.compressor_point(service, compressor | {'displacement_m3_s': high_displacement},
                                           vapor_middle.pressure_pa, liquid_high.pressure_pa)
    rejection = cooling + low_point['shaft_power_w'] + high_point['shaft_power_w']

    def valve_kv(mass, liquid, outlet_pressure):
        return mass * 3600. / (.5 * math.sqrt(
            1000. * liquid.density_kg_m3 * (liquid.pressure_pa - outlet_pressure) / 1e5))

    precision = lambda value: float(format(value, '.10g'))
    nodes['Compressor'].name = '低级压缩机'
    nodes['Compressor'].parameters['displacement_m3_s'] = precision(low_displacement)
    nodes['Compressor'].position = Position(x=280, y=320)
    nodes['Valve'].name = '中压至低压供液阀'
    nodes['Valve'].parameters['kv_m3_h'] = precision(valve_kv(low_mass, liquid_middle, vapor_low.pressure_pa))
    nodes['Condenser'].parameters['ua_w_k'] = precision(rejection / 15.)
    nodes['Condenser'].position = Position(x=820, y=80)
    nodes['High'].position = Position(x=1000, y=80)
    project.instances.extend([
        ModuleInstance(id='Intermediate', module_id='lp_drum_multi', name='开式闪蒸中冷器',
            parameters={'volume_m3': .4, 'height_m': 1.5, 'temperature_k': middle, 'level_ratio': .4},
            position=Position(x=460, y=320)),
        ModuleInstance(id='HighCompressor', module_id='refrigerant_compressor', name='高级压缩机',
            parameters={'displacement_m3_s': precision(high_displacement), 'load_ratio': .75},
            position=Position(x=640, y=80)),
        ModuleInstance(id='HighValve', module_id='expansion_valve', name='高压至中压节流阀',
            parameters={'kv_m3_h': precision(valve_kv(high_mass, liquid_high, vapor_middle.pressure_pa)),
                        'opening_ratio': .5}, position=Position(x=820, y=320))])
    for connection in project.connections:
        if connection.source.instance_id == 'Compressor' and connection.source.port_id == 'discharge':
            connection.target = Endpoint(instance_id='Intermediate', port_id='in0')
        elif connection.source.instance_id == 'High' and connection.source.port_id == 'liquid':
            connection.target = Endpoint(instance_id='HighValve', port_id='in0')
    for source, target in ((('HighValve', 'out0'), ('Intermediate', 'in1')),
                           (('Intermediate', 'liquid'), ('Valve', 'in0')),
                           (('Intermediate', 'vapor'), ('HighCompressor', 'suction')),
                           (('HighCompressor', 'discharge'), ('Condenser', 'in0'))):
        project.connections.append(Connection(id=f'link-{len(project.connections)+1}',
            source=Endpoint(instance_id=source[0], port_id=source[1]),
            target=Endpoint(instance_id=target[0], port_id=target[1])))
    used = {instance.module_id for instance in project.instances}
    project.modules = [module for key, module in catalog.items() if key in used]
    project.id, project.name = 'modular-two-stage-intercooling', '设备组合 · 两级压缩与开式闪蒸中冷'
    project.description = ('R134a 泵供液单库；低/中/高压初始饱和温度 -25/-5/35°C。'
        '中压饱和容器混合低级排气与高压节流来液，液相供低压阀、饱和气供高级压缩机。'
        '三个容器的质量与内能共同推进；设计点净库负荷 5 kW，无自动联锁、管路压降或厂家性能标定。')
    return project


def two_stage_recipe():
    """Canvas instructions with explicit equipment and links, without private solver data."""
    project = modular_two_stage_example()
    return {'name': project.name, 'fluid': project.fluid.model_dump(mode='json'), 'duration_s': 600., 'dt_s': 60.,
            'solver': project.solver.model_dump(mode='json'),
            'instances': [i.model_dump(mode='json', exclude_none=True) for i in project.instances],
            'connections': [c.model_dump(mode='json') for c in project.connections]}
