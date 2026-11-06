"""Actual makeup/drain branches around an open pool with prescribed evaporation."""
from .catalog import catalog_map
from .models import Project


def tower_pool_example(makeup=False):
    catalog=catalog_map()
    instances=[{'id':'Pool','name':'塔池','module_id':'tower_pool','parameters':{
        'area_m2':1.,'level_m':1.,'height_m':2.,'temperature_k':303.15,'evaporation_kg_s':.001,'drift_kg_s':.0001}}]
    connections=[]
    for index,(port,pressure) in enumerate([('in0',111000.),('in1',200000.),('out0',111000.),('out1',101325.)]):
        valve,boundary=f'Valve{index}',f'Boundary{index}'
        instances.extend([{'id':valve,'name':valve,'module_id':'valve','parameters':{
            'opening_ratio':.02 if makeup and index==1 else .0002 if makeup and index==3 else 0.,'kv_m3_h':1.}},
            {'id':boundary,'name':boundary,'module_id':'source','parameters':{'pressure_pa':pressure,'temperature_k':293.15}}])
        connections.extend([{'id':f'a{index}','source':{'instance_id':boundary,'port_id':'out0'},
            'target':{'instance_id':valve,'port_id':'in0'}},{'id':f'b{index}',
            'source':{'instance_id':valve,'port_id':'out0'},'target':{'instance_id':'Pool','port_id':port}}])
    return Project(id='tower-pool-makeup' if makeup else 'tower-pool-evaporation',name='塔池 · 实际补排水' if makeup else '塔池 · 蒸发库存',
        fluid={'fluid':'Water','phase_policy':'liquid'},modules=[catalog[k] for k in ('source','valve','tower_pool')],
        instances=instances,connections=connections,solver={'thermal':True,'property_coupling':'node',
            'dynamic_step_s':10.,'max_coupling_iterations':60,'thermal_tolerance_k':1e-8})
