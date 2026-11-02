"""Basic HVAC equipment cases with explicit pressure references and public meters."""
from pathlib import Path

from .catalog import catalog_map
from .models import ControlScript, MeasurementSpec, ModuleInstance, Position, Project, Scenario
from .packages import load_module_package

ROOT = Path(__file__).resolve().parents[2]
HVAC_EXAMPLES = {
    'hvac-water-balance': '暖通基础 · 两支路水力平衡',
    'hvac-three-way-mixing': '暖通基础 · 三通阀混流',
    'hvac-pump-switch': '暖通基础 · 工作泵与备用泵切换',
    'hvac-basic-plant': '暖通基础 · 双盘管冷水机房',
}


def meter(identifier, label, kind, sources, quantity, canonical, display=None, scale=1., offset=0.):
    return MeasurementSpec(id=identifier, label=label, kind=kind, sources=sources,
        unit={'quantity':quantity, 'canonical_unit':canonical, 'display_unit':display or canonical,
              'display_scale':scale, 'display_offset':offset})


def hvac_example(name):
    if name not in HVAC_EXAMPLES:
        raise KeyError(name)
    catalog = catalog_map()
    if name == 'hvac-basic-plant':
        from .chiller_examples import chiller_air_example
        project = chiller_air_example()
        project.id, project.name = name, HVAC_EXAMPLES[name]
    else:
        project = Project(id=name, name=HVAC_EXAMPLES[name], fluid={'phase_policy':'liquid'},
                          solver={'thermal':False, 'module_cache':True, 'module_mixed_jacobian':True})
    project.description = '基础设备组网与控制演示；尺寸、曲线和负荷为可复现教学假设。'

    def add(iid, kind, **params):
        if kind not in {m.id for m in project.modules}:
            project.modules.append(catalog[kind] if kind in catalog else load_module_package(ROOT/'modules'/kind))
        project.instances.append(ModuleInstance(id=iid, module_id=kind, name=iid, parameters=params))

    def link(a, b):
        def endpoint(key):
            iid, port = key.split(':')
            return {'instance_id':iid, 'port_id':port}
        from .models import Connection
        project.connections.append(Connection(id='hvac'+str(len(project.connections)), source=endpoint(a), target=endpoint(b)))

    def path(*ports):
        for a, b in zip(ports[::2], ports[1::2]):
            link(a, b)

    if name == 'hvac-three-way-mixing':
        add('Hot', 'source', pressure_pa=250000., temperature_k=313.15)
        add('Cold', 'source', pressure_pa=250000., temperature_k=283.15)
        add('Return', 'source', pressure_pa=200000., temperature_k=293.15)
        add('ThreeWay', 'water_three_way_valve', Valve_opening_ratio=.5)
        path('Hot:out0','ThreeWay:a', 'Cold:out0','ThreeWay:b', 'ThreeWay:common','Return:out0')
        project.solver.thermal = True
        project.solver.property_coupling = 'node'
        project.measurements = [meter('mixed-temperature', '混合水温', 'value', ['ThreeWay.common.temperature_k'],
                                      'temperature','K','°C',offset=-273.15)]
        project.scenarios = [Scenario(id=key, name=label, overrides={'ThreeWay':{'Valve_opening_ratio':opening}})
                            for key,label,opening in [('cold','冷路全开',0.),('mixed','两路各半',.5),('hot','热路全开',1.)]]
    elif name == 'hvac-pump-switch':
        add('Ref', 'source', pressure_pa=200000.)
        add('ReturnJoin', 'junction')
        add('Suction', 'water_header_2')
        add('Discharge', 'water_collector_2')
        add('Load', 'pipe', length_m=25., diameter_m=.05)
        path('Ref:out0','ReturnJoin:in0', 'ReturnJoin:out0','Suction:common',
             'Discharge:common','Load:in0', 'Load:out0','ReturnJoin:out1')
        for index in (1,2):
            add('Pump'+str(index), 'hvac_water_pump', running=1. if index==1 else 0.)
            add('Check'+str(index), 'hvac_check_valve')
            path('Suction:branch'+str(index),'Pump'+str(index)+':in0',
                 'Pump'+str(index)+':out0','Check'+str(index)+':in0',
                 'Check'+str(index)+':out0','Discharge:branch'+str(index))
        project.measurements = [meter('pump-dp','供回水压差','difference',
            ['Discharge.common.pressure_pa','Suction.common.pressure_pa'],'pressure','Pa','kPa',1000.)]
        project.control_scripts = [ControlScript(id='duty-standby', enabled=True, sample_s=1.,
            outputs=['Pump1.param.running','Pump2.param.running'],
            source='''# 两台泵同时切换；止回阀由真实压差决定导通。
def initialize(ctx):
    ctx.state['switched'] = False
def step(ctx, dt):
    if ctx.time_s >= 5 and not ctx.state['switched']:
        ctx.write('Pump2.param.running', 1.)
        ctx.write('Pump1.param.running', 0.)
        ctx.state['switched'] = True
def finalize(ctx):
    pass
''')]
    else:
        plant = name == 'hvac-basic-plant'
        if not plant and name == 'hvac-water-balance':
            # 体积流量测点按“质量流量 ÷ 端口密度”计算，端口物性只在热力层打开时进入运行帧。
            project.solver.thermal = True
        if plant:
            # Keep the air, chilled-water and condenser-water circuits independent.
            project.connections = [c for c in project.connections if c.id not in ('water3','water4','water5')]
            project.instances = [i for i in project.instances if i.id != 'WaterValve']
            # Two stages share the original coil's total UA rather than doubling it.
            next(i for i in project.instances if i.id == 'Coil').parameters.update(
                air_side_ua_w_k=2000., water_side_ua_w_k=4000.)
            add('Coil2', 'water_coil', air_side_ua_w_k=2000., water_side_ua_w_k=4000.)
            edge = next(c for c in project.connections if c.source.instance_id=='Coil' and c.source.port_id=='out0')
            old_target = edge.target.model_copy(deep=True)
            edge.target.instance_id, edge.target.port_id = 'Coil2', 'in0'
            link('Coil2:out0', old_target.instance_id+':'+old_target.port_id)
            add('Strainer', 'water_strainer', rated_flow_m3_h=6., clean_pressure_drop_pa=1500.)
            add('Reducer', 'pipe_reducer', inlet_diameter_m=.065, outlet_diameter_m=.05)
            add('Isolation', 'water_shutoff_valve', kv_m3_h=30.)
            path('Chiller:out0','Strainer:in0', 'Strainer:out0','Reducer:in0',
                 'Reducer:out0','Isolation:in0', 'Isolation:out0','Header:common',
                 'Collector:common','ChilledJoin:out1')
        else:
            add('Ref', 'source', pressure_pa=200000.)
            add('ReturnJoin', 'junction')
            add('Pump', 'hvac_water_pump')
            add('Strainer', 'water_strainer')
            add('Reducer', 'pipe_reducer')
            path('Ref:out0','ReturnJoin:in0', 'ReturnJoin:out0','Pump:in0', 'Pump:out0','Strainer:in0',
                 'Strainer:out0','Reducer:in0', 'Reducer:out0','Header:common', 'Collector:common','ReturnJoin:out1')
        add('Header', 'water_header_2')
        add('Collector', 'water_collector_2')
        for index in (1,2):
            add('Balance'+str(index), 'water_balancing_valve', kv_m3_h=12. if plant else 16., opening_ratio=.8 if index==1 else 1.)
            if plant:
                terminal = 'Coil' if index==1 else 'Coil2'
                path('Header:branch'+str(index),'Balance'+str(index)+':in0',
                     'Balance'+str(index)+':out0',terminal+':in1', terminal+':out1','Collector:branch'+str(index))
            else:
                terminal = 'Load'+str(index)
                add(terminal, 'pipe', length_m=20. if index==1 else 50., diameter_m=.05)
                path('Header:branch'+str(index),'Balance'+str(index)+':in0',
                     'Balance'+str(index)+':out0',terminal+':in0', terminal+':out0','Collector:branch'+str(index))
        project.measurements = [meter('supply-dp','供回水压差','difference',
            ['Header.common.pressure_pa','Collector.common.pressure_pa'],'pressure','Pa','kPa',1000.)]
        for index in (1,2):
            project.measurements.append(meter('branch'+str(index)+'-flow', '支路 '+str(index)+' 体积流量', 'volume_flow',
                ['Balance'+str(index)+'.main.mass_flow_kg_s','Balance'+str(index)+'.in0.density_kg_m3'],
                'volume_flow','m3/s','m³/h',1/3600.))
        project.scenarios = [Scenario(id='open', name='平衡阀全开', overrides={'Balance1':{'opening_ratio':1.}})]
        if plant:
            project.measurements.append(meter('coil2-power','第二盘管水侧热功率','thermal_power',
                ['Coil2.ch1.mass_flow_kg_s','Coil2.out1.enthalpy_j_kg','Coil2.in1.enthalpy_j_kg'],'power','W','kW',1000.))
    for index, instance in enumerate(project.instances):
        instance.position = Position(x=110+(index%6)*210, y=110+(index//6)*160)
    return Project.model_validate(project.model_dump(mode='json'))
