"""A boundary-fed buffer with explicit heat storage, plus the stopped-flow variant."""
from .catalog import catalog_map
from .model_types.domain import Project


def buffer_example(stagnant=False):
    catalog = catalog_map()
    project = Project(id='closed-buffer-cooling' if stagnant else 'closed-buffer-mixing',
        name='闭式缓冲水箱 · 停流散热' if stagnant else '闭式缓冲水箱 · 热水混合',
        description='显式固定热质量的双口充分混合液体模型；外网定压力，无气垫、分层和热膨胀。',
        fluid={'fluid':'Water', 'phase_policy':'liquid'}, modules=[catalog['source'], catalog['closed_buffer_tank']],
        instances=[{'id':'Supply', 'module_id':'source', 'name':'热水入口', 'position':{'x':100,'y':220},
                    'parameters':{'pressure_pa':200000. if stagnant else 201000., 'temperature_k':333.15}},
                   {'id':'Buffer', 'module_id':'closed_buffer_tank', 'name':'固定热质量混合水箱',
                    'position':{'x':430,'y':220}, 'parameters':{'mass_kg':100., 'temperature_k':313.15 if stagnant else 293.15,
                        'heat_loss_ua_w_k':100. if stagnant else 10., 'ambient_temperature_k':293.15}},
                   {'id':'Return', 'module_id':'source', 'name':'出口压力边界', 'position':{'x':760,'y':220},
                    'parameters':{'pressure_pa':200000., 'temperature_k':293.15}}],
        connections=[{'id':'supply','source':{'instance_id':'Supply','port_id':'out0'},
                      'target':{'instance_id':'Buffer','port_id':'in0'}},
                     {'id':'return','source':{'instance_id':'Buffer','port_id':'out0'},
                      'target':{'instance_id':'Return','port_id':'out0'}}],
        solver={'thermal':True, 'property_coupling':'node', 'dynamic_step_s':10., 'max_coupling_iterations':40})
    if stagnant:
        from .model_types.domain import Connection, Endpoint, ModuleInstance
        project.modules.append(catalog['valve'])
        project.instances.append(ModuleInstance(id='Isolation', module_id='valve', name='关闭的隔离阀',
            parameters={'opening_ratio':0.}, position={'x':260.,'y':220.}))
        project.connections[0].target = Endpoint(instance_id='Isolation',port_id='in0')
        project.connections.append(Connection(id='isolated-inlet',source=Endpoint(instance_id='Isolation',port_id='out0'),
                                              target=Endpoint(instance_id='Buffer',port_id='in0')))
    return project


def buffer_recipe(stagnant=False):
    project = buffer_example(stagnant)
    return {'name':project.name, 'fluid':project.fluid.model_dump(mode='json'),
            'solver':project.solver.model_dump(mode='json'), 'duration_s':300., 'dt_s':30.,
            'instances':[item.model_dump(mode='json',exclude_none=True) for item in project.instances],
            'connections':[item.model_dump(mode='json') for item in project.connections]}
