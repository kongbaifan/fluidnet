import pytest

from fn_engine.compiler import compile_project
from fn_engine.models import ModuleInstance, Connection, Endpoint
from fn_engine.solver import solve_dynamic
from test_thermal import prototype
from test_run_control import custom_project


@pytest.mark.parametrize('name',['water-net','heat-loop','tank-control'])
def test_sparse_matches_dense(name):
    model=prototype(name)
    dense=solve_dynamic(compile_project(model),.2,.1)
    model.solver.hydraulic_method='sparse'
    sparse=solve_dynamic(compile_project(model),.2,.1)
    for a,b in zip(dense,sparse):
        for key,value in a.variables.items():
            if isinstance(value,(int,float)):
                assert b.variables[key]==pytest.approx(value,rel=1e-6,abs=1e-7),key
        assert b.metrics['mass_residual_kg_s']<=model.solver.mass_tolerance_kg_s


@pytest.mark.parametrize('parallelism',[1,2])
def test_batched_modules_keep_independent_state(parallelism):
    model=custom_project()
    for i in range(2,5):
        model.instances.append(ModuleInstance(id=f'V{i}',module_id=model.modules[-1].id,name=f'V{i}',parameters={'opening_ratio':i*.1,'kv_m3_h':10}))
        model.connections.extend([
            Connection(id=f'in{i}',source=Endpoint(instance_id='B1',port_id='out0'),target=Endpoint(instance_id=f'V{i}',port_id='in0')),
            Connection(id=f'out{i}',source=Endpoint(instance_id=f'V{i}',port_id='out0'),target=Endpoint(instance_id='B2',port_id='out0'))])
    # Endpoints may connect only once; merge them through explicit junctions instead.
    from fn_engine.catalog import catalog_map
    definition=catalog_map()['junction']
    definition.ports=[definition.ports[0].model_copy(update={'id':f'p{i}'}) for i in range(5)]
    model.modules.append(definition)
    for side in ('in','out'):
        model.instances.append(ModuleInstance(id='J'+side,module_id='junction',name=side))
    model.connections=[]
    for side,boundary,port in [('in','B1','in0'),('out','B2','out0')]:
        model.connections.append(Connection(id='b'+side,source=Endpoint(instance_id=boundary,port_id='out0'),target=Endpoint(instance_id='J'+side,port_id='p0')))
        for i in range(1,5):
            model.connections.append(Connection(id=side+str(i),source=Endpoint(instance_id='J'+side,port_id=f'p{i}'),target=Endpoint(instance_id=f'V{i}',port_id=port)))
    model.solver.batch_modules=False
    reference=solve_dynamic(compile_project(model),.2,.1)
    model.solver.batch_modules=True
    model.solver.module_parallelism=parallelism
    actual=solve_dynamic(compile_project(model),.2,.1)
    assert actual[-1].variables==reference[-1].variables
    assert actual[-1].variables['V1.state.throughput_kg']!=actual[-1].variables['V2.state.throughput_kg']
