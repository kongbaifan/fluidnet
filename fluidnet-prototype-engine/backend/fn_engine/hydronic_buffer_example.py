"""Wet coil with an explicit mixed liquid store in its independently specified water circuit."""
from .catalog import catalog_map
from .models import Project


def example(stagnant=False, reverse=False):
    catalog=catalog_map()
    nodes=[];links=[]
    def source(iid,p,t,w=0):
        nodes.append({'id':iid,'name':iid,'module_id':'source','parameters':{
            'pressure_pa':p,'temperature_k':t,'humidity_ratio_kg_kg':w}})
    source('AirIn',101425.,300.15,.010);source('AirOut',101325.,300.15,.010)
    source('WaterIn',201000.,280.15)
    source('WaterOut',200000.,280.15)
    nodes.extend([{'id':'Buffer','module_id':'hydronic_buffer_tank','name':'风水混合缓冲箱',
                   'parameters':{'mass_kg':30.,'temperature_k':290.15,'heat_loss_ua_w_k':10.,'ambient_temperature_k':293.15}},
                  {'id':'Coil','module_id':'water_coil','name':'真实水盘管'}])
    for a,b in [('AirIn:out0','Coil:in0'),('Coil:out0','AirOut:out0'),('WaterIn:out0','Buffer:in0'),
                ('Buffer:out0','Coil:in1'),('Coil:out1','WaterOut:out0')]:
        x,y=a.split(':');z,w=b.split(':');links.append({'id':f'edge-{len(links)}','source':{'instance_id':x,'port_id':y},'target':{'instance_id':z,'port_id':w}})
    if reverse:
        for link in links:
            for end in ('source','target'):
                if link[end]['instance_id']=='Buffer':
                    link[end]['port_id']='out0' if link[end]['port_id']=='in0' else 'in0'
    if stagnant:
        nodes.append({'id':'Isolation','module_id':'valve','name':'停流隔离阀','parameters':{'opening_ratio':0.}})
        target=next(link for link in links if link['source']['instance_id']=='WaterIn')
        old=target['target'];target['target']={'instance_id':'Isolation','port_id':'in0'}
        links.append({'id':'isolated','source':{'instance_id':'Isolation','port_id':'out0'},'target':old})
    for i,node in enumerate(nodes):node['position']={'x':100+(i%3)*330,'y':100+(i//3)*250}
    return Project(id='hydronic-buffer',name='水盘管与混合缓冲箱',
        fluid={'fluid':'Air','phase_policy':'gas'},modules=[catalog[k] for k in ('source','water_coil','hydronic_buffer_tank','valve')],
        instances=nodes,connections=links,circuit_fluids=[{'id':'water','anchor':{'instance_id':'Buffer','port_id':'in0'},'fluid':{'fluid':'Water','phase_policy':'liquid'}}],
        solver={'thermal':True,'property_coupling':'node','moist_air':True,'dynamic_step_s':1.,'max_coupling_iterations':80,
                'moist_air_options':{'contract_version':1,'max_iterations':160,'humidity_tolerance_kg_kg':1e-10}})
