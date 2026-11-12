"""Contract-built HVAC cases; IDs and boundaries are ordinary editable Project data."""
from pathlib import Path

from .catalog import catalog_map
from .model_types.domain import Project
from .packages import load_module_package, package_ref

ROOT=Path(__file__).resolve().parents[2]
HVAC_EXPANSION_EXAMPLES = (
    'air-branch-dry', 'air-branch-moist', 'fan-running-dry', 'fan-running-moist',
    'plate-water-glycol', 'air-cooled-chiller', 'air-recovery-moist',
    'air-source-heat-pump', 'enthalpy-recovery',
)


def example(name):
    if name not in HVAC_EXPANSION_EXAMPLES:
        raise KeyError(name)
    if name=='air-cooled-chiller':return air_chiller_example()
    if name=='air-source-heat-pump':return heat_pump_example()
    if name=='air-recovery-moist':return air_recovery_example()
    if name=='enthalpy-recovery':return enthalpy_recovery_example()
    moist=name.endswith('moist')
    air=not name.startswith('plate')
    kind='air_branch_box' if name.startswith('air-branch') else 'fan_performance' if name.startswith('fan') else 'plate_exchanger'
    module=load_module_package(ROOT/'modules'/kind)
    # Public examples carry frozen inline source; a checkout path is not portable.
    module.package_path=None
    nodes=[];links=[]
    def source(iid,p,t=298.15,w=.008):
        nodes.append({'id':iid,'name':iid,'module_id':'source','parameters':{'pressure_pa':p,'temperature_k':t,'humidity_ratio_kg_kg':w}})
    def link(a,b):
        ai,ap=a.split(':');bi,bp=b.split(':')
        links.append({'id':f'edge-{len(links)}','source':{'instance_id':ai,'port_id':ap},'target':{'instance_id':bi,'port_id':bp}})
    if kind=='air_branch_box':
        source('Supply',101525.);source('ReturnA',101325.);source('ReturnB',101325.)
        nodes.append({'id':'Box-Own','name':'分支箱','module_id':kind,'package':package_ref(module).model_dump(mode='json')})
        link('Supply:out0','Box-Own:common');link('Box-Own:branch1','ReturnA:out0');link('Box-Own:branch2','ReturnB:out0')
    elif kind=='fan_performance':
        source('Inlet',101325.);source('Outlet',101575.)
        nodes.append({'id':'Fan-Own','name':'性能风机','module_id':kind,'package':package_ref(module).model_dump(mode='json')})
        link('Inlet:out0','Fan-Own:in0');link('Fan-Own:out0','Outlet:out0')
    else:
        source('HotIn',220000.,333.15);source('HotOut',200000.,333.15)
        source('ColdIn',220000.,293.15);source('ColdOut',200000.,293.15)
        nodes.append({'id':'Plate-Own','name':'板式换热器','module_id':kind,'package':package_ref(module).model_dump(mode='json')})
        for side,prefix in [('hot','Hot'),('cold','Cold')]:
            link(prefix+'In:out0','Plate-Own:'+side+'_in');link('Plate-Own:'+side+'_out',prefix+'Out:out0')
    for i,node in enumerate(nodes):node['position']={'x':110+(i%3)*330,'y':130+(i//3)*220}
    return Project(id=name,name=name,fluid={'fluid':'Air' if air else 'Water','phase_policy':'gas' if air else 'liquid'},
        modules=[catalog_map()['source'],module],instances=nodes,connections=links,
        circuit_fluids=[] if air else [{'id':'glycol','anchor':{'instance_id':'ColdIn','port_id':'out0'},'fluid':{'fluid':'INCOMP::MEG[0.3]','phase_policy':'liquid'}}],
        solver={'thermal':True,'property_coupling':'node','moist_air':moist,'module_mixed_jacobian':False,
            'max_coupling_iterations':60,'moist_air_options':{'contract_version':1,'max_iterations':120} if moist else None})


def recipe(project):
    return {'name':project.name,'fluid':project.fluid.model_dump(mode='json'),'solver':project.solver.model_dump(mode='json'),
        'duration_s':2.,'dt_s':1.,'instances':[n.model_dump(mode='json',exclude_none=True) for n in project.instances],
        'connections':[c.model_dump(mode='json') for c in project.connections],
        'circuit_fluids':[c.model_dump(mode='json') for c in project.circuit_fluids]}


def air_chiller_example():
    catalog=catalog_map()
    return Project(id='air-cooled-chiller',name='风冷冷水机组单水回路',fluid={'fluid':'Water','phase_policy':'liquid'},
        modules=[catalog['source'],catalog['air_cooled_chiller']],instances=[
            {'id':'Return','module_id':'source','name':'回水边界','parameters':{'pressure_pa':250000.,'temperature_k':285.15},'position':{'x':100.,'y':220.}},
            {'id':'Chiller','module_id':'air_cooled_chiller','name':'风冷冷水机组','position':{'x':420.,'y':220.}},
            {'id':'Supply','module_id':'source','name':'供水边界','parameters':{'pressure_pa':249000.,'temperature_k':280.15},'position':{'x':740.,'y':220.}}],
        connections=[{'id':'in','source':{'instance_id':'Return','port_id':'out0'},'target':{'instance_id':'Chiller','port_id':'in0'}},
            {'id':'out','source':{'instance_id':'Chiller','port_id':'out0'},'target':{'instance_id':'Supply','port_id':'out0'}}],
        solver={'thermal':True,'property_coupling':'node'})


def air_recovery_example():
    module=load_module_package(ROOT/'modules/air_recovery_sensible')
    module.package_path=None
    instances=[{'id':'Recovery','name':'显热回收器','module_id':module.id,'package':package_ref(module).model_dump(mode='json'),
                'position':{'x':430.,'y':250.}}]
    connections=[]
    for side,temp,humidity,y in [('exhaust',303.15,.007,140.),('supply',283.15,.003,360.)]:
        for end,pressure,x in [('in',101425.,100.),('out',101325.,760.)]:
            iid=side+'_'+end
            instances.append({'id':iid,'name':iid,'module_id':'source','parameters':{'pressure_pa':pressure,'temperature_k':temp,
                'humidity_ratio_kg_kg':humidity},'position':{'x':x,'y':y}})
            connections.append({'id':iid,'source':{'instance_id':iid if end=='in' else 'Recovery','port_id':'out0' if end=='in' else iid},
                'target':{'instance_id':'Recovery' if end=='in' else iid,'port_id':iid if end=='in' else 'out0'}})
    return Project(id='air-recovery-moist',name='双风道显热回收',fluid={'fluid':'Air','phase_policy':'gas'},
        modules=[catalog_map()['source'],module],instances=instances,connections=connections,
        solver={'thermal':True,'property_coupling':'node','moist_air':True,'module_mixed_jacobian':False,
                'max_coupling_iterations':60,'moist_air_options':{'contract_version':1,'max_iterations':120}})


def heat_pump_example():
    p=air_chiller_example();catalog=catalog_map()
    p.id='air-source-heat-pump';p.name='空气源供热热泵干盘管'
    p.modules=[catalog['source'],catalog['air_source_heat_pump']]
    for n in p.instances:
        if n.id=='Return':n.parameters['temperature_k']=308.15
        elif n.id=='Supply':n.parameters['temperature_k']=313.15
        else:
            n.module_id='air_source_heat_pump';n.name='空气源供热热泵'
            n.parameters={'diameter_m':.025,'loss_coefficient':20.}
    return p


def enthalpy_recovery_example():
    p=air_recovery_example();p.id='enthalpy-recovery';p.name='四口全热回收无凝结'
    p.modules=[catalog_map()['source'],catalog_map()['enthalpy_recovery']]
    p.instances[0].module_id='enthalpy_recovery';p.instances[0].package=None;p.instances[0].name='全热回收器'
    return p
