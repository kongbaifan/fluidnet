"""Small refrigeration/secondary-loop development cases in canonical units.

The secondary circuit is closed: its pressure source provides static pressure,
not a prescribed return temperature or cooling load. A warm pipe represents an
ambient heat load; all heat removed by the immersed coil enters the LP vessel.
"""
from ..catalog import catalog_map
from ..models import (
    CircuitFluid, Connection, Endpoint, FluidConfig, ModuleInstance, Position,
    Project, Scenario, SolverOptions, ThermalCoupling,
)


def _link(identifier, source, target):
    return Connection(id=identifier, source=Endpoint(instance_id=source[0], port_id=source[1]),
                      target=Endpoint(instance_id=target[0], port_id=target[1]))


def thermal_coupling_example(coolant: str = 'INCOMP::MEG[0.3]', *, topology: str = 'single') -> Project:
    """Single-stage NH3 plant cooling a pumped water/30% glycol load loop.

These are bounded development assumptions, not a field-calibrated equipment
selection. No active controller or schedule is required, so the same project
can be used for a true equilibrium solve and dynamic perturbation studies.
The independent two-loop case fixes its fluids to water and 30% glycol;
coolant selects the fluid for the single-loop and parallel-branch cases.
"""
    if topology not in {'single', 'parallel', 'independent'}:
        raise ValueError('topology must be single, parallel or independent')
    if topology == 'independent':
        coolant = 'Water'
    instances = [
        ModuleInstance(id='LP1', module_id='lp_drum', name='氨侧低压容器',
            position=Position(x=140, y=120), parameters={'volume_m3':2., 'temperature_k':278.15, 'level_ratio':.4}),
        ModuleInstance(id='K1', module_id='refrigerant_compressor', name='氨压缩机',
            position=Position(x=350, y=70), parameters={'displacement_m3_s':.005, 'load_ratio':.8}),
        ModuleInstance(id='EC1', module_id='evaporative_condenser', name='冷凝器',
            position=Position(x=570, y=70), parameters={'ua_w_k':1100., 'wet_bulb_temperature_k':293.15,
                                                     'fan_power_w':120., 'fan_ratio':1., 'return_gas_ratio':1.}),
        ModuleInstance(id='HP1', module_id='hp_receiver', name='氨侧高压容器',
            position=Position(x=770, y=150), parameters={'volume_m3':2., 'temperature_k':308.15, 'level_ratio':.4}),
        ModuleInstance(id='EV1', module_id='expansion_valve', name='节流阀',
            position=Position(x=450, y=250), parameters={'kv_m3_h':.045, 'opening_ratio':.5}),
        ModuleInstance(id='WB1', module_id='source', name='二次侧静压参考',
            position=Position(x=130, y=440), parameters={'pressure_pa':250000., 'temperature_k':293.15}),
        ModuleInstance(id='WN1', module_id='junction', name='二次侧连接节点', position=Position(x=290, y=440)),
        ModuleInstance(id='WP1', module_id='pump', name='二次侧循环泵', position=Position(x=430, y=410),
            parameters={'head_curve':[[0.,3.],[10.,0.]], 'speed_ratio':1., 'efficiency_ratio':.75}),
        ModuleInstance(id='WL1', module_id='pipe', name='环境热负载', position=Position(x=640, y=410),
            parameters={'length_m':20., 'diameter_m':.04, 'roughness_m':.00001,
                        'heat_loss_ua_w_k':1000., 'ambient_temperature_k':303.15}),
        ModuleInstance(id='WV1', module_id='valve', name='二次侧调节阀', position=Position(x=790, y=490),
            parameters={'kv_m3_h':16., 'opening_ratio':.8}),
        ModuleInstance(id='HX_W', module_id='pipe', name='低压容器浸没盘管', position=Position(x=530, y=600),
            parameters={'length_m':2., 'diameter_m':.04, 'roughness_m':.00001,
                        'heat_loss_ua_w_k':0., 'thermal_cells':0}),
    ]
    used = {instance.module_id for instance in instances}
    catalog = catalog_map()
    project = Project(id='thermal-coupling-nh3-glycol-v1', name='氨制冷站与水／乙二醇回路联算',
        description='单级氨站与闭式二次回路通过浸没盘管交换热量；二次侧温度由环境热负载、泵热和制冷侧共同决定。'
                    '仅作为开发参考，未作设备厂家或现场标定。',
        fluid=FluidConfig(fluid=coolant, phase_policy='liquid'),
        modules=[catalog[key] for key in catalog if key in used], instances=instances,
        connections=[
            _link('r1', ('LP1','vapor'), ('K1','suction')),
            _link('r2', ('K1','discharge'), ('EC1','in0')),
            _link('r3', ('EC1','out0'), ('HP1','in0')),
            _link('r4', ('HP1','liquid'), ('EV1','in0')),
            _link('r5', ('EV1','out0'), ('LP1','in0')),
            _link('w0', ('WB1','out0'), ('WN1','in0')),
            _link('w1', ('WN1','out0'), ('WP1','in0')),
            _link('w2', ('WP1','out0'), ('WL1','in0')),
            _link('w3', ('WL1','out0'), ('WV1','in0')),
            _link('w4', ('WV1','out0'), ('HX_W','in0')),
            _link('w5', ('HX_W','out0'), ('WN1','out1')),
        ],
        circuit_fluids=[
            CircuitFluid(id='nh3', anchor=Endpoint(instance_id='LP1',port_id='in0'),
                         fluid=FluidConfig(fluid='Ammonia')),
            CircuitFluid(id='secondary', anchor=Endpoint(instance_id='WB1',port_id='out0'),
                         fluid=FluidConfig(fluid=coolant, phase_policy='liquid')),
        ],
        thermal_couplings=[ThermalCoupling(id='HX1', fluid_instance_id='HX_W', fluid_channel_id='ch0',
                                          refrigerant_vessel_id='LP1', ua_w_k=1800.)],
        scenarios=[
            Scenario(id='rated', name='基础环境 30°C'),
            Scenario(id='warm_load', name='环境热负载升高至 40°C', overrides={'WL1':{'ambient_temperature_k':313.15}}),
            Scenario(id='reduced_flow', name='二次侧阀门开度减至 40%', overrides={'WV1':{'opening_ratio':.4}}),
        ], solver=SolverOptions(dynamic_step_s=1., hydraulic_method='auto'))
    if topology != 'single':
        _add_second_coil(project, topology)
    return _design_point(project)


def _add_second_coil(project, topology):
    """Extend the algebraic liquid network without connecting its mass to NH3."""
    original = {instance.id: instance for instance in project.instances}
    rename = {'WB1': 'WB2', 'WN1': 'WN2', 'WP1': 'WP2', 'WL1': 'WL2', 'WV1': 'WV2', 'HX_W': 'HX_W2'}
    copy_ids = set(rename) if topology == 'independent' else {'WL1', 'WV1', 'HX_W'}
    for identifier in rename:
        if identifier not in copy_ids:
            continue
        instance = original[identifier].model_copy(deep=True)
        instance.id = rename[identifier]
        instance.name = original[identifier].name + ' · 第二路'
        instance.position.y += 300
        project.instances.append(instance)
    instances = {instance.id: instance for instance in project.instances}
    instances['WL2'].parameters['heat_loss_ua_w_k'] = 800.
    instances['WV2'].parameters.update(kv_m3_h=12., opening_ratio=.7)

    if topology == 'independent':
        second_edges = []
        for edge in project.connections:
            if edge.source.instance_id in rename and edge.target.instance_id in rename:
                second_edges.append(_link('second_' + edge.id,
                    (rename[edge.source.instance_id], edge.source.port_id),
                    (rename[edge.target.instance_id], edge.target.port_id)))
        project.connections.extend(second_edges)
        project.circuit_fluids.append(CircuitFluid(id='secondary2', anchor=Endpoint(instance_id='WB2', port_id='out0'),
            fluid=FluidConfig(fluid='INCOMP::MEG[0.3]', phase_policy='liquid')))
        project.name = '双盘管 · 水与乙二醇独立回路'
    else:
        project.instances.extend([
            ModuleInstance(id='WS1', module_id='junction', name='二次侧分流节点', position=Position(x=530, y=430)),
            ModuleInstance(id='WM1', module_id='junction', name='二次侧汇流节点', position=Position(x=280, y=720)),
        ])
        project.connections = [edge for edge in project.connections if edge.id not in {'w2', 'w5'}]
        project.connections.extend([
            _link('split_in', ('WP1', 'out0'), ('WS1', 'in0')),
            _link('branch1_in', ('WS1', 'out0'), ('WL1', 'in0')),
            _link('branch2_in', ('WS1', 'out1'), ('WL2', 'in0')),
            _link('branch2_valve', ('WL2', 'out0'), ('WV2', 'in0')),
            _link('branch2_coil', ('WV2', 'out0'), ('HX_W2', 'in0')),
            _link('branch1_return', ('HX_W', 'out0'), ('WM1', 'in0')),
            _link('branch2_return', ('HX_W2', 'out0'), ('WM1', 'out1')),
            _link('merged_return', ('WM1', 'out0'), ('WN1', 'out1')),
        ])
        project.name = '双盘管 · 同回路双支路'
    project.id = f'thermal-coupling-dual-{topology}-v1'
    project.description = ('两根不同液体通路的浸没盘管向同一氨侧低压容器传热；液体侧无储量。'
                           '按两路总热负载配平制冷站，仅作为开发参考，未经厂家或现场标定。')
    project.thermal_couplings.append(ThermalCoupling(id='HX2', fluid_instance_id='HX_W2',
                                                    refrigerant_vessel_id='LP1', ua_w_k=1400.))
    project.scenarios.append(Scenario(id='second_load', name='第二路热负载升高至 40°C',
                                     overrides={'WL2': {'ambient_temperature_k': 313.15}}))


def _design_point(project):
    """Size the three fixed devices at the declared 5/35 °C saturation point.

    With both vessel temperatures fixed, the liquid-loop load determines the
    refrigerant flow. Compressor displacement, valve Kv and condenser UA must
    agree with that flow; arbitrary independent values need not admit a steady
    equilibrium. Sizing happens only while creating this example, never in a run.
    """
    from ..compiler import compile_project
    from .coupling import CoupledStationSession

    session = CoupledStationSession(compile_project(project), 1., 1.)
    try:
        result = session._current()
        service = session.services['LP1']
        low, high = result['vessels']['LP1'], result['vessels']['HP1']
        vapor = service.state_pq(low.pressure_pa, 1.)
        liquid = service.state_pq(high.pressure_pa, 0.)
        heat = sum(coil['heat_w'] for coil in result['couplings'].values())
        mass = heat / (vapor.enthalpy_j_kg - liquid.enthalpy_j_kg)
        compressor = result['devices']['K1']
        ratio = mass / compressor['mass_flow_kg_s']
        instances = {instance.id: instance for instance in project.instances}
        instances['K1'].parameters['displacement_m3_s'] *= ratio
        instances['EV1'].parameters['kv_m3_h'] *= mass / result['devices']['EV1']['mass_flow_kg_s']
        instances['EC1'].parameters['ua_w_k'] *= ((heat + ratio * compressor['shaft_power_w'])
                                               / result['devices']['EC1']['heat_rejection_w'])
        return project
    finally:
        session.close()
