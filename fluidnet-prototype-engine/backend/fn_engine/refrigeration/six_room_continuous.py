"""Integrated six-room reference plant; all geometry and capacities are explicit assumptions."""
from copy import deepcopy
import math

from ..catalog import catalog_map
from ..model_types.domain import Connection, Endpoint, ModuleInstance, Position
from ..properties import property_service
from .large_cold_store_control import controlled_large_cold_store
from .large_cold_store_example import ROOMS


def continuous_large_cold_store(*, processes=True, oil=True, controls=True):
    project = controlled_large_cold_store()
    catalog = catalog_map()
    nodes = {n.id: n for n in project.instances}
    service = property_service(project.fluid)
    metadata = {'basis': 'six-room reference assumptions; no manufacturer calibration',
                'work_compressors_per_stage': 2, 'standby_compressors_per_stage': 1,
                'pumps_per_zone': {'duty': 1, 'standby': 1}, 'rooms': {}, 'pump_curves': {}}

    def add(iid, kind, name, page='plant', x=0., y=0., **parameters):
        node = ModuleInstance(id=iid, module_id=kind, name=name, page_id=page,
                              position=Position(x=x, y=y), parameters=parameters)
        project.instances.append(node); nodes[iid] = node
        return node

    def link(a, ap, b, bp):
        project.connections.append(Connection(id=f'continuous-{len(project.connections):03}',
            source=Endpoint(instance_id=a, port_id=ap), target=Endpoint(instance_id=b, port_id=bp)))

    def insert(edge, iid, kind, name, **parameters):
        target = edge.target.model_copy(deep=True)
        add(iid, kind, name, page=nodes[edge.source.instance_id].page_id, **parameters)
        edge.target = Endpoint(instance_id=iid, port_id='in0')
        link(iid, 'out0', target.instance_id, target.port_id)

    # Bottom take-offs provide physical hydrostatic suction head upstream of the filters.
    # Preserve the original M/U volumes while using the existing headed-vessel geometry.
    for iid in ('LP', 'IP'):
        vessel = nodes[iid]
        old = vessel.parameters
        diameter = 2.5
        vessel.module_id = 'headed_receiver'
        vessel.parameters = {key: old[key] for key in ('temperature_k', 'level_ratio')}
        vessel.parameters.update(diameter_m=diameter,
            length_m=(old['volume_m3'] - math.pi * diameter**3 / 6.) / (math.pi * diameter**2 / 4.),
            tap0_height_ratio=.02)
        for edge in project.connections:
            if edge.source.instance_id == iid and edge.source.port_id == 'liquid': edge.source.port_id = 'tap0'
    add('IP_INLET', 'refrigerant_header', '中压补液及湿回气汇集')
    for edge in project.connections:
        if edge.target.instance_id == 'IP' and edge.target.port_id in ('in1', 'in2'):
            edge.target = Endpoint(instance_id='IP_INLET', port_id='in' + str(int(edge.target.port_id[-1]) - 1))
    link('IP_INLET', 'out0', 'IP', 'in1')

    # Two working compressors plus one equally sized standby at each pressure stage.
    for zone in ('LT', 'HT'):
        first = nodes[zone + '_K1']
        parameters = deepcopy(first.parameters); parameters['running'] = 0.
        add(zone + '_K3', 'refrigerant_compressor', zone + ' 备用压缩机', **parameters)
        link(zone + '_SUC', 'out2', zone + '_K3', 'suction')
        link(zone + '_K3', 'discharge', zone + '_DIS', 'in2')
        controller = next(c for c in project.controllers if c.instance_id == first.id).model_copy(deep=True)
        controller.id, controller.instance_id = zone + '_capacity_3', zone + '_K3'
        project.controllers.append(controller)
        if oil:
            edge = next(e for e in project.connections if e.source.instance_id == zone + '_DIS')
            insert(edge, zone + '_OIL', 'compressor_oil_system', zone + ' 共用油分离回油冷却',
                   initial_sump_mass_kg=200., initial_separator_mass_kg=2., initial_oil_temperature_k=303.15,
                   diameter_m=.25, loss_coefficient=1., carryover_ratio=.0005, separation_efficiency=.99,
                   gas_contact_ua_w_k=100., evaporator_contact_ua_w_k=10., oil_cooler_ua_w_k=200.,
                   fouling_per_kg=.02, oil_reference_flow_kg_s=4.,
                   oil_source='六库参考输入：每压力级一套共用油系统，独立油库存；非厂家标定')

    for zone, vessel, temperature in (('LT', 'LP', 241.15), ('MT', 'IP', 265.15)):
        pump = nodes[zone + '_PUMP']
        flow = pump.parameters['rated_mass_flow_kg_s']
        rho = service.state_tq(temperature, 0.).density_kg_m3
        volume = flow / rho * 3600.
        head = 80000. / (rho * 9.80665)
        curve = [[0., head * 1.3], [volume, head], [volume * 1.5, head * .5], [volume * 2., 0.]]
        metadata['pump_curves'][zone] = curve
        pump.module_id = 'refrigerant_curve_pump'
        pump.parameters = {'running': 1., 'speed_ratio': 1., 'head_curve': curve, 'diameter_m': .10,
                           'performance_source': '六库原设计循环倍率4和80kPa压升生成的参考曲线'}
        suction = next(e for e in project.connections if e.target.instance_id == pump.id)
        original = suction.source.model_copy(deep=True)
        suction.source = Endpoint(instance_id=zone + '_PUMP_SUC', port_id='out0')
        add(zone + '_PUMP_SUC', 'refrigerant_header', zone + ' 工作备用泵吸液总管')
        add(zone + '_FILTER', 'refrigerant_strainer', zone + ' 泵前过滤器', diameter_m=.15, loss_coefficient=1.)
        link(original.instance_id, original.port_id, zone + '_FILTER', 'in0')
        link(zone + '_FILTER', 'out0', zone + '_PUMP_SUC', 'in0')
        add(zone + '_PUMP2', 'refrigerant_curve_pump', zone + ' 备用液泵', **{**deepcopy(pump.parameters), 'running': 0.})
        link(zone + '_PUMP_SUC', 'out1', zone + '_PUMP2', 'in0')
        link(zone + '_PUMP2', 'out0', zone + '_FEED', 'in1')
        for iid in (pump.id, zone + '_PUMP2'):
            edge = next(e for e in project.connections if e.source.instance_id == iid)
            insert(edge, iid + '_CHECK', 'refrigerant_check_valve', iid + ' 排液止回阀',
                   kv_m3_h=100., cracking_pressure_pa=100.)

    for number, (iid, name, temperature, _, zone, length, width, height, capacity, _) in enumerate(ROOMS):
        room = nodes[iid]
        if processes:
            room.module_id = 'logistics_cold_room'
            # Split the original effective thermal capacity; do not count stored goods twice.
            goods_mass = .45 * capacity / (1800. if zone == 'LT' else 3500.)
            room.parameters.update(heat_capacity_j_k=.55 * capacity, goods_mass_kg=goods_mass,
                goods_initial_temperature_k=temperature + 273.15, goods_ua_w_k=30000.,
                dry_air_mass_kg=length * width * height * 1.3, door_opening_ratio=0.,
                door_width_m=2.5, door_height_m=3., door_protection_efficiency=.7,
                process_source='六库参考输入：原热容按55%空气围护/45%货物分配；货物初态与库温一致')
            add(iid + '_HEAT', 'room_heat_manifold', name + ' 两台冷风机汇集', page=room.page_id)
            for e in project.connections:
                if e.target.instance_id == iid and e.target.port_id.startswith('heat'):
                    index = e.target.port_id.removeprefix('heat')
                    e.target = Endpoint(instance_id=iid + '_HEAT', port_id='in' + index)
            link(iid + '_HEAT', 'out0', iid, 'heat')
        metadata['rooms'][iid] = {'zone': zone, 'target_k': temperature + 273.15,
            'base_heat_input_w': room.parameters['heat_input_w'], 'branch_length_m': 20. + 5. * number}
        for index in (1, 2):
            cooler = nodes[f'{iid}_AC{index}']
            cooler.module_id = 'frost_hotgas_cooler' if processes else 'network_air_cooler'
            cooler.parameters.update(diameter_m=.08 if zone == 'LT' else .065, loss_coefficient=2.)
            if processes:
                original_ua = cooler.parameters['ua_w_k']
                evap = 241.15 if zone == 'LT' else 265.15
                cooler.parameters.update(ua_w_k=original_ua * 1.35, refrigerant_contact_ua_w_k=original_ua * 5.,
                    initial_surface_temperature_k=evap + 1., metal_heat_capacity_j_k=300000.,
                    initial_frost_mass_kg=2., surface_area_m2=300., dry_air_flow_kg_s=35.,
                    hot_gas_kv_m3_h=.8, hot_gas_ua_w_k=6000., predrain_duration_s=60.,
                    defrost_duration_s=900., drip_duration_s=120., recool_duration_s=60.)
            for direction in ('SUPPLY', 'RETURN'):
                edge = next(e for e in project.connections if
                    direction == 'SUPPLY' and e.target.instance_id == cooler.id and e.target.port_id == 'in0'
                    or direction == 'RETURN' and e.source.instance_id == cooler.id and e.source.port_id == 'out0')
                insert(edge, cooler.id + '_' + direction, 'refrigerant_network_pipe', name + f' {index} ' + direction,
                       length_m=20. + 5. * number + 2. * (index - 1),
                       diameter_m=(.04 if direction == 'SUPPLY' else .10) if zone == 'LT' else
                                  (.032 if direction == 'SUPPLY' else .08), loss_coefficient=2.)
            edge = next(e for e in project.connections if e.target.instance_id == cooler.id and e.target.port_id == 'in0')
            insert(edge, cooler.id + '_VALVE', 'refrigerant_network_valve', name + f' {index} 供液阀',
                   kv_m3_h=12. if zone == 'LT' else 8., opening_ratio=1.)

    if processes:
        # One actual high-pressure vapor source, condensate returned to the middle-pressure vessel.
        add('HOT_MAIN', 'refrigerant_header', '高压融霜热气总管')
        add('HOT_DRAIN', 'refrigerant_header', '融霜凝液回中压总管')
        link('HP', 'vapor', 'HOT_MAIN', 'in0'); link('HOT_DRAIN', 'out0', 'IP_INLET', 'in2')
        for zone, main_index in (('LT', 0), ('MT', 1)):
            add(zone + '_HOT', 'refrigerant_header', zone + ' 热气分配')
            add(zone + '_DRAIN', 'refrigerant_header', zone + ' 融霜回液汇集')
            link('HOT_MAIN', 'out' + str(main_index), zone + '_HOT', 'in0')
            link(zone + '_DRAIN', 'out0', 'HOT_DRAIN', 'in' + str(main_index))
            for room_index, row in enumerate(r for r in ROOMS if r[4] == zone):
                iid, name = row[:2]
                add(iid + '_HOT', 'refrigerant_header', name + ' 热气', page=nodes[iid].page_id)
                add(iid + '_DRAIN', 'refrigerant_header', name + ' 凝液', page=nodes[iid].page_id)
                link(zone + '_HOT', 'out' + str(room_index), iid + '_HOT', 'in0')
                link(iid + '_DRAIN', 'out0', zone + '_DRAIN', 'in' + str(room_index))
                for index in (1, 2):
                    link(iid + '_HOT', 'out' + str(index - 1), f'{iid}_AC{index}', 'hot_in')
                    link(f'{iid}_AC{index}', 'hot_out', iid + '_DRAIN', 'in' + str(index - 1))

    project.id, project.name = 'large-cold-store-continuous', '六库房冷库 · 全设备持续仿真'
    project.description = ('六库双温区氨两级系统：真实图式供回液、工作/备用机泵、两级共用油系统、'
                           '货物热湿、十二台霜层冷风机及热气融霜。参数为自定义工程假设；HEM与集中库存模型。')
    project.solver.dynamic_step_s = 30.
    project.events, project.scenarios = [], []
    project.modules = [catalog[key].model_copy(deep=True) for key in dict.fromkeys(n.module_id for n in project.instances)]
    # Draw the two cooler branches in flow order, with one thermal inventory per room.
    for number, row in enumerate(ROOMS):
        iid = row[0]
        offset = 950. * (number % 2)
        positions = {iid: (480., 430.), iid + '_HEAT': (640., 430.),
            iid + '_FEED': (80., 210.), iid + '_RETURN': (780., 210.),
            iid + '_HOT': (220., 40.), iid + '_DRAIN': (640., 40.)}
        for index, y in ((1, 130.), (2, 290.)):
            prefix = f'{iid}_AC{index}'
            positions.update({prefix + '_SUPPLY': (220., y), prefix + '_VALVE': (360., y),
                              prefix: (500., y), prefix + '_RETURN': (640., y)})
        for key, (x, y) in positions.items():
            if key in nodes: nodes[key].position = Position(x=x + offset, y=y)
    plant_positions = {'HP': (1200., 200.), 'IP': (100., 200.), 'LP': (100., 620.),
        'COND': (1020., 200.), 'HP_VALVE': (1020., 400.), 'IP_INLET': (300., 400.),
        'IP_LIQ': (100., 420.), 'LT_VALVE': (100., 520.),
        'HOT_MAIN': (1200., 40.), 'LT_HOT': (1600., 40.), 'MT_HOT': (2000., 40.),
        'HOT_DRAIN': (1200., 900.), 'LT_DRAIN': (1600., 900.), 'MT_DRAIN': (2000., 900.)}
    for zone, y in (('HT', 200.), ('LT', 620.)):
        plant_positions.update({zone + '_SUC': (300., y), zone + '_DIS': (660., y), zone + '_OIL': (840., y)})
        for index, dy in ((1, -120.), (2, 0.), (3, 120.)):
            plant_positions[f'{zone}_K{index}'] = (480., y + dy)
    for zone, y in (('MT', 200.), ('LT', 620.)):
        plant_positions.update({zone + '_FILTER': (1400., y), zone + '_PUMP_SUC': (1560., y),
            zone + '_PUMP': (1720., y - 50.), zone + '_PUMP2': (1720., y + 110.),
            zone + '_PUMP_CHECK': (1880., y - 50.), zone + '_PUMP2_CHECK': (1880., y + 110.),
            zone + '_FEED': (2040., y), zone + '_RETURN': (2200., y)})
    for key, (x, y) in plant_positions.items():
        if key in nodes: nodes[key].position = Position(x=x, y=y)
    if controls:
        from .six_room_operation import configure_operation
        configure_operation(project, metadata, processes=processes)
    return project, metadata
