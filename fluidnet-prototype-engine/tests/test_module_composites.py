from copy import deepcopy

import pytest

from fn_engine.composites import module_from_group
from fn_engine.compiler import compile_project
from fn_engine.models import ModuleInstance, Project, Connection, Endpoint, ModuleTestRequest, ModuleSaveRequest
from fn_engine.module_templates import create_template
from fn_engine.packages import ModuleStore
from fn_engine.bench import run_module_test
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady
from test_module_execution_network import network_for, ROOT


def group():
    module=create_template('managed_state','group_valve','Group valve')
    for parameter in module.parameters: parameter.runtime=True
    manual=network_for(module,2).project
    composite=module_from_group(manual,['D1','D2'],'two_valves','Two valves')
    ports=list(composite.composite.external_ports)
    project=Project(id='composite-test',name='Composite test',modules=[manual.modules[0],composite],
        instances=[manual.instances[0],ModuleInstance(id='C1',module_id=composite.id,name='Group'),manual.instances[-1]],
        connections=[Connection(id='in',source=Endpoint(instance_id='B1',port_id='out0'),target=Endpoint(instance_id='C1',port_id=ports[0])),
            Connection(id='out',source=Endpoint(instance_id='C1',port_id=ports[1]),target=Endpoint(instance_id='B2',port_id='out0'))])
    return manual,composite,project


def test_composed_two_valves_equal_manual_network_and_independent_states():
    manual,composite,project=group()
    reference=solve_steady(compile_project(manual))
    network=compile_project(project)
    frame=solve_steady(network)
    assert frame.variables['C1.main.mass_flow_kg_s']==pytest.approx(reference.variables['D1.main.mass_flow_kg_s'],rel=1e-6)
    assert frame.variables['C1.main.pressure_drop_pa']==pytest.approx(130000,abs=1)
    session=SimulationSession(network,.2,.1)
    try:
        session.initialize();session.advance();frame=session.advance()
        assert frame.variables['C1.state.D1.commit_count']==2
        assert frame.variables['C1.state.D2.commit_count']==2
        assert len(session.runners)==2
        assert session.runners['C1__D1'].state is not session.runners['C1__D2'].state
        session.set_parameter('C1','D1_opening_ratio',.4)
        assert network.parameters['C1__D1']['opening_ratio']==.4
    finally: session.close()


def test_nested_composite_expands_deterministically_and_can_publish_reload(tmp_path):
    manual,first,project=group()
    nested=module_from_group(project,['C1'],'nested_valves','Nested')
    result=run_module_test(ModuleTestRequest(module=nested,duration_s=.2,dt_s=.1))
    assert result.frame.valid and result.committed.state['children']
    store=ModuleStore(ROOT/'modules',tmp_path)
    release=store.save(ModuleSaveRequest(module=nested,expected_latest_version=0))
    restored=store.get(nested.id,1).module
    assert restored.composite==release.module.composite
    assert restored.definition_hash==release.module.definition_hash


@pytest.mark.parametrize('fault',['missing','version','duplicate','port'])
def test_invalid_dependency_or_mapping_rejected_before_execution(fault):
    _,composite,project=group()
    broken=deepcopy(project)
    module=broken.modules[-1]
    if fault=='missing': module.composite.modules=[]
    elif fault=='version': module.composite.children[0].version+=1
    elif fault=='duplicate': module.composite.children[1].id=module.composite.children[0].id
    else: next(iter(module.composite.external_ports.values())).port_id='missing'
    with pytest.raises(ValueError): compile_project(broken)
