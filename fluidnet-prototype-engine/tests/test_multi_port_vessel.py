"""多支路饱和容器：同一容器四个进口，多台冷凝器/多路回气汇入同一压力等级。"""
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance
from fn_engine.refrigeration.examples import station_example
from fn_engine.solver import solve_dynamic


def link(identifier, a, b):
    return Connection(id=identifier, source=Endpoint(instance_id=a[0], port_id=a[1]),
                      target=Endpoint(instance_id=b[0], port_id=b[1]))


def multi_inlet_station():
    project = station_example()
    catalog = catalog_map()
    instances = {instance.id: instance for instance in project.instances}
    instances['HP1'].module_id = 'hp_receiver_multi'
    instances['LP1'].module_id = 'lp_drum_multi'
    project.modules = [module for module in project.modules if module.id not in {'hp_receiver', 'lp_drum'}]
    project.modules += [catalog['hp_receiver_multi'], catalog['lp_drum_multi']]
    project.instances.append(ModuleInstance(id='EC2', module_id='evaporative_condenser', name='第二台冷凝器',
                                            parameters={'ua_w_k': 20000.}))
    project.connections += [link('d1b', ('DH1', 'out1'), ('EC2', 'in0')),
                            link('c2', ('EC2', 'out0'), ('HP1', 'in2'))]
    return project


def test_multi_inlet_vessels_join_one_pressure_level():
    network = compile_project(multi_inlet_station())
    assert network.kinds['HP1'] == 'saturated_vessel'
    assert network.kinds['LP1'] == 'saturated_vessel'
    # Both condensers discharge into the same receiver level, and the valve draws from it.
    assert network.vessel('EC1', 'out0') == 'HP1'
    assert network.vessel('EC2', 'out0') == 'HP1'
    assert network.vessel('EV1', 'in0') == 'HP1'
    # Unused optional inlets do not break the level resolution.
    assert network.vessel('LP1', 'vapor') == 'LP1'


def test_multi_inlet_vessel_runs_with_two_condensers():
    frames = solve_dynamic(compile_project(multi_inlet_station()), 120., 10.)
    last = frames[-1]
    assert last.variables['HP1.state.mass_kg'] > 0
    assert last.variables['EC1.heat_rejection_w'] > 0
    assert last.variables['EC2.heat_rejection_w'] > 0
    # One inventory per circuit: the extra inlet must not create a second pressure level.
    assert last.metrics['mass_residual_kg_circuit0'] < 1e-6
