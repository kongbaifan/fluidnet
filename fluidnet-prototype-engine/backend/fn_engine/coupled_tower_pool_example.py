"""A circulating heat load, wet-contact pool and real makeup/blowdown branches."""
from .catalog import catalog_map
from .models import Project


def coupled_tower_pool_example(makeup=True):
    catalog=catalog_map()
    items=[('Pool','coupled_tower_pool',{'temperature_k':303.15}),
           ('Pump','pump',{'speed_ratio':.6}),('Load','heater',{'heat_input_w':5000.}),
           ('Pipe','pipe',{'length_m':40.,'diameter_m':.04}),
           ('Makeup','source',{'pressure_pa':200000.,'temperature_k':293.15}),
           ('MakeupValve','valve',{'kv_m3_h':1.,'opening_ratio':.02 if makeup else 0.}),
           ('DrainValve','valve',{'kv_m3_h':1.,'opening_ratio':.0002 if makeup else 0.}),
           ('Drain','source',{'pressure_pa':101325.,'temperature_k':293.15})]
    links=[('Pool:out0','Pump:in0'),('Pump:out0','Load:in0'),('Load:out0','Pipe:in0'),('Pipe:out0','Pool:in0'),
           ('Makeup:out0','MakeupValve:in0'),('MakeupValve:out0','Pool:in1'),
           ('Pool:out1','DrainValve:in0'),('DrainValve:out0','Drain:out0')]
    nodes=[{'id':iid,'module_id':module,'name':iid,'parameters':params,
            'position':{'x':100.+(i%4)*260.,'y':140.+(i//4)*220.}} for i,(iid,module,params) in enumerate(items)]
    connections=[]
    for i,(a,b) in enumerate(links):
        ai,ap=a.split(':');bi,bp=b.split(':')
        connections.append({'id':f'link-{i}','source':{'instance_id':ai,'port_id':ap},
                            'target':{'instance_id':bi,'port_id':bp}})
    return Project(id='wet-pool-makeup' if makeup else 'wet-pool-no-makeup',
        name='湿接触冷却塔池 · 实际补排' if makeup else '湿接触冷却塔池 · 无补水库存',
        description='完全混合湿接触池体与环境湿空气热湿联算，液泵循环和5kW热负荷；无隐含补水或排污。',
        modules=[catalog[key] for key in dict.fromkeys(module for _,module,_ in items)],instances=nodes,connections=connections,
        fluid={'fluid':'Water','phase_policy':'liquid'},solver={'thermal':True,'property_coupling':'node',
            'dynamic_step_s':10.,'max_coupling_iterations':60,'thermal_tolerance_k':1e-8})
