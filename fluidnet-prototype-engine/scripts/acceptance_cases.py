"""Explicit engineering parameters for two topologies shown in Baselu tutorials.

The public screenshots do not provide complete model parameters or a numerical
reference solution. These are declared acceptance assumptions, not fitted values.
"""
from pathlib import Path

from fn_engine.catalog import catalog_map
from fn_engine.models import Connection, Endpoint, ModuleInstance, PortSpec, Project
from fn_engine.packages import load_module_package


def assemble(name, nodes, edges, extra=()):
    catalog = catalog_map()
    kinds = list(dict.fromkeys(kind for _, kind, _ in nodes))
    definitions = {k:catalog[k] for k in kinds if k in catalog}
    definitions.update({m.id:m for m in extra})
    endpoint = lambda text: Endpoint(instance_id=text.split(':')[0], port_id=text.split(':')[1])
    return Project(id=name, name=name, modules=list(definitions.values()),
        instances=[ModuleInstance(id=i, name=i, module_id=k, parameters=p) for i,k,p in nodes],
        connections=[Connection(id=f'e{i}', source=endpoint(a), target=endpoint(b)) for i,(a,b) in enumerate(edges)])


def parallel(opening=.8, python_valve=False):
    module = load_module_package(Path(__file__).resolve().parents[1] / 'modules' / 'programmable_valve')
    model = assemble('baselu-parallel', [
        ('B1','source',{'pressure_pa':201325}), ('P1','pump',{}), ('L0','pipe',{'length_m':10}),
        ('J0','junction',{}), ('L1','pipe',{'length_m':30}), ('V1',module.id if python_valve else 'valve',{'opening_ratio':opening}),
        ('L2','pipe',{'length_m':30}), ('J1','junction',{}), ('B2','source',{'pressure_pa':120000})],
        [('B1:out0','P1:in0'),('P1:out0','L0:in0'),('L0:out0','J0:in0'),
         ('J0:out0','L1:in0'),('L1:out0','J1:out0'),('J0:out1','V1:in0'),
         ('V1:out0','L2:in0'),('L2:out0','J1:out1'),('J1:in0','B2:out0')],
        [module] if python_valve else [])
    model.solver.hydraulic_method = 'sparse'
    return model


def tanks(charging=True):
    junction = catalog_map()['junction'].model_copy(deep=True)
    junction.ports.append(PortSpec(id='out2', label='第三支路', direction='out', required=False))
    nodes = [('B1','source',{'pressure_pa':101325}),('P1','pump',{}),('J0','junction',{}),
             ('J1','junction',{}),('L0','pipe',{'length_m':10}),('B2','source',{'pressure_pa':101325})]
    edges = [('B1:out0','P1:in0'),('P1:out0','J0:in0'),('J1:in0','L0:in0'),('L0:out0','B2:out0')]
    for i, port in enumerate(['out0','out1','out2'],1):
        nodes.extend([(f'VI{i}','valve',{'kv_m3_h':2,'opening_ratio':.6 if charging else 0}),
                      (f'T{i}','tank',{'area_m2':2,'height_m':3,'level_m':1}),
                      (f'VO{i}','valve',{'kv_m3_h':2,'opening_ratio':.6})])
        edges.extend([(f'J0:{port}',f'VI{i}:in0'),(f'VI{i}:out0',f'T{i}:in0'),
                      (f'T{i}:out0',f'VO{i}:in0'),(f'VO{i}:out0',f'J1:{port}')])
    model = assemble('baselu-tanks-charge' if charging else 'baselu-tanks-drain', nodes, edges, [junction])
    model.solver.hydraulic_method = 'sparse'
    return model
