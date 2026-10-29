"""从固定项目生成风侧变量目录，供界面、批次、运行和报告共用。"""
import hashlib
import json

from . import __version__
from .air_models import AirVariableDescriptor
from .models import UnitSpec

# label, quantity, canonical, display, scale, offset, mass_basis
UNITS = {
    'temperature':('温度','temperature','K','°C',1.,-273.15,'none'),
    'pressure':('压力','pressure','Pa','kPa',1000.,0.,'none'),
    'humidity':('含湿量','humidity_ratio','kg/kg_da','g/kg_da',.001,0.,'dry_air'),
    'rh':('相对湿度','ratio','1','%',.01,0.,'none'),
    'enthalpy':('混合物比焓','specific_enthalpy','J/kg','kJ/kg',1000.,0.,'mixture'),
    'enthalpy_da':('干空气基准比焓','specific_enthalpy_dry_air','J/kg_da','kJ/kg_da',1000.,0.,'dry_air'),
    'cp':('混合物定压比热','specific_heat','J/(kg·K)','kJ/(kg·K)',1000.,0.,'mixture'),
    'cp_da':('干空气基准比热','specific_heat_dry_air','J/(kg_da·K)','kJ/(kg_da·K)',1000.,0.,'dry_air'),
    'density':('混合物密度','density','kg/m3','kg/m3',1.,0.,'mixture'),
    'viscosity':('动力黏度','dynamic_viscosity','Pa·s','mPa·s',.001,0.,'none'),
    'mass':('混合物质量流量','mass_flow','kg/s','kg/s',1.,0.,'mixture'),
    'dry_flow':('干空气质量流量','dry_air_mass_flow','kg_da/s','kg_da/s',1.,0.,'dry_air'),
    'water_flow':('水分流量','mass_flow','kg/s','kg/s',1.,0.,'water'),
    'volume':('实际体积流量','volume_flow','m3/h','m3/h',1.,0.,'none'),
    'power':('功率','power','W','kW',1000.,0.,'none'),
    'energy':('能量','energy','J','kWh',3600000.,0.,'none'),
    'water':('水量','mass','kg','kg',1.,0.,'water'),
    'dry_mass':('干空气存量','dry_air_mass','kg_da','kg_da',1.,0.,'dry_air'),
    'ratio':('比例','ratio','1','1',1.,0.,'none'),
    'delta_t':('温差','temperature_difference','K','K',1.,0.,'none'),
    'count':('次数','count','1','1',1.,0.,'none'),
}
PORTS = {'pressure_pa':'pressure','temperature_k':'temperature','enthalpy_j_kg':'enthalpy','density_kg_m3':'density',
    'viscosity_pa_s':'viscosity','specific_heat_j_kg_k':'cp','mass_flow_kg_s':'mass'}
WET_PORTS = {'humidity_ratio_kg_kg':'humidity','relative_humidity':'rh','enthalpy_j_kg_dry_air':'enthalpy_da',
    'specific_heat_j_kg_dry_air_k':'cp_da','dew_point_k':'temperature','wet_bulb_k':'temperature',
    'dry_air_mass_flow_kg_s':'dry_flow','water_vapor_mass_flow_kg_s':'water_flow'}
DEVICE_FIELDS = {
    'cooling_coil':{'total_heat_w':('总冷量','power'),'sensible_heat_w':('显热冷量','power'),
        'latent_heat_w':('潜热冷量','power'),'condensate_kg_s':('凝水量','water_flow'),'shr':('显热比','ratio'),
        'cooling_load_w':('外部冷源负荷','power'),'condensate_enthalpy_flow_w':('凝水携出焓流','power'),
        'outlet_humidity_ratio_kg_kg':('出口含湿量','humidity'),'wet':('湿工况','bool'),'active':('制冷有效','bool'),
        'state.condensate_kg':('累计凝水量','water'),'state.cooling_energy_j':('累计冷量','energy')},
    'humidifier':{'requested_moisture_kg_s':('请求加水量','water_flow'),'moisture_addition_kg_s':('实际加水量','water_flow'),
        'limited':('饱和限幅','bool'),'state.water_added_kg':('累计加水量','water'),
        'state.heating_energy_j':('累计补热','energy')},
    'air_mixing_box':{'fresh_air_fraction':('新风比例','rh'),'dry_air_mass_residual_kg_s':('干空气质量残差','dry_flow')},
    'air_filter':{'loading_ratio':('污堵比例','rh')},
    'air_room':{'state.temperature_k':('房间温度','temperature'),'state.humidity_ratio_kg_kg':('房间含湿量','humidity'),
        'state.relative_humidity':('房间相对湿度','rh'),'state.dry_air_mass_kg':('有效干空气存量','dry_mass'),
        'state.water_vapor_mass_kg':('水蒸气存量','water'),'state.stored_energy_j':('房间储能','energy'),
        'sensible_load_w':('室内显热负荷','power'),'moisture_load_kg_s':('室内散湿','water_flow'),
        'envelope_heat_w':('围护传热','power'),'infiltration_heat_w':('渗透热量','power'),
        'infiltration_moisture_kg_s':('渗透水分','water_flow'),'state.moisture_added_kg':('累计散湿','water'),
        'state.load_energy_j':('累计负荷能量','energy')},
    'cooling_tower_moist':{'heat_rejected_w':('排热量','power'),'water_outlet_temperature_k':('出水温度','temperature'),
        'air_outlet_temperature_k':('排风温度','temperature'),'air_outlet_humidity_ratio_kg_kg':('排风含湿量','humidity'),
        'approach_k':('湿球逼近度','delta_t'),'evaporation_kg_s':('蒸发量','water_flow'),'drift_kg_s':('飘水量','water_flow'),
        'blowdown_kg_s':('排污量','water_flow'),'makeup_kg_s':('补水量','water_flow'),
        'achieved_concentration_ratio':('实际浓缩倍数','ratio'),'water_residual_kg_s':('水量残差','water_flow'),
        'energy_residual_w':('能量残差','power'),'state.evaporated_kg':('累计蒸发','water'),
        'state.drift_kg':('累计飘水','water'),'state.blowdown_kg':('累计排污','water'),
        'state.makeup_kg':('累计补水','water'),'state.heat_rejected_j':('累计排热','energy')},
}


def is_air_project(project):
    used={i.module_id for i in project.instances}
    return project.solver.moist_air or any(m.id in used and m.solver_model=='cooling_tower_moist' for m in project.modules)


def collect_air_variables(project):
    result={}
    definitions={m.id:m for m in project.modules}
    def add(iid,name,kind,label=None,source='derived',port=None,channel=None,dynamic=False):
        key=f'{iid}.{name}'
        if kind=='bool':
            descriptor=AirVariableDescriptor(key=key,label=label or name,instance_id=iid,value_type='boolean',quantity='boolean')
        else:
            default,quantity,canonical,display,scale,offset,basis=UNITS[kind]
            descriptor=AirVariableDescriptor(key=key,label=label or default,instance_id=iid,quantity=quantity,mass_basis=basis,
                unit=UnitSpec(quantity=quantity,canonical_unit=canonical,display_unit=display,display_scale=scale,display_offset=offset))
        descriptor.source,descriptor.port_id,descriptor.channel_id=source,port,channel
        descriptor.nullable=name.split('.')[-1] in ('dew_point_k','wet_bulb_k','shr','fresh_air_fraction','achieved_concentration_ratio')
        descriptor.available_in=['dynamic'] if dynamic else ['steady','dynamic']
        result[key]=descriptor
    for inst in project.instances:
        definition=definitions[inst.module_id]
        # 保留官方/Python 模块自己的派生量，再用显式风侧语义覆盖公共量。
        for variable in definition.variables:
            if variable.source in ('parameter','port') or variable.unit is None:
                continue
            key=f'{inst.id}.{variable.id}'
            result[key]=AirVariableDescriptor(key=key,label=f'{inst.name} · {variable.label}',instance_id=inst.id,
                quantity=variable.quantity,unit=variable.unit,source=variable.source,
                available_in=['dynamic'] if variable.id.startswith('state.') else ['steady','dynamic'])
        for port in definition.ports:
            for name,kind in (PORTS | (WET_PORTS if project.solver.moist_air else {})).items():
                add(inst.id,f'{port.id}.{name}',kind,f'{inst.name} · {port.label} · {UNITS[kind][0]}',source='port',port=port.id)
        for ch in definition.channels:
            if not ch.enabled:
                continue
            fields={'mass_flow_kg_s':'mass','volume_flow_m3_h':'volume','pressure_drop_pa':'pressure','heat_w':'power',
                    'inlet_temperature_k':'temperature','outlet_temperature_k':'temperature'}
            if project.solver.moist_air:
                fields.update(dry_air_mass_flow_kg_s='dry_flow',inlet_mass_flow_kg_s='mass',outlet_mass_flow_kg_s='mass')
            for name,kind in fields.items():
                add(inst.id,f'{ch.id}.{name}',kind,channel=ch.id)
                if len(definition.channels)==1:
                    add(inst.id,name,kind,channel=ch.id)
        for name,(label,kind) in DEVICE_FIELDS.get(definition.solver_model,{}).items():
            dynamic=name.startswith('state.') and name not in {
                'state.temperature_k','state.humidity_ratio_kg_kg','state.relative_humidity','state.dry_air_mass_kg',
                'state.water_vapor_mass_kg','state.stored_energy_j'}
            add(inst.id,name,kind,f'{inst.name} · {label}',source='state' if name.startswith('state.') else 'derived',dynamic=dynamic)
        for parameter in definition.parameters:
            if parameter.value_type=='curve':
                continue
            key=f'{inst.id}.param.{parameter.id}'
            result[key]=AirVariableDescriptor(key=key,label=f'{inst.name} · {parameter.label}',instance_id=inst.id,
                value_type=parameter.value_type,quantity=parameter.unit.quantity if parameter.unit else parameter.value_type,
                unit=parameter.unit,source='parameter',writable=parameter.runtime and parameter.writable,
                mass_basis='dry_air' if parameter.unit and 'kg_da' in parameter.unit.canonical_unit else 'none')
    for name,kind in {'energy_residual_w':'power','moisture_residual_kg_s':'water_flow',
                      'dry_air_mass_residual_kg_s':'dry_flow','air_transport_iterations':'count'}.items():
        if project.solver.moist_air or name=='energy_residual_w':
            add('metrics',name,kind,source='system')
    return list(result.values())


def make_air_metadata(project):
    if not is_air_project(project):
        return None
    if project.solver.moist_air and project.solver.moist_air_options is None:
        return None
    import CoolProp
    snapshot=project.model_dump(mode='json')
    digest=hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return {'contract_version':1,'engine_version':__version__,'property_backend':'coolprop_ha',
        'property_version':CoolProp.__version__,'continuity_basis':'dry_air' if project.solver.moist_air else 'water',
        'enthalpy_basis':'dry_air' if project.solver.moist_air else 'water',
        'project_snapshot_hash':digest,'variable_catalog':[v.model_dump(mode='json') for v in collect_air_variables(project)],
        'assumptions':['低速单相流动；湿空气公共比焓和流量以当地混合物计，热湿输运以干空气计。',
            '湿盘管采用外部规定机器露点，不含冷水侧/制冷剂侧真实耦合。',
            '房间采用固定有效干空气存量；真实新风与平衡渗透须避免重复计入。',
            '冷却塔为接触效能教学模型，空气为规定流股，不能用于填料设计或厂家选型。']}
