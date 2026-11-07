"""A six-room ammonia warehouse assembled solely from existing public equipment.

Dimensions and loads are declared modelling assumptions, not a manufacturer's
design or a copy of a published plant. See docs/LARGE_COLD_STORE_DESIGN.md.
"""
import math

from ..catalog import catalog_map
from ..model_types.base import FluidConfig
from ..model_types.domain import Connection, Endpoint, ModuleInstance, Position, Project, Scenario, SolverOptions
from ..properties import property_service
from . import devices


ROOMS = (
    ('F01', '冷冻库 1', -24., 250000., 'LT', 40., 30., 12., 7e8, 3000.),
    ('F02', '冷冻库 2', -22., 250000., 'LT', 40., 30., 12., 7e8, 3000.),
    ('F03', '冷冻库 3', -20., 250000., 'LT', 40., 30., 12., 7e8, 3000.),
    ('F04', '冷冻库 4', -18., 250000., 'LT', 40., 30., 12., 7e8, 3000.),
    ('C01', '冷藏库 1', 2., 150000., 'MT', 30., 30., 10., 1.2e9, 2000.),
    ('C02', '冷藏库 2', 4., 150000., 'MT', 30., 30., 10., 1.2e9, 2000.),
)


def build_large_cold_store():
    catalog = catalog_map()
    fluid = FluidConfig(fluid='Ammonia', phase_policy='any')
    service = property_service(fluid)
    defaults = lambda key: {parameter.id: parameter.default for parameter in catalog[key].parameters}
    precision = lambda value: float(format(value, '.10g'))
    low, middle, high = 241.15, 265.15, 308.15
    lv, ml, mv, hl = (service.state_tq(temperature, quality) for temperature, quality in
                      ((low, 1.), (middle, 0.), (middle, 1.), (high, 0.)))
    gross = {zone: sum(room[3] + 2 * room[9] for room in ROOMS if room[4] == zone) for zone in ('LT', 'MT')}
    pump_flow, pump_heat = {}, {}
    for zone, temperature in (('LT', low), ('MT', middle)):
        liquid, vapor = service.state_tq(temperature, 0.), service.state_tq(temperature, 1.)
        pump_flow[zone] = precision(4 * gross[zone] / (vapor.enthalpy_j_kg - liquid.enthalpy_j_kg))
        point = devices.pump_point(service, defaults('refrigerant_pump') | {
            'rated_mass_flow_kg_s': pump_flow[zone], 'rated_pressure_rise_pa': 80000., 'speed_ratio': 1.}, liquid.pressure_pa)
        pump_heat[zone] = point['heat_to_fluid_w']
    low_mass = (gross['LT'] + pump_heat['LT']) / (lv.enthalpy_j_kg - ml.enthalpy_j_kg)
    compressor = defaults('refrigerant_compressor') | {'load_ratio': .75}
    low_displacement = precision(low_mass / (2 * .75 * compressor['volumetric_efficiency'] * lv.density_kg_m3))
    low_point = devices.compressor_point(service, compressor | {'displacement_m3_s': low_displacement}, lv.pressure_pa, mv.pressure_pa)
    # Middle balance includes low-stage discharge, flash gas and the chilled rooms.
    high_mass = (low_mass * (low_point['discharge_enthalpy_j_kg'] - ml.enthalpy_j_kg)
                 + gross['MT'] + pump_heat['MT']) / (mv.enthalpy_j_kg - hl.enthalpy_j_kg)
    high_displacement = precision(high_mass / (2 * .75 * compressor['volumetric_efficiency'] * mv.density_kg_m3))
    high_point = devices.compressor_point(service, compressor | {'displacement_m3_s': high_displacement}, mv.pressure_pa, hl.pressure_pa)
    rejection = sum(gross.values()) + sum(pump_heat.values()) + 2 * (low_point['shaft_power_w'] + high_point['shaft_power_w'])

    def kv(mass, liquid, downstream):
        return precision(mass * 3600 / (.5 * math.sqrt(1000 * liquid.density_kg_m3 * (liquid.pressure_pa - downstream) / 1e5)))

    nodes, edges = [], []

    def add(iid, kind, name, x, y, page='plant', **params):
        nodes.append(ModuleInstance(id=iid, module_id=kind, name=name, page_id=page,
                                    position=Position(x=x, y=y), parameters=params))

    def link(left, right):
        a, ap = left.split(':'); b, bp = right.split(':')
        edges.append(Connection(id=f'pipe-{len(edges) + 1:03}', source=Endpoint(instance_id=a, port_id=ap),
                                target=Endpoint(instance_id=b, port_id=bp)))

    add('HP', 'hp_receiver', '高压贮液器', 1150, 160, volume_m3=30., height_m=3., temperature_k=high, level_ratio=.5)
    add('IP', 'lp_drum_multi', '中压中冷兼冷藏供液桶', 680, 400, volume_m3=25., height_m=3., temperature_k=middle, level_ratio=.4)
    add('LP', 'lp_drum', '低压冷冻循环桶', 160, 570, volume_m3=35., height_m=3., temperature_k=low, level_ratio=.4)
    add('COND', 'evaporative_condenser', '集中蒸发式冷凝器', 930, 160, ua_w_k=precision(rejection / 11.),
        wet_bulb_temperature_k=297.15, fan_power_w=22000., fan_ratio=1., return_gas_ratio=1.)
    for zone, displacement, x, y in (('LT', low_displacement, 360, 400), ('HT', high_displacement, 720, 160)):
        add(zone + '_SUC', 'refrigerant_header', zone + ' 吸气集管', x - 150, y)
        add(zone + '_DIS', 'refrigerant_header', zone + ' 排气集管', x + 150, y)
        for index in range(2):
            iid = zone + '_K' + str(index + 1)
            add(iid, 'refrigerant_compressor', ('低级' if zone == 'LT' else '高级') + f'压缩机 {index + 1}', x, y + index * 130,
                displacement_m3_s=displacement, load_ratio=.75)
            link(f'{zone}_SUC:out{index}', iid + ':suction')
            link(iid + ':discharge', f'{zone}_DIS:in{index}')
    link('LP:vapor', 'LT_SUC:in0'); link('LT_DIS:out0', 'IP:in0')
    link('IP:vapor', 'HT_SUC:in0'); link('HT_DIS:out0', 'COND:in0'); link('COND:out0', 'HP:in0')
    add('HP_VALVE', 'expansion_valve', '高压至中压补液阀', 1150, 400, kv_m3_h=kv(high_mass, hl, mv.pressure_pa), opening_ratio=.5)
    add('LT_VALVE', 'expansion_valve', '中压至低压补液阀', 400, 570, kv_m3_h=kv(low_mass, ml, lv.pressure_pa), opening_ratio=.5)
    add('IP_LIQ', 'refrigerant_header', '中压液体分流', 680, 570)
    link('HP:liquid', 'HP_VALVE:in0'); link('HP_VALVE:out0', 'IP:in1')
    link('IP:liquid', 'IP_LIQ:in0'); link('IP_LIQ:out0', 'LT_VALVE:in0'); link('LT_VALVE:out0', 'LP:in0')
    for zone, vessel, y in (('LT', 'LP', 790), ('MT', 'IP', 1000)):
        add(zone + '_PUMP', 'refrigerant_pump', zone + ' 液泵', 400, y,
            rated_mass_flow_kg_s=pump_flow[zone], rated_pressure_rise_pa=80000., speed_ratio=1.)
        add(zone + '_FEED', 'refrigerant_header', zone + ' 供液总管', 680, y)
        add(zone + '_RETURN', 'refrigerant_header', zone + ' 湿回气总管', 930, y)
        link('LP:liquid' if zone == 'LT' else 'IP_LIQ:out1', zone + '_PUMP:in0')
        link(zone + '_PUMP:out0', zone + '_FEED:in0')
        link(zone + '_RETURN:out0', vessel + (':in1' if zone == 'LT' else ':in2'))
    positions = {'LT': 0, 'MT': 0}
    room_summary = []
    for number, (iid, name, temperature, net, zone, length, width, height, capacity, fan) in enumerate(ROOMS):
        idx = positions[zone]; positions[zone] += 1
        page = 'frozen-a' if number < 2 else 'frozen-b' if number < 4 else 'chilled'
        y = 190 + (number % 2) * 340
        wall, roof, floor = .22 * 2 * (length + width) * height, .18 * length * width, .22 * length * width
        envelope = (wall + roof) * (32 - temperature) + floor * (10 - temperature)
        internal = net - envelope
        assert internal > 0
        add(iid, 'cold_room_multi', name, 1000, y + 70, page, temperature_k=temperature + 273.15,
            heat_capacity_j_k=capacity, ambient_temperature_k=305.15, ground_temperature_k=283.15,
            wall_ua_w_k=wall, roof_ua_w_k=roof, floor_ua_w_k=floor, heat_input_w=internal)
        add(iid + '_FEED', 'refrigerant_header', name + ' 供液', 190, y + 70, page)
        add(iid + '_RETURN', 'refrigerant_header', name + ' 回气', 790, y + 70, page)
        link(f'{zone}_FEED:out{idx}', iid + '_FEED:in0')
        link(iid + '_RETURN:out0', f'{zone}_RETURN:in{idx}')
        evap = low if zone == 'LT' else middle
        for index in range(2):
            cooler = iid + '_AC' + str(index + 1)
            add(cooler, 'air_cooler', name + f' 冷风机 {index + 1}', 480, y + index * 150, page,
                ua_w_k=precision((net / 2 + fan) / (temperature + 273.15 - evap)), fan_power_w=fan,
                fan_ratio=1., supply_valve_ratio=1.)
            link(iid + f'_FEED:out{index}', cooler + ':in0')
            link(cooler + ':out0', iid + f'_RETURN:in{index}')
            link(cooler + ':heat', iid + f':heat{index}')
        room_summary.append({'id': iid, 'name': name, 'temperature_c': temperature, 'net_load_w': net,
            'envelope_load_w': envelope, 'additional_heat_w': internal, 'volume_m3': length * width * height,
            'heat_capacity_j_k': capacity, 'cooler_count': 2, 'zone': zone})
    used = {node.module_id for node in nodes}
    scenarios = [Scenario(id='baseline', name='基准 · 六库设计工作点'),
        Scenario(id='f01-extra-load', name='冷冻库 1 增加 100 kW 附加热负荷',
                 overrides={'F01': {'heat_input_w': room_summary[0]['additional_heat_w'] + 100000.}}),
        Scenario(id='f01-cooler-off', name='冷冻库 1 一台冷风机停供',
                 overrides={'F01_AC1': {'running': 0., 'supply_valve_ratio': 0.}})]
    project = Project(id='large-cold-store-six-room', name='大型多库房冷库 · 六库/双温区/氨两级泵供液',
        description='公开工业冷库资料启发的自定示范工程：6库、12冷风机、1.3MW净库负荷。全部设备和连接显式。'
        '常效率压缩机、理想集管、集总库房；非厂家选型，不含油路、两相管压降、热气融霜或自动调度。',
        modules=[definition.model_copy(deep=True) for key, definition in catalog.items() if key in used],
        instances=nodes, connections=edges, fluid=fluid, solver=SolverOptions(dynamic_step_s=10.), scenarios=scenarios)
    metadata = {'basis': 'engineering assumptions, not an as-built or calibrated plant', 'rooms': room_summary,
        'net_room_load_w': sum(room[3] for room in ROOMS), 'gross_evaporator_load_w': gross,
        'circulation_ratio': 4., 'pump_flow_kg_s': pump_flow, 'pump_heat_w': pump_heat,
        'low_stage_mass_flow_kg_s': low_mass, 'high_stage_mass_flow_kg_s': high_mass,
        'heat_rejection_w': rejection, 'instances': len(nodes), 'connections': len(edges),
        'pressure_levels_c': {'LP': -32., 'IP': -8., 'HP': 35.}, 'total_volume_m3': sum(r['volume_m3'] for r in room_summary)}
    return project, metadata


def assembly_recipe():
    project, _ = build_large_cold_store()
    return {'name': project.name, 'fluid': project.fluid.model_dump(mode='json'), 'duration_s': 600., 'dt_s': 10.,
        'solver': project.solver.model_dump(mode='json'),
        'instances': [node.model_dump(mode='json', exclude_none=True) for node in project.instances],
        'connections': [edge.model_dump(mode='json') for edge in project.connections]}
