"""Pressure-driven filling/draining through a real liquid mass-storage node."""
from .catalog import catalog_map
from .models import Project


def expansion_example():
    catalog=catalog_map()
    return Project(id='gas-expansion-fill',name='气垫膨胀罐 · 充水压升',
        description='两压力边界经细管接气垫罐；真实质量储存、液体EOS、等温气体pV和压缩功共同计算。',
        modules=[catalog[k] for k in ('source','pipe','gas_expansion_tank')],
        fluid={'fluid':'Water','phase_policy':'liquid'},
        solver={'thermal':True,'property_coupling':'node','dynamic_step_s':1.,'max_coupling_iterations':60,
                'thermal_tolerance_k':1e-8,'pressure_tolerance_pa':.01},
        instances=[{'id':'Supply','name':'入口','module_id':'source','parameters':{'pressure_pa':270000.}},
                   {'id':'InPipe','name':'入口阻力管','module_id':'pipe','parameters':{'length_m':10.,'diameter_m':.01}},
                   {'id':'Expansion','name':'等温气垫罐','module_id':'gas_expansion_tank'},
                   {'id':'OutPipe','name':'出口阻力管','module_id':'pipe','parameters':{'length_m':10.,'diameter_m':.01}},
                   {'id':'Return','name':'出口','module_id':'source','parameters':{'pressure_pa':250000.}}],
        connections=[{'id':f'edge-{i}','source':{'instance_id':a,'port_id':ap},'target':{'instance_id':b,'port_id':bp}}
            for i,(a,ap,b,bp) in enumerate([('Supply','out0','InPipe','in0'),('InPipe','out0','Expansion','in0'),
                ('Expansion','out0','OutPipe','in0'),('OutPipe','out0','Return','out0')])])
