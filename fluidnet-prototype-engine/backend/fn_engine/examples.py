"""Reference PID projects shared by the UI and numerical acceptance tests."""
from .catalog import catalog_map
from .models import Connection, Endpoint, ModuleInstance, PIDController, Project


def pid_example(kind):
    if kind == 'level':
        nodes = [('B1','source',{'pressure_pa':150000}), ('V1','valve',{'kv_m3_h':4.,'opening_ratio':.5}),
                 ('T1','tank',{'area_m2':.2,'height_m':3.,'level_m':1.}),
                 ('V2','valve',{'kv_m3_h':4.,'opening_ratio':.5}),('B2','source',{'pressure_pa':101325})]
        links = [('B1:out0','V1:in0'),('V1:out0','T1:in0'),('T1:out0','V2:in0'),('V2:out0','B2:out0')]
        controller = PIDController(id='level',measurement='T1.state.level_m',instance_id='V1',parameter_id='opening_ratio',
                                   setpoint=1.5,kp=4.,ki=.02,sample_s=.5,minimum=0,maximum=1)
        name = 'PID 水箱液位控制'
    elif kind == 'temperature':
        nodes = [('B1','source',{}),('V1','valve',{'opening_ratio':0}),
                 ('T1','tank',{'area_m2':.05,'level_m':1.,'height_m':3.,'heat_loss_ua_w_k':100.})]
        links = [('B1:out0','V1:in0'),('V1:out0','T1:in0')]
        controller = PIDController(id='temperature',measurement='T1.state.temperature_k',instance_id='T1',parameter_id='heat_input_w',
                                   setpoint=303.15,kp=2000,ki=30,sample_s=1.,minimum=0,maximum=10000)
        name = 'PID 水箱温度控制'
    else:
        raise KeyError(kind)
    catalog = catalog_map()
    endpoint = lambda key: Endpoint(instance_id=key.split(':')[0],port_id=key.split(':')[1])
    return Project(id='pid-'+kind,name=name,controllers=[controller],
        modules=[catalog[key] for key in dict.fromkeys(n[1] for n in nodes)],
        instances=[ModuleInstance(id=id,module_id=kind,name=id,parameters=params) for id,kind,params in nodes],
        connections=[Connection(id=f'e{i}',source=endpoint(a),target=endpoint(b)) for i,(a,b) in enumerate(links)])
