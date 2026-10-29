"""六个规范风侧教学算例；参数为公开模型假设，不冒充现场标定数据。"""
from pathlib import Path

from .catalog import catalog_map
from .models import Connection, Endpoint, FluidConfig, ModuleInstance, Project, SolverOptions
from .packages import load_module_package

AIR_EXAMPLES = ('air-coil-wet','air-mixing','ahu-wet','ahu-room','air-parallel-wet','cooling-tower-moist')


def air_example(name):
    if name not in AIR_EXAMPLES:
        raise KeyError(name)
    catalog=catalog_map()
    nodes,links=[],[]

    def add(iid,kind,**params):
        nodes.append(ModuleInstance(id=iid,module_id=kind,name=catalog[kind].name if kind in catalog else '送风机',parameters=params))

    def boundary(iid,p=101325.,t=303.15,w=.014):
        add(iid,'source',pressure_pa=p,temperature_k=t,humidity_ratio_kg_kg=w)

    def connect(a,b):
        links.append((a,b))

    if name=='cooling-tower-moist':
        add('Hot','source',pressure_pa=103325.,temperature_k=310.15)
        add('Tower','cooling_tower_moist',air_volume_flow_m3_s=3.)
        add('Return','source',pressure_pa=101325.,temperature_k=303.15)
        links=[('Hot:out0','Tower:in0'),('Tower:out0','Return:out0')]
    elif name=='air-coil-wet':
        boundary('Fresh',101425.)
        add('Coil','cooling_coil',loss_coefficient=4.)
        boundary('Outlet',t=293.15,w=.008)
        links=[('Fresh:out0','Coil:in0'),('Coil:out0','Outlet:out0')]
    elif name=='air-parallel-wet':
        boundary('Fresh')
        add('Fan','fan'); add('Split','junction'); add('Join','junction')
        add('Coil','cooling_coil',loss_coefficient=4.); add('Filter','air_filter')
        add('OutletDuct','duct',length_m=10.)
        boundary('Outlet')
        links=[('Fresh:out0','Fan:in0'),('Fan:out0','Split:in0'),('Split:out0','Coil:in0'),
               ('Split:out1','Filter:in0'),('Coil:out0','Join:in0'),('Filter:out0','Join:out0'),
               ('Join:out1','OutletDuct:in0'),('OutletDuct:out0','Outlet:out0')]
    else:
        room=name=='ahu-room'
        boundary('Fresh',101325. if room or name=='ahu-wet' else 101525.)
        add('FreshDuct','duct',length_m=10.)
        add('ReturnDuct','duct',length_m=20.)
        add('Mix','air_mixing_box')
        links=[('Fresh:out0','FreshDuct:in0'),('FreshDuct:out0','Mix:fresh_in'),('ReturnDuct:out0','Mix:return_in')]
        if not room:
            boundary('Return',101325. if name=='ahu-wet' else 101475.,299.15,.009)
            connect('Return:out0','ReturnDuct:in0')
        if name=='air-mixing':
            add('SupplyDuct','duct',length_m=10.); boundary('Outlet')
            connect('Mix:supply_out','SupplyDuct:in0');connect('SupplyDuct:out0','Outlet:out0')
        else:
            add('Filter','air_filter',clean_pressure_drop_pa=40.)
            add('Coil','cooling_coil',loss_coefficient=2.)
            add('Reheat','heater',heat_input_w=2500.,diameter_m=.4,loss_coefficient=.2)
            add('Humidifier','humidifier',mode='isothermal',moisture_addition_kg_kg=.0002,loss_coefficient=.2)
            add('Fan','fan')
            add('SupplyDuct','duct',length_m=10.)
            links.extend([('Mix:supply_out','Filter:in0'),('Filter:out0','Coil:in0'),('Coil:out0','Reheat:in0'),
                          ('Reheat:out0','Humidifier:in0'),('Humidifier:out0','Fan:in0'),('Fan:out0','SupplyDuct:in0')])
            if room:
                add('Room','air_room',sensible_load_w=1500.,moisture_load_kg_s=.0001,envelope_ua_w_k=50.)
                add('ReturnSplit','junction'); add('ExhaustDuct','duct',length_m=20.,duct_width_m=.25,duct_height_m=.25)
                boundary('Exhaust')
                links.extend([('SupplyDuct:out0','Room:supply_in'),('Room:return_out','ReturnSplit:in0'),
                    ('ReturnSplit:out0','ReturnDuct:in0'),('ReturnSplit:out1','ExhaustDuct:in0'),('ExhaustDuct:out0','Exhaust:out0')])
            else:
                boundary('Outlet'); connect('SupplyDuct:out0','Outlet:out0')
    used=list(dict.fromkeys(inst.module_id for inst in nodes))
    if 'fan' in used:
        catalog['fan']=load_module_package(Path(__file__).resolve().parents[2]/'modules'/'fan')
    endpoint=lambda key:Endpoint(instance_id=key.split(':')[0],port_id=key.split(':')[1])
    moist=name!='cooling-tower-moist'
    return Project(id=name,name={'air-coil-wet':'湿盘管除湿','air-mixing':'新回风混合','ahu-wet':'空气处理机组',
        'ahu-room':'房间送回风热湿系统','air-parallel-wet':'并联风侧设备','cooling-tower-moist':'冷却塔水耗'}[name],
        fluid=FluidConfig(fluid='Air' if moist else 'Water',phase_policy='gas' if moist else 'liquid'),
        modules=[catalog[k] for k in used],instances=nodes,
        connections=[Connection(id=f'e{i}',source=endpoint(a),target=endpoint(b)) for i,(a,b) in enumerate(links)],
        solver=SolverOptions(moist_air=moist,property_coupling='node',max_coupling_iterations=40,
                             moist_air_options={'contract_version':1,'max_iterations':120} if moist else None))
